"""Headless D0 rendering, lifecycle, and isolation regression checks."""

import gc
import json
import subprocess
import sys
import tempfile
import unittest
import weakref
from pathlib import Path
from types import SimpleNamespace
from tkinter import StringVar, Tcl, TclError
from unittest.mock import patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp
from python_to_exe.dopagaki_app import DopagakiApp
from python_to_exe.editor import theme as normal_theme
from python_to_exe.editor.column_layout import ColumnLayout
from python_to_exe.editor.document import EditorDocument
from python_to_exe.editor.dopagaki import theme
from python_to_exe.editor.dopagaki.effects import ActiveCellPulse, CellEffects
from python_to_exe.editor.dopagaki.motion import Intensity, MotionController
from python_to_exe.editor.dopagaki.ui import DopagakiEditorWindow, DopagakiTableGrid
from python_to_exe.editor.grid import TableGrid
from python_to_exe.editor.table_model import CellSelection, TableModel
from python_to_exe.editor.window import EditorWindow


class Scheduler:
    def __init__(self):
        self.jobs = {}
        self.serial = 0
        self.destroyed = False

    def after(self, delay, callback):
        if self.destroyed:
            raise TclError("destroyed")
        self.serial += 1
        job = f"after#{self.serial}"
        self.jobs[job] = (delay, callback)
        return job

    def after_cancel(self, job):
        self.jobs.pop(job, None)
        if self.destroyed:
            raise TclError("destroyed")

    def run_next(self):
        job = next(iter(self.jobs))
        _, callback = self.jobs.pop(job)
        callback()


class Clock:
    now = 50.0

    def __call__(self):
        return self.now


class Canvas:
    """Canvas-item stub: tracks draws separately from grid redraws and focus."""

    def __init__(self):
        self.items = {}
        self.serial = 0
        self.origin_x = self.origin_y = 0
        self.width, self.height = 800, 500
        self.focus_count = 0
        self.grid_redraws = 0

    def create_rectangle(self, *coords, **options):
        self.serial += 1
        self.items[self.serial] = dict(coords=coords, **options)
        return self.serial

    create_text = create_rectangle
    create_line = create_rectangle

    def coords(self, item, *coords):
        self.items[item]["coords"] = coords

    def itemconfigure(self, item, **options):
        self.items[item].update(options)

    def tag_raise(self, item):
        assert item in self.items

    def delete(self, tag):
        if tag == "grid":
            self.grid_redraws += 1
        self.items = {key: value for key, value in self.items.items()
                      if key != tag and value.get("tags") != tag}

    def canvasx(self, value):
        return self.origin_x + value

    def canvasy(self, value):
        return self.origin_y + value

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def configure(self, **options):
        self.scrollregion = options.get("scrollregion")

    def focus_set(self):
        self.focus_count += 1

    @property
    def effects(self):
        return [item for item in self.items.values() if item.get("tags") == "dopagaki_effect"]


