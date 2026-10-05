"""The F5 track: the user's own local copy of "Let's Go" (dopagaki3.md §13.3).

Nothing here ships or is committed. The trimmed WebM/Opus lives in the user's
data folder; it is decoded once with ffmpeg (if present) into a 48 kHz stereo
16-bit WAV in the user cache. A user-made WAV with the same stem is used as-is.
Without either, F5 simply has no track (synthesized effects still play).

Cue measured on the trimmed file: 180.00 BPM (beat 1/3 s, bar 4/3 s, stable
across the whole track), drop at 21.506 s (the user's cue; the track breathes
at ~21.25 s and lands at 21.5 s).
"""

import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path


TRACK = "lets_go_dopagaki"
BPM = 180.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
DROP = 21.506
LEAD_BARS = 2            # F5 starts the track 2 bars before the drop.
START = DROP - LEAD_BARS * BAR
TAIL_BARS = 2            # After the climax the drop keeps playing for 2 bars ...
FADE_BARS = 1            # ... then fades out over 1 bar.
FAIL_FADE = 0.5


def data_dir(platform=None, environ=None, home=None):
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform.startswith("win"):
        base = environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
    else:
        base = environ.get("XDG_DATA_HOME") or str(home / ".local" / "share")
    return Path(base) / "tsv-tas-2-gui" / "dopagaki"


def usable_wav(path):
    try:
        with wave.open(str(path), "rb") as file:
            return (file.getframerate(), file.getnchannels(), file.getsampwidth()) == (48000, 2, 2) \
                and file.getnframes() > 0
    except (OSError, EOFError, wave.Error):
        return False


class MusicLibrary:
    def __init__(self, source_dir, cache_dir, ffmpeg=None, runner=subprocess.run):
        self.source_dir = Path(source_dir)
        self.cache = Path(cache_dir) / f"{TRACK}.wav"
        self.ffmpeg = ffmpeg if ffmpeg is not None else shutil.which("ffmpeg")
        self.runner = runner
        self.path = None
        self.status = "unprepared"  # -> ready / missing / no_decoder / failed

    def prepare(self):
        """Blocking; call from a background thread. Never raises."""
        user_wav = self.source_dir / f"{TRACK}.wav"
        if usable_wav(user_wav):
            return self._ready(user_wav)
        if usable_wav(self.cache):
            return self._ready(self.cache)
        source = self.source_dir / f"{TRACK}.webm"
        if not source.is_file():
            self.status = "missing"
            return False
        if not self.ffmpeg:
            self.status = "no_decoder"
            return False
        temporary = self.cache.with_suffix(".tmp.wav")
        try:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            self.runner([self.ffmpeg, "-v", "error", "-y", "-i", str(source), "-ar", "48000",
                         "-ac", "2", "-c:a", "pcm_s16le", str(temporary)],
                        check=True, capture_output=True, timeout=120,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if not usable_wav(temporary):
                raise OSError("decoded track is not usable")
            temporary.replace(self.cache)
        except (OSError, subprocess.SubprocessError, ValueError):
            self.status = "failed"
            try:
                temporary.unlink()
            except OSError:
                pass
            return False
        return self._ready(self.cache)

    def _ready(self, path):
        self.path, self.status = path, "ready"
        return True
