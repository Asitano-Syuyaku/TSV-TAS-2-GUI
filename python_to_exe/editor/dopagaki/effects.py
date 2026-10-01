"""A small cell-border pulse, using only a Canvas item and visual coordinates."""

import math
import weakref
from tkinter import TclError

from .motion import Intensity, MotionController
from .theme import PULSE_COLORS, COMMIT_COLORS, blend_color
from .micro import EffectBatch, RingPulse, WidgetPulse, duration_for
from .hype import Hype, curve
from .juice import JuiceEffect
from .particles import ParticleSystem, spawn_count


class ActiveCellPulse:
    duration = 0.180

    def __init__(self, canvas, box, strength, *, duration=0.180, colors=PULSE_COLORS, amplitude=2.0):
        self._canvas = weakref.ref(canvas)
        self._box = box
        self._strength = strength
        self._item = None
        self._progress = 0.0
        self.duration = duration
        self._colors = colors
        self._amplitude = amplitude
        self.cell = None

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
        options = dict(outline=blend_color(*self._colors, amount),
                       width=2.0 + self._amplitude * amount, state="normal")
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
    """D0/D1 targets and bounded D2 juice sharing the original controller."""

    def __init__(self, scheduler, canvas, intensity=Intensity.MID, *, clock=None):
        self.motion = MotionController(scheduler, intensity, clock=clock)
        self._canvas = weakref.ref(canvas)
        self._last_cell = None
        self._clock = self.motion._clock
        self._closed = False
        self.hype = Hype(self._clock)
        self.particles = None  # D2 surfaces attach only in a full Dopagaki Editor.
        self._meter = self._border = None
        self._base_border = "#3b5272"
        self._reward_until = self._accent_until = 0.0

    def attach_juice(self, meter, border, *, left=0, top=0):
        if self.particles is not None:
            self.remove("juice")
            self.particles.close()
        self.particles = ParticleSystem()
        self.particles.register("grid", self._canvas(), left=left, top=top,
                                background=self._canvas().cget("background"), dark=False)
        self.particles.register("meter", meter)
        self._meter, self._border = weakref.ref(meter), weakref.ref(border)
        self._base_border = border.cget("highlightbackground")
        self.set_intensity(self.motion.intensity)

    def set_intensity(self, level):
        if Intensity(level) != self.motion.intensity:
            self._reward_until = self._accent_until = 0.0
        self.motion.set_intensity(level)
        meter = self._meter() if self._meter is not None else None
        if meter is not None:
            meter.set_level(self.motion.intensity)
            meter.paint(self.hype.value(), self.motion.intensity)

    def interaction(self, event, *, origin=None, surface="grid", direction=(0.8, -1.0)):
        if self._closed or self.particles is None or self.motion.intensity == Intensity.OFF:
            return
        now = self._clock()
        value, rewards, admitted = self.hype.add(event, now)
        if admitted and origin is not None:
            self.particles.spawn(surface, origin, spawn_count(event, self.motion.intensity, value),
                                 self.motion.intensity, value, now, direction=direction)
        if rewards:
            self._reward_until = now + 0.320
        if value >= 0.65 and event != "cell" and admitted:
            self._accent_until = now + (0.280 if value >= 0.80 else 0.180)
        if rewards and max(rewards) >= 0.75:
            self._accent_until = now + 0.280
        self._refresh_juice(now)

    def _refresh_juice(self, now):
        old = self.effect_for("juice")
        if old is not None:
            old.handoff()
        self.play_effect("juice", JuiceEffect(
            self.particles, self.hype, self._meter, self._border, self._base_border,
            self.motion.intensity, self._clock, now, self._reward_until, self._accent_until))

    def micro_strength(self):
        boost = 0.16 * curve(self.hype.value()) if self.particles is not None else 0.0
        return min(1.0, self.motion.intensity.multiplier * (1 + boost))

    def effect_for(self, key):
        batch = self.motion.effect
        return batch.tracks.get(key, (None, 0))[0] if isinstance(batch, EffectBatch) else None

    def remove(self, key):
        batch = self.motion.effect
        if isinstance(batch, EffectBatch):
            entry = batch.tracks.pop(key, None)
            if entry is not None:
                entry[0].finish()
            if not batch.tracks:
                self.motion.clear()
            else:
                # A removed long pulse must not leave ticks running after the
                # remaining targets finish. Keep the controller's original
                # time origin and shorten just this finite batch's deadline.
                batch.duration = max(start + effect.duration
                                     for effect, start in batch.tracks.values()) - self.motion._started_at

    def play_effect(self, key, effect):
        if self._closed or self.motion.intensity == Intensity.OFF:
            effect.finish()
            return False
        now = self._clock()
        batch = self.motion.effect
        tracks = batch.take() if isinstance(batch, EffectBatch) else {}
        for old_key, (old, start) in tuple(tracks.items()):
            if old_key == key or now >= start + old.duration:
                old.finish()
                del tracks[old_key]
        if len(tracks) >= 8:
            oldest = min(tracks, key=lambda name: tracks[name][1])
            tracks.pop(oldest)[0].finish()
        tracks[key] = (effect, now)
        return self.motion.play(EffectBatch(tracks, self._clock, now))

    def pulse_widget(self, key, widget, kind, *, ink=False):
        self.remove(key)  # Restore styles before sampling the replacement's base.
        if not self._closed and self.motion.intensity != Intensity.OFF:
            self.play_effect(key, WidgetPulse(widget, self.micro_strength(),
                                             duration_for(self.motion.intensity, kind), ink=ink))

    def pulse_ring(self, column, canvas, plot_height):
        if not self._closed and self.motion.intensity != Intensity.OFF:
            self.play_effect(f"stick{column}", RingPulse(canvas, self.micro_strength(),
                                                        duration_for(self.motion.intensity, "stick"), plot_height))

    def commit(self, cell, box):
        if self._closed or box is None or self.motion.intensity == Intensity.OFF:
            return
        canvas = self._canvas()
        if canvas is not None:
            self.interaction("commit", origin=(box[2] - 5, box[1] + 5))
            pulse = ActiveCellPulse(canvas, box, self.micro_strength(),
                                    duration=duration_for(self.motion.intensity, "commit"),
                                    colors=COMMIT_COLORS, amplitude=3.0)
            pulse.cell = cell
            self.play_effect("commit", pulse)

    def sync_cell(self, cell, box):
        changed = self._last_cell is not None and cell != self._last_cell
        self._last_cell = cell
        if changed:
            canvas = self._canvas() if self._canvas is not None else None
            if canvas is not None and box is not None and self.motion.intensity != Intensity.OFF:
                self.interaction("cell", origin=(box[2] - 5, box[1] + 5))
                amplitude = 2.0 + (0.8 * curve(self.hype.value()) if self.particles is not None else 0.0)
                self.play_effect("cell", ActiveCellPulse(canvas, box, self.micro_strength(),
                                                        duration=duration_for(self.motion.intensity, "cell"),
                                                        amplitude=amplitude))
            else:
                self.remove("cell")
        elif self.effect_for("cell") is not None:
            self.effect_for("cell").relocate(box)

    def close(self):
        self._closed = True
        self.motion.close()
        if self.particles is not None:
            self.particles.close()
        if self.hype is not None:
            self.hype.close()
        self.particles = self.hype = self._meter = self._border = None
        self._clock = None
        self._canvas = None
        self._last_cell = None
