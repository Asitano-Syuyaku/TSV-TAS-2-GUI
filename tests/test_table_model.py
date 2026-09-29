"""Lossless, literal TAB table data independent of a display server."""

import tempfile
import unittest
from pathlib import Path

from python_to_exe.editor.document import EditorDocument
from python_to_exe.editor.table_model import CellSelection, TableModel, visible_span


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

    def test_rectangular_selection_and_tsv_copy(self):
        selection = CellSelection((1, 2))
        selection.move_to(0, 0, extend=True)
        self.assertEqual(selection.anchor, (1, 2))
        self.assertEqual(selection.active, (0, 0))
        self.assertEqual(selection.bounds, (0, 1, 0, 2))
        model = TableModel("A\tB\t\nC\tD\n")
        self.assertEqual(model.copy_range(selection.bounds), "A\tB\t\nC\tD\t")
        selection.move_to(2, 1)
        self.assertEqual(selection.bounds, (2, 2, 1, 1))
        selection.clamp(2, 1)
        self.assertEqual(selection.active, (1, 1))

    def test_paste_scalar_matrix_ragged_trailing_and_japanese(self):
        model = TableModel("x\tkeep\nq\tstay")
        self.assertEqual(model.paste(0, 0, "A\tB\r\nC\tD\r\n"), (2, 2))
        self.assertEqual(model.to_text(), "A\tB\nC\tD")
        self.assertEqual(model.paste(1, 1, "a\t\n日本語"), (2, 2))
        self.assertEqual(model.to_text(), "A\tB\nC\ta\t\n\t日本語")
        self.assertEqual(model.paste(0, 1, "猫"), (1, 1))
        self.assertEqual(model.to_text(), "A\t猫\nC\ta\t\n\t日本語")
        self.assertEqual(TableModel.clipboard_rows("A\t\n\n"), [["A", ""], [""]])
        ragged = TableModel("x\ty\tz\n1\t2\t3")
        ragged.paste(0, 0, "A\tB\nC")
        self.assertEqual(ragged.to_text(), "A\tB\tz\nC\t2\t3")

    def test_clear_cut_and_row_column_operations_keep_literal_rows(self):
        original = "a\t\t\n\n/pause\n$angle = 90\n// comment"
        model = TableModel(original)
        self.assertEqual(model.copy_range((0, 1, 0, 2)), "a\t\t\n\t\t")
        model.clear_range((0, 1, 0, 2))
        self.assertEqual(model.to_text(), "\t\t\n\n/pause\n$angle = 90\n// comment")
        model = TableModel(original)
        model.insert_row(1)
        self.assertEqual(model.to_text(), "a\t\t\n\n\n/pause\n$angle = 90\n// comment")
        model.delete_row(1)
        self.assertEqual(model.to_text(), original)
        model.duplicate_row(0)
        self.assertEqual(model.rows[1], ["a", "", ""])
        model.delete_row(1)
        self.assertEqual(model.to_text(), original)
        model.insert_column(1)
        self.assertEqual(model.rows[0], ["a", "", "", ""])
        self.assertEqual(model.rows[1], ["", ""])
        self.assertEqual(model.rows[2], ["/pause", ""])
        model.delete_column(1)
        self.assertEqual(model.to_text(), original)
        model = TableModel("one")
        model.delete_row(0)
        self.assertEqual(model.to_text(), "")
        model.delete_column(0)
        self.assertEqual(model.to_text(), "")

    def test_ten_thousand_rows_copy_selection_and_paste(self):
        model = TableModel("\n".join(f"{row}\tvalue\t" for row in range(10000)))
        selection = CellSelection((9000, 0), (9999, 2))
        self.assertEqual(model.copy_range(selection.bounds).count("\n"), 999)
        updated = model.copy()
        updated.paste(9000, 1, "猫\t犬\n鳥\t魚")
        self.assertEqual(updated.row_count, 10000)
        self.assertEqual(updated.cell(9000, 1), "猫")
        self.assertEqual(updated.cell(9001, 2), "魚")
        self.assertEqual(updated.cell(8999, 1), "value")


if __name__ == "__main__":
    unittest.main()
