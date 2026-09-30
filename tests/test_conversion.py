import importlib
import contextlib
import io
import json
import os
import runpy
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python_to_exe"))

from converter_logic import build_commands, load_ftp_config, python_command, save_ftp_config, scripts_dir


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tas gui test ")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.input = self.work / "input with spaces.tsv"
        self.input.write_text("1\ta\n1\tb\n", encoding="utf-8")

    def run_command(self, command):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def build(self, format_name, **options):
        return build_commands(self.input, self.work, "output with spaces", format_name,
                              base_dir=ROOT, interpreter=[sys.executable], **options)

    def test_binary_output_and_source_python(self):
        self.assertEqual(python_command(), [sys.executable])
        self.assertEqual(scripts_dir(), ROOT)
        command = self.build("binary")[0]
        self.assertNotIn("-", command[2:3])
        self.run_command(command)
        self.assertEqual((self.work / "output with spaces").read_bytes()[:4], b"BOOB")

    def test_stas_commands_do_not_add_logical_frames(self):
        self.input.write_text("1\ta\n/absStick on\n/speed 2\n/pause\n/loadFile 1\n"
                              "/reloadFile\n/demo on\n1\tb\n", encoding="utf-8")
        self.run_command(self.build("stas")[0])
        data = (self.work / "output with spaces.stas").read_bytes()
        self.assertEqual(data[:4], b"STAS")
        self.assertEqual(struct.unpack_from("<I", data, 24)[0], 1)

    def test_nxtas_and_reverse_conversion(self):
        self.run_command(self.build("nxtas", skip_empty=True)[0])
        nx_path = self.work / "output with spaces.txt"
        self.assertIn("KEY_A", nx_path.read_text())
        commands = build_commands(nx_path, self.work, "round trip", "binary",
                                  base_dir=ROOT, interpreter=[sys.executable])
        self.assertEqual(len(commands), 2)
        self.run_command(commands[0])
        self.assertIn("a", (self.work / "round trip.tsv").read_text())
        self.run_command(commands[1])
        self.assertEqual((self.work / "round trip").read_bytes()[:4], b"BOOB")

    def test_txt_input_converts_to_each_output_format(self):
        source = self.work / "nx input with spaces.txt"
        source.write_text("0 KEY_A 0;0 0;0\n1 KEY_B 0;0 0;0\n")
        for format_name, suffix, signature in (("binary", "", b"BOOB"),
                                               ("stas", ".stas", b"STAS"),
                                               ("nxtas", ".txt", b"0 ")):
            base_name = "from nx " + format_name
            commands = build_commands(source, self.work, base_name, format_name,
                                      base_dir=ROOT, interpreter=[sys.executable])
            self.assertEqual(len(commands), 2)
            for command in commands:
                self.run_command(command)
            self.assertTrue((self.work / (base_name + ".tsv")).is_file())
            self.assertTrue((self.work / (base_name + suffix)).read_bytes().startswith(signature))

    def test_debug_output(self):
        self.run_command(self.build("binary", debug=True)[0])
        debug_path = self.work / "output with spaces-debug.csv"
        self.assertTrue(debug_path.is_file())
        contents = debug_path.read_bytes()
        self.assertIn(b"Frame,2ndPlayer", contents)
        self.assertNotIn(b"\r\r\n", contents)

    def test_ftp_command_combinations_and_config_types(self):
        for format_name, expected in (("binary", "-f"), ("stas", "-fs"),
                                      ("nxtas", "-fne")):
            command = self.build(format_name, ftp=True,
                                 skip_empty=format_name == "nxtas")[0]
            self.assertEqual(command[2], expected)
        save_ftp_config(self.work, "example.invalid", "5000", "tester", "")
        config = json.loads((self.work / "ftp_config.json").read_text())
        self.assertEqual(set(config), {"ip", "port", "user", "passwd"})
        self.assertIsInstance(config["port"], int)

    def test_malformed_ftp_config_does_not_break_startup(self):
        (self.work / "ftp_config.json").write_text("[]")
        self.assertEqual(load_ftp_config(self.work), {})

    def test_ftp_upload_uses_output_basename(self):
        save_ftp_config(self.work, "example.invalid", "5000", "tester", "")
        output = self.work / "output with spaces.stas"
        argv = [str(ROOT / "tsv-tas.py"), "-fs", str(self.input), str(output)]
        original_cwd = Path.cwd()
        try:
            os.chdir(self.work)
            with patch.object(sys, "argv", argv), patch("ftplib.FTP") as ftp, \
                 contextlib.redirect_stdout(io.StringIO()):
                ftp.return_value.storbinary.return_value = "226 OK"
                runpy.run_path(str(ROOT / "tsv-tas.py"), run_name="__main__")
                remote_path = ftp.return_value.storbinary.call_args.args[0]
                self.assertEqual(remote_path, "STOR SMO/tas/scripts/output with spaces.stas")
        finally:
            os.chdir(original_cwd)

    def test_invalid_skip_and_output_collision(self):
        with self.assertRaises(ValueError):
            self.build("binary", skip_empty=True)
        nx_path = self.work / "same.txt"
        nx_path.write_text("0 KEY_A 0;0 0;0\n")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            build_commands(nx_path, self.work, "same", "nxtas", base_dir=ROOT,
                           interpreter=[sys.executable])

    def test_frozen_python_is_not_gui_executable(self):
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", str(self.work / "gui.exe")), \
             patch("converter_logic.shutil.which", side_effect=lambda name: "/usr/bin/python3" if name == "python" else None):
            self.assertEqual(python_command(), ["/usr/bin/python3"])


