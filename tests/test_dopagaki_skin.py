"""Dopagaki3 Phase 1 (dopagaki3.md §15 P1): neon skin, command deck and GC hold."""

import gc
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import Mock

from python_to_exe import background
from python_to_exe.app_settings import AppSettings
from python_to_exe.editor import theme
from python_to_exe.editor.resources import neon_icon_path, palette_icon_path
from python_to_exe.editor.tsv_syntax import CANDIDATES
from python_to_exe.editor.validation import ValidationResult
from python_to_exe.editor.window import EditorWindow


SCRIPT = "$angle = 90\n// note\n5\tls($angle)\n1\ta\trs(0)\n/pause\n2\tzl\n"


def luminance(color):
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
              for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first, second):
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class NeonTokenTests(unittest.TestCase):
    def test_spec_tokens_are_hex_and_keep_fixed_meanings(self):
        colors = theme.COLORS
        for key in ("cell_background", "virtual_cell", "neon_yellow", "neon_magenta",
                    "neon_green", "neon_purple", "neon_orange", "on_neon", "cursor_line"):
            self.assertRegex(colors[key], r"^#[0-9a-fA-F]{6}$")
        self.assertEqual(colors["accent"], theme.STICK_RAMPS["ls"][0])        # CYAN = LS
        self.assertEqual(colors["neon_magenta"], theme.STICK_RAMPS["rs"][0])  # MAGENTA = RS
        self.assertEqual(theme.SYNTAX_COLORS["duration"], colors["neon_yellow"])
        self.assertEqual(len(theme.HEAT_RAMP), 5)
        self.assertTrue(all(len(ramp) == 4 for ramp in theme.STICK_RAMPS.values()))
        self.assertNotEqual(colors["virtual_cell"], colors["cell_background"])

    def test_readable_text_on_dark_surfaces_and_dark_text_on_neon(self):
        colors = theme.COLORS
        readable = ["text", "muted_text", "neon_yellow", "accent", "neon_orange", "error"]
        for surface in ("cell_background", "panel_background", "secondary_background"):
            for key in readable:
                self.assertGreaterEqual(contrast(colors[key], colors[surface]), 4.5, (key, surface))
            for color in theme.SYNTAX_COLORS.values():
                self.assertGreaterEqual(contrast(color, colors[surface]), 4.5, (color, surface))
        for kind in ("primary", "convert", "send"):
            options = theme.button_options(kind)
            self.assertGreaterEqual(contrast(options["foreground"], options["background"]), 4.5)
        self.assertGreaterEqual(contrast(colors["text"], colors["active_cell"]), 4.5)

    def test_neon_icon_variants_exist_beside_the_bundled_originals(self):
        for item in CANDIDATES:
            if item.icon_key:
                original = palette_icon_path(item.icon_key)
                self.assertEqual(neon_icon_path(original), original.parent / "neon" / original.name)
                self.assertTrue(neon_icon_path(original).is_file(), item.icon_key)


class GCHoldTests(unittest.TestCase):
    def setUp(self):
        background.resume_gc()  # Start from a clean module state.
        self.addCleanup(gc.enable if gc.isenabled() else gc.disable)
        self.addCleanup(background.resume_gc)
        gc.enable()

    def test_worker_hold_never_resumes_and_tk_thread_resume_waits_for_all(self):
        first, second = background.hold_gc(), background.hold_gc()
        self.assertFalse(gc.isenabled())
        first.release()
        first.release()  # Idempotent.
        self.assertFalse(background.resume_gc())
        self.assertFalse(gc.isenabled())
        with second:
            pass
        self.assertFalse(gc.isenabled())  # Releasing never re-enables by itself.
        self.assertTrue(background.resume_gc())
        self.assertTrue(gc.isenabled())
        self.assertFalse(background.resume_gc())

    def test_caller_disabled_gc_is_never_enabled_by_the_hold(self):
        gc.disable()
        with background.hold_gc():
            pass
        self.assertFalse(background.resume_gc())
        self.assertFalse(gc.isenabled())

    def test_gc_stays_paused_for_the_whole_worker_thread(self):
        observed = []
        hold = background.hold_gc()

        def worker():
            with hold:
                observed.append(gc.isenabled())
            observed.append(gc.isenabled())

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(observed, [False, False])
        self.assertTrue(background.resume_gc())


