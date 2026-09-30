"""D1 headless isolation, timing, coalescing, and lifecycle regressions."""

import gc
import unittest
import weakref
from types import SimpleNamespace
from unittest.mock import patch

from test_dopagaki import Canvas, Clock, Scheduler, headless_grid, RecordedEffect
from test_table_grid import EntryStub
from python_to_exe.editor.debug_csv import StickFrame, StickState
from python_to_exe.editor.dopagaki.effects import CellEffects
from python_to_exe.editor.dopagaki.micro import WidgetPulse, duration_for
from python_to_exe.editor.dopagaki.motion import Intensity
from python_to_exe.editor.dopagaki.ui import DopagakiEditorWindow
from python_to_exe.editor.dopagaki.widgets import FrameValues, DopagakiStickPreview
from python_to_exe.editor.tsv_syntax import CANDIDATES, CompletionState
from python_to_exe.editor.window import EditorWindow


class Widget:
    def __init__(self):
        self.options = dict(background="#293553", activebackground="#3c496b",
                            highlightbackground="#3b5272", foreground="#edf5ff",
                            font="fixed", image="original-icon", text="", command="original")
        self.mapped = False

    def cget(self, key):
        return self.options[key]

    def configure(self, **options):
        self.options.update(options)

    config = configure

    def pack(self, **_options):
        self.mapped = True

    def pack_forget(self):
        self.mapped = False


class Plot(Canvas):
    create_oval = Canvas.create_rectangle

    def delete(self, tag):
        if tag == "all":
            self.items.clear()
        else:
            super().delete(tag)


def frame_values(effects, text="Start: 0f | Duration: 1f | End: 0f | Total: 9f"):
    display = FrameValues.__new__(FrameValues)
    display._effects = weakref.ref(effects)
    display._values = None
    display._text = ""
    display.fields, display.hint = Widget(), Widget()
    display.prefixes = [Widget() for _ in range(4)]
    display.value_labels = [Widget() for _ in range(4)]
    display.configure(text=text)
    return display


