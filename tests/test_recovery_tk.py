"""Recovery lifecycle through real Tk, with an isolated user config directory."""

import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp
from python_to_exe.editor.document import EditorDocument
from python_to_exe.editor.recovery import RecoverySnapshot, RecoveryStore


class RecoveryTkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tas recovery 日本語 ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.settings_path = self.folder / "config" / "settings.json"
        self.recovery_dir = self.settings_path.parent / "recovery"

    def make_app(self, language="en"):
        try:
            app = TASConverterApp(language, settings=AppSettings(self.settings_path))
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(lambda: app.destroy() if app._tclCommands is not None else None)
        app.update()
        return app

    def file(self, name="input 日本語.tsv", raw="1\ta\r\n1\tb\t\r\n"):
        path = self.folder / name
        path.write_bytes(raw.encode("utf-8"))
        return path

    def records(self):
        return RecoveryStore(self.recovery_dir).load()

    @staticmethod
    def editors(app):
        # Headless tests reload this module; inspect the factory's current class.
        from python_to_exe.editor.window import EditorWindow
        return [child for child in app.winfo_children() if isinstance(child, EditorWindow)]

    @staticmethod
    def edit(editor, value="// 未保存\n"):
        editor.text.insert("end-1c", value)
        editor._sync_text()

    @staticmethod
    def flush(editor):
        if editor._recovery_job is not None:
            editor.after_cancel(editor._recovery_job)
            editor._recovery_job = None
        editor._write_recovery()

    def wait_for(self, app, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            app.update()
            time.sleep(0.02)
        self.assertTrue(predicate())

    def test_tsv_txt_debounce_save_save_as_and_failed_save(self):
        app = self.make_app()
        for suffix in ("tsv", "txt"):
            with self.subTest(suffix=suffix):
                source = self.file(f"input {suffix}.{suffix}")
                original = source.read_bytes()
                editor = app._create_editor(initial_path=source)
                self.edit(editor)
                self.assertEqual(self.records(), ())
                self.wait_for(app, lambda: len(self.records()) == 1)
                snapshot = self.records()[0]
                self.assertEqual(snapshot.original_path, str(source))
                self.assertEqual(snapshot.source_kind, suffix)
                self.assertEqual(snapshot.text, "1\ta\r\n1\tb\t\r\n// 未保存\r\n")
                self.assertEqual(source.read_bytes(), original)
                with patch.object(editor.document, "save", side_effect=OSError("disk full")), \
                     patch("python_to_exe.editor.window.messagebox.showerror") as error:
                    self.assertFalse(editor.save())
                    error.assert_called_once()
                self.assertTrue(editor.document.modified)
                self.assertEqual(self.records(), (snapshot,))
                self.assertTrue(editor.save())
                self.assertFalse(editor.document.modified)
                self.assertEqual(self.records(), ())
                self.assertEqual(source.read_bytes(), snapshot.text.encode("utf-8"))

                self.edit(editor, "// Save As\n")
                self.flush(editor)
                target = self.folder / f"new {suffix}.{suffix}"
                with patch("python_to_exe.editor.window.filedialog.asksaveasfilename",
                           return_value=str(target)):
                    self.assertTrue(editor.save_as())
                self.assertEqual(self.records(), ())
                self.assertFalse(editor.document.modified)
                self.assertIn(b"// Save As\r\n", target.read_bytes())
                self.assertTrue(editor.close_editor())

    def test_pending_entry_recovery_does_not_commit_select_or_change_undo(self):
        app = self.make_app()
        source = self.file()
        editor = app._create_editor(initial_path=source)
        self.assertTrue(editor.show_table())
        app.update()
        grid = editor.table_grid
        grid.selected = (0, 1)
        grid.begin_edit()
        grid._editor.delete(0, "end")
        grid._editor.insert(0, "未確定")
        before = (grid._editor, grid.model.to_text(), grid.selection.bounds,
                  grid._editor.index("insert"), editor.document.text,
                  editor.text.edit("canundo"), editor.text.edit("canredo"))
        self.assertFalse(editor.document.modified)
        self.wait_for(app, lambda: bool(self.records()))
        self.assertEqual(self.records()[0].text, "1\t未確定\r\n1\tb\t\r\n")
        self.assertEqual((grid._editor, grid.model.to_text(), grid.selection.bounds,
                          grid._editor.index("insert"), editor.document.text,
                          editor.text.edit("canundo"), editor.text.edit("canredo")), before)
        self.assertFalse(editor.document.modified)
        self.assertEqual(source.read_bytes(), b"1\ta\r\n1\tb\t\r\n")
        grid.cancel_edit()
        self.assertEqual(self.records(), ())
        self.assertTrue(editor.close_editor())

    def test_untitled_forced_destroy_restore_again_and_discard(self):
        app = self.make_app("ja")
        editor = app._create_editor()
        self.edit(editor, "1\ta\t\n// 日本語\n")
        self.wait_for(app, lambda: bool(self.records()))
        snapshot = self.records()[0]
        self.assertEqual(snapshot.display_name, editor.words["untitled"])
        app.destroy()  # No WM_DELETE_WINDOW cleanup: equivalent to an abrupt shutdown.
        self.assertEqual(self.records(), (snapshot,))

        with patch("python_to_exe.converter_gui.messagebox.askyesnocancel", return_value=True) as ask:
            recovered_app = self.make_app("ja")
        self.assertIn("復元", ask.call_args.args[1])
        recovered = self.editors(recovered_app)[0]
        self.assertIsNone(recovered.document.path)
        self.assertTrue(recovered.document.modified)
        self.assertEqual(recovered.document.text, snapshot.text)
        with patch("python_to_exe.editor.window.filedialog.asksaveasfilename", return_value=""):
            self.assertFalse(recovered.save())
        self.assertEqual(self.records(), (snapshot,))
        recovered_app.destroy()
        self.assertEqual(self.records(), (snapshot,))

        with patch("python_to_exe.converter_gui.messagebox.askyesnocancel", return_value=False):
            discarded = self.make_app()
        self.assertEqual(self.editors(discarded), [])
        self.assertEqual(self.records(), ())
        discarded.destroy()
        with patch("python_to_exe.converter_gui.messagebox.askyesnocancel") as ask:
            self.make_app()
        ask.assert_not_called()

    def test_startup_cancel_preserves_multiple_files(self):
        app = self.make_app()
        source = self.file()
        for _ in range(2):
            editor = app._create_editor(initial_path=source)
            self.edit(editor)
            self.flush(editor)
        records = self.records()
        self.assertEqual(len(records), 2)
        app.destroy()
        before = {path.name: path.read_bytes() for path in self.recovery_dir.glob("*.json")}
        with patch("python_to_exe.converter_gui.messagebox.askyesnocancel", return_value=None) as ask:
            restarted = self.make_app()
        ask.assert_called_once()
        self.assertEqual(self.editors(restarted), [])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.recovery_dir.glob("*.json")})

    def test_external_change_missing_and_same_original_restore_independently(self):
        app = self.make_app()
        source = self.file()
        for number in range(2):
            editor = app._create_editor(initial_path=source)
            self.edit(editor, f"// buffer {number}\n")
            self.flush(editor)
        snapshots = self.records()
        app.destroy()
        source.write_bytes(b"external change\n")
        with patch("python_to_exe.converter_gui.messagebox.askyesnocancel", return_value=True), \
             patch("python_to_exe.converter_gui.messagebox.showwarning") as warning:
            restarted = self.make_app()
        self.assertEqual(warning.call_count, 2)
        self.assertIn("changed", warning.call_args.args[1])
        editors = self.editors(restarted)
        self.assertEqual(len(editors), 2)
        self.assertEqual({editor.document.text for editor in editors},
                         {snapshot.text.replace("\r\n", "\n") for snapshot in snapshots})
        self.assertEqual(len({editor._recovery_id for editor in editors}), 2)
        self.assertTrue(all(editor.document.path == source and editor.document.modified for editor in editors))
        self.assertEqual(source.read_bytes(), b"external change\n")
        self.assertEqual(len(self.records()), 2)
        restarted.destroy()

        source.unlink()
        with patch("python_to_exe.converter_gui.messagebox.askyesnocancel", return_value=True), \
             patch("python_to_exe.converter_gui.messagebox.showwarning") as warning:
            missing_app = self.make_app()
        self.assertEqual(warning.call_count, 2)
        self.assertIn(missing_app.words["recovery_missing"], warning.call_args.args[1])
        self.assertFalse(source.exists())
        self.assertTrue(all(editor.document.modified for editor in self.editors(missing_app)))

    def test_close_new_open_save_discard_cancel_and_failed_open(self):
        app = self.make_app()
        target = self.file("target.txt", "0 KEY_A 0;0 0;0\n")
        for action in ("close", "new", "open"):
            for choice in (True, False, None):
                with self.subTest(action=action, choice=choice):
                    source = self.file(f"{action}-{choice}.tsv")
                    original = source.read_bytes()
                    editor = app._create_editor(initial_path=source)
                    self.edit(editor)
                    self.flush(editor)
                    old_id = editor._recovery_id
                    before = (editor.document.path, editor.document.text, editor.document.modified)
                    operation = {"close": editor.close_editor, "new": editor.new_document,
                                 "open": lambda: editor.open_file(target)}[action]
                    with patch("python_to_exe.editor.window.messagebox.askyesnocancel", return_value=choice):
                        self.assertEqual(operation(), choice is not None)
                    if choice is None:
                        self.assertEqual((editor.document.path, editor.document.text,
                                          editor.document.modified), before)
                        self.assertTrue(app.recovery_store._path(old_id).is_file())
                        app.recovery_store.delete(old_id)
                    else:
                        self.assertFalse(app.recovery_store._path(old_id).exists())
                        if action != "close":
                            self.assertNotEqual(editor._recovery_id, old_id)
                            self.assertFalse(editor.document.modified)
                    self.assertEqual(source.read_bytes() == original, choice is not True)
                    if editor.winfo_exists():
                        editor.destroy()

        editor = app._create_editor(initial_path=source)
        self.edit(editor)
        self.flush(editor)
        before = (editor.document.path, editor.document.text, self.records())
        with patch("python_to_exe.editor.window.messagebox.askyesnocancel", return_value=False), \
             patch("python_to_exe.editor.window.messagebox.showerror"):
            self.assertFalse(editor.open_file(self.folder / "missing.tsv"))
        self.assertEqual((editor.document.path, editor.document.text, self.records()), before)

    def test_parent_close_cancel_then_discard_and_untitled_save_cancel(self):
        app = self.make_app()
        editor = app._create_editor()
        self.edit(editor)
        self.flush(editor)
        with patch("python_to_exe.editor.window.messagebox.askyesnocancel", return_value=True), \
             patch("python_to_exe.editor.window.filedialog.asksaveasfilename", return_value=""):
            self.assertFalse(editor.close_editor())
        self.assertTrue(self.records())
        with patch("python_to_exe.editor.window.messagebox.askyesnocancel", return_value=None):
            self.assertFalse(app._close_app())
        self.assertTrue(app.winfo_exists())
        self.assertTrue(self.records())
        with patch("python_to_exe.editor.window.messagebox.askyesnocancel", return_value=False):
            app._close_app()
        self.assertEqual(self.records(), ())

    def test_f5_f8_save_cleanup_and_failed_removal_does_not_fail_save(self):
        app = self.make_app()
        source = self.file()
        editor = app._create_editor(initial_path=source)
        editor.on_convert = Mock(return_value=True)
        for send in (False, True):
            self.edit(editor)
            self.flush(editor)
            self.assertTrue(self.records())
            self.assertTrue(editor.save_and_convert(send_ftp=send))
            editor.on_convert.assert_called_with(source, send_ftp=send)
            self.assertFalse(editor.document.modified)
            self.assertEqual(self.records(), ())
        self.edit(editor)
        self.flush(editor)
        with patch("python_to_exe.editor.recovery.Path.unlink", side_effect=PermissionError("locked")):
            self.assertTrue(editor.save())
        self.assertFalse(editor.document.modified)
        self.assertTrue(self.records())
        self.assertIn("Recovery removal failed", app.log_text.get("1.0", "end"))

    def test_undo_redo_and_selection_do_not_mutate_recovery_or_document(self):
        app = self.make_app()
        source = self.file()
        editor = app._create_editor(initial_path=source)
        self.edit(editor)
        self.flush(editor)
        snapshot = self.records()[0]
        job = editor._recovery_job
        editor.text.mark_set("insert", "1.0")
        editor._update_status()
        editor.show_table()
        editor.table_grid._move(0, 9)
        editor.table_grid._move(20, 0)
        editor.show_raw()
        self.assertEqual(editor._recovery_job, job)
        self.assertEqual(self.records(), (snapshot,))
        self.assertTrue(editor.document.modified)
        self.assertTrue(editor.undo())
        self.assertFalse(editor.document.modified)
        self.assertEqual(self.records(), ())
        self.assertTrue(editor.redo())
        self.flush(editor)
        self.assertEqual(self.records()[0].text, snapshot.text)
        self.assertEqual(source.read_bytes(), b"1\ta\r\n1\tb\t\r\n")

    def test_abrupt_process_exit_leaves_a_restorable_untitled_buffer(self):
        # Exercise an actual process exit without Python/Tk destruction cleanup.
        self.make_app().destroy()  # Establish that this environment has real Tk.
        program = """
import os
import sys
import time
from pathlib import Path
from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp
app = TASConverterApp('en', settings=AppSettings(Path(sys.argv[1])))
app.update()
editor = app._create_editor()
editor.text.insert('1.0', '1\\ta\\t\\n// 未保存\\n')
deadline = time.monotonic() + 5
target = app.recovery_store._path(editor._recovery_id)
while time.monotonic() < deadline:
    app.update()
    if target.exists():
        os._exit(0)
    time.sleep(0.02)
os._exit(2)
"""
        result = subprocess.run([sys.executable, "-c", program, str(self.settings_path)],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.records()), 1)
        with patch("python_to_exe.converter_gui.messagebox.askyesnocancel", return_value=True):
            restarted = self.make_app()
        editor = self.editors(restarted)[0]
        self.assertIsNone(editor.document.path)
        self.assertEqual(editor.document.text, "1\ta\t\n// 未保存\n")
        self.assertTrue(editor.document.modified)
        self.assertEqual(len(self.records()), 1)

    def test_native_startup_dialog_jp_en_restores_without_mocking_messagebox(self):
        for language in ("ja", "en"):
            with self.subTest(language=language):
                store = RecoveryStore(self.recovery_dir)
                document = EditorDocument()
                document.set_text("1\ta\t\n// 日本語\n")
                snapshot = RecoverySnapshot.capture(store.new_id(), document, "Untitled 日本語")
                self.assertTrue(store.write(snapshot))
                try:
                    app = TASConverterApp(language, settings=AppSettings(self.settings_path))
                except tk.TclError as error:
                    self.skipTest(f"graphical Tk display unavailable: {error}")
                self.addCleanup(lambda root=app: root.destroy() if root._tclCommands is not None else None)
                shown, errors = [], []
                app.report_callback_exception = lambda *error: errors.append(error)
                deadline = time.monotonic() + 3

                def answer():
                    dialog = ".__tk__messagebox"
                    if app.tk.call("winfo", "exists", dialog):
                        pending, labels = [dialog], []
                        while pending:
                            widget = pending.pop()
                            pending.extend(app.tk.splitlist(app.tk.call("winfo", "children", widget)))
                            if app.tk.call("winfo", "class", widget) in ("Label", "TLabel", "Button", "TButton"):
                                labels.append(str(app.tk.call(widget, "cget", "-text")))
                        shown.append("\n".join(labels))
                        app.tk.call(dialog + ".yes", "invoke")
                    elif time.monotonic() < deadline:
                        app.after(20, answer)
                    else:
                        app.tk.setvar("tk::Priv(button)", "cancel")

                app.after(20, answer)
                app.update()
                self.assertEqual(errors, [])
                self.assertEqual(len(shown), 1)
                self.assertIn(app.words["recovery_choices"], shown[0])
                self.assertIn(snapshot.display_name, shown[0])
                editor = self.editors(app)[0]
                self.assertEqual(editor.document.text, document.text)
                self.assertTrue(editor.document.modified)
                self.assertEqual(self.records(), (snapshot,))
                with patch("python_to_exe.editor.window.messagebox.askyesnocancel", return_value=False):
                    self.assertTrue(editor.close_editor())
                app.destroy()


if __name__ == "__main__":
    unittest.main()
