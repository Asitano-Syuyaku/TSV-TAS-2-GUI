"""Dopagaki3 Phase 2 (dopagaki3.md §15 P2): HEAT, FX engine, FEVER HUD, settings."""

import gc
import tempfile
import time
import tkinter as tk
import unittest
import weakref
from pathlib import Path
from types import SimpleNamespace

from python_to_exe.app_settings import AppSettings
from python_to_exe.editor import theme
from python_to_exe.editor.dopa import fx as fxmod
from python_to_exe.editor.dopa.heat import (HeatState, extra_tier, format_dopa, frames_as_time,
                                            intensity, shout_tier)
from python_to_exe.editor.window import EditorWindow


SCRIPT = "5\tls(90)\n1\ta\trs(0)\n2\tzl\n"


class HeatTests(unittest.TestCase):
    def test_intensity_ratchet_and_extra(self):
        self.assertAlmostEqual(intensity(0), 0.08)
        self.assertAlmostEqual(intensity(29), 1.0)
        self.assertEqual((intensity(30), extra_tier(30)), (1.0, 1))
        self.assertAlmostEqual(intensity(40), 1.1)
        self.assertAlmostEqual(intensity(500), 1.5)
        values = [intensity(i) for i in range(60)]
        self.assertEqual(values, sorted(values))

    def test_combo_window_gain_and_never_dropping_heat(self):
        heat = HeatState()
        first = heat.productive(10.0)
        self.assertEqual((first.combo, first.gain), (1, round(10 * 1.05 * (1 + 2 * intensity(1)))))
        self.assertEqual(heat.productive(12.9).combo, 2)
        self.assertTrue(heat.combo_alive(13.0))
        self.assertEqual(heat.productive(16.0).combo, 1)  # More than 3.0s later.
        actions, dopa = heat.actions, heat.dopa
        heat.reset_combo()
        self.assertEqual((heat.actions, heat.dopa, heat.combo), (actions, dopa, 0))

    def test_shout_ladder(self):
        self.assertEqual([shout_tier(n) for n in (5, 10, 20, 30, 50, 75, 100, 150, 200)],
                         [0, 1, 2, 3, 4, 5, 6, 6, 6])
        self.assertIsNone(shout_tier(4))
        self.assertIsNone(shout_tier(120))

    def test_confirmed_totals_baseline_delta_and_single_milestones(self):
        heat = HeatState()
        opened = heat.confirmed_total(5000)  # Opening a long script is no achievement.
        self.assertEqual((opened.delta, opened.milestone), (None, None))
        self.assertEqual(heat.confirmed_total(4990).delta, -10)
        crossed = heat.confirmed_total(12000)
        self.assertEqual((crossed.delta, crossed.milestone), (7010, 10000))  # Highest one.
        heat.confirmed_total(900)
        self.assertEqual(heat.confirmed_total(12000).milestone, 3600)  # 1000 and 3600: first time.
        heat.confirmed_total(900)
        self.assertIsNone(heat.confirmed_total(12000).milestone)  # Once per session.
        heat.document_replaced()
        self.assertIsNone(heat.confirmed_total(30000).delta)

    def test_number_formats(self):
        self.assertEqual(format_dopa(1234, "ja"), "1,234")
        self.assertEqual(format_dopa(44420000, "ja"), "4442万")
        self.assertEqual(format_dopa(123456, "ja"), "12万")
        self.assertEqual(format_dopa(12345, "ja"), "1.2万")
        self.assertEqual(format_dopa(99999, "en"), "99,999")
        self.assertEqual(format_dopa(1250000, "en"), "1.2M")
        self.assertEqual(frames_as_time(4212), "1:10.20")
        self.assertEqual(frames_as_time(216000), "1:00:00.00")


class TkCase(unittest.TestCase):
    def make_root(self):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        root.withdraw()
        self.addCleanup(root.destroy)
        self.errors = []
        root.report_callback_exception = lambda *error: self.errors.append(error)
        return root


