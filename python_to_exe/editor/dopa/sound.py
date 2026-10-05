"""Synthesized sound effects (dopagaki3.md §13, dopagaki-music skill). No Tk, no files in git.

Every effect is generated from code: pure Python oscillators at 24 kHz,
linearly upsampled to the 48 kHz mixer rate, peak-normalized, and cached as
16-bit mono WAV in the user cache. A user override WAV (48 kHz, 16-bit PCM)
with the same name replaces an effect; anything else is ignored.

Musical choices follow the skill: effects sit in D (the F5 track is in D),
pitches climb with the combo, failure is a "ポヨン" bounce in a major context
(never a minor fail sting), and the 確定 sounds are the skill's kyuin / star /
fanfare / coins shapes.
"""

import math
import random
import wave
from array import array
from pathlib import Path


RATE = 48000
SYNTH_RATE = 24000
CACHE_VERSION = "v1"
# D major pentatonic from D5: bright over silence, safe next to the D track.
PIP_STEPS = (74, 76, 78, 81, 83, 86, 88, 90)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _buffer(seconds):
    return [0.0] * int(seconds * SYNTH_RATE)


def _add_tone(out, start, freq, seconds, wave="sine", level=0.3, attack=0.003, tau=0.1,
              sustain=0.0, glide_to=None, glide_seconds=None, vibrato=None, release=0.03):
    """Phase-accumulating oscillator with an attack / exponential decay envelope."""
    begin = int(start * SYNTH_RATE)
    count = min(int(seconds * SYNTH_RATE), len(out) - begin)
    if count <= 0:
        return
    glide = glide_seconds or seconds
    phase = 0.0
    tail = max(1, int(release * SYNTH_RATE))
    for index in range(count):
        t = index / SYNTH_RATE
        f = freq
        if glide_to is not None:
            f = freq * (glide_to / freq) ** min(1.0, t / glide)
        if vibrato is not None and t > vibrato[2]:
            f += vibrato[1] * math.sin(2 * math.pi * vibrato[0] * t)
        phase = (phase + f / SYNTH_RATE) % 1.0
        if wave == "sine":
            sample = math.sin(2 * math.pi * phase)
        elif wave == "square":
            sample = 1.0 if phase < 0.5 else -1.0
        elif wave == "pulse":
            sample = 1.0 if phase < 0.25 else -0.33
        elif wave == "saw":
            sample = 2 * phase - 1
        else:  # triangle
            sample = 4 * abs(phase - 0.5) - 1
        if t < attack:
            gain = t / attack
        else:
            gain = sustain + (1 - sustain) * math.exp(-(t - attack) / tau)
        if index > count - tail:
            gain *= (count - index) / tail
        out[begin + index] += level * gain * sample


def _add_noise(out, start, seconds, level=0.2, seed=0, tau=0.1, attack=0.002, low=0.0,
               high=1.0, rise=False):
    """Filtered noise; `low` is a one-pole high-pass mix, `high` a one-pole low-pass."""
    rng = random.Random(seed)
    begin = int(start * SYNTH_RATE)
    count = min(int(seconds * SYNTH_RATE), len(out) - begin)
    lp = hp = 0.0
    for index in range(max(0, count)):
        t = index / SYNTH_RATE
        raw = rng.uniform(-1, 1)
        cutoff = high if not rise else 0.05 + (high - 0.05) * (index / max(1, count))
        lp += cutoff * (raw - lp)
        hp = lp - low * hp if low else lp
        gain = t / attack if t < attack else math.exp(-(t - attack) / tau)
        if rise:
            gain = min(1.0, t / (seconds * 0.9))
        out[begin + index] += level * gain * hp


def _kick(out, start, level=0.8):
    _add_tone(out, start, 150, 0.32, level=level, tau=0.09, glide_to=42, glide_seconds=0.12)
    _add_noise(out, start, 0.01, level=level * 0.2, seed=7)


def _glock(out, start, midi, level=0.3, seconds=0.5):
    f = hz(midi)
    _add_tone(out, start, f, seconds, level=level, tau=seconds / 3)
    _add_tone(out, start, f * 2.76, seconds * 0.4, level=level * 0.25, tau=seconds / 8)


def _brass(out, start, midi, seconds, level=0.12):
    for cents in (-6, 6):
        _add_tone(out, start, hz(midi) * 2 ** (cents / 1200), seconds, wave="saw", level=level,
                  attack=0.025, tau=0.3, sustain=0.6, release=0.05)


