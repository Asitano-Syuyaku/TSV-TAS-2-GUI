"""Expected artifacts, native folder launch, and confirmed conversion results."""

import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from queue import SimpleQueue
from types import SimpleNamespace
from unittest.mock import Mock, patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp, TEXT
from python_to_exe.converter_logic import build_commands, conversion_outputs, open_output_folder


ROOT = Path(__file__).resolve().parents[1]


class OutputPathsTests(unittest.TestCase):
    def test_paths_match_command_builder_for_all_formats_and_input_types(self):
        with tempfile.TemporaryDirectory(prefix="tas output 日本語 ") as folder:
            work = Path(folder)
            for extension in (".tsv", ".txt"):
                source = work / ("input with spaces" + extension)
                source.write_text("1\ta\n" if extension == ".tsv" else "0 KEY_A 0;0 0;0\n")
                for output_format, suffix in (("binary", ""), ("stas", ".stas"), ("nxtas", ".txt")):
                    with self.subTest(extension=extension, output_format=output_format):
                        outputs = conversion_outputs(source, work, "出力 with.dots", output_format,
                                                     debug=True, ftp=True)
                        primary = work / ("出力 with.dots" + suffix)
                        self.assertEqual(outputs.primary, primary)
                        self.assertEqual(outputs.debug_csv, Path(str(primary) + "-debug.csv"))
                        self.assertEqual(outputs.intermediate_tsv,
                                         work / "出力 with.dots.tsv" if extension == ".txt" else None)
                        self.assertTrue(outputs.ftp_requested)
                        commands = build_commands(source, work, "出力 with.dots", output_format,
                                                  debug=True, ftp=True, base_dir=ROOT,
                                                  interpreter=[sys.executable])
                        self.assertEqual(Path(commands[-1][-1]), outputs.primary)
                        self.assertEqual(Path(commands[-1][-2]), outputs.intermediate_tsv or source)
                        if outputs.intermediate_tsv:
                            self.assertEqual(Path(commands[0][-1]), outputs.intermediate_tsv)

    def test_metadata_needs_no_generated_files_and_optional_outputs_are_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            source, directory = Path(folder) / "input.tsv", Path(folder) / "not created"
            outputs = conversion_outputs(source, directory, "plain", "binary")
            self.assertEqual(outputs.primary, directory / "plain")
            self.assertIsNone(outputs.debug_csv)
            self.assertIsNone(outputs.intermediate_tsv)
            self.assertFalse(outputs.ftp_requested)
            self.assertFalse(source.exists())
            self.assertFalse(directory.exists())
            with self.assertRaisesRegex(ValueError, "Unknown output format"):
                conversion_outputs(source, directory, "plain", "unknown")

    def test_real_converter_artifacts_match_metadata_for_tsv_and_txt(self):
        with tempfile.TemporaryDirectory(prefix="tas artifacts 日本語 ") as folder:
            work = Path(folder)
            for extension in (".tsv", ".txt"):
                source = work / ("input with spaces" + extension)
                source.write_text("1\ta\n1\tb\n" if extension == ".tsv"
                                  else "0 KEY_A 0;0 0;0\n1 KEY_B 0;0 0;0\n", encoding="utf-8")
                for output_format, signature in (("binary", b"BOOB"), ("stas", b"STAS"), ("nxtas", b"0 ")):
                    with self.subTest(extension=extension, output_format=output_format):
                        name = "resolved 日本語 " + extension[1:] + output_format
                        outputs = conversion_outputs(source, work, name, output_format, debug=True)
                        for command in build_commands(source, work, name, output_format, debug=True,
                                                      base_dir=ROOT, interpreter=[sys.executable]):
                            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
                            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertTrue(outputs.primary.read_bytes().startswith(signature))
                        self.assertTrue(outputs.debug_csv.read_bytes().startswith(b"Frame,2ndPlayer,"))
                        if outputs.intermediate_tsv:
                            self.assertIn("a", outputs.intermediate_tsv.read_text(encoding="utf-8"))


