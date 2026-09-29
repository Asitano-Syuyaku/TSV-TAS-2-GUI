"""Headless checks for visible-cell drawing and single-cell commits."""

import importlib
import sys
import types
import unittest
from unittest.mock import patch

from python_to_exe.editor.table_model import TableModel


class CanvasStub:
    def __init__(self):
        self.rectangles = 0
        self.labels = 0

    def canvasx(self, value):
        return 0

    def canvasy(self, value):
        return 9000 * 24

    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 500

    def delete(self, tag):
        pass

    def create_rectangle(self, *args, **kwargs):
        self.rectangles += 1

    def create_text(self, *args, **kwargs):
        self.labels += 1


class TableGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_tk = types.ModuleType("tkinter")
        fake_tk.Frame = type("FakeFrame", (), {"winfo_exists": lambda self: True})
        with patch.dict(sys.modules, {"tkinter": fake_tk}):
            sys.modules.pop("python_to_exe.editor.grid", None)
            cls.module = importlib.import_module("python_to_exe.editor.grid")

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("python_to_exe.editor.grid", None)

    def test_draws_only_visible_cells_and_headers(self):
        grid = self.module.TableGrid.__new__(self.module.TableGrid)
        grid.canvas = CanvasStub()
        grid.model = TableModel("\n".join(f"{i}\ta\tb" for i in range(10000)))
        grid.font = types.SimpleNamespace(measure=lambda value: len(value) * 8)
        grid.selected = (9000, 1)
        grid.header_height = grid.row_height = 24
        grid.gutter_width = 48
        grid.column_width = 160
        grid._draw_job = None
        grid._editor = None
        grid._draw_visible()
        self.assertLess(grid.canvas.rectangles, 150)
        self.assertLess(grid.canvas.labels, 150)

    def test_commit_changes_one_line_only(self):
        grid = self.module.TableGrid.__new__(self.module.TableGrid)
        grid.model = TableModel("a\t\t\n/pause")
        grid.selected = (0, 1)
        events = []
        grid.on_change = lambda row, old, new: events.append((row, old, new)) or True
        grid._update_region = lambda: None
        grid._schedule_draw = lambda: None
        grid._editor = types.SimpleNamespace(get=lambda: "日本語", destroy=lambda: None)
        self.assertTrue(grid.commit_edit())
        self.assertEqual(events, [(0, "a\t\t", "a\t日本語\t")])
        self.assertEqual(grid.model.to_text(), "a\t日本語\t\n/pause")

    def test_arrow_tab_and_enter_move_selected_cell(self):
        grid = self.module.TableGrid.__new__(self.module.TableGrid)
        grid.model = TableModel("a\tb\nc\td")
        grid.selected = (0, 0)
        grid._editor = None
        grid._update_region = lambda: None
        grid._ensure_visible = lambda: None
        grid._schedule_draw = lambda: None
        grid.begin_edit = lambda: None
        grid.on_select = lambda: None
        self.assertEqual(grid._move(0, 1), "break")
        self.assertEqual(grid.selected, (0, 1))
        self.assertEqual(grid._move(1, 0), "break")
        self.assertEqual(grid.selected, (1, 1))
        self.assertEqual(grid._move(0, -1), "break")
        self.assertEqual(grid.selected, (1, 0))

    def test_horizontal_scroll_keeps_gutter_fixed_and_hits_visible_cell(self):
        grid = self.module.TableGrid.__new__(self.module.TableGrid)
        grid.model = TableModel("a\tb\tc\td")
        grid.selected = (0, 0)
        grid.gutter_width = 48
        grid.header_height = grid.row_height = 24
        grid.column_width = 160
        grid.canvas = types.SimpleNamespace(canvasx=lambda x: x + 320,
                                            canvasy=lambda y: y)
        grid.commit_edit = lambda: True
        grid._ensure_visible = lambda: None
        grid._schedule_draw = lambda: None
        grid.on_select = lambda: None
        grid.begin_edit = lambda: None
        grid._click(types.SimpleNamespace(x=20, y=40))
        self.assertEqual(grid.selected, (0, 0))  # Fixed gutter, not a cell.
        grid._click(types.SimpleNamespace(x=50, y=40))
        self.assertEqual(grid.selected, (0, 2))


if __name__ == "__main__":
    unittest.main()