class RecordedEffect:
    duration = 0.18

    def __init__(self):
        self.progress = []
        self.finishes = 0

    def render(self, progress):
        self.progress.append(progress)

    def finish(self):
        self.finishes += 1


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.scheduler, self.clock = Scheduler(), Clock()
        self.motion = MotionController(self.scheduler, clock=self.clock)

    def test_idle_and_completed_animation_leave_no_callback_or_effect(self):
        self.assertEqual(self.scheduler.jobs, {})
        effect = RecordedEffect()
        self.assertTrue(self.motion.play(effect))
        self.assertEqual(effect.progress, [0])  # Feedback begins immediately.
        self.assertEqual(len(self.scheduler.jobs), 1)
        self.clock.now += 0.09
        self.scheduler.run_next()
        self.assertAlmostEqual(effect.progress[-1], 0.5)
        self.assertEqual(len(self.scheduler.jobs), 1)
        self.clock.now += 0.10
        self.scheduler.run_next()
        self.assertEqual(effect.progress[-1], 1)
        self.assertEqual(effect.finishes, 1)
        self.assertIsNone(self.motion.effect)
        self.assertFalse(self.motion.pending)
        self.assertEqual(self.scheduler.jobs, {})

    def test_delayed_tick_skips_missed_frames(self):
        effect = RecordedEffect()
        self.motion.play(effect)
        self.clock.now += 20.0
        self.scheduler.run_next()
        self.assertEqual(effect.progress, [0.0, 1.0])
        self.assertEqual(self.scheduler.jobs, {})

    def test_default_clock_is_monotonic(self):
        with patch("python_to_exe.editor.dopagaki.motion.time.monotonic", side_effect=[10.0, 10.09]):
            motion = MotionController(self.scheduler)
            effect = RecordedEffect()
            motion.play(effect)
            self.scheduler.run_next()
            self.assertAlmostEqual(effect.progress[-1], 0.5)
            motion.close()

    def test_replacement_rejects_old_callback_without_touching_new_job(self):
        first, second = RecordedEffect(), RecordedEffect()
        self.motion.play(first)
        stale = next(iter(self.scheduler.jobs.values()))[1]
        self.motion.play(second)
        jobs = dict(self.scheduler.jobs)
        stale()
        self.assertEqual(first.finishes, 1)
        self.assertEqual(second.progress, [0])
        self.assertEqual(self.scheduler.jobs, jobs)
        self.assertTrue(self.motion.pending)
        self.motion.close()

    def test_off_cancels_immediately_and_rejects_new_motion(self):
        effect = RecordedEffect()
        self.motion.play(effect)
        stale = next(iter(self.scheduler.jobs.values()))[1]
        self.motion.set_intensity("OFF")
        stale()
        self.assertEqual(effect.finishes, 1)
        self.assertEqual(self.scheduler.jobs, {})
        rejected = RecordedEffect()
        self.assertFalse(self.motion.play(rejected))
        self.assertEqual(rejected.progress, [])
        self.assertEqual(rejected.finishes, 1)
        self.motion.set_intensity("LOW")
        self.assertTrue(self.motion.play(RecordedEffect()))
        self.motion.close()

    def test_close_is_idempotent_and_old_callback_cannot_render(self):
        effect = RecordedEffect()
        self.motion.play(effect)
        stale = next(iter(self.scheduler.jobs.values()))[1]
        self.motion.close()
        self.motion.close()
        stale()
        self.assertEqual(effect.progress, [0])
        self.assertEqual(effect.finishes, 1)
        self.assertEqual(self.scheduler.jobs, {})
        self.assertFalse(self.motion.play(RecordedEffect()))

    def test_scheduler_and_callback_do_not_hold_editor_or_controller_alive(self):
        self.motion.play(RecordedEffect())
        stale = next(iter(self.scheduler.jobs.values()))[1]
        scheduler_ref, motion_ref = weakref.ref(self.scheduler), weakref.ref(self.motion)
        del self.scheduler
        gc.collect()
        self.assertIsNone(scheduler_ref())
        del self.motion
        gc.collect()
        self.assertIsNone(motion_ref())
        stale()

    def test_dead_tk_scheduler_and_renderer_cleanup(self):
        self.scheduler.destroyed = True
        effect = RecordedEffect()
        self.assertFalse(self.motion.play(effect))
        self.assertEqual(effect.finishes, 1)
        self.assertIsNone(self.motion.effect)
        self.scheduler.destroyed = False
        motion = MotionController(self.scheduler, clock=self.clock)
        with patch.object(RecordedEffect, "render", side_effect=TclError("canvas destroyed")):
            effect = RecordedEffect()
            self.assertFalse(motion.play(effect))
            self.assertEqual(effect.finishes, 1)
            self.assertEqual(self.scheduler.jobs, {})

    def test_invalid_lifetimes_and_render_failure_release_effects(self):
        for duration in (0, -1, float("inf"), float("nan")):
            effect = RecordedEffect()
            effect.duration = duration
            with self.assertRaises(ValueError):
                self.motion.play(effect)
            self.assertEqual(effect.finishes, 1)
            self.assertEqual(self.scheduler.jobs, {})
        with patch.object(RecordedEffect, "render", side_effect=ValueError("broken effect")):
            effect = RecordedEffect()
            with self.assertRaises(ValueError):
                self.motion.play(effect)
            self.assertIsNone(self.motion.effect)
            self.assertEqual(effect.finishes, 1)


