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

from converter_logic import build_commands, python_command, save_ftp_config, scripts_dir


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

    def test_debug_output(self):
        self.run_command(self.build("binary", debug=True)[0])
        debug_path = self.work / "output with spaces-debug.csv"
        self.assertTrue(debug_path.is_file())
        self.assertIn("Frame,2ndPlayer", debug_path.read_text())

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
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "script with spaces.tsv"
                source.write_text("1\ta\n")
                for format_name in ("binary", "stas", "nxtas"):
                    captured = []
                    for app in (en_app, ja_app):
                        app.after = lambda delay, callback, *args, **kwargs: callback(*args, **kwargs)
                        app.log = lambda message: None
                        values = (str(source), directory, "out with spaces", format_name,
                                  format_name == "nxtas", True, False)
                        with patch("converter_gui.subprocess.run") as run:
                            run.return_value = types.SimpleNamespace(returncode=0, stdout="", stderr="")
                            app.convert(values, ("", "", "", ""))
                            captured.append(run.call_args.args[0])
                    self.assertEqual(captured[0], captured[1])
        for name in ("converter_gui", "main_en", "main_jp"):
            sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()
