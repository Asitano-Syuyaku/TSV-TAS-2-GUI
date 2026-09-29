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
        fake_tk.TclError = RuntimeError
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
        grid.selection.move_to(9999, 2, extend=True)
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
                                            canvasy=lambda y: y,
                                            focus_set=lambda: None)
        grid.commit_edit = lambda: True
        grid._ensure_visible = lambda: None
        grid._schedule_draw = lambda: None
        grid.on_select = lambda: None
        grid.begin_edit = lambda: None
        grid._click(types.SimpleNamespace(x=20, y=40))
        self.assertEqual(grid.selected, (0, 0))  # Fixed gutter, not a cell.
        grid._click(types.SimpleNamespace(x=50, y=40))
        self.assertEqual(grid.selected, (0, 2))

    def _working_grid(self, text):
        grid = self.module.TableGrid.__new__(self.module.TableGrid)
        grid.model = TableModel(text)
        grid.selected = (0, 0)
        grid._editor = None
        grid._update_region = lambda: None
        grid._ensure_visible = lambda: None
        grid._schedule_draw = lambda: None
        grid.on_select = lambda: None
        grid.changes = []
        grid.on_transform = lambda old, new: grid.changes.append((old, new)) or True
        clipboard = []
        grid.clipboard_clear = clipboard.clear
        grid.clipboard_append = clipboard.append
        grid.clipboard_get = lambda: clipboard[0]
        return grid, clipboard

    def test_copy_cut_paste_clear_and_structural_actions(self):
        grid, clipboard = self._working_grid("A\tB\t\nC\tD\t\n/pause")
        grid.selection.move_to(1, 2, extend=True)
        self.assertTrue(grid.copy_selection())
        self.assertEqual(clipboard, ["A\tB\t\nC\tD\t"])
        self.assertEqual(grid.changes, [])
        self.assertTrue(grid.cut_selection())
        self.assertEqual(grid.model.to_text(), "\t\t\n\t\t\n/pause")
        self.assertEqual(len(grid.changes), 1)
        grid.selected = (2, 0)
        self.assertTrue(grid.paste_clipboard())
        self.assertEqual(grid.model.to_text(), "\t\t\n\t\t\nA\tB\t\nC\tD\t")
        self.assertEqual(grid.selection.bounds, (2, 3, 0, 2))
        self.assertTrue(grid.clear_selection())
        self.assertEqual(grid.model.to_text(), "\t\t\n\t\t\n\t\t\n\t\t")
        grid.selected = (1, 0)
        self.assertTrue(grid.insert_row())
        self.assertEqual(grid.model.row_count, 5)
        self.assertTrue(grid.duplicate_row())
        self.assertEqual(grid.model.row_count, 6)
        self.assertTrue(grid.delete_row())
        self.assertEqual(grid.model.row_count, 5)
        self.assertTrue(grid.insert_column())
        self.assertEqual(grid.model.column_count, 4)
        self.assertTrue(grid.delete_column())
        self.assertEqual(grid.model.column_count, 3)
        self.assertEqual(len(grid.changes), 8)

    def test_shift_click_drag_and_shift_arrow_extend_rectangle(self):
        grid, _ = self._working_grid("a\tb\tc\nd\te\tf")
        grid.canvas = types.SimpleNamespace(
            canvasx=lambda x: x, canvasy=lambda y: y,
            focus_set=lambda: None, winfo_width=lambda: 800,
            winfo_height=lambda: 500)
        grid.gutter_width = 48
        grid.header_height = grid.row_height = 24
        grid.column_width = 160
        grid._edit_job = None
        grid._click(types.SimpleNamespace(x=60, y=35, state=0))
        grid._click(types.SimpleNamespace(x=220, y=60, state=1))
        self.assertEqual(grid.selection.anchor, (0, 0))
        self.assertEqual(grid.selection.active, (1, 1))
        self.assertEqual(grid.selection.bounds, (0, 1, 0, 1))
        grid._click(types.SimpleNamespace(x=220, y=35, state=0))
        grid._drag(types.SimpleNamespace(x=380, y=60))
        self.assertEqual(grid.selection.bounds, (0, 1, 1, 2))
        grid.begin_edit = lambda: self.fail("Shift movement must not start editing")
        self.assertEqual(grid._move(-1, 0, extend=True), "break")
        self.assertEqual(grid.selection.bounds, (0, 0, 1, 2))

    def test_entry_clipboard_keeps_text_editing_but_routes_tsv_paste(self):
        grid, clipboard = self._working_grid("old\tkeep")
        events = []
        grid._editor = types.SimpleNamespace(get=lambda: "old", destroy=lambda: None,
                                             event_generate=events.append)
        grid.on_change = lambda row, old, new: True
        self.assertTrue(grid.clipboard_action("Copy"))
        self.assertTrue(grid.clipboard_action("Cut"))
        self.assertEqual(events, ["<<Copy>>", "<<Cut>>"])
        clipboard.append("猫")
        self.assertIsNone(grid._entry_paste())
        self.assertTrue(grid.clipboard_action("Paste"))
        self.assertEqual(events[-1], "<<Paste>>")
        clipboard[0] = "猫\t犬\r\n鳥\t魚\r\n"
        self.assertEqual(grid._entry_paste(), "break")
        self.assertEqual(grid.model.to_text(), "猫\t犬\n鳥\t魚")
        self.assertEqual(len(grid.changes), 1)


if __name__ == "__main__":
    unittest.main()
