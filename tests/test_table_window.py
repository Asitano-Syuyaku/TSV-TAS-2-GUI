"""Headless checks for Raw/Table state and the existing save paths."""

import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from python_to_exe.editor.document import EditorDocument
from python_to_exe.editor.table_model import TableModel


class TextStub:
    def __init__(self, value=""):
        self.value = value
        self._undo = []
        self._redo = []
        self._before = None

    def _offset(self, index):
        if index in ("end", "end-1c"):
            return len(self.value)
        if index == "insert":
            return 0
        if index.startswith("1.0+") and index.endswith("c"):
            return int(index[4:-1])
        base, _, suffix = index.partition(" ")
        line = int(base.split(".")[0])
        start = sum(len(part) + 1 for part in self.value.split("\n")[:line - 1])
        if suffix == "lineend":
            return start + len(self.value.split("\n")[line - 1])
        return start

    def get(self, first, last):
        return self.value[self._offset(first):self._offset(last)]

    def delete(self, first, last):
        start, end = self._offset(first), self._offset(last)
        self.value = self.value[:start] + self.value[end:]

    def insert(self, first, value):
        start = self._offset(first)
        self.value = self.value[:start] + value + self.value[start:]

    def edit_separator(self):
        if self._before is None:
            self._before = self.value
        else:
            if self.value != self._before:
                self._undo.append(self._before)
                self._redo.clear()
            self._before = None

    def cget(self, name):
        return getattr(self, name, True)

    def configure(self, **options):
        for name, value in options.items():
            setattr(self, name, value)

    def edit_undo(self):
        self._redo.append(self.value)
        self.value = self._undo.pop()

    def edit_redo(self):
        self._undo.append(self.value)
        self.value = self._redo.pop()

    def edit_reset(self):
        self._undo.clear()
        self._redo.clear()

    def edit_modified(self, value=None):
        return False

    def index(self, index):
        return "1.0"

    def focus_set(self):
        pass


class GridStub:
    def __init__(self, on_change):
        self.on_change = on_change
        self.model = TableModel("")
        self.selected = (0, 0)
        self.pending = None
        self.canvas = SimpleNamespace(focus_set=lambda: None)

    def set_text(self, text):
        self.model = TableModel(text)

    def commit_edit(self):
        if self.pending is None:
            return True
        row, column, value = self.pending
        old_line = self.model.line(row)
        new_line = self.model.changed_line(row, column, value)
        if old_line != new_line and not self.on_change(row, old_line, new_line):
            return False
        self.model.update_line(row, new_line)
        self.pending = None
        return True

    def pack(self, **kwargs):
        pass

    def pack_forget(self):
        pass


class TableWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_tk = types.ModuleType("tkinter")
        fake_tk.Toplevel = type("FakeToplevel", (), {})
        fake_tk.filedialog = SimpleNamespace()
        fake_tk.font = SimpleNamespace()
        fake_tk.messagebox = SimpleNamespace()
        with patch.dict(sys.modules, {"tkinter": fake_tk}):
            sys.modules.pop("python_to_exe.editor.window", None)
            cls.editor_window = importlib.import_module("python_to_exe.editor.window")

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("python_to_exe.editor.window", None)

    def _window(self, path):
        window = self.editor_window.EditorWindow.__new__(self.editor_window.EditorWindow)
        window.words = self.editor_window.LABELS["en"]
        window.document = EditorDocument()
        if path is not None:
            window.document.open(path)
        window.text = TextStub(window.document.text)
        window.status = SimpleNamespace(config=lambda **kwargs: None)
        window.raw_frame = SimpleNamespace(pack=lambda **kwargs: None, pack_forget=lambda: None)
        window.table_grid = GridStub(window._table_cell_changed)
        window._table_button = SimpleNamespace(configure=lambda **kwargs: None, state=None)
        window._table_button.configure = lambda **kwargs: vars(window._table_button).update(kwargs)
        window._view = "raw"
        window.title = lambda value: None
        window._schedule_line_numbers = lambda: None
        window.on_saved = None
        window.on_convert = None
        window.can_convert = None
        return window

    def test_new_document_table_edit_save_as_and_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self._window(None)
            window._update_view_button()
            self.assertEqual(window._table_button.state, "normal")
            self.assertTrue(window.show_table())
            self.assertFalse(window.document.modified)
            window.table_grid.pending = (0, 0, "猫")
            with patch.object(self.editor_window.filedialog, "asksaveasfilename", return_value="",
                              create=True):
                self.assertFalse(window.save_as())
            self.assertEqual(window._view, "table")
            self.assertEqual(window.document.text, "")
            self.assertIsNone(window.document.path)
            self.assertEqual(window.table_grid.pending, (0, 0, "猫"))
            self.assertEqual(window._table_button.state, "normal")

            target = Path(folder) / "new 日本語.tsv"
            with patch.object(self.editor_window.filedialog, "asksaveasfilename",
                              return_value=str(target), create=True):
                self.assertTrue(window.save_as())
            self.assertEqual(target.read_text(encoding="utf-8"), "猫")
            self.assertEqual(window.document.path, target)
            self.assertEqual(window._view, "table")
            self.assertEqual(window._table_button.state, "normal")
            self.assertFalse(window.document.modified)

    def test_table_save_as_txt_commits_and_switches_raw(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "script.tsv"
            source.write_text("A\tB", encoding="utf-8")
            window = self._window(source)
            window._update_view_button()
            self.assertEqual(window._table_button.state, "normal")
            self.assertTrue(window.show_table())
            window.table_grid.pending = (0, 1, "犬")
            target = Path(folder) / "script.txt"
            with patch.object(self.editor_window.filedialog, "asksaveasfilename",
                              return_value=str(target), create=True):
                self.assertTrue(window.save_as())
            self.assertEqual(target.read_text(encoding="utf-8"), "A\t犬")
            self.assertEqual(window._view, "raw")
            self.assertEqual(window._table_button.state, "disabled")
            self.assertFalse(window.show_table())
            self.assertFalse(window.document.modified)

    def test_view_only_is_lossless_edit_undo_redo_save_and_convert(self):
        with tempfile.TemporaryDirectory(prefix="table 日本語 ") as folder:
            source = Path(folder) / "my script.tsv"
            original = b"1\ta\t\r\n\r\n/pause\r\n"
            source.write_bytes(original)
            window = self._window(source)
            self.assertTrue(window.show_table())
            self.assertEqual(window.table_grid.model.to_text(), window.document.text)
            self.assertFalse(window.document.modified)
            self.assertTrue(window.show_raw())
            self.assertFalse(window.document.modified)
            self.assertEqual(window.text.value, window.document.text)
            self.assertEqual(source.read_bytes(), original)

            self.assertTrue(window.show_table())
            window.table_grid.pending = (0, 1, "猫")
            self.assertTrue(window.show_raw())
            self.assertEqual(window.document.text, "1\t猫\t\n\n/pause\n")
            self.assertTrue(window.document.modified)
            self.assertTrue(window.undo())
            self.assertFalse(window.document.modified)
            self.assertTrue(window.redo())
            self.assertTrue(window.document.modified)
            self.assertTrue(window.save())
            self.assertEqual(source.read_bytes(), "1\t猫\t\r\n\r\n/pause\r\n".encode())

            window.text.value = "1\t犬\t\n\n/pause\n"
            window._sync_text()
            self.assertTrue(window.show_table())
            self.assertEqual(window.table_grid.model.cell(0, 1), "犬")
            window.table_grid.pending = (0, 1, "鳥")
            converted = []
            window.on_convert = lambda path: converted.append((path, path.read_bytes())) or True
            self.assertTrue(window.save_and_convert())
            self.assertEqual(converted, [(source, "1\t鳥\t\r\n\r\n/pause\r\n".encode())])
            self.assertFalse(window.document.modified)

            renamed = Path(folder) / "renamed 日本語.tsv"
            with patch.object(self.editor_window.filedialog, "asksaveasfilename", return_value=str(renamed),
                              create=True):
                self.assertTrue(window.save_as())
            self.assertEqual(window.document.path, renamed)
            self.assertEqual(renamed.read_bytes(), converted[0][1])

            txt_path = Path(folder) / "renamed 日本語.txt"
            with patch.object(self.editor_window.filedialog, "asksaveasfilename", return_value=str(txt_path),
                              create=True):
                self.assertTrue(window.save_as())
            self.assertEqual(window._view, "raw")
            self.assertFalse(window.show_table())
            self.assertEqual(txt_path.read_bytes(), converted[0][1])

    def test_txt_stays_raw(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "script.txt"
            source.write_text("0\tKEY_A", encoding="utf-8")
            window = self._window(source)
            window._update_view_button()
            self.assertEqual(window._table_button.state, "disabled")
            self.assertFalse(window.show_table())
            self.assertEqual(window._view, "raw")

            tsv = Path(folder) / "script.tsv"
            tsv.write_text("A\tB", encoding="utf-8")
            window = self._window(tsv)
            self.assertTrue(window.show_table())
            self.assertTrue(window.open_file(source))
            self.assertEqual(window._view, "raw")
            self.assertEqual(window.document.path, source)
            self.assertEqual(window._table_button.state, "disabled")

    def test_bulk_changes_are_one_undo_step_and_keep_save_paths(self):
        with tempfile.TemporaryDirectory(prefix="spreadsheet 日本語 ") as folder:
            source = Path(folder) / "my script.tsv"
            source.write_bytes(b"A\tB\t\r\nC\tD\t\r\n")
            window = self._window(source)
            self.assertTrue(window.show_table())
            original = window.document.text
            model = TableModel(original)
            model.paste(0, 0, "猫\t犬\r\n鳥\t魚\r\n")
            pasted = model.to_text()
            self.assertTrue(window._table_text_changed(original, pasted))
            window.table_grid.set_text(pasted)
            self.assertTrue(window.document.modified)
            self.assertEqual(len(window.text._undo), 1)
            self.assertTrue(window.undo())
            self.assertEqual(window.document.text, original)
            self.assertFalse(window.document.modified)
            self.assertTrue(window.redo())
            self.assertEqual(window.document.text, pasted)

            model.insert_row(1)
            inserted = model.to_text()
            self.assertTrue(window._table_text_changed(pasted, inserted))
            window.table_grid.set_text(inserted)
            self.assertTrue(window.undo())
            self.assertEqual(window.document.text, pasted)
            self.assertTrue(window.undo())
            self.assertEqual(window.document.text, original)
            self.assertTrue(window.redo())
            self.assertTrue(window.redo())
            self.assertEqual(window.document.text, inserted)
            self.assertTrue(window.save())
            self.assertEqual(source.read_bytes(), "猫\t犬\t\r\n\r\n鳥\t魚\t\r\n".encode())

            renamed = Path(folder) / "保存 先.tsv"
            with patch.object(self.editor_window.filedialog, "asksaveasfilename", return_value=str(renamed),
                              create=True):
                self.assertTrue(window.save_as())
            self.assertEqual(renamed.read_bytes(), source.read_bytes())
            model.delete_column(2)
            updated = model.to_text()
            self.assertTrue(window._table_text_changed(inserted, updated))
            window.table_grid.set_text(updated)
            converted = []
            window.on_convert = lambda path: converted.append(path.read_bytes()) or True
            self.assertTrue(window.save_and_convert())
            self.assertEqual(converted, ["猫\t犬\r\n\r\n鳥\t魚\r\n".encode()])
            self.assertFalse(window.document.modified)

    def test_each_range_and_structure_edit_uses_one_text_undo_step(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "undo.tsv"
            source.write_text("A\tB\t\nC\tD\t\n", encoding="utf-8")
            changes = (
                ("clear_range", ((0, 1, 0, 1),)),
                ("insert_row", (1,)), ("delete_row", (0,)),
                ("duplicate_row", (0,)),
                ("insert_column", (1,)), ("delete_column", (1,)),
            )
            for operation, args in changes:
                with self.subTest(operation=operation):
                    window = self._window(source)
                    self.assertTrue(window.show_table())
                    original = window.document.text
                    model = TableModel(original)
                    getattr(model, operation)(*args)
                    updated = model.to_text()
                    self.assertNotEqual(original, updated)
                    self.assertTrue(window._table_text_changed(original, updated))
                    window.table_grid.set_text(updated)
                    self.assertEqual(len(window.text._undo), 1)
                    self.assertTrue(window.undo())
                    self.assertEqual(window.document.text, original)
                    self.assertFalse(window.document.modified)
                    self.assertTrue(window.redo())
                    self.assertEqual(window.document.text, updated)
                    self.assertTrue(window.document.modified)


if __name__ == "__main__":
    unittest.main()
