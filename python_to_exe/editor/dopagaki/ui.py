"""Thin Tk adapters for the existing grid/editor; all editing logic is inherited."""

import tkinter as tk

from ..grid import TableGrid
from ..window import EditorWindow
from . import theme
from .effects import CellEffects
from .motion import Intensity


class DopagakiTableGrid(TableGrid):
    ui_theme = theme

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.effects = CellEffects(self, self.canvas)
        self.bind("<Unmap>", self._pause_effects)

    def _visible_active_box(self):
        x1, y1, x2, y2 = self._cell_box(*self.selected)
        x0, y0 = self.canvas.canvasx(0), self.canvas.canvasy(0)
        x1 = max(x1, x0 + self.gutter_width) + 2
        y1 = max(y1, y0 + self.header_height) + 2
        x2 = min(x2, x0 + self.canvas.winfo_width()) - 2
        y2 = min(y2, y0 + self.canvas.winfo_height()) - 2
        return (x1, y1, x2, y2) if x1 < x2 and y1 < y2 else None

    def _draw_visible(self):
        super()._draw_visible()
        effects = getattr(self, "effects", None)
        if effects is not None and self.winfo_exists():
            # The normal draw/selection path remains authoritative. Only observe
            # its result, including clipping after scroll/column resize.
            effects.sync_cell(self.selected, self._visible_active_box() if self.winfo_ismapped() else None)

    def _pause_effects(self, event):
        if event.widget is self and self.effects is not None:
            self.effects.motion.clear()

    def close_effects(self):
        effects, self.effects = getattr(self, "effects", None), None
        if effects is not None:
            effects.close()

    def _on_destroy(self, event):
        if event.widget is self:
            self.close_effects()
            # A Tk Variable owns its trace command independently of widgets.
            # Removing widget commands alone leaves this callback holding the
            # grid and its Editor after a cell has been edited.
            value = getattr(self, "_entry_value", None)
            trace = getattr(self, "_entry_value_trace", None)
            if value is not None and trace is not None:
                try:
                    value.trace_remove("write", trace)
                except tk.TclError:
                    pass
            self._entry_value_trace = None
            self._entry_value = None
        super()._on_destroy(event)


class DopagakiEditorWindow(EditorWindow):
    ui_theme = theme
    table_grid_class = DopagakiTableGrid

    def __init__(self, master, language="en", *args, **kwargs):
        super().__init__(master, language, *args, **kwargs)
        self._motion_intensity = tk.StringVar(
            self, value=self.settings.get("dopagaki_intensity", "MID"))
        self.table_grid.effects.motion.set_intensity(self._motion_intensity.get())
        menu = self.nametowidget(self.cget("menu"))
        motion_menu = tk.Menu(menu, tearoff=False, background=theme.COLORS["panel_background"],
                              foreground=theme.COLORS["text"],
                              activebackground=theme.COLORS["accent"],
                              activeforeground=theme.COLORS["panel_background"])
        for level in Intensity:
            motion_menu.add_radiobutton(label=level.value, value=level.value,
                                       variable=self._motion_intensity,
                                       command=self._intensity_changed)
        label = "演出の強さ" if language == "ja" else "Motion intensity"
        menu.add_cascade(label="Dopagaki: " + label, menu=motion_menu)

    def _intensity_changed(self):
        level = Intensity(self._motion_intensity.get())
        self.table_grid.effects.motion.set_intensity(level)
        self.settings.update(dopagaki_intensity=level.value)

    def destroy(self):
        grid = getattr(self, "table_grid", None)
        if grid is not None:
            grid.close_effects()
        super().destroy()

    def _on_destroy(self, event):
        if event.widget is self:
            grid = getattr(self, "table_grid", None)
            if grid is not None:
                grid.close_effects()
            self._motion_intensity = None
        super()._on_destroy(event)
