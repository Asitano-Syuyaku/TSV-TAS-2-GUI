"""Canvas table that draws visible TSV cells and edits one cell at a time."""

import tkinter as tk

from .table_model import TableModel, visible_span


class TableGrid(tk.Frame):
    def __init__(self, master, font, on_change, on_select, on_undo, on_redo):
        super().__init__(master)
        self.font = font
        self.on_change = on_change
        self.on_select = on_select
        self.on_undo = on_undo
        self.on_redo = on_redo
        self.row_height = max(font.metrics("linespace") + 8, 24)
        self.column_width = max(font.measure("0" * 18) + 12, 160)
        self.header_height = self.row_height
        self.gutter_width = max(font.measure("00000") + 12, 48)
        self.model = TableModel("")
        self.selected = (0, 0)
        self._editor = None
        self._draw_job = None

        self.canvas = tk.Canvas(self, background="white", highlightthickness=0,
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

        self.canvas.bind("<Configure>", lambda event: self._schedule_draw())
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda event: self._wheel_units(-1))
        self.canvas.bind("<Button-5>", lambda event: self._wheel_units(1))
        for key, delta in (("Up", (-1, 0)), ("Down", (1, 0)),
                           ("Left", (0, -1)), ("Right", (0, 1)),
                           ("Return", (1, 0)), ("Tab", (0, 1)),
                           ("Shift-Tab", (0, -1))):
            self.canvas.bind(f"<{key}>", lambda event, move=delta: self._move(*move))
        self._bind_history(self.canvas)
        self._update_region()

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
        row, column = self.selected
        self.selected = (min(row, self.model.row_count - 1),
                         min(column, self.model.column_count - 1))
        self._update_region()
        self._schedule_draw()
        self.on_select()

    def _update_region(self):
        columns = max(self.model.column_count, self.selected[1] + 1)
        width = self.gutter_width + columns * self.column_width
        height = self.header_height + self.model.row_count * self.row_height
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _on_view(self, scrollbar, first, last):
        scrollbar.set(first, last)
        self._schedule_draw()

    def _schedule_draw(self):
        if self._draw_job is None:
            self._draw_job = self.after_idle(self._draw_visible)

    def _draw_visible(self):
        self._draw_job = None
        if not self.winfo_exists():
            return
        canvas = self.canvas
        x0, y0 = canvas.canvasx(0), canvas.canvasy(0)
        width, height = canvas.winfo_width(), canvas.winfo_height()
        rows = visible_span(y0, height, self.header_height,
                            self.row_height, self.model.row_count)
        columns = visible_span(x0, width, self.gutter_width,
                               self.column_width,
                               max(self.model.column_count, self.selected[1] + 1))
        canvas.delete("grid")
        for row in rows:
            y = self.header_height + row * self.row_height
            for column in columns:
                x = self.gutter_width + column * self.column_width
                canvas.create_rectangle(x, y, x + self.column_width, y + self.row_height,
                                        outline="gray", tags="grid")
                value = self.model.cell(row, column)
                if value:
                    canvas.create_text(x + 5, y + self.row_height / 2,
                                       text=self._display(value), anchor="w",
                                       font=self.font, tags="grid")
        row, column = self.selected
        if row in rows and column in columns:
            x = self.gutter_width + column * self.column_width
            y = self.header_height + row * self.row_height
            canvas.create_rectangle(x + 1, y + 1, x + self.column_width - 1,
                                    y + self.row_height - 1, outline="blue",
                                    width=2, tags="grid")
        # Opaque headers cover cells scrolled beneath the fixed row-number gutter.
        for row in rows:
            y = self.header_height + row * self.row_height
            canvas.create_rectangle(x0, y, x0 + self.gutter_width, y + self.row_height,
                                    fill="white", outline="gray", tags="grid")
            canvas.create_text(x0 + self.gutter_width - 5, y + self.row_height / 2,
                               text=str(row + 1), anchor="e", font=self.font, tags="grid")
        for column in columns:
            x = self.gutter_width + column * self.column_width
            canvas.create_rectangle(x, y0, x + self.column_width, y0 + self.header_height,
                                    fill="white", outline="gray", tags="grid")
            canvas.create_text(x + self.column_width / 2, y0 + self.header_height / 2,
                               text=str(column + 1), font=self.font, tags="grid")
        canvas.create_rectangle(x0, y0, x0 + self.gutter_width,
                                y0 + self.header_height, fill="white",
                                outline="gray", tags="grid")
        self._position_editor()

    def _display(self, value):
        limit = max(1, (self.column_width - 12) // max(self.font.measure("0"), 1))
        visible = value[:limit]
        while visible and self.font.measure(visible + ("…" if len(visible) < len(value) else "")) > self.column_width - 12:
            visible = visible[:-1]
        return visible + ("…" if len(visible) < len(value) else "")

    def _position_editor(self):
        if self._editor is None:
            return
        row, column = self.selected
        x = self.gutter_width + column * self.column_width - self.canvas.canvasx(0)
        y = self.header_height + row * self.row_height - self.canvas.canvasy(0)
        if (x + self.column_width <= self.gutter_width or
                y + self.row_height <= self.header_height or
                x >= self.canvas.winfo_width() or y >= self.canvas.winfo_height()):
            self._editor.place_forget()
        else:
            self._editor.place(x=x, y=y, width=self.column_width, height=self.row_height)

    def _click(self, event):
        if event.x < self.gutter_width or event.y < self.header_height:
            return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        row = int((y - self.header_height) // self.row_height)
        column = int((x - self.gutter_width) // self.column_width)
        if row >= self.model.row_count or column >= self.model.column_count:
            return
        if not self.commit_edit():
            return
        self.selected = row, column
        self._ensure_visible()
        self.on_select()
        self._schedule_draw()
        self.begin_edit()

    def begin_edit(self):
        if self._editor is not None:
            return
        row, column = self.selected
        editor = tk.Entry(self.canvas, font=self.font)
        editor.insert(0, self.model.cell(row, column))
        self._editor = editor
        self._position_editor()
        editor.focus_set()
        editor.select_range(0, "end")
        for key, delta in (("Up", (-1, 0)), ("Down", (1, 0)),
                           ("Left", (0, -1)), ("Right", (0, 1)),
                           ("Return", (1, 0)), ("Tab", (0, 1)),
                           ("Shift-Tab", (0, -1))):
            editor.bind(f"<{key}>", lambda event, move=delta: self._move(*move))
        editor.bind("<Escape>", lambda event: self.cancel_edit())
        self._bind_history(editor)

    def cancel_edit(self):
        if self._editor is not None:
            self._editor.destroy()
            self._editor = None
            self.canvas.focus_set()
            self._schedule_draw()
        return "break"

    def commit_edit(self):
        if self._editor is None:
            return True
        row, column = self.selected
        try:
            new_line = self.model.changed_line(row, column, self._editor.get())
        except ValueError:
            self._editor.bell()
            return False
        old_line = self.model.line(row)
        if new_line != old_line:
            if not self.on_change(row, old_line, new_line):
                return False
            self.model.update_line(row, new_line)
            self._update_region()
        self._editor.destroy()
        self._editor = None
        self._schedule_draw()
        return True

    def _move(self, row_delta, column_delta):
        if not self.commit_edit():
            return "break"
        row, column = self.selected
        self.selected = (max(0, min(self.model.row_count - 1, row + row_delta)),
                         max(0, min(self.model.column_count, column + column_delta)))
        self._update_region()
        self._ensure_visible()
        self.on_select()
        self._schedule_draw()
        self.begin_edit()
        return "break"

    def _ensure_visible(self):
        row, column = self.selected
        x = self.gutter_width + column * self.column_width
        y = self.header_height + row * self.row_height
        left, top = self.canvas.canvasx(0), self.canvas.canvasy(0)
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        total_width = self.gutter_width + max(self.model.column_count, column + 1) * self.column_width
        total_height = self.header_height + self.model.row_count * self.row_height
        if x < left + self.gutter_width:
            self.canvas.xview_moveto(max(0, (x - self.gutter_width) / total_width))
        elif x + self.column_width > left + width:
            self.canvas.xview_moveto(max(0, (x + self.column_width - width) / total_width))
        if y < top + self.header_height:
            self.canvas.yview_moveto(max(0, (y - self.header_height) / total_height))
        elif y + self.row_height > top + height:
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
