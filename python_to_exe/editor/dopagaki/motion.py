"""A finite, single-effect monotonic clock driven by Tk's after scheduler."""

from enum import Enum
import math
import time
import weakref
from tkinter import TclError


class Intensity(str, Enum):
    OFF = "OFF"
    LOW = "LOW"
    MID = "MID"
    FULL = "FULL"

    @property
    def multiplier(self):
        return {"OFF": 0.0, "LOW": 0.28, "MID": 0.62, "FULL": 1.0}[self.value]


class MotionController:
    """Own one effect (duration/render/finish) and at most one pending callback.

    Playing replaces the previous effect. No ticks are scheduled while idle.
    Scheduler and scheduled closure references are weak, so a retained timer
    cannot keep a closed Editor alive. Generation guards reject stale callbacks.
    """

    def __init__(self, scheduler, intensity=Intensity.MID, *, clock=None, tick_ms=16):
        if type(tick_ms) is not int or tick_ms < 1:
            raise ValueError("tick_ms must be a positive integer")
        self._scheduler = weakref.ref(scheduler)
        self._clock = time.monotonic if clock is None else clock
        self._tick_ms = tick_ms
        self.intensity = Intensity(intensity)
        self._effect = None
        self._job = None
        self._generation = 0
        self._started_at = 0.0
        self._closed = False

    @property
    def effect(self):
        return self._effect

    @property
    def pending(self):
        return self._job is not None

    def set_intensity(self, intensity):
        intensity = Intensity(intensity)
        if intensity != self.intensity:
            self.intensity = intensity
            self.clear()

    def play(self, effect):
        self.clear()
        if self._closed or self.intensity == Intensity.OFF:
            effect.finish()
            return False
        if not math.isfinite(effect.duration) or effect.duration <= 0:
            effect.finish()
            raise ValueError("effects must have a finite, positive duration")
        self._effect = effect
        self._started_at = self._clock()
        self._render(0.0)
        if self._effect is not None:
            self._schedule()
        return self._effect is not None

    def clear(self):
        self._generation += 1
        job, self._job = self._job, None
        scheduler = self._scheduler() if self._scheduler is not None else None
        if job is not None and scheduler is not None:
            try:
                scheduler.after_cancel(job)
            except TclError:
                pass  # Tk may already have destroyed the scheduler.
        effect, self._effect = self._effect, None
        if effect is not None:
            try:
                effect.finish()
            except TclError:
                pass

    def close(self):
        self._closed = True
        self.clear()
        self._scheduler = None
        self._clock = None

    def _render(self, progress):
        try:
            self._effect.render(progress)
        except TclError:
            self.close()
        except Exception:
            self.clear()
            raise

    def _schedule(self):
        scheduler = self._scheduler() if self._scheduler is not None else None
        if scheduler is None:
            self.close()
            return
        reference, generation = weakref.ref(self), self._generation

        def tick():
            controller = reference()
            if controller is not None:
                controller._tick(generation)

        try:
            self._job = scheduler.after(self._tick_ms, tick)
        except TclError:
            self.close()

    def _tick(self, generation):
        if generation != self._generation or self._closed or self._effect is None:
            return
        self._job = None
        progress = min(1.0, max(0.0, (self._clock() - self._started_at) / self._effect.duration))
        self._render(progress)
        if generation != self._generation or self._effect is None:
            return
        if progress >= 1.0:
            self.clear()
        else:
            self._schedule()
