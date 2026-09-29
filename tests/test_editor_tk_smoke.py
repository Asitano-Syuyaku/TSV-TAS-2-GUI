"""Real Tk integration: run explicitly under WSLg or another graphical desktop."""

import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

from python_to_exe.converter_gui import TASConverterApp
from python_to_exe.editor.window import EditorWindow


class RealTkSmokeTests(unittest.TestCase):
    def test_japanese_converter_opens_same_editor_controls(self):
        try:
            app = TASConverterApp("ja")
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(app.destroy)
        app.open_editor()
        editor = next(child for child in app.winfo_children()
                      if isinstance(child, EditorWindow))
        self.assertTrue(editor.show_table())
        app.update()
        self.assertEqual(editor.table_grid.labels["duration_header"], "フレーム数")
        self.assertGreaterEqual(editor.table_grid.display_column_count, 7)
        self.assertTrue(editor.input_palette.winfo_ismapped())
        self.assertFalse(editor.document.modified)

    def test_editor_validation_and_error_jump(self):
        try:
            app = TASConverterApp("en")
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(app.destroy)
        with tempfile.TemporaryDirectory(prefix="tas Tk 日本語 ") as folder:
            source = Path(folder) / "script with spaces.tsv"
            source.write_text("1\ta\n1\tls(\n", encoding="utf-8")
            app.format_var.set("stas")
            app.debug_var.set(True)
            app.ftp_var.set(True)
            app._set_input_path(source)
            settings_before = (app.format_var.get(), app.debug_var.get(),
                               app.ftp_var.get(), app.input_entry.get(),
                               app.output_entry.get(), app.outname_entry.get())
            app.open_editor()
            editor = next(child for child in app.winfo_children()
                          if isinstance(child, EditorWindow))
            app.update()
            self.assertTrue(editor.winfo_exists())
            self.assertTrue(editor.show_table())
            app.update()
            self.assertTrue(editor.input_palette.winfo_ismapped())
            self.assertFalse(editor.document.modified)
            grid = editor.table_grid

            width_before = grid.columns.width(0)
            edge = int(grid.gutter_width + grid.columns.edge(1) - grid.canvas.canvasx(0))
            grid._click(SimpleNamespace(x=edge, y=2, state=0))
            grid._drag(SimpleNamespace(x=edge + 35, y=2))
            grid._release(SimpleNamespace(x=edge + 35, y=2))
            self.assertEqual(grid.columns.width(0), width_before + 35)

            grid.selected = (0, 1)
            grid.begin_edit()
            grid._editor.delete(0, "end")
            grid._editor.insert(0, "b")
            self.assertTrue(grid.commit_edit())
            self.assertTrue(editor.validate())
            deadline = time.monotonic() + 10
            while editor._validation_pending and time.monotonic() < deadline:
                app.update()
                time.sleep(0.02)
            self.assertFalse(editor._validation_pending)
            self.assertEqual(editor._problem_rows.get(1), 2)
            self.assertEqual((app.format_var.get(), app.debug_var.get(),
                              app.ftp_var.get(), app.input_entry.get(),
                              app.output_entry.get(), app.outname_entry.get()),
                             settings_before)
            self.assertIn("Syntax error(s) on line 2", editor._problems_text.get("1.0", "end"))
            editor._problem_double_click(SimpleNamespace(x=3, y=3))
            self.assertEqual(grid.selected, (1, 0))
            self.assertTrue(editor.show_raw())
            editor._problem_double_click(SimpleNamespace(x=3, y=3))
            self.assertEqual(editor.text.index("insert"), "2.0")

            editor.text.delete("2.0", "2.0 lineend")
            editor.text.insert("2.0", "1\ta")
            app.update()
            self.assertEqual(editor._problem_rows, {})
            self.assertTrue(editor.validate())
            deadline = time.monotonic() + 10
            while editor._validation_pending and time.monotonic() < deadline:
                app.update()
                time.sleep(0.02)
            self.assertFalse(editor._validation_pending)
            self.assertEqual(editor._problems_title.cget("text"), "No errors")
            self.assertFalse(editor.document.modified)
            self.assertTrue(editor.undo())
            self.assertTrue(editor.document.modified)
            self.assertTrue(editor.redo())
            self.assertFalse(editor.document.modified)

            self.assertTrue(editor.new_document())
            self.assertTrue(editor.show_table())
            app.update()
            self.assertGreaterEqual(grid.display_column_count, 7)
            self.assertEqual(editor.document.text, "")
            self.assertFalse(editor.document.modified)
            self.assertLessEqual(grid._cell_box(0, 6)[2] - grid.canvas.canvasx(0),
                                 grid.canvas.winfo_width())
            for _ in range(7):
                grid._move(0, 1)
            self.assertEqual(grid.selected, (0, 7))
            self.assertEqual(editor.document.text, "")
            grid.begin_edit(initial="H")
            self.assertTrue(grid.commit_edit())
            self.assertEqual(editor.document.text, "\t" * 7 + "H")
