"""Real Tk integration: run explicitly under WSLg or another graphical desktop."""

import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from python_to_exe.converter_gui import TASConverterApp
from python_to_exe.editor.debug_csv import DebugFrames
from python_to_exe.editor.frame_inspector import HEADER_HEIGHT, ROW_HEIGHT
from python_to_exe.editor.line_positions import analyze_positions
from python_to_exe.editor.window import EditorWindow


class RealTkSmokeTests(unittest.TestCase):
    def test_selected_line_frame_position_refresh_and_stale_result(self):
        try:
            app = TASConverterApp("en")
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(app.destroy)
        with tempfile.TemporaryDirectory(prefix="tas positions ") as folder:
            source = Path(folder) / "positions.tsv"
            original = "1\ta\n33\tb\n"
            source.write_text(original, encoding="utf-8")
            app._set_input_path(source)
            app.ftp_var.set(True)
            app.debug_var.set(True)
            settings = (app.ftp_var.get(), app.debug_var.get(), app.output_entry.get(),
                        app.outname_entry.get())
            with patch("python_to_exe.editor.line_positions.analyze_positions",
                       wraps=analyze_positions) as analyze:
                app.open_editor()
                editor = next(child for child in app.winfo_children()
                              if isinstance(child, EditorWindow))
                deadline = time.monotonic() + 6
                while editor._positions is None and time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.02)
                self.assertIsNotNone(editor._positions)
                self.assertEqual(analyze.call_count, 1)
                editor.text.mark_set("insert", "1.0")
                editor._update_status()
                self.assertIn("Start: 0f | Duration: 1f | End: 0f | Total: 34f",
                              editor.frame_status.cget("text"))
                self.assertTrue(editor.show_table())
                editor.table_grid.jump_to_row(1)
                self.assertIn("Start: 1f | Duration: 33f | End: 33f | Total: 34f",
                              editor.frame_status.cget("text"))
                editor.table_grid.begin_edit()
                self.assertIn("Start: 1f", editor.frame_status.cget("text"))
                editor.table_grid._editor.insert("end", "x")
                self.assertIn("updating", editor.frame_status.cget("text"))
                editor.table_grid.cancel_edit()
                self.assertIn("Start: 1f", editor.frame_status.cget("text"))
                editor.table_grid._move(0, 1)
                self.assertIn("Start: 1f", editor.frame_status.cget("text"))
                self.assertTrue(editor.show_raw())
                editor.text.mark_set("insert", "1.0")
                editor._update_status()
                self.assertIn("Start: 0f", editor.frame_status.cget("text"))
                editor.text.mark_set("insert", "2.0")
                editor._update_status()
                self.assertIn("Start: 1f", editor.frame_status.cget("text"))
                self.assertEqual(analyze.call_count, 1)

                editor.text.delete("2.1", "2.2")
                app.update()
                self.assertEqual(analyze.call_count, 1)
                editor.text.insert("2.1", "4")
                app.update()
                self.assertIn("updating", editor.frame_status.cget("text"))
                self.assertEqual(analyze.call_count, 1)
                deadline = time.monotonic() + 6
                while (editor._positions is None and time.monotonic() < deadline):
                    app.update()
                    time.sleep(0.02)
                self.assertIsNotNone(editor._positions)
                self.assertEqual(analyze.call_count, 2)
                self.assertIn("Start: 1f | Duration: 34f | End: 34f | Total: 35f",
                              editor.frame_status.cget("text"))
                self.assertEqual(source.read_text(encoding="utf-8"), original)
                self.assertTrue(editor.document.modified)
                self.assertEqual((app.ftp_var.get(), app.debug_var.get(),
                                  app.output_entry.get(), app.outname_entry.get()), settings)

                editor.text.delete("2.0", "2.0 lineend")
                editor.text.insert("2.0", "1\tls(")
                app.update()
                self.assertIn("updating", editor.frame_status.cget("text"))
                deadline = time.monotonic() + 6
                while ((editor._position_job is not None or editor._position_worker_active)
                       and time.monotonic() < deadline):
                    app.update()
                    time.sleep(0.02)
                self.assertIsNone(editor._positions)
                self.assertIn("unavailable", editor.frame_status.cget("text"))
                self.assertEqual(analyze.call_count, 3)
                self.assertTrue(editor.undo())
                self.assertTrue(editor.document.modified)

            editor.destroy()
            started = threading.Event()
            release = threading.Event()
            calls = []

            def delayed(snapshot, base_dir=None):
                calls.append(snapshot)
                if len(calls) == 1:
                    started.set()
                    release.wait(5)
                return analyze_positions(snapshot, base_dir=base_dir)

            with patch("python_to_exe.editor.line_positions.analyze_positions", delayed):
                app.open_editor()
                editor = next(child for child in app.winfo_children()
                              if isinstance(child, EditorWindow))
                deadline = time.monotonic() + 6
                while not started.is_set() and time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.02)
                self.assertTrue(started.is_set())
                editor.text.delete("2.0", "2.0 lineend")
                editor.text.insert("2.0", "2\tb")
                app.update()
                release.set()
                deadline = time.monotonic() + 6
                while (editor._positions is None and time.monotonic() < deadline):
                    app.update()
                    time.sleep(0.02)
                self.assertEqual(len(calls), 2)
                self.assertIn("Total: 3f", editor.frame_status.cget("text"))
                self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_analyze_frames_inspector_and_problems(self):
        try:
            app = TASConverterApp("en")
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(app.destroy)
        with tempfile.TemporaryDirectory(prefix="tas frames 日本語 ") as folder:
            source = Path(folder) / "frames with spaces.tsv"
            source.write_text("$is_two_player = true\n2\ta\tca\n", encoding="utf-8")
            app._set_input_path(source)
            app.debug_var.set(False)
            app.ftp_var.set(True)
            settings = (app.debug_var.get(), app.ftp_var.get(), app.format_var.get(),
                        app.output_entry.get(), app.outname_entry.get())
            app.open_editor()
            editor = next(child for child in app.winfo_children()
                          if isinstance(child, EditorWindow))
            self.assertTrue(editor.show_table())
            app.update()
            editor.table_grid.selected = (1, 1)
            editor.table_grid.begin_edit()
            editor.table_grid._editor.delete(0, "end")
            editor.table_grid._editor.insert(0, "b")
            self.assertTrue(editor.analyze_frames())
            deadline = time.monotonic() + 10
            while editor._analysis_pending and time.monotonic() < deadline:
                app.update()
                time.sleep(0.02)
            self.assertFalse(editor._analysis_pending)
            inspector = editor._frame_inspector
            self.assertTrue(inspector.winfo_exists())
            self.assertEqual(inspector.frames.total_frames, 2)
            self.assertEqual(len(inspector.frames.rows), 4)
            self.assertIn("2\tb\tca", source.read_text(encoding="utf-8"))
            self.assertIn("Total Frames: 2", inspector.total_label.cget("text"))
            self.assertEqual((app.debug_var.get(), app.ftp_var.get(), app.format_var.get(),
                              app.output_entry.get(), app.outname_entry.get()), settings)
            inspector._click(SimpleNamespace(x=10, y=HEADER_HEIGHT + ROW_HEIGHT + 3))
            self.assertEqual(inspector.selected_row, 1)
            self.assertIn("2ndPlayer: True", inspector.detail_text.get("1.0", "end"))
            self.assertIn("lg.r.xx:", inspector.detail_text.get("1.0", "end"))
            inspector.frame_entry.insert(0, "1")
            self.assertTrue(inspector.go_to_frame())
            self.assertEqual(inspector.selected_row, 2)
            self.assertTrue(editor.show_raw())
            self.assertTrue(editor.show_table())
            self.assertTrue(inspector.winfo_exists())

            self.assertTrue(editor.show_raw())
            editor.text.delete("1.0", "end")
            editor.text.insert("1.0", "1\tls(\n")
            self.assertTrue(editor.analyze_frames())
            deadline = time.monotonic() + 10
            while editor._analysis_pending and time.monotonic() < deadline:
                app.update()
                time.sleep(0.02)
            self.assertFalse(editor._analysis_pending)
            self.assertIs(editor._frame_inspector, inspector)
            self.assertEqual(inspector.frames.total_frames, 2)
            self.assertTrue(editor._problems_panel.winfo_ismapped())
            self.assertIn("Syntax error(s) on line 1", editor._problems_text.get("1.0", "end"))
            self.assertIn("Previous analysis", inspector.feedback.cget("text"))

            editor.text.delete("1.0", "end")
            editor.text.insert("1.0", "1\ta\n")
            self.assertTrue(editor.analyze_frames())
            deadline = time.monotonic() + 10
            while editor._analysis_pending and time.monotonic() < deadline:
                app.update()
                time.sleep(0.02)
            self.assertFalse(editor._analysis_pending)
            self.assertEqual(inspector.frames.total_frames, 1)
            self.assertFalse(editor._problems_panel.winfo_ismapped())

            original = inspector.frames
            rows = tuple((str(index),) + original.rows[0][1:] for index in range(10000))
            many = DebugFrames(original.headers, rows,
                               {index: index for index in range(10000)}, 10000)
            inspector.set_data(many, source)
            app.update()
            self.assertLess(len(inspector.canvas.find_all()), 1000)
            inspector.frame_entry.delete(0, "end")
            inspector.frame_entry.insert(0, "9999")
            self.assertTrue(inspector.go_to_frame())
            app.update()
            self.assertEqual(inspector.selected_row, 9999)
            self.assertLess(len(inspector.canvas.find_all()), 1000)

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