class MicroTests(unittest.TestCase):
    def setUp(self):
        self.scheduler, self.clock, self.canvas = Scheduler(), Clock(), Plot()
        self.effects = CellEffects(self.scheduler, self.canvas, clock=self.clock)

    def tearDown(self):
        self.effects.close()

    def expire(self):
        self.clock.now += 1.0
        if self.scheduler.jobs:
            self.scheduler.run_next()
        self.assertEqual(self.scheduler.jobs, {})
        self.assertIsNone(self.effects.motion.effect)

    def test_shared_callback_preserves_other_targets_absolute_lifetimes(self):
        first, second = RecordedEffect(), RecordedEffect()
        self.effects.play_effect("first", first)
        self.clock.now += 0.10
        self.effects.play_effect("second", second)
        self.assertEqual(len(self.scheduler.jobs), 1)
        self.assertAlmostEqual(first.progress[-1], 0.10 / first.duration)
        self.clock.now += 0.09
        self.scheduler.run_next()
        self.assertEqual(first.finishes, 1)
        self.assertIsNone(self.effects.effect_for("first"))
        self.assertIs(self.effects.effect_for("second"), second)
        self.assertAlmostEqual(second.progress[-1], 0.5)
        self.expire()
        self.assertEqual(second.finishes, 1)

    def test_replace_restores_button_styles_before_capturing_new_baseline(self):
        widget = Widget()
        original = dict(widget.options)
        for _ in range(300):
            self.effects.pulse_widget("palette", widget, "palette")
            self.assertEqual(len(self.scheduler.jobs), 1)
            self.assertEqual(len(self.effects.motion.effect.tracks), 1)
            self.assertEqual(widget.cget("image"), original["image"])
            self.assertEqual(widget.cget("font"), original["font"])
        self.expire()
        self.assertEqual(widget.options, original)

    def test_removing_longest_target_shortens_batch_without_extra_idle_ticks(self):
        first, second = RecordedEffect(), RecordedEffect()
        self.effects.play_effect("first", first)
        self.clock.now += 0.10
        self.effects.play_effect("second", second)
        self.effects.remove("second")
        self.clock.now += 0.09
        self.scheduler.run_next()
        self.assertEqual(first.finishes, 1)
        self.assertEqual(second.finishes, 1)
        self.assertIsNone(self.effects.motion.effect)
        self.assertEqual(self.scheduler.jobs, {})

    def test_off_cancels_all_targets_immediately_and_does_not_change_widget_content(self):
        widget = Widget()
        original = dict(widget.options)
        self.effects.pulse_widget("palette", widget, "palette")
        self.effects.pulse_ring(0, self.canvas, 126)
        stale = next(iter(self.scheduler.jobs.values()))[1]
        self.effects.motion.set_intensity("OFF")
        stale()
        self.effects.pulse_widget("page", widget, "page", ink=True)
        self.effects.pulse_ring(1, self.canvas, 126)
        display = frame_values(self.effects)
        display.configure(text="Start: 1f | Duration: 2f | End: 2f | Total: 9f")
        self.assertEqual(display._values, ("1f", "2f", "2f", "9f"))
        self.assertEqual(widget.options, original)
        self.assertEqual(self.canvas.items, {})
        self.assertEqual(self.scheduler.jobs, {})

    def test_levels_change_amplitude_and_duration_without_geometry_changes(self):
        widget = Widget()
        colors, durations = [], []
        for level in (Intensity.LOW, Intensity.MID, Intensity.FULL):
            self.effects.motion.set_intensity(level)
            self.effects.pulse_widget("palette", widget, "palette")
            colors.append(widget.cget("background"))
            durations.append(self.effects.effect_for("palette").duration)
            self.assertEqual(widget.cget("font"), "fixed")
            self.assertNotIn("width", widget.options)
        self.assertEqual(len(set(colors)), 3)
        self.assertEqual(durations, sorted(set(durations)))
        for level in (Intensity.LOW, Intensity.MID, Intensity.FULL):
            self.assertTrue(0.150 <= duration_for(level, "cell") <= 0.220)
            self.assertTrue(0.100 <= duration_for(level, "frame") <= 0.250)

    def test_target_cap_and_destroy_release_every_primitive_and_stale_callback(self):
        references = []
        widgets = [Widget() for _ in range(30)]
        original = [dict(widget.options) for widget in widgets]
        for index in range(30):
            effect = WidgetPulse(widgets[index], 1.0, 0.18)
            references.append(weakref.ref(effect))
            self.effects.play_effect(str(index), effect)
            self.assertLessEqual(len(self.effects.motion.effect.tracks), 8)
            self.assertEqual(len(self.scheduler.jobs), 1)
        stale = next(iter(self.scheduler.jobs.values()))[1]
        del effect
        self.effects.close()
        stale()
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))
        self.assertEqual([widget.options for widget in widgets], original)
        self.assertEqual(self.scheduler.jobs, {})

    def test_frame_only_changed_values_pulse_and_readable_text_is_identical(self):
        display = frame_values(self.effects)
        self.assertEqual(self.scheduler.jobs, {})
        old = [dict(value.options) for value in display.value_labels]
        message = "Start: 2f | Duration: 1f | End: 2f | Total: 9f"
        display.configure(text=message)
        self.assertEqual(display.cget("text"), message)
        self.assertNotEqual(display.value_labels[0].cget("foreground"), old[0]["foreground"])
        self.assertEqual(display.value_labels[1].options, old[1])
        self.assertNotEqual(display.value_labels[2].cget("foreground"), old[2]["foreground"])
        self.assertEqual(display.value_labels[3].options, old[3])
        font = [value.cget("font") for value in display.value_labels]
        self.expire()
        self.assertEqual([value.cget("font") for value in display.value_labels], font)
        self.assertEqual(display.cget("text"), message)
        display.configure(text=message)
        self.assertEqual(self.scheduler.jobs, {})
        large = "Start: 2f | Duration: 999999999f | End: 1000000000f | Total: 1000000001f"
        display.configure(text=large)
        self.assertEqual(display.cget("text"), large)
        self.assertEqual([value.cget("font") for value in display.value_labels], font)
        display.configure(text="Frame: updating...")
        self.assertEqual(display.cget("text"), "Frame: updating...")

    def test_stick_redraw_preserves_resolved_values_and_previous_three_samples(self):
        preview = DopagakiStickPreview.__new__(DopagakiStickPreview)
        preview._effects = weakref.ref(self.effects)
        preview.plots = [self.canvas, Plot()]
        preview.values = [Widget(), Widget()]
        preview.frame = 3
        state = StickState(16384, 32767, 0.75, 90)
        preview.samples = tuple(StickFrame(frame, state, state) for frame in (3, 2, 1, 0))
        before = preview.frame, preview.samples
        preview._draw(0)
        original = dict(preview.values[0].options)
        self.effects.pulse_ring(0, self.canvas, 126)
        for _ in range(300):
            preview._draw(0)  # Real shared draw deletes/rebuilds plot items.
            self.effects.pulse_ring(0, self.canvas, 126)
            self.assertEqual(sum(item.get("tags") == "dopagaki_ring"
                                 for item in self.canvas.items.values()), 1)
        self.assertEqual((preview.frame, preview.samples), before)
        self.assertEqual(preview.values[0].options, original)
        samples = [item for item in self.canvas.items.values() if isinstance(item.get("tags"), tuple)]
        self.assertEqual(len(samples), 4)
        self.expire()
        self.assertFalse(any(item.get("tags") == "dopagaki_ring" for item in self.canvas.items.values()))


