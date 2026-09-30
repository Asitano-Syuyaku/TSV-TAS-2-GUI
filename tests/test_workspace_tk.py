"""Real Tk workspace persistence with isolated settings and multiple Editors."""

import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp


class WorkspaceTkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tas workspace Tk 日本語 ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.settings = AppSettings(self.folder / "settings.json")
        self.callback_errors = []

    def make_app(self, language="en", settings=None):
        try:
            app = TASConverterApp(language, settings=settings or self.settings)
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(lambda: app.destroy() if app._tclCommands is not None else None)
        app.report_callback_exception = lambda *error: self.callback_errors.append(error)
        app.update()
        return app

    def pump_until(self, app, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        self.assertTrue(predicate())
        self.assertEqual(self.callback_errors, [])

    @staticmethod
    def state(editor):
        grid = editor.table_grid
        return (editor.document.path, editor.document.text, editor.document.modified,
                editor.document._saved_raw, editor.text.edit("canundo"), editor.text.edit("canredo"),
                grid.selection.bounds, editor._position_revision)

    @staticmethod
    def drag_width(editor, column, delta, release=True):
        grid = editor.table_grid
        x = int(grid.gutter_width + grid.columns.edge(column + 1) - grid.canvas.canvasx(0))
        grid.canvas.event_generate("<ButtonPress-1>", x=x, y=5)
        grid.canvas.event_generate("<B1-Motion>", x=x + delta, y=5)
        if release:
            grid.canvas.event_generate("<ButtonRelease-1>", x=x + delta, y=5)
        return x

    def test_default_window_and_valid_geometry_restore_jp_en_without_position(self):
        for language in ("ja", "en"):
            with self.subTest(language=language):
                app = self.make_app(language)
                editor = app._create_editor()
                app.update()
                self.assertEqual((editor.winfo_width(), editor.winfo_height()), (1200, 700))
                self.assertEqual(editor.minsize(), (800, 500))
                self.assertEqual(editor._view, "raw")
                self.assertEqual(editor._palette_page, 1)
                self.assertTrue(editor.close_editor())
                self.settings.update(editor_width=1350, editor_height=810)
                editor = app._create_editor()
                app.update()
                self.assertEqual((editor.winfo_width(), editor.winfo_height()), (1350, 810))
                # Geometry request stores size only, never the previous screen position.
                self.assertEqual(editor.geometry().split("+")[0], "1350x810")
                editor.close_editor()
                app.destroy()
                self.settings.update(editor_width=1200, editor_height=700)

    def test_resize_writes_are_debounced_and_close_flushes_pending_size(self):
        app = self.make_app()
        editor = app._create_editor()
        app.update()
        with patch.object(self.settings, "save", wraps=self.settings.save) as save:
            for width, height in ((1260, 730), (1290, 745), (1320, 760)):
                editor.geometry(f"{width}x{height}")
                app.update()
            self.assertEqual(self.settings.get("editor_width"), 1320)
            self.assertEqual(self.settings.get("editor_height"), 760)
            self.assertIsNotNone(editor._workspace_job)
            save.assert_not_called()
            self.pump_until(app, lambda: editor._workspace_job is None)
            save.assert_called_once()
            self.assertEqual(AppSettings(self.settings.path).get("editor_width"), 1320)
            editor.geometry("1380x820")
            app.update()
            self.assertIsNotNone(editor._workspace_job)
            self.assertTrue(editor.close_editor())
            self.assertEqual(save.call_count, 2)
        reopened = app._create_editor()
        app.update()
        self.assertEqual((reopened.winfo_width(), reopened.winfo_height()), (1380, 820))
        self.assertEqual(AppSettings(self.settings.path).get("editor_height"), 820)

    def test_child_configure_move_only_and_invalid_sizes_do_not_persist(self):
        app = self.make_app()
        editor = app._create_editor()
        app.update()
        with patch.object(self.settings, "save", wraps=self.settings.save) as save:
            for widget, width, height in ((editor.text, 1300, 800), (editor, 1200, 700),
                                          (editor, 1, 1), (editor, 999999, 700)):
                editor._workspace_resized(SimpleNamespace(widget=widget, width=width, height=height))
            self.assertIsNone(editor._workspace_job)
            self.assertEqual(self.settings.get("editor_width"), 1200)
            save.assert_not_called()

    def test_column_drag_saves_on_release_and_reopens_with_sparse_widths(self):
        app = self.make_app()
        editor = app._create_editor()
        editor.show_table()
        app.update()
        before = self.state(editor)
        grid = editor.table_grid
        self.assertEqual(grid.columns.export_widths(), {})
        self.assertEqual(grid.columns.width(0), 112)
        with patch.object(self.settings, "save", wraps=self.settings.save) as save:
            x = self.drag_width(editor, 0, 30, release=False)
            self.assertEqual(grid.columns.width(0), 142)
            save.assert_not_called()
            grid.canvas.event_generate("<ButtonRelease-1>", x=x + 30, y=5)
            save.assert_called_once()
        self.assertEqual(self.settings.get("editor_column_widths"), {"0": 142})
        self.assertEqual(self.state(editor), before)
        editor.close_editor()
        editor = app._create_editor()
        app.update()
        self.assertEqual(editor._view, "table")
        self.assertEqual(editor.table_grid.columns.width(0), 142)
        self.assertEqual(editor.table_grid.columns.width(1), 148)
        self.drag_width(editor, 0, -30)
        self.assertEqual(self.settings.get("editor_column_widths"), {})
        self.assertFalse(editor.document.modified)

    def test_saved_future_column_and_table_raw_switch_keep_widths(self):
        self.settings.update(editor_column_widths={"0": 90, "1": 130, "10000": 230}, editor_view="table")
        app = self.make_app()
        editor = app._create_editor()
        app.update()
        grid = editor.table_grid
        self.assertEqual(grid.columns.width(0), 90)
        self.assertEqual(grid.columns.width(1), 130)
        self.assertEqual(grid.columns.width(10000), 230)
        self.assertLess(len(grid.columns._edges), 50)
        before = self.state(editor)
        editor.show_raw()
        editor.show_table()
        self.assertEqual(grid.columns.width(0), 90)
        self.assertEqual(grid.columns.width(10000), 230)
        self.assertEqual(self.state(editor), before)

    def test_advanced_and_table_restore_across_app_restart(self):
        app = self.make_app()
        editor = app._create_editor()
        before = self.state(editor)
        editor._palette_next.invoke()
        editor.show_table()
        app.update()
        self.assertEqual(self.state(editor), before)
        self.assertEqual(self.settings.get("editor_palette_page"), 1)
        self.assertEqual(self.settings.get("editor_view"), "table")
        self.assertTrue(editor.close_editor())
        app.destroy()
        restored = AppSettings(self.settings.path)
        app = self.make_app("ja", settings=restored)
        editor = app._create_editor()
        app.update()
        self.assertEqual(editor._palette_page, 2)
        self.assertEqual(editor._palette_page_label.cget("text"), "2 / 2")
        self.assertEqual(editor._view, "table")
        self.assertTrue(editor.input_palette.winfo_ismapped())
        self.assertFalse(editor.document.modified)
        editor.show_raw()
        editor.close_editor()
        editor = app._create_editor()
        app.update()
        self.assertEqual(editor._view, "raw")
        self.assertEqual(editor._palette_page, 2)

    def test_txt_open_and_save_as_use_raw_without_erasing_table_preference(self):
        self.settings.update(editor_view="table", editor_palette_page=1)
        app = self.make_app()
        source = self.folder / "input 日本語.txt"
        source.write_bytes(b"0 KEY_A 0;0 0;0\n")
        editor = app._create_editor(initial_path=source)
        app.update()
        self.assertEqual(editor._view, "raw")
        self.assertEqual(editor._table_button.cget("state"), "disabled")
        self.assertFalse(editor.show_table())
        self.assertEqual(self.settings.get("editor_view"), "table")
        self.assertFalse(editor.document.modified)
        self.assertTrue(editor.new_document())
        self.assertEqual(editor._view, "table")
        self.assertEqual(editor._palette_page, 2)
        self.assertTrue(editor._save_to(self.folder / "empty.txt"))
        self.assertEqual(editor._view, "raw")
        self.assertEqual(self.settings.get("editor_view"), "table")
        self.assertTrue(editor.new_document())
        self.assertEqual(editor._view, "table")
        tsv = self.folder / "script.tsv"
        tsv.write_text("1\ta\t\n", encoding="utf-8")
        self.assertTrue(editor.open_file(tsv))
        self.assertEqual(editor._view, "table")
        self.assertFalse(editor.document.modified)
        self.assertEqual(self.settings.get("editor_view"), "table")
        self.assertEqual(self.settings.get("editor_palette_page"), 1)

    def test_internal_raw_switch_does_not_change_explicit_view_preference(self):
        self.settings.update(editor_view="table")
        app = self.make_app()
        editor = app._create_editor()
        app.update()
        editor.show_find()
        self.assertEqual(editor._view, "raw")
        self.assertEqual(self.settings.get("editor_view"), "table")
        self.assertFalse(editor.document.modified)
        self.assertTrue(editor.new_document())
        self.assertEqual(editor._view, "table")
        editor.show_raw()
        self.assertEqual(self.settings.get("editor_view"), "raw")

    def test_workspace_changes_preserve_buffer_undo_redo_selection_and_frame_input(self):
        app = self.make_app()
        editor = app._create_editor()
        editor.text.insert("1.0", "1\ta\t\n1\t日本語\n")
        editor.text.edit_separator()
        editor._sync_text()
        editor.show_table()
        grid = editor.table_grid
        grid.selection.move_to(0, 1)
        grid.selection.move_to(1, 2, extend=True)
        editor.frame_entry.insert(0, "123")
        before = self.state(editor)
        app.update()
        self.drag_width(editor, 0, 20)
        editor._show_palette_page(2)
        editor.geometry("1340x790")
        app.update()
        editor.show_raw()
        editor.show_table()
        self.assertEqual(self.state(editor), before)
        self.assertEqual(editor.frame_entry.get(), "123")
        self.assertTrue(editor.undo())
        self.assertEqual(editor.document.text, "")
        self.assertTrue(editor.redo())
        self.assertEqual(editor.document.text, "1\ta\t\n1\t日本語\n")
        self.assertTrue(editor.document.modified)
        # User preferences never store these live Editor states.
        saved = self.settings.path.read_text()
        self.assertNotIn("日本語", saved)
        self.assertNotIn("go_frame", saved)

    def test_multiple_editors_merge_changed_fields_and_old_close_cannot_roll_back(self):
        app = self.make_app()
        one, two = app._create_editor(), app._create_editor()
        app.update()
        self.assertIs(one.settings, two.settings)
        one.show_table()
        two.show_table()
        app.update()
        self.drag_width(one, 0, 20)
        self.drag_width(two, 1, 30)
        self.assertEqual(self.settings.get("editor_column_widths"), {"0": 132, "1": 178})
        one.geometry("1360x800")
        app.update()
        two.geometry("1440x850")
        app.update()
        self.assertIsNotNone(one._workspace_job)
        self.assertIsNotNone(two._workspace_job)
        one._show_palette_page(2)
        two._show_palette_page(1)
        two.show_raw()
        self.assertTrue(one.close_editor())
        # Closing the older layout flushes the shared latest state, not its own copy.
        saved = AppSettings(self.settings.path)
        self.assertEqual((saved.get("editor_width"), saved.get("editor_height")), (1440, 850))
        self.assertEqual(saved.get("editor_view"), "raw")
        self.assertEqual(saved.get("editor_palette_page"), 0)
        self.assertEqual(saved.get("editor_column_widths"), {"0": 132, "1": 178})
        two.close_editor()
        editor = app._create_editor()
        app.update()
        self.assertEqual((editor.winfo_width(), editor.winfo_height()), (1440, 850))
        self.assertEqual(editor._view, "raw")
        self.assertEqual(editor._palette_page, 1)
        self.assertEqual(editor.table_grid.columns.width(0), 132)
        self.assertEqual(editor.table_grid.columns.width(1), 178)

    def test_settings_write_failure_does_not_crash_or_modify_document(self):
        app = self.make_app()
        editor = app._create_editor()
        app.update()
        before = self.state(editor)
        with patch("python_to_exe.app_settings.os.replace", side_effect=OSError("read only")):
            editor._show_palette_page(2)
            editor.show_table()
            editor.geometry("1320x780")
            app.update()
            self.pump_until(app, lambda: editor._workspace_job is None)
            self.assertEqual(self.state(editor), before)
            self.assertTrue(editor.close_editor())
        self.assertEqual(self.callback_errors, [])


if __name__ == "__main__":
    unittest.main()