def _pip(step):
    out = _buffer(0.06)
    midi = PIP_STEPS[step % len(PIP_STEPS)]
    _add_tone(out, 0, hz(midi), 0.05, wave="pulse", level=0.25, tau=0.02)
    _add_tone(out, 0, hz(midi + 12), 0.04, wave="sine", level=0.1, tau=0.015)
    return out


def _lock():
    out = _buffer(0.12)
    _add_tone(out, 0, hz(81), 0.04, wave="triangle", level=0.35, tau=0.02)
    _add_noise(out, 0, 0.008, level=0.25, seed=3, high=0.9)
    _add_tone(out, 0.035, hz(86), 0.07, wave="triangle", level=0.35, tau=0.03)
    return out


def _save():
    out = _buffer(0.2)
    _add_noise(out, 0, 0.12, level=0.25, seed=11, high=0.9, rise=True)
    _glock(out, 0.1, 86, level=0.3, seconds=0.1)
    return out


def _clear():
    out = _buffer(0.55)
    for index, midi in enumerate((74, 78, 81, 86)):
        _glock(out, index * 0.06, midi, level=0.3, seconds=0.35)
    _add_noise(out, 0.2, 0.3, level=0.04, seed=5, high=0.95, low=0.9)
    return out


def _fanfare_short():
    """F5 success without the track: D power chords (no third), a short brass hit."""
    out = _buffer(0.7)
    for offset, midis in ((0.0, (50, 57, 62)), (0.11, (50, 57, 62, 69))):
        for midi in midis:
            _brass(out, offset, midi, 0.42 if offset else 0.1)
    _glock(out, 0.11, 86, level=0.25, seconds=0.5)
    _kick(out, 0.11, level=0.6)
    return out


def _oshii():
    """The skill's 'wrong': a bounce down, then a recovering hop up. Never minor."""
    out = _buffer(0.6)
    _add_tone(out, 0, 520, 0.32, level=0.4, tau=0.12, glide_to=170, glide_seconds=0.26,
              vibrato=(14, 30, 0.0))
    _add_tone(out, 0.42, 260, 0.12, wave="triangle", level=0.3, tau=0.05, glide_to=520,
              glide_seconds=0.09)
    return out


def _rewind():
    out = _buffer(0.17)
    _add_tone(out, 0, 1200, 0.15, wave="square", level=0.12, tau=0.08, glide_to=300)
    return out


def _stamp():
    out = _buffer(0.3)
    _kick(out, 0, level=0.9)
    _add_noise(out, 0, 0.02, level=0.3, seed=9, high=0.95, low=0.8)
    return out


def _shout(tier):
    out = _buffer(0.6 if tier >= 5 else 0.45)
    _add_noise(out, 0, 0.12, level=0.12 + tier * 0.03, seed=13 + tier, high=0.9, rise=True)
    _kick(out, 0.11, level=0.6 + tier * 0.06)
    if tier >= 3:
        for midi in (50, 57, 62):
            _brass(out, 0.11, midi, 0.3, level=0.06 + tier * 0.01)
    if tier >= 5:
        _add_noise(out, 0.11, 0.45, level=0.12, seed=21, tau=0.3, high=0.95, low=0.9)
    return out


def _alarm():
    out = _buffer(0.75)
    for index in range(6):
        _add_tone(out, index * 0.11, 880 if index % 2 == 0 else 660, 0.1, wave="square",
                  level=0.09, tau=0.2, sustain=0.8)
    _add_tone(out, 0, 120, 0.45, level=0.7, tau=0.15, glide_to=62, glide_seconds=0.2)
    return out


def _kyuin():
    out = _buffer(1.0)
    for cents in (-12, 12):
        _add_tone(out, 0, 380 * 2 ** (cents / 1200), 0.95, wave="saw", level=0.09, attack=0.02,
                  tau=0.3, sustain=0.8, glide_to=2350, glide_seconds=0.42,
                  vibrato=(9, 60, 0.43))
    _add_noise(out, 0, 0.9, level=0.05, seed=17, high=0.95, low=0.9, rise=True)
    return out


def _star(index):
    out = _buffer(0.3)
    _glock(out, 0, (86, 90, 93)[index % 3], level=0.35, seconds=0.25)
    return out


