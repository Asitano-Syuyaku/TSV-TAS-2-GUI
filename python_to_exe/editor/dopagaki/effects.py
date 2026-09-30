"""A small cell-border pulse, using only a Canvas item and visual coordinates."""

import math
import weakref
from tkinter import TclError

from .motion import Intensity, MotionController
from .theme import PULSE_COLORS


def blend_color(first, second, amount):
    channels = [round(int(first[index:index + 2], 16) * (1 - amount) +
                      int(second[index:index + 2], 16) * amount)
                for index in (1, 3, 5)]
    return "#" + "".join(f"{value:02x}" for value in channels)


class ActiveCellPulse:
    duration = 0.180

    def __init__(self, canvas, box, strength):
        self._canvas = weakref.ref(canvas)
        self._box = box
        self._strength = strength
        self._item = None
        self._progress = 0.0

    def render(self, progress):
        canvas = self._canvas() if self._canvas is not None else None
        if canvas is None:
            return
        self._progress = progress
        if self._box is None:
            if self._item is not None:
                canvas.itemconfigure(self._item, state="hidden")
            return
        # Immediate accent on arrival, then a single smooth crest and fade.
        amount = self._strength * (0.35 * (1 - progress) + 0.65 * math.sin(math.pi * progress))
        options = dict(outline=blend_color(*PULSE_COLORS, amount),
                       width=2.0 + 2.0 * amount, state="normal")
        if self._item is None:
            self._item = canvas.create_rectangle(*self._box, fill="", tags="dopagaki_effect", **options)
        else:
            canvas.coords(self._item, *self._box)
            canvas.itemconfigure(self._item, **options)
        canvas.tag_raise(self._item)

    def relocate(self, box):
        self._box = box
        self.render(self._progress)

    def finish(self):
        canvas = self._canvas() if self._canvas is not None else None
        item, self._item = self._item, None
        self._canvas = None
        self._box = None
        if canvas is not None and item is not None:
            try:
                canvas.delete(item)
            except TclError:
                pass


class CellEffects:
    """Track only the last visual cell and one finite pulse; no Editor reference."""

    def __init__(self, scheduler, canvas, intensity=Intensity.MID, *, clock=None):
        self.motion = MotionController(scheduler, intensity, clock=clock)
        self._canvas = weakref.ref(canvas)
        self._last_cell = None

    def sync_cell(self, cell, box):
        changed = self._last_cell is not None and cell != self._last_cell
        self._last_cell = cell
        if changed:
            canvas = self._canvas() if self._canvas is not None else None
            if canvas is not None and box is not None and self.motion.intensity != Intensity.OFF:
                self.motion.play(ActiveCellPulse(canvas, box, self.motion.intensity.multiplier))
            else:
                self.motion.clear()
        elif self.motion.effect is not None:
            self.motion.effect.relocate(box)

    def close(self):
        self.motion.close()
        self._canvas = None
        self._last_cell = None