class HookTests(unittest.TestCase):
    def test_x11_shift_tab_reuses_the_existing_entry_binding(self):
        grid = headless_grid()
        bindings = {}

        def bind(key, callback=None):
            if callback is None:
                return bindings[key]
            bindings[key] = callback

        entry = SimpleNamespace(bind=bind)
        grid._bind_entry_navigation(entry)
        self.assertIs(bindings["<ISO_Left_Tab>"], bindings["<Shift-Tab>"])
        grid.close_effects()

    def test_all_apply_paths_emit_commit_only_after_actual_accepted_cell_change(self):
        grid = headless_grid()
        grid._draw_visible()
        grid.on_change = lambda *_args: True
        entry = SimpleNamespace(get=lambda: "1", bell=lambda: None)
        grid._editor = entry
        self.assertTrue(grid._apply_editor_value())
        self.assertIsNone(grid.effects.effect_for("commit"))
        entry.get = lambda: "2"
        self.assertTrue(grid._apply_editor_value())
        self.assertIsNotNone(grid.effects.effect_for("commit"))
        accepted = grid.effects.effect_for("commit")
        started = grid.effects.motion._started_at
        grid.clock.now += 0.10
        self.assertTrue(grid._apply_editor_value())  # Same accepted contents.
        self.assertIs(grid.effects.effect_for("commit"), accepted)
        self.assertEqual(grid.effects.motion._started_at, started)
        grid.effects.motion.clear()
        grid.on_change = lambda *_args: False
        entry.get = lambda: "3"
        self.assertFalse(grid._apply_editor_value())
        self.assertIsNone(grid.effects.effect_for("commit"))
        self.assertEqual(grid.model.cell(0, 0), "2")
        entry.get = lambda: "bad\tvalue"
        self.assertFalse(grid._apply_editor_value())
        self.assertIsNone(grid.effects.effect_for("commit"))
        grid.close_effects()

    def test_three_hundred_changed_commits_replace_one_feedback_and_expire(self):
        grid = headless_grid()
        grid.on_change = lambda *_args: True
        grid._editor = SimpleNamespace(get=lambda: "1", bell=lambda: None)
        references = []
        for index in range(300):
            grid._editor.get = lambda index=index: str(index + 2)
            self.assertTrue(grid._apply_editor_value())
            references.append(weakref.ref(grid.effects.effect_for("commit")))
            self.assertEqual(len(grid.scheduler.jobs), 1)
            self.assertEqual(len(grid.canvas.effects), 1)
        grid.clock.now += 1
        grid.scheduler.run_next()
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))
        self.assertEqual(grid.canvas.effects, [])
        self.assertEqual(grid.scheduler.jobs, {})
        grid.close_effects()

    def test_palette_wrapper_preserves_all_candidate_text_placeholders_and_icons(self):
        grid = headless_grid()
        grid._completion, grid._popup = CompletionState(), None
        grid._editor = EntryStub(None)
        grid.selected = (0, 3)
        editor = DopagakiEditorWindow.__new__(DopagakiEditorWindow)
        editor.table_grid = grid
        columns = []
        editor.stick_preview = SimpleNamespace(pulse=columns.append)
        for candidate in CANDIDATES:
            grid._editor.delete(0, "end")
            grid._editor.selection_clear()
            button = Widget()
            calls = []
            button.tk = SimpleNamespace(call=lambda command: calls.append(command) or
                                        grid.insert_candidate(candidate))
            with patch.object(EditorWindow, "_palette_button", return_value=button):
                editor._palette_button(None, candidate)
            button.cget("command")()
            self.assertEqual(calls, ["original"])
            self.assertEqual(grid._editor.get(), candidate.text)
            self.assertEqual(grid._editor.selected_range, candidate.select)
            self.assertEqual(button.cget("image"), "original-icon")
            self.assertEqual(grid.model.cell(0, 3), "")
            grid.effects.motion.clear()
        self.assertEqual(columns, [0 if item.category == "left_stick" else 1
                                   for item in CANDIDATES if item.category in ("left_stick", "right_stick")])
        grid.close_effects()

    def test_page_switch_preserves_document_history_selection_entry_and_scroll(self):
        grid = headless_grid()
        editor = DopagakiEditorWindow.__new__(DopagakiEditorWindow)
        editor.table_grid = grid
        editor._palette_pages = [(Widget(), Plot()), (Widget(), Plot())]
        editor._palette_page = 1
        editor._palette_page_label = Widget()
        editor._palette_previous, editor._palette_next = Widget(), Widget()
        saved = {}
        editor.settings = SimpleNamespace(update=lambda **values: saved.update(values))
        editor.document = SimpleNamespace(text="unchanged", modified=False, undo=["history"])
        grid._editor = EntryStub(None)
        grid._editor.insert(0, "pending")
        grid.selection.move_to(1, 2, extend=True)
        state = (dict(editor.document.__dict__), grid.selection.anchor, grid.selection.active,
                 grid._editor, grid._editor.get())
        for index in range(100):
            editor._show_palette_page(2 if index % 2 == 0 else 1)
            self.assertEqual(len(grid.scheduler.jobs), 1)
        self.assertEqual((dict(editor.document.__dict__), grid.selection.anchor, grid.selection.active,
                          grid._editor, grid._editor.get()), state)
        self.assertEqual(saved["editor_palette_page"], 0)
        self.assertEqual([canvas.origin_y for _page, canvas in editor._palette_pages], [0, 0])
        grid.clock.now += 1
        grid.scheduler.run_next()
        self.assertEqual(grid.scheduler.jobs, {})
        grid.close_effects()


if __name__ == "__main__":
    unittest.main()
