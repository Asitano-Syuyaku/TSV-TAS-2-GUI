"""Finite D1 primitives and a bounded group for the unchanged D0 controller."""

import weakref
from tkinter import TclError

from .theme import MICRO_COLORS, MICRO_DURATIONS, blend_color


def duration_for(level, kind):
    return MICRO_DURATIONS[kind][{"OFF": 0, "LOW": 0, "MID": 1, "FULL": 2}[level.value]]


class EffectBatch:
    """At most eight named targets, sharing one MotionController callback.

    Transferring tracks during replacement preserves each effect's absolute
    start time; another operation cannot restart or prolong unrelated effects.
    """

    def __init__(self, tracks, clock, now):
        self.tracks = tracks
        self._clock = clock
        self.duration = max(start + effect.duration for effect, start in tracks.values()) - now

    def take(self):
        tracks, self.tracks = self.tracks, {}
        return tracks

    def render(self, _progress):
        now = self._clock()
        for key, (effect, start) in tuple(self.tracks.items()):
            progress = min(1.0, max(0.0, (now - start) / effect.duration))
            try:
                effect.render(progress)
            except TclError:
                progress = 1.0  # A disappearing target must not stop other UI effects.
            if progress >= 1.0:
                effect.finish()
                del self.tracks[key]

    def finish(self):
        for effect, _start in self.take().values():
            effect.finish()
        self._clock = None


class WidgetPulse:
    """Color-only pulse; restores exact styles, leaving images/fonts/layout alone."""

    def __init__(self, widget, strength, duration, *, ink=False):
        self._widget = weakref.ref(widget)
        self.duration = duration
        self._strength = strength
        names = ("foreground",) if ink else ("background", "activebackground", "highlightbackground")
        self._original = {name: widget.cget(name) for name in names}
        self._ink = ink

    def render(self, progress):
        widget = self._widget() if self._widget is not None else None
        if widget is None:
            return
        amount = self._strength * (1 - progress) ** 1.5
        options = {name: blend_color(color, MICRO_COLORS["ink" if self._ink else
                                                       "ring" if name == "highlightbackground" else "surface"], amount)
                   for name, color in self._original.items()}
        widget.configure(**options)

    def finish(self):
        widget = self._widget() if self._widget is not None else None
        self._widget = None
        if widget is not None:
            try:
                widget.configure(**self._original)
            except TclError:
                pass
        self._original.clear()


class ValuePulses:
    """One slot containing only changed Frame Position values (at most four)."""

    def __init__(self, effects):
        self.effects = effects
        self.duration = max(effect.duration for effect in effects)

    def render(self, progress):
        for effect in self.effects:
            effect.render(progress)

    def finish(self):
        for effect in self.effects:
            effect.finish()
        self.effects.clear()


class RingPulse:
    """A unit-circle border only; never reads or alters resolved stick samples."""

    def __init__(self, canvas, strength, duration, plot_height):
        self._canvas = weakref.ref(canvas)
        self._strength = strength
        self.duration = duration
        self._height = plot_height
        self._item = None
        self._progress = 0.0

    def invalidate(self):
        # The normal preview draw deletes all items. Its adapter calls this
        # before that draw, then recreates only this ring afterward.
        canvas = self._canvas() if self._canvas is not None else None
        if canvas is not None and self._item is not None:
            canvas.delete(self._item)
        self._item = None

    def render(self, progress):
        canvas = self._canvas() if self._canvas is not None else None
        if canvas is None:
            return
        self._progress = progress
        width = max(canvas.winfo_width(), 160)
        cx, cy = width / 2, self._height / 2
        amount = self._strength * (1 - progress) ** 1.5
        radius = min(width, self._height) / 2 - 10 + 3 * amount
        coords = (cx - radius, cy - radius, cx + radius, cy + radius)
        options = dict(outline=blend_color("#34d6eb", MICRO_COLORS["ring"], amount),
                       width=1 + 3 * amount)
        if self._item is None:
            self._item = canvas.create_oval(*coords, fill="", tags="dopagaki_ring", **options)
        else:
            canvas.coords(self._item, *coords)
            canvas.itemconfigure(self._item, **options)
        canvas.tag_raise(self._item)

    def repaint(self):
        self.render(self._progress)

    def finish(self):
        try:
            self.invalidate()
        except TclError:
            pass
        self._canvas = None