class SkinTkTests(unittest.TestCase):
    def make_editor(self, language="en", text=SCRIPT, size="1200x700", **options):
        folder = tempfile.TemporaryDirectory(prefix="tas dopagaki 日本語 ")
        self.addCleanup(folder.cleanup)
        source = Path(folder.name) / "route.tsv"
        source.write_text(text, encoding="utf-8")
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        root.withdraw()
        root._tas_app_settings = AppSettings(Path(folder.name) / "settings.json")
        self.addCleanup(root.destroy)
        self.theme_before = ttk.Style(root).theme_use()
        editor = EditorWindow(root, language=language, initial_path=source, **options)
        editor.geometry(size)
        editor.show_table()
        root.update()
        return root, editor, source

    def wait_for(self, root, condition):
        deadline = time.monotonic() + 10
        while not condition() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        root.update()
        self.assertTrue(condition(), "background analysis did not finish")

    def test_deck_buttons_call_the_existing_commands(self):
        on_convert = Mock(return_value=True)
        on_validate = Mock(return_value=True)
        on_analyze = Mock(return_value=True)
        root, editor, source = self.make_editor(on_convert=on_convert, on_validate=on_validate,
                                                on_analyze=on_analyze)
        self.assertIn("F5", editor._convert_button.cget("text"))
        self.assertIn("F8", editor._send_button.cget("text"))
        editor._convert_button.invoke()
        on_convert.assert_called_with(editor.document.path, send_ftp=False)
        editor._send_button.invoke()
        on_convert.assert_called_with(editor.document.path, send_ftp=True)
        editor._validate_button.invoke()
        editor._analyze_button.invoke()
        self.assertEqual((on_validate.call_count, on_analyze.call_count), (1, 1))
        self.assertEqual(editor.document.text, SCRIPT)
        self.assertEqual(source.read_text(encoding="utf-8"), SCRIPT)

    def test_deck_keeps_f5_f8_whole_at_minimum_width(self):
        for language in ("en", "ja"):
            with self.subTest(language=language):
                root, editor, _ = self.make_editor(language=language, size="800x500")
                for _ in range(3):
                    root.update()
                for button in (editor._convert_button, editor._send_button):
                    self.assertTrue(button.winfo_ismapped())
                    self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())
                checks = editor._analyze_button
                self.assertLessEqual(checks.winfo_rootx() + checks.winfo_width(),
                                     editor._convert_button.winfo_rootx())
                editor.geometry("1200x700")
                for _ in range(3):
                    root.update()
                self.assertFalse(editor._deck_compact)
                self.doCleanups()

    def test_frame_readout_is_yellow_only_when_converter_confirmed(self):
        root, editor, _ = self.make_editor()
        self.assertEqual(editor.frame_status.cget("foreground"), theme.COLORS["muted_text"])
        self.wait_for(root, lambda: editor._positions is not None)
        editor.table_grid.jump_to_row(3, column=1)
        self.assertIn("Start: 5f", editor.frame_status.cget("text"))
        self.assertEqual(editor.frame_status.cget("foreground"), theme.COLORS["neon_yellow"])
        editor.table_grid.begin_edit(initial="b")
        root.update()
        self.assertEqual(editor.frame_status.cget("text"), editor.words["frame_updating"])
        self.assertEqual(editor.frame_status.cget("foreground"), theme.COLORS["muted_text"])
        editor.table_grid.cancel_edit()

    def test_problem_badges_decorate_without_changing_factual_text(self):
        root, editor, _ = self.make_editor()
        editor._show_validation_result(ValidationResult(True))
        root.update()
        self.assertEqual(editor._problems_title.cget("text"), editor.words["no_errors"])
        self.assertEqual(editor._problems_badge.cget("text"), "✔")
        self.assertFalse(editor._problems_tape.winfo_ismapped())
        message = "Error: Invalid local duration in row 3"
        editor._show_validation_result(ValidationResult(False, stderr=message))
        root.update()
        self.assertEqual(editor._problems_title.cget("text"),
                         editor.words["problems"] + " — " + editor.words["jump_hint"])
        self.assertEqual(editor._problems_badge.cget("text"), editor.words["dopa_oshii"])
        self.assertTrue(editor._problems_tape.winfo_ismapped())
        self.assertEqual(editor._problems_text.get("1.0", "end-1c"), message)
        editor._show_problem_title(editor.words["validating"])
        root.update()
        self.assertFalse(editor._problems_badge.winfo_ismapped())
        self.assertFalse(editor._problems_tape.winfo_ismapped())

    def test_raw_cursor_line_and_modified_dot_are_display_only(self):
        root, editor, _ = self.make_editor()
        editor.show_raw()
        for line in (3, 5, 1):
            editor.text.mark_set("insert", f"{line}.1")
            editor._update_status()
            ranges = editor.text.tag_ranges("cursor_line")
            self.assertEqual([str(index) for index in ranges], [f"{line}.0", f"{line + 1}.0"])
        self.assertEqual(editor._modified_dot.cget("text"), "")
        self.assertEqual(editor.document.text, SCRIPT)
        with self.assertRaises(tk.TclError):
            editor.text.edit_undo()  # The tag added no Undo step.
        editor.text.insert("2.0", "1\tb\n")
        editor._on_modified()
        self.assertEqual(editor._modified_dot.cget("text"), "●")
        self.assertEqual(len(editor.text.tag_ranges("cursor_line")), 2)

    def test_dark_scrollbars_leave_the_global_ttk_theme(self):
        root, editor, _ = self.make_editor()
        bars = [child for child in editor.palette_canvas.master.winfo_children()
                if isinstance(child, ttk.Scrollbar)]
        bars += [child for child in editor.table_grid.winfo_children()
                 if isinstance(child, ttk.Scrollbar)]
        self.assertEqual(len(bars), 3)
        self.assertTrue(all(bar.cget("style").startswith("Dopa.") for bar in bars))
        self.assertEqual(ttk.Style(root).theme_use(), self.theme_before)
        second = EditorWindow(root, language="ja")  # Styles are registered once.
        self.addCleanup(second.destroy)
        self.assertEqual(ttk.Style(root).theme_use(), self.theme_before)

    def test_table_marks_virtual_cells_and_locks_on_the_active_cell(self):
        root, editor, _ = self.make_editor()
        grid = editor.table_grid
        grid.jump_to_row(1, column=0)
        grid._draw_visible()
        canvas = grid.canvas
        fills = {}
        for item in canvas.find_withtag("grid"):
            if canvas.type(item) == "rectangle":
                fills.setdefault(tuple(canvas.coords(item)), canvas.itemcget(item, "fill"))
        virtual = tuple(float(value) for value in grid._cell_box(grid.model.row_count + 1, 1))
        real = tuple(float(value) for value in grid._cell_box(0, 1))
        self.assertEqual(fills[virtual], theme.COLORS["virtual_cell"])
        self.assertEqual(fills[real], theme.COLORS["cell_background"])
        yellow = [item for item in canvas.find_withtag("grid") if canvas.type(item) == "line"
                  and canvas.itemcget(item, "fill") == theme.COLORS["neon_yellow"]]
        self.assertEqual(len(yellow), 5)  # Four lock-on corners plus the duration header rule.
        self.assertEqual(grid.model.to_text(), SCRIPT)

    def test_palette_uses_neon_icons_and_completion_popup_is_skinned(self):
        root, editor, _ = self.make_editor()
        self.assertIn("neon", editor._palette_icons["button_a"].cget("file"))
        grid = editor.table_grid
        grid.jump_to_row(5, column=1)
        grid.begin_edit(initial="l")
        root.update()
        self.assertEqual(grid._popup.cget("selectbackground"), theme.COLORS["neon_magenta"])
        grid.cancel_edit()
        self.assertEqual(editor.document.text, SCRIPT)

    def test_stick_preview_lamp_and_single_current_ring(self):
        root, editor, _ = self.make_editor()
        preview = editor.stick_preview
        self.assertEqual(preview.lamp.cget("foreground"), theme.COLORS["neon_yellow"])
        self.wait_for(root, lambda: editor._stick_frames is not None)
        editor.table_grid.jump_to_row(2, column=1)
        root.update()
        self.assertFalse(preview.lamp.winfo_ismapped())
        for plot in preview.plots:
            self.assertEqual(len(plot.find_withtag("current_ring")), 1)
            self.assertEqual(len(plot.find_withtag("sample")), len(preview.samples))


if __name__ == "__main__":
    unittest.main()
