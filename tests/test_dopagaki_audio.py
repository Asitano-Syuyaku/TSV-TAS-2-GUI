"""D3.1 standard Windows audio, deterministic only; no real player or long wait."""

import base64
import gc
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave
import weakref

from test_dopagaki import Clock, Scheduler
from test_dopagaki_ritual import View
from python_to_exe.editor.dopagaki import audio
from python_to_exe.editor.dopagaki.motion import Intensity
from python_to_exe.editor.dopagaki.ritual import ConvertRitual, DROP_SECONDS, RitualState


class Process:
    def __init__(self):
        self.returncode = None
        self.terminated = self.killed = self.waits = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated += 1
        self.returncode = -15

    def kill(self):
        self.killed += 1
        self.returncode = -9

    def wait(self, timeout=None):
        self.waits += 1
        return self.returncode


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.wav = Path(self.folder.name) / "Let's Go $() 日本語.wav"
        with wave.open(str(self.wav), 'wb') as clip:
            clip.setparams((2, 2, 48000, 12000, 'NONE', 'not compressed'))
            clip.writeframes(b'\0' * 48000)
        self.clock = Clock()
        self.module = SimpleNamespace(SND_FILENAME=1, SND_ASYNC=2, SND_NODEFAULT=4,
                                      PlaySound=Mock())
        self.addCleanup(self.clear_native)

    def clear_native(self):
        owner = audio.WinSoundBackend._owner
        if owner is not None and owner() is not None:
            owner().stop()
        audio.WinSoundBackend._owner = None

    def powershell(self, popen=None):
        backend = audio.SoundPlayerBackend('powershell.exe', popen=popen or Mock(return_value=Process()))
        backend._translate = Mock(return_value="C:\\Users\\O'Brien\\$() 日本語.wav")
        self.addCleanup(backend.close)
        return backend

    def native(self):
        backend = audio.WinSoundBackend(module=self.module, clock=self.clock)
        self.addCleanup(backend.close)
        return backend

    def test_default_prefers_local_wav_with_webm_fallback(self):
        with patch('pathlib.Path.home', return_value=Path(self.folder.name)):
            storage = Path(self.folder.name) / '.local/share/tsv-tas-2-gui/dopagaki'
            storage.mkdir(parents=True)
            webm, wav = storage/'lets_go_dopagaki.webm', storage/'lets_go_dopagaki_f5.wav'
            self.assertEqual(audio.AudioConfig().media_path, str(webm))
            webm.write_bytes(b'not decoded by Python')
            wav.write_bytes(self.wav.read_bytes())
            self.assertEqual(audio.AudioConfig().media_path, str(wav))
            self.assertEqual(audio.AudioConfig(path=str(webm)).media_path, str(webm))

    def test_runtime_platform_detection(self):
        with patch.object(audio.sys, 'platform', 'win32'):
            self.assertEqual(audio._runtime_platform(), 'windows')
        with patch.object(audio.sys, 'platform', 'linux'), patch.dict(audio.os.environ, {}, clear=True):
            with patch.object(audio.platform, 'release', return_value='6.6-microsoft-standard-WSL2'):
                self.assertEqual(audio._runtime_platform(), 'wsl')
            with patch.object(audio.platform, 'release', return_value='6.6-generic'):
                self.assertEqual(audio._runtime_platform(), 'other')
                with patch.dict(audio.os.environ, {'WSL_INTEROP': '/run/WSL/1_interop'}):
                    self.assertEqual(audio._runtime_platform(), 'wsl')

    def test_factory_platform_priority_and_no_load_at_editor_init(self):
        for runtime, expected in [('windows', audio.WinSoundBackend), ('wsl', audio.SoundPlayerBackend),
                                  ('other', audio.FFplayBackend)]:
            with patch.object(audio, '_runtime_platform', return_value=runtime), \
                 patch.object(audio.wave, 'open') as load, patch.object(audio.subprocess, 'Popen') as spawn:
                backend = audio.create_audio_backend(audio.AudioConfig())
                self.assertIsInstance(backend._candidates[0], expected)
                self.assertIsInstance(backend._candidates[-1], audio.FFplayBackend)
                self.assertEqual(backend.name, 'visual-only')
                load.assert_not_called()
                spawn.assert_not_called()
                backend.close()

    def test_native_async_file_and_header_only_no_memory_payload(self):
        backend = self.native()
        with patch.object(wave.Wave_read, 'readframes', side_effect=AssertionError('PCM load')):
            self.assertTrue(backend.play(self.wav))
        self.module.PlaySound.assert_called_once_with(str(self.wav), 7)
        self.assertTrue(backend.poll())
        self.assertIsNone(backend.process)
        self.assertEqual(backend.launched_at, self.clock.now)

    def test_native_stop_replace_close(self):
        backend = self.native()
        self.assertTrue(backend.play(self.wav))
        self.assertTrue(backend.play(self.wav))
        self.assertEqual(self.module.PlaySound.call_args_list[1].args, (None, 0))
        self.assertTrue(backend.stop())
        self.assertFalse(backend.poll())
        backend.close()
        self.assertFalse(backend.play(self.wav))

    def test_native_duration_poll_without_after_or_worker(self):
        backend = self.native()
        backend.play(self.wav)
        self.clock.now += .249
        self.assertTrue(backend.poll())
        self.clock.now += .002
        self.assertFalse(backend.poll())

    def test_native_global_owner_and_old_editor_cannot_stop_new_sound(self):
        first, second = self.native(), self.native()
        first.play(self.wav)
        second.play(self.wav)
        self.assertFalse(first.poll())
        self.assertTrue(second.poll())
        calls = self.module.PlaySound.call_count
        first.close()
        self.assertEqual(self.module.PlaySound.call_count, calls)
        self.assertTrue(second.poll())

    def test_native_failed_stop_prevents_replacement(self):
        backend = self.native()
        backend.play(self.wav)
        self.module.PlaySound.side_effect = RuntimeError('device failure')
        self.assertFalse(backend.play(self.wav))
        self.assertEqual(self.module.PlaySound.call_count, 2)  # Only attempted stop.
        self.module.PlaySound.side_effect = None

    def test_native_missing_module_and_device_exception_are_nonfatal(self):
        backend = audio.WinSoundBackend()
        with patch.dict('sys.modules', {'winsound': None}):
            self.assertFalse(backend.play(self.wav))
        backend = self.native()
        self.module.PlaySound.side_effect = RuntimeError('no sound device')
        self.assertFalse(backend.play(self.wav))
        self.assertFalse(backend.poll())

    def test_native_missing_non_wav_corrupt_and_relative_files_rejected(self):
        backend = self.native()
        corrupt = Path(self.folder.name)/'bad.wav'
        corrupt.write_bytes(b'not WAV')
        webm = Path(self.folder.name)/'audio.webm'
        webm.write_bytes(b'not WAV')
        for path in (self.wav.parent/'missing.wav', corrupt, webm, 'relative.wav', 'bad\0.wav'):
            self.assertFalse(backend.play(path))
        self.module.PlaySound.assert_not_called()

    def test_soundplayer_encoded_path_is_data_and_shell_free(self):
        popen = Mock(return_value=Process())
        backend = self.powershell(popen)
        self.assertTrue(backend.play(self.wav))
        argv, = popen.call_args.args
        self.assertEqual(argv[0], 'powershell.exe')
        self.assertIn('-NonInteractive', argv)
        script = base64.b64decode(argv[-1]).decode('utf-16-le')
        self.assertIn('$player.Load(); $player.PlaySync()', script)
        self.assertIn('$player.Stop(); $player.Dispose()', script)
        self.assertNotIn("O'Brien", script)
        encoded_path = script.split("FromBase64String('", 1)[1].split("')", 1)[0]
        self.assertEqual(base64.b64decode(encoded_path).decode('utf-8'), backend._translate.return_value)
        self.assertFalse(popen.call_args.kwargs.get('shell', False))
        self.assertEqual(popen.call_args.kwargs['stdout'], subprocess.DEVNULL)
        backend._translate.assert_called_once_with(self.wav, '-w')

    def test_soundplayer_stop_replace_and_reap(self):
        first, second = Process(), Process()
        backend = self.powershell(Mock(side_effect=[first, second]))
        self.assertTrue(backend.play(self.wav))
        self.assertTrue(backend.poll())
        self.assertTrue(backend.play(self.wav))
        self.assertEqual((first.terminated, first.waits), (1, 1))
        self.assertIs(backend.process, second)
        backend.close()
        self.assertEqual((second.terminated, second.waits), (1, 1))
        self.assertIsNone(backend.process)
        self.assertFalse(backend.play(self.wav))

    def test_soundplayer_natural_exit_and_midplay_failure(self):
        for code in (0, 1):
            backend = self.powershell()
            backend.play(self.wav)
            process = backend.process
            process.returncode = code
            self.assertFalse(backend.poll())
            self.assertIsNone(backend.process)
            self.assertEqual(bool(backend.last_error), bool(code))

    def test_soundplayer_timeout_kill_and_reap(self):
        process = Mock(poll=Mock(return_value=None),
                       wait=Mock(side_effect=[subprocess.TimeoutExpired('powershell', .15), 0]))
        backend = self.powershell(Mock(return_value=process))
        backend.play(self.wav)
        self.assertTrue(backend.stop())
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)

    def test_soundplayer_missing_bad_wav_invalid_path_and_spawn_failure(self):
        spawn = Mock(side_effect=OSError('spawn failed'))
        backend = self.powershell(spawn)
        for path in ('relative.wav', 'bad\0.wav', self.wav.parent/'missing.wav'):
            self.assertFalse(backend.play(path))
        spawn.assert_not_called()
        self.assertFalse(backend.play(self.wav))
        self.assertIn('spawn failed', backend.last_error)
        self.assertIsNone(backend.process)

    def test_soundplayer_missing_powershell(self):
        backend = audio.SoundPlayerBackend(popen=Mock())
        with patch.object(audio.shutil, 'which', return_value=None):
            self.assertFalse(backend.play(self.wav))
        backend._popen.assert_not_called()

    def test_soundplayer_translation_error(self):
        backend = self.powershell()
        backend._translate.side_effect = subprocess.TimeoutExpired('wslpath', 2)
        self.assertFalse(backend.play(self.wav))
        backend._popen.assert_not_called()

    def test_auto_native_windows_wav_first(self):
        backend = audio.AutoAudioBackend(audio.AudioConfig(player='/explicit/ffplay'), runtime='windows')
        backend._candidates[0]._module = self.module
        backend._candidates[-1]._popen = Mock()
        self.assertTrue(backend.play(self.wav))
        self.assertEqual(backend.name, 'winsound')
        backend._candidates[-1]._popen.assert_not_called()
        backend.close()

    def test_auto_wsl_wav_first_and_explicit_ffplay_fallback(self):
        backend = audio.AutoAudioBackend(audio.AudioConfig(player='/explicit/ffplay'), runtime='wsl')
        native, ffplay = backend._candidates
        native.powershell = 'powershell.exe'
        native._translate = Mock(return_value='C:\\audio.wav')
        native._popen = Mock(return_value=Process())
        ffplay._popen = Mock(return_value=Process())
        self.assertTrue(backend.play(self.wav))
        self.assertEqual(backend.name, 'PowerShell SoundPlayer')
        ffplay._popen.assert_not_called()
        native._popen.side_effect = OSError('PowerShell spawn failed')
        self.assertTrue(backend.play(self.wav))
        self.assertEqual(backend.name, 'ffplay')
        backend.close()

    def test_auto_missing_wav_webm_uses_ffplay_and_keeps_user_override(self):
        backend = audio.AutoAudioBackend(audio.AudioConfig(player='/explicit/ffplay'), runtime='windows')
        native, ffplay = backend._candidates
        native._module = self.module
        ffplay._popen = Mock(return_value=Process())
        webm = self.wav.with_suffix('.webm')
        webm.write_bytes(b'backend consumes compressed file')
        self.assertTrue(backend.play(webm))
        self.assertEqual(backend.name, 'ffplay')
        self.module.PlaySound.assert_not_called()
        self.assertEqual(ffplay._popen.call_args.args[0][-1], str(webm))
        backend.close()

    def test_auto_missing_native_and_ffplay_is_visual_only(self):
        backend = audio.AutoAudioBackend(audio.AudioConfig(), runtime='wsl')
        with patch.object(audio.shutil, 'which', return_value=None):
            self.assertFalse(backend.play(self.wav))
        self.assertEqual(backend.name, 'visual-only')
        self.assertIsNone(backend.process)
        self.assertIn('unavailable', backend.last_error)
        backend.close()

    def test_auto_failed_stop_keeps_ownership_and_never_launches_fallback(self):
        backend = audio.AutoAudioBackend(audio.AudioConfig(player='/explicit/ffplay'), runtime='wsl')
        native, ffplay = backend._candidates
        native.powershell, native._translate = 'powershell.exe', Mock(return_value='C:\\audio.wav')
        process = Mock(poll=Mock(return_value=None), terminate=Mock(side_effect=OSError('denied')))
        native._popen, ffplay._popen = Mock(return_value=process), Mock()
        self.assertTrue(backend.play(self.wav))
        self.assertFalse(backend.play(self.wav))
        self.assertIs(backend.process, process)
        ffplay._popen.assert_not_called()
        process.terminate.side_effect = None
        backend.close()

    def test_auto_cannot_overlap_a_different_native_owner_whose_stop_failed(self):
        first = self.native()
        first.play(self.wav)
        backend = audio.AutoAudioBackend(audio.AudioConfig(player='/explicit/ffplay'), runtime='windows')
        backend._candidates[0]._module = self.module
        backend._candidates[-1]._popen = Mock()
        self.module.PlaySound.side_effect = RuntimeError('native stop failed')
        self.assertFalse(backend.play(self.wav))
        backend._candidates[-1]._popen.assert_not_called()
        self.assertIn('native stop failed', backend.last_error)
        self.module.PlaySound.side_effect = None
        backend.close()

    def test_auto_midplay_exit_is_visual_only_no_second_player(self):
        backend = audio.AutoAudioBackend(audio.AudioConfig(player='/explicit/ffplay'), runtime='other')
        backend._candidates[0]._popen = Mock(return_value=Process())
        backend.play(self.wav)
        backend.process.returncode = 1
        self.assertFalse(backend.poll())
        self.assertIsNone(backend.process)
        backend._candidates[0]._popen.assert_called_once()
        backend.close()

    def test_auto_close_releases_player_and_rejects_future_play(self):
        backend = audio.AutoAudioBackend(audio.AudioConfig(player='/explicit/ffplay'), runtime='other')
        backend._candidates[0]._popen = Mock(return_value=Process())
        backend.play(self.wav)
        process = backend.process
        backend.close()
        self.assertEqual((process.terminated, process.waits), (1, 1))
        self.assertIsNone(backend.process)
        self.assertFalse(backend.play(self.wav))

    def test_ritual_generation_off_cancel_and_close_with_process_backend(self):
        scheduler, view = Scheduler(), View()
        backend = self.powershell()
        ritual = ConvertRitual(scheduler, view, backend=backend,
                               config=audio.AudioConfig(path=str(self.wav)), clock=self.clock)
        ritual.start(Intensity.OFF)
        self.assertIsNone(backend.process)
        self.assertFalse(scheduler.jobs)
        ritual.start()
        first = backend.process
        stale = ritual.receiver()
        ritual.start()
        self.assertEqual(first.waits, 1)
        stale(True)
        self.assertEqual(ritual.state, RitualState.PRELUDE)
        self.clock.now += DROP_SECONDS
        scheduler.run_next()
        self.assertEqual(ritual.state, RitualState.WAITING_FOR_CONVERTER)
        self.assertNotIn('success', [event[0] for event in view.events])
        ritual.cancel()
        self.assertIsNone(backend.process)
        self.assertFalse(scheduler.jobs)
        reference = weakref.ref(ritual)
        ritual.close()
        del ritual
        gc.collect()
        self.assertIsNone(reference())
        stale(False)


if __name__ == '__main__':
    unittest.main()
