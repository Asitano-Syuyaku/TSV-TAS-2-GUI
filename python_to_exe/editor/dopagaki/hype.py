"""Ephemeral UI heat: a monotonic, lazy decay model with no Tk timers."""

import math
import time


GAINS = {"cell": 0.006, "commit": 0.04, "palette": 0.06, "stick": 0.07,
         "page": 0.015, "jump": 0.07, "operation": 0.08}
THRESHOLDS = (0.25, 0.50, 0.75, 0.90)


def curve(value):
    return 0.08 + 0.92 * min(1.0, max(0.0, value)) ** 1.3


class Hype:
    """One scalar and four latches, independent of settings/document/history.

    Arrow autorepeat is admitted at most once per 120ms. Even continuous
    movement's maximum gain rate is below the five-second decay equilibrium
    needed to reach high heat. Other meaningful operations retain their gains.
    """

    __slots__ = ("_clock", "_value", "_at", "_last_move", "_latched",
                 "half_life", "__weakref__")

    def __init__(self, clock=None, *, half_life=5.0):
        if not math.isfinite(half_life) or half_life <= 0:
            raise ValueError("half_life must be finite and positive")
        self._clock = time.monotonic if clock is None else clock
        self.half_life = half_life
        self._value = 0.0
        self._at = self._clock()
        self._last_move = -math.inf
        self._latched = set()

    def value(self, now=None):
        if self._clock is None:
            return 0.0
        now = self._clock() if now is None else now
        value = self._value * 2 ** (-max(0.0, now - self._at) / self.half_life)
        return 0.0 if value < 0.0005 else value

    def add(self, event, now=None):
        """Return (current heat, newly crossed milestones, admitted event)."""
        if self._clock is None:
            return 0.0, (), False
        gain = GAINS[event]
        now = self._clock() if now is None else now
        before = self.value(now)
        self._latched.difference_update(threshold for threshold in THRESHOLDS
                                        if before <= threshold - 0.08)
        admitted = event != "cell" or now - self._last_move >= 0.120
        if event == "cell" and admitted:
            self._last_move = now
        self._value = min(1.0, before + (gain if admitted else 0.0))
        self._at = now
        rewards = tuple(threshold for threshold in THRESHOLDS
                        if before < threshold <= self._value and threshold not in self._latched)
        self._latched.update(rewards)
        return self._value, rewards, admitted

    def close(self):
        self._clock = None
        self._value = 0.0
        self._latched.clear()
