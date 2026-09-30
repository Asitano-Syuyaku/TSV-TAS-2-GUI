"""Cached converter-map reverse lookup and inline navigation with real Tk."""

import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp
from python_to_exe.editor.line_positions import LinePosition, LinePositions, analyze_positions


class FrameLookupTests(unittest.TestCase):
    def test_start_middle_end_and_row_boundary(self):
        positions = LinePositions({1: LinePosition(0, 1, 0),
                                   2: LinePosition(1, 3, 3)}, 4)
        for frame, line in ((0, 1), (1, 2), (2, 2), (3, 2)):
            with self.subTest(frame=frame):
                self.assertEqual(positions.line_for_frame(frame), line)

    def test_nonpositive_rows_do_not_own_frames(self):
        positions = LinePositions({1: LinePosition(0, 0, None),
                                   2: LinePosition(0, -2, None),
                                   3: LinePosition(0, 3, 2)}, 3)
        self.assertEqual(positions.line_for_frame(0), 3)
        self.assertEqual(positions.line_for_frame(2), 3)
        self.assertIsNone(LinePositions({1: LinePosition(0, 0, None)}, 1).line_for_frame(0))

    def test_invalid_frame_and_empty_map(self):
        positions = LinePositions({1: LinePosition(0, 2, 1)}, 2)
        for frame in (-1, 2, 100):
            self.assertIsNone(positions.line_for_frame(frame))
        self.assertIsNone(LinePositions({}, 0).line_for_frame(0))

    def test_missing_or_unsafe_ranges_and_gaps(self):
        for row in (LinePosition(0, 2, None), LinePosition(-1, 2, 0),
                    LinePosition(0, 3, 1), LinePosition(0, 1, -1),
                    LinePosition(0, 3, 2)):
            with self.subTest(row=row):
                self.assertIsNone(LinePositions({1: row}, 2).line_for_frame(0))
        gap = LinePositions({1: LinePosition(0, 1, 0),
                             2: LinePosition(2, 1, 2)}, 3)
        self.assertIsNone(gap.line_for_frame(1))

    def test_ambiguous_overlap_is_not_guessed(self):
        positions = LinePositions({1: LinePosition(0, 3, 2),
                                   2: LinePosition(1, 2, 2)}, 3)
        self.assertEqual(positions.line_for_frame(0), 1)
        self.assertIsNone(positions.line_for_frame(1))