class EffectTests(unittest.TestCase):
    def setUp(self):
        self.canvas, self.scheduler, self.clock = Canvas(), Scheduler(), Clock()
        self.effects = CellEffects(self.scheduler, self.canvas, clock=self.clock)
        self.box = (50, 26, 158, 46)

    def test_initial_draw_and_same_cell_redraw_are_idle(self):
        for _ in range(100):
            self.effects.sync_cell((0, 0), self.box)
        self.assertEqual(self.canvas.effects, [])
        self.assertEqual(self.scheduler.jobs, {})

    def test_pulse_only_updates_its_canvas_item_without_redrawing_grid_or_focus(self):
        self.effects.sync_cell((0, 0), self.box)
        self.effects.sync_cell((0, 1), self.box)
        self.assertEqual(len(self.canvas.effects), 1)
        self.assertEqual(self.canvas.effects[0]["fill"], "")
        self.clock.now += 0.08
        self.scheduler.run_next()
        self.assertEqual(len(self.canvas.effects), 1)
        self.assertEqual(self.canvas.grid_redraws, 0)
        self.assertEqual(self.canvas.focus_count, 0)
        self.clock.now += 0.20
        self.scheduler.run_next()
        self.assertEqual(self.canvas.effects, [])
        self.assertEqual(self.scheduler.jobs, {})

    def test_intensities_change_pulse_amplitude_and_off_creates_nothing(self):
        widths = []
        for level in Intensity:
            self.effects.motion.set_intensity(level)
            self.effects.sync_cell((0, 0), self.box)
            self.effects.sync_cell((0, 1), self.box)
            if level == Intensity.OFF:
                self.assertEqual(self.canvas.effects, [])
                self.assertEqual(self.scheduler.jobs, {})
            else:
                widths.append(self.canvas.effects[0]["width"])
        self.assertEqual(widths, sorted(set(widths)))
        self.effects.close()

    def test_scroll_relocates_and_hides_pulse_without_restarting_timer(self):
        self.effects.sync_cell((0, 0), self.box)
        self.effects.sync_cell((0, 1), self.box)
        jobs = dict(self.scheduler.jobs)
        moved = (60, 40, 190, 60)
        self.effects.sync_cell((0, 1), moved)
        self.assertEqual(self.canvas.effects[0]["coords"], moved)
        self.effects.sync_cell((0, 1), None)
        self.assertEqual(self.canvas.effects[0]["state"], "hidden")
        self.effects.sync_cell((0, 1), moved)
        self.assertEqual(self.canvas.effects[0]["state"], "normal")
        self.assertEqual(self.scheduler.jobs, jobs)
        self.effects.close()

    def test_one_thousand_cell_moves_remain_bounded_and_expire_collectably(self):
        references = []
        self.effects.sync_cell((0, 0), self.box)
        for column in range(1, 1001):
            self.effects.sync_cell((0, column), self.box)
            references.append(weakref.ref(self.effects.motion.effect))
            self.assertEqual(len(self.canvas.effects), 1)
            self.assertEqual(len(self.scheduler.jobs), 1)
        self.clock.now += 1.0
        self.scheduler.run_next()
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))
        self.assertEqual(self.canvas.items, {})
        self.assertEqual(self.scheduler.jobs, {})


def headless_grid(grid_class=DopagakiTableGrid):
    grid = grid_class.__new__(grid_class)
    grid.canvas = Canvas()
    grid.model = TableModel("1\ta\r\n2\tb\n")
    grid.selection = CellSelection()
    grid.font = SimpleNamespace(measure=lambda value: len(value) * 8)
    grid.row_height = grid.header_height = 24
    grid.gutter_width = 48
    grid.column_width = 160
    grid._columns = ColumnLayout(160)
    grid._draw_job = grid._scroll_region = grid._editor = None
    grid._entry_value = grid._entry_value_trace = None
    grid._selection_axis = None
    grid.display_row_count, grid.display_column_count = 21, 8
    grid.winfo_exists = grid.winfo_ismapped = lambda: True
    grid.scheduler = Scheduler()
    grid.after_cancel = grid.scheduler.after_cancel
    grid.after = grid.scheduler.after
    grid.after_idle = lambda callback: grid.scheduler.after(0, callback)
    grid.on_select = lambda: None
    grid.clock = Clock()
    if grid_class is DopagakiTableGrid:
        grid.effects = CellEffects(grid, grid.canvas, clock=grid.clock)
    return grid


