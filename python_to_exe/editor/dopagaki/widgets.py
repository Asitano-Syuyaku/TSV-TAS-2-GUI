"""D1 presentation adapters: keep the shared Frame/Stick values authoritative."""

import tkinter as tk
import weakref

from ..stick_preview import StickPreview, PLOT_HEIGHT
from . import theme
from .micro import ValuePulses, WidgetPulse, duration_for
from .motion import Intensity


class FrameValues(tk.Frame):
    """Display the existing status string with independently colored value labels.

    This adapter only splits the shared editor's formatted presentation string;
    it never computes frame numbers or accesses the document/analysis cache.
    """

    def __init__(self, master, fonts, effects, text):
        super().__init__(master, background=theme.COLORS["secondary_background"])
        self._effects = weakref.ref(effects)
        self._text = ""
        self._values = None
        options = theme.label_options("secondary_background", "frame_info", fonts)
        self.hint = tk.Label(self, **options)
        self.fields = tk.Frame(self, background=theme.COLORS["secondary_background"])
        self.prefixes, self.value_labels = [], []
        for index in range(4):
            if index:
                tk.Label(self.fields, text=" | ", **options).pack(side="left")
            prefix = tk.Label(self.fields, **options)
            value = tk.Label(self.fields, **options)
            prefix.pack(side="left")
            value.pack(side="left")
            self.prefixes.append(prefix)
            self.value_labels.append(value)
        self.configure(text=text)

    def configure(self, cnf=None, **kwargs):
        if "text" not in kwargs:
            return super().configure(cnf, **kwargs)
        text = kwargs.pop("text")
        self._text = text
        parts = text.split(" | ")
        if len(parts) != 4 or any(": " not in part for part in parts):
            effects = self._effects()
            if effects is not None:
                effects.remove("frame")
            self.fields.pack_forget()
            self.hint.configure(text=text)
            self.hint.pack()
        else:
            pairs = [part.rsplit(": ", 1) for part in parts]
            values = tuple(value for _prefix, value in pairs)
            changed = ([index for index in range(4) if self._values[index] != values[index]]
                       if self._values is not None else [])
            self.hint.pack_forget()
            self.fields.pack()
            for index, (prefix, value) in enumerate(pairs):
                self.prefixes[index].configure(text=prefix + ": ")
                self.value_labels[index].configure(text=value)
            self._values = values
            effects = self._effects()
            if changed and effects is not None:
                effects.remove("frame")
                if effects.motion.intensity != Intensity.OFF:
                    effects.play_effect("frame", ValuePulses([
                        WidgetPulse(self.value_labels[index], effects.micro_strength(),
                                    duration_for(effects.motion.intensity, "frame"), ink=True)
                        for index in changed]))
        if kwargs or cnf:
            return super().configure(cnf, **kwargs)

    config = configure

    def cget(self, key):
        return self._text if key == "text" else super().cget(key)


class DopagakiStickPreview(StickPreview):
    def attach_effects(self, effects):
        self._effects = weakref.ref(effects)
        self.bind("<Unmap>", self._pause_rings)
        if effects.particles is not None:
            for column, canvas in enumerate(self.plots):
                effects.particles.register(f"stick{column}", canvas)

    def _manager(self):
        reference = getattr(self, "_effects", None)
        return reference() if reference is not None else None

    def _pause_rings(self, event):
        effects = self._manager()
        if event.widget is self and effects is not None:
            for column in range(2):
                effects.remove(f"stick{column}")
                if effects.particles is not None:
                    effects.particles.clear_surface(f"stick{column}")

    def _draw(self, column):
        effects = self._manager()
        ring = effects.effect_for(f"stick{column}") if effects is not None else None
        if ring is not None:
            ring.invalidate()
        if effects is not None and effects.particles is not None:
            effects.particles.invalidate(f"stick{column}")
        super()._draw(column)
        if ring is not None:
            ring.repaint()
        if effects is not None and effects.particles is not None and effects.particles.particles:
            effects.particles.render(effects._clock(), only=f"stick{column}")

    def pulse(self, column):
        effects = self._manager()
        if effects is not None and self.winfo_ismapped():
            width = max(self.plots[column].winfo_width(), 160)
            sign = -1 if column == 0 else 1
            radius = min(width, PLOT_HEIGHT) / 2 - 10
            effects.interaction("stick", surface=f"stick{column}",
                                origin=(width / 2 + sign * radius * 0.70, PLOT_HEIGHT / 2 - radius * 0.65),
                                direction=(sign, -0.45))
            effects.pulse_ring(column, self.plots[column], PLOT_HEIGHT)
