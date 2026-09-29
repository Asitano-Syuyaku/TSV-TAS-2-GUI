"""Resolved Debug CSV data and temporary converter analysis."""

import csv
import io
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from python_to_exe.editor.debug_csv import SUMMARY_FIELDS, parse_debug_csv
from python_to_exe.editor.frame_inspector import MAIN_COLUMNS
from python_to_exe.editor.validation import analyze_script


ROOT = Path(__file__).resolve().parents[1]


def make_csv(rows, extra=("la.x", "new.motion.field")):
    headers = SUMMARY_FIELDS + extra
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    for frame, second in rows:
        values = {name: "0" for name in headers}
        values.update(Frame=str(frame), **{"2ndPlayer": str(second), "Command": "[]",
                                          "new.motion.field": "future-value"})
        writer.writerow([values[name] for name in headers])
    stream.seek(0)
    return stream


class DebugCsvTests(unittest.TestCase):
    def test_header_rows_total_2p_lookup_and_unknown_details(self):
        self.assertEqual(tuple(field for _, field, _ in MAIN_COLUMNS), SUMMARY_FIELDS)
        frames = parse_debug_csv(make_csv([(0, False), (0, True), (3, False), (3, True)]))
        self.assertEqual(len(frames.rows), 4)
        self.assertEqual(frames.total_frames, 4)  # max(Frame)+1, not CSV row count.
        self.assertEqual(frames.row_for_frame(0), 0)
        self.assertEqual(frames.row_for_frame(3), 2)
        self.assertIsNone(frames.row_for_frame(1))
        self.assertEqual(frames.summary(1)[1], "2P")
        self.assertEqual(frames.detail(1)["new.motion.field"], "future-value")

    def test_empty_header_only_and_malformed_csv(self):
        frames = parse_debug_csv(make_csv([]))
        self.assertEqual((len(frames.rows), frames.total_frames, frames.row_for_frame(0)),
                         (0, 0, None))
        with self.assertRaisesRegex(ValueError, "missing header"):
            parse_debug_csv(io.StringIO(""))
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            parse_debug_csv(io.StringIO("Frame,2ndPlayer\n0,False\n"))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_debug_csv(io.StringIO(",".join(SUMMARY_FIELDS + ("Frame",)) + "\n"))
        headers = ",".join(SUMMARY_FIELDS)
        with self.assertRaisesRegex(ValueError, "fields"):
            parse_debug_csv(io.StringIO(headers + "\n0,False\n"))
        for frame, second, error in (("x", "False", "invalid Frame"),
                                     ("-1", "False", "negative Frame"),
                                     ("0", "maybe", "invalid 2ndPlayer")):
            values = ["0"] * len(SUMMARY_FIELDS)
            values[0], values[1] = frame, second
            with self.assertRaisesRegex(ValueError, error):
                parse_debug_csv(io.StringIO(headers + "\n" + ",".join(values) + "\n"))
        with self.assertRaises(csv.Error):
            parse_debug_csv(io.StringIO(headers + "\n\"unterminated\n"))

    def test_ten_thousand_rows_parse_and_lookup(self):
        source = make_csv(((frame, False) for frame in range(10000)),
                          extra=tuple(f"motion.{index}" for index in range(32)))
        started = time.perf_counter()
        frames = parse_debug_csv(source)
        self.assertEqual((len(frames.rows), frames.total_frames), (10000, 10000))
        self.assertEqual(len(frames.headers), 44)
        self.assertEqual(frames.row_for_frame(9999), 9999)
        self.assertLess(time.perf_counter() - started, 5)

    def test_analyze_success_real_converter_and_temp_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="tas analyze 日本語 ") as folder:
            source = Path(folder) / "script with spaces.tsv"
            source.write_text("$is_two_player = true\n2\ta\tca\n", encoding="utf-8")
            for output_format in ("binary", "stas", "nxtas"):
                result = analyze_script(source, output_format, base_dir=ROOT)
                self.assertTrue(result.success, result.report.text)
                self.assertEqual(result.frames.total_frames, 2)
                self.assertEqual(len(result.frames.rows), 4)
                self.assertEqual(result.frames.row_for_frame(1), 2)
                self.assertIn("lg.r.xx", result.frames.headers)
                self.assertEqual([path.name for path in Path(folder).iterdir()], [source.name])

    def test_converter_failure_and_missing_csv_do_not_return_old_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bad.tsv"
            source.write_text("1\tls(\n", encoding="utf-8")
            failed = analyze_script(source, "binary", base_dir=ROOT)
            self.assertFalse(failed.success)
            self.assertIsNone(failed.frames)
            self.assertIn("Syntax error(s) on line 1", failed.report.stderr)
            self.assertEqual([path.name for path in Path(folder).iterdir()], [source.name])

            source.write_text("1\ta\n", encoding="utf-8")
            commands = []

            def no_csv(command, **kwargs):
                commands.append(command)
                return SimpleNamespace(returncode=0, stdout="success\n", stderr="")

            missing = analyze_script(source, "stas", base_dir=ROOT, runner=no_csv)
            self.assertFalse(missing.success)
            self.assertIsNone(missing.frames)
            self.assertIn("Debug CSV was not generated", missing.report.stderr)
            self.assertEqual(commands[0][2], "-sd")
            self.assertNotIn("f", commands[0][2])
            self.assertEqual([path.name for path in Path(folder).iterdir()], [source.name])
            self.assertFalse(Path(commands[0][-1]).parent.exists())

            def bad_csv(command, **kwargs):
                Path(command[-1] + "-debug.csv").write_text("bad,header\n1,2\n",
                                                            encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            malformed = analyze_script(source, "binary", base_dir=ROOT, runner=bad_csv)
            self.assertFalse(malformed.success)
            self.assertIsNone(malformed.frames)
            self.assertIn("missing required fields", malformed.report.stderr)

    def test_txt_analyze_uses_normal_reverse_conversion_pipeline(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "nx with spaces.txt"
            source.write_text("0 KEY_A 0;0 0;0\n", encoding="utf-8")
            result = analyze_script(source, "binary", base_dir=ROOT)
            self.assertTrue(result.success, result.report.text)
            self.assertEqual(result.frames.total_frames, 1)
            self.assertEqual([path.name for path in Path(folder).iterdir()], [source.name])
