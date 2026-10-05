"""HEAT / COMBO / DOPA / ROUND for one Editor session (dopagaki3.md §7.3).

Pure state with injected time. These are game numbers (T6): they never enter
the document, Undo, Recovery or settings. Frame totals arrive here only after
the converter confirmed them; this module never derives frame data itself.
"""

from dataclasses import dataclass
from typing import Optional


COMBO_WINDOW = 3.0
HEAT_N = 30
# Editor actions are small, so EXTRA rises every 10 confirmations (not skill's 3).
EX_STEP = 10
MAX_COMBO_BONUS = 60
# Session milestones on converter-confirmed totals (1 minute = 3600f @60fps).
MILESTONES = (1000, 3600, 10000, 18000, 100000)
SHOUT_TIERS = {5: 0, 10: 1, 20: 2, 30: 3, 50: 4, 75: 5, 100: 6}


def intensity(actions, n=HEAT_N):
    """Skill's Dopa.E for the round, then extraE once the round passes N."""
    actions = max(0, actions)
    if actions >= n:
        return 1 + min(0.5, ((actions - n) // EX_STEP) * 0.1)
    if n <= 1:
        return 1.0
    return 0.08 + 0.92 * (actions / (n - 1)) ** 1.3


def extra_tier(actions, n=HEAT_N):
    return 0 if actions < n else 1 + (actions - n) // EX_STEP


def shout_tier(combo):
    """Ladder tier for this combo count, or None between milestones (§7.4)."""
    if combo in SHOUT_TIERS:
        return SHOUT_TIERS[combo]
    if combo > 100 and combo % 50 == 0:
        return 6
    return None


@dataclass(frozen=True)
class Reward:
    gain: int
    dopa: int
    combo: int
    multiplier: float
    intensity: float
    extra: int
    shout: Optional[int]
    segments: int
    level_up: bool


@dataclass(frozen=True)
class Confirmation:
    """A converter-confirmed total compared with the previous confirmed one."""
    total: int
    delta: Optional[int]
    milestone: Optional[int]


class HeatState:
    def __init__(self):
        self.dopa = 0
        self.round = 1
        self.actions = 0
        self.combo = 0
        self._last = None
        self._baseline = None
        self._milestones = set()
        self._round_gain = 0

    @property
    def intensity(self):
        return intensity(self.actions)

    @property
    def extra(self):
        return extra_tier(self.actions)

    @property
    def segments(self):
        """Lit HEAT segments, 0-10."""
        return max(0, min(10, int(min(1.0, self.intensity) * 10 + 1e-9)))

    @property
    def multiplier(self):
        return 1 + 0.05 * min(self.combo, MAX_COMBO_BONUS)

    def productive(self, now):
        """One action that really changed the document."""
        if self._last is not None and now - self._last <= COMBO_WINDOW:
            self.combo += 1
        else:
            self.combo = 1
        self._last = now
        before = self.segments
        self.actions += 1
        heat, extra = self.intensity, self.extra
        gain = round(10 * self.multiplier * (1 + 2 * heat) * (1 + 0.5 * extra))
        self.dopa += gain
        self._round_gain += gain
        return Reward(gain, self.dopa, self.combo, self.multiplier, heat, extra,
                      shout_tier(self.combo), self.segments, self.segments > before)

    def combo_alive(self, now):
        return (self.combo >= 2 and self._last is not None and
                now - self._last <= COMBO_WINDOW)

    def reset_combo(self):
        """Failures reset only the combo; HEAT and DOPA never drop (§7.3)."""
        self.combo = 0

    def document_replaced(self):
        """New/Open: a fresh round of the same session; DOPA stays."""
        self.actions = 0
        self.combo = 0
        self._last = None
        self._baseline = None
        self._round_gain = 0

    def settle(self):
        """F5/F8 success (§7.3): cash the round in and start the next one quietly.

        Returns the bonus, or None for a round without any productive action.
        """
        if not self.actions:
            return None
        bonus = round(self._round_gain * (0.5 + self.intensity))
        self.dopa += bonus
        self.round += 1
        self.actions = 0
        self.combo = 0
        self._last = None
        self._round_gain = 0
        return bonus

    def confirmed_total(self, total):
        """Delta and milestone only against a previous confirmed total.

        The first confirmation of a document is its baseline: opening a long
        script is not an achievement, and no delta exists to show yet.
        """
        previous, self._baseline = self._baseline, total
        if previous is None:
            return Confirmation(total, None, None)
        crossed = [mark for mark in MILESTONES
                   if previous < mark <= total and mark not in self._milestones]
        self._milestones.update(crossed)
        return Confirmation(total, total - previous, max(crossed) if crossed else None)


def format_dopa(value, language):
    """Inflated game number: JA 万/億/兆 like the skill's Dopa.fmt, EN K/M/B."""
    value = int(round(value))
    magnitude = abs(value)

    def unit(scaled, suffix):
        if scaled < 10:
            return f"{int(scaled * 10) / 10:.1f}{suffix}"
        return f"{int(scaled)}{suffix}"

    if language == "ja":
        for base, suffix in ((10 ** 12, "兆"), (10 ** 8, "億"), (10 ** 4, "万")):
            if magnitude >= base:
                return ("-" if value < 0 else "") + unit(magnitude / base, suffix)
        return f"{value:,}"
    for base, suffix in ((10 ** 9, "B"), (10 ** 6, "M"), (10 ** 5, "K")):
        if magnitude >= base:
            return ("-" if value < 0 else "") + unit(magnitude / base, suffix)
    return f"{value:,}"


def frames_as_time(frames, fps=60):
    """Converted display only (§6.1): 4212f -> 1:10.20 at 60fps."""
    hundredths = frames * 100 // fps
    seconds, hundredths = divmod(hundredths, 100)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}.{hundredths:02d}"
    return f"{minutes}:{seconds:02d}.{hundredths:02d}"
