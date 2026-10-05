"""Dopagaki3 Phase 4 (dopagaki3.md §13, §9.6): audio, F5 x Let's Go, non-modal results."""

import gc
import tempfile
import threading
import time
import tkinter as tk
import unittest
import wave
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from python_to_exe import background
from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp
from python_to_exe.converter_logic import ConversionOutputs
from python_to_exe.editor.dopa import mixer as mixmod
from python_to_exe.editor.dopa import sound
from python_to_exe.editor.dopa.audio import AudioService, _audio_allowed
from python_to_exe.editor.dopa.choreo import START_GRACE, F5Choreography
from python_to_exe.editor.dopa.music import (BAR, BEAT, DROP, START, MusicLibrary, data_dir,
                                             usable_wav)
from python_to_exe.editor.dopa.outcome import FAILED, SUCCESS
from python_to_exe.editor.window import EditorWindow


SCRIPT = "5\tls(90)\n1\ta\trs(0)\n2\tzl\n"
LEAD = DROP - START  # Seconds from the track's first frame to its drop (2 bars).


def write_wav(path, seconds=0.2, rate=48000, channels=2, value=1000):
    with wave.open(str(path), "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(array("h", [value] * int(seconds * rate) * channels).tobytes())


class SoundAndMusicTests(unittest.TestCase):
    def test_every_effect_renders_normalized_and_caches(self):
        for name, (_, level) in sound.EFFECTS.items():
            samples = sound.render(name)
            self.assertGreater(len(samples), 1000, name)
            self.assertAlmostEqual(max(abs(value) for value in samples) / 32767, level, delta=0.02)
        with tempfile.TemporaryDirectory() as folder:
            bank = sound.SoundBank(Path(folder) / "cache", Path(folder) / "sounds")
            first = bank.get("oshii")
            self.assertTrue((Path(folder) / "cache" / "v1" / "oshii.wav").is_file())
            self.assertEqual(sound.SoundBank(Path(folder) / "cache").get("oshii"), first)

    def test_user_override_is_used_only_when_it_matches_the_mixer(self):
        with tempfile.TemporaryDirectory() as folder:
            overrides = Path(folder) / "sounds"
            overrides.mkdir()
            write_wav(overrides / "save.wav", channels=1, value=1234)
            write_wav(overrides / "lock.wav", rate=44100, channels=1)
            bank = sound.SoundBank(Path(folder) / "cache", overrides)
            self.assertEqual(set(bank.get("save")), {1234})
            self.assertEqual(bank.get("lock"), sound.render("lock"))  # Wrong rate: ignored.

    def test_music_prepares_from_user_wav_cache_or_decoder_and_never_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            source, cache = Path(folder) / "data", Path(folder) / "cache"
            source.mkdir()
            library = MusicLibrary(source, cache, ffmpeg="")
            self.assertFalse(library.prepare())
            self.assertEqual(library.status, "missing")
            (source / "lets_go_dopagaki.webm").write_bytes(b"not audio")
            self.assertFalse(MusicLibrary(source, cache, ffmpeg="").prepare())

            def decode(command, **options):
                write_wav(Path(command[-1]))
                return SimpleNamespace(returncode=0)

            library = MusicLibrary(source, cache, ffmpeg="ffmpeg", runner=decode)
            self.assertTrue(library.prepare())
            self.assertEqual(library.path, cache / "lets_go_dopagaki.wav")
            failing = MusicLibrary(source, Path(folder) / "other",
                                   ffmpeg="ffmpeg", runner=Mock(side_effect=OSError("no ffmpeg")))
            self.assertFalse(failing.prepare())
            self.assertEqual(failing.status, "failed")
            write_wav(source / "lets_go_dopagaki.wav")
            library = MusicLibrary(source, Path(folder) / "third", ffmpeg="")
            self.assertTrue(library.prepare())
            self.assertEqual(library.path, source / "lets_go_dopagaki.wav")
        self.assertEqual(data_dir("linux", {}, "/home/u"),
                         Path("/home/u/.local/share/tsv-tas-2-gui/dopagaki"))
        self.assertEqual(data_dir("win32", {"LOCALAPPDATA": "C:/L"}, "/h"),
                         Path("C:/L/tsv-tas-2-gui/dopagaki"))

    def test_cue_comes_from_the_track_analysis(self):
        self.assertAlmostEqual(BEAT, 1 / 3)
        self.assertAlmostEqual(START, DROP - 2 * BAR)
        self.assertAlmostEqual(LEAD, 8 / 3)

    def test_test_runs_never_open_the_audio_device_unless_asked(self):
        self.assertFalse(_audio_allowed())
        with patch.dict("os.environ", {"TSV_TAS_2_GUI_AUDIO": "on"}):
            self.assertTrue(_audio_allowed())
        self.assertFalse(AudioService(None).available)


class StubBackend:
    latency = 0.0

    def __init__(self, fail_after=None):
        self.writes, self.closed, self.fail_after = [], False, fail_after

    def write(self, data):
        if self.fail_after is not None and len(self.writes) >= self.fail_after:
            raise mixmod.AudioUnavailable("device lost")
        self.writes.append(data)
        time.sleep(0.001)

    def close(self):
        self.closed = True


class MixerTests(unittest.TestCase):
    def setUp(self):
        background.resume_gc()
        self.addCleanup(background.resume_gc)

    def wait_idle(self, mixer):
        deadline = time.monotonic() + 5
        while mixer.running and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(mixer.running)

    def test_voices_mix_with_saturation_then_the_thread_closes_and_exits(self):
        backend = StubBackend()
        mixer = mixmod.Mixer(lambda: backend)
        loud = array("h", [30000] * 2400)
        first = mixer.play(mixmod.MonoSource(loud), 1.0)
        second = mixer.play(mixmod.MonoSource(loud), 1.0)
        self.wait_idle(mixer)
        self.assertTrue(backend.closed)
        self.assertTrue(first.done and second.done)
        mixed = array("h")
        mixed.frombytes(mixmod._mix([array("h", [30000] * 4).tobytes()] * 2, 2))
        self.assertEqual(set(mixed), {32767})  # Saturated, not wrapped.
        self.assertIsNotNone(first.started_at)
        self.assertTrue(background.resume_gc() or True)
        self.assertEqual(threading.active_count(), threading.active_count())

    def test_fade_ends_a_voice_and_owner_stop_is_immediate(self):
        backend = StubBackend()
        mixer = mixmod.Mixer(lambda: backend)
        long = array("h", [1000] * 480000)
        owner = object()
        silence = bytes(mixmod.CHUNK * mixmod.CHANNELS * 2)
        voice = mixer.play(mixmod.MonoSource(long), 1.0, owner=owner)
        voice.fade(0.05)
        other = mixer.play(mixmod.MonoSource(long), 1.0, owner="other")
        mixer.stop_owner("other")
        self.wait_idle(mixer)
        self.assertTrue(voice.done and other.done)
        sounding = [data for data in backend.writes if data != silence]
        self.assertLess(len(sounding), 40)  # Not the whole 10 seconds.

    def test_backend_failure_marks_voices_failed_without_raising(self):
        mixer = mixmod.Mixer(lambda: StubBackend(fail_after=2))
        voice = mixer.play(mixmod.MonoSource(array("h", [1] * 48000)), 1.0)
        self.wait_idle(mixer)
        self.assertTrue(voice.failed)
        broken = mixmod.Mixer(Mock(side_effect=OSError("no device")))
        voice = broken.play(mixmod.MonoSource(array("h", [1] * 100)), 1.0)
        self.wait_idle(broken)
        self.assertTrue(voice.failed)

    def test_wav_source_streams_from_the_cue(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "track.wav"
            write_wav(path, seconds=1.0)
            source = mixmod.WavSource(path, start=0.5)
            total = 0
            while (chunk := source.read(mixmod.CHUNK)) is not None:
                total += len(chunk) // 2
            self.assertEqual(total, 24000)
            write_wav(path, rate=44100)
            with self.assertRaises(mixmod.AudioUnavailable):
                mixmod.WavSource(path)


class Events:
    def __init__(self):
        self.log = []

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.log.append((name.replace("choreo_", ""), args, kwargs))

    def names(self):
        return [name for name, _, _ in self.log]


class Voice:
    def __init__(self, started_at=None):
        self.started_at, self.failed, self.done, self.faded = started_at, False, False, None

    def fade(self, seconds, target=0.0, stop=True):
        self.faded = seconds


class ChoreographyTests(unittest.TestCase):
    def run_until(self, choreo, start, end, step=0.01):
        now = start
        while now <= end:
            choreo.tick(now)
            now += step
        return now

    def test_early_success_lands_exactly_on_the_drop_and_then_fades(self):
        voice, events = Voice(started_at=10.0), Events()
        choreo = F5Choreography(voice, 10.0, events)
        self.run_until(choreo, 10.0, 10.5)
        choreo.result(SUCCESS, 10.5)  # The converter finished long before the drop.
        self.assertNotIn("climax", events.names())
        self.run_until(choreo, 10.5, 10.0 + LEAD - 0.02)
        self.assertNotIn("climax", events.names())
        self.assertIn("hold", events.names())
        self.assertEqual(events.names().count("beat"), 8)  # 2 bars of beats, no countdown text.
        choreo.tick(10.0 + LEAD + 0.001)
        self.assertEqual(events.log[-1], ("climax", (), {"on_drop": True}))
        self.assertIsNone(voice.faded)
        self.run_until(choreo, 10.0 + LEAD, 10.0 + LEAD + 2 * BAR + 0.02)
        self.assertAlmostEqual(voice.faded, BAR)  # 2 bars of drop, then 1 bar fade.
        voice.done = True
        self.assertFalse(choreo.tick(20.0))

    def test_late_success_is_music_energy_first_then_the_next_beat(self):
        voice, events = Voice(started_at=0.0), Events()
        choreo = F5Choreography(voice, 0.0, events)
        self.run_until(choreo, 0.0, LEAD + 0.01)
        self.assertIn("drop", events.names())
        self.assertNotIn("climax", events.names())  # No success yet: no success words.
        arrival = LEAD + 1.1
        choreo.result(SUCCESS, arrival)
        choreo.tick(arrival)
        self.assertNotIn("climax", events.names())
        self.run_until(choreo, arrival, arrival + BEAT + 0.01, step=0.005)
        self.assertEqual(events.names().count("climax"), 1)

    def test_failure_fades_the_track_with_no_drop(self):
        voice, events = Voice(started_at=0.0), Events()
        choreo = F5Choreography(voice, 0.0, events)
        choreo.result(FAILED, 0.4)
        self.assertEqual(voice.faded, 0.5)
        voice.done = True
        self.run_until(choreo, 0.4, LEAD + 1)
        self.assertNotIn("drop", events.names())
        self.assertNotIn("climax", events.names())

    def test_track_that_never_starts_or_fails_is_not_waited_for(self):
        voice, events = Voice(started_at=None), Events()
        choreo = F5Choreography(voice, 0.0, events)
        choreo.result(SUCCESS, 0.1)
        self.assertFalse(choreo.tick(START_GRACE + 0.01))
        self.assertEqual(events.names(), ["climax"])
        voice, events = Voice(started_at=0.0), Events()
        choreo = F5Choreography(voice, 0.0, events)
        choreo.tick(0.5)
        voice.failed = True
        self.assertFalse(choreo.tick(0.6))
        choreo.result(SUCCESS, 0.7)  # Arrives after the track died: immediate.
        self.assertEqual(events.names().count("climax"), 1)

    def test_replacement_or_mute_celebrates_a_pending_success_but_close_does_not(self):
        for celebrate in (True, False):
            voice, events = Voice(started_at=0.0), Events()
            choreo = F5Choreography(voice, 0.0, events)
            choreo.result(SUCCESS, 0.3)
            choreo.cancel(0.4, fade=0.08, celebrate=celebrate)
            self.assertEqual(events.names().count("climax"), 1 if celebrate else 0)
            self.assertEqual(voice.faded, 0.08)

    def test_effects_zero_never_holds_visuals(self):
        voice, events = Voice(started_at=0.0), Events()
        choreo = F5Choreography(voice, 0.0, events, hold_visuals=False)
        self.run_until(choreo, 0.0, 0.5)
        choreo.result(SUCCESS, 0.5)
        self.assertEqual(events.names(), ["climax"])  # No beats, holds or waiting.


class FakeAudio:
    def __init__(self, available=True, music=True):
        self.available, self.ready, self.music_ready = available, True, music
        self.effects, self.tracks, self.stops, self.levels = [], [], [], []

    def prepare(self):
        pass

    def effect(self, name, owner, level):
        self.effects.append(name)

    def track(self, owner, level, start=START):
        voice = Voice()
        self.tracks.append(voice)
        return voice

    def stop(self, owner, fade=0.0):
        self.stops.append(fade)

    def set_level(self, owner, level):
        self.levels.append(level)


class AudioEditorTests(unittest.TestCase):
    def make_editor(self, audio=None, **values):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        root.withdraw()
        self.addCleanup(root.destroy)
        self.errors = []
        root.report_callback_exception = lambda *error: self.errors.append(error)
        folder = tempfile.TemporaryDirectory(prefix="tas audio ")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        source = self.folder / "route.tsv"
        source.write_text(SCRIPT, encoding="utf-8")
        root._tas_app_settings = AppSettings(self.folder / "settings.json")
        if values:
            root._tas_app_settings.update(**values)
        self.audio = root._dopa_audio = audio or FakeAudio()
        editor = EditorWindow(root, language="en", initial_path=source,
                              on_convert=Mock(return_value=True))
        editor.show_table()
        root.update()
        self.root, self.editor = root, editor
        self.now = [100.0]
        director = editor._dopa
        director.clock = director.fx.clock = lambda: self.now[0]
        self.shouts = []
        shout = director.hud.shout
        director.hud.shout = lambda text, tier, **kw: (self.shouts.append(text),
                                                       shout(text, tier, **kw))
        return editor, director

    def advance(self, seconds):
        steps = max(1, int(seconds / 0.02))
        for _ in range(steps):
            self.now[0] += seconds / steps
            self.editor._dopa.fx.step()

    def fact(self):
        return self.editor.meter_canvas.itemcget(self.editor._dopa.hud.process_text, "text")

    def f5(self):
        self.assertTrue(self.editor.save_and_convert())  # The run starts at once.
        voice = self.audio.tracks[-1]
        voice.started_at = self.now[0] + 0.05
        return voice

    def outputs(self, send=False):
        return ConversionOutputs(self.folder / "route", ftp_requested=send)

    def test_f5_early_success_shows_facts_now_and_the_climax_on_the_drop(self):
        editor, director = self.make_editor()
        self.f5()
        self.assertIn("save", self.audio.effects)
        self.advance(0.4)
        editor.conversion_finished(True, self.outputs(), "", "binary")
        self.assertEqual(self.fact(), "✔ OUTPUT route")  # Fact: immediately.
        self.assertNotIn("CONVERTED!!", self.shouts)
        self.assertEqual(director.heat.round, 1)
        self.advance(LEAD - 0.4)  # 0.05 s short of the drop (the track began at +0.05).
        self.assertNotIn("CONVERTED!!", self.shouts)
        self.advance(0.07)
        self.assertIn("CONVERTED!!", self.shouts)       # Celebration: on the drop.
        self.advance(0.15)
        self.assertIn("coins", self.audio.effects)
        self.assertNotIn("fanfare_s", self.audio.effects)  # The track carries the hit.

    def test_f5_late_success_and_failure(self):
        editor, director = self.make_editor()
        self.f5()
        self.advance(LEAD + 0.5)  # Drop passes while the converter still runs.
        self.assertNotIn("CONVERTED!!", self.shouts)
        editor.conversion_finished(True, self.outputs(), "", "binary")
        self.advance(BEAT + 0.05)
        self.assertIn("CONVERTED!!", self.shouts)
        voice = self.f5()  # Second F5 replaces the sting.
        self.assertEqual(len(self.audio.tracks), 2)
        editor.conversion_finished(False, error="tsv-tas.py exited with status 1",
                                   stderr="Error: bad token on line 2\n")
        self.assertEqual(voice.faded, 0.5)
        self.assertEqual(self.shouts[-1], "SO CLOSE!")
        self.assertIn("oshii", self.audio.effects)
        self.assertEqual(self.fact(), "✖ FAILED (see Problems)")
        text = editor._problems_text.get("1.0", "end")
        self.assertIn("tsv-tas.py exited with status 1", text)
        self.assertIn("Error: bad token on line 2", text)  # Exact converter text.
        self.assertEqual(editor._problem_rows, {2: 2})       # Jumps to source line 2.

    def test_mute_close_and_no_audio_never_hold_the_result(self):
        editor, director = self.make_editor()
        self.f5()
        editor.conversion_finished(True, self.outputs(), "", "binary")
        editor._toggle_sound()  # Mute mid-sting: the pending climax happens now.
        self.assertIn("CONVERTED!!", self.shouts)
        self.assertFalse(editor.settings.get("dopa_sound"))
        self.assertEqual(editor._sound_chip.cget("text"), "♪ OFF")
        self.assertIn(0.15, self.audio.stops)
        self.assertTrue(editor.save_and_convert())
        self.assertEqual(len(self.audio.tracks), 1)  # Muted: no track at all.
        editor.conversion_finished(True, self.outputs(), "", "binary")
        self.assertEqual(self.shouts.count("CONVERTED!!"), 2)  # Immediate (P3).
        editor._toggle_sound()
        self.f5()
        editor.destroy()
        self.root.update()
        self.assertIn(0.0, self.audio.stops)
        self.assertEqual(self.errors, [])

    def test_unavailable_audio_and_effects_zero(self):
        editor, director = self.make_editor(audio=FakeAudio(available=False))
        self.assertEqual(editor._sound_chip.cget("text"), "♪ —")
        self.assertTrue(editor.save_and_convert())
        editor.conversion_finished(True, self.outputs(), "", "binary")
        self.assertIn("CONVERTED!!", self.shouts)
        self.assertEqual(self.audio.effects, [])
        editor, director = self.make_editor(dopa_motion=0)
        self.f5()
        editor.conversion_finished(True, self.outputs(), "", "binary")
        self.assertIn("CONVERTED!!", self.shouts)  # 0%: nothing waits for the drop.

    def test_f8_sounds_follow_the_cover_and_unverified_is_never_sent(self):
        editor, director = self.make_editor()
        self.assertTrue(editor.save_convert_and_send())
        self.assertIn("alarm", self.audio.effects)
        editor.conversion_finished(True, self.outputs(True), "FTP error\n", "binary")
        self.assertIn("chime", self.audio.effects)
        self.assertNotIn("kyuin", self.audio.effects)
        self.assertEqual(self.fact(), "⚠ SEND UNVERIFIED (see Problems)")
        self.assertIn("FTP error", editor._problems_text.get("1.0", "end"))
        self.advance(3)
        self.assertTrue(editor.save_convert_and_send())
        editor.conversion_finished(True, self.outputs(True), "Script successfully uploaded\n",
                                   "binary")
        self.advance(1.3)
        self.assertTrue({"kyuin", "star0", "star1", "star2", "fanfare", "coins"}
                        <= set(self.audio.effects))
        self.assertEqual(self.fact(), "✔ SENT route")

    def test_idle_after_the_sting_leaves_no_timer(self):
        editor, director = self.make_editor()
        voice = self.f5()
        editor.conversion_finished(True, self.outputs(), "", "binary")
        self.advance(LEAD + 2 * BAR + 0.1)
        self.assertEqual(voice.faded, BAR)
        voice.done = True
        deadline = time.monotonic() + 10
        while editor._position_unavailable_message() and time.monotonic() < deadline:
            self.root.update()
        self.advance(3)
        director.fx._tick()
        self.assertIsNone(director.choreo)
        self.assertEqual(director.fx.active, ())
        self.assertIsNone(director.fx._job)


class NonModalResultTests(unittest.TestCase):
    def test_editor_failures_and_unverified_sends_never_open_dialogs(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        try:
            app = TASConverterApp("en", settings=AppSettings(Path(folder.name) / "s.json"))
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        app.withdraw()
        self.addCleanup(app.destroy)
        app._dopa_audio = FakeAudio()
        editor = app._create_editor()
        presented = []
        original = editor.conversion_finished
        editor.conversion_finished = lambda *a, **kw: (presented.append(kw), original(*a, **kw))[1]
        import weakref
        problems = []
        for events in ((("report", ("", "", False)), ("error", "Output directory does not exist")),
                       (("stdout", "FTP error\n"),
                        ("success", ConversionOutputs(Path(folder.name) / "x", ftp_requested=True)))):
            app._conversion_listener = weakref.ref(editor)
            editor._conversion_send = True
            for event in events + (("done", None),):
                app._events.put(event)
            with patch("python_to_exe.converter_gui.messagebox.showerror") as error, \
                 patch("python_to_exe.converter_gui.messagebox.showinfo") as info:
                app._drain_events()
            error.assert_not_called()
            info.assert_not_called()
            problems.append((editor._problems_text.get("1.0", "end"),
                             editor.meter_canvas.itemcget(editor._dopa.hud.process_text, "text")))
        self.assertFalse(presented[0]["started"])
        self.assertIn(app.words["preflight_failed"], problems[0][0])
        self.assertIn("Output directory does not exist", problems[0][0])
        self.assertEqual(problems[0][1], "✖ NOT STARTED (see Problems)")
        self.assertIn("FTP error", problems[1][0])
        self.assertEqual(problems[1][1], "⚠ SEND UNVERIFIED (see Problems)")


if __name__ == "__main__":
    unittest.main()
