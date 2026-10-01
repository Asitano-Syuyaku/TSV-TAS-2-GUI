"""Optional one-player audio, separate from documents and conversion results."""

from dataclasses import asdict, dataclass
import base64
import json
import math
import os
from pathlib import Path, PureWindowsPath
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import wave
import weakref


def default_audio_path():
    folder = Path.home() / ".local/share/tsv-tas-2-gui/dopagaki"
    wav = folder / "lets_go_dopagaki_f5.wav"
    return wav if wav.is_file() else folder / "lets_go_dopagaki.webm"


def _runtime_platform():
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux") and (
            os.environ.get("WSL_INTEROP") or "microsoft" in platform.release().lower()):
        return "wsl"
    return "other"


def _local_media(path):
    path = str(path)
    if os.name != "nt" and PureWindowsPath(path).is_absolute() and not Path(path).is_absolute():
        path = _ProcessBackend._translate(path, "-u")
    media = Path(path).expanduser()
    if not media.is_absolute() or not media.is_file():
        raise ValueError("local audio file unavailable")
    return media


def _wav_duration(media):
    if media.suffix.lower() != ".wav":
        raise ValueError("native audio requires PCM WAV")
    # Header only: Python never loads/retains the PCM payload.
    with wave.open(str(media), "rb") as audio:
        if audio.getcomptype() != "NONE" or not audio.getnframes() or not audio.getframerate():
            raise ValueError("invalid PCM WAV")
        return audio.getnframes() / audio.getframerate()


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


