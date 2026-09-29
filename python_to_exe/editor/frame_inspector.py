"""Visible-row Canvas view of resolved converter Debug CSV frames."""

import tkinter as tk
from pathlib import Path


# Display labels are intentionally separate from the converter's exact CSV fields.
MAIN_COLUMNS = (
    ("Frame", "Frame", 70), ("Player", "2ndPlayer", 70),
    ("Buttons", "Buttons", 90), ("ButtonsOn", "ButtonsOn", 95),
    ("ButtonsOff", "ButtonsOff", 95), ("LS angle", "ls.theta", 90),
    ("LS X", "ls.x", 80), ("LS Y", "ls.y", 80),
    ("RS angle", "rs.theta", 90), ("RS X", "rs.x", 80),
    ("RS Y", "rs.y", 80), ("Command", "Command", 180),
)
ROW_HEIGHT = 24
HEADER_HEIGHT = 26


class FrameInspector(tk.Toplevel):
    def __init__(self, master, words, frames, source):
        super().__init__(master)
        self.words = words
        self.frames = frames
        self.source = Path(source)
        self.selected_row = None
        self._draw_job = None
        self._column_edges = [0]
        for _, _, width in MAIN_COLUMNS:
            self._column_edges.append(self._column_edges[-1] + width)
        self.geometry("1050x550")

        top = tk.Frame(self)
        top.pack(fill="x")
        self.total_label = tk.Label(top, anchor="w")
        self.total_label.pack(side="left", padx=6)
        tk.Label(top, text=words["frame_number"]).pack(side="left")
        self.frame_entry = tk.Entry(top, width=12)
        self.frame_entry.pack(side="left", padx=4)
        self.frame_entry.bind("<Return>", lambda event: self.go_to_frame())
        tk.Button(top, text=words["go"], command=self.go_to_frame).pack(side="left")
        self.feedback = tk.Label(top, anchor="w")
        self.feedback.pack(side="left", padx=8)

        body = tk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, background="#ffffff", highlightthickness=0)
        vertical = tk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        horizontal = tk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=lambda first, last: self._scrolled(vertical, first, last),
                              xscrollcommand=lambda first, last: self._scrolled(horizontal, first, last))
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", lambda event: self._schedule_draw())
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda event: self._wheel_units(-1))
        self.canvas.bind("<Button-5>", lambda event: self._wheel_units(1))
        self.bind("<Destroy>", self._on_destroy)

        tk.Label(self, text=words["frame_details"], anchor="w").pack(fill="x")
        detail_area = tk.Frame(self)
        detail_area.pack(fill="x")
        self.detail_text = tk.Text(detail_area, height=7, wrap="none", state="disabled")
        detail_scroll = tk.Scrollbar(detail_area, command=self.detail_text.yview)
        detail_horizontal = tk.Scrollbar(detail_area, orient="horizontal",
                                         command=self.detail_text.xview)
        self.detail_text.configure(yscrollcommand=detail_scroll.set,
                                   xscrollcommand=detail_horizontal.set)
        self.detail_text.grid(row=0, column=0, sticky="nsew")
        detail_scroll.grid(row=0, column=1, sticky="ns")
        detail_horizontal.grid(row=1, column=0, sticky="ew")
        detail_area.grid_columnconfigure(0, weight=1)
        self.set_data(frames, source)

    def _on_destroy(self, event):
        if event.widget is self and self._draw_job is not None:
            self.after_cancel(self._draw_job)
            self._draw_job = None

    def _scrolled(self, scrollbar, first, last):
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
        canvas.delete("inspector")
        y0 = canvas.canvasy(0)
        x0 = canvas.canvasx(0)
        x1 = x0 + canvas.winfo_width()
        first = max(0, int((y0 - HEADER_HEIGHT) // ROW_HEIGHT))
        last = min(len(self.frames.rows),
                   int((y0 + canvas.winfo_height() - HEADER_HEIGHT) // ROW_HEIGHT) + 2)
        for row in range(first, max(first, last)):
            values = self.frames.summary(row)
            y = HEADER_HEIGHT + row * ROW_HEIGHT
            background = ("#cde1fa" if row == self.selected_row else
                          "#f7f9fc" if row % 2 else "#ffffff")
            for column, value in enumerate(values):
                left, right = self._column_edges[column:column + 2]
                if right < x0 or left > x1:
                    continue
                canvas.create_rectangle(left, y, right, y + ROW_HEIGHT,
                                        fill=background, outline="#d5dce6", tags="inspector")
                limit = max(1, (right - left - 10) // 7)
                shown = str(value)
                if len(shown) > limit:
                    shown = shown[:limit - 1] + "…"
                canvas.create_text(left + 4, y + ROW_HEIGHT / 2, text=shown,
                                   anchor="w",
                                   fill="#243447", tags="inspector")
        for column, (label, _, _) in enumerate(MAIN_COLUMNS):
            left, right = self._column_edges[column:column + 2]
            if right < x0 or left > x1:
                continue
            canvas.create_rectangle(left, y0, right, y0 + HEADER_HEIGHT,
                                    fill="#e4ebf3", outline="#78889c", tags="inspector")
            canvas.create_text(left + 4, y0 + HEADER_HEIGHT / 2, text=label,
                               anchor="w", fill="#26384d", tags="inspector")

    def _click(self, event):
        if event.y < HEADER_HEIGHT:
            return
        row = int((self.canvas.canvasy(event.y) - HEADER_HEIGHT) // ROW_HEIGHT)
        self.select_row(row)

    def _wheel(self, event):
        if event.delta:
            self._wheel_units(-int(event.delta / 120) or (-1 if event.delta > 0 else 1))
        return "break"

    def _wheel_units(self, units):
        self.canvas.yview_scroll(units, "units")
        return "break"

    def select_row(self, row):
        if not 0 <= row < len(self.frames.rows):
            return False
        self.selected_row = row
        self._show_detail(row)
        self._schedule_draw()
        return True

    def _show_detail(self, row):
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", "\n".join(
            f"{field}: {value}" for field, value in self.frames.detail(row).items()))
        self.detail_text.configure(state="disabled")

    def go_to_frame(self):
        try:
            frame = int(self.frame_entry.get().strip())
        except ValueError:
            self.feedback.configure(text=self.words["invalid_frame"])
            return False
        row = self.frames.row_for_frame(frame)
        if row is None:
            self.feedback.configure(text=self.words["frame_not_found"])
            return False
        self.feedback.configure(text="")
        self.select_row(row)
        height = HEADER_HEIGHT + max(1, len(self.frames.rows)) * ROW_HEIGHT
        self.canvas.yview_moveto((HEADER_HEIGHT + row * ROW_HEIGHT) / height)
        self._schedule_draw()
        return True

    def mark_stale(self):
        self.feedback.configure(text=self.words["previous_frames"])

    def set_data(self, frames, source):
        self.frames = frames
        self.source = Path(source)
        self.title(f"{self.words['frame_inspector']} — {self.source.name}")
        self.total_label.configure(text=f"{self.words['total_frames']}: {frames.total_frames}")
        self.feedback.configure(text="")
        self.selected_row = None
        self.canvas.configure(scrollregion=(0, 0, self._column_edges[-1],
                                            HEADER_HEIGHT + max(1, len(frames.rows)) * ROW_HEIGHT))
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.configure(state="disabled")
        if frames.rows:
            self.select_row(0)
        self._schedule_draw()
