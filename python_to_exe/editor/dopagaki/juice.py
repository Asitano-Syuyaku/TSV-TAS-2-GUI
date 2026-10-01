"""Small heat meter and the eighth finite batch slot for D2 additions."""

import tkinter as tk
import weakref

from . import theme
from .hype import curve
from .motion import Intensity


class HypeMeter(tk.Canvas):
    """A 14px Palette strip, updated only by interactions/active animations.

    Its last sample stays static at idle. The next interaction samples lazy
    decay; this widget never schedules a decay/animation callback of its own.
    """

    def __init__(self, master, font, before):
        super().__init__(master, height=14, highlightthickness=0, borderwidth=0,
                         takefocus=False, background=theme.COLORS["panel_background"])
        self._before = weakref.ref(before)
        self._value, self._level, self._reward = 0.0, Intensity.MID, False
        self._painted = None
        self._label = self.create_text(2, 7, anchor="w", text="HYPE", font=font)
        self._track = self.create_rectangle(78, 5, 79, 10, outline="")
        self._fill = self.create_rectangle(78, 5, 78, 10, outline="")
        self.bind("<Configure>", self._resized)

    def set_level(self, level):
        if level == Intensity.OFF:
            self.pack_forget()
        elif self._before() is not None:
            self.pack(before=self._before(), fill="x", padx=6, pady=(0, 2))
        self.paint(self._value, level, False)

    def _resized(self, _event):
        self.paint(self._value, self._level, self._reward)

    def paint(self, value, level, reward=False):
        self._value, self._level, self._reward = value, level, reward
        width = max(80, self.winfo_width() - 3)
        heat_color = theme.blend_color(theme.HYPE_COLORS[0], theme.HYPE_COLORS[1], value)
        if value >= 0.75:
            heat_color = theme.blend_color(theme.HYPE_COLORS[1], theme.HYPE_COLORS[2], (value - 0.75) * 4)
        color = theme.blend_color(theme.COLORS["muted_text"], heat_color,
                                  level.multiplier * (0.35 + 0.65 * curve(value)))
        fill = 78 + round((width - 78) * value)
        state = width, fill, color, reward
        previous = self._painted
        if state == previous:
            return
        if previous is None or width != previous[0]:
            self.coords(self._track, 78, 5, width, 10)
            self.itemconfigure(self._track, fill=theme.COLORS["subtle_border"])
        if previous is None or fill != previous[1]:
            self.coords(self._fill, 78, 5, fill, 10)
        if previous is None or color != previous[2]:
            self.itemconfigure(self._fill, fill=color)
            self.itemconfigure(self._label, fill=color)
        if previous is None or reward != previous[3]:
            self.itemconfigure(self._label, text="HYPE UP" if reward else "HYPE")
        self._painted = state


class JuiceEffect:
    """A finite facade; particles retain their own absolute births on handoff.

    The manager keeps the bounded particle system/model, never this effect.
    A replaced facade detaches before finish, so it neither clears transferred
    particles nor retains completed-effect references. All Tk targets are weak.
    """

    def __init__(self, particles, hype, meter, border, base_border, level, clock,
                 now, reward_until, accent_until, *, ritual=None):
        self._particles = particles
        self._hype = weakref.ref(hype)
        self._meter, self._border = meter, border
        self._base_border, self._level = base_border, level
        self._clock = clock
        self._ritual = ritual
        self._reward_until, self._accent_until = reward_until, accent_until
        view = ritual() if ritual is not None else None
        self.duration = max(now + 0.220, particles.deadline, reward_until, accent_until,
                            view.deadline if view is not None else 0.0) - now

    def render(self, _progress):
        now = self._clock()
        self._particles.render(now)
        view = self._ritual() if self._ritual is not None else None
        if view is not None:
            view.render(now)
        hype = self._hype()
        value = hype.value(now) if hype is not None else 0.0
        meter = self._meter() if self._meter is not None else None
        if meter is not None:
            meter.paint(value, self._level, now < self._reward_until)
        border = self._border() if self._border is not None else None
        if border is not None:
            amount = (max(0.0, (self._accent_until - now) / 0.280)
                      if now < self._accent_until else 0.0)
            amount = min(1.0, amount) * self._level.multiplier * curve(value)
            color = theme.HYPE_COLORS[2] if value >= 0.80 else theme.HYPE_COLORS[1]
            border.configure(highlightbackground=theme.blend_color(self._base_border, color, amount))

    def handoff(self):
        self._particles = self._hype = self._meter = self._border = self._clock = self._ritual = None

    def finish(self):
        view = self._ritual() if self._ritual is not None else None
        if view is not None:
            view.complete_animation()
        if self._particles is not None:
            self._particles.clear()
        border = self._border() if self._border is not None else None
        if border is not None:
            try:
                border.configure(highlightbackground=self._base_border)
            except tk.TclError:
                pass
        meter = self._meter() if self._meter is not None else None
        hype = self._hype() if self._hype is not None else None
        if meter is not None and hype is not None:
            try:
                meter.paint(hype.value(), self._level, False)
            except tk.TclError:
                pass
        self.handoff()