class InlineFrameTkTests(unittest.TestCase):
    SCRIPT = "$n = 3\n// comment\n/pause\n1\ta\t\n$n\tb\n2\tls(90)\n"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tas frame navigation 日本語 ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def make_editor(self, language="en", script=None, suffix=".tsv"):
        settings = AppSettings(self.folder / language / "settings.json")
        try:
            app = TASConverterApp(language, settings=settings)
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(lambda: app.destroy() if app._tclCommands is not None else None)
        self.callback_errors = []
        app.report_callback_exception = lambda *error: self.callback_errors.append(error)
        app.update()
        source = self.folder / (language + " source 日本語" + suffix)
        source.write_bytes((self.SCRIPT if script is None else script).encode("utf-8"))
        editor = app._create_editor(initial_path=source)
        app.update()
        return app, editor, source

    def wait_mapping(self, app, editor):
        deadline = time.monotonic() + 6
        while (editor._positions is None or editor._position_worker_active or
               editor._position_job is not None) and time.monotonic() < deadline:
            app.update()
            time.sleep(0.02)
        self.assertIsNotNone(editor._positions)
        self.assertEqual(self.callback_errors, [])

    @staticmethod
    def shortcut(widget, sequence):
        # Call the registered Tk handler to avoid WSLg window-manager focus races.
        script = next(script for tag in widget.bindtags()
                      if (script := widget.bind_class(tag, f"<{sequence}>")))
        command = script.split("[", 1)[1].split(" ", 1)[0]
        key = sequence.rsplit("-", 1)[-1]
        return widget.tk.call(command, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "", 0,
                              key, 0, str(widget), 2, 0, 0, 0)

    @staticmethod
    def value(editor, value):
        editor.frame_entry.delete(0, "end")
        editor.frame_entry.insert(0, value)

    @staticmethod
    def content_state(editor):
        return (editor.document.path, editor.document.text, editor.document.modified,
                editor.document._saved_raw, editor.text.get("1.0", "end-1c"),
                editor.text.edit("canundo"), editor.text.edit("canredo"),
                editor._position_revision, editor._document_revision)

    def test_jp_en_inline_layout_bindings_menu_and_no_dialog(self):
        for language in ("ja", "en"):
            with self.subTest(language=language):
                app, editor, _ = self.make_editor(language)
                self.wait_mapping(app, editor)
                editor.show_table()
                app.update()
                editor.focus_force()
                app.update()
                self.assertTrue(editor.frame_entry.winfo_ismapped())
                self.assertTrue(editor.frame_go_button.winfo_ismapped())
                self.assertEqual(editor.frame_go_button.cget("text"), editor.words["go"])
                self.assertEqual(int(editor.frame_entry.cget("width")), 7)
                bar = editor.frame_status.master
                # All normal controls fit fully in a single row at 1200 px.
                for widget in bar.winfo_children():
                    if widget.winfo_ismapped():
                        self.assertEqual(widget.winfo_width(), widget.winfo_reqwidth())
                        self.assertLessEqual(widget.winfo_x() + widget.winfo_width(), 1200)
                self.assertLess(editor.frame_status.winfo_x(), editor.frame_entry.master.winfo_x())
                menu = editor.nametowidget(editor.cget("menu"))
                search = editor.nametowidget(menu.entrycget(3, "menu"))
                self.assertEqual(search.entrycget("end", "label"), editor.words["go_to_frame"])
                self.assertEqual(search.entrycget("end", "accelerator"), "Ctrl+G")
                before_children = tuple(app.winfo_children())
                self.value(editor, "2")
                before = self.content_state(editor)
                self.assertEqual(self.shortcut(editor.table_grid.canvas, "Control-g"), "break")
                app.update()
                self.assertIs(editor.focus_get(), editor.frame_entry)
                self.assertEqual((editor.frame_entry.index("sel.first"),
                                  editor.frame_entry.index("sel.last")), (0, 1))
                self.assertEqual(tuple(app.winfo_children()), before_children)
                self.assertEqual(self.shortcut(editor.frame_entry, "Return"), "break")
                self.assertEqual(editor.table_grid.selected, (4, 0))
                self.assertEqual(editor._frame_jump_feedback.cget("text"), "")
                self.assertEqual(self.content_state(editor), before)
                self.assertEqual(self.shortcut(editor.text, "Control-g"), "break")
                self.assertEqual(self.shortcut(editor.frame_entry, "Escape"), "break")
                app.update()
                self.assertIs(editor.focus_get(), editor.table_grid.canvas)
                self.assertEqual(self.callback_errors, [])
                app.destroy()

    def test_table_and_raw_jump_keep_contents_history_and_column_without_converter_run(self):
        app, editor, source = self.make_editor()
        with patch("python_to_exe.editor.line_positions.analyze_positions", wraps=analyze_positions) as run:
            self.wait_mapping(app, editor)
            self.assertEqual(run.call_count, 1)
            editor.show_table()
            grid = editor.table_grid
            grid.jump_to_row(3, column=2)
            grid.selection.move_to(5, 2, extend=True)
            before = self.content_state(editor)
            for value, row in (("0", 3), ("1", 4), ("3", 4), ("4", 5), ("5", 5)):
                self.value(editor, value)
                self.assertTrue(editor.go_to_frame())
                self.assertEqual(grid.selected, (row, 2))
                self.assertEqual(grid.selection.anchor, grid.selection.active)
            # Preserve a valid virtual column, not just columns in that source row.
            grid.selected = (5, 30)
            grid._update_region()
            self.value(editor, "0")
            self.assertTrue(editor.go_to_frame())
            self.assertEqual(grid.selected, (3, 30))
            x1, _, x2, _ = grid._cell_box(*grid.selected)
            app.update()
            self.assertGreaterEqual(x1, grid.canvas.canvasx(0))
            self.assertLessEqual(x2, grid.canvas.canvasx(grid.canvas.winfo_width()))
            self.assertEqual(self.content_state(editor), before)
            self.assertEqual(editor.frame_status.cget("text"),
                             "Start: 0f | Duration: 1f | End: 0f | Total: 6f")
            editor.show_raw()
            self.value(editor, "3")
            self.assertTrue(editor.go_to_frame())
            self.assertEqual(editor.text.index("insert"), "5.0")
            self.assertEqual(editor.frame_status.cget("text"),
                             "Start: 1f | Duration: 3f | End: 3f | Total: 6f")
            self.assertEqual(self.content_state(editor), before)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(source.read_bytes(), self.SCRIPT.encode("utf-8"))

    def test_invalid_values_use_inline_feedback_and_do_not_change_selection(self):
        app, editor, _ = self.make_editor()
        self.wait_mapping(app, editor)
        editor.show_table()
        editor.table_grid.jump_to_row(4, column=1)
        before = self.content_state(editor)
        selected = editor.table_grid.selection.bounds
        with patch("python_to_exe.editor.window.messagebox.showerror") as error:
            for value in ("", "abc", "1.5", "-1", "6", "999", "1_0"):
                self.value(editor, value)
                self.assertFalse(editor.go_to_frame())
                self.assertEqual(editor._frame_jump_feedback.cget("text"),
                                 editor.words["frame_range"].format(last=5))
                self.assertEqual(editor.table_grid.selection.bounds, selected)
                self.assertEqual(self.content_state(editor), before)
            error.assert_not_called()
        self.value(editor, " 0 ")
        self.assertTrue(editor.frame_go_button.invoke())
        self.assertFalse(editor._frame_jump_feedback.winfo_manager())

    def test_mapping_missing_updating_stale_or_failed_cannot_jump(self):
        app, editor, _ = self.make_editor()
        self.wait_mapping(app, editor)
        positions, key = editor._positions, editor._position_key
        self.value(editor, "0")
        before = self.content_state(editor)
        cursor = editor.text.index("insert")
        for state in ("missing", "updating", "stale", "worker"):
            with self.subTest(state=state):
                editor._positions = None if state == "missing" else positions
                editor._position_key = (True, "old snapshot") if state == "stale" else key
                editor._position_job = "not dispatched" if state == "updating" else None
                editor._position_worker_active = state == "worker"
                try:
                    self.assertFalse(editor.go_to_frame())
                    message = editor.words["frame_error" if state == "missing" else "frame_updating"]
                    self.assertEqual(editor._frame_jump_feedback.cget("text"), message)
                    self.assertEqual(editor.text.index("insert"), cursor)
                    self.assertEqual(self.content_state(editor), before)
                finally:
                    editor._position_job = None
                    editor._position_worker_active = False
                    editor._position_key = key
        editor._positions = positions
        # A real failed converter run must leave no navigable old map.
        editor.text.delete("1.0", "end")
        editor.text.insert("1.0", "1\tls(")
        app.update()
        deadline = time.monotonic() + 6
        while (editor._position_job is not None or editor._position_worker_active) and time.monotonic() < deadline:
            app.update()
            time.sleep(0.02)
        self.assertIsNone(editor._positions)
        self.assertFalse(editor.go_to_frame())
        self.assertEqual(editor._frame_jump_feedback.cget("text"), editor.words["frame_error"])

    def test_txt_zero_total_and_no_positive_match(self):
        app, editor, _ = self.make_editor(suffix=".txt", script="0 KEY_A 0;0 0;0\n")
        self.value(editor, "0")
        before = self.content_state(editor)
        self.assertFalse(editor.go_to_frame())
        self.assertEqual(editor._frame_jump_feedback.cget("text"), editor.words["frame_unavailable"])
        self.assertEqual(self.content_state(editor), before)
        editor.destroy()
        editor = app._create_editor()
        editor.text.insert("1.0", "0\ta\n")
        app.update()
        self.wait_mapping(app, editor)
        positions = editor._positions
        # Some zero-frame scripts fail in the current converter; test the UI's
        # empty-total branch with a resolved empty map, without altering its core.
        editor._positions = LinePositions(positions.rows, 0)
        self.assertEqual(editor._positions.total_frames, 0)
        self.value(editor, "0")
        self.assertFalse(editor.go_to_frame())
        self.assertEqual(editor._frame_jump_feedback.cget("text"), editor.words["no_frames"])
        editor._positions = positions
        self.assertFalse(editor.go_to_frame())
        self.assertEqual(editor._frame_jump_feedback.cget("text"), editor.words["frame_no_source"])

    def test_ctrl_g_keeps_pending_edit_and_go_commits_before_checking_mapping(self):
        app, editor, source = self.make_editor()
        self.wait_mapping(app, editor)
        editor.show_table()
        app.update()
        grid = editor.table_grid
        grid.jump_to_row(4, column=0)
        grid.begin_edit(initial="4")
        entry = grid._editor
        before = self.content_state(editor)
        self.value(editor, "4")
        self.shortcut(entry, "Control-g")
        self.assertIs(grid._editor, entry)
        self.assertEqual(grid._editor.get(), "4")
        self.assertEqual(self.content_state(editor), before)
        self.shortcut(editor.frame_entry, "Escape")
        self.assertIs(grid._editor, entry)
        self.assertFalse(editor.go_to_frame())
        self.assertIsNone(grid._editor)
        self.assertIsNone(editor._positions)
        self.assertEqual(grid.selected, (4, 0))
        self.assertEqual(editor._frame_jump_feedback.cget("text"), editor.words["frame_updating"])
        self.assertTrue(editor.document.modified)
        self.assertEqual(source.read_bytes(), self.SCRIPT.encode("utf-8"))
        self.wait_mapping(app, editor)
        before = self.content_state(editor)
        self.assertTrue(editor.go_to_frame())
        self.assertEqual(grid.selected, (4, 0))  # Frame 4 is still in the now-4f row.
        self.assertEqual(self.content_state(editor), before)
        self.assertTrue(editor.undo())
        self.assertEqual(editor.document.text, self.SCRIPT)
        self.assertFalse(editor.document.modified)
        self.assertTrue(editor.redo())
        self.assertIn("4\tb", editor.document.text)

    def test_unchanged_cell_commits_and_jumps_immediately_but_invalid_edit_does_not(self):
        app, editor, _ = self.make_editor()
        self.wait_mapping(app, editor)
        editor.show_table()
        grid = editor.table_grid
        grid.jump_to_row(3, column=1)
        grid.begin_edit()
        before = self.content_state(editor)
        self.value(editor, "5")
        self.assertTrue(editor.go_to_frame())
        self.assertEqual(grid.selected, (5, 1))
        self.assertEqual(self.content_state(editor), before)
        grid.begin_edit(initial="bad\tcell")
        before = self.content_state(editor)
        self.assertFalse(editor.go_to_frame())
        self.assertIsNotNone(grid._editor)
        self.assertEqual(editor._frame_jump_feedback.cget("text"), editor.words["frame_commit_failed"])
        self.assertEqual(self.content_state(editor), before)

    def test_raw_unsynced_edit_cannot_jump_using_old_mapping(self):
        app, editor, _ = self.make_editor()
        self.wait_mapping(app, editor)
        # Do not pump Tk: the <<Modified>> callback has not synchronized this edit yet.
        editor.text.delete("4.0", "4.0 lineend")
        editor.text.insert("4.0", "2\ta\t")
        self.value(editor, "0")
        cursor = editor.text.index("insert")
        self.assertFalse(editor.go_to_frame())
        self.assertEqual(editor.text.index("insert"), cursor)
        self.assertIsNone(editor._positions)
        self.assertEqual(editor._frame_jump_feedback.cget("text"), editor.words["frame_updating"])
        self.wait_mapping(app, editor)
        before = self.content_state(editor)
        self.assertTrue(editor.go_to_frame())
        self.assertEqual(editor.text.index("insert"), "4.0")
        self.assertEqual(self.content_state(editor), before)

    def test_offscreen_source_jump_and_existing_undo_redo_are_preserved(self):
        script = "1\ta\t\n" * 200
        app, editor, source = self.make_editor(script=script)
        editor.text.edit_separator()
        editor.text.insert("end-1c", "1\tb\n")
        editor.text.edit_separator()
        editor._sync_text()
        self.wait_mapping(app, editor)
        before = self.content_state(editor)
        editor.show_table()
        self.value(editor, "199")
        self.assertTrue(editor.go_to_frame())
        app.update()
        self.assertEqual(editor.table_grid.selected, (199, 0))
        self.assertGreater(editor.table_grid.canvas.yview()[0], 0)
        self.assertEqual(self.content_state(editor), before)
        editor.show_raw()
        self.assertTrue(editor.go_to_frame())
        app.update()
        self.assertEqual(editor.text.index("insert"), "200.0")
        self.assertIsNotNone(editor.text.dlineinfo("200.0"))
        self.assertEqual(self.content_state(editor), before)
        self.assertTrue(editor.undo())
        self.assertEqual(editor.document.text, script)
        self.assertFalse(editor.document.modified)
        self.wait_mapping(app, editor)
        before = self.content_state(editor)
        self.assertTrue(editor.go_to_frame())
        self.assertEqual(self.content_state(editor), before)
        self.assertTrue(editor.redo())
        self.assertEqual(editor.document.text, script + "1\tb\n")
        self.assertTrue(editor.document.modified)
        self.assertEqual(source.read_bytes(), script.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
