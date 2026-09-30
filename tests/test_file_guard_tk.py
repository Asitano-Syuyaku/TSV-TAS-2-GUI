"""Real Tk external-save warnings and Editor workflow, with isolated config."""

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


class FileGuardTkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tas file guard 日本語 ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.settings_path = self.folder / "config" / "settings.json"

    def make_app(self, language="en"):
        try:
            app = TASConverterApp(language, settings=AppSettings(self.settings_path))
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(lambda: app.destroy() if app._tclCommands is not None else None)
        app.update()
        return app

    def source(self, name="input 日本語.tsv"):
        path = self.folder / name
        path.write_bytes("1\ta\t\r\n// 日本語\n1\tb\r\n".encode("utf-8"))
        return path

    @staticmethod
    def edit(editor):
        editor.text.edit_separator()
        editor.text.insert("end-1c", "// 未保存\n")
        editor.text.edit_separator()
        editor._sync_text()

    @staticmethod
    def flush(editor):
        if editor._recovery_job is not None:
            editor.after_cancel(editor._recovery_job)
            editor._recovery_job = None
        editor._write_recovery()

    @staticmethod
    def state(editor):
        return (editor.document.path, editor.document.text, editor.document.modified,
                editor.document._saved_raw, editor.text.get("1.0", "end-1c"),
                editor.text.index("insert"), editor.text.edit("canundo"), editor.text.edit("canredo"),
                editor._view, editor.table_grid.selection.bounds)

    @staticmethod
    def shortcut(widget, sequence):
        # Invoke the real registered Tk binding, avoiding WSLg window focus races.
        script = next(script for tag in widget.bindtags()
                      if (script := widget.bind_class(tag, f"<{sequence}>")))
        command = script.split("[", 1)[1].split(" ", 1)[0]
        key = sequence.rsplit("-", 1)[-1]
        return widget.tk.call(command, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "", 0,
                              key, 0, str(widget), 2, 0, 0, 0)

    def test_ctrl_s_changed_no_yes_and_second_save_preserve_history_newlines(self):
        for language in ("ja", "en"):
            with self.subTest(language=language):
                app = self.make_app(language)
                source = self.source()
                editor = app._create_editor(initial_path=source)
                self.edit(editor)
                self.flush(editor)
                recovery_path = app.recovery_store._path(editor._recovery_id)
                recovery = recovery_path.read_bytes()
                expected = editor.document._serialize().encode("utf-8")
                before = self.state(editor)
                source.write_bytes(b"external content\n")
                with patch("python_to_exe.editor.window.messagebox.askyesno", return_value=False) as ask:
                    self.assertEqual(self.shortcut(editor.text, "Control-s"), "break")
                ask.assert_called_once()
                self.assertIn(editor.words["external_changed"], ask.call_args.args[1])
                self.assertEqual(ask.call_args.kwargs["default"], "no")
                self.assertEqual(source.read_bytes(), b"external content\n")
                self.assertEqual(self.state(editor), before)
                self.assertEqual(recovery_path.read_bytes(), recovery)
                with patch("python_to_exe.editor.window.messagebox.askyesno", return_value=True) as ask:
                    self.assertEqual(self.shortcut(editor.text, "Control-s"), "break")
                ask.assert_called_once()
                self.assertEqual(source.read_bytes(), expected)
                self.assertFalse(editor.document.modified)
                self.assertFalse(recovery_path.exists())
                self.assertEqual(editor.document.external_status(), "unchanged")
                with patch("python_to_exe.editor.window.messagebox.askyesno") as ask:
                    self.assertTrue(editor.save())
                ask.assert_not_called()
                self.assertTrue(editor.undo())
                self.assertTrue(editor.document.modified)
                self.assertTrue(editor.redo())
                self.assertFalse(editor.document.modified)
                app.destroy()

    def test_missing_no_yes_and_unreadable_never_overwrite(self):
        app = self.make_app()
        source = self.source("input.txt")
        editor = app._create_editor(initial_path=source)
        self.edit(editor)
        self.flush(editor)
        recovery_path = app.recovery_store._path(editor._recovery_id)
        before, recovery = self.state(editor), recovery_path.read_bytes()
        source.unlink()
        with patch("python_to_exe.editor.window.messagebox.askyesno", return_value=False) as ask:
            self.assertFalse(editor.save())
        self.assertIn(editor.words["external_missing"], ask.call_args.args[1])
        self.assertFalse(source.exists())
        self.assertEqual(self.state(editor), before)
        self.assertEqual(recovery_path.read_bytes(), recovery)
        with patch("python_to_exe.editor.window.messagebox.askyesno", return_value=True):
            self.assertTrue(editor.save())
        self.assertTrue(source.exists())
        self.assertFalse(recovery_path.exists())

        self.edit(editor)
        self.flush(editor)
        before, recovery, disk = self.state(editor), recovery_path.read_bytes(), source.read_bytes()
        with patch("python_to_exe.editor.document.disk_status", return_value="unreadable"), \
             patch("python_to_exe.editor.window.messagebox.askyesno") as ask, \
             patch("python_to_exe.editor.window.messagebox.showerror") as error, \
             patch.object(editor.document, "save") as save:
            self.assertFalse(editor.save())
            ask.assert_not_called()
            save.assert_not_called()
            self.assertIn(editor.words["external_unreadable"], error.call_args.args[1])
        self.assertEqual(self.state(editor), before)
        self.assertEqual(source.read_bytes(), disk)
        self.assertEqual(recovery_path.read_bytes(), recovery)

    def test_save_as_same_path_is_guarded_but_other_target_uses_dialog_overwrite(self):
        app = self.make_app()
        source = self.source()
        editor = app._create_editor(initial_path=source)
        self.edit(editor)
        self.flush(editor)
        source.write_bytes(b"external content")
        alias = str(source.parent) + "/./" + source.name
        before = self.state(editor)
        with patch("python_to_exe.editor.window.filedialog.asksaveasfilename", return_value=alias), \
             patch("python_to_exe.editor.window.messagebox.askyesno", return_value=False) as ask:
            self.assertFalse(editor.save_as())
        ask.assert_called_once()
        self.assertEqual(self.state(editor), before)
        self.assertEqual(source.read_bytes(), b"external content")
        target = self.folder / "existing copy.txt"
        target.write_bytes(b"existing file chosen in Save As")
        # The real file dialog/OS owns overwrite confirmation for a different target.
        with patch("python_to_exe.editor.window.filedialog.asksaveasfilename", return_value=str(target)), \
             patch("python_to_exe.editor.window.messagebox.askyesno") as ask:
            self.assertTrue(editor.save_as())
        ask.assert_not_called()
        self.assertEqual(editor.document.path, target)
        self.assertEqual(editor.document.external_status(), "unchanged")
        self.assertEqual(source.read_bytes(), b"external content")
        self.assertFalse(app.recovery_store._path(editor._recovery_id).exists())

    def test_f5_f8_refusal_stops_converter_ftp_even_when_buffer_is_unmodified(self):
        app = self.make_app()
        for dirty in (False, True):
            for status in ("changed", "missing", "unreadable"):
                for send in (False, True):
                    with self.subTest(dirty=dirty, status=status, send=send):
                        source = self.source()
                        editor = app._create_editor(initial_path=source)
                        if dirty:
                            self.edit(editor)
                            self.flush(editor)
                        before = self.state(editor)
                        recovery_path = app.recovery_store._path(editor._recovery_id)
                        recovery = recovery_path.read_bytes() if dirty else None
                        app.ftp_var.set(not send)
                        if status == "missing":
                            source.unlink()
                        elif status == "changed":
                            source.write_bytes(b"external edit")
                        with patch("python_to_exe.editor.document.disk_status", return_value=status), \
                             patch("python_to_exe.editor.window.messagebox.askyesno", return_value=False), \
                             patch("python_to_exe.editor.window.messagebox.showerror"), \
                             patch.object(app, "start_conversion") as convert:
                            key = "F8" if send else "F5"
                            self.assertEqual(self.shortcut(editor.text, key), "break")
                            convert.assert_not_called()
                        self.assertFalse(app._busy())
                        self.assertEqual(self.state(editor), before)
                        self.assertEqual(recovery_path.read_bytes() if dirty else None, recovery)
                        self.assertFalse((self.folder / "ftp_config.json").exists())
                        if status == "changed":
                            self.assertEqual(source.read_bytes(), b"external edit")
                        if status == "missing":
                            self.assertFalse(source.exists())
                        # Isolated test cleanup, not a normal discard/save path.
                        app.recovery_store.delete(editor._recovery_id)
                        editor.destroy()

    def test_f5_f8_yes_saves_before_request_with_correct_ftp_override(self):
        app = self.make_app()
        for send in (False, True):
            with self.subTest(send=send):
                source = self.source()
                editor = app._create_editor(initial_path=source)
                self.edit(editor)
                self.flush(editor)
                expected = editor.document._serialize().encode("utf-8")
                source.write_bytes(b"external edit")
                app.ftp_var.set(not send)

                def start(ftp_override=None):
                    self.assertEqual(ftp_override, send)
                    self.assertEqual(source.read_bytes(), expected)
                    self.assertFalse(editor.document.modified)
                    self.assertEqual(app.input_entry.get(), str(source))
                    self.assertFalse(app.recovery_store._path(editor._recovery_id).exists())
                    return True

                with patch("python_to_exe.editor.window.messagebox.askyesno", return_value=True), \
                     patch.object(app, "start_conversion", side_effect=start) as convert:
                    self.assertTrue(editor.save_and_convert(send_ftp=send))
                convert.assert_called_once_with(ftp_override=send)
                editor.destroy()

    def test_pending_table_entry_no_preserves_entry_selection_undo_and_recovery(self):
        app = self.make_app()
        source = self.source()
        editor = app._create_editor(initial_path=source)
        editor.show_table()
        app.update()
        grid = editor.table_grid
        grid.selected = (0, 1)
        grid.begin_edit(initial="未確定")
        self.flush(editor)
        recovery_path = app.recovery_store._path(editor._recovery_id)
        recovery = recovery_path.read_bytes()
        before, entry = self.state(editor), grid._editor
        source.write_bytes(b"external edit")
        with patch("python_to_exe.editor.window.messagebox.askyesno", return_value=False), \
             patch.object(app, "start_conversion") as convert:
            for key in ("Control-s", "F5", "F8"):
                self.assertEqual(self.shortcut(entry, key), "break")
                self.assertEqual(self.state(editor), before)
                self.assertIs(grid._editor, entry)
                self.assertEqual(entry.get(), "未確定")
                self.assertEqual(recovery_path.read_bytes(), recovery)
            convert.assert_not_called()

    def test_recovery_startup_warning_then_save_guard_keeps_old_baseline(self):
        for status in ("changed", "missing"):
            with self.subTest(status=status):
                source = self.source()
                document = EditorDocument()
                document.open(source)
                baseline = document._saved_raw
                document.set_text(document.text + "// 復旧\n")
                store = RecoveryStore(self.settings_path.parent / "recovery")
                snapshot = RecoverySnapshot.capture(store.new_id(), document, source.name)
                store.write(snapshot)
                if status == "changed":
                    source.write_bytes(b"external edit")
                else:
                    source.unlink()
                with patch("python_to_exe.converter_gui.messagebox.askyesnocancel", return_value=True), \
                     patch("python_to_exe.converter_gui.messagebox.showwarning") as warning:
                    app = self.make_app()
                warning.assert_called_once()
                # Headless tests reload window.py, so use the current factory class.
                from python_to_exe.editor.window import EditorWindow
                editor = next(child for child in app.winfo_children() if isinstance(child, EditorWindow))
                self.assertEqual(editor.document._saved_raw, baseline)
                self.assertTrue(editor.document.modified)
                recovery_path = app.recovery_store._path(editor._recovery_id)
                recovery = recovery_path.read_bytes()
                before = self.state(editor)
                with patch("python_to_exe.editor.window.messagebox.askyesno", return_value=False) as ask:
                    self.assertFalse(editor.save())
                self.assertIn(editor.words["external_" + status], ask.call_args.args[1])
                self.assertEqual(self.state(editor), before)
                self.assertEqual(recovery_path.read_bytes(), recovery)
                self.assertEqual(source.exists(), status != "missing")
                if status == "changed":
                    self.assertEqual(source.read_bytes(), b"external edit")
                target = self.folder / (status + " recovered.tsv")
                with patch("python_to_exe.editor.window.filedialog.asksaveasfilename", return_value=str(target)):
                    self.assertTrue(editor.save_as())
                self.assertEqual(editor.document.external_status(), "unchanged")
                self.assertFalse(recovery_path.exists())
                app.destroy()

    def test_failed_save_and_read_only_snapshot_actions_do_not_update_baseline(self):
        app = self.make_app()
        source = self.source()
        editor = app._create_editor(initial_path=source)
        self.edit(editor)
        self.flush(editor)
        baseline = editor.document._saved_raw
        source.write_bytes(b"external edit")
        recovery_path = app.recovery_store._path(editor._recovery_id)
        recovery = recovery_path.read_bytes()
        with patch("python_to_exe.editor.window.messagebox.askyesno", return_value=True), \
             patch("python_to_exe.editor.window.messagebox.showerror"), \
             patch.object(editor.document, "save", side_effect=OSError("disk full")):
            self.assertFalse(editor.save())
        self.assertEqual(editor.document._saved_raw, baseline)
        self.assertEqual(recovery_path.read_bytes(), recovery)
        self.assertEqual(source.read_bytes(), b"external edit")
        # These callbacks take snapshots and intentionally do not save any disk file.
        editor.on_validate = Mock(return_value=True)
        editor.can_validate = lambda: True
        self.assertTrue(editor.validate())
        editor.on_analyze = Mock(return_value=True)
        editor.can_analyze = lambda: True
        self.assertTrue(editor.analyze_frames())
        self.flush(editor)
        self.assertEqual(editor.document._saved_raw, baseline)
        self.assertEqual(editor.document.external_status(), "changed")
        self.assertEqual(source.read_bytes(), b"external edit")

    def test_disk_recheck_blocks_new_conflict_or_unreadable_after_confirmation(self):
        app = self.make_app()
        source = self.source()
        editor = app._create_editor(initial_path=source)
        self.edit(editor)
        self.flush(editor)
        source.write_bytes(b"external edit")
        recovery_path = app.recovery_store._path(editor._recovery_id)
        before, recovery = self.state(editor), recovery_path.read_bytes()
        for statuses, message, asks in ((["unchanged", "changed"], "external_retry", 0),
                                        (["changed", "unreadable"], "external_unreadable", 1)):
            with self.subTest(statuses=statuses), \
                 patch.object(editor.document, "external_status", side_effect=statuses), \
                 patch("python_to_exe.editor.window.messagebox.askyesno", return_value=True) as ask, \
                 patch("python_to_exe.editor.window.messagebox.showerror") as error:
                self.assertFalse(editor.save())
                self.assertEqual(ask.call_count, asks)
                self.assertIn(editor.words[message], error.call_args.args[1])
            self.assertEqual(self.state(editor), before)
            self.assertEqual(recovery_path.read_bytes(), recovery)
            self.assertEqual(source.read_bytes(), b"external edit")

    def test_native_jp_en_ctrl_s_changed_and_missing_dialogs(self):
        for language in ("ja", "en"):
            with self.subTest(language=language):
                app = self.make_app(language)
                source = self.source()
                editor = app._create_editor(initial_path=source)
                self.edit(editor)
                expected = editor.document._serialize().encode("utf-8")
                errors = []
                app.report_callback_exception = lambda *error: errors.append(error)
                for status in ("changed", "missing"):
                    if status == "changed":
                        source.write_bytes(b"external edit")
                    else:
                        source.unlink()
                    for consent in (False, True):
                        shown, deadline = [], time.monotonic() + 3

                        def answer():
                            dialog = str(editor) + ".__tk__messagebox"
                            if app.tk.call("winfo", "exists", dialog):
                                pending, labels = [dialog], []
                                while pending:
                                    widget = pending.pop()
                                    pending.extend(app.tk.splitlist(app.tk.call("winfo", "children", widget)))
                                    if app.tk.call("winfo", "class", widget) in ("Label", "TLabel", "Button", "TButton"):
                                        labels.append(str(app.tk.call(widget, "cget", "-text")))
                                shown.append("\n".join(labels))
                                app.tk.call(dialog + (".yes" if consent else ".no"), "invoke")
                            elif time.monotonic() < deadline:
                                app.after(20, answer)
                            else:
                                app.tk.setvar("tk::Priv(button)", "cancel")

                        app.after(20, answer)
                        self.assertEqual(self.shortcut(editor.text, "Control-s"), "break")
                        self.assertEqual(errors, [])
                        self.assertEqual(len(shown), 1)
                        self.assertIn(editor.words["external_" + status], shown[0])
                        if consent:
                            self.assertEqual(source.read_bytes(), expected)
                        elif status == "changed":
                            self.assertEqual(source.read_bytes(), b"external edit")
                        else:
                            self.assertFalse(source.exists())
                app.destroy()


if __name__ == "__main__":
    unittest.main()
