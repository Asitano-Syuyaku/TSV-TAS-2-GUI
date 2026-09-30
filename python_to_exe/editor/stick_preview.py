"""Read-only LS/RS plots from cached converter Debug CSV samples."""

import tkinter as tk

from .theme import COLORS, SIZES, SPACING, TRAIL_COLORS, label_options


STICK_SCALE = 32767.0
PLOT_HEIGHT = SIZES["plot_height"]


def point_position(state, center_x, center_y, radius):
    """Scale resolved coordinates for a unit circle; positive Y points upward."""
    if state.x is None or state.y is None:
        return None
    return (center_x + state.x / STICK_SCALE * radius,
            center_y - state.y / STICK_SCALE * radius)


class StickPreview(tk.Frame):
    def __init__(self, master, fonts=None):
        super().__init__(master, background=COLORS["panel_background"])
        self.frame = None
        self.samples = ()
        self._key = None
        self.plots, self.values = [], []
        self.status = tk.Label(self, text="—", anchor="w", **label_options(role="small", fonts=fonts))
        self.status.grid(row=0, column=0, columnspan=2, sticky="ew", padx=3)
        for column, name in enumerate(("LS", "RS")):
            self.grid_columnconfigure(column, weight=1, uniform="sticks")
            tk.Label(self, text=name, **label_options(role="heading", fonts=fonts)).grid(row=1, column=column)
            canvas = tk.Canvas(self, width=SIZES["plot_width"], height=PLOT_HEIGHT, highlightthickness=0,
                               background=COLORS["panel_background"])
            canvas.grid(row=2, column=column, sticky="ew", padx=SPACING["button_gap"])
            values = tk.Label(self, text="x: —  y: —\nr: —  θ: —", **label_options(role="small", fonts=fonts))
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
        if frame is None:
            self.status.configure(text=message)
            self.status.grid()
        else:
            self.status.configure(text="")
            self.status.grid_remove()
        for column in range(2):
            self._draw(column)

    def _draw(self, column):
        canvas = self.plots[column]
        canvas.delete("all")
        width = max(canvas.winfo_width(), SIZES["plot_width"])
        height = PLOT_HEIGHT
        cx, cy = width / 2, height / 2
        radius = min(width, height) / 2 - 10
        canvas.create_line(cx - radius, cy, cx + radius, cy, fill=COLORS["preview_axis"])
        canvas.create_line(cx, cy - radius, cx, cy + radius, fill=COLORS["preview_axis"])
        canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                           outline=COLORS["preview_circle"])
        canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill=COLORS["preview_center"], outline="")
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
