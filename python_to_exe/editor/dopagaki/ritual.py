"""F5's sparse monotonic timeline, independent of converter/document state."""

from dataclasses import dataclass
from enum import Enum
import math
import time
import weakref
from tkinter import TclError

from .audio import AudioConfig, AudioBackend
from .motion import Intensity


DROP_SECONDS = 21.506


class RitualState(str, Enum):
    IDLE = "IDLE"
    PRELUDE = "PRELUDE"
    SUCCESS_READY = "SUCCESS_READY"
    WAITING_FOR_CONVERTER = "WAITING_FOR_CONVERTER"
    SUCCESS_FINALE = "SUCCESS_FINALE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class RitualTimeline:
    drop: float = DROP_SECONDS
    countdown_step: float = 1.0
    build_events: tuple = ((6.0, "build"), (9.0, "spark"), (12.0, "tension"),
                           (15.0, "spark"), (17.0, "spark"))

    def __post_init__(self):
        if (not math.isfinite(self.drop) or not math.isfinite(self.countdown_step)
                or self.countdown_step <= 0 or self.drop <= 3 * self.countdown_step):
            raise ValueError("invalid finite ritual timeline")
        if any(not math.isfinite(at) or not 0 < at < self.drop - 3 * self.countdown_step
               for at, _event in self.build_events):
            raise ValueError("build events must precede countdown")

    def events(self, config):
        offset = config.sync_offset_ms / 1000
        return sorted((*((at + offset, event) for at, event in self.build_events),
                       (self.drop - 3 * self.countdown_step + offset, "3"),
                       (self.drop - 2 * self.countdown_step + offset, "2"),
                       (self.drop - self.countdown_step + offset, "1"),
                       (self.drop + offset, "drop"),
                       (self.drop + config.tail_seconds + offset, "settle")))


class ConvertRitual:
    """One reused ritual, one pending phase callback, weak generation-bound receiver.

    after() only wakes for an absolute next event. A delayed wake shows the
    current phase and skips missed countdowns/sparks. MotionController handles
    the view's finite animations separately, including when waiting for a late
    converter. The output/result is never held here, only its success boolean.
    """

    def __init__(self, scheduler, view, *, backend=None, config=None, timeline=None, clock=None):
        self._scheduler = weakref.ref(scheduler)
        self._clock = time.monotonic if clock is None else clock
        self.view = view
        self.backend = AudioBackend() if backend is None else backend
        self.config = AudioConfig() if config is None else config
        self.timeline = RitualTimeline() if timeline is None else timeline
        self.state = RitualState.IDLE
        self.generation = 0
        self._ticket = 0
        self._job = None
        self._started_at = None
        self._events = ()
        self._next = 0
        self._result = None
        self._dropped = False
        self._celebrated = False
        self._closed = False
        self.audio_playing = False

    @property
    def pending(self):
        return self._job is not None

    @property
    def elapsed(self):
        return max(0.0, self._clock() - self._started_at) if self._started_at is not None else 0.0

    def _cancel_job(self):
        self._ticket += 1
        job, self._job = self._job, None
        scheduler = self._scheduler() if self._scheduler is not None else None
        if job is not None and scheduler is not None:
            try:
                scheduler.after_cancel(job)
            except TclError:
                pass

    def stop_audio(self):
        self.audio_playing = False
        try:
            self.backend.stop()
        except Exception:
            pass  # Audio failure never becomes a converter failure.

    def cancel(self):
        self.generation += 1
        self._cancel_job()
        self.stop_audio()
        self._started_at = None
        self._events = ()
        self._result = None
        self._dropped = False
        self._celebrated = False
        if self.view is not None:
            try:
                self.view.clear()
            except TclError:
                pass  # Direct Tcl/root destruction may have removed Canvas commands.
        self.state = RitualState.CANCELLED

    def start(self, level=Intensity.MID):
        self.cancel()
        if self._closed or Intensity(level) == Intensity.OFF:
            return self.generation
        self._started_at = self._clock()
        self._events = self.timeline.events(self.config)
        self._next = 0
        self.state = RitualState.PRELUDE
        if self.config.enabled:
            try:
                self.audio_playing = bool(self.backend.play(self.config.media_path))
            except Exception:
                self.stop_audio()
        self.view.show("start", 0.0)
        self._advance()
        return self.generation

    def receiver(self):
        reference, generation = weakref.ref(self), self.generation

        def receive(success, _payload=None):
            ritual = reference()
            if ritual is not None:
                ritual.result(generation, success)

        return receive

    def result(self, generation, success):
        if (self._closed or generation != self.generation or self._started_at is None
                or self._result is not None):
            return False
        self._result = bool(success)
        if not success:
            self._cancel_job()
            self.stop_audio()
            self.view.clear()
            self.state = RitualState.FAILED
            self.view.show("failure", 0.0)
            return True
        if self._dropped:
            self._success()
        elif self._clock() >= self._started_at + self.timeline.drop + self.config.sync_offset_ms / 1000:
            self._advance()
            if not self._celebrated:
                self._success()
        else:
            self.state = RitualState.SUCCESS_READY
            self.view.show("ready", self.elapsed / self.timeline.drop)
        return True

    def _success(self):
        if self._celebrated:
            return
        self._celebrated = True
        self.state = RitualState.SUCCESS_FINALE
        self.view.show("success", 1.0)

    def _advance(self):
        self._cancel_job()
        elapsed = self.elapsed
        now = self._clock()
        latest = None
        while self._next < len(self._events) and self._started_at + self._events[self._next][0] <= now:
            latest = self._events[self._next][1]
            self._next += 1
        if self.audio_playing:
            try:
                self.audio_playing = bool(self.backend.poll())
            except Exception:
                self.stop_audio()
        if latest == "settle":
            self._dropped = True
            self.stop_audio()
            self.state = (RitualState.SUCCESS_FINALE if self._result is True
                          else RitualState.WAITING_FOR_CONVERTER)
            self.view.show("settle", 1.0, pending=self._result is None)
        elif latest == "drop":
            self._dropped = True
            self.view.show("drop", 1.0)
            if self._result is True:
                self._success()
            else:
                self.state = RitualState.WAITING_FOR_CONVERTER
                self.view.show("pending", 1.0)
            if not self.audio_playing:
                # Finite view cleanup handles the visual end. No eight-second
                # phase callback is needed merely to stop an absent player.
                self._next = len(self._events)
        elif latest is not None:
            self.view.show(latest, min(1.0, max(0.0, elapsed / self.timeline.drop)))
        self._schedule()

    def _schedule(self):
        if self._next >= len(self._events) or self._started_at is None:
            return
        scheduler = self._scheduler() if self._scheduler is not None else None
        if scheduler is None:
            self.close()
            return
        reference, generation, ticket = weakref.ref(self), self.generation, self._ticket
        delay = max(1, math.ceil((self._started_at + self._events[self._next][0] - self._clock()) * 1000))

        def wake():
            ritual = reference()
            if ritual is not None:
                ritual._wake(generation, ticket)

        try:
            self._job = scheduler.after(delay, wake)
        except TclError:
            self.close()

    def _wake(self, generation, ticket):
        if self._closed or generation != self.generation or ticket != self._ticket:
            return
        self._job = None
        self._advance()

    def close(self):
        self.cancel()
        self._closed = True
        try:
            self.backend.close()
        except Exception:
            pass
        self.view = self.backend = self._scheduler = self._clock = None
