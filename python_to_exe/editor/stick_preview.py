"""Read-only LS/RS plots from cached converter Debug CSV samples."""

import tkinter as tk


STICK_SCALE = 32767.0
TRAIL_COLORS = ("#cc2828", "#dc7777", "#e7aaaa", "#f0cece")


def point_position(state, center_x, center_y, radius):
    """Scale resolved coordinates for a unit circle; positive Y points upward."""
    if state.x is None or state.y is None:
        return None
    return (center_x + state.x / STICK_SCALE * radius,
            center_y - state.y / STICK_SCALE * radius)


class StickPreview(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.frame = None
        self.samples = ()
        self._key = None
        self.plots, self.values = [], []
        self.status = tk.Label(self, text="—", anchor="w")
        self.status.grid(row=0, column=0, columnspan=2, sticky="ew", padx=3)
        for column, name in enumerate(("LS", "RS")):
            self.grid_columnconfigure(column, weight=1, uniform="sticks")
            tk.Label(self, text=name).grid(row=1, column=column)
            canvas = tk.Canvas(self, width=160, height=138, highlightthickness=0,
                               background="white")
            canvas.grid(row=2, column=column, sticky="ew", padx=2)
            values = tk.Label(self, text="x: —  y: —\nr: —  θ: —")
            values.grid(row=3, column=column, sticky="ew")
            self.plots.append(canvas)
            self.values.append(values)
            canvas.bind("<Configure>", lambda event, index=column: self._draw(index))

    def show(self, frame=None, samples=(), message="—"):
        key = (frame, samples, message)
        if key == self._key:
            return
        self._key = key
        self.frame, self.samples = frame, samples
        self.status.configure(text=message if frame is None else f"{frame}f · 1P")
        for column in range(2):
            self._draw(column)

    def _draw(self, column):
        canvas = self.plots[column]
        canvas.delete("all")
        width = max(canvas.winfo_width(), 160)
        height = 138
        cx, cy = width / 2, height / 2
        radius = min(width, height) / 2 - 10
        canvas.create_line(cx - radius, cy, cx + radius, cy, fill="#dddddd")
        canvas.create_line(cx, cy - radius, cx, cy + radius, fill="#dddddd")
        canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                           outline="#777777")
        canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill="#777777", outline="")
        current = None
        for sample in reversed(self.samples):
            age = self.frame - sample.frame
            state = sample.left if column == 0 else sample.right
            if age == 0:
                current = state
            point = point_position(state, cx, cy, radius)
            if point is not None:
                x, y = point
                size = 4 if age == 0 else 3
                canvas.create_oval(x - size, y - size, x + size, y + size,
                                   fill=TRAIL_COLORS[age], outline="",
                                   tags=("sample", f"age{age}"))

        def display(value, scale=1):
            return "—" if value is None else f"{value / scale:.3g}"

        if current is None:
            text = "x: —  y: —\nr: —  θ: —"
        else:
            text = (f"x: {display(current.x, STICK_SCALE)}  y: {display(current.y, STICK_SCALE)}\n"
                    f"r: {display(current.radius)}  θ: {display(current.angle)}°")
        self.values[column].configure(text=text)