class FakeWidget:
    def __init__(self, *args, **kwargs):
        self.value = ""
        self.state = kwargs.get("state")

    def grid(self, **kwargs):
        return self

    def pack(self, **kwargs):
        return self

    def grid_remove(self):
        pass

    def config(self, **kwargs):
        self.state = kwargs.get("state", self.state)

    def insert(self, index, value):
        self.value = value

    def delete(self, start, end):
        self.value = ""

    def get(self):
        return self.value

    def title(self, title):
        self.window_title = title

    def resizable(self, *args):
        pass


class FakeVar:
    def __init__(self, value=False):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class GuiStartupTests(unittest.TestCase):
    def test_both_launchers_share_behavior_and_start(self):
        fake_tk = types.ModuleType("tkinter")
        fake_tk.Tk = fake_tk.Label = fake_tk.Entry = fake_tk.Button = FakeWidget
        fake_tk.Frame = fake_tk.Radiobutton = fake_tk.Checkbutton = fake_tk.Text = FakeWidget
        fake_tk.BooleanVar = fake_tk.StringVar = FakeVar
        fake_tk.END = "end"
        fake_tk.filedialog = types.SimpleNamespace()
        fake_tk.messagebox = types.SimpleNamespace(showinfo=lambda *args: None,
                                                    showerror=lambda *args: None)
        with patch.dict(sys.modules, {"tkinter": fake_tk}):
            for name in ("converter_gui", "main_en", "main_jp"):
                sys.modules.pop(name, None)
            english = importlib.import_module("main_en")
            japanese = importlib.import_module("main_jp")
            self.assertIs(english.TASConverterApp, japanese.TASConverterApp)
            en_app = english.TASConverterApp("en")
            ja_app = japanese.TASConverterApp("ja")
            self.assertEqual(en_app.format_var.get(), ja_app.format_var.get())
            self.assertEqual(en_app.skip_check.state, "disabled")
            en_app.format_var.set("nxtas")
            en_app.toggle_skip()
            self.assertEqual(en_app.skip_check.state, "normal")
            self.assertNotEqual(en_app.window_title, ja_app.window_title)
            opened = []
            fake_editor = types.ModuleType("editor.window")
            fake_editor.EditorWindow = lambda master, **kwargs: opened.append((master, kwargs))
            with patch.dict(sys.modules, {"editor.window": fake_editor}):
                en_app.open_editor()
                ja_app.open_editor()
            self.assertEqual([item[1]["language"] for item in opened], ["en", "ja"])
            self.assertTrue(all(item[1]["initial_path"] is None for item in opened))
            self.assertTrue(all(callable(item[1]["on_convert"]) for item in opened))
            self.assertTrue(all(item[1]["can_convert"]() for item in opened))
            sample = Path("example with spaces") / "sample.tsv"
            another = sample.with_name("another.txt")
            next_input = Path("next input") / "test.tsv"
            for app, options in opened:
                options["on_saved"](sample)
                self.assertEqual(app.input_entry.get(), str(sample))
                self.assertEqual(app.outname_entry.get(), "sample")
                self.assertEqual(app.output_entry.get(), os.path.dirname(os.path.abspath(sample)))
                app.output_entry.delete(0, fake_tk.END)
                app.output_entry.insert(0, "chosen output")
                options["on_saved"](another)
                self.assertEqual(app.output_entry.get(), "chosen output")
                self.assertEqual(app.outname_entry.get(), "sample")
                app.output_entry.delete(0, fake_tk.END)
                fake_tk.filedialog.askopenfilename = lambda **kwargs: str(next_input)
                app.browse_input()
                self.assertEqual(app.output_entry.get(), os.path.dirname(os.path.abspath(next_input)))
            en_app.output_entry.delete(0, fake_tk.END)
            en_app.output_entry.insert(0, "chosen output")
            en_app.outname_entry.delete(0, fake_tk.END)
            en_app.outname_entry.insert(0, "chosen name")
            with patch.dict(sys.modules, {"editor.window": fake_editor}):
                en_app.open_editor()
            second_editor = opened[-1][1]
            second_editor["on_saved"](another)
            with patch.object(en_app, "start_conversion", return_value=True) as start:
                self.assertTrue(opened[0][1]["on_convert"](sample))
                start.assert_called_once_with(ftp_override=False)
            self.assertEqual(en_app.input_entry.get(), str(sample))
            self.assertEqual(en_app.output_entry.get(), "chosen output")
            self.assertEqual(en_app.outname_entry.get(), "chosen name")
            en_app._conversion_running = True
            with patch.object(en_app, "start_conversion") as start:
                self.assertFalse(opened[0][1]["on_convert"](another))
                start.assert_not_called()
            self.assertEqual(en_app.input_entry.get(), str(sample))
            en_app._conversion_running = False
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "script with spaces.tsv"
                source.write_text("1\ta\n")
                for format_name in ("binary", "stas", "nxtas"):
                    captured = []
                    for app in (en_app, ja_app):
                        app.after = lambda *args, **kwargs: self.fail("worker called Tk")
                        messages = []
                        app.log = messages.append
                        values = (str(source), directory, "out with spaces", format_name,
                                  format_name == "nxtas", True, False)
                        with patch("converter_gui.subprocess.run") as run:
                            run.return_value = types.SimpleNamespace(returncode=0, stdout="", stderr="")
                            app.convert(values, ("", "", "", ""))
                            captured.append(run.call_args.args[0])
                        app.after = lambda delay, callback, *args, **kwargs: callback(*args, **kwargs)
                        app._drain_events()
                        self.assertEqual(app.convert_btn.state, "normal")
                        self.assertEqual(len(messages), 1)
                    self.assertEqual(captured[0], captured[1])
                with patch("converter_gui.subprocess.run") as run, \
                     patch.object(fake_tk.messagebox, "showerror") as showerror:
                    run.return_value = types.SimpleNamespace(returncode=1, stdout="", stderr="failed")
                    en_app.convert((str(source), directory, "out with spaces", "binary",
                                    False, False, False), ("", "", "", ""))
                    en_app._drain_events()
                    showerror.assert_called_once()
                    self.assertEqual(en_app.convert_btn.state, "normal")
        for name in ("converter_gui", "main_en", "main_jp"):
            sys.modules.pop(name, None)


