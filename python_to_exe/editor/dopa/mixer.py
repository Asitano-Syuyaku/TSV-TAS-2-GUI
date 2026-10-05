"""One process-wide software mixer for music and effects (dopagaki3.md §13).

A single output stream (48 kHz, stereo, 16-bit) keeps the track and the
effects on one clock. The mixer thread exists only while something sounds:
when every voice has ended it closes the device and exits, leaving no thread,
process or timer behind. It never touches Tk, and it pauses automatic GC
while it runs (background.hold_gc) for the same reason the analysis workers do.

Backends, all without new dependencies:
- Windows: WinMM waveOut through ctypes (multiple prepared buffers).
- Linux / WSLg: raw PCM piped to pw-play, pacat or aplay.
"""

import os
import shutil
import subprocess
import sys
import threading
import time
import warnings
import wave
from array import array

if __package__ == "editor.dopa":  # Script / PyInstaller layout.
    from background import hold_gc
else:
    from ...background import hold_gc

try:  # Fast C helpers while they exist (removed in Python 3.13).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import audioop
except ImportError:
    audioop = None


RATE = 48000
CHANNELS = 2
CHUNK = 1200            # Frames per write: 25 ms.
IDLE_CLOSE = 0.3        # Seconds of silence before the device closes.


class AudioUnavailable(Exception):
    pass


# Sources ------------------------------------------------------------------------


class MonoSource:
    """An effect: mono samples, duplicated to both channels."""

    def __init__(self, samples):
        self.samples, self.position = samples, 0

    def read(self, frames):
        part = self.samples[self.position:self.position + frames]
        self.position += len(part)
        if not len(part):
            return None
        stereo = array("h", bytes(len(part) * 4))
        stereo[0::2] = part
        stereo[1::2] = part
        return stereo


class WavSource:
    """The track: streamed from a 48 kHz stereo 16-bit WAV, from `start` seconds."""

    def __init__(self, path, start=0.0):
        self.file = wave.open(str(path), "rb")
        if (self.file.getframerate(), self.file.getnchannels(), self.file.getsampwidth()) != \
                (RATE, CHANNELS, 2):
            self.file.close()
            raise AudioUnavailable("Music cache must be 48 kHz stereo 16-bit PCM")
        self.file.setpos(min(self.file.getnframes(), max(0, int(start * RATE))))

    def read(self, frames):
        data = self.file.readframes(frames)
        if not data:
            self.close()
            return None
        samples = array("h")
        samples.frombytes(data)
        return samples

    def close(self):
        try:
            self.file.close()
        except Exception:
            pass


class Voice:
    """One playing sound. Gains are 0..1; fades ramp per chunk."""

    def __init__(self, source, gain, owner=None, kind="effect"):
        self.source, self.owner, self.kind = source, owner, kind
        self.gain = self.target = gain
        self.step = 0.0
        self.stop_after_fade = False
        self.done = False
        self.failed = False
        self.started_at = None  # Monotonic time its first frame reaches the output.

    def fade(self, seconds, target=0.0, stop=True):
        chunks = max(1, int(seconds * RATE / CHUNK))
        self.target = target
        self.step = (target - self.gain) / chunks
        self.stop_after_fade = stop


def _scale(samples, gain):
    if audioop is not None:
        return audioop.mul(samples.tobytes(), 2, gain)
    return array("h", (int(value * gain) for value in samples)).tobytes()


def _mix(buffers, frames):
    """Sum 16-bit interleaved buffers with saturation."""
    size = frames * CHANNELS * 2
    if audioop is not None:
        out = bytes(size)
        for data in buffers:
            out = audioop.add(out, data.ljust(size, b"\0"), 2)
        return out
    total = [0] * (frames * CHANNELS)
    for data in buffers:
        part = array("h")
        part.frombytes(data)
        for index, value in enumerate(part):
            total[index] += value
    return array("h", (32767 if value > 32767 else -32768 if value < -32768 else value
                       for value in total)).tobytes()