class IntegrationTests(unittest.TestCase):
    def test_closed_grid_releases_tcl_entry_trace_without_a_tk_window(self):
        # Tcl alone needs no display. A real variable trace keeps its callback
        # (and the grid/editor captured by it) alive until explicitly removed.
        interpreter = Tcl()
        grid = headless_grid()
        editor = DopagakiEditorWindow.__new__(DopagakiEditorWindow)
        grid.on_select = editor._update_status

        def install_entry_trace(target):
            target._entry_value = StringVar(interpreter)
            target._entry_value_trace = target._entry_value.trace_add(
                "write", lambda *_: target._notify_edit_change())
            return target._entry_value_trace

        command = install_entry_trace(grid)
        self.assertTrue(interpreter.call("info", "commands", command))
        references = weakref.ref(grid), weakref.ref(editor)
        grid._on_destroy(SimpleNamespace(widget=grid))
        self.assertFalse(interpreter.call("info", "commands", command))
        del grid, editor
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))

    def test_themes_are_isolated_and_import_needs_no_display(self):
        result = subprocess.run([sys.executable, "-c",
                                 "import sys; from python_to_exe.editor.dopagaki import theme; "
                                 "assert 'tkinter' not in sys.modules"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        normal_colors = dict(normal_theme.COLORS)
        self.assertIs(EditorWindow.ui_theme, normal_theme)
        self.assertIs(TableGrid.ui_theme, normal_theme)
        self.assertIsNone(TASConverterApp.editor_class)
        self.assertIs(DopagakiApp.editor_class, DopagakiEditorWindow)
        self.assertNotEqual(theme.COLORS["app_background"], normal_colors["app_background"])
        self.assertEqual(theme.TABLE_COLORS["panel_background"], normal_colors["panel_background"])
        self.assertEqual(theme.TABLE_COLORS["text"], normal_colors["text"])
        for options in (theme.button_options(), theme.entry_options(), theme.label_options()):
            self.assertTrue({"command", "text", "state", "undo", "variable"}.isdisjoint(options))
        self.assertEqual(normal_theme.COLORS, normal_colors)

    def test_shared_editor_factory_preserves_all_conversion_and_analysis_callbacks(self):
        captured = []
        app = SimpleNamespace(editor_class=lambda *args, **kwargs: captured.append((args, kwargs)),
                              language="ja", _editor_saved=object(), _convert_editor_file=object(),
                              _validate_editor_snapshot=object(), _analyze_editor_snapshot=object(),
                              _busy=lambda: False)
        TASConverterApp._create_editor(app, initial_path="example.tsv", recovery="snapshot")
        args, options = captured[0]
        self.assertEqual(args, (app,))
        self.assertEqual(options["initial_path"], "example.tsv")
        self.assertEqual(options["recovery"], "snapshot")
        self.assertIs(options["on_convert"], app._convert_editor_file)
        self.assertIs(options["on_validate"], app._validate_editor_snapshot)
        self.assertIs(options["on_analyze"], app._analyze_editor_snapshot)
        self.assertTrue(options["can_convert"]())
        app._busy = lambda: True
        self.assertFalse(options["can_convert"]())

    def test_pulse_and_intensity_preserve_document_modified_history_and_selection(self):
        grid = headless_grid()
        document = EditorDocument()
        document.set_text(grid.model.to_text())
        editor = SimpleNamespace(document=document, table_grid=grid,
                                 undo=["older text"], redo=["newer text"],
                                 frame_data=object(), line_map=object())
        grid._draw_visible()
        grid.selection.move_to(1, 1, extend=True)
        before = (dict(document.__dict__), grid.model.to_text(), grid.selection.anchor,
                  grid.selection.active, grid.selection.bounds, document.modified,
                  editor.undo[:], editor.redo[:], editor.frame_data, editor.line_map)
        grid._draw_visible()
        redraws = grid.canvas.grid_redraws
        grid.clock.now += 0.09
        grid.scheduler.run_next()
        self.assertEqual(grid.canvas.grid_redraws, redraws)
        for level in Intensity:
            editor._motion_intensity = SimpleNamespace(get=lambda level=level: level.value)
            editor.settings = SimpleNamespace(update=lambda **_values: None)
            DopagakiEditorWindow._intensity_changed(editor)
        after = (dict(document.__dict__), grid.model.to_text(), grid.selection.anchor,
                 grid.selection.active, grid.selection.bounds, document.modified,
                 editor.undo[:], editor.redo[:], editor.frame_data, editor.line_map)
        self.assertEqual(after, before)
        self.assertEqual(grid.canvas.effects, [])
        self.assertEqual(grid.scheduler.jobs, {})

    def test_off_leaves_static_dopagaki_theme_and_normal_grid_appearance_is_unchanged(self):
        normal = headless_grid(TableGrid)
        normal._draw_visible()
        normal_items = dict(normal.canvas.items)
        grid = headless_grid()
        grid.effects.motion.set_intensity("OFF")
        grid._draw_visible()
        grid.selection.move_to(1, 1)
        grid._draw_visible()
        self.assertEqual(grid.canvas.effects, [])
        self.assertEqual(grid.scheduler.jobs, {})
        self.assertIn(theme.TABLE_COLORS["active_selection_outline"],
                      [item.get("outline") for item in grid.canvas.items.values()])
        normal._draw_visible()
        self.assertEqual(list(normal.canvas.items.values()), list(normal_items.values()))

    def test_pulse_tracks_scrolling_and_resize_without_crossing_fixed_headers(self):
        grid = headless_grid()
        grid._draw_visible()
        grid.selection.move_to(1, 1)
        grid._draw_visible()
        grid.canvas.origin_x = 180
        grid.canvas.origin_y = 32
        grid.columns.set_width(1, 220)
        grid._draw_visible()
        x1, y1, x2, y2 = grid.canvas.effects[0]["coords"]
        self.assertGreaterEqual(x1, grid.canvas.origin_x + grid.gutter_width + 2)
        self.assertGreaterEqual(y1, grid.canvas.origin_y + grid.header_height + 2)
        self.assertLessEqual(x2, grid.canvas.origin_x + grid.canvas.width - 2)
        self.assertLessEqual(y2, grid.canvas.origin_y + grid.canvas.height - 2)
        grid.canvas.origin_y = 300
        grid._draw_visible()
        self.assertEqual(grid.canvas.effects[0]["state"], "hidden")
        grid.close_effects()

    def test_unmap_and_destroy_cancel_pulse_and_release_grid_and_editor_thirty_times(self):
        references = []
        for _ in range(30):
            grid = headless_grid()
            grid._draw_visible()
            grid.selection.move_to(1, 1)
            grid._draw_visible()
            effects = grid.effects
            stale = next(iter(grid.scheduler.jobs.values()))[1]
            editor = DopagakiEditorWindow.__new__(DopagakiEditorWindow)
            editor.table_grid = grid
            editor._flush_workspace = lambda: None
            editor._palette_icons, editor._theme_fonts = {}, {}
            editor._recovery_store = None
            editor._gutter_job = editor._highlight_job = editor._position_job = None
            editor._position_poll_job = editor._recovery_job = None
            DopagakiTableGrid._pause_effects(grid, SimpleNamespace(widget=object()))
            self.assertTrue(grid.scheduler.jobs)
            DopagakiTableGrid._pause_effects(grid, SimpleNamespace(widget=grid))
            self.assertEqual(grid.scheduler.jobs, {})
            grid.selection.move_to(0, 1)
            grid._draw_visible()
            DopagakiEditorWindow._on_destroy(editor, SimpleNamespace(widget=object()))
            self.assertIsNotNone(grid.effects)
            DopagakiEditorWindow._on_destroy(editor, SimpleNamespace(widget=editor))
            stale()
            self.assertIsNone(grid.effects)
            self.assertEqual(grid.scheduler.jobs, {})
            self.assertEqual(grid.canvas.effects, [])
            references.extend((weakref.ref(editor), weakref.ref(grid), weakref.ref(effects.motion)))
            del editor, grid, effects
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))

    def test_intensity_persists_in_user_settings_and_invalid_values_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = AppSettings(path)
            self.assertEqual(settings.get("dopagaki_intensity"), "MID")
            for level in Intensity:
                settings.update(dopagaki_intensity=level.value)
                self.assertEqual(AppSettings(path).get("dopagaki_intensity"), level.value)
            for value in (None, "full", "HIGH", True, 1, [], {}):
                path.write_text(json.dumps({"version": 1, "dopagaki_intensity": value}), encoding="utf-8")
                self.assertEqual(AppSettings(path).get("dopagaki_intensity"), "MID")


if __name__ == "__main__":
    unittest.main()
