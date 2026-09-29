import unittest
from pathlib import Path

from python_to_exe.editor.text_ops import (file_kind, find_next, find_previous,
                                           line_column, replace_all, replace_current)


class EditorTextOperationsTests(unittest.TestCase):
    def test_find_next_previous_and_wrap_with_japanese(self):
        text = "開始\t猫\n猫\t終了"
        self.assertEqual(find_next(text, "猫"), (3, 4))
        self.assertEqual(find_next(text, "猫", 4), (5, 6))
        self.assertEqual(find_next(text, "猫", len(text)), (3, 4))
        self.assertEqual(find_previous(text, "猫", 5), (3, 4))
        self.assertEqual(find_previous(text, "猫", 3), (5, 6))
        self.assertIsNone(find_next(text, "鳥"))
        self.assertIsNone(find_previous(text, ""))

    def test_replace_current_and_all_keep_tabs_and_newlines(self):
        original = "1\t猫\r\n2\t猫\n"
        self.assertEqual(replace_current(original, "猫", "犬", (2, 3)), "1\t犬\r\n2\t猫\n")
        self.assertIsNone(replace_current(original, "鳥", "犬", (2, 3)))
        self.assertIsNone(replace_current(original, "猫", "犬", None))
        self.assertEqual(replace_all(original, "猫", "犬"), ("1\t犬\r\n2\t犬\n", 2))
        self.assertEqual(replace_all(original, "鳥", "犬"), (original, 0))
        self.assertEqual(replace_all(original, "", "犬"), (original, 0))

    def test_status_position_and_file_kind(self):
        self.assertEqual(line_column("1.0"), (1, 1))
        self.assertEqual(line_column("42.7"), (42, 8))
        self.assertEqual(file_kind(Path("sample.tsv")), "TSV-TAS")
        self.assertEqual(file_kind(Path("sample.txt")), "nx-TAS")
        self.assertEqual(file_kind(None), "TSV-TAS")


if __name__ == "__main__":
    unittest.main()
