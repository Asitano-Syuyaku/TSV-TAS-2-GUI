"""Converter-owned source-line mapping and disposable snapshot analysis."""

import io
import subprocess
import unittest
from pathlib import Path

from python_to_exe.editor.line_positions import (LinePosition, analyze_positions,
                                                  parse_line_positions)


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
        # Current converter gives a truly blank physical line its default duration 1.
        self.assertEqual(positions.for_line(6), LinePosition(1, 1, 1))
        self.assertEqual(positions.for_line(7), LinePosition(2, 1, 2))
        self.assertEqual(positions.total_frames, 3)

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
