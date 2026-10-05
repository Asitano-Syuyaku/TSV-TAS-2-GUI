"""Readability bugfix before Final Acceptance: DPI awareness, scale, density (not font size)."""

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe import display
from python_to_exe.app_settings import AppSettings
from python_to_exe.editor import theme
from python_to_exe.editor.dopa.fonts import FontBook
from python_to_exe.editor.window import EditorWindow


class ScaleTests(unittest.TestCase):
    def tearDown(self):
        theme.set_ui_scale(1.0)

    def test_non_windows_is_untouched(self):
        self.assertEqual(display.enable_dpi_awareness("linux"), "not-windows")
        self.assertFalse(display.configure_root(object(), platform="linux"))
        self.assertEqual(theme.px(400), 400)

    def test_scale_grows_pixel_geometry_and_never_shrinks_it(self):
        theme.set_ui_scale(1.25)
        self.assertEqual(theme.px(400), 500)
        theme.set_ui_scale(0.8)  # Never below 96-DPI sizes.
        self.assertEqual(theme.px(400), 400)

    def test_windows_configuration_sets_scale_from_the_root_dpi(self):
        class Root:
            def winfo_fpixels(self, _):
                return 120.0

        with patch("tkinter.font.families", return_value=()):
            self.assertTrue(display.configure_root(Root(), platform="win32"))
        self.assertAlmostEqual(theme.UI_SCALE["value"], 1.25)


class TkDisplayTests(unittest.TestCase):
    def make_editor(self, size):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        root.withdraw()
        self.addCleanup(root.destroy)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        source = Path(folder.name) / "route.tsv"
        source.write_text("5\tls(90)\n1\ta\n", encoding="utf-8")
        root._tas_app_settings = AppSettings(Path(folder.name) / "settings.json")
        editor = EditorWindow(root, language="ja", initial_path=source)
        editor.geometry(size)
        editor.show_table()
        for _ in range(5):
            root.update()
        return root, editor

    def tearDown(self):
        theme.set_ui_scale(1.0)

    def test_font_pixels_follow_the_display_scale(self):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        root.withdraw()
        self.addCleanup(root.destroy)
        theme.set_ui_scale(1.5)
        self.assertEqual(FontBook(root).get("meter", 22).cget("size"), -33)
        self.assertGreaterEqual(theme.MIN_TEXT_POINTS, 9)

    def test_short_windows_change_density_not_font_size(self):
        root, editor = self.make_editor("800x480")
        editor._show_problem_title(editor.words["problems"])
        editor._fit_density(480)
        root.update()
        self.assertFalse(editor.frame_status.winfo_ismapped())     # Duplicate of the METER.
        self.assertTrue(editor.frame_entry.winfo_ismapped())       # Go stays.
        self.assertEqual(int(editor._problems_text.cget("height")), 2)
        status = editor._status_row
        self.assertTrue(status.winfo_ismapped())                    # Never squeezed out.
        self.assertLessEqual(status.winfo_y() + status.winfo_height(), editor.winfo_height())
        font_before = editor.table_grid.font.actual("size")
        editor._fit_density(800)
        root.update()
        self.assertTrue(editor.frame_status.winfo_ismapped())
        self.assertLess(editor.frame_status.winfo_x(), editor.frame_entry.master.winfo_x())
        self.assertEqual(int(editor._problems_text.cget("height")), 4)
        self.assertEqual(editor.table_grid.font.actual("size"), font_before)

    def test_stick_preview_stays_whole_in_short_windows(self):
        root, editor = self.make_editor("1200x1000")
        preview, canvas = editor.stick_preview, editor.palette_canvas
        page = preview.master
        group, buttons = editor._palette_fold
        size = preview.plots[0].winfo_height()

        def check(columns):
            root.update()
            self.assertEqual(editor._palette_fold_columns, columns)
            self.assertEqual({int(button.grid_info()["column"]) for button, _ in buttons},
                             set(range(columns)))
            self.assertLessEqual(preview.winfo_y() + preview.winfo_height(), page.winfo_height())
            self.assertEqual(preview.plots[0].winfo_height(), size)  # Never a smaller plot.

        check(2)
        self.assertEqual(canvas.yview(), (0.0, 1.0))  # Everything fits: nothing scrolls.
        for geometry in ("1200x700", "1280x650", "800x500"):
            editor.geometry(geometry)
            check(4)
        editor._show_palette_page(2)
        editor.geometry("1200x1000")
        root.update()
        editor._show_palette_page(1)
        check(2)
        editor.geometry("1280x650")
        check(4)

    def test_reward_block_stays_inside_a_narrow_canvas(self):
        root, editor = self.make_editor("800x500")
        reward = editor.reward_canvas
        editor._dopa.hud._layout_reward()
        root.update()
        right = max(reward.bbox(item)[2] for item in (editor._dopa.hud.dopa, editor._dopa.hud.round_text,
                                                      editor._dopa.hud.dopa_label))
        self.assertLessEqual(right, reward.winfo_width())


if __name__ == "__main__":
    unittest.main()
