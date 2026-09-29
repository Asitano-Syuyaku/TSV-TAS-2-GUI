"""Canvas table that draws visible TSV cells and edits one cell at a time."""

import tkinter as tk

from .column_layout import ColumnLayout
from .table_model import CellSelection, TableModel, visible_span
from .tsv_syntax import (CompletionState, candidates_for, classify_cell,
                         completion_span, insert_template)


CANVAS_BACKGROUND = "#f2f5f9"
CELL_BACKGROUND = "#ffffff"
GRID_LINE = "#8d9aab"
HEADER_BACKGROUND = "#e4ebf3"
HEADER_SELECTED = "#c9d9ec"
HEADER_LINE = "#65768b"
SELECTION_BACKGROUND = "#c9e0fb"
SELECTION_LINE = "#4e86bf"
ACTIVE_BACKGROUND = "#a9d0fb"
ACTIVE_LINE = "#075ca8"
SYNTAX_COLORS = {"duration": "#295fa3", "command": "#8741a8",
                 "comment": "#53805a", "variable": "#9a621f", "input": "#234a84"}


def column_label(index):
    """Spreadsheet-style column heading, starting at A."""
    label = ""
    number = index + 1
    while number:
        number, letter = divmod(number - 1, 26)
        label = chr(65 + letter) + label
    return label


