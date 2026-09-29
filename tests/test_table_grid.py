"""Headless checks for visible-cell drawing and single-cell commits."""

import importlib
import sys
import types
import unittest
from unittest.mock import patch

from python_to_exe.editor.table_model import TableModel


class CanvasStub:
    def __init__(self, origin_x=0, origin_y=9000 * 24, width=800, height=500):
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.width = width
        self.height = height
        self.rectangles = 0
        self.labels = 0
        self.boxes = []
        self.texts = []
        self.lines = []

    def canvasx(self, value):
        return self.origin_x + value

    def canvasy(self, value):
        return self.origin_y + value

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def delete(self, tag):
        pass

    def create_rectangle(self, *args, **kwargs):
        self.rectangles += 1
        self.boxes.append((args, kwargs))

    def create_text(self, *args, **kwargs):
        self.labels += 1
        self.texts.append((args, kwargs))

    def create_line(self, *args, **kwargs):
        self.lines.append((args, kwargs))


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

    def test_cell_borders_selection_headers_and_entry_align_after_scroll(self):
        grid = self.module.TableGrid.__new__(self.module.TableGrid)
        grid.canvas = CanvasStub(origin_x=160, origin_y=24, width=480, height=120)
        grid.model = TableModel("A\t\tC\tD\nE\tF\t\tH\nI\tJ\tK\tL")
        grid.font = types.SimpleNamespace(measure=lambda value: len(value) * 8)
        grid.selected = (0, 1)
        grid.selection.move_to(1, 2, extend=True)
        grid.header_height = grid.row_height = 24
        grid.gutter_width = 48
        grid.column_width = 160
        grid._draw_job = None
        grid._editor = None
        before = grid.model.to_text()
        grid._draw_visible()
        self.assertEqual(grid.model.to_text(), before)

        def matching(box, **options):
            return [style for coords, style in grid.canvas.boxes
                    if coords == box and all(style.get(key) == value
                                             for key, value in options.items())]

        blank_box = grid._cell_box(0, 1)
        adjacent_box = grid._cell_box(0, 2)
        self.assertEqual(blank_box[2], adjacent_box[0])
        self.assertTrue(matching(blank_box, fill=self.module.SELECTION_BACKGROUND,
                                 outline=self.module.GRID_LINE, width=2))
        active_box = grid._cell_box(1, 2)
        self.assertTrue(matching(active_box, fill=self.module.ACTIVE_BACKGROUND,
                                 outline=self.module.GRID_LINE, width=2))
        self.assertTrue(matching(active_box, outline=self.module.ACTIVE_LINE, width=3))
        self.assertTrue(any(style.get("outline") == self.module.SELECTION_LINE
                            for _, style in grid.canvas.boxes))
        self.assertTrue(matching((160, 48, 208, 72),
                                 fill=self.module.HEADER_SELECTED,
                                 outline=self.module.HEADER_LINE))
        self.assertTrue(matching((368, 24, 528, 48),
                                 fill=self.module.HEADER_SELECTED,
                                 outline=self.module.HEADER_LINE))
        self.assertIn("C", [style.get("text") for _, style in grid.canvas.texts])
        self.assertEqual(grid.canvas.lines[-2][0], (208, 24, 208, 144))
        self.assertEqual(grid.canvas.lines[-1][0], (160, 48, 640, 48))

        placed = []
        grid._editor = types.SimpleNamespace(place=lambda **options: placed.append(options))
        grid._position_editor()
        self.assertEqual(placed, [{"x": 208, "y": 24, "width": 160, "height": 24}])

        # A partly scrolled cell must not put its Entry over fixed headers.
        grid.canvas.origin_x = 200
        grid.canvas.origin_y = 35
        grid.selected = (1, 1)
        grid._position_editor()
        self.assertEqual(placed[-1], {"x": 48, "y": 24,
                                      "width": 120, "height": 13})

    def test_column_labels_and_empty_cell_hit_area(self):
        self.assertEqual([self.module.column_label(index) for index in
                          (0, 25, 26, 51, 52, 701)],
                         ["A", "Z", "AA", "AZ", "BA", "ZZ"])
        grid = self.module.TableGrid.__new__(self.module.TableGrid)
        grid.canvas = CanvasStub(origin_x=160, origin_y=0)
        grid.model = TableModel("A\t\tC")
        grid.selected = (0, 0)
        grid.header_height = grid.row_height = 24
        grid.gutter_width = 48
        grid.column_width = 160
        self.assertEqual(grid._hit_cell(types.SimpleNamespace(x=50, y=35)), (0, 1))
        self.assertEqual(grid._hit_cell(types.SimpleNamespace(x=210, y=35)), (0, 2))
        self.assertIsNone(grid._hit_cell(types.SimpleNamespace(x=20, y=35)))

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
