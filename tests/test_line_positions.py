"""Converter-owned source-line mapping and disposable snapshot analysis."""

import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from python_to_exe.converter_logic import build_commands
from python_to_exe.editor.debug_csv import load_debug_csv
from python_to_exe.editor.line_positions import (LinePosition, LinePositions,
                                                  analyze_positions, parse_line_positions)


ROOT = Path(__file__).resolve().parents[1]


class LinePositionTests(unittest.TestCase):
    def analyze(self, text):
        result = analyze_positions(text, base_dir=ROOT)
        self.assertTrue(result.success, result.error)
        return result.positions

    def test_basic_zero_based_position_and_total(self):
        positions = self.analyze("1\ta\n33\tb\n")
        self.assertEqual(positions.for_line(1), LinePosition(0, 1, 0))
        self.assertEqual(positions.for_line(2), LinePosition(1, 33, 33))
        self.assertEqual(positions.total_frames, 34)
        self.assertIsNone(positions.for_line(3))

    def test_variables_math_previous_duration_and_source_numbers(self):
        positions = self.analyze("$n = 33\n1\ta\n$n\tb\n1+2\ta\n!\tb\n")
        self.assertEqual(positions.for_line(1), LinePosition(0, 0, None))
        self.assertEqual(positions.for_line(2), LinePosition(0, 1, 0))
        self.assertEqual(positions.for_line(3), LinePosition(1, 33, 33))
        self.assertEqual(positions.for_line(4), LinePosition(34, 3, 36))
        self.assertEqual(positions.for_line(5), LinePosition(37, 3, 39))
        self.assertEqual(positions.total_frames, 40)

    def test_comment_command_zero_toggle_and_blank_line_follow_converter(self):
        positions = self.analyze("1\ta\n// comment\n/pause\n0\ta\n*\tb\n\n1\tb\n")
        self.assertEqual(positions.for_line(2), LinePosition(1, 0, None))
        self.assertEqual(positions.for_line(3), LinePosition(1, 0, None))
        self.assertEqual(positions.for_line(4), LinePosition(1, 0, None))
        self.assertEqual(positions.for_line(5), LinePosition(1, 0, None))
        self.assertEqual(positions.for_line(6), LinePosition(1, 0, None))
        self.assertEqual(positions.for_line(7), LinePosition(1, 1, 1))
        self.assertEqual(positions.total_frames, 2)

    def test_only_completely_empty_rows_consume_zero_frames(self):
        positions = self.analyze("1\ta\n\n\t\n \t  \n\ta\n\tls(90)\n1\tb\n")
        for line in (2, 3, 4):
            self.assertEqual(positions.for_line(line), LinePosition(1, 0, None))
        self.assertEqual(positions.for_line(5), LinePosition(1, 1, 1))
        self.assertEqual(positions.for_line(6), LinePosition(2, 1, 2))
        self.assertEqual(positions.for_line(7), LinePosition(3, 1, 3))
        self.assertEqual(positions.total_frames, 4)

    def test_blank_row_does_not_change_previous_resolved_duration(self):
        positions = self.analyze("2\ta\n\n!\tb\n")
        self.assertEqual(positions.for_line(2), LinePosition(2, 0, None))
        self.assertEqual(positions.for_line(3), LinePosition(2, 2, 3))
        self.assertEqual(positions.total_frames, 4)

    def test_eighteen_frames_and_zero_based_output_formats(self):
        source_text = "1\ta\n\n5\n" + "1\n" * 11 + "1\tzl\n"
        positions = self.analyze(source_text)
        self.assertEqual(positions.total_frames, 18)
        self.assertEqual(positions.for_line(1), LinePosition(0, 1, 0))
        self.assertEqual(positions.for_line(2), LinePosition(1, 0, None))
        self.assertEqual(positions.for_line(15), LinePosition(17, 1, 17))
        self.assertEqual(positions.for_range(1, 15), LinePosition(0, 18, 17))
        self.assertEqual(positions.for_range(15, 1), LinePosition(0, 18, 17))
        self.assertEqual(positions.for_range(2, 2), LinePosition(1, 0, None))
        self.assertIsNone(positions.for_range(1, 16))
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "eighteen.tsv"
            source.write_text(source_text, encoding="utf-8")
            for format_name, suffix in (("binary", ""), ("stas", ".stas"),
                                        ("nxtas", ".txt")):
                commands = build_commands(source, folder, format_name, format_name,
                                          debug=True, base_dir=ROOT)
                result = subprocess.run(commands[-1], cwd=ROOT, capture_output=True,
                                        text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                output = Path(folder) / (format_name + suffix)
                frames = load_debug_csv(str(output) + "-debug.csv")
                self.assertEqual(frames.total_frames, 18)
                self.assertEqual(frames.detail(0)["Frame"], "0")
                self.assertEqual(frames.detail(17)["Frame"], "17")
                if format_name == "nxtas":
                    steps = [int(line.split()[0]) for line in output.read_text().splitlines()]
                    self.assertEqual(steps, list(range(18)))
                elif format_name == "stas":
                    data = output.read_bytes()
                    prefix = b"\x00\x00\x04\x00\x00\x00\x00\x00"
                    self.assertIn(prefix + (0).to_bytes(4, "little"), data)
                    self.assertIn(prefix + (17).to_bytes(4, "little"), data)

    def test_blank_only_script_has_no_frames_in_each_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "blank.tsv"
            source.write_text("\n\t\n \t  \n", encoding="utf-8")
            for format_name in ("binary", "stas", "nxtas"):
                commands = build_commands(source, folder, format_name, format_name,
                                          line_map=True, base_dir=ROOT)
                result = subprocess.run(commands[-1], cwd=ROOT, capture_output=True,
                                        text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                positions = self.analyze(source.read_text(encoding="utf-8"))
                self.assertEqual(positions.total_frames, 0)

    def test_loop_sequence_and_local_duration_keep_converter_row_duration(self):
        positions = self.analyze("3\ta[1]|b[?]\n3\ta[1]/b[1]\n3\ta[2]\n"
                                 "3\ta[*]\n")
        self.assertEqual(positions.for_line(1), LinePosition(0, 3, 2))
        self.assertEqual(positions.for_line(2), LinePosition(3, 3, 5))
        self.assertEqual(positions.for_line(3), LinePosition(6, 3, 8))
        self.assertEqual(positions.for_line(4), LinePosition(9, 3, 11))
        self.assertEqual(positions.total_frames, 12)

    def test_negative_duration_is_reported_without_editor_evaluation(self):
        positions = self.analyze("5\ta\n-2\tb\n")
        self.assertEqual(positions.for_line(2), LinePosition(5, -2, None))
        self.assertEqual(positions.total_frames, 5)
        self.assertIsNone(positions.for_range(1, 2))

    def test_noncontiguous_metadata_range_is_not_guessed(self):
        positions = LinePositions({1: LinePosition(0, 2, 1),
                                   2: LinePosition(4, 2, 5)}, 6)
        self.assertIsNone(positions.for_range(1, 2))

    def test_two_player_rows_share_one_logical_frame_count(self):
        positions = self.analyze("$is_two_player = true\n1\ta\tca\n33\tb\tcb\n")
        self.assertEqual(positions.for_line(3), LinePosition(1, 33, 33))
        self.assertEqual(positions.total_frames, 34)

    def test_parser_rejects_malformed_sidecar(self):
        with self.assertRaisesRegex(ValueError, "header"):
            parse_line_positions(io.StringIO("SourceLine,Duration\n"))
        header = "SourceLine,StartFrame,Duration,EndFrame,TotalFrames\n"
        with self.assertRaisesRegex(ValueError, "row"):
            parse_line_positions(io.StringIO(header + "1,0,1\n"))
        with self.assertRaisesRegex(ValueError, "Inconsistent"):
            parse_line_positions(io.StringIO(header + "2,0,1,0,1\n"))

    def test_analysis_failure_ftp_off_and_temp_cleanup(self):
        paths = []
        commands = []

        def runner(command, **kwargs):
            commands.append(command)
            paths.append(Path(command[-2]).parent)
            return subprocess.run(command, **kwargs)

        result = analyze_positions("1\ta\n", base_dir=ROOT, runner=runner)
        self.assertTrue(result.success, result.error)
        self.assertIn("-m", commands[0])
        self.assertNotIn("-f", commands[0])
        self.assertNotIn("-d", commands[0])
        self.assertTrue(all(not path.exists() for path in paths))
        failed = analyze_positions("1\tls(\n", base_dir=ROOT, runner=runner)
        self.assertFalse(failed.success)
        self.assertIn("Syntax error(s) on line 1", failed.error)
        self.assertTrue(all(not path.exists() for path in paths))
