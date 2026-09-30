"""Recent menus and preference restoration through real Tk, using isolated config."""

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp
from python_to_exe.editor.window import EditorWindow


class RecentFilesTkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tas recent 日本語 ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.settings_path = self.folder / "config" / "settings.json"

    def make_app(self, language="en"):
        try:
            app = TASConverterApp(language, settings=AppSettings(self.settings_path))
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        # Some tests close through WM_DELETE_WINDOW; do not query a destroyed Tk root.
        self.addCleanup(lambda: app.destroy() if app._tclCommands is not None else None)
        return app

    def file(self, name, text="1\ta\n"):
        path = self.folder / name
        path.write_text(text, encoding="utf-8")
        return path

    @staticmethod
    def state(editor):
        return (editor.document.path, editor.document.text, editor.document.modified,
                editor._view, editor.table_grid.selection.bounds)

    def test_jp_en_open_save_as_save_and_convert_record_the_requesting_file(self):
        for language in ("ja", "en"):
            with self.subTest(language=language):
                app = self.make_app(language)
                editor = EditorWindow(app, language=language, on_convert=Mock(return_value=True))
                source = self.file(f"input {language} 日本語.tsv")
                self.assertTrue(editor.open_file(source))
                self.assertIs(editor.settings, app.settings)
                self.assertEqual(app.settings.recent_files[0], str(source))
                target = self.folder / f"saved {language}.txt"
                with patch("python_to_exe.editor.window.filedialog.asksaveasfilename",
                           return_value=str(target)):
                    self.assertTrue(editor.save_as())
                self.assertEqual(app.settings.recent_files[:2], (str(target), str(source)))
                # A successful Save moves an older entry back to the top.
                app.settings.add_recent(source)
                self.assertTrue(editor.save())
                self.assertEqual(app.settings.recent_files[0], str(target))
                for send in (False, True):
                    app.settings.add_recent(source)
                    self.assertTrue(editor.save_and_convert(send_ftp=send))
                    editor.on_convert.assert_called_with(target, send_ftp=send)
                    self.assertEqual(app.settings.recent_files[0], str(target))
                menu = editor.nametowidget(editor.cget("menu"))
                file_menu = editor.nametowidget(menu.entrycget(1, "menu"))
                self.assertIn(editor.words["recent_files"],
                              [file_menu.entrycget(i, "label") for i in range(file_menu.index("end") + 1)])
                app.destroy()

    def test_recent_open_uses_existing_modified_confirmation_and_cancel_is_safe(self):
        app = self.make_app()
        source, target = self.file("source.tsv"), self.file("target.tsv", "2\tb\n")
        editor = EditorWindow(app, initial_path=source)
        editor.text.insert("end-1c", "// unsaved")
        app.update()
        before = self.state(editor)
        with patch("python_to_exe.editor.window.messagebox.askyesnocancel", return_value=None) as ask:
            self.assertFalse(editor._open_recent(str(target)))
            ask.assert_called_once()
        self.assertEqual(self.state(editor), before)
        self.assertEqual(source.read_text(encoding="utf-8"), "1\ta\n")
        with patch("python_to_exe.editor.window.messagebox.askyesnocancel", return_value=False) as ask:
            self.assertTrue(editor._open_recent(str(target)))
            ask.assert_called_once()
        self.assertEqual(editor.document.path, target)
        self.assertFalse(editor.document.modified)
        self.assertEqual(app.settings.recent_files[0], str(target))

    def test_missing_recent_removes_only_entry_without_touching_current_document(self):
        app = self.make_app()
        source = self.file("source.tsv")
        missing = self.folder / "removed 日本語.tsv"
        editor = EditorWindow(app, initial_path=source)
        editor.text.insert("end-1c", "// unsaved")
        app.update()
        app.settings.add_recent(missing)
        before = self.state(editor)
        with patch("python_to_exe.editor.window.messagebox.showerror") as error, \
             patch("python_to_exe.editor.window.messagebox.askyesnocancel") as ask:
            self.assertFalse(editor._open_recent(str(missing)))
            error.assert_called_once()
            self.assertIn(str(missing), error.call_args.args[1])
            ask.assert_not_called()
        self.assertEqual(self.state(editor), before)
        self.assertEqual(AppSettings(self.settings_path).recent_files, (str(source),))

    def test_multiple_editors_share_latest_recent_menu_and_clear_without_affecting_state(self):
        app = self.make_app()
        first, second = self.file("first.tsv"), self.file("second.txt", "0 KEY_A 0;0 0;0\n")
        one = EditorWindow(app, initial_path=first)
        two = EditorWindow(app, language="ja", initial_path=second)
        self.assertIs(one.settings, two.settings)
        one.text.insert("end-1c", "// unsaved")
        app.update()
        before = self.state(one)
        # Posting refreshes the submenu in the older window, without an observer/listener queue.
        one._recent_menu.post(20, 20)
        try:
            self.assertEqual(one._recent_menu.entrycget(0, "label"), f"1 {second}")
        finally:
            one._recent_menu.unpost()
        two.settings.add_recent(first)
        one._refresh_recent_menu()
        self.assertEqual(one._recent_menu.entrycget(0, "label"), f"1 {first}")
        one._recent_menu.invoke(one._recent_menu.index("end"))
        self.assertEqual(AppSettings(self.settings_path).recent_files, ())
        two._refresh_recent_menu()
        self.assertEqual(two._recent_menu.entrycget(0, "state"), "disabled")
        self.assertEqual(self.state(one), before)
        one.undo()
        self.assertEqual(one.document.text, "1\ta\n")
        one.redo()
        self.assertEqual(one.document.text, before[1])

    def test_browse_initialdirs_recent_add_and_cancel(self):
        app = self.make_app()
        source = self.file("input with spaces.tsv")
        app.settings.update(last_input_directory=str(self.folder), last_output_directory=str(self.folder))
        with patch("python_to_exe.converter_gui.filedialog.askopenfilename", return_value=str(source)) as dialog:
            app.browse_input()
            self.assertEqual(dialog.call_args.kwargs["initialdir"], str(self.folder))
        self.assertEqual(app.settings.recent_files, (str(source),))
        self.assertEqual(app.settings.get("last_input_directory"), str(self.folder))
        output = self.folder / "output with spaces"
        output.mkdir()
        with patch("python_to_exe.converter_gui.filedialog.askdirectory", return_value=str(output)) as dialog:
            app.browse_output()
            self.assertEqual(dialog.call_args.kwargs["initialdir"], str(self.folder))
        self.assertEqual(AppSettings(self.settings_path).get("last_output_directory"), str(output))
        before = app.settings.recent_files
        with patch("python_to_exe.converter_gui.filedialog.askopenfilename", return_value=""):
            app.browse_input()
        self.assertEqual(app.settings.recent_files, before)
        app.settings.update(last_input_directory=str(self.folder / "missing"))
        with patch("python_to_exe.converter_gui.filedialog.askopenfilename", return_value="") as dialog:
            app.browse_input()
            self.assertNotIn("initialdir", dialog.call_args.kwargs)

    def test_format_debug_restore_ftp_off_no_auto_open_and_skip_consistency(self):
        for language in ("en", "ja"):
            with self.subTest(language=language):
                app = self.make_app(language)
                format_frame = next(child for child in app.winfo_children()
                                    if any(isinstance(item, tk.Radiobutton) for item in child.winfo_children()))
                stas = next(child for child in format_frame.winfo_children() if child.cget("value") == "stas")
                app.skip_var.set(True)
                stas.invoke()
                debug = next(child for child in app.winfo_children()
                             if isinstance(child, tk.Checkbutton) and child.cget("text") == app.words["debug"])
                if not app.debug_var.get():
                    debug.invoke()
                self.assertEqual(app.settings.get("output_format"), "stas")
                self.assertTrue(app.settings.get("debug_enabled"))
                app.ftp_var.set(True)
                app.settings.add_recent(self.file("last.tsv"))
                app._close_app()
                persisted = json.loads(self.settings_path.read_text(encoding="utf-8"))
                self.assertNotIn("ftp_enabled", persisted)
                restored = self.make_app(language)
                self.assertEqual(restored.format_var.get(), "stas")
                self.assertTrue(restored.debug_var.get())
                self.assertFalse(restored.ftp_var.get())
                self.assertFalse(restored.skip_var.get())
                self.assertEqual(restored.skip_check.cget("state"), "disabled")
                self.assertEqual(restored.input_entry.get(), "")
                self.assertEqual(restored.output_entry.get(), "")
                editor = EditorWindow(restored, language=language)
                self.assertIsNone(editor.document.path)
                self.assertEqual(editor.document.text, "")
                self.assertFalse(editor.document.modified)
                restored.destroy()

    def test_standalone_editors_share_settings_on_their_root(self):
        app = self.make_app()
        shared = app.settings
        del app.settings
        app._tas_app_settings = shared
        one, two = EditorWindow(app), EditorWindow(app)
        self.assertIs(one.settings, two.settings)
        self.assertIs(one.settings, shared)