class FolderOpenTests(unittest.TestCase):
    def test_windows_startfile_without_subprocess(self):
        with tempfile.TemporaryDirectory(prefix="tas folder 日本語 ") as folder, \
             patch("python_to_exe.converter_logic.sys.platform", "win32"), \
             patch.object(os, "startfile", create=True) as start, \
             patch("python_to_exe.converter_logic.subprocess.run") as run:
            open_output_folder(folder)
            start.assert_called_once_with(str(Path(folder).resolve()))
            run.assert_not_called()

    def test_linux_and_macos_safe_argument_lists(self):
        with tempfile.TemporaryDirectory(prefix="tas folder 日本語 ") as folder:
            for platform, launcher in (("linux", "xdg-open"), ("darwin", "open")):
                with self.subTest(platform=platform), \
                     patch("python_to_exe.converter_logic.sys.platform", platform), \
                     patch("python_to_exe.converter_logic.subprocess.run") as run:
                    open_output_folder(folder)
                    self.assertEqual(run.call_args.args[0], [launcher, str(Path(folder).resolve())])
                    self.assertTrue(run.call_args.kwargs["check"])
                    self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_invalid_folder_never_launches(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch("python_to_exe.converter_logic.subprocess.run") as run:
            file = Path(folder) / "file.tsv"
            file.touch()
            for value in ("", str(Path(folder) / "missing"), str(file)):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    open_output_folder(value)
            run.assert_not_called()

    def test_launch_errors_remain_visible_to_caller(self):
        with tempfile.TemporaryDirectory() as folder:
            for error in (FileNotFoundError("xdg-open unavailable"),
                          subprocess.CalledProcessError(1, ["xdg-open", folder]),
                          subprocess.TimeoutExpired(["xdg-open", folder], 10)):
                with self.subTest(error=error), \
                     patch("python_to_exe.converter_logic.sys.platform", "linux"), \
                     patch("python_to_exe.converter_logic.subprocess.run", side_effect=error), \
                     self.assertRaises(type(error)):
                    open_output_folder(folder)


class ConversionResultTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tas results 日本語 ")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.source = self.work / "input with spaces.tsv"
        self.source.write_text("1\ta", encoding="utf-8")

    def app(self, language="en"):
        # Exercise the real worker/event handler without creating Tk widgets.
        app = TASConverterApp.__new__(TASConverterApp)
        app.language, app.words, app.base_dir = language, TEXT[language], self.work
        app._events, app._last_successful_output = SimpleQueue(), None
        app.convert_btn = SimpleNamespace(config=Mock())
        app.after = Mock(side_effect=AssertionError("worker must not call Tk"))
        app.log = Mock()
        return app

    @staticmethod
    def generate(command, **options):
        primary = Path(command[-1])
        primary.write_bytes(b"")  # Even a valid empty nx-TAS output must be accepted.
        if any("d" in flag[1:] for flag in command[2:-2] if flag.startswith("-")):
            Path(str(primary) + "-debug.csv").write_bytes(b"debug")
        return subprocess.CompletedProcess(command, 0, "generated", "diagnostic")

    def test_verified_success_metadata_updates_last_output_on_main_thread_only(self):
        source = self.work / "nx input 日本語.txt"
        source.write_text("0 KEY_A 0;0 0;0\n", encoding="utf-8")
        for language in ("en", "ja"):
            with self.subTest(language=language):
                app = self.app(language)
                with patch("python_to_exe.converter_gui.subprocess.run", side_effect=self.generate), \
                     patch("python_to_exe.converter_gui.messagebox.showinfo") as success, \
                     patch("python_to_exe.converter_gui.messagebox.showerror") as failure:
                    app.convert((str(source), str(self.work), "result", "stas", False, True, True),
                                ("example.invalid", "5000", "tester", ""))
                    self.assertIsNone(app._last_successful_output)
                    app.after.assert_not_called()
                    app._drain_events()
                outputs = conversion_outputs(source, self.work, "result", "stas", debug=True, ftp=True)
                self.assertEqual(app._last_successful_output, outputs.primary)
                log = "\n".join(call.args[0] for call in app.log.call_args_list)
                for path in (outputs.primary, outputs.debug_csv, outputs.intermediate_tsv):
                    self.assertIn(str(path), log)
                self.assertIn(app.words["result_ftp"], log)
                self.assertIn(str(outputs.primary), success.call_args.args[1])
                self.assertIn(app.words["result_ftp"], success.call_args.args[1])
                self.assertNotIn(str(outputs.debug_csv), success.call_args.args[1])
                failure.assert_not_called()

    def test_optional_outputs_and_ftp_are_not_reported_when_disabled(self):
        app = self.app()
        with patch("python_to_exe.converter_gui.subprocess.run", side_effect=self.generate), \
             patch("python_to_exe.converter_gui.messagebox.showinfo") as success:
            app.convert((str(self.source), str(self.work), "plain", "nxtas", False, False, False), ())
            app._drain_events()
        self.assertEqual(app._last_successful_output, self.work / "plain.txt")
        log = "\n".join(call.args[0] for call in app.log.call_args_list)
        for key in ("result_debug", "result_intermediate", "result_ftp"):
            self.assertNotIn(app.words[key], log)
            self.assertNotIn(app.words[key], success.call_args.args[1])

    def test_every_conversion_stage_uses_utf8_without_changing_parent_environment(self):
        for language in ("en", "ja"):
            for extension in (".tsv", ".txt"):
                for ftp in (False, True):
                    with self.subTest(language=language, extension=extension, ftp=ftp):
                        source = self.work / ("入力 with spaces" + extension)
                        source.write_text("1\ta" if extension == ".tsv"
                                          else "0 KEY_A 0;0 0;0\n", encoding="utf-8")
                        app = self.app(language)
                        with patch.dict(os.environ, {"PYTHONUTF8": "0", "TAS_ENV_TEST": "keep"}):
                            before = dict(os.environ)
                            with patch("python_to_exe.converter_gui.subprocess.run",
                                       side_effect=self.generate) as run:
                                app.convert((str(source), str(self.work), "出力 result", "stas",
                                             False, True, ftp), ("example.invalid", "5000", "", ""))
                            self.assertEqual(dict(os.environ), before)
                            self.assertEqual(run.call_count, 2 if extension == ".txt" else 1)
                            for call in run.call_args_list:
                                options = call.kwargs
                                self.assertTrue(options["text"])
                                self.assertEqual(options.get("encoding"), "utf-8")
                                self.assertEqual(options["errors"], "replace")
                                self.assertEqual(options["env"], {**before, "PYTHONUTF8": "1"})
                                self.assertIsNot(options["env"], os.environ)
                                self.assertFalse(options.get("shell", False))

    def test_real_gui_worker_converts_japanese_tsv_and_txt_under_non_utf8_environment(self):
        for extension in (".tsv", ".txt"):
            source = self.work / ("入力 with spaces" + extension)
            source.write_text("1\ta\t// 日本語コメント\n1\tls(90)\n" if extension == ".tsv"
                              else "0 KEY_A 0;0 0;0\n1 KEY_B 0;0 0;0\n", encoding="utf-8")
            destination = self.work / "出力 directory"
            destination.mkdir(exist_ok=True)
            for output_format, signature in (("binary", b"BOOB"), ("stas", b"STAS"),
                                             ("nxtas", b"0 ")):
                with self.subTest(extension=extension, output_format=output_format):
                    app = self.app()
                    app.base_dir = ROOT
                    name = extension[1:] + " 日本語 output " + output_format
                    with patch.dict(os.environ, {"PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0",
                                                 "LC_ALL": "C", "LANG": "C"}), \
                         patch("python_to_exe.converter_gui.messagebox.showinfo") as success, \
                         patch("python_to_exe.converter_gui.messagebox.showerror") as failure:
                        before = dict(os.environ)
                        app.convert((str(source), str(destination), name, output_format,
                                     output_format == "nxtas", True, False), ())
                        app._drain_events()
                        self.assertEqual(dict(os.environ), before)
                    self.assertFalse(failure.called, failure.call_args)
                    success.assert_called_once()
                    outputs = conversion_outputs(source, destination, name, output_format, debug=True)
                    self.assertTrue(outputs.primary.read_bytes().startswith(signature))
                    self.assertTrue(outputs.debug_csv.read_bytes().startswith(b"Frame,2ndPlayer,"))
                    if extension == ".txt":
                        self.assertIn("a", outputs.intermediate_tsv.read_text(encoding="utf-8"))

    def test_failure_missing_artifacts_and_nonzero_exit_keep_previous_success(self):
        for mode in ("exit", "primary", "debug", "intermediate", "second_stage"):
            with self.subTest(mode=mode):
                app = self.app()
                previous = app._last_successful_output = self.work / "last successful output"
                source = self.source
                if mode in ("intermediate", "second_stage"):
                    source = self.work / "source.txt"
                    source.write_text("0 KEY_A 0;0 0;0\n", encoding="utf-8")
                name = "missing " + mode
                calls = []

                def runner(command, **options):
                    calls.append(command)
                    if mode == "exit" or (mode == "second_stage" and len(calls) == 2):
                        return subprocess.CompletedProcess(command, 1, "stdout", "converter error")
                    if mode not in ("primary", "intermediate"):
                        Path(command[-1]).touch()
                    return subprocess.CompletedProcess(command, 0, "stdout", "stderr")

                with patch("python_to_exe.converter_gui.subprocess.run", side_effect=runner), \
                     patch("python_to_exe.converter_gui.messagebox.showinfo") as success, \
                     patch("python_to_exe.converter_gui.messagebox.showerror") as failure:
                    app.convert((str(source), str(self.work), name, "binary", False, mode == "debug", False), ())
                    app._drain_events()
                success.assert_not_called()
                failure.assert_called_once()
                self.assertEqual(app._last_successful_output, previous)
                self.assertFalse(app._conversion_running)
                if mode == "intermediate":
                    self.assertEqual(len(calls), 1)  # Do not compile a missing intermediate TSV.
                if mode in ("primary", "debug", "intermediate"):
                    self.assertIn("was not generated", failure.call_args.args[1])
                self.assertIn("stdout", "\n".join(call.args[0] for call in app.log.call_args_list))

    def test_gui_folder_errors_do_not_crash_or_change_last_output(self):
        app = self.app("ja")
        app.output_entry = SimpleNamespace(get=lambda: str(self.work))
        previous = app._last_successful_output = self.work / "last output"
        for error in (OSError("launcher failed"), ValueError("Output directory does not exist"),
                      subprocess.CalledProcessError(1, ["xdg-open", str(self.work)])):
            with self.subTest(error=error), \
                 patch("python_to_exe.converter_gui.open_output_folder", side_effect=error), \
                 patch("python_to_exe.converter_gui.messagebox.showerror") as failure:
                app.open_output_folder()
                failure.assert_called_once()
                self.assertEqual(app._last_successful_output, previous)


class OutputWorkflowTkTests(unittest.TestCase):
    def test_parent_conversion_logs_paths_and_output_folder_action(self):
        with tempfile.TemporaryDirectory(prefix="tas Tk outputs 日本語 ") as folder:
            work = Path(folder)
            try:
                app = TASConverterApp("ja", settings=AppSettings(work / "settings.json"))
            except tk.TclError as error:
                self.skipTest(f"graphical Tk display unavailable: {error}")
            self.addCleanup(app.destroy)
            source = work / "nx input 日本語.txt"
            source.write_text("0 KEY_A 0;0 0;0\n1 KEY_B 0;0 0;0\n", encoding="utf-8")
            app._set_input_path(source)
            app.format_var.set("stas")
            app.debug_var.set(True)
            with patch("python_to_exe.converter_gui.messagebox.showinfo") as success, \
                 patch("python_to_exe.converter_gui.messagebox.showerror") as failure:
                app.convert_btn.invoke()
                deadline = time.monotonic() + 8
                while app._busy() and time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.01)
                self.assertFalse(app._busy())
                success.assert_called_once()
                failure.assert_not_called()
                outputs = conversion_outputs(source, work, source.stem, "stas", debug=True)
                self.assertEqual(app._last_successful_output, outputs.primary)
                log = app.log_text.get("1.0", "end")
                for path in (outputs.primary, outputs.debug_csv, outputs.intermediate_tsv):
                    self.assertIn(str(path), log)
                self.assertIn(str(outputs.primary), success.call_args.args[1])
                self.assertNotIn(app.words["result_ftp"], log)
            output_buttons = [child for frame in app.winfo_children() for child in frame.winfo_children()
                              if isinstance(child, tk.Button) and child.cget("text") == app.words["open_output"]]
            self.assertEqual(len(output_buttons), 1)
            with patch("python_to_exe.converter_gui.open_output_folder") as opener:
                output_buttons[0].invoke()
                opener.assert_called_once_with(str(work))
            app.output_entry.delete(0, "end")
            with patch("python_to_exe.converter_gui.messagebox.showerror") as failure:
                output_buttons[0].invoke()
                failure.assert_called_once_with(app.words["error_title"], "出力ディレクトリを指定してください。")