class _ProcessBackend(AudioBackend):
    """One owned, reaped player; no threads, Tk callbacks or PCM buffers."""

    name = "player"

    def __init__(self, *, popen=None):
        self._popen = subprocess.Popen if popen is None else popen
        self._process = None
        self._closed = False
        self.launched_at = None
        self.last_error = ""

    @property
    def process(self):
        return self._process

    @staticmethod
    def _translate(path, option):
        result = subprocess.run(["wslpath", option, str(path)], capture_output=True,
                                text=True, timeout=2, check=True)
        return result.stdout.strip()

    def _spawn(self, arguments):
        self.launched_at = time.monotonic()
        self._process = self._popen(
            arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True

    def poll(self):
        process = self._process
        if process is None:
            return False
        code = process.poll()
        if code is None:
            return True
        self._process = None  # poll() also reaps on POSIX.
        if code:
            self.last_error = f"{self.name} exited with status {code}"
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


class FFplayBackend(_ProcessBackend):
    """Shell-free ffplay fallback, discovered on PATH or selected explicitly."""

    name = "ffplay"

    def __init__(self, player="", *, volume=70, popen=None):
        super().__init__(popen=popen)
        self.player, self.volume = player, volume

    def play(self, path):
        if self._closed or not self.stop():
            return False
        self.last_error = ""
        try:
            player = self.player or shutil.which("ffplay") or shutil.which("ffplay.exe")
            if not player:
                self.last_error = "ffplay unavailable"
                return False
            if os.name != "nt" and PureWindowsPath(player).is_absolute() and not Path(player).is_absolute():
                player = self._translate(player, "-u")
            # Preserve FFplay's existing path/override handling.
            path = str(path)
            if os.name != "nt" and PureWindowsPath(path).is_absolute() and not Path(path).is_absolute():
                path = self._translate(path, "-u")
            media = Path(path).expanduser()
            if not media.is_file():
                self.last_error = "audio file unavailable"
                return False
            argument = (self._translate(media, "-w")
                        if os.name != "nt" and str(player).lower().endswith(".exe") else str(media))
            return self._spawn([str(player), "-nodisp", "-autoexit", "-loglevel", "error", "-nostats",
                                "-volume", str(self.volume), "-i", argument])
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self.last_error = str(error)
            return False


class WinSoundBackend(AudioBackend):
    """Native Windows async WAV playback; duration-derived poll, no timer/thread.

    PlaySound is process-global. A weak owner prevents an old Editor's cleanup
    from stopping a newer Editor's playback. System volume is left untouched.
    """

    name = "winsound"
    _owner = None

    def __init__(self, *, module=None, clock=None):
        self._module = module
        self._clock = time.monotonic if clock is None else clock
        self._playing = self._closed = False
        self._until = 0.0
        self.launched_at = None
        self.last_error = ""

    @property
    def process(self):
        return None  # Native async API has no subprocess.

    def play(self, path):
        if self._closed:
            return False
        owner = self._owner() if self._owner is not None else None
        if owner is not None and owner.stop() is False:
            self.last_error = owner.last_error
            return False
        self.last_error = ""
        try:
            media = _local_media(path)
            duration = _wav_duration(media)
            if self._module is None:
                import winsound
                self._module = winsound
            self.launched_at = self._clock()
            self._module.PlaySound(str(media), self._module.SND_FILENAME |
                                   self._module.SND_ASYNC | self._module.SND_NODEFAULT)
            self._playing = True
            self._until = self.launched_at + duration
            WinSoundBackend._owner = weakref.ref(self)
            return True
        except (ImportError, OSError, ValueError, RuntimeError, wave.Error, EOFError) as error:
            self.last_error = str(error)
            return False

    def poll(self):
        owner = self._owner() if self._owner is not None else None
        if owner is not self or self._clock() >= self._until:
            self._playing = False
        return self._playing

    def stop(self):
        if self._owner is not None and self._owner() is self:
            try:
                self._module.PlaySound(None, 0)
            except (OSError, RuntimeError) as error:
                self.last_error = str(error)
                return False
            WinSoundBackend._owner = None
        self._playing = False
        return True

    def close(self):
        self._closed = True
        self.stop()


class SoundPlayerBackend(_ProcessBackend):
    """WSL -> Windows PowerShell SoundPlayer.PlaySync, only a local PCM WAV.

    User paths are UTF-8 base64 data in a fixed UTF-16LE EncodedCommand, never
    executable PowerShell fragments. Load/PlaySync run only in the owned child.
    """

    name = "PowerShell SoundPlayer"

    def __init__(self, powershell="", *, popen=None):
        super().__init__(popen=popen)
        self.powershell = powershell

    def play(self, path):
        if self._closed or not self.stop():
            return False
        self.last_error = ""
        try:
            media = _local_media(path)
            _wav_duration(media)
            player = self.powershell or shutil.which("powershell.exe")
            if not player:
                self.last_error = "PowerShell unavailable"
                return False
            path_data = base64.b64encode(self._translate(media, "-w").encode("utf-8")).decode("ascii")
            script = (
                "$ErrorActionPreference='Stop'; $player=$null; try { "
                f"$path=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{path_data}')); "
                "$player=New-Object System.Media.SoundPlayer; $player.SoundLocation=$path; "
                "$player.LoadTimeout=5000; $player.Load(); $player.PlaySync(); exit 0 "
                "} catch { exit 1 } finally { if ($null -ne $player) { $player.Stop(); $player.Dispose() } }")
            encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
            return self._spawn([str(player), "-NoLogo", "-NoProfile", "-NonInteractive",
                                "-WindowStyle", "Hidden", "-EncodedCommand", encoded])
        except (OSError, ValueError, subprocess.SubprocessError, wave.Error, EOFError) as error:
            self.last_error = str(error)
            return False


class AutoAudioBackend(AudioBackend):
    """At most two candidates, one active player, no discovery or loading at init."""

    def __init__(self, config, *, runtime=None):
        runtime = _runtime_platform() if runtime is None else runtime
        native = (WinSoundBackend() if runtime == "windows" else
                  SoundPlayerBackend() if runtime == "wsl" else None)
        self._candidates = ([native] if native is not None else []) + [FFplayBackend(config.player, volume=config.volume)]
        self._active = None
        self._closed = False
        self.last_error = ""

    @property
    def process(self):
        return self._active.process if self._active is not None else None

    @property
    def name(self):
        return self._active.name if self._active is not None else "visual-only"

    @property
    def launched_at(self):
        return self._active.launched_at if self._active is not None else None

    def play(self, path):
        if self._closed or not self.stop():
            return False
        errors = []
        for backend in self._candidates:
            try:
                if backend.play(path):
                    self._active = backend
                    self.last_error = ""
                    return True
            except Exception as error:
                backend.last_error = str(error)
            errors.append(f"{backend.name}: {backend.last_error}")
            if (isinstance(backend, WinSoundBackend) and backend._owner is not None
                    and backend._owner() is not None):
                break  # Another native owner could not stop; do not overlap ffplay.
            if backend.stop() is False:
                self._active = backend  # Keep ownership; never start an overlapping fallback.
                break
        self.last_error = "; ".join(errors)
        return False

    def poll(self):
        if self._active is None:
            return False
        if self._active.poll():
            return True
        self.last_error = self._active.last_error
        self.stop()
        return False

    def stop(self):
        if self._active is not None:
            if self._active.stop() is False:
                self.last_error = self._active.last_error
                return False
            self._active = None
        return True

    def close(self):
        self._closed = True
        self.stop()
        for backend in self._candidates:
            backend.close()


def create_audio_backend(config):
    return AutoAudioBackend(config)
