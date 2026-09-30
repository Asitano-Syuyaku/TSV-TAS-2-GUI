"""Real Tk Editor save/local-convert/FTP actions; no network transfer is performed."""

import json
import subprocess
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp
from python_to_exe.editor.validation import analyze_script
from python_to_exe.editor.window import EditorWindow


ROOT = Path(__file__).resolve().parents[1]


class EditorActionTkTests(unittest.TestCase):
    def make_app(self, folder, language="en"):
        settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(settings_dir.cleanup)
        try:
            app = TASConverterApp(language, settings=AppSettings(Path(settings_dir.name) / "settings.json"))
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(app.destroy)
        app.base_dir = Path(folder)
        for entry, value in zip((app.ip_entry, app.port_entry, app.user_entry, app.pass_entry),
                                ("example.invalid", "5000", "tester", "test password")):
            entry.delete(0, "end")
            entry.insert(0, value)
        return app

    def open_editor(self, app, path=None):
        if path is not None:
            app._set_input_path(path)
        before = set(app.winfo_children())
        app.open_editor()
        editor = next(child for child in app.winfo_children()
                      if isinstance(child, EditorWindow) and child not in before)
        app.update()
        return editor

    def wait_for(self, app, condition):
        deadline = time.monotonic() + 8
        while not condition() and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        app.update()
        self.assertTrue(condition(), "background operation did not finish")

    @staticmethod
    def shortcut(widget, keysym):
        # Invoke the registered real Tk key callback without WSLg focus races.
        script = next(script for tag in widget.bindtags()
                      if (script := widget.bind_class(tag, f"<{keysym}>")))
        command = script.split("[", 1)[1].split(" ", 1)[0]
        return widget.tk.call(command, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "", 0,
                              keysym, 0, str(widget), 2, 0, 0, 0)

    @staticmethod
    def process_module(runner):
        # Do not mock the global subprocess module used by Frame Position workers.
        return SimpleNamespace(run=runner, list2cmdline=subprocess.list2cmdline,
                               CREATE_NO_WINDOW=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    @staticmethod
    def file_menu(editor):
        menu = editor.nametowidget(editor.cget("menu"))
        index = next(i for i in range(menu.index("end") + 1)
                     if menu.type(i) == "cascade" and menu.entrycget(i, "label") == editor.words["file"])
        return editor.nametowidget(menu.entrycget(index, "menu"))

    def test_jp_en_menu_shortcuts_requesting_editor_save_options_and_history(self):
        for language in ("en", "ja"):
            with self.subTest(language=language), tempfile.TemporaryDirectory(
                    prefix="tas Editor actions 日本語 ") as folder:
                work = Path(folder)
                first, second = work / "first 日本語.tsv", work / "second with spaces.tsv"
                first.write_bytes(b"1\ta\r\n")
                second.write_bytes(b"1\tx\n")
                app = self.make_app(work, language)
                editor = self.open_editor(app, first)
                other = self.open_editor(app, second)
                app.output_entry.delete(0, "end")
                app.output_entry.insert(0, str(work))
                app.outname_entry.delete(0, "end")
                app.outname_entry.insert(0, "chosen result")
                app.format_var.set("nxtas")
                app.skip_var.set(True)
                app.debug_var.set(True)
                editor.show_table()
                grid = editor.table_grid
                grid.selected = (0, 1)
                grid.begin_edit(initial="b")
                selection = grid.selection.anchor, grid.selection.active
                menu = self.file_menu(editor)
                items = {menu.entrycget(i, "label"): i for i in range(menu.index("end") + 1)}
                self.assertEqual(menu.entrycget(items[editor.words["save_convert"]], "accelerator"), "F5")
                self.assertEqual(menu.entrycget(items[editor.words["save_convert_send"]], "accelerator"), "F8")
                calls = []

                def runner(command, **options):
                    # The source must already contain the committed/saved cell.
                    calls.append((command, Path(command[-2]).read_bytes()))
                    return subprocess.CompletedProcess(command, 0, "generated\n", "")

                with patch("python_to_exe.converter_gui.subprocess", self.process_module(runner)), \
                     patch("python_to_exe.converter_gui.messagebox.showinfo"):
                    app.ftp_var.set(True)
                    self.assertEqual(self.shortcut(grid.canvas, "F5"), "break")
                    self.wait_for(app, lambda: not app._busy())
                    self.assertEqual(calls[-1][1], b"1\tb\r\n")
                    self.assertIn("-ned", calls[-1][0])
                    self.assertNotIn("-fned", calls[-1][0])
                    self.assertEqual(app.input_entry.get(), str(first))
                    self.assertEqual((grid.selection.anchor, grid.selection.active), selection)
                    self.assertFalse(editor.document.modified)
                    self.assertFalse((work / "ftp_config.json").exists())
                    self.assertTrue(app.ftp_var.get())
                    # Saving retains the shared Raw/Table Undo and Redo history.
                    editor.undo()
                    self.assertEqual(editor.document.text, "1\ta\n")
                    self.assertTrue(editor.document.modified)
                    editor.redo()
                    self.assertEqual(editor.document.text, "1\tb\n")
                    self.assertFalse(editor.document.modified)

                    other.save()  # Simulate another Editor taking over Input.
                    self.assertEqual(app.input_entry.get(), str(second))
                    app.ftp_var.set(False)
                    grid.begin_edit(initial="zl")
                    self.assertEqual(self.shortcut(grid._editor, "F8"), "break")
                    self.wait_for(app, lambda: not app._busy())
                    self.assertEqual(calls[-1][1], b"1\tzl\r\n")
                    self.assertIn("-fned", calls[-1][0])
                    self.assertEqual(app.input_entry.get(), str(first))
                    self.assertEqual(app.output_entry.get(), str(work))
                    self.assertEqual(app.outname_entry.get(), "chosen result")
                    self.assertFalse(app.ftp_var.get())
                    self.assertTrue(app.debug_var.get())
                    self.assertTrue(app.skip_var.get())
                    self.assertFalse(editor.document.modified)
                    self.assertEqual(json.loads((work / "ftp_config.json").read_text(encoding="utf-8")),
                                     dict(ip="example.invalid", port=5000,
                                          user="tester", passwd="test password"))
                    log = app.log_text.get("1.0", "end")
                    self.assertIn(app.words["editor_local"], log)
                    self.assertIn(app.words["editor_send"], log)
                    self.assertEqual(len(calls), 2)
                self.doCleanups()

    def test_untitled_cancel_both_actions_then_send_saves_real_file_and_fills_outputs(self):
        with tempfile.TemporaryDirectory(prefix="tas untitled 日本語 ") as folder:
            work = Path(folder)
            app = self.make_app(work)
            editor = self.open_editor(app)
            editor.text.insert("1.0", "1\ta")
            app.update()
            calls = []

            def runner(command, **options):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("python_to_exe.converter_gui.subprocess", self.process_module(runner)), \
                 patch("python_to_exe.converter_gui.messagebox.showinfo"), \
                 patch("python_to_exe.editor.window.filedialog.asksaveasfilename", return_value="") as save_as:
                before = editor.text.index("insert")
                for action in (editor.save_and_convert, editor.save_convert_and_send):
                    self.assertFalse(action())
                    self.assertIsNone(editor.document.path)
                    self.assertTrue(editor.document.modified)
                    self.assertEqual(editor.text.index("insert"), before)
                self.assertEqual(save_as.call_count, 2)
                self.assertEqual(calls, [])
                self.assertFalse(app._busy())
                self.assertEqual(app.input_entry.get(), "")
                self.assertEqual(list(work.iterdir()), [])
                editor.undo()
                self.assertEqual(editor.document.text, "")
                editor.redo()
                self.assertEqual(editor.document.text, "1\ta")

                source = work / "新規 with spaces.tsv"
                save_as.return_value = str(source)
                app.ftp_var.set(False)
                self.assertTrue(editor.save_convert_and_send())
                self.wait_for(app, lambda: not app._busy())
                self.assertEqual(source.read_bytes(), b"1\ta")
                self.assertEqual(Path(calls[0][-2]), source)
                self.assertIn("-f", calls[0])
                self.assertEqual(app.input_entry.get(), str(source))
                self.assertEqual(app.output_entry.get(), str(work))
                self.assertEqual(app.outname_entry.get(), source.stem)
                self.assertEqual(editor.document.path, source)
                self.assertFalse(editor.document.modified)

    def test_repeated_f5_f8_checks_and_analyze_to_send_are_busy_protected(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            source = work / "script.tsv"
            source.write_text("1\ta", encoding="utf-8")
            app = self.make_app(work)
            editor = self.open_editor(app, source)
            calls = []
            for send in (False, True):
                started, release = threading.Event(), threading.Event()

                def runner(command, **options):
                    calls.append(command)
                    started.set()
                    release.wait(5)
                    return subprocess.CompletedProcess(command, 0, "", "")

                with patch("python_to_exe.converter_gui.subprocess", self.process_module(runner)), \
                     patch("python_to_exe.converter_gui.messagebox.showinfo"):
                    action = editor.save_convert_and_send if send else editor.save_and_convert
                    self.assertTrue(action())
                    self.wait_for(app, started.is_set)
                    for _ in range(10):
                        self.assertFalse(editor.save_and_convert())
                        self.assertFalse(editor.save_convert_and_send())
                    self.assertFalse(editor.validate())
                    self.assertFalse(editor.analyze_frames())
                    self.assertFalse(app.start_conversion())
                    self.assertEqual(app.convert_btn.cget("state"), "disabled")
                    release.set()
                    self.wait_for(app, lambda: not app._busy())
                    self.assertEqual(app.convert_btn.cget("state"), "normal")
            self.assertEqual(len(calls), 2)

            started, release = threading.Event(), threading.Event()

            def delayed(snapshot, output_format, skip_empty, base_dir):
                started.set()
                release.wait(5)
                return analyze_script(snapshot, output_format, skip_empty, ROOT)

            with patch("python_to_exe.editor.validation.analyze_script", delayed):
                self.assertTrue(editor.analyze_frames())
                self.wait_for(app, started.is_set)
                self.assertFalse(editor.save_convert_and_send())
                self.assertFalse(editor.save_and_convert())
                release.set()
                self.wait_for(app, lambda: not app._busy())
            self.assertEqual(source.read_text(encoding="utf-8"), "1\ta")
            self.assertEqual(len(calls), 2)
