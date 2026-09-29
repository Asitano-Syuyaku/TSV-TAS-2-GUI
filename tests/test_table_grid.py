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
        self.scrollregion = (0, 0, width, height)
        self.horizontal_moves = 0
        self.focus_count = 0
        self.region_updates = 0
        self.bindings = {}

    def canvasx(self, value):
        return self.origin_x + value

    def canvasy(self, value):
        return self.origin_y + value

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def configure(self, **options):
        self.scrollregion = options.get("scrollregion", self.scrollregion)
        if "scrollregion" in options:
            self.region_updates += 1

    def focus_set(self):
        self.focus_count += 1

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def xview_moveto(self, fraction):
        extent = self.scrollregion[2]
        self.origin_x = max(0, min(extent - self.width, fraction * extent))
        self.horizontal_moves += 1

    def yview_moveto(self, fraction):
        extent = self.scrollregion[3]
        self.origin_y = max(0, min(extent - self.height, fraction * extent))

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


class EntryStub:
    created = 0

    def __init__(self, _parent, **_options):
        type(self).created += 1
        self.value = ""
        self.destroyed = False
        self.bindings = {}
        self.placement = None

    def insert(self, _index, value):
        self.value = value

    def get(self):
        return self.value

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def place(self, **options):
        self.placement = options

    def place_forget(self):
        self.placement = None

    def focus_set(self):
        pass

    def select_range(self, _start, _end):
        pass

    def destroy(self):
        self.destroyed = True

    def winfo_exists(self):
        return not self.destroyed


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
        grid.begin_edit = lambda: self.fail("Navigation must not create an Entry")
        grid.on_select = lambda: None
        self.assertEqual(grid._move(0, 1), "break")
        self.assertEqual(grid.selected, (0, 1))
        self.assertEqual(grid._move(1, 0), "break")
        self.assertEqual(grid.selected, (1, 1))
        self.assertEqual(grid._move(0, -1), "break")
        self.assertEqual(grid.selected, (1, 0))

    def _navigation_grid(self, text="A"):
        grid = self.module.TableGrid.__new__(self.module.TableGrid)
        grid.canvas = CanvasStub(origin_y=0, width=470, height=120)
        grid.model = TableModel(text)
        grid.selected = (0, 0)
        grid.gutter_width = 48
        grid.header_height = grid.row_height = 24
        grid.column_width = 160
        grid.font = None
        grid._editor = None
        grid._edit_job = None
        grid._draw_job = None
        grid._scroll_region = None
        grid.on_select = lambda: None
        changes = []
        grid.on_change = lambda row, old, new: changes.append((old, new)) or True
        pending = []
        grid.after_idle = lambda callback: pending.append(callback) or len(pending)
        grid._draw_visible = lambda: setattr(grid, "_draw_job", None)
        grid._update_region()
        grid._bind_canvas_navigation()
        return grid, pending, changes

    def test_burst_tab_moves_virtual_active_cell_without_creating_entries(self):
        EntryStub.created = 0
        grid, pending, changes = self._navigation_grid()

        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            for index in range(150):
                self.assertEqual(grid.canvas.bindings["<Tab>"](types.SimpleNamespace()),
                                 "break")
                self.assertEqual(grid.selected, (0, index + 1))
            self.assertEqual(EntryStub.created, 0)
            self.assertEqual(grid.model.to_text(), "A")
            self.assertEqual(grid.model.column_count, 1)
            self.assertEqual(len(changes), 0)
            self.assertEqual(len(pending), 1)  # All redraws share one idle job.
            self.assertGreater(grid.canvas.horizontal_moves, 0)
            self.assertEqual(grid.canvas.scrollregion[2],
                             grid.gutter_width + 151 * grid.column_width)
            active_x = grid._cell_box(*grid.selected)[0] - grid.canvas.origin_x
            self.assertGreaterEqual(active_x, grid.gutter_width)
            self.assertLessEqual(active_x + grid.column_width, grid.canvas.width)
            pending.pop(0)()
            grid.font = types.SimpleNamespace(measure=lambda value: len(value) * 8)
            self.module.TableGrid._draw_visible(grid)
            self.assertTrue(any(
                coords == grid._cell_box(0, 150) and style.get("outline") == self.module.ACTIVE_LINE
                for coords, style in grid.canvas.boxes))
            self.assertLess(grid.canvas.rectangles, 30)

            grid.begin_edit()
            self.assertEqual(EntryStub.created, 1)
            editor = grid._editor
            self.assertEqual(editor.placement["x"],
                             max(grid._cell_box(0, 150)[0] - grid.canvas.origin_x,
                                 grid.gutter_width))
            editor.value = "終わり"
            self.assertEqual(editor.bindings["<Tab>"](types.SimpleNamespace(widget=editor)),
                             "break")
            self.assertIsNone(grid._editor)
            self.assertFalse(editor.destroyed)  # No destroy during its key event.
            self.assertEqual(grid.canvas.focus_count, 1)
            self.assertEqual(grid.selected, (0, 151))
            self.assertEqual(grid.model.column_count, 151)
            self.assertEqual(grid.model.to_text(), "A" + "\t" * 150 + "終わり")
            self.assertEqual(EntryStub.created, 1)
            self.assertLessEqual(len(pending), 2)  # One cleanup, one redraw.
            while pending:
                pending.pop(0)()
            self.assertTrue(editor.destroyed)
            self.assertEqual(len(changes), 1)

            self.assertEqual(grid.canvas.bindings["<Shift-Tab>"](
                types.SimpleNamespace()), "break")
            self.assertEqual(grid.selected, (0, 150))
            self.assertEqual(grid.canvas.bindings["<Tab>"](types.SimpleNamespace()),
                             "break")
            self.assertEqual(grid.selected, (0, 151))
            self.assertEqual(EntryStub.created, 1)

    def test_entry_commit_tab_enter_escape_and_canvas_navigation(self):
        EntryStub.created = 0
        grid, pending, changes = self._navigation_grid("A\t\nB\t")
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            self.assertEqual(grid.canvas.bindings["<Return>"](
                types.SimpleNamespace()), "break")
            first = grid._editor
            first.value = "猫"
            self.assertEqual(first.bindings["<Tab>"](types.SimpleNamespace(widget=first)),
                             "break")
            self.assertIsNone(grid._editor)
            self.assertEqual(grid.selected, (0, 1))
            self.assertEqual(grid.model.to_text(), "猫\t\nB\t")
            self.assertFalse(first.destroyed)
            queued = len(pending)
            for _ in range(100):
                self.assertEqual(first.bindings["<Tab>"](
                    types.SimpleNamespace(widget=first)), "break")
            self.assertEqual(len(pending), queued)
            self.assertEqual(grid.selected, (0, 1))

            self.assertEqual(grid._move(0, -1), "break")
            self.assertEqual(grid.selected, (0, 0))
            self.assertEqual(grid._move(0, 1, extend=True), "break")
            self.assertEqual(grid.selection.bounds, (0, 0, 0, 1))
            self.assertEqual(grid._move(0, -1), "break")
            self.assertEqual(grid.selection.bounds, (0, 0, 0, 0))
            self.assertEqual(EntryStub.created, 1)

            grid.begin_edit()
            second = grid._editor
            second.value = "犬"
            self.assertEqual(second.bindings["<Return>"](
                types.SimpleNamespace(widget=second)), "break")
            self.assertIsNone(grid._editor)
            self.assertEqual(grid.selected, (1, 0))
            self.assertEqual(grid.model.to_text(), "犬\t\nB\t")

            grid.begin_edit()
            third = grid._editor
            third.value = "discarded"
            self.assertEqual(third.bindings["<Escape>"](
                types.SimpleNamespace(widget=third)), "break")
            self.assertIsNone(grid._editor)
            self.assertEqual(grid.model.to_text(), "犬\t\nB\t")
            self.assertEqual(len(changes), 2)
            history = []
            grid.on_undo = lambda: history.append("undo")
            grid.on_redo = lambda: history.append("redo")
            grid.begin_edit()
            undo_editor = grid._editor
            self.assertEqual(undo_editor.bindings["<Control-z>"](
                types.SimpleNamespace(widget=undo_editor)), "break")
            grid.begin_edit()
            redo_editor = grid._editor
            self.assertEqual(redo_editor.bindings["<Control-y>"](
                types.SimpleNamespace(widget=redo_editor)), "break")
            self.assertEqual(history, ["undo", "redo"])
            self.assertIsNone(grid._editor)
            self.assertEqual(EntryStub.created, 5)
            self.assertLessEqual(len(pending), 6)  # Cleanup per edit, one redraw.
            while pending:
                pending.pop(0)()
            self.assertTrue(first.destroyed)
            self.assertTrue(second.destroyed)
            self.assertTrue(third.destroyed)
            self.assertTrue(undo_editor.destroyed)
            self.assertTrue(redo_editor.destroyed)

    def test_scroll_region_is_not_reconfigured_within_existing_columns(self):
        grid, pending, _ = self._navigation_grid("\t".join("x" for _ in range(10)))
        self.assertEqual(grid.canvas.region_updates, 1)
        self.assertEqual(grid.canvas.bindings["<Tab>"](types.SimpleNamespace()), "break")
        self.assertEqual(grid.canvas.horizontal_moves, 0)
        for _ in range(8):
            grid.canvas.bindings["<Tab>"](types.SimpleNamespace())
        self.assertEqual(grid.selected, (0, 9))
        self.assertEqual(grid.canvas.region_updates, 1)
        self.assertGreater(grid.canvas.horizontal_moves, 0)
        self.assertEqual(len(pending), 1)

    def test_empty_virtual_edit_then_tab_does_not_add_trailing_tabs(self):
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            for text in ("A", "A\t"):
                with self.subTest(text=text):
                    grid, pending, changes = self._navigation_grid(text)
                    column_count = grid.model.column_count
                    for _ in range(column_count):
                        grid.canvas.bindings["<Tab>"](types.SimpleNamespace())
                    grid.begin_edit()
                    editor = grid._editor
                    self.assertEqual(editor.bindings["<Tab>"](
                        types.SimpleNamespace(widget=editor)), "break")
                    self.assertEqual(grid.selected, (0, column_count + 1))
                    self.assertEqual(grid.model.column_count, column_count)
                    self.assertEqual(grid.model.to_text(), text)
                    self.assertEqual(changes, [])
                    while pending:
                        pending.pop(0)()
                    self.assertTrue(editor.destroyed)

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
        pending = []
        grid.canvas = types.SimpleNamespace(focus_set=lambda: None)
        grid.after_idle = lambda callback: pending.append(callback)
        grid._editor = types.SimpleNamespace(get=lambda: "old", destroy=lambda: None,
                                             place_forget=lambda: None,
                                             winfo_exists=lambda: True,
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
        self.assertIsNone(grid._editor)
        pending.pop(0)()
        self.assertEqual(grid.model.to_text(), "猫\t犬\n鳥\t魚")
        self.assertEqual(len(grid.changes), 1)


if __name__ == "__main__":
    unittest.main()