def _fanfare():
    out = _buffer(1.3)
    for interval, delay in zip((0, 7, 12, 16, 19, 24), range(6)):
        _brass(out, delay * 0.025, 50 + interval, 1.0, level=0.07)
    for midi in (86, 90, 93, 98):
        _glock(out, 0.05, midi, level=0.15, seconds=0.8)
    _kick(out, 0, level=0.8)
    _add_noise(out, 0, 1.2, level=0.1, seed=23, tau=0.4, high=0.95, low=0.9)
    for index in range(6):
        _add_tone(out, 0.6 + index * 0.05, 120, 0.3, level=0.3 + index * 0.06, tau=0.1,
                  glide_to=62, glide_seconds=0.2)
    return out


def _coins():
    out = _buffer(0.95)
    rng = random.Random(31)
    for _ in range(9):
        start = rng.uniform(0, 0.65)
        base = hz(rng.choice((86, 93, 98)))
        _add_tone(out, start, base, 0.05, wave="square", level=0.05, tau=0.04)
        _add_tone(out, start + 0.05, base * 1.335, 0.18, wave="square", level=0.05, tau=0.1)
    return out


def _chime():
    """SEND unverified: one calm bell, not a celebration."""
    out = _buffer(0.6)
    _add_tone(out, 0, hz(81), 0.55, level=0.3, tau=0.25)
    _add_tone(out, 0, hz(81) * 2.4, 0.3, level=0.06, tau=0.1)
    return out


# name -> (builder, output level relative to full scale)
EFFECTS = {f"pip{step}": (lambda step=step: _pip(step), 0.45) for step in range(8)}
EFFECTS.update({
    "lock": (_lock, 0.5), "save": (_save, 0.6), "clear": (_clear, 0.7),
    "fanfare_s": (_fanfare_short, 0.85), "oshii": (_oshii, 0.7), "rewind": (_rewind, 0.45),
    "stamp": (_stamp, 0.8), "alarm": (_alarm, 0.65), "kyuin": (_kyuin, 0.8),
    "fanfare": (_fanfare, 0.9), "coins": (_coins, 0.55), "chime": (_chime, 0.6),
    **{f"shout{tier}": (lambda tier=tier: _shout(tier), 0.7) for tier in range(2, 7)},
    **{f"star{index}": (lambda index=index: _star(index), 0.6) for index in range(3)},
})


def render(name):
    """Synthesize one effect as 48 kHz mono int16 samples."""
    builder, level = EFFECTS[name]
    samples = builder()
    peak = max((abs(value) for value in samples), default=0.0) or 1.0
    scale = level * 32767 / peak
    out = array("h")
    previous = 0.0
    for value in samples:  # 2x linear upsample to the mixer rate.
        current = value * scale
        out.append(int((previous + current) / 2))
        out.append(int(current))
        previous = current
    return out


def write_wav(path, samples, rate=RATE, channels=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with wave.open(str(temporary), "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(samples.tobytes())
    temporary.replace(path)


def read_mono(path):
    """48 kHz 16-bit PCM WAV as mono int16 samples, or None when unusable."""
    try:
        with wave.open(str(path), "rb") as file:
            if file.getsampwidth() != 2 or file.getframerate() != RATE or \
                    file.getnchannels() not in (1, 2):
                return None
            data = array("h")
            data.frombytes(file.readframes(file.getnframes()))
            if file.getnchannels() == 2:
                data = array("h", ((a + b) // 2 for a, b in zip(data[::2], data[1::2])))
            return data
    except (OSError, EOFError, wave.Error):
        return None


class SoundBank:
    """Effects by name: user override, then cache, then synthesis (written to the cache)."""

    def __init__(self, cache_dir, override_dir=None):
        self.cache_dir = Path(cache_dir) / CACHE_VERSION
        self.override_dir = Path(override_dir) if override_dir else None
        self._sounds = {}

    def get(self, name):
        found = self._sounds.get(name)
        if found is not None:
            return found
        samples = None
        if self.override_dir is not None:
            samples = read_mono(self.override_dir / f"{name}.wav")
        if samples is None:
            cached = self.cache_dir / f"{name}.wav"
            samples = read_mono(cached) if cached.is_file() else None
            if samples is None:
                samples = render(name)
                try:
                    write_wav(cached, samples)
                except OSError:
                    pass  # Cache is an optimization; the sound still plays.
        self._sounds[name] = samples
        return samples

    def warm(self, names=None):
        for name in names or EFFECTS:
            self.get(name)
