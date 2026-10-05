"""F5 x "Let's Go" choreography (dopagaki3.md §13.3). Pure: time in, events out.

The conversion is never delayed: the track starts with the run, 2 bars before
its drop. Facts appear the moment the Converter reports them (the director
does that before calling `result`). Only the celebration may wait:

- success before the drop: the climax lands on the drop (<= 2 bars of waiting);
- no result yet at the drop: the drop is music energy only, never "CONVERTED";
- success after the drop: the climax lands on the next beat (<= 1 beat);
- failure: the track fades out at once; there is no drop to celebrate;
- the track cannot start, fails, or is muted: nothing waits for it.

After the climax the drop keeps playing for 2 bars, then fades over 1 bar.
"""

import math

from .music import BAR, BEAT, DROP, FADE_BARS, FAIL_FADE, START, TAIL_BARS
from .outcome import FAILED


START_GRACE = 0.6  # The track must reach the output within this, or it is ignored.


class F5Choreography:
    def __init__(self, voice, now, events, hold_visuals=True):
        self.voice = voice
        self.created = now
        self.events = events
        self.hold_visuals = hold_visuals
        self.outcome = None
        self.climaxed = False
        self.dropped = False
        self.held = False
        self.lost = voice is None
        self.ended = False
        self._beat = None
        self._climax_at = None   # Music time of a beat-quantized late climax.
        self._climax_music = None
        self._fading = False

    # Inputs ------------------------------------------------------------------------

    def music_time(self, now):
        voice = self.voice
        if voice is None or voice.started_at is None:
            return None
        return START + (now - voice.started_at)

    def result(self, outcome, now):
        self.outcome = outcome
        if outcome == FAILED:
            self._stop(FAIL_FADE)  # No drop for a failed run.
            return
        if self.lost or not self.hold_visuals:
            self._climax(now)
            return
        position = self.music_time(now)
        if position is not None and position >= DROP:
            beats = math.ceil((position - DROP) / BEAT - 1e-9)
            self._climax_at = DROP + beats * BEAT  # Next beat on the drop's grid.
        # Otherwise tick() lands it on the drop.

    def cancel(self, now, fade=0.08, celebrate=True):
        """Second F5 or mute: a pending celebration happens now. Close: just stop."""
        if celebrate and self.outcome not in (None, FAILED) and not self.climaxed:
            self._climax(now)
        self._stop(fade)

    # Clock ---------------------------------------------------------------------------

    def tick(self, now):
        """Advance; returns False once nothing more will happen on the clock."""
        if self.ended:
            return False
        voice = self.voice
        if not self.lost and (voice.failed or (voice.started_at is None and
                                               now - self.created > START_GRACE)):
            self._lose(now)
            return False
        position = self.music_time(now)
        if position is None:
            return True
        if not self.climaxed and not self.dropped:
            beat = math.floor((position - DROP) / BEAT + 1e-9)
            if beat < 0 and beat != self._beat:
                self._beat = beat
                if self.hold_visuals:
                    self.events.choreo_beat(-beat)
                if beat == -1 and not self.held:
                    self.held = True  # The track's own breath before the drop.
                    if self.hold_visuals:
                        self.events.choreo_hold()
        if position >= DROP and not self.dropped:
            self.dropped = True
            if self.outcome is not None and self.outcome != FAILED and not self.climaxed:
                self._climax(now, position)
            elif self.outcome is None and self.hold_visuals:
                self.events.choreo_drop()  # Music energy only: nothing succeeded yet.
        if self._climax_at is not None and not self.climaxed and position >= self._climax_at:
            self._climax(now, position)
        if self.climaxed and self._climax_music is None:
            self._climax_music = position  # Celebrated before the track was audible.
        if self.climaxed and not self._fading and self._climax_music is not None and \
                position >= self._climax_music + TAIL_BARS * BAR:
            self._stop(FADE_BARS * BAR)
        if voice.done:
            if self.outcome is not None and self.outcome != FAILED and not self.climaxed:
                self._climax(now)  # The track ended first: celebrate without it.
            self.ended = True
            return False
        return True

    # Internals -----------------------------------------------------------------------

    def _climax(self, now, position=None):
        if self.climaxed:
            return
        self.climaxed = True
        self._climax_music = position if position is not None else self.music_time(now)
        self.events.choreo_climax(on_drop=position is not None)

    def _lose(self, now):
        self.lost = True
        if self.outcome is not None and self.outcome != FAILED and not self.climaxed:
            self._climax(now)
        self._stop(0.0)

    def _stop(self, fade):
        voice = self.voice
        if voice is not None and not voice.done:
            if fade > 0:
                voice.fade(fade)
            else:
                voice.done = True
        self._fading = True
        if voice is None or fade <= 0:
            self.ended = True
