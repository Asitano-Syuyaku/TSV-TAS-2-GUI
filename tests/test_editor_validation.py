"""Converter-backed validation and conservative source-line extraction."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from python_to_exe.editor.tsv_syntax import classify_row
from python_to_exe.editor.validation import (ValidationResult, parse_problems,
                                              validate_script)


ROOT = Path(__file__).resolve().parents[1]


class EditorValidationTests(unittest.TestCase):
    def test_visual_row_roles_are_hints_only(self):
        rows = {"\t": "blank", "1\ta": "input", "// note\tignored": "comment",
                "/pause": "command", "$angle = 90": "variable",
                "6\ta/b": "control", "6\tls(0)->ls(90)": "control",
                "6\ta|b": "control"}
        self.assertEqual({line: classify_row(line) for line in rows}, rows)

    def test_line_numbers_only_from_current_explicit_converter_forms(self):
        message = ("Syntax error(s) on line 2 prevented script generation\n"
                   "Error: Loop on line 3 has a problem\n"
                   "Error: bad duration (line 4)\n"
                   "  File \"tsv-tas.py\", line 17, in parse\n"
                   "Unrelated note on line 1\n"
                   "Error: Invalid scenario number\n"
                   "Syntax error(s) on line 999\n")
        problems = parse_problems(message, 4)
        self.assertEqual([problem.line for problem in problems],
                         [2, 3, 4, None, None, None, None])
        self.assertEqual("\n".join(item.text for item in problems) + "\n", message)
        self.assertEqual(parse_problems("Error: unknown", 4)[0].line, None)
        self.assertEqual(parse_problems("Error: Bad on line 2", None)[0].line, None)

    def test_success_and_failure_use_real_converter_without_user_output(self):
        with tempfile.TemporaryDirectory(prefix="tas validation 日本語 ") as folder:
            source = Path(folder) / "script with spaces.tsv"
            sentinel = Path(folder) / "user output.stas"
            sentinel.write_bytes(b"keep")
            source.write_text("1\ta\n", encoding="utf-8")
            for output_format in ("binary", "stas", "nxtas"):
                result = validate_script(source, output_format, base_dir=ROOT)
                self.assertTrue(result.success, result.text)
                self.assertEqual(sentinel.read_bytes(), b"keep")
                self.assertEqual(sorted(path.name for path in Path(folder).iterdir()),
                                 ["script with spaces.tsv", "user output.stas"])
            source.write_text("1\ta\n1\tls(\n", encoding="utf-8")
            result = validate_script(source, "binary", base_dir=ROOT)
            self.assertFalse(result.success)
            self.assertIn("Syntax error(s) on line 2", result.stderr)
            self.assertEqual(result.problems(2)[0].line, 2)
            self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_txt_pipeline_and_flags_never_enable_ftp_or_debug(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "nx 日本語.txt"
            source.write_text("0 KEY_A 0;0 0;0\n", encoding="utf-8")
            for output_format in ("binary", "stas", "nxtas"):
                actual = validate_script(source, output_format, base_dir=ROOT)
                self.assertTrue(actual.success, actual.text)
            self.assertEqual([path.name for path in Path(folder).iterdir()], [source.name])
            commands = []

            def runner(command, **kwargs):
                commands.append(command)
                return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

            result = validate_script(source, "nxtas", skip_empty=True, base_dir=ROOT,
                                     runner=runner)
            self.assertTrue(result.success)
            self.assertEqual(len(commands), 2)
            self.assertEqual(Path(commands[0][1]).name, "nx-tas-to-tsv-tas.py")
            self.assertEqual(Path(commands[1][1]).name, "tsv-tas.py")
            self.assertEqual(commands[1][2], "-ne")
            self.assertNotIn("f", commands[1][2])
            self.assertNotIn("d", commands[1][2])
            self.assertEqual(result.problems(1)[0].line, None)

    def test_error_text_is_preserved_and_failure_stops_pipeline(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bad.tsv"
            source.write_text("1\ta", encoding="utf-8")
            calls = []

            def runner(command, **kwargs):
                calls.append(command)
                return SimpleNamespace(returncode=1, stdout="diagnostic stdout\n",
                                       stderr="Error: Loop on line 1\n")

            result = validate_script(source, "binary", base_dir=ROOT, runner=runner)
            self.assertFalse(result.success)
            self.assertEqual(result.stdout, "diagnostic stdout\n")
            self.assertEqual(result.stderr, "Error: Loop on line 1\n")
            self.assertEqual(result.problems(1)[0].line, 1)
            self.assertEqual(len(calls), 1)
            self.assertEqual(ValidationResult(False, "a", "b").text, "b\na")
