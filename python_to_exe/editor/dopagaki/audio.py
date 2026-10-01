"""Optional one-player audio, separate from documents and conversion results."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import tempfile


def default_audio_path():
    return Path.home() / ".local/share/tsv-tas-2-gui/dopagaki/lets_go_dopagaki.webm"


@dataclass(frozen=True)
class AudioConfig:
    enabled: bool = True
    path: str = ""
    player: str = ""
    volume: int = 70
    sync_offset_ms: int = 0
    tail_seconds: float = 8.0

    @property
    def media_path(self):
        return self.path or str(default_audio_path())

    @classmethod
    def clean(cls, values):
        defaults = asdict(cls())
        if not isinstance(values, dict):
            return cls()
        if type(values.get("enabled")) is bool:
            defaults["enabled"] = values["enabled"]
        for key in ("path", "player"):
            value = values.get(key)
            if isinstance(value, str) and len(value) <= 4096 and "\0" not in value:
                if not value or Path(value).expanduser().is_absolute() or PureWindowsPath(value).is_absolute():
                    defaults[key] = value
        for key, low, high in (("volume", 0, 100), ("sync_offset_ms", -2000, 2000)):
            value = values.get(key)
            if type(value) is int and low <= value <= high:
                defaults[key] = value
        value = values.get("tail_seconds")
        if type(value) in (int, float) and math.isfinite(value) and 2 <= value <= 60:
            defaults["tail_seconds"] = float(value)
        return cls(**defaults)


class AudioSettings:
    """Small user-only JSON alongside AppSettings; normal settings stay unchanged."""

    def __init__(self, path):
        self.path = Path(path) if path is not None else None
        try:
            values = json.loads(self.path.read_text(encoding="utf-8")) if self.path else {}
        except (OSError, ValueError):
            values = {}
        self.config = AudioConfig.clean(values)

    def update(self, **values):
        self.config = AudioConfig.clean({**asdict(self.config), **values})
        if self.path is None:
            return False
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".dopagaki-audio-", dir=self.path.parent)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(asdict(self.config), handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            return True
        except (OSError, ValueError):
            return False
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass


class AudioBackend:
    """Minimal replaceable backend. No backend owns Tk callbacks or UI references."""

    def play(self, path):
        return False

    def stop(self):
        pass

    def poll(self):
        return False

    def close(self):
        self.stop()


class FFplayBackend(AudioBackend):
    """Shell-free ffplay subprocess, at most one; missing player is a normal fallback.

    On WSL, explicit Windows paths are translated using wslpath. Discovery is
    PATH-only, never a filesystem scan or an install during F5. A Windows player
    outside PATH can be selected in the Dopagaki menu. stdout/stderr cannot fill
    a pipe and hold a player alive. Stop reaps the old process before replacement.
    """

    def __init__(self, player="", *, volume=70, popen=None):
        self.player = player
        self.volume = volume
        self._popen = subprocess.Popen if popen is None else popen
        self._process = None
        self._closed = False
        self.last_error = ""

    @property
    def process(self):
        return self._process

    @staticmethod
    def _translate(path, option):
        result = subprocess.run(["wslpath", option, str(path)], capture_output=True,
                                text=True, timeout=2, check=True)
        return result.stdout.strip()

    def play(self, path):
        if self._closed or not self.stop():
            return False
        self.last_error = ""
        try:
            player = self.player or shutil.which("ffplay") or shutil.which("ffplay.exe")
            if not player:
                self.last_error = "ffplay unavailable"
                return False
            path = str(path)
            if os.name != "nt":
                if PureWindowsPath(player).is_absolute() and not Path(player).is_absolute():
                    player = self._translate(player, "-u")
                if PureWindowsPath(path).is_absolute() and not Path(path).is_absolute():
                    path = self._translate(path, "-u")
            media = Path(path).expanduser()
            if not media.is_file():
                self.last_error = "audio file unavailable"
                return False
            argument = (self._translate(media, "-w")
                        if os.name != "nt" and str(player).lower().endswith(".exe") else str(media))
            self._process = self._popen(
                [str(player), "-nodisp", "-autoexit", "-loglevel", "error", "-nostats",
                 "-volume", str(self.volume), "-i", argument],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return True
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self.last_error = str(error)
            return False

    def poll(self):
        process = self._process
        if process is None:
            return False
        code = process.poll()
        if code is None:
            return True
        self._process = None  # poll() also reaps on POSIX.
        if code:
            self.last_error = f"ffplay exited with status {code}"
        return False

    def stop(self):
        process = self._process
        if process is None:
            return True
        try:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=0.15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.15)
            self._process = None
            return True
        except (OSError, subprocess.SubprocessError) as error:
            # Never launch another player while an owned one may still be alive.
            self.last_error = str(error)
            return False

    def close(self):
        self._closed = True
        self.stop()
