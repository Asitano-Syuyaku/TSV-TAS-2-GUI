"""Read-only LS/RS plots from cached converter Debug CSV samples."""

import tkinter as tk

from .theme import COLORS, SIZES, SPACING, STICK_CORE, STICK_RAMPS, label_options


STICK_SCALE = 32767.0
PLOT_HEIGHT = SIZES["plot_height"]
STICKS = ("ls", "rs")
# State lamp beside the unchanged status text (§8.4): pending vs unavailable.
LAMP_COLORS = {"pending": COLORS["neon_yellow"], "unavailable": COLORS["neon_orange"]}


def point_position(state, center_x, center_y, radius):
    """Scale resolved coordinates for a unit circle; positive Y points upward."""
    if state.x is None or state.y is None:
        return None
    return (center_x + state.x / STICK_SCALE * radius,
            center_y - state.y / STICK_SCALE * radius)


class StickPreview(tk.Frame):
    def __init__(self, master, fonts=None, title=""):
        super().__init__(master, background=COLORS["panel_background"])
        self.frame = None
        self.samples = ()
        self._key = None
        self.plots, self.values = [], []
        heading = tk.Frame(self, background=COLORS["panel_background"])
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", padx=SPACING["button_gap"],
                     pady=(SPACING["category_top"], SPACING["category_bottom"]))
        self.title = tk.Label(heading, text=title, anchor="w",
                              **label_options(role="heading", fonts=fonts))
        self.title.pack(side="left")
        self.status = tk.Label(heading, text="—", anchor="e",
                               **label_options(role="small", fonts=fonts))
        self.status.pack(side="right", padx=(SPACING["gap"], 0))
        self.lamp = tk.Label(heading, text="●", **label_options(role="small", fonts=fonts))
        for column, name in enumerate(STICKS):
            color = STICK_RAMPS[name][0]
            self.grid_columnconfigure(column, weight=1, uniform="sticks")
            label = tk.Label(self, text=name.upper(), **label_options(role="heading", fonts=fonts))
            label.configure(foreground=color)
            label.grid(row=1, column=column)
            canvas = tk.Canvas(self, width=SIZES["plot_width"], height=PLOT_HEIGHT, highlightthickness=0,
                               background=COLORS["preview_background"])
            canvas.grid(row=2, column=column, sticky="ew", padx=SPACING["button_gap"])
            values = tk.Label(self, text="x: —  y: —\nr: —  θ: —", **label_options(role="small", fonts=fonts))
            values.configure(foreground=color)
            values.grid(row=3, column=column, sticky="ew")
            self.plots.append(canvas)
            self.values.append(values)
            canvas.bind("<Configure>", lambda event, index=column: self._draw(index))

    def show(self, frame=None, samples=(), message="—", lamp="unavailable"):
        key = (frame, samples, message, lamp)
        if key == self._key:
            return
        self._key = key
        self.frame, self.samples = frame, samples
        if frame is None:
            self.status.configure(text=message)
            self.status.pack(side="right", padx=(SPACING["gap"], 0))
            self.lamp.configure(foreground=LAMP_COLORS.get(lamp, LAMP_COLORS["unavailable"]))
            self.lamp.pack(side="right")
        else:
            self.status.configure(text="")
            self.status.pack_forget()
            self.lamp.pack_forget()
        for column in range(2):
            self._draw(column)

    def _draw(self, column):
        canvas = self.plots[column]
        ramp = STICK_RAMPS[STICKS[column]]
        canvas.delete("all")
        width = max(canvas.winfo_width(), SIZES["plot_width"])
        height = PLOT_HEIGHT
        cx, cy = width / 2, height / 2
        radius = min(width, height) / 2 - 10
        canvas.create_line(cx - radius, cy, cx + radius, cy, fill=COLORS["preview_axis"])
        canvas.create_line(cx, cy - radius, cx, cy + radius, fill=COLORS["preview_axis"])
        half = radius / 2
        canvas.create_oval(cx - half, cy - half, cx + half, cy + half,
                           outline=COLORS["preview_circle"], dash=(2, 4))
        canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                           outline=ramp[0], width=2)
        canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill=COLORS["preview_center"], outline="")
        current = None
        for sample in reversed(self.samples):
            age = self.frame - sample.frame
            state = sample.left if column == 0 else sample.right
            if age == 0:
                current = state
            # Exact converter coordinates only; points are never interpolated (T1).
            point = point_position(state, cx, cy, radius)
            if point is not None:
                x, y = point
                if age == 0:
                    canvas.create_oval(x - 7, y - 7, x + 7, y + 7, outline=ramp[0], width=2,
                                       tags=("current_ring",))
                    size, fill = 4, STICK_CORE
                else:
                    size, fill = 3, ramp[age]
                canvas.create_oval(x - size, y - size, x + size, y + size,
                                   fill=fill, outline="", tags=("sample", f"age{age}"))

        def display(value, scale=1):
            return "—" if value is None else f"{value / scale:.3g}"

        if current is None:
            text = "x: —  y: —\nr: —  θ: —"
        else:
            text = (f"x: {display(current.x, STICK_SCALE)}  y: {display(current.y, STICK_SCALE)}\n"
                    f"r: {display(current.radius)}  θ: {display(current.angle)}°")
        self.values[column].configure(text=text)