class FxEngineTests(TkCase):
    def setUp(self):
        self.root = self.make_root()
        self.canvas = tk.Canvas(self.root, width=300, height=200)
        self.now = [100.0]
        self.engine = fxmod.FxEngine(self.root, clock=lambda: self.now[0])

    def fx_items(self):
        return self.canvas.find_withtag(fxmod.FX_TAG)

    def test_punch_frames_then_cleanup_and_idle_ticker(self):
        effect = self.engine.add(fxmod.Punch(self.canvas, (10, 10, 110, 40), "#141124"))
        self.assertIsNotNone(self.engine._job)
        rect = effect.rect
        self.assertEqual(self.canvas.itemcget(rect, "outline"), fxmod.NEON[1])  # YELLOW at 0ms.
        self.assertAlmostEqual(self.canvas.coords(rect)[0], 10 - 9.0)          # 1.18x box.
        self.engine.step(100.12)
        self.assertGreater(self.canvas.coords(rect)[0], 1.0)
        self.engine.step(100.3)
        self.assertEqual(self.fx_items(), ())
        self.engine._tick()
        self.assertIsNone(self.engine._job)  # No effects: the ticker stops.

    def test_particle_cap_and_reduced_motion(self):
        self.assertEqual(self.engine.particle_count(500, self.canvas, 90), 90)
        self.engine.add(fxmod.Sparks(self.canvas, (50, 50), (0, 1), 60, "#141124", seed=1))
        self.assertEqual(self.engine.particle_count(500, self.canvas, 90), 30)
        self.engine.motion = 0
        self.assertTrue(self.engine.reduced)
        self.assertEqual(self.engine.particle_count(10, self.canvas, 90), 0)
        self.assertFalse(self.engine.flash_allowed())

    def test_flash_rate_limit(self):
        self.assertTrue(self.engine.flash_allowed())
        self.now[0] += 0.39
        self.assertFalse(self.engine.flash_allowed())
        self.now[0] += 0.02
        self.assertTrue(self.engine.flash_allowed())
        self.engine.flashes = False
        self.now[0] += 1
        self.assertFalse(self.engine.flash_allowed())

    def test_shout_slam_schedule_and_reduced_fade(self):
        self.assertAlmostEqual(fxmod.slam_scale(0.0), 2.8)
        self.assertAlmostEqual(fxmod.slam_scale(0.09), 0.88)
        self.assertAlmostEqual(fxmod.slam_scale(0.15), 1.08)
        self.assertAlmostEqual(fxmod.slam_scale(0.5), 1.0 + 0.02 * (0.29 / 0.61))
        self.assertAlmostEqual(fxmod.slam_scale(1.0), 1.45)

        class Fonts:
            def __init__(self):
                self.sizes = []

            def get(self, role, pixels, bold=True):
                self.sizes.append(round(pixels))
                return ("TkDefaultFont", -max(6, round(pixels)))

        fonts = Fonts()
        self.engine.add(fxmod.Shout(self.canvas, (150, 100), "NICE!", fonts, 20, "#ffffff",
                                    "#000000", "#0f0d1a", reduced=True))
        self.engine.step(100.4)
        self.assertEqual(set(fonts.sizes), {20})  # Reduced: no scale change, only fades.
        self.assertEqual(len(self.fx_items()), 10)  # 8 outline + shadow + face.

    def test_shake_moves_only_the_view_and_returns(self):
        item = self.canvas.create_rectangle(5, 5, 20, 20)
        self.engine.add(fxmod.Shake(self.canvas, power=1.0, seed=3))
        self.engine.step(100.1)
        self.assertEqual(self.canvas.coords(item), [5.0, 5.0, 20.0, 20.0])
        self.engine.step(100.3)
        self.assertEqual((self.canvas.canvasx(0), self.canvas.canvasy(0)), (0.0, 0.0))