# Backends ------------------------------------------------------------------------


class PipeBackend:
    """Raw PCM to a player process (pw-play / pacat / aplay)."""

    COMMANDS = (
        ("pw-play", ["--rate", str(RATE), "--channels", str(CHANNELS), "--format", "s16",
                     "--latency", "20ms", "-"]),
        ("pacat", ["--raw", f"--rate={RATE}", f"--channels={CHANNELS}", "--format=s16le",
                   "--latency-msec=20"]),
        ("aplay", ["-q", "-f", "S16_LE", "-r", str(RATE), "-c", str(CHANNELS), "-B", "40000"]),
    )
    latency = 0.06  # Player buffer plus a small pipe: estimate for the visual clock.

    @classmethod
    def find(cls):
        for name, arguments in cls.COMMANDS:
            path = shutil.which(name)
            if path:
                return [path, *arguments]
        return None

    def __init__(self, command):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:  # A small pipe keeps the written-ahead audio, and the latency, short.
            import fcntl
            fcntl.fcntl(self.process.stdin.fileno(), 1031, 8192)  # F_SETPIPE_SZ
        except (ImportError, OSError):
            pass

    def write(self, data):
        try:
            self.process.stdin.write(data)
        except (BrokenPipeError, OSError, ValueError) as error:
            raise AudioUnavailable(str(error)) from None

    def close(self):
        try:
            self.process.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()


class WinMMBackend:
    """Windows waveOut via ctypes: a ring of prepared buffers, refilled as they finish."""

    BUFFERS = 4
    latency = 0.03

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class WAVEFORMATEX(ctypes.Structure):
            _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD),
                        ("nSamplesPerSec", wintypes.DWORD), ("nAvgBytesPerSec", wintypes.DWORD),
                        ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
                        ("cbSize", wintypes.WORD)]

        class WAVEHDR(ctypes.Structure):
            pass

        WAVEHDR._fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD),
                            ("dwBytesRecorded", wintypes.DWORD), ("dwUser", ctypes.c_size_t),
                            ("dwFlags", wintypes.DWORD), ("dwLoops", wintypes.DWORD),
                            ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]
        self.ctypes = ctypes
        self.winmm = ctypes.WinDLL("winmm")
        self.handle = ctypes.c_void_p()
        fmt = WAVEFORMATEX(1, CHANNELS, RATE, RATE * CHANNELS * 2, CHANNELS * 2, 16, 0)
        result = self.winmm.waveOutOpen(ctypes.byref(self.handle), ctypes.c_uint(0xFFFFFFFF),
                                        ctypes.byref(fmt), None, None, 0)
        if result:
            raise AudioUnavailable(f"waveOutOpen failed ({result})")
        size = CHUNK * CHANNELS * 2
        self.size = ctypes.sizeof(WAVEHDR)
        self.buffers = [ctypes.create_string_buffer(size) for _ in range(self.BUFFERS)]
        self.headers = [WAVEHDR() for _ in range(self.BUFFERS)]
        self.prepared = [False] * self.BUFFERS
        self.next = 0

    def write(self, data):
        ctypes = self.ctypes
        index, header = self.next, self.headers[self.next]
        if self.prepared[index]:
            while not header.dwFlags & 0x1:  # WHDR_DONE: the device is still playing it.
                time.sleep(0.002)
            self.winmm.waveOutUnprepareHeader(self.handle, ctypes.byref(header), self.size)
        ctypes.memmove(self.buffers[index], data, len(data))
        header.lpData = ctypes.cast(self.buffers[index], ctypes.c_void_p)
        header.dwBufferLength = len(data)
        header.dwFlags = 0
        if self.winmm.waveOutPrepareHeader(self.handle, ctypes.byref(header), self.size) or \
                self.winmm.waveOutWrite(self.handle, ctypes.byref(header), self.size):
            raise AudioUnavailable("waveOutWrite failed")
        self.prepared[index] = True
        self.next = (index + 1) % self.BUFFERS

    def close(self):
        ctypes = self.ctypes
        # Let queued audio finish (at most BUFFERS chunks), then release.
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline and any(
                prepared and not header.dwFlags & 0x1
                for prepared, header in zip(self.prepared, self.headers)):
            time.sleep(0.005)
        self.winmm.waveOutReset(self.handle)
        for prepared, header in zip(self.prepared, self.headers):
            if prepared:
                self.winmm.waveOutUnprepareHeader(self.handle, ctypes.byref(header), self.size)
        self.winmm.waveOutClose(self.handle)


