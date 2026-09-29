"""Lossless, literal TAB table data independent of a display server."""

import tempfile
import unittest
from pathlib import Path

from python_to_exe.editor.document import EditorDocument
from python_to_exe.editor.table_model import TableModel, visible_span


class TableModelTests(unittest.TestCase):
    def test_round_trip_keeps_tabs_blank_rows_and_special_lines(self):
        for text in ("", "\n", "a\t\t\n\n/pause\n$angle = 90\n// comment\n日本語\t",
                     "a\tb\t\t\n\n最後\t"):
            with self.subTest(text=text):
                model = TableModel(text)
                self.assertEqual(model.to_text(), text)
        model = TableModel("one\t\t\n\n/pause")
        self.assertEqual(model.rows, [["one", "", ""], [""], ["/pause"]])

    def test_edit_changes_only_one_line_and_preserves_empty_cells(self):
        model = TableModel("a\t\t\n\n/pause")
        self.assertEqual(model.changed_line(0, 1, "日本語"), "a\t日本語\t")
        model.update_line(0, model.changed_line(0, 1, "日本語"))
        self.assertEqual(model.to_text(), "a\t日本語\t\n\n/pause")
        self.assertEqual(model.changed_line(1, 2, ""), "")
        self.assertEqual(model.changed_line(1, 2, "b"), "\t\tb")
        for invalid in ("a\tb", "a\nb", "a\rb"):
            with self.assertRaises(ValueError):
                model.changed_line(0, 0, invalid)

    def test_original_lf_and_crlf_bytes_survive_view_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="table 日本語 ") as folder:
            for ending in (b"\n", b"\r\n"):
                source = Path(folder) / ("test-crlf.tsv" if ending == b"\r\n" else "test-lf.tsv")
                original = b"1\ta\t" + ending + ending + "/pause".encode() + ending
                source.write_bytes(original)
                document = EditorDocument()
                document.open(source)
                model = TableModel(document.text)
                self.assertEqual(model.to_text(), document.text)
                self.assertFalse(document.modified)
                document.save()
                self.assertEqual(source.read_bytes(), original)
                model.update_line(0, model.changed_line(0, 1, "猫"))
                document.set_text(model.to_text())
                document.save()
                self.assertEqual(source.read_bytes(), "1\t猫\t".encode() + ending + ending + b"/pause" + ending)

    def test_visible_work_is_bounded_for_ten_thousand_rows(self):
        model = TableModel("\n".join(f"{row}\tvalue\t" for row in range(10000)))
        self.assertEqual(model.row_count, 10000)
        self.assertEqual(model.column_count, 3)
        self.assertLessEqual(len(visible_span(50000, 500, 24, 24, model.row_count)), 25)
        self.assertLessEqual(len(visible_span(1000, 800, 48, 160, model.column_count)), 3)


if __name__ == "__main__":
    unittest.main()