class FeverEditorTests(TkCase):
    def make_editor(self, text=SCRIPT, language="en", settings=None, **values):
        root = self.make_root()
        folder = tempfile.TemporaryDirectory(prefix="tas fever ")
        self.addCleanup(folder.cleanup)
        source = Path(folder.name) / "route.tsv"
        source.write_text(text, encoding="utf-8")
        root._tas_app_settings = settings or AppSettings(Path(folder.name) / "settings.json")
        if values:
            root._tas_app_settings.update(**values)
        editor = EditorWindow(root, language=language, initial_path=source)
        editor.geometry("1200x700")
        editor.show_table()
        root.update()
        self.root, self.editor = root, editor
        self.now = [500.0]
        director = editor._dopa
        director.clock = director.fx.clock = lambda: self.now[0]
        return root, editor, source

    def wait_for(self, condition):
        deadline = time.monotonic() + 10
        while not condition() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        self.assertTrue(condition(), "background analysis did not finish")

    def commit(self, row, column, value, direction=(0, 1)):
        grid = self.editor.table_grid
        grid.jump_to_row(row, column=column)
        grid.begin_edit(initial=value)
        grid._entry_move(SimpleNamespace(widget=grid._editor), *direction)

    def table_fx(self):
        return self.editor.table_grid.canvas.find_withtag("fx")

    def test_tab_commit_rewards_after_the_real_change_only(self):
        root, editor, _ = self.make_editor()
        grid, heat = editor.table_grid, editor._dopa.heat
        grid.jump_to_row(1, column=0)
        grid._move(0, 1)  # Navigation alone is not productive.
        grid.begin_edit(initial="a")  # Cell B2 already holds "a".
        grid._entry_move(SimpleNamespace(widget=grid._editor), 0, 1)  # Same value: no change.
        self.assertEqual((heat.actions, heat.dopa), (0, 0))
        self.commit(1, 3, "zr")
        self.assertEqual(editor.document.text, "5\tls(90)\n1\ta\trs(0)\tzr\n2\tzl\n")
        self.assertEqual(heat.actions, 1)
        self.assertGreater(heat.dopa, 0)
        self.assertTrue(self.table_fx())
        self.assertIs(editor.focus_get(), grid.canvas)
        self.assertEqual(grid.selected, (1, 4))
        self.assertTrue(editor.undo())  # One Undo step restores; FX added none.
        self.assertEqual(editor.document.text, SCRIPT)
        self.assertEqual(heat.actions, 1)  # HEAT never drops on Undo.
        self.now[0] += 2
        editor._dopa.fx.step()
        self.assertEqual(self.table_fx(), ())
        self.assertEqual(self.errors, [])

    def test_pending_edit_ime_entry_and_autocomplete_are_untouched_by_fx(self):
        root, editor, _ = self.make_editor()
        grid = editor.table_grid
        self.commit(0, 2, "a")  # FX running on the same canvas.
        grid.jump_to_row(2, column=2)
        grid.begin_edit(initial="l")
        root.update()
        entry = grid._editor
        self.assertTrue(grid._completion.open)
        entry.insert("end", "s(猫")  # Entry text as an IME would leave it.
        before = entry.get(), entry.index("insert"), editor.focus_get()
        for step in range(10):
            self.now[0] += 0.03
            editor._dopa.fx.step()
            grid._draw_visible()
        self.assertEqual((entry.get(), entry.index("insert"), editor.focus_get()), before)
        grid.cancel_edit()
        self.assertEqual(editor._dopa.heat.actions, 1)  # Cancel is not productive.

    def test_transform_and_raw_line_commits_are_productive(self):
        root, editor, _ = self.make_editor()
        heat = editor._dopa.heat
        editor.table_grid.jump_to_row(0, column=0)
        self.assertTrue(editor._table_action("insert_row_below"))
        self.assertEqual(heat.actions, 1)
        editor.show_raw()
        editor.text.mark_set("insert", "1.end")
        editor._raw_return()
        editor.text.insert("insert", "\n")
        root.update()
        self.assertEqual(heat.actions, 2)
        editor._raw_return()  # The new line is blank: no reward.
        editor.text.insert("insert", "\n")
        root.update()
        self.assertEqual(heat.actions, 2)
        editor._raw_return()  # Return that inserted nothing (IME confirm).
        root.update()
        self.assertEqual(heat.actions, 2)

    def test_meter_snaps_confirmed_data_and_delta_follows_real_totals(self):
        root, editor, _ = self.make_editor()
        hud, meter = editor._dopa.hud, editor.meter_canvas
        self.wait_for(lambda: editor._positions is not None)
        editor.table_grid.jump_to_row(1, column=1)
        self.assertEqual([meter.itemcget(item, "text") for item in hud.values], ["5", "1", "5", "8"])
        self.assertEqual(meter.itemcget(hud.lamp, "fill"), theme.COLORS["neon_green"])
        self.commit(2, 0, "12")  # 2f -> 12f.
        self.assertEqual(meter.itemcget(hud.values[3], "text"), "- - -")
        pops = []
        original = editor._dopa.hud.delta
        editor._dopa.hud.delta = lambda frames: (pops.append(frames), original(frames))
        self.wait_for(lambda: editor._positions is not None)
        self.assertEqual(meter.itemcget(hud.values[3], "text"), "18")
        self.assertEqual(pops, [10])
        self.assertEqual(editor._positions.total_frames, 18)

    def test_no_milestone_for_an_opened_long_script(self):
        root, editor, _ = self.make_editor("1200\ta\n")
        shouts = []
        editor._dopa.hud.shout = lambda text, tier, **kw: shouts.append(text)
        self.wait_for(lambda: editor._positions is not None)
        self.assertEqual(shouts, [])
        self.commit(0, 0, "4000")
        self.wait_for(lambda: editor._positions is not None)
        self.assertEqual(shouts, ["1 MINUTE!!"])

    def test_settings_menu_chip_shortcut_and_other_editors(self):
        root, editor, _ = self.make_editor()
        settings = editor.settings
        other = EditorWindow(root, language="ja")
        self.addCleanup(other.destroy)
        editor._cycle_dopa_motion()
        self.assertEqual(settings.get("dopa_motion"), 75)
        self.assertEqual(editor._dopa.fx.motion, 0.75)
        self.assertEqual(other._dopa.fx.motion, 0.75)
        self.assertEqual(other._dopa_chip.cget("text"), "演出 75%")
        editor._dopa_chip.event_generate("<Button-1>")
        self.assertEqual(settings.get("dopa_motion"), 50)
        editor._dopa_motion_var.set(0)
        editor._set_dopa(motion=0)
        self.assertTrue(editor._dopa.fx.reduced)
        self.assertEqual(editor._dopa_chip.cget("text"), "FX 0%")
        editor._set_dopa(flash=False)
        self.assertFalse(other._dopa.fx.flashes)
        self.assertEqual(AppSettings(settings.path).get("dopa_motion"), 0)
        self.assertEqual(editor.document.text, SCRIPT)

    def test_invalid_saved_preferences_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text('{"version": 1, "dopa_motion": 33, "dopa_flash": "yes"}',
                            encoding="utf-8")
            settings = AppSettings(path)
            self.assertEqual((settings.get("dopa_motion"), settings.get("dopa_flash")), (100, True))

    def test_work_focus_keeps_rewards_but_no_motion(self):
        root, editor, _ = self.make_editor(dopa_motion=0)
        self.commit(0, 2, "a")
        kinds = {type(effect).__name__ for effect in editor._dopa.fx.active}
        self.assertTrue({"Punch", "Pop"} <= kinds)
        self.assertFalse(kinds & {"Sparks", "Ring", "LockOn", "Burst", "Shake", "Ambient"})
        self.assertEqual(editor._dopa.heat.actions, 1)

    def test_palette_flash_returns_to_theme_colors_and_still_inserts(self):
        root, editor, _ = self.make_editor()
        grid = editor.table_grid
        grid.jump_to_row(2, column=2)
        buttons = []

        def collect(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Button) and child.cget("text") == "B":
                    buttons.append(child)
                collect(child)

        collect(editor.input_palette)
        button = buttons[0]
        button.invoke()
        button.invoke()  # Pressed again mid-flash.
        self.assertEqual(grid._editor.get(), "bb")
        self.now[0] += 1
        editor._dopa.fx.step()
        normal = theme.button_options("palette")
        self.assertEqual(button.cget("background"), normal["background"])
        self.assertEqual(button.cget("activebackground"), normal["activebackground"])
        grid.cancel_edit()

    def test_destroy_mid_effects_releases_editor_without_callback_errors(self):
        root, editor, _ = self.make_editor()
        self.commit(0, 2, "a")
        editor._dopa.heat.actions = 40
        self.commit(1, 3, "b")  # EX: ambient tapes, rays and RIM cycle running.
        engine = editor._dopa.fx
        self.assertIsNotNone(engine._job)
        reference = weakref.ref(editor)
        editor.destroy()
        root.update()
        self.assertIsNone(engine._job)
        self.assertEqual(engine.active, ())
        self.assertIsNone(engine.widget)  # A closed engine keeps no Editor alive.
        self.assertEqual(self.errors, [])
        del editor, engine
        self.editor = None
        gc.collect()
        self.assertIsNone(reference())


if __name__ == "__main__":
    unittest.main()