class TableGrid(tk.Frame):
    def __init__(self, master, font, on_change, on_transform, on_select,
                 on_undo, on_redo, labels=None):
        super().__init__(master)
        self.font = font
        self.on_change = on_change
        self.on_transform = on_transform
        self.on_select = on_select
        self.on_undo = on_undo
        self.on_redo = on_redo
        self.row_height = max(font.metrics("linespace") + 8, 24)
        self.column_width = max(font.measure("0" * 18) + 12, 160)
        self._columns = ColumnLayout(self.column_width)
        self.header_height = self.row_height
        self.gutter_width = max(font.measure("00000") + 12, 48)
        self.model = TableModel("")
        self.selection = CellSelection()
        self._editor = None
        self._entry_widget = None
        self._draw_job = None
        self._scroll_region = None
        self.display_row_count = 0
        self.display_column_count = 0
        self._drag_ready = False
        self._selection_axis = None
        self._drag_axis = None
        self._resize_column = None
        self._resize_cursor = None
        self._completion = CompletionState()
        self._popup = None

        self.canvas = tk.Canvas(self, background=CANVAS_BACKGROUND, highlightthickness=0,
                                takefocus=True)
        vertical = tk.Scrollbar(self, orient="vertical", command=self._scroll_y)
        horizontal = tk.Scrollbar(self, orient="horizontal", command=self._scroll_x)
        self.canvas.configure(
            yscrollcommand=lambda first, last: self._on_view(vertical, first, last),
            xscrollcommand=lambda first, last: self._on_view(horizontal, first, last))
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.canvas.bind("<Configure>", self._canvas_resized)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-Button-1>", self._double_click)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Motion>", self._header_motion)
        self.canvas.bind("<Button-3>", self._right_click)
        self.canvas.bind("<KeyPress>", self._type_to_edit)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda event: self._wheel_units(-1))
        self.canvas.bind("<Button-5>", lambda event: self._wheel_units(1))
        self._bind_canvas_navigation()
        self.canvas.bind("<Delete>", lambda event: self._key_action(self.clear_selection))
        self.canvas.bind("<BackSpace>", lambda event: self._key_action(self.clear_selection))
        self._bind_clipboard(self.canvas)
        self._bind_history(self.canvas)
        if labels is not None:
            self._build_context_menus(labels)
        self._update_region()

    def _build_context_menus(self, labels):
        actions = {
            "row": ("insert_row_above", "insert_row_below", "duplicate_row",
                    "delete_row", "cut", "copy", "paste"),
            "column": ("insert_column_left", "insert_column_right",
                       "delete_column", "cut", "copy", "paste"),
            "cell": ("cut", "copy", "paste", "clear_cells",
                     "insert_row_above", "insert_row_below", "duplicate_row",
                     "delete_row", "insert_column_left", "insert_column_right",
                     "delete_column"),
        }
        commands = {"cut": self.cut_selection, "copy": self.copy_selection,
                    "paste": self.paste_clipboard, "clear_cells": self.clear_selection}
        self._context_menus = {}
        for kind, entries in actions.items():
            menu = tk.Menu(self, tearoff=False)
            for key in entries:
                command = commands[key] if key in commands else getattr(self, key)
                menu.add_command(label=labels[key], command=command)
            self._context_menus[kind] = menu

    def _bind_canvas_navigation(self):
        for key, delta in (("Up", (-1, 0)), ("Down", (1, 0)),
                           ("Left", (0, -1)), ("Right", (0, 1)),
                           ("Tab", (0, 1)),
                           ("Shift-Tab", (0, -1))):
            self.canvas.bind(f"<{key}>", lambda event, move=delta: self._move(*move))
        self.canvas.bind("<Return>", lambda event: self._move(1, 0))
        self.canvas.bind("<F2>", self._start_edit)
        self.canvas.bind("<Shift-Return>", lambda event: self._move(-1, 0))
        for key, delta in (("Up", (-1, 0)), ("Down", (1, 0)),
                           ("Left", (0, -1)), ("Right", (0, 1))):
            self.canvas.bind(f"<Shift-{key}>",
                             lambda event, move=delta: self._move(*move, extend=True))

    @property
    def selected(self):
        return self.selection.active

    @selected.setter
    def selected(self, cell):
        if not hasattr(self, "selection"):
            self.selection = CellSelection(cell)
        else:
            self.selection.move_to(*cell)

    def _selection_bounds(self):
        top, bottom, left, right = self.selection.bounds
        axis = getattr(self, "_selection_axis", None)
        if axis == "row":
            return top, bottom, 0, max(self.model.column_count - 1, right)
        if axis == "column":
            return 0, max(self.model.row_count - 1, bottom), left, right
        return top, bottom, left, right

    @staticmethod
    def _key_action(action):
        action()
        return "break"

    def _bind_clipboard(self, widget):
        for sequence, action in (("<Control-c>", self.copy_selection),
                                 ("<Control-x>", self.cut_selection),
                                 ("<Control-v>", self.paste_clipboard)):
            widget.bind(sequence, lambda event, command=action: self._key_action(command))

    def _bind_history(self, widget):
        widget.bind("<Control-z>", lambda event: self._history(self.on_undo))
        widget.bind("<Control-y>", lambda event: self._history(self.on_redo))

    @staticmethod
    def _history(action):
        action()
        return "break"

    def set_text(self, text):
        if self._editor is not None:
            raise RuntimeError("Commit the current cell before refreshing the table")
        self.model = TableModel(text)
        self._selection_axis = None
        self._update_region()
        self._schedule_draw()
        self.on_select()

    @property
    def columns(self):
        # Tests also construct grids without Tk's __init__.
        if not hasattr(self, "_columns"):
            self._columns = ColumnLayout(self.column_width)
        return self._columns

    def _update_region(self):
        viewport_columns = self.columns.cover_count(
            max(0, self.canvas.winfo_width() - self.gutter_width))
        viewport_rows = max(1, (max(0, self.canvas.winfo_height() - self.header_height)
                                + self.row_height - 1) // self.row_height)
        self.display_column_count = max(getattr(self, "display_column_count", 0),
                                        self.model.column_count + 1, self.selected[1] + 1,
                                        self.selection.anchor[1] + 1, viewport_columns)
        self.display_row_count = max(getattr(self, "display_row_count", 0),
                                     self.model.row_count + 1, self.selected[0] + 1,
                                     self.selection.anchor[0] + 1, viewport_rows)
        width = self.gutter_width + self.columns.edge(self.display_column_count)
        height = self.header_height + self.display_row_count * self.row_height
        region = (0, 0, width, height)
        if region != self._scroll_region:
            self.canvas.configure(scrollregion=region)
            self._scroll_region = region

    def _canvas_resized(self, _event=None):
        self._update_region()
        self._schedule_draw()

    def _on_view(self, scrollbar, first, last):
        scrollbar.set(first, last)
        self._schedule_draw()

    def _schedule_draw(self):
        if self._draw_job is None:
            self._draw_job = self.after_idle(self._draw_visible)

    def _cell_box(self, row, column):
        x = self.gutter_width + self.columns.edge(column)
        y = self.header_height + row * self.row_height
        return x, y, x + self.columns.width(column), y + self.row_height

    def _draw_visible(self):
        self._draw_job = None
        if not self.winfo_exists():
            return
        canvas = self.canvas
        x0, y0 = canvas.canvasx(0), canvas.canvasy(0)
        width, height = canvas.winfo_width(), canvas.winfo_height()
        rows = visible_span(y0, height, self.header_height, self.row_height,
                            max(getattr(self, "display_row_count", 0),
                                self.model.row_count + 1, self.selected[0] + 1,
                                self.selection.anchor[0] + 1))
        columns = self.columns.visible(
            x0, width, self.gutter_width,
            max(getattr(self, "display_column_count", 0),
                self.model.column_count + 1, self.selected[1] + 1,
                self.selection.anchor[1] + 1))
        canvas.delete("grid")
        top, bottom, left, right = self._selection_bounds()
        axis = getattr(self, "_selection_axis", None)
        for row in rows:
            for column in columns:
                x1, y1, x2, y2 = self._cell_box(row, column)
                chosen = top <= row <= bottom and left <= column <= right
                canvas.create_rectangle(x1, y1, x2, y2,
                                        fill=(ACTIVE_BACKGROUND if (row, column) == self.selected
                                              else SELECTION_BACKGROUND if chosen
                                              else CELL_BACKGROUND),
                                        outline=GRID_LINE, width=2, tags="grid")
                value = self.model.cell(row, column)
                if value:
                    canvas.create_text(x1 + 6, y1 + self.row_height / 2,
                                       text=self._display(value, self.columns.width(column)), anchor="w",
                                       fill=SYNTAX_COLORS.get(classify_cell(value, column),
                                                              "#1f2937"),
                                       font=self.font, tags="grid")
        if top != bottom or left != right:
            x1, y1, _, _ = self._cell_box(top, left)
            _, _, x2, y2 = self._cell_box(bottom, right)
            canvas.create_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1,
                                    outline=SELECTION_LINE, width=2, tags="grid")
        # Opaque headers cover cells scrolled beneath the fixed row-number gutter.
        for row in rows:
            y = self.header_height + row * self.row_height
            canvas.create_rectangle(x0, y, x0 + self.gutter_width, y + self.row_height,
                                    fill=HEADER_SELECTED if axis != "column" and top <= row <= bottom
                                    else HEADER_BACKGROUND,
                                    outline=HEADER_LINE, width=2, tags="grid")
            canvas.create_text(x0 + self.gutter_width - 5, y + self.row_height / 2,
                               text=str(row + 1), anchor="e", fill="#26384d",
                               font=self.font, tags="grid")
        for column in columns:
            x = self.gutter_width + self.columns.edge(column)
            column_width = self.columns.width(column)
            canvas.create_rectangle(x, y0, x + column_width, y0 + self.header_height,
                                    fill=HEADER_SELECTED if axis != "row" and left <= column <= right
                                    else HEADER_BACKGROUND,
                                    outline=HEADER_LINE, width=2, tags="grid")
            canvas.create_text(x + column_width / 2, y0 + self.header_height / 2,
                               text=column_label(column), fill="#26384d",
                               font=self.font, tags="grid")
        canvas.create_rectangle(x0, y0, x0 + self.gutter_width,
                                y0 + self.header_height, fill=HEADER_BACKGROUND,
                                outline=HEADER_LINE, width=2, tags="grid")
        canvas.create_line(x0 + self.gutter_width, y0,
                           x0 + self.gutter_width, y0 + height,
                           fill=HEADER_LINE, width=3, tags="grid")
        canvas.create_line(x0, y0 + self.header_height,
                           x0 + width, y0 + self.header_height,
                           fill=HEADER_LINE, width=3, tags="grid")
        row, column = self.selected
        if row in rows and column in columns:
            x1, y1, x2, y2 = self._cell_box(row, column)
            x1 = max(x1, x0 + self.gutter_width)
            y1 = max(y1, y0 + self.header_height)
            if x1 < x2 and y1 < y2:
                canvas.create_rectangle(x1, y1, x2, y2,
                                        outline=ACTIVE_LINE, width=3, tags="grid")
        self._position_editor()

    def _display(self, value, width):
        limit = max(1, (width - 12) // max(self.font.measure("0"), 1))
        visible = value[:limit]
        while visible and self.font.measure(visible + ("…" if len(visible) < len(value) else "")) > width - 12:
            visible = visible[:-1]
        return visible + ("…" if len(visible) < len(value) else "")

    def _position_editor(self):
        if self._editor is None:
            return
        row, column = self.selected
        x1, y1, x2, _ = self._cell_box(row, column)
        x = x1 - self.canvas.canvasx(0)
        y = y1 - self.canvas.canvasy(0)
        left = max(x, self.gutter_width)
        top = max(y, self.header_height)
        right = min(x2 - self.canvas.canvasx(0), self.canvas.winfo_width())
        bottom = min(y + self.row_height, self.canvas.winfo_height())
        if left >= right or top >= bottom:
            self._editor.place_forget()
            if getattr(self, "_popup", None) is not None:
                self._popup.place_forget()
        else:
            self._editor.place(x=left, y=top, width=right - left, height=bottom - top)
            self._position_popup(left, top, right - left, bottom - top)

    def _position_popup(self, x, y, width, height):
        completion = getattr(self, "_completion", None)
        if completion is None or not completion.open or self._popup is None:
            return
        desired = min(8, len(completion.items)) * self.row_height
        below = y + height
        room_below = self.canvas.winfo_height() - below
        room_above = y - self.header_height
        if room_below >= room_above:
            popup_height = min(desired, max(self.row_height, room_below))
            top = below
        else:
            popup_height = min(desired, max(self.row_height, room_above))
            top = y - popup_height
        popup_width = min(max(width, 220), max(1, self.canvas.winfo_width() - self.gutter_width))
        x = max(self.gutter_width, min(x, self.canvas.winfo_width() - popup_width))
        self._popup.place(x=x, y=top, width=popup_width, height=popup_height)

    def _hit_cell(self, event, clamp=False):
        x, y = event.x, event.y
        if clamp:
            x = max(self.gutter_width, min(x, self.canvas.winfo_width() - 1))
            y = max(self.header_height, min(y, self.canvas.winfo_height() - 1))
        elif x < self.gutter_width or y < self.header_height:
            return None
        row = int((self.canvas.canvasy(y) - self.header_height) // self.row_height)
        column_count = max(getattr(self, "display_column_count", 0),
                           self.model.column_count + 1, self.selected[1] + 1)
        offset = self.canvas.canvasx(x) - self.gutter_width
        if not clamp and offset >= self.columns.edge(column_count):
            return None
        column = self.columns.at(offset, column_count)
        last_row = max(getattr(self, "display_row_count", 0) - 1,
                       self.model.row_count, self.selected[0])
        last_column = max(getattr(self, "display_column_count", 0) - 1,
                          self.model.column_count, self.selected[1])
        if not clamp and (row > last_row or column > last_column):
            return None
        return max(0, min(row, last_row)), max(0, min(column, last_column))

    def _hit_target(self, event):
        if event.x < self.gutter_width and event.y < self.header_height:
            return None
        if event.x < self.gutter_width:
            row = int((self.canvas.canvasy(event.y) - self.header_height) // self.row_height)
            if 0 <= row < max(getattr(self, "display_row_count", 0),
                              self.model.row_count + 1, self.selected[0] + 1):
                return "row", row
            return None
        if event.y < self.header_height:
            column_count = max(getattr(self, "display_column_count", 0),
                               self.model.column_count + 1, self.selected[1] + 1)
            offset = self.canvas.canvasx(event.x) - self.gutter_width
            if offset >= self.columns.edge(column_count):
                return None
            column = self.columns.at(offset, column_count)
            if 0 <= column < max(getattr(self, "display_column_count", 0),
                                 self.model.column_count + 1, self.selected[1] + 1):
                return "column", column
            return None
        cell = self._hit_cell(event)
        return ("cell", cell) if cell is not None else None

    def _select_header(self, kind, index, extend=False):
        if kind == "row":
            anchor = (self.selection.anchor[0] if extend and
                      getattr(self, "_selection_axis", None) == "row" else index)
            column = self.columns.at(self.canvas.canvasx(self.gutter_width) -
                                     self.gutter_width,
                                     max(getattr(self, "display_column_count", 0),
                                         self.model.column_count + 1))
            self.selection.anchor = anchor, column
            self.selection.active = index, column
        else:
            anchor = (self.selection.anchor[1] if extend and
                      getattr(self, "_selection_axis", None) == "column" else index)
            row = max(0, int((self.canvas.canvasy(self.header_height) -
                              self.header_height) // self.row_height))
            self.selection.anchor = row, anchor
            self.selection.active = row, index
        self._selection_axis = kind

    def _select_target(self, target, extend=False):
        kind, value = target
        if kind == "cell":
            self.selection.move_to(*value, extend=extend)
            self._selection_axis = None
        else:
            self._select_header(kind, value, extend)
        self._update_region()
        self._ensure_visible()
        self.on_select()
        self._schedule_draw()

    def _click(self, event):
        self._drag_ready = False
        self._drag_axis = None
        resize_column = self._header_resize_target(event)
        if resize_column is not None:
            if self.commit_edit():
                self._resize_column = resize_column
                self._resize_start_x = event.x
                self._resize_start_width = self.columns.width(resize_column)
                self.canvas.focus_set()
                self._set_resize_cursor(True)
            return "break"
        target = self._hit_target(event)
        if target is None:
            return
        if not self.commit_edit():
            return
        self._select_target(target, extend=bool(getattr(event, "state", 0) & 0x0001))
        self._drag_ready = True
        self._drag_axis = target[0]
        self.canvas.focus_set()

    def _double_click(self, event):
        self._click(event)
        if self._drag_ready and self._drag_axis == "cell":
            self.begin_edit(caret_x=event.x)
        return "break"

    def _drag(self, event):
        resize_column = getattr(self, "_resize_column", None)
        if resize_column is not None:
            if self.columns.set_width(resize_column,
                                      self._resize_start_width + event.x - self._resize_start_x):
                self._update_region()
                self._schedule_draw()
            return "break"
        if not self._drag_ready:
            return
        if self._drag_axis == "cell":
            cell = self._hit_cell(event, clamp=True)
            if cell is None or cell == self.selected:
                return
            self.selection.move_to(*cell, extend=True)
        else:
            coordinate = event.y if self._drag_axis == "row" else event.x
            if self._drag_axis == "row":
                index = max(0, int((self.canvas.canvasy(coordinate) -
                                    self.header_height) // self.row_height))
            else:
                index = self.columns.at(self.canvas.canvasx(coordinate) -
                                        self.gutter_width,
                                        max(getattr(self, "display_column_count", 0),
                                            self.model.column_count + 1))
            limit = (max(getattr(self, "display_row_count", 0) - 1,
                         self.model.row_count, self.selected[0]) if self._drag_axis == "row"
                     else max(getattr(self, "display_column_count", 0) - 1,
                              self.model.column_count, self.selected[1]))
            self._select_header(self._drag_axis, min(index, limit), extend=True)
        self._update_region()
        self.on_select()
        self._schedule_draw()

    def _release(self, event):
        if getattr(self, "_resize_column", None) is not None:
            self._resize_column = None
            self._drag_axis = None
            self._ensure_visible()
            self._schedule_draw()
            self._header_motion(event)
            return "break"
        self._drag_ready = False
        self._drag_axis = None

    def _header_resize_target(self, event):
        if event.y >= self.header_height or event.x < self.gutter_width:
            return None
        column = self.columns.resize_hit(
            self.canvas.canvasx(event.x) - self.gutter_width,
            max(getattr(self, "display_column_count", 0),
                self.model.column_count + 1))
        if column is None:
            return None
        edge_on_screen = (self.gutter_width + self.columns.edge(column + 1) -
                          self.canvas.canvasx(0))
        return column if edge_on_screen > self.gutter_width + 5 else None

    def _set_resize_cursor(self, resizing):
        cursor = "sb_h_double_arrow" if resizing else ""
        if getattr(self, "_resize_cursor", None) != cursor:
            self.canvas.configure(cursor=cursor)
            self._resize_cursor = cursor

    def _header_motion(self, event):
        self._set_resize_cursor(getattr(self, "_resize_column", None) is not None or
                                self._header_resize_target(event) is not None)

    def _right_click(self, event):
        target = self._hit_target(event)
        if target is None or not self.commit_edit():
            return "break"
        kind, value = target
        top, bottom, left, right = self._selection_bounds()
        if kind == "cell":
            selected = top <= value[0] <= bottom and left <= value[1] <= right
        elif kind == "row":
            selected = getattr(self, "_selection_axis", None) == "row" and top <= value <= bottom
        else:
            selected = getattr(self, "_selection_axis", None) == "column" and left <= value <= right
        if not selected:
            self._select_target(target)
        self.canvas.focus_set()
        menu = self._context_menus[kind]
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def begin_edit(self, initial=None, caret_x=None):
        if self._editor is not None:
            return
        row, column = self.selected
        self.selection.move_to(row, column)
        self._selection_axis = None
        editor = self._entry_widget
        if editor is None:
            editor = tk.Entry(self.canvas, font=self.font, exportselection=False,
                              background=ACTIVE_BACKGROUND, relief="flat",
                              highlightthickness=3, highlightbackground=ACTIVE_LINE,
                              highlightcolor=ACTIVE_LINE)
            self._entry_widget = editor
            self._bind_entry_navigation(editor)
        editor.delete(0, "end")
        editor.insert(0, self.model.cell(row, column) if initial is None else initial)
        editor.xview_moveto(0)
        self._editor = editor
        self._position_editor()
        editor.focus_set()
        editor.selection_clear()
        if caret_x is None:
            editor.icursor("end")
        else:
            x1, _, _, _ = self._cell_box(row, column)
            left = max(x1 - self.canvas.canvasx(0), self.gutter_width)
            editor.icursor(f"@{max(0, int(caret_x - left))}")
        self.on_select()
        self._schedule_draw()
        if initial is not None:
            self._refresh_completion()

    def _bind_entry_navigation(self, editor):
        for key, delta in (("Return", (1, 0)), ("Tab", (0, 1))):
            editor.bind(f"<{key}>", lambda event, move=delta: self._completion_or_move(event, *move))
        for key, delta in (("Shift-Return", (-1, 0)), ("Shift-Tab", (0, -1))):
            editor.bind(f"<{key}>", lambda event, move=delta: self._entry_move(event, *move))
        editor.bind("<Escape>", self._completion_or_cancel)
        editor.bind("<Up>", lambda event: self._popup_step(event, -1))
        editor.bind("<Down>", lambda event: self._popup_step(event, 1))
        editor.bind("<KeyRelease>", self._entry_key_released)
        editor.bind("<Control-a>", self._entry_select_all)
        editor.bind("<Control-v>", self._entry_paste)
        editor.bind("<Control-z>", lambda event: self._entry_history(event, self.on_undo))
        editor.bind("<Control-y>", lambda event: self._entry_history(event, self.on_redo))

    def _start_edit(self, _event=None):
        self.begin_edit()
        return "break"

    def _type_to_edit(self, event):
        char = getattr(event, "char", "")
        # ASCII keys can start a cell directly. IME composition stays in Entry,
        # opened with F2 or double click, using Tk's standard text input handling.
        if (getattr(event, "state", 0) & 0x000c or len(char) != 1 or
                not 32 <= ord(char) <= 126):
            return None
        self.begin_edit(initial=char)
        return "break"

    def _entry_move(self, event, row_delta, column_delta, extend=False):
        if event.widget is not self._editor:
            return "break"  # Ignore a key event from an editor already closed.
        self._close_popup()
        if not self._apply_editor_value():
            return "break"
        self._close_editor()
        return self._move(row_delta, column_delta, extend=extend)

    def _entry_history(self, event, action):
        if event.widget is not self._editor:
            return "break"
        if self._apply_editor_value():
            self._close_editor()
            action()
        return "break"

    def _entry_select_all(self, event):
        if event.widget is self._editor:
            self._editor.select_range(0, "end")
            self._editor.icursor("end")
        return "break"

    def _close_editor(self):
        editor = self._editor
        if editor is None:
            return
        self._editor = None
        self._close_popup()
        editor.place_forget()
        self.canvas.focus_set()

    def _close_popup(self):
        if hasattr(self, "_completion"):
            self._completion.close()
        if getattr(self, "_popup", None) is not None:
            self._popup.place_forget()

    def _refresh_completion(self):
        if self._editor is None:
            self._close_popup()
            return
        editor = self._editor
        choices = candidates_for(editor.get(), editor.index("insert"), self.selected[1])
        if not choices:
            self._close_popup()
            return
        self._completion.show(choices)
        if self._popup is None:
            self._popup = tk.Listbox(self.canvas, font=self.font, exportselection=False,
                                     activestyle="dotbox", takefocus=False)
            self._popup.bind("<ButtonRelease-1>", self._popup_mouse)
        self._popup.delete(0, "end")
        for item in choices:
            self._popup.insert("end", item.label)
        self._popup.selection_set(0)
        self._popup.activate(0)
        self._position_editor()

    def _entry_key_released(self, event):
        if event.widget is not self._editor:
            return
        key = getattr(event, "keysym", "")
        state = getattr(event, "state", 0)
        if (key in ("Up", "Down", "Return", "Tab", "Escape",
                    "Control_L", "Control_R", "Alt_L", "Alt_R") or
                state & 0x0008 or (state & 0x0004 and key.lower() not in ("v", "x"))):
            return
        self._refresh_completion()

    def _popup_step(self, event, delta):
        if event.widget is not self._editor or not self._completion.open:
            return None
        self._completion.step(delta)
        self._popup.selection_clear(0, "end")
        self._popup.selection_set(self._completion.index)
        self._popup.activate(self._completion.index)
        self._popup.see(self._completion.index)
        return "break"

    def _accept_completion(self):
        candidate = self._completion.current
        if candidate is None:
            return False
        editor = self._editor
        span = completion_span(editor.get(), editor.index("insert"), self.selected[1])
        if span is None:
            self._close_popup()
            return False
        self._insert_candidate(candidate, span[0], span[1])
        return True

    def _completion_or_move(self, event, row_delta, column_delta):
        if event.widget is not self._editor:
            return "break"
        if self._completion.open and self._accept_completion():
            return "break"
        return self._entry_move(event, row_delta, column_delta)

    def _completion_or_cancel(self, event):
        if event.widget is not self._editor:
            return "break"
        if self._completion.open:
            self._close_popup()
            self._editor.focus_set()
            return "break"
        return self.cancel_edit()

    def _popup_mouse(self, _event):
        selected = self._popup.curselection()
        if selected and self._completion.open:
            self._completion.index = int(selected[0])
            self._accept_completion()
        return "break"

    def _insert_candidate(self, candidate, start, end):
        editor = self._editor
        updated, caret, selection = insert_template(editor.get(), start, end, candidate)
        editor.delete(0, "end")
        editor.insert(0, updated)
        editor.icursor(caret)
        if selection is not None:
            editor.select_range(*selection)
            editor.icursor(selection[1])
        self._close_popup()
        editor.focus_set()

    def insert_candidate(self, candidate):
        """Palette insertion replaces a selected cell or inserts at the Entry caret."""
        if self._editor is None:
            self.begin_edit(initial="")
        editor = self._editor
        if editor.selection_present():
            start, end = editor.index("sel.first"), editor.index("sel.last")
        else:
            start = end = editor.index("insert")
        self._insert_candidate(candidate, start, end)

    def _entry_paste(self, _event=None):
        try:
            data = self.clipboard_get()
        except tk.TclError:
            return None
        if "\t" in data or "\n" in data or "\r" in data:
            if not self._apply_editor_value():
                return "break"
            self._close_editor()
            self.paste_text(data)
            return "break"
        return None  # Let Entry paste ordinary cell text at its insertion point.

    def clipboard_action(self, kind):
        if self._editor is not None:
            if kind == "Paste" and self._entry_paste() == "break":
                return True
            self._editor.event_generate(f"<<{kind}>>")
            return True
        return {"Copy": self.copy_selection,
                "Cut": self.cut_selection,
                "Paste": self.paste_clipboard}[kind]()

    def cancel_edit(self):
        if self._editor is not None:
            self._close_editor()
            self._schedule_draw()
        return "break"

    def _apply_editor_value(self):
        row, column = self.selected
        value = self._editor.get()
        if "\t" in value or "\n" in value or "\r" in value:
            self._editor.bell()
            return False
        if row >= self.model.row_count:
            if not value:
                return True
            updated = self.model.copy()
            updated.paste(row, column, value)
            return self._apply_model(updated)
        try:
            new_line = self.model.changed_line(row, column, value)
        except ValueError:
            self._editor.bell()
            return False
        old_line = self.model.line(row)
        if new_line != old_line:
            if not self.on_change(row, old_line, new_line):
                return False
            self.model.update_line(row, new_line)
            self._update_region()
        return True

    def commit_edit(self):
        if self._editor is None:
            return True
        if not self._apply_editor_value():
            return False
        self._close_editor()
        self._schedule_draw()
        return True

    def _apply_model(self, updated, anchor=None, active=None):
        previous = self.model.to_text()
        current = updated.to_text()
        if current != previous and not self.on_transform(previous, current):
            return False
        self.model = updated
        self._selection_axis = None
        if anchor is not None:
            self.selection.move_to(*anchor)
        if active is not None:
            self.selection.move_to(*active, extend=True)
        self._update_region()
        self._ensure_visible()
        self.on_select()
        self._schedule_draw()
        return True

    def copy_selection(self):
        if not self.commit_edit():
            return False
        try:
            self.clipboard_clear()
            self.clipboard_append(self.model.copy_range(self._selection_bounds()))
        except tk.TclError:
            return False
        return True

    def cut_selection(self):
        return self.copy_selection() and self.clear_selection()

    def paste_clipboard(self):
        try:
            data = self.clipboard_get()
        except tk.TclError:
            return False
        return self.paste_text(data)

    def paste_text(self, data):
        if not self.commit_edit():
            return False
        top, _, left, _ = self._selection_bounds()
        if not data and top >= self.model.row_count:
            return True
        updated = self.model.copy()
        rows, columns = updated.paste(top, left, data)
        return self._apply_model(updated, (top, left),
                                 (top + rows - 1, left + columns - 1))

    def clear_selection(self):
        if not self.commit_edit():
            return False
        updated = self.model.copy()
        updated.clear_range(self._selection_bounds())
        return self._apply_model(updated)

    def insert_row_above(self):
        if not self.commit_edit():
            return False
        row, column = self.selected
        updated = self.model.copy()
        index = row
        updated.insert_row(index)
        return self._apply_model(updated, (index, column))

    def insert_row_below(self):
        if not self.commit_edit():
            return False
        row, column = self.selected
        updated = self.model.copy()
        index = row + 1
        updated.insert_row(index)
        return self._apply_model(updated, (index, column))

    def insert_row(self):
        return self.insert_row_above()

    def delete_row(self):
        if not self.commit_edit():
            return False
        row, column = self.selected
        first, last = (self._selection_bounds()[:2] if
                       getattr(self, "_selection_axis", None) == "row" else (row, row))
        if first >= self.model.row_count:
            return False
        updated = self.model.copy()
        updated.delete_rows(first, last)
        return self._apply_model(updated, (min(first, updated.row_count - 1), column))

    def duplicate_row(self):
        if not self.commit_edit():
            return False
        row, column = self.selected
        updated = self.model.copy()
        if row >= updated.row_count:
            return False
        updated.duplicate_row(row)
        return self._apply_model(updated, (row + 1, column))

    def insert_column_left(self):
        if not self.commit_edit():
            return False
        row, column = self.selected
        updated = self.model.copy()
        index = column
        updated.insert_column(index)
        return self._apply_model(updated, (row, index))

    def insert_column_right(self):
        if not self.commit_edit():
            return False
        row, column = self.selected
        updated = self.model.copy()
        index = column + 1
        updated.insert_column(index)
        return self._apply_model(updated, (row, index))

    def insert_column(self):
        return self.insert_column_left()

    def delete_column(self):
        if not self.commit_edit():
            return False
        row, column = self.selected
        updated = self.model.copy()
        first, last = (self._selection_bounds()[2:] if
                       getattr(self, "_selection_axis", None) == "column" else (column, column))
        if first >= self.model.column_count:
            return False
        updated.delete_columns(first, last)
        return self._apply_model(updated, (row, min(first, updated.column_count - 1)))

    def _move(self, row_delta, column_delta, extend=False):
        if not self.commit_edit():
            return "break"
        row, column = self.selected
        self.selection.move_to(
            max(0, row + row_delta),
            max(0, column + column_delta),
            extend=extend)
        self._selection_axis = None
        self._update_region()
        self._ensure_visible()
        self.on_select()
        self._schedule_draw()
        return "break"

    def _ensure_visible(self):
        row, column = self.selected
        x = self.gutter_width + self.columns.edge(column)
        column_width = self.columns.width(column)
        y = self.header_height + row * self.row_height
        left, top = self.canvas.canvasx(0), self.canvas.canvasy(0)
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        total_width = self.gutter_width + self.columns.edge(
            max(getattr(self, "display_column_count", 0), column + 1))
        total_height = self.header_height + max(getattr(self, "display_row_count", 0),
                                                row + 1) * self.row_height
        axis = getattr(self, "_selection_axis", None)
        if axis != "row" and x < left + self.gutter_width:
            self.canvas.xview_moveto(max(0, (x - self.gutter_width) / total_width))
        elif axis != "row" and x + column_width > left + width:
            self.canvas.xview_moveto(max(0, (x + column_width - width) / total_width))
        if axis != "column" and y < top + self.header_height:
            self.canvas.yview_moveto(max(0, (y - self.header_height) / total_height))
        elif axis != "column" and y + self.row_height > top + height:
            self.canvas.yview_moveto(max(0, (y + self.row_height - height) / total_height))

    def _scroll_x(self, *args):
        if self.commit_edit():
            self.canvas.xview(*args)
            self._schedule_draw()

    def _scroll_y(self, *args):
        if self.commit_edit():
            self.canvas.yview(*args)
            self._schedule_draw()

    def _wheel(self, event):
        return self._wheel_units(-1 if event.delta > 0 else 1)

    def _wheel_units(self, direction):
        self._scroll_y("scroll", direction, "units")
        return "break"