class EditorConverterFlowTests(unittest.TestCase):
    def setUp(self):
        fake_tk = types.ModuleType("tkinter")
        fake_tk.Tk = fake_tk.Label = fake_tk.Entry = fake_tk.Button = FakeWidget
        fake_tk.Frame = fake_tk.Radiobutton = fake_tk.Checkbutton = fake_tk.Text = FakeWidget
        fake_tk.BooleanVar = fake_tk.StringVar = FakeVar
        fake_tk.END = "end"
        fake_tk.filedialog = types.SimpleNamespace()
        fake_tk.messagebox = types.SimpleNamespace(showinfo=lambda *args: None,
                                                    showerror=lambda *args: None)
        module_patch = patch.dict(sys.modules, {"tkinter": fake_tk})
        module_patch.start()
        self.addCleanup(module_patch.stop)
        sys.modules.pop("converter_gui", None)
        self.addCleanup(sys.modules.pop, "converter_gui", None)
        self.gui = importlib.import_module("converter_gui")

    def app(self, language):
        app = self.gui.TASConverterApp(language)
        app.after = lambda delay, callback: None
        app.log = lambda message: None
        return app

    def test_editor_ftp_override_preserves_options_fields_and_checkbox(self):
        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with tempfile.TemporaryDirectory(prefix="tas actions 日本語 ") as directory:
            work = Path(directory)
            source = work / "input with spaces.tsv"
            source.write_text("1\ta", encoding="utf-8")
            by_language = {}
            for language in ("en", "ja"):
                app = self.app(language)
                app.base_dir = work
                app.output_entry.insert(0, str(work))
                app.outname_entry.insert(0, "chosen output")
                ftp_fields = ("example.invalid", "5000", "tester", "test password")
                for entry, value in zip((app.ip_entry, app.port_entry, app.user_entry,
                                         app.pass_entry), ftp_fields):
                    entry.delete(0, "end")
                    entry.insert(0, value)
                captured = by_language[language] = []
                for checked in (False, True):
                    for send in (False, True):
                        for output_format in ("binary", "stas", "nxtas"):
                            for debug in (False, True):
                                app.ftp_var.set(checked)
                                app.format_var.set(output_format)
                                app.skip_var.set(True)
                                app.debug_var.set(debug)
                                config = work / "ftp_config.json"
                                config.write_text("{}", encoding="utf-8")
                                logs = []
                                app.log = logs.append
                                with patch.object(self.gui.threading, "Thread", ImmediateThread), \
                                     patch.object(self.gui.subprocess, "run") as run, \
                                     patch.object(self.gui, "save_ftp_config", wraps=self.gui.save_ftp_config) as save:
                                    run.return_value = types.SimpleNamespace(returncode=0, stdout="", stderr="")
                                    self.assertTrue(app._convert_editor_file(source, send_ftp=send))
                                    command = run.call_args.args[0]
                                    captured.append(command)
                                    flags = command[2][1:] if command[2].startswith("-") else ""
                                    self.assertEqual("f" in flags, send)
                                    self.assertEqual("d" in flags, debug)
                                    self.assertEqual("e" in flags, output_format == "nxtas")
                                    self.assertEqual("n" in flags, output_format == "nxtas")
                                    self.assertEqual("s" in flags, output_format == "stas")
                                    self.assertEqual(Path(command[-2]), source)
                                    suffix = {"binary": "", "stas": ".stas", "nxtas": ".txt"}[output_format]
                                    self.assertEqual(Path(command[-1]), work / ("chosen output" + suffix))
                                    if send:
                                        save.assert_called_once_with(work, *ftp_fields)
                                        self.assertEqual(json.loads(config.read_text(encoding="utf-8")),
                                                         dict(ip=ftp_fields[0], port=5000,
                                                              user=ftp_fields[2], passwd=ftp_fields[3]))
                                    else:
                                        save.assert_not_called()
                                        self.assertEqual(config.read_text(encoding="utf-8"), "{}")
                                self.assertEqual(app.ftp_var.get(), checked)
                                self.assertEqual(app.debug_var.get(), debug)
                                self.assertTrue(app.skip_var.get())
                                self.assertEqual(app.format_var.get(), output_format)
                                self.assertEqual(app.output_entry.get(), str(work))
                                self.assertEqual(app.outname_entry.get(), "chosen output")
                                app._drain_events()
                                self.assertEqual(logs[0].splitlines()[0],
                                                 app.words["editor_send" if send else "editor_local"])
            self.assertEqual(by_language["en"], by_language["ja"])

    def test_start_conversion_retains_checkbox_semantics(self):
        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "script.tsv"
            source.write_text("1\ta", encoding="utf-8")
            app = self.app("en")
            app.base_dir = work
            app._editor_saved(source)
            app.port_entry.delete(0, "end")
            app.port_entry.insert(0, "5000")
            for checked in (False, True):
                app.ftp_var.set(checked)
                with patch.object(self.gui.threading, "Thread", ImmediateThread), \
                     patch.object(self.gui.subprocess, "run") as run:
                    run.return_value = types.SimpleNamespace(returncode=0, stdout="", stderr="")
                    self.assertTrue(app.start_conversion())
                    command = run.call_args.args[0]
                    self.assertEqual("-f" in command, checked)
                app._drain_events()
                self.assertEqual(app.ftp_var.get(), checked)

    def test_invalid_ftp_port_stops_before_subprocess_and_preserves_existing_output(self):
        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "script.tsv"
            source.write_text("1\ta", encoding="utf-8")
            output = work / "chosen.stas"
            output.write_bytes(b"existing output")
            config = work / "ftp_config.json"
            config.write_bytes(b"{}")
            app = self.app("en")
            app.base_dir = work
            app.format_var.set("stas")
            app.outname_entry.insert(0, "chosen")
            app.port_entry.delete(0, "end")
            app.port_entry.insert(0, "invalid")
            logs = []
            app.log = logs.append
            with patch.object(self.gui.threading, "Thread", ImmediateThread), \
                 patch.object(self.gui.subprocess, "run") as run, \
                 patch.object(self.gui.messagebox, "showerror") as error:
                self.assertTrue(app._convert_editor_file(source, send_ftp=True))
                app._drain_events()
                run.assert_not_called()
                error.assert_called_once_with(app.words["error_title"], "FTP port must be an integer")
            self.assertIn(app.words["preflight_failed"], "\n".join(logs))
            self.assertEqual(output.read_bytes(), b"existing output")
            self.assertEqual(config.read_bytes(), b"{}")
            self.assertFalse(app._busy())

    def test_editor_local_send_and_checks_share_busy_guard(self):
        starts = []

        class PendingThread:
            def __init__(self, target, args, daemon):
                starts.append((target, args))

            def start(self):
                pass

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "script.tsv"
            other = Path(directory) / "other.tsv"
            source.write_text("1\ta", encoding="utf-8")
            for send in (False, True):
                app = self.app("en")
                before = len(starts)
                with patch.object(self.gui.threading, "Thread", PendingThread):
                    self.assertTrue(app._convert_editor_file(source, send_ftp=send))
                    for next_send in (False, True):
                        self.assertFalse(app._convert_editor_file(other, send_ftp=next_send))
                    self.assertFalse(app.start_conversion())
                    self.assertFalse(app._validate_editor_snapshot(None, None))
                    self.assertFalse(app._analyze_editor_snapshot(None, None))
                self.assertEqual(len(starts), before + 1)
                self.assertEqual(starts[-1][1][0][6], send)
                self.assertEqual(app.input_entry.get(), str(source))
                app._events.put(("done", None))
                app._drain_events()
                for flag in ("_validation_running", "_analysis_running"):
                    setattr(app, flag, True)
                    with patch.object(self.gui.threading, "Thread", PendingThread):
                        self.assertFalse(app._convert_editor_file(other, send_ftp=False))
                        self.assertFalse(app._convert_editor_file(other, send_ftp=True))
                    setattr(app, flag, False)
                self.assertEqual(len(starts), before + 1)

    def test_txt_editor_conversion_uses_existing_pipeline_in_both_languages(self):
        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with tempfile.TemporaryDirectory(prefix="tas 日本語 path with spaces ") as directory:
            work = Path(directory)
            source = work / "nx 日本語 input.txt"
            source.write_text("0 KEY_A 0;0 0;0\n1 KEY_B 0;0 0;0\n", encoding="utf-8")
            commands_by_language = {}
            for language in ("en", "ja"):
                app = self.app(language)
                captured = []
                commands_by_language[language] = captured
                real_run = subprocess.run

                def record_and_run(command, **kwargs):
                    captured.append(command)
                    return real_run(command, **kwargs)

                for format_name, name, suffix, signature in (
                    ("binary", source.stem, "", b"BOOB"),
                    ("stas", "converted stas 日本語", ".stas", b"STAS"),
                    ("nxtas", "converted nx 日本語", ".txt", b"0 "),
                ):
                    app.format_var.set(format_name)
                    app.skip_var.set(format_name == "nxtas")
                    app.debug_var.set(format_name == "stas")
                    app.outname_entry.delete(0, "end")
                    if format_name != "binary":
                        app.outname_entry.insert(0, name)
                    with patch.object(self.gui.threading, "Thread", ImmediateThread), \
                         patch.object(self.gui.subprocess, "run", side_effect=record_and_run):
                        self.assertTrue(app._convert_editor_file(source))
                    self.assertEqual(app.input_entry.get(), str(source))
                    self.assertEqual(app.output_entry.get(), str(work))
                    self.assertEqual(app.outname_entry.get(), name)
                    self.assertTrue(app._conversion_running)
                    app._drain_events()
                    self.assertFalse(app._conversion_running)
                    self.assertTrue((work / (name + suffix)).read_bytes().startswith(signature))
                self.assertEqual(len(captured), 6)
                self.assertTrue(all(command[1].endswith("nx-tas-to-tsv-tas.py")
                                    for command in captured[::2]))
                self.assertTrue(all(command[1].endswith("tsv-tas.py")
                                    for command in captured[1::2]))
                self.assertIn("-sd", captured[3])
                self.assertIn("-ne", captured[5])
                self.assertTrue((work / "converted stas 日本語.stas-debug.csv").is_file())
            self.assertEqual(commands_by_language["en"], commands_by_language["ja"])

    def test_ftp_debug_skip_and_double_start_guard(self):
        with tempfile.TemporaryDirectory(prefix="tas 日本語 path with spaces ") as directory:
            work = Path(directory)
            source = work / "input 日本語.tsv"
            source.write_text("1\ta\n", encoding="utf-8")
            commands = []
            for language in ("en", "ja"):
                app = self.app(language)
                logs = []
                app.log = logs.append
                app.base_dir = work
                app.format_var.set("nxtas")
                app.skip_var.set(True)
                app.debug_var.set(True)
                app.ftp_var.set(True)
                for entry, value in ((app.ip_entry, "example.invalid"),
                                     (app.port_entry, "5000"), (app.user_entry, "tester")):
                    entry.insert(0, value)

                class ImmediateThread:
                    def __init__(self, target, args, daemon):
                        self.target, self.args = target, args

                    def start(self):
                        self.target(*self.args)

                with patch.object(self.gui.threading, "Thread", ImmediateThread), \
                     patch.object(self.gui.subprocess, "run") as run:
                    run.return_value = types.SimpleNamespace(returncode=0, stdout="done", stderr="diagnostic")
                    self.assertTrue(app._convert_editor_file(source, send_ftp=True))
                    commands.append(run.call_args.args[0])
                self.assertIn("-fned", commands[-1])
                self.assertEqual(json.loads((work / "ftp_config.json").read_text())["port"], 5000)
                app._drain_events()
                self.assertIn("done", "\n".join(logs))
                self.assertIn("diagnostic", "\n".join(logs))

                starts = []

                class PendingThread:
                    def __init__(self, target, args, daemon):
                        starts.append((target, args))

                    def start(self):
                        pass

                with patch.object(self.gui.threading, "Thread", PendingThread):
                    self.assertTrue(app._convert_editor_file(source))
                    self.assertFalse(app._convert_editor_file(source))
                    self.assertFalse(app.start_conversion())
                self.assertEqual(len(starts), 1)
                self.assertEqual(app.convert_btn.state, "disabled")
                app._events.put(("done", None))
                app._drain_events()
                self.assertFalse(app._conversion_running)
                self.assertEqual(app.convert_btn.state, "normal")
            self.assertEqual(commands[0], commands[1])


if __name__ == "__main__":
    unittest.main()
