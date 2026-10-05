"""Process-wide audio for the Editor (dopagaki3.md §13): effects, the F5 track, settings.

Audio is decoration. A missing device, player, decoder or file only means
silence; it never fails or delays a save, a conversion or a send (Truth Contract).
Automated test runs never open the device unless TSV_TAS_2_GUI_AUDIO=on.
"""

import os
import sys
import tempfile
import threading
from pathlib import Path

from .mixer import Mixer, MonoSource, WavSource, default_backend_factory
from .music import START, MusicLibrary, data_dir
from .sound import CACHE_VERSION, SoundBank

if __package__ == "editor.dopa":
    from background import hold_gc
else:
    from ...background import hold_gc


VOLUME_LEVELS = {1: 0.4, 2: 0.65, 3: 0.9}
MUSIC_GAIN = 0.55   # The track is mastered to full scale: leave room for effects.
EFFECT_GAIN = 0.85


def _audio_allowed():
    choice = os.environ.get("TSV_TAS_2_GUI_AUDIO", "").lower()
    if choice in ("on", "1", "yes"):
        return True
    if choice in ("off", "0", "no"):
        return False
    return "unittest" not in sys.modules  # Test runs stay silent by default.


class AudioService:
    def __init__(self, config_dir, backend_factory=None, music_dir=None, clock=None):
        if backend_factory is None and _audio_allowed():
            backend_factory = default_backend_factory()
        self.mixer = Mixer(backend_factory, **({"clock": clock} if clock else {})) \
            if backend_factory else None
        config = Path(config_dir) if config_dir else Path(tempfile.gettempdir()) / "TSV-TAS-2-GUI"
        cache = config / "sound-cache"
        self.bank = SoundBank(cache, override_dir=config / "sounds")
        self.music = MusicLibrary(music_dir or data_dir(), cache / CACHE_VERSION)
        self._ready = threading.Event()
        self._started = False

    @classmethod
    def for_root(cls, root, config_dir):
        """One service per Tk root (one per process in the app)."""
        service = getattr(root, "_dopa_audio", None)
        if service is None:
            service = root._dopa_audio = cls(config_dir)
        return service

    @property
    def available(self):
        return self.mixer is not None

    @property
    def ready(self):
        return self._ready.is_set()

    @property
    def music_ready(self):
        return self.ready and self.music.status == "ready"

    def prepare(self):
        """Warm effects and decode the track once, off the Tk thread."""
        if not self.available or self._started:
            return
        self._started = True
        gc_hold = hold_gc()

        def work():
            with gc_hold:
                try:
                    self.bank.warm()
                    self.music.prepare()
                finally:
                    self._ready.set()

        try:
            threading.Thread(target=work, daemon=True, name="dopa-audio-prepare").start()
        except Exception:
            gc_hold.release()
            self._ready.set()

    def effect(self, name, owner, level):
        if not self.ready or not self.available:
            return None
        samples = self.bank._sounds.get(name)
        if samples is None:
            return None
        return self.mixer.play(MonoSource(samples), EFFECT_GAIN * VOLUME_LEVELS[level], owner)

    def track(self, owner, level, start=START):
        if not self.music_ready or not self.available:
            return None
        try:
            source = WavSource(self.music.path, start)
        except Exception:
            return None
        return self.mixer.play(source, MUSIC_GAIN * VOLUME_LEVELS[level], owner, kind="music")

    def set_level(self, owner, level):
        """Apply a new volume to this owner's sounding voices."""
        if not self.available:
            return
        for voice in self.mixer.voices():
            if voice.owner is owner and not voice.step:
                base = MUSIC_GAIN if voice.kind == "music" else EFFECT_GAIN
                voice.gain = voice.target = base * VOLUME_LEVELS[level]

    def stop(self, owner, fade=0.0):
        if self.available:
            self.mixer.stop_owner(owner, fade)
