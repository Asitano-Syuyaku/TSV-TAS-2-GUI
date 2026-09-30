"""Resolved Debug CSV data and temporary converter analysis."""

import csv
import io
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from python_to_exe.editor.debug_csv import (SUMMARY_FIELDS, load_debug_csv,
                                           load_stick_csv, parse_debug_csv,
                                           resolved_sticks)
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

    def test_windows_newlines_and_legacy_blank_records(self):
        # csv.writer emits CRLF. A legacy Windows text stream translated its LF
        # again, producing CR CR LF and an empty csv.reader record per data row.
        original = make_csv([(0, False), (0, True), (2, False)]).getvalue()
        header, *data_rows = original.splitlines(keepends=True)
        legacy = header + "".join(row.replace("\r\n", "\r\r\n") for row in data_rows)
        cases = ((original, 3),
                 (original.replace("\r\n", "\n"), 3),
                 (legacy, 3))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "windows-debug.csv"
            for content, expected_total in cases:
                path.write_bytes(content.encode("utf-8"))
                frames = load_debug_csv(path)
                self.assertEqual((len(frames.rows), frames.total_frames), (3, expected_total))
                self.assertEqual([frames.summary(i)[1] for i in range(3)],
                                 ["1P", "2P", "1P"])
                self.assertEqual(frames.row_for_frame(2), 2)

    def test_only_zero_field_records_are_skipped(self):
        original = make_csv([(0, False), (1, False)]).getvalue()
        header, first, second = original.splitlines(keepends=True)
        frames = parse_debug_csv(io.StringIO(header + "\r\n" + first + "\n" + second,
                                             newline=""))
        self.assertEqual((len(frames.rows), frames.total_frames), (2, 2))
        for malformed in ("0,False\r\n", '""\r\n'):
            with self.assertRaisesRegex(ValueError, "fields"):
                parse_debug_csv(io.StringIO(header + first + "\n" + malformed + second,
                                            newline=""))

    def test_streamed_sticks_match_full_csv_with_2p_gaps_and_windows_blanks(self):
        source = make_csv([(0, False), (0, True), (3, False), (3, True), (3, False)],
                          extra=("lx.r", "rs.r", "future.motion"))
        rows = list(csv.reader(source))
        headers = rows[0]
        for index, row in enumerate(rows[1:]):
            row[headers.index("ls.x")] = str(index * 100)
            row[headers.index("ls.y")] = "nan" if index == 4 else "1234"
            row[headers.index("Command")] = "日本語,\"quoted\""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "日本語 with spaces-debug.csv"
            with path.open("w", encoding="utf-8", newline="") as target:
                csv.writer(target).writerows(rows)
            original = path.read_bytes()
            for content in (original, original.replace(b"\r\n", b"\r\r\n")):
                path.write_bytes(content)
                full = load_debug_csv(path)
                streamed = load_stick_csv(path)
                self.assertEqual(streamed, resolved_sticks(full))
                self.assertEqual(tuple(streamed.rows), (0, 3))
                self.assertEqual(streamed.rows[3].left.x, 400)
                self.assertIsNone(streamed.rows[3].left.y)
                self.assertEqual(full.detail(4)["Command"], "日本語,\"quoted\"")
                self.assertIn("future.motion", full.detail(4))

    def test_streamed_reader_still_validates_discarded_2p_rows(self):
        original = make_csv([(0, False), (1, True)]).getvalue()
        rows = list(csv.reader(io.StringIO(original)))
        cases = ((rows[-1][:-1], "fields"),
                 (["-1"] + rows[-1][1:], "negative Frame"),
                 (["bad"] + rows[-1][1:], "invalid Frame"),
                 (["1", "maybe"] + rows[-1][2:], "invalid 2ndPlayer"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            for bad_row, error in cases:
                with path.open("w", encoding="utf-8", newline="") as target:
                    csv.writer(target).writerows(rows[:-1] + [bad_row])
                with self.assertRaisesRegex(ValueError, error):
                    load_stick_csv(path)

    def test_shared_values_keep_every_literal_and_are_local_to_each_read(self):
        original = make_csv(((index, False) for index in range(5000))).getvalue()
        first = parse_debug_csv(io.StringIO(original))
        second = parse_debug_csv(io.StringIO(original))
        self.assertEqual(first, second)
        column = first.headers.index("new.motion.field")
        self.assertEqual(first.rows[-1][0], "4999")
        self.assertIs(first.rows[0][column], first.rows[-1][column])
        self.assertIsNot(first.rows[0][column], second.rows[0][column])

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
