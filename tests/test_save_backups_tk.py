"""Real Tk save/backup integration; isolated config and no FTP transfer."""

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp
from python_to_exe.editor.save_backups import backup_path


class SaveBackupTkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tas backup Tk 日本語 ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def make_app(self, language="en"):
        try:
            app = TASConverterApp(language, settings=AppSettings(self.folder / "config/settings.json"))
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(lambda: app.destroy() if app._tclCommands is not None else None)
        self.callback_errors = []
        app.report_callback_exception = lambda *error: self.callback_errors.append(error)
        app.update()
        return app

    def source(self, name="route with spaces 日本語.tsv"):
        target = self.folder / name
        target.write_bytes("1\ta\t\r\n// 日本語\n".encode("utf-8"))
        return target

    @staticmethod
    def edit(editor):
        editor.text.edit_separator()
        editor.text.insert("end-1c", "1\tb\n")
        editor.text.edit_separator()
        editor._sync_text()
        if editor._recovery_job is not None:
            editor.after_cancel(editor._recovery_job)
            editor._recovery_job = None
        editor._write_recovery()

    @staticmethod
    def shortcut(widget, sequence):
        # Run the registered real Tk binding without relying on WSLg focus timing.
        script = next(script for tag in widget.bindtags()
                      if (script := widget.bind_class(tag, f"<{sequence}>")))
        command = script.split("[", 1)[1].split(" ", 1)[0]
        key = sequence.rsplit("-", 1)[-1]
        return widget.tk.call(command, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "", 0,
                              key, 0, str(widget), 2, 0, 0, 0)

    @staticmethod
    def state(editor):
        return (editor.document.__dict__.copy(), editor.text.get("1.0", "end-1c"),
                editor.text.index("insert"), editor.text.edit("canundo"),
                editor.text.edit("canredo"), editor.table_grid.selection.bounds, editor._view)

    def history(self, target):
        return {path.name: path.read_bytes() for path in target.parent.glob(target.name + ".before*")}

    def test_ctrl_s_rotation_preserves_selection_undo_and_removes_recovery(self):
        for language in ("ja", "en"):
            with self.subTest(language=language):
                app = self.make_app(language)
                target = self.source()
                original = target.read_bytes()
                editor = app._create_editor(initial_path=target)
                self.edit(editor)
                expected = editor.document._serialize().encode("utf-8")
                editor.show_table()
                app.update()
                editor.table_grid.selected = (0, 1)
                selection = editor.table_grid.selection.bounds
                recovery = app.recovery_store._path(editor._recovery_id)
                self.assertTrue(recovery.exists())
                self.assertEqual(self.shortcut(editor.table_grid.canvas, "Control-s"), "break")
                self.assertEqual(target.read_bytes(), expected)
                self.assertEqual(backup_path(target, 1).read_bytes(), original)
                self.assertEqual(editor.table_grid.selection.bounds, selection)
                self.assertFalse(editor.document.modified)
                self.assertFalse(recovery.exists())
                self.assertTrue(editor.undo())
                self.assertTrue(editor.document.modified)
                self.assertTrue(editor.redo())
                self.assertFalse(editor.document.modified)
                # Another explicit save backs up the actual current disk version.
                self.assertTrue(editor.save())
                self.assertEqual(backup_path(target, 1).read_bytes(), expected)
                self.assertEqual(backup_path(target, 2).read_bytes(), original)
                self.assertEqual(app.settings.recent_files, (str(target),))
                app.update()
                self.assertEqual(self.callback_errors, [])
                app.destroy()

    def test_external_no_does_not_rotate_yes_captures_external_disk_bytes(self):
        app = self.make_app()
        target = self.source()
        editor = app._create_editor(initial_path=target)
        self.edit(editor)
        expected = editor.document._serialize().encode("utf-8")
        backup_path(target, 1).write_bytes(b"older history")
        external = b"external disk\xff\r\n\n"
        target.write_bytes(external)
        state, history = self.state(editor), self.history(target)
        recovery = app.recovery_store._path(editor._recovery_id)
        recovery_bytes = recovery.read_bytes()
        with patch("python_to_exe.editor.window.messagebox.askyesno", return_value=False):
            self.assertFalse(editor.save())
        self.assertEqual(self.state(editor), state)
        self.assertEqual(self.history(target), history)
        self.assertEqual(recovery.read_bytes(), recovery_bytes)
        self.assertEqual(target.read_bytes(), external)
        with patch("python_to_exe.editor.window.messagebox.askyesno", return_value=True):
            self.assertTrue(editor.save())
        self.assertEqual(backup_path(target, 1).read_bytes(), external)
        self.assertEqual(backup_path(target, 2).read_bytes(), b"older history")
        self.assertEqual(target.read_bytes(), expected)
        self.assertFalse(recovery.exists())

    def test_save_as_targets_only_destination_and_never_registers_backups(self):
        app = self.make_app()
        source = self.source()
        editor = app._create_editor(initial_path=source)
        self.edit(editor)
        backup_path(source, 1).write_bytes(b"source history")
        old_source, history = source.read_bytes(), self.history(source)
        fresh = self.folder / "new destination.tsv"
        existing = self.folder / "existing destination.tsv"
        existing.write_bytes(b"destination\r\n")
        for target in (fresh, existing):
            with patch("python_to_exe.editor.window.filedialog.asksaveasfilename",
                       return_value=str(target)):
                self.assertTrue(editor.save_as())
            self.assertEqual(editor.document.path, target)
        self.assertEqual(self.history(fresh), {})
        self.assertEqual(backup_path(existing, 1).read_bytes(), b"destination\r\n")
        self.assertEqual(source.read_bytes(), old_source)
        self.assertEqual(self.history(source), history)
        self.assertTrue(all(Path(path).suffix == ".tsv" for path in app.settings.recent_files))
        self.assertEqual(list(app.recovery_store.directory.glob("*.json")), [])

    def test_f5_f8_save_backup_before_requesting_conversion_with_ftp_override(self):
        app = self.make_app()
        for send in (False, True):
            with self.subTest(send=send):
                target = self.source(f"action {send}.tsv")
                original = target.read_bytes()
                editor = app._create_editor(initial_path=target)
                self.edit(editor)
                expected = editor.document._serialize().encode("utf-8")
                app.ftp_var.set(not send)

                def start(ftp_override=None):
                    self.assertEqual(ftp_override, send)
                    self.assertEqual(target.read_bytes(), expected)
                    self.assertEqual(backup_path(target, 1).read_bytes(), original)
                    self.assertFalse(editor.document.modified)
                    self.assertFalse(app.recovery_store._path(editor._recovery_id).exists())
                    self.assertEqual(app.input_entry.get(), str(target))
                    return True

                with patch.object(app, "start_conversion", side_effect=start) as convert:
                    self.assertEqual(self.shortcut(editor.text, "F8" if send else "F5"), "break")
                    convert.assert_called_once_with(ftp_override=send)
                self.assertEqual(app.ftp_var.get(), not send)
                editor.destroy()
        app.update()
        self.assertEqual(self.callback_errors, [])

    def test_backup_failure_stops_f5_f8_keeps_disk_buffer_undo_and_recovery(self):
        app = self.make_app()
        for send in (False, True):
            with self.subTest(send=send):
                target = self.source(f"failed {send}.tsv")
                original = target.read_bytes()
                backup_path(target, 1).write_bytes(b"prior history")
                editor = app._create_editor(initial_path=target)
                self.edit(editor)
                before, history = self.state(editor), self.history(target)
                recovery = app.recovery_store._path(editor._recovery_id)
                recovery_bytes = recovery.read_bytes()
                with patch("python_to_exe.editor.save_backups.shutil.copyfileobj",
                           side_effect=OSError("backup disk full")), \
                     patch("python_to_exe.editor.window.messagebox.showerror") as error, \
                     patch.object(app, "start_conversion") as convert:
                    self.assertEqual(self.shortcut(editor.text, "F8" if send else "F5"), "break")
                    convert.assert_not_called()
                    self.assertIn("backup disk full", error.call_args.args[1])
                self.assertEqual(target.read_bytes(), original)
                self.assertEqual(self.history(target), history)
                self.assertEqual(self.state(editor), before)
                self.assertEqual(recovery.read_bytes(), recovery_bytes)
                self.assertFalse(app._busy())
                self.assertEqual(list(self.folder.glob(".tas-*-*")), [])
                editor.destroy()
        self.assertEqual(self.callback_errors, [])

    def test_external_refusals_block_f5_f8_before_any_backup_io(self):
        app = self.make_app()
        for status in ("changed", "missing", "unreadable"):
            for send in (False, True):
                with self.subTest(status=status, send=send):
                    target = self.source()
                    editor = app._create_editor(initial_path=target)
                    self.edit(editor)
                    before = self.state(editor)
                    backup_path(target, 1).write_bytes(b"older history")
                    history = self.history(target)
                    with patch("python_to_exe.editor.document.disk_status", return_value=status), \
                         patch("python_to_exe.editor.window.messagebox.askyesno", return_value=False), \
                         patch("python_to_exe.editor.window.messagebox.showerror"), \
                         patch("python_to_exe.editor.document.create_save_backup") as backup, \
                         patch.object(app, "start_conversion") as convert:
                        self.assertFalse(editor.save_and_convert(send_ftp=send))
                        backup.assert_not_called()
                        convert.assert_not_called()
                    self.assertEqual(self.state(editor), before)
                    self.assertEqual(self.history(target), history)
                    self.assertTrue(app.recovery_store._path(editor._recovery_id).exists())
                    editor.destroy()


if __name__ == "__main__":
    unittest.main()