def default_backend_factory():
    """A callable opening the platform backend, or None when this machine cannot play."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.WinDLL("winmm")
        except (ImportError, OSError):
            return None
        return WinMMBackend
    command = PipeBackend.find()
    if command is None:
        return None
    return lambda: PipeBackend(command)


# Mixer -----------------------------------------------------------------------------


class Mixer:
    def __init__(self, backend_factory, clock=time.monotonic):
        self.backend_factory = backend_factory
        self.clock = clock
        self.volume = 1.0
        self._voices = []
        self._lock = threading.Lock()
        self._thread = None
        self._closing = False
        self.failures = 0

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def play(self, source, gain=1.0, owner=None, kind="effect"):
        voice = Voice(source, gain, owner, kind)
        with self._lock:
            self._voices.append(voice)
            # A closing thread will not pick this voice up: start a fresh one.
            start = self._closing or self._thread is None or not self._thread.is_alive()
            if start:
                self._closing = False
                gc_hold = hold_gc()  # Taken on the caller's (Tk) thread before start.
                self._thread = threading.Thread(target=self._run, args=(gc_hold,), daemon=True,
                                                name="dopa-mixer")
        if start:
            try:
                self._thread.start()
            except Exception:
                gc_hold.release()
                raise
        return voice

    def stop_owner(self, owner, fade=0.0):
        with self._lock:
            for voice in self._voices:
                if voice.owner is owner:
                    if fade > 0:
                        voice.fade(fade)
                    else:
                        voice.done = True

    def voices(self):
        with self._lock:
            return tuple(self._voices)

    def _run(self, gc_hold):
        with gc_hold:
            try:
                backend = self.backend_factory()
            except Exception:
                self._fail_all()
                return
            idle_since = None
            try:
                while True:
                    with self._lock:
                        finished = [voice for voice in self._voices if voice.done]
                        voices = [voice for voice in self._voices if not voice.done]
                        self._voices = voices
                    for voice in finished:
                        close = getattr(voice.source, "close", None)
                        if close is not None:
                            close()
                    if not voices:
                        now = self.clock()
                        idle_since = idle_since or now
                        if now - idle_since >= IDLE_CLOSE:
                            with self._lock:
                                if not self._voices:
                                    self._closing = True
                                    break
                        backend.write(bytes(CHUNK * CHANNELS * 2))
                        continue
                    idle_since = None
                    buffers = []
                    for voice in voices:
                        data = voice.source.read(CHUNK)
                        if data is None:
                            voice.done = True
                            continue
                        if voice.started_at is None:
                            voice.started_at = self.clock() + backend.latency
                        gain = voice.gain * self.volume
                        buffers.append(_scale(data, gain) if gain != 1 else data.tobytes())
                        if voice.step:
                            voice.gain += voice.step
                            if (voice.step < 0 and voice.gain <= voice.target) or \
                                    (voice.step > 0 and voice.gain >= voice.target):
                                voice.gain, voice.step = voice.target, 0.0
                                if voice.stop_after_fade:
                                    voice.done = True
                    backend.write(_mix(buffers, CHUNK))
            except AudioUnavailable:
                self.failures += 1
                self._fail_all()
            finally:
                try:
                    backend.close()
                except Exception:
                    pass

    def _fail_all(self):
        with self._lock:
            failed, self._voices = self._voices, []
        for voice in failed:
            voice.failed = voice.done = True
            close = getattr(voice.source, "close", None)
            if close is not None:
                close()
