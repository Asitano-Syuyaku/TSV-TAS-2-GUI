"""Headless checks for visible-cell drawing and single-cell commits."""

import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe.editor.document import EditorDocument
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
        self.cursor = 0
        self.selected_range = None

    def delete(self, _start, _end):
        self.value = ""
        self.cursor = 0

    def insert(self, _index, value):
        self.value = value
        self.cursor = len(value)

    def get(self):
        return self.value

    def xview_moveto(self, _fraction):
        pass

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def place(self, **options):
        self.placement = options

    def place_forget(self):
        self.placement = None

    def focus_set(self):
        pass

    def select_range(self, _start, _end):
        self.selected_range = (_start, _end)

    def selection_clear(self):
        self.selected_range = None

    def icursor(self, index):
        self.cursor = len(self.value) if index == "end" else index

    def index(self, index):
        if index == "insert":
            return self.cursor
        if index == "sel.first" and self.selected_range is not None:
            return self.selected_range[0]
        if index == "sel.last" and self.selected_range is not None:
            return len(self.value) if self.selected_range[1] == "end" else self.selected_range[1]
        raise ValueError(index)

    def selection_present(self):
        return self.selected_range is not None

    def type_text(self, text):
        self.value = self.value[:self.cursor] + text + self.value[self.cursor:]
        self.cursor += len(text)

    def destroy(self):
        self.destroyed = True

    def winfo_exists(self):
        return not self.destroyed


class ListboxStub:
    def __init__(self, _parent, **_options):
        self.items = []
        self.bindings = {}
        self.selected = ()
        self.placement = None

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def delete(self, _start, _end):
        self.items.clear()

    def insert(self, _index, value):
        self.items.append(value)

    def selection_set(self, index):
        self.selected = (index,)

    def selection_clear(self, _start, _end):
        self.selected = ()

    def activate(self, _index):
        pass

    def see(self, _index):
        pass

    def curselection(self):
        return self.selected

    def place(self, **options):
        self.placement = options

    def place_forget(self):
        self.placement = None


class TableGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_tk = types.ModuleType("tkinter")
        fake_tk.Frame = type("FakeFrame", (), {"winfo_exists": lambda self: True})
        fake_tk.TclError = RuntimeError
        fake_tk.Listbox = ListboxStub
        with patch.dict(sys.modules, {"tkinter": fake_tk}):
            sys.modules.pop("python_to_exe.editor.grid", None)
            cls.module = importlib.import_module("python_to_exe.editor.grid")

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("python_to_exe.editor.grid", None)

    def test_a_to_g_guides_are_visual_only_with_initial_a_to_h_columns(self):
        grid = self.module.TableGrid.__new__(self.module.TableGrid)
        grid.canvas = CanvasStub(origin_y=0, width=800, height=240)
        grid.model = TableModel("")
        grid.font = types.SimpleNamespace(measure=lambda value: len(value) * 8)
        grid.selected = (0, 0)
        grid.header_height = grid.row_height = 24
        grid.gutter_width = 48
        grid.column_width = 160
        grid._draw_job = None
        grid._editor = None
        grid._scroll_region = None
        grid.on_select = lambda: None
        grid.after_idle = lambda callback: 1
        grid.labels = {"duration_header": "フレーム数", "button_header": "ボタン"}
        before = grid.model.to_text()
        grid._update_region()
        self.assertEqual(grid.display_column_count, 8)
        self.assertEqual(grid.model.to_text(), before)
        self.assertEqual([self.module.column_heading(index, grid.labels)
                          for index in range(8)],
                         ["A · フレーム数", "B · LS", "C · RS",
                          "D · ボタン", "E · ボタン", "F · ボタン", "G · ボタン", "H"])
        for _ in range(8):
            grid._move(0, 1)
        self.assertEqual(grid.selected, (0, 8))
        self.assertEqual(grid.display_column_count, 9)
        self.assertEqual(grid.model.to_text(), before)

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
        before = grid.model.to_text()
        classifier = self.module.classify_cell
        classified = []
        with patch.object(self.module, "classify_cell",
                          side_effect=lambda value, column: classified.append((value, column))
                          or classifier(value, column)):
            grid._draw_visible()
        self.assertEqual(grid.model.to_text(), before)
        self.assertLess(len(classified), 100)
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
                                 outline=self.module.GRID_LINE, width=self.module.LINE_WIDTHS["grid"]))
        active_box = grid._cell_box(1, 2)
        self.assertTrue(matching(active_box, fill=self.module.ACTIVE_BACKGROUND,
                                 outline=self.module.GRID_LINE, width=self.module.LINE_WIDTHS["grid"]))
        self.assertTrue(matching(active_box, outline=self.module.ACTIVE_LINE,
                                 width=self.module.LINE_WIDTHS["active"]))
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
        grid.canvas = types.SimpleNamespace(focus_set=lambda: None)
        grid._editor = types.SimpleNamespace(get=lambda: "日本語", place_forget=lambda: None)
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
        grid._entry_widget = None
        grid._completion = self.module.CompletionState()
        grid._popup = None
        grid._selection_axis = None
        grid._resize_column = None
        grid._resize_cursor = None
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

    def test_display_extent_persists_after_navigation_and_selection(self):
        grid, _, changes = self._navigation_grid("A\tB")
        original = grid.model.to_text()
        self.assertGreaterEqual(grid.display_column_count, 3)
        self.assertGreaterEqual(grid.display_row_count, 4)
        grid._move(19, 9)
        expanded = (grid.display_row_count, grid.display_column_count)
        region = grid.canvas.scrollregion
        grid._move(-19, -9)
        grid._click(types.SimpleNamespace(x=60, y=35, state=0))
        self.assertEqual(grid.selected, (0, 0))
        self.assertEqual((grid.display_row_count, grid.display_column_count), expanded)
        self.assertEqual(grid.canvas.scrollregion, region)
        self.assertEqual(grid._hit_target(types.SimpleNamespace(x=370, y=83)),
                         ("cell", (2, 2)))
        self.assertEqual(grid.model.to_text(), original)
        self.assertEqual(grid.model.column_count, 2)
        self.assertEqual(grid.model.row_count, 1)
        self.assertEqual(changes, [])

        with tempfile.TemporaryDirectory() as folder:
            document = EditorDocument()
            document.set_text(grid.model.to_text())
            path = Path(folder) / "virtual.tsv"
            document.save(path)
            self.assertEqual(path.read_bytes(), b"A\tB")

    def test_wide_initial_view_stops_at_h_but_navigation_paste_and_insert_can_extend(self):
        grid, _, changes = self._navigation_grid("")
        grid.font = types.SimpleNamespace(measure=lambda value: len(value) * 8)
        grid._columns = self.module.ColumnLayout(
            grid.column_width, default_widths=dict(enumerate(self.module.TABLE_COLUMN_WIDTHS)))
        grid.canvas.width = 2000
        grid._canvas_resized()
        self.assertEqual(grid.display_column_count, 8)
        self.module.TableGrid._draw_visible(grid)
        for column in range(8):
            self.assertTrue(any(box == grid._cell_box(0, column) for box, _ in grid.canvas.boxes))
        self.assertFalse(any(box == grid._cell_box(0, 8) for box, _ in grid.canvas.boxes))
        self.assertEqual(grid.model.to_text(), "")
        self.assertEqual(changes, [])

        grid._move(0, 8)
        self.assertEqual(grid.selected, (0, 8))
        self.assertEqual(grid.display_column_count, 9)
        self.assertEqual(grid.model.to_text(), "")
        grid._move(0, -8)
        self.assertEqual(grid.display_column_count, 9)  # Reached cells remain available.

        transformed = []
        grid.on_transform = lambda before, after: transformed.append((before, after)) or True
        grid.selected = (0, 7)
        self.assertTrue(grid.paste_text("H\tI\t"))
        self.assertEqual(grid.model.to_text(), "\t" * 7 + "H\tI\t")
        self.assertEqual(grid.model.column_count, 10)
        self.assertGreaterEqual(grid.display_column_count, 10)
        grid.selected = (0, 7)
        self.assertTrue(grid.insert_column_right())
        self.assertEqual(grid.model.to_text(), "\t" * 7 + "H\t\tI\t")
        self.assertEqual(grid.model.column_count, 11)
        self.assertEqual(len(transformed), 2)

    def test_new_document_and_resize_fill_viewport_without_serializing(self):
        grid, _, _ = self._navigation_grid("")
        grid.font = types.SimpleNamespace(measure=lambda value: len(value) * 8)
        self.assertGreaterEqual(grid.display_column_count, 3)
        self.assertGreaterEqual(grid.display_row_count, 4)
        self.module.TableGrid._draw_visible(grid)
        self.assertTrue(any(coords == grid._cell_box(2, 2)
                            for coords, _ in grid.canvas.boxes))
        self.assertEqual(grid.model.to_text(), "")
        grid.canvas.width = 950
        grid.canvas.height = 400
        grid._canvas_resized()
        large = (grid.display_row_count, grid.display_column_count)
        self.assertGreaterEqual(large[0], 16)
        self.assertGreaterEqual(large[1], 6)
        grid.canvas.width = 470
        grid.canvas.height = 120
        grid._canvas_resized()
        self.assertEqual((grid.display_row_count, grid.display_column_count), large)
        self.assertEqual(grid.model.to_text(), "")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "new.tsv"
            document = EditorDocument()
            document.save(path)
            self.assertEqual(path.read_bytes(), b"")

    def test_far_virtual_cell_writes_only_on_commit(self):
        grid, _, changes = self._navigation_grid("A\tB")
        transformations = []
        grid.on_transform = lambda before, after: transformations.append((before, after)) or True
        grid._move(19, 9)
        self.assertEqual(grid.model.to_text(), "A\tB")
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            grid.begin_edit(initial="猫")
            self.assertEqual(grid.model.to_text(), "A\tB")
            self.assertTrue(grid.commit_edit())
        self.assertEqual(grid.model.row_count, 20)
        self.assertEqual(grid.model.column_count, 10)
        self.assertEqual(grid.model.to_text(), "A\tB" + "\n" * 19 + "\t" * 9 + "猫")
        self.assertEqual(len(changes), 0)  # Virtual row uses the bulk change path.
        self.assertEqual(transformations, [("A\tB", grid.model.to_text())])
        grid._move(-19, -9)
        self.assertGreaterEqual(grid.display_row_count, 20)
        self.assertGreaterEqual(grid.display_column_count, 10)

    def test_header_boundary_drag_resizes_without_selecting_or_editing(self):
        grid, _, changes = self._navigation_grid("A\tB\tC")
        grid.on_change = lambda *_args: self.fail("Resize must not edit a cell")
        grid.on_transform = lambda *_args: self.fail("Resize must not enter Undo history")
        original = grid.model.to_text()
        boundary = grid.gutter_width + grid.columns.edge(1)
        grid._header_motion(types.SimpleNamespace(x=boundary, y=10))
        self.assertEqual(grid._resize_cursor, "sb_h_double_arrow")
        grid._click(types.SimpleNamespace(x=boundary, y=10, state=0))
        self.assertEqual(grid._resize_column, 0)
        self.assertIsNone(grid._selection_axis)
        self.assertEqual(grid.selected, (0, 0))
        grid._drag(types.SimpleNamespace(x=boundary + 50, y=10))
        self.assertEqual(grid.columns.width(0), 210)
        self.assertEqual(grid.columns.width(1), 160)
        self.assertEqual(grid._cell_box(0, 1)[0], boundary + 50)
        grid._release(types.SimpleNamespace(x=boundary + 50, y=10))
        self.assertIsNone(grid._resize_column)
        self.assertEqual(grid.model.to_text(), original)
        self.assertEqual(changes, [])

        grid._click(types.SimpleNamespace(x=80, y=10, state=0))
        self.assertEqual(grid._selection_axis, "column")
        self.assertEqual(grid.selected[1], 0)
        grid._click(types.SimpleNamespace(x=boundary + 50, y=10, state=0))
        grid._drag(types.SimpleNamespace(x=-500, y=10))
        self.assertEqual(grid.columns.width(0), 48)
        grid._release(types.SimpleNamespace(x=-500, y=10))
        self.assertEqual(grid.columns.width(1), 160)
        self.assertEqual(grid.model.to_text(), original)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "widths.tsv"
            source.write_text(original, encoding="utf-8")
            document = EditorDocument()
            document.open(source)
            self.assertFalse(document.modified)
            document.save()
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_resize_after_horizontal_scroll_keeps_hits_selection_and_entry_aligned(self):
        grid, _, _ = self._navigation_grid("A\tB\tC\tD\tE\tF")
        grid._move(0, 5)
        self.assertGreater(grid.canvas.origin_x, 0)
        boundary = grid.gutter_width + grid.columns.edge(5) - grid.canvas.origin_x
        self.assertEqual(grid._header_resize_target(
            types.SimpleNamespace(x=boundary, y=10)), 4)
        grid._click(types.SimpleNamespace(x=boundary, y=10, state=0))
        grid._drag(types.SimpleNamespace(x=boundary + 35, y=10))
        grid._release(types.SimpleNamespace(x=boundary + 35, y=10))
        self.assertEqual(grid.columns.width(4), 195)
        self.assertEqual(grid.columns.width(5), 160)
        x1, y1, x2, y2 = grid._cell_box(0, 5)
        center = (x1 + x2) / 2 - grid.canvas.origin_x
        self.assertEqual(grid._hit_cell(types.SimpleNamespace(x=center, y=35)), (0, 5))
        grid.selection.move_to(0, 4)
        grid.selection.move_to(0, 5, extend=True)
        grid.font = types.SimpleNamespace(measure=lambda value: len(value) * 8)
        self.module.TableGrid._draw_visible(grid)
        selection_box = (grid._cell_box(0, 4)[0] + 1, y1 + 1, x2 - 1, y2 - 1)
        self.assertTrue(any(coords == selection_box and
                            style.get("outline") == self.module.SELECTION_LINE
                            for coords, style in grid.canvas.boxes))
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            grid.begin_edit()
            self.assertEqual(grid._editor.placement["x"],
                             max(x1 - grid.canvas.origin_x, grid.gutter_width))
            self.assertEqual(grid._editor.placement["width"],
                             min(x2 - grid.canvas.origin_x, grid.canvas.width) -
                             max(x1 - grid.canvas.origin_x, grid.gutter_width))
            grid.cancel_edit()

    def test_column_width_survives_table_refresh_and_virtual_columns_use_default(self):
        grid, _, _ = self._navigation_grid("A\tB")
        self.assertTrue(grid.columns.set_width(0, 220))
        grid._update_region()
        grid.set_text("A\tB")  # Raw -> Table refresh uses the same TableGrid instance.
        self.assertEqual(grid.columns.width(0), 220)
        self.assertEqual(grid.columns.width(50), grid.column_width)
        self.assertEqual(grid.model.to_text(), "A\tB")
        grid._move(0, 50)
        self.assertEqual(grid.columns.width(50), grid.column_width)
        self.assertEqual(grid.model.to_text(), "A\tB")

    def test_autocomplete_popup_tracks_resized_entry(self):
        grid, _, _ = self._navigation_grid("A\tB")
        grid.canvas.width = 800
        grid.columns.set_width(0, 210)
        grid._canvas_resized()
        grid.selected = (0, 1)
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            grid.begin_edit(initial="l")
            x = grid._cell_box(0, 1)[0] - grid.canvas.origin_x
            self.assertEqual(grid._editor.placement["x"], x)
            self.assertEqual(grid._popup.placement["x"], x)
            self.assertEqual(grid._popup.placement["y"],
                             grid._editor.placement["y"] + grid._editor.placement["height"])
            grid.cancel_edit()

    def test_resized_grid_still_draws_only_visible_cells_of_ten_thousand_rows(self):
        grid, _, _ = self._navigation_grid("\n".join("1\ta\tb" for _ in range(10000)))
        grid.canvas.origin_y = 9000 * grid.row_height
        grid.font = types.SimpleNamespace(measure=lambda value: len(value) * 8)
        grid.columns.set_width(1, 230)
        grid.display_column_count = 500
        grid._update_region()
        before = grid.model.to_text()
        self.module.TableGrid._draw_visible(grid)
        self.assertLess(grid.canvas.rectangles, 100)
        self.assertEqual(grid.model.to_text(), before)

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
            self.assertFalse(editor.destroyed)
            self.assertEqual(grid.canvas.focus_count, 1)
            self.assertEqual(grid.selected, (0, 151))
            self.assertEqual(grid.model.column_count, 151)
            self.assertEqual(grid.model.to_text(), "A" + "\t" * 150 + "終わり")
            self.assertEqual(EntryStub.created, 1)
            self.assertLessEqual(len(pending), 1)  # Only one redraw.
            while pending:
                pending.pop(0)()
            self.assertFalse(editor.destroyed)
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
            self.assertEqual(grid.canvas.bindings["<F2>"](
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
            self.assertEqual(grid.canvas.bindings["<Shift-Return>"](
                types.SimpleNamespace()), "break")
            self.assertEqual(grid.selected, (0, 0))
            self.assertEqual(grid.canvas.bindings["<Return>"](
                types.SimpleNamespace()), "break")
            self.assertEqual(grid.selected, (1, 0))

            grid.begin_edit()
            up_editor = grid._editor
            up_editor.value = "鳥"
            self.assertEqual(up_editor.bindings["<Shift-Return>"](
                types.SimpleNamespace(widget=up_editor)), "break")
            self.assertEqual(grid.selected, (0, 0))
            self.assertEqual(grid.model.to_text(), "犬\t\n鳥\t")
            grid.canvas.bindings["<Tab>"](types.SimpleNamespace())
            grid.begin_edit()
            left_editor = grid._editor
            left_editor.value = "魚"
            self.assertEqual(left_editor.bindings["<Shift-Tab>"](
                types.SimpleNamespace(widget=left_editor)), "break")
            self.assertEqual(grid.selected, (0, 0))
            self.assertEqual(grid.model.to_text(), "犬\t魚\n鳥\t")
            self.assertEqual(len(changes), 4)
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
            self.assertEqual(EntryStub.created, 1)
            self.assertLessEqual(len(pending), 1)
            while pending:
                pending.pop(0)()
            self.assertIs(first, second)
            self.assertIs(first, third)
            self.assertIs(first, undo_editor)
            self.assertIs(first, redo_editor)
            self.assertIs(first, up_editor)
            self.assertIs(first, left_editor)
            self.assertFalse(first.destroyed)

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

    def test_direct_typing_replaces_cell_and_shortcuts_do_not_type(self):
        EntryStub.created = 0
        grid, pending, changes = self._navigation_grid("abc\tkeep\nbottom\tup")
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            for state, char in ((0x0004, "c"), (0x0008, "a"),
                                (0, "\t"), (0, "あ")):
                self.assertIsNone(grid._type_to_edit(types.SimpleNamespace(
                    state=state, char=char)))
            self.assertIsNone(grid._editor)
            self.assertEqual(EntryStub.created, 0)

            grid.selection.move_to(1, 1, extend=True)
            self.assertEqual(grid._type_to_edit(types.SimpleNamespace(
                state=0, char="l")), "break")
            editor = grid._editor
            self.assertEqual(editor.value, "l")
            self.assertEqual(grid.selection.bounds, (1, 1, 1, 1))
            editor.type_text("s(90)")
            self.assertEqual(editor.value, "ls(90)")
            editor.bindings["<KeyRelease>"](types.SimpleNamespace(widget=editor, keysym="parenright"))
            self.assertEqual(editor.bindings["<Tab>"](
                types.SimpleNamespace(widget=editor)), "break")
            self.assertEqual(grid.model.to_text(), "abc\tkeep\nbottom\tls(90)")
            self.assertEqual(changes, [("bottom\tup", "bottom\tls(90)")])
            self.assertIsNone(grid._editor)
            self.assertEqual(EntryStub.created, 1)

            for char in ("/", "$", "1", "(", ")"):
                grid.selected = (0, 0)
                self.assertEqual(grid._type_to_edit(types.SimpleNamespace(
                    state=0, char=char)), "break")
                self.assertIs(grid._editor, editor)
                self.assertEqual(editor.value, char)
                self.assertEqual(editor.bindings["<Escape>"](
                    types.SimpleNamespace(widget=editor)), "break")
                if grid._editor is not None:
                    self.assertEqual(editor.bindings["<Escape>"](
                        types.SimpleNamespace(widget=editor)), "break")
            self.assertEqual(grid.model.to_text(), "abc\tkeep\nbottom\tls(90)")
            self.assertEqual(EntryStub.created, 1)
            for _ in range(100):
                grid.begin_edit()
                self.assertIs(grid._editor, editor)
                grid.cancel_edit()
            self.assertEqual(EntryStub.created, 1)
            self.assertLessEqual(len(pending), 1)

    def test_click_f2_and_double_click_edit_existing_text_without_delayed_job(self):
        EntryStub.created = 0
        grid, _, _ = self._navigation_grid("abc\tkeep")
        grid.after = lambda *_args: self.fail("Single click must not schedule editing")
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            event = types.SimpleNamespace(x=60, y=35, state=0)
            grid._click(event)
            grid._release(event)
            self.assertIsNone(grid._editor)
            self.assertEqual(EntryStub.created, 0)

            self.assertEqual(grid.canvas.bindings["<F2>"](
                types.SimpleNamespace()), "break")
            editor = grid._editor
            self.assertEqual(editor.value, "abc")
            self.assertEqual(editor.cursor, 3)
            self.assertNotIn("<Left>", editor.bindings)
            self.assertNotIn("<Right>", editor.bindings)
            self.assertNotIn("<Home>", editor.bindings)
            self.assertNotIn("<End>", editor.bindings)
            self.assertEqual(editor.bindings["<Control-a>"](
                types.SimpleNamespace(widget=editor)), "break")
            self.assertEqual(editor.selected_range, (0, "end"))
            self.assertNotIn("<Control-c>", editor.bindings)
            self.assertNotIn("<Control-x>", editor.bindings)
            self.assertEqual(editor.bindings["<Escape>"](
                types.SimpleNamespace(widget=editor)), "break")

            grid._double_click(event)
            self.assertIs(grid._editor, editor)
            self.assertEqual(editor.value, "abc")
            self.assertEqual(editor.cursor, "@12")
            self.assertEqual(EntryStub.created, 1)

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
                    self.assertFalse(editor.destroyed)

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
        grid._update_region = lambda: None
        grid._ensure_visible = lambda: None
        grid._schedule_draw = lambda: None
        grid.on_select = lambda: None
        grid.begin_edit = lambda: None
        grid._click(types.SimpleNamespace(x=20, y=40))
        self.assertEqual(grid._selection_bounds(), (0, 0, 0, 3))
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
        self.assertEqual(pending, [])
        self.assertEqual(grid.model.to_text(), "猫\t犬\n鳥\t魚")
        self.assertEqual(len(grid.changes), 1)

    def test_scrolled_headers_select_whole_rows_and_columns(self):
        grid, _ = self._working_grid("A\tB\tC\nD\tE\tF\nG\tH\tI")
        grid.canvas = CanvasStub(origin_x=160, origin_y=24)
        grid.gutter_width = 48
        grid.header_height = grid.row_height = 24
        grid.column_width = 160
        grid._click(types.SimpleNamespace(x=20, y=40, state=0))
        self.assertEqual(grid._selection_bounds(), (1, 1, 0, 2))
        self.assertEqual(grid.selected, (1, 1))
        grid._click(types.SimpleNamespace(x=20, y=64, state=1))
        self.assertEqual(grid._selection_bounds(), (1, 2, 0, 2))
        grid._click(types.SimpleNamespace(x=60, y=10, state=0))
        self.assertEqual(grid._selection_bounds(), (0, 2, 1, 1))
        self.assertEqual(grid.selected, (1, 1))
        grid._click(types.SimpleNamespace(x=220, y=10, state=1))
        self.assertEqual(grid._selection_bounds(), (0, 2, 1, 2))

    def test_context_menus_select_target_and_expose_actions(self):
        class MenuStub:
            def __init__(self, *_args, **_kwargs):
                self.items = []
                self.popup = None

            def add_command(self, **options):
                self.items.append(options)

            def tk_popup(self, x, y):
                self.popup = x, y

            def grab_release(self):
                pass

        grid, _ = self._working_grid("A\tB\nC\tD")
        grid.canvas = CanvasStub(origin_y=0)
        grid.gutter_width = 48
        grid.header_height = grid.row_height = 24
        grid.column_width = 160
        keys = ("insert_row_above", "insert_row_below", "duplicate_row",
                "delete_row", "insert_column_left", "insert_column_right",
                "delete_column", "cut", "copy", "paste", "clear_cells")
        with patch.object(self.module.tk, "Menu", MenuStub, create=True):
            grid._build_context_menus({key: key for key in keys})
        self.assertEqual(len(grid._context_menus["row"].items), 7)
        self.assertEqual(len(grid._context_menus["column"].items), 6)
        self.assertEqual(len(grid._context_menus["cell"].items), 11)
        grid._right_click(types.SimpleNamespace(x=20, y=40, x_root=90, y_root=100))
        self.assertEqual(grid._selection_bounds(), (0, 0, 0, 1))
        self.assertEqual(grid._context_menus["row"].popup, (90, 100))
        grid._right_click(types.SimpleNamespace(x=220, y=10, x_root=91, y_root=101))
        self.assertEqual(grid._selection_bounds(), (0, 1, 1, 1))
        self.assertEqual(grid._context_menus["column"].popup, (91, 101))
        grid._right_click(types.SimpleNamespace(x=60, y=40, x_root=92, y_root=102))
        self.assertEqual(grid._selection_bounds(), (0, 0, 0, 0))
        self.assertEqual(grid._context_menus["cell"].popup, (92, 102))

    def test_virtual_row_navigation_and_first_edit(self):
        grid, pending, changes = self._navigation_grid("A\nB")
        transformed = []
        grid.on_transform = lambda old, new: transformed.append((old, new)) or True
        for _ in range(52):
            grid.canvas.bindings["<Return>"](types.SimpleNamespace())
        self.assertEqual(grid.selected, (52, 0))
        self.assertEqual(grid.model.to_text(), "A\nB")
        self.assertEqual(grid.model.row_count, 2)
        self.assertEqual(grid.model.column_count, 1)
        self.assertEqual(len(pending), 1)
        self.assertGreater(grid.canvas.scrollregion[3], grid.canvas.height)
        grid._move(-1, 0)
        grid._move(1, 0)
        self.assertEqual(grid.model.to_text(), "A\nB")
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            grid.begin_edit()
            grid._editor.value = "猫"
            self.assertTrue(grid.commit_edit())
        self.assertEqual(grid.model.to_text(), "A\nB" + "\n" * 51 + "猫")
        self.assertEqual(grid.model.row_count, 53)
        self.assertEqual(len(transformed), 1)
        self.assertEqual(transformed[0][0], "A\nB")
        self.assertEqual(changes, [])

    def test_enter_burst_and_direct_vertical_input_reuse_entry(self):
        grid, pending, _ = self._navigation_grid("A")
        grid.on_transform = lambda old, new: True
        for _ in range(160):
            grid.canvas.bindings["<Return>"](types.SimpleNamespace())
        self.assertEqual(grid.selected, (160, 0))
        self.assertEqual(grid.model.to_text(), "A")
        self.assertEqual(len(pending), 1)
        grid.selected = (0, 0)
        EntryStub.created = 0
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            for value in "123":
                self.assertEqual(grid._type_to_edit(types.SimpleNamespace(char=value, state=0)),
                                 "break")
                editor = grid._editor
                self.assertEqual(editor.value, value)
                self.assertEqual(editor.bindings["<Return>"](
                    types.SimpleNamespace(widget=editor)), "break")
                self.assertIsNone(grid._editor)
        self.assertEqual(grid.model.to_text(), "1\n2\n3")
        self.assertEqual(grid.selected, (3, 0))
        self.assertEqual(EntryStub.created, 1)

    def test_structural_actions_and_multi_header_deletion(self):
        original = "A\tB\t\nC\tD\t\nE\tF\t"
        cases = (
            ("insert_row_above", (1, 1), "A\tB\t\n\nC\tD\t\nE\tF\t"),
            ("insert_row_below", (1, 1), "A\tB\t\nC\tD\t\n\nE\tF\t"),
            ("duplicate_row", (1, 1), "A\tB\t\nC\tD\t\nC\tD\t\nE\tF\t"),
            ("delete_row", (1, 1), "A\tB\t\nE\tF\t"),
            ("insert_column_left", (1, 1), "A\t\tB\t\nC\t\tD\t\nE\t\tF\t"),
            ("insert_column_right", (1, 1), "A\tB\t\t\nC\tD\t\t\nE\tF\t\t"),
            ("delete_column", (1, 1), "A\t\nC\t\nE\t"),
        )
        for action, cell, expected in cases:
            with self.subTest(action=action):
                grid, _ = self._working_grid(original)
                grid.selected = cell
                self.assertTrue(getattr(grid, action)())
                self.assertEqual(grid.model.to_text(), expected)
                self.assertEqual(len(grid.changes), 1)
        grid, _ = self._working_grid(original)
        grid._selection_axis = "row"
        grid.selection.anchor = (0, 0)
        grid.selection.active = (1, 0)
        self.assertTrue(grid.delete_row())
        self.assertEqual(grid.model.to_text(), "E\tF\t")
        grid, _ = self._working_grid(original)
        grid._selection_axis = "column"
        grid.selection.anchor = (0, 1)
        grid.selection.active = (0, 2)
        self.assertTrue(grid.delete_column())
        self.assertEqual(grid.model.to_text(), "A\nC\nE")

    def test_ten_thousand_row_header_selection_stays_visible_only(self):
        grid = self.module.TableGrid.__new__(self.module.TableGrid)
        grid.canvas = CanvasStub(origin_y=9000 * 24)
        grid.model = TableModel("\n".join(f"{i}\ta\tb" for i in range(10000)))
        grid.font = types.SimpleNamespace(measure=lambda value: len(value) * 8)
        grid.selected = (9000, 0)
        grid.header_height = grid.row_height = 24
        grid.gutter_width = 48
        grid.column_width = 160
        grid._draw_job = None
        grid._editor = None
        grid._scroll_region = None
        grid._ensure_visible = lambda: None
        grid._schedule_draw = lambda: None
        grid.on_select = lambda: None
        grid._click(types.SimpleNamespace(x=20, y=40, state=0))
        self.assertEqual(grid._selection_bounds()[:2], (9000, 9000))
        grid._draw_visible()
        self.assertLess(grid.canvas.rectangles, 200)  # Seven guide columns stay visible.
        grid.canvas.rectangles = 0
        grid._click(types.SimpleNamespace(x=55, y=10, state=0))
        self.assertEqual(grid._selection_bounds(), (0, 9999, 0, 0))
        grid._draw_visible()
        self.assertLess(grid.canvas.rectangles, 200)

    def test_autocomplete_popup_keyboard_mouse_and_escape(self):
        grid, _, _ = self._navigation_grid("old")
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            self.assertEqual(grid._type_to_edit(types.SimpleNamespace(char="l", state=0)),
                             "break")
            editor = grid._editor
            self.assertTrue(grid._completion.open)
            self.assertIsNotNone(grid._popup.placement)
            self.assertEqual(editor.bindings["<Down>"](
                types.SimpleNamespace(widget=editor)), "break")
            self.assertEqual(editor.bindings["<Down>"](
                types.SimpleNamespace(widget=editor)), "break")
            self.assertEqual(grid._completion.current.text, "ls(0)")
            self.assertEqual(editor.bindings["<Up>"](
                types.SimpleNamespace(widget=editor)), "break")
            self.assertEqual(grid._completion.current.text, "ls")
            editor.bindings["<Down>"](types.SimpleNamespace(widget=editor))
            self.assertEqual(editor.bindings["<Tab>"](
                types.SimpleNamespace(widget=editor)), "break")
            self.assertIs(grid._editor, editor)
            self.assertFalse(grid._completion.open)
            self.assertEqual(editor.value, "ls(0)")
            self.assertEqual(editor.selected_range, (3, 4))
            self.assertEqual(grid.selected, (0, 0))
            self.assertEqual(editor.bindings["<Tab>"](
                types.SimpleNamespace(widget=editor)), "break")
            self.assertIsNone(grid._editor)
            self.assertEqual(grid.selected, (0, 1))
            self.assertEqual(grid.model.to_text(), "ls(0)")

            grid.selected = (0, 0)
            grid._type_to_edit(types.SimpleNamespace(char="/", state=0))
            editor = grid._editor
            self.assertEqual(len(grid._completion.items), 8)
            grid._popup.selection_clear(0, "end")
            grid._popup.selection_set(4)
            grid._popup.bindings["<ButtonRelease-1>"](types.SimpleNamespace())
            self.assertEqual(editor.value, "/pause")
            self.assertIs(grid._editor, editor)
            self.assertFalse(grid._completion.open)
            editor.bindings["<Return>"](types.SimpleNamespace(widget=editor))
            self.assertEqual(grid.selected, (1, 0))
            self.assertEqual(grid.model.to_text(), "/pause")

            grid.selected = (0, 0)
            grid._type_to_edit(types.SimpleNamespace(char="/", state=0))
            self.assertTrue(grid._completion.open)
            self.assertEqual(editor.bindings["<Escape>"](
                types.SimpleNamespace(widget=editor)), "break")
            self.assertIs(grid._editor, editor)
            self.assertFalse(grid._completion.open)
            editor.bindings["<KeyRelease>"](
                types.SimpleNamespace(widget=editor, keysym="c", state=0x0004))
            self.assertFalse(grid._completion.open)
            self.assertEqual(editor.bindings["<Escape>"](
                types.SimpleNamespace(widget=editor)), "break")
            self.assertIsNone(grid._editor)

    def test_popup_enter_accepts_without_navigation(self):
        grid, _, _ = self._navigation_grid("old")
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            grid._type_to_edit(types.SimpleNamespace(char="/", state=0))
            editor = grid._editor
            for _ in range(4):
                editor.bindings["<Down>"](types.SimpleNamespace(widget=editor))
            self.assertEqual(grid._completion.current.text, "/pause")
            self.assertEqual(editor.bindings["<Return>"](
                types.SimpleNamespace(widget=editor)), "break")
            self.assertEqual(editor.value, "/pause")
            self.assertIs(grid._editor, editor)
            self.assertEqual(grid.selected, (0, 0))
            self.assertEqual(grid.model.to_text(), "old")
            self.assertEqual(editor.bindings["<Return>"](
                types.SimpleNamespace(widget=editor)), "break")
            self.assertEqual(grid.selected, (1, 0))
            self.assertEqual(grid.model.to_text(), "/pause")

    def test_palette_starts_edit_and_inserts_at_caret(self):
        from python_to_exe.editor.tsv_syntax import CANDIDATES

        grid, _, _ = self._navigation_grid("old\tkeep")
        stick = next(item for item in CANDIDATES if item.label == "ls(angle)")
        button = next(item for item in CANDIDATES if item.text == "a")
        grid.selected = (0, 1)
        with patch.object(self.module.tk, "Entry", EntryStub, create=True):
            grid.insert_candidate(stick)
            editor = grid._editor
            self.assertEqual(grid.selected, (0, 1))
            self.assertEqual(editor.value, "ls(0)")
            self.assertEqual(editor.selected_range, (3, 4))
            self.assertEqual(grid.model.to_text(), "old\tkeep")
            grid.insert_candidate(button)
            self.assertEqual(editor.value, "ls(a)")
            self.assertTrue(grid.commit_edit())
            self.assertEqual(grid.model.to_text(), "old\tls(a)")
            grid.begin_edit()
            editor.icursor(2)
            grid.insert_candidate(button)
            self.assertEqual(editor.value, "lsa(a)")
            self.assertIs(grid._editor, editor)

    def test_palette_only_marks_document_modified_after_cell_commit(self):
        from python_to_exe.editor.tsv_syntax import CANDIDATES

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "palette.tsv"
            source.write_text("A\tB", encoding="utf-8")
            document = EditorDocument()
            document.open(source)
            grid, _, _ = self._navigation_grid(document.text)
            grid.selected = (0, 1)
            grid.on_change = lambda _row, _old, new: document.set_text(new) or True
            button = next(item for item in CANDIDATES if item.text == "a")
            with patch.object(self.module.tk, "Entry", EntryStub, create=True):
                grid.insert_candidate(button)
                self.assertEqual(grid.selected, (0, 1))
                self.assertFalse(document.modified)
                self.assertTrue(grid.commit_edit())
            self.assertTrue(document.modified)
            self.assertEqual(document.text, "A\ta")
            document.save()
            self.assertEqual(source.read_bytes(), b"A\ta")

    def test_advanced_palette_reuses_text_and_placeholder_insertion(self):
        from python_to_exe.editor.tsv_syntax import CANDIDATES, PALETTE_PAGES

        for candidate in (item for item in CANDIDATES if item.category in PALETTE_PAGES[1]):
            with self.subTest(candidate=candidate.label):
                grid, _, _ = self._navigation_grid("1\told\tkeep")
                grid.selected = (0, 1)
                with patch.object(self.module.tk, "Entry", EntryStub, create=True):
                    grid.insert_candidate(candidate)
                    editor = grid._editor
                    self.assertEqual(editor.value, candidate.text)
                    self.assertEqual(editor.selected_range, candidate.select)
                    self.assertEqual(grid.selected, (0, 1))
                    self.assertEqual(grid.model.to_text(), "1\told\tkeep")
                    self.assertTrue(grid.commit_edit())
                    self.assertEqual(grid.model.to_text(), "1\t" + candidate.text + "\tkeep")
                    grid.begin_edit()
                    self.assertIs(grid._editor, editor)
                    editor.delete(0, "end")
                    editor.insert(0, "ab")
                    editor.icursor(1)
                    grid.insert_candidate(candidate)
                    self.assertEqual(editor.value, "a" + candidate.text + "b")
                    self.assertEqual(editor.selected_range,
                                     tuple(1 + value for value in candidate.select)
                                     if candidate.select else None)


if __name__ == "__main__":
    unittest.main()
