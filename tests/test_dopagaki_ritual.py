"""D3 fake-clock timelines, truthful results, one-player and UI isolation."""

import gc
import json
from pathlib import Path
from queue import SimpleQueue
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import weakref
from tkinter import TclError

from test_dopagaki import Clock, Scheduler, headless_grid
from test_dopagaki_hype import enable, ParticleCanvas
from test_dopagaki_micro import Widget, frame_values
from python_to_exe.converter_gui import TASConverterApp, TEXT
from python_to_exe.converter_logic import build_commands
from python_to_exe.dopagaki_app import DopagakiApp
from python_to_exe.editor.document import EditorDocument
from python_to_exe.editor.debug_csv import StickFrame, StickState
from python_to_exe.editor.dopagaki.audio import AudioBackend, AudioConfig, AudioSettings, FFplayBackend, default_audio_path
from python_to_exe.editor.dopagaki.motion import Intensity
from python_to_exe.editor.dopagaki.particles import CAPS
from python_to_exe.editor.dopagaki.ritual import ConvertRitual, DROP_SECONDS, RitualState, RitualTimeline
from python_to_exe.editor.dopagaki.ritual_view import RitualView, STAMP_TAG, STATIC_TAG, PARTICLE_OWNER
from python_to_exe.editor.dopagaki.ui import DopagakiEditorWindow
from python_to_exe.editor.dopagaki.widgets import DopagakiStickPreview


class View:
    def __init__(self):
        self.events = []
        self.clears = 0

    def show(self, event, progress, **options):
        self.events.append((event, progress, options))

    def clear(self):
        self.clears += 1


class Backend(AudioBackend):
    def __init__(self):
        self.playing = False
        self.paths = []
        self.stops = 0

    def play(self, path):
        if self.playing:
            raise AssertionError("overlapping playback")
        self.paths.append(path)
        self.playing = True
        return True

    def poll(self):
        return self.playing

    def stop(self):
        self.stops += 1
        self.playing = False


class RitualTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.scheduler, self.view, self.backend = Clock(), Scheduler(), View(), Backend()
        self.ritual = ConvertRitual(self.scheduler, self.view, backend=self.backend, clock=self.clock)
        self.origin = self.clock.now

    def tearDown(self):
        self.ritual.close()

    def start(self, level=Intensity.MID):
        self.origin = self.clock.now
        return self.ritual.start(level)

    def advance(self, elapsed):
        self.clock.now = self.origin + elapsed
        self.scheduler.run_next()

    def names(self):
        return [event for event, _progress, _options in self.view.events]

    def test_exact_timeline_and_countdown_sparse_single_callback(self):
        self.start()
        self.assertEqual(DROP_SECONDS, 21.506)
        self.assertEqual(self.names(), ["start"])
        self.assertEqual(next(iter(self.scheduler.jobs.values()))[0], 6000)
        for at, event in self.ritual.timeline.events(self.ritual.config):
            self.advance(at)
            self.assertEqual(self.names()[-1], "pending" if event == "drop" else event)
            self.assertLessEqual(len(self.scheduler.jobs), 1)
        countdown = [(at, event) for at, event in self.ritual.timeline.events(self.ritual.config)
                     if event in ("3", "2", "1", "drop")]
        for (at, event), expected in zip(countdown, (18.506, 19.506, 20.506, 21.506)):
            self.assertAlmostEqual(at, expected)
        self.assertFalse(self.scheduler.jobs)
        self.assertFalse(self.backend.playing)

    def test_early_success_latches_boolean_until_drop(self):
        token = self.start()
        payload = object()
        self.clock.now += 1.2
        self.ritual.receiver()(True, payload)
        self.assertEqual(self.ritual.state, RitualState.SUCCESS_READY)
        self.assertNotIn("success", self.names())
        self.assertIs(self.ritual._result, True)
        self.advance(DROP_SECONDS)
        self.assertEqual(self.names()[-2:], ["drop", "success"])
        self.assertEqual(self.ritual.state, RitualState.SUCCESS_FINALE)
        self.assertFalse(self.ritual.result(token, True))  # one reward only

    def test_drop_with_pending_converter_never_claims_success(self):
        token = self.start()
        self.advance(DROP_SECONDS)
        self.assertEqual(self.names()[-2:], ["drop", "pending"])
        self.assertNotIn("success", self.names())
        self.assertEqual(self.ritual.state, RitualState.WAITING_FOR_CONVERTER)
        self.clock.now += 2
        self.assertTrue(self.ritual.result(token, True))
        self.assertEqual(self.names()[-1], "success")

    def test_late_success_after_audio_settle_still_gets_fresh_finale(self):
        token = self.start()
        self.advance(DROP_SECONDS + 8)
        self.assertFalse(self.scheduler.jobs)
        self.assertEqual(self.ritual.state, RitualState.WAITING_FOR_CONVERTER)
        self.assertTrue(self.ritual.result(token, True))
        self.assertEqual(self.names()[-1], "success")

    def test_result_arrives_after_drop_before_delayed_phase_callback(self):
        token = self.start()
        self.clock.now = self.origin + DROP_SECONDS + 0.3
        self.ritual.result(token, True)
        self.assertEqual(self.names()[-2:], ["drop", "success"])
        self.assertEqual(len(self.scheduler.jobs), 1)

    def test_result_arrives_after_whole_timeline_before_phase_callback(self):
        token = self.start()
        self.clock.now = self.origin + 80
        self.ritual.result(token, True)
        self.assertEqual(self.names()[-1], "success")
        self.assertNotIn("3", self.names())
        self.assertFalse(self.backend.playing)
        self.assertFalse(self.scheduler.jobs)

    def test_failure_before_and_after_drop_cancels_success_and_audio(self):
        for at in (1.2, DROP_SECONDS + 1):
            token = self.start()
            stale = next(iter(self.scheduler.jobs.values()))[1]
            self.clock.now += at
            self.ritual.result(token, False)
            self.assertEqual(self.ritual.state, RitualState.FAILED)
            self.assertEqual(self.names()[-1], "failure")
            self.assertNotIn("success", self.names())
            self.assertFalse(self.backend.playing)
            self.assertFalse(self.scheduler.jobs)
            previous = list(self.view.events)
            stale()
            self.assertEqual(self.view.events, previous)

    def test_failure_after_emitted_music_drop_never_emits_conversion_success(self):
        token = self.start()
        self.advance(DROP_SECONDS)
        self.ritual.result(token, False)
        self.assertEqual(self.names(), ['start', 'drop', 'pending', 'failure'])
        self.assertFalse(self.scheduler.jobs)
        self.assertFalse(self.backend.playing)

    def test_delayed_wake_skips_missed_countdowns_and_sparks(self):
        self.start()
        self.advance(20.7)
        self.assertEqual(self.names(), ["start", "1"])
        self.advance(23)
        self.assertEqual(self.names()[-2:], ["drop", "pending"])

    def test_cancel_and_repeat_generation_reject_old_results_and_timer(self):
        self.start()
        receiver = self.ritual.receiver()
        stale = next(iter(self.scheduler.jobs.values()))[1]
        self.ritual.cancel()
        self.assertFalse(self.scheduler.jobs)
        self.start()
        jobs, events = dict(self.scheduler.jobs), list(self.view.events)
        receiver(True)
        stale()
        self.assertEqual(self.scheduler.jobs, jobs)
        self.assertEqual(self.view.events, events)
        self.assertEqual(self.ritual.state, RitualState.PRELUDE)
        self.assertEqual(len(self.scheduler.jobs), 1)

    def test_off_and_muted_start(self):
        self.start(Intensity.OFF)
        self.assertFalse(self.view.events)
        self.assertFalse(self.backend.paths)
        self.assertFalse(self.scheduler.jobs)
        self.ritual.config = AudioConfig(enabled=False)
        self.start()
        self.assertEqual(self.names(), ["start"])
        self.assertFalse(self.backend.paths)

    def test_audio_missing_backend_exception_and_mid_play_failure_are_visual_only(self):
        for failing in (AudioBackend(), Mock(play=Mock(side_effect=OSError("unavailable")),
                                           stop=Mock(), close=Mock())):
            self.ritual.backend = failing
            self.start()
            self.advance(DROP_SECONDS)
            self.assertEqual(self.names()[-2:], ["drop", "pending"])
            self.assertNotEqual(self.ritual.state, RitualState.FAILED)
        self.ritual.backend = self.backend
        token = self.start()
        self.backend.playing = False
        self.advance(6)
        self.assertFalse(self.ritual.audio_playing)
        self.ritual.result(token, True)
        self.advance(DROP_SECONDS)
        self.assertEqual(self.names()[-1], "success")

    def test_sync_offset_moves_visual_events_only(self):
        self.ritual.config = AudioConfig(sync_offset_ms=250)
        self.start()
        self.advance(DROP_SECONDS)
        self.assertNotIn("drop", self.names())
        self.advance(DROP_SECONDS + 0.250)
        self.assertEqual(self.names()[-2:], ["drop", "pending"])
        self.assertEqual(self.backend.paths, [str(default_audio_path())])

    def test_visual_only_drop_has_no_unnecessary_audio_tail_callback(self):
        self.ritual.backend = AudioBackend()
        self.start()
        self.advance(DROP_SECONDS)
        self.assertFalse(self.scheduler.jobs)
        self.assertEqual(self.ritual.state, RitualState.WAITING_FOR_CONVERTER)

    def test_deterministic_replacements_cleanup_and_collectability(self):
        receivers = []
        for _ in range(100):
            self.start()
            receivers.append(self.ritual.receiver())
            self.clock.now += 0.2
            self.assertEqual(len(self.scheduler.jobs), 1)
        reference = weakref.ref(self.ritual)
        self.ritual.close()
        self.assertFalse(self.scheduler.jobs)
        self.assertFalse(self.backend.playing)
        ritual, self.ritual = self.ritual, ConvertRitual(self.scheduler, View(), clock=self.clock)
        del ritual
        gc.collect()
        self.assertIsNone(reference())
        for receiver in receivers:
            receiver(True)

    def test_short_timeline_is_injected_not_a_production_setting(self):
        timeline = RitualTimeline(drop=0.4, countdown_step=0.05,
                                  build_events=((0.08, "build"), (0.16, "tension")))
        self.ritual.timeline = timeline
        self.start()
        self.advance(0.4)
        self.assertIn("drop", self.names())
        self.assertEqual(RitualTimeline().drop, DROP_SECONDS)
        with self.assertRaises(ValueError):
            RitualTimeline(drop=float("nan"))


class AudioTests(unittest.TestCase):
    def test_local_defaults_and_settings_are_separate_and_sanitized(self):
        with tempfile.TemporaryDirectory() as directory, patch("pathlib.Path.home", return_value=Path(directory)):
            self.assertEqual(default_audio_path(), Path(directory)/".local/share/tsv-tas-2-gui/dopagaki/lets_go_dopagaki.webm")
            path = Path(directory)/"dopagaki_audio.json"
            settings = AudioSettings(path)
            self.assertTrue(settings.update(enabled=False, path=str(Path(directory)/"audio 日本語.webm"),
                                            player="C:\\FFmpeg\\ffplay.exe", sync_offset_ms=120, volume=50))
            self.assertEqual(AudioSettings(path).config, settings.config)
            saved = json.loads(path.read_text())
            self.assertNotIn("document", saved)
            self.assertNotIn("hype", saved)
            self.assertEqual(AudioConfig.clean({'path': 'relative', 'volume': True,
                                                'sync_offset_ms': float('inf'), 'tail_seconds': float('nan')}), AudioConfig())
            path.write_text('{invalid')
            self.assertEqual(AudioSettings(path).config, AudioConfig())

    def test_missing_player_missing_file_and_spawn_exception(self):
        backend = FFplayBackend()
        with patch("python_to_exe.editor.dopagaki.audio.shutil.which", return_value=None):
            self.assertFalse(backend.play("missing.webm"))
        backend = FFplayBackend("ffplay", popen=Mock(side_effect=OSError("spawn failed")))
        self.assertFalse(backend.play("missing.webm"))
        with tempfile.NamedTemporaryFile(suffix='.webm') as handle:
            self.assertFalse(backend.play(handle.name))
        self.assertIsNone(backend.process)

    def test_safe_argv_replacement_termination_and_natural_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"Let's Go $not_shell 日本語.webm"
            path.write_bytes(b"audio stub")
            processes = [Mock(poll=Mock(return_value=None)), Mock(poll=Mock(return_value=None))]
            popen = Mock(side_effect=processes)
            backend = FFplayBackend('/usr/bin/ffplay', popen=popen)
            self.assertTrue(backend.play(path))
            argv, = popen.call_args.args
            self.assertEqual(argv[-1], str(path))
            self.assertIn('-nodisp', argv)
            self.assertFalse(popen.call_args.kwargs.get('shell', False))
            self.assertTrue(backend.play(path))
            processes[0].terminate.assert_called_once()
            processes[0].wait.assert_called_once()
            processes[1].poll.return_value = 1
            self.assertFalse(backend.poll())
            self.assertIsNone(backend.process)
            self.assertIn('status 1', backend.last_error)
            backend.close()
            self.assertFalse(backend.play(path))

    def test_terminate_timeout_kills_and_reaps(self):
        process = Mock(poll=Mock(return_value=None),
                       wait=Mock(side_effect=[subprocess.TimeoutExpired('ffplay', .15), 0]))
        backend = FFplayBackend()
        backend._process = process
        self.assertTrue(backend.stop())
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)
        self.assertIsNone(backend.process)

    def test_stop_failure_does_not_overlap_a_new_player(self):
        process = Mock(poll=Mock(return_value=None), terminate=Mock(side_effect=OSError('denied')))
        backend = FFplayBackend('/usr/bin/ffplay', popen=Mock())
        backend._process = process
        self.assertFalse(backend.play('new.webm'))
        backend._popen.assert_not_called()
        self.assertIs(backend.process, process)

    def test_windows_player_on_wsl_translates_paths_without_shell(self):
        with tempfile.NamedTemporaryFile(suffix='.webm') as handle:
            process = Mock(poll=Mock(return_value=None))
            backend = FFplayBackend('C:\\tools\\ffplay.exe', popen=Mock(return_value=process))
            with patch('python_to_exe.editor.dopagaki.audio.os.name', 'posix'), \
                 patch.object(backend, '_translate', side_effect=['/mnt/c/tools/ffplay.exe',
                                                                  '\\\\wsl.localhost\\Ubuntu\\media.webm']) as translate:
                self.assertTrue(backend.play(handle.name))
                self.assertEqual(backend._popen.call_args.args[0][0], '/mnt/c/tools/ffplay.exe')
                self.assertEqual(backend._popen.call_args.args[0][-1], '\\\\wsl.localhost\\Ubuntu\\media.webm')
                self.assertEqual([call.args[1] for call in translate.call_args_list], ['-u', '-w'])
            backend.close()


class Editor(SimpleNamespace):
    pass


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.grid = headless_grid()
        self.meter, self.border = enable(self.grid)
        self.effects = self.grid.effects
        self.editor = Editor(table_grid=self.grid, frame_status=frame_values(self.effects),
                             _palette_page_label=Widget(),
                             stick_preview=SimpleNamespace(winfo_ismapped=lambda: False),
                             _problems_panel=SimpleNamespace(winfo_ismapped=lambda: False),
                             master=SimpleNamespace(log_text=Widget()))
        self.view = RitualView(self.editor)
        self.effects.attach_ritual(self.view)
        self.effects.set_intensity(Intensity.FULL)
        self.view.level = Intensity.FULL

    def tearDown(self):
        self.view.close()
        self.grid.close_effects()

    def idle(self):
        self.grid.clock.now += 2
        if self.grid.scheduler.jobs:
            self.grid.scheduler.run_next()
        self.assertFalse(self.effects.motion.pending)
        self.assertFalse(self.effects.particles.particles)

    def test_countdown_stamp_shares_existing_motion_callback_and_cap(self):
        for event in ('start', 'build', 'tension', '3', '2', '1', 'drop', 'success'):
            self.view.show(event, 1)
            self.assertEqual(len(self.grid.scheduler.jobs), 1)
            self.assertLessEqual(len(self.effects.motion.effect.tracks), 8)
            self.assertLessEqual(len(self.effects.particles.particles), CAPS['FULL'])
        self.assertTrue(any(item.get('tags') == STAMP_TAG for item in self.grid.canvas.items.values()))
        self.idle()
        self.assertFalse(any(item.get('tags') == STAMP_TAG for item in self.grid.canvas.items.values()))
        self.view.clear()
        self.assertFalse(any(item.get('tags') == STATIC_TAG for item in self.grid.canvas.items.values()))

    def test_countdown_typography_and_border_escalate_without_widget_geometry_changes(self):
        sizes, widths = [], []
        for event in ('3', '2', '1'):
            self.view.show(event, .9)
            sizes.append(self.grid.canvas.items[self.view._items[-1]]['font'][1])
            widths.append(next(item['width'] for item in self.grid.canvas.items.values()
                               if item.get('tags') == STATIC_TAG and 'outline' in item))
        self.assertLess(sizes[0], sizes[1])
        self.assertLess(sizes[1], sizes[2])
        self.assertLess(widths[0], widths[1])
        self.assertLess(widths[1], widths[2])
        self.assertEqual(self.grid.canvas.focus_count, 0)

    def test_long_stamp_uses_measured_peak_width_and_refits_after_resize(self):
        interpreter = SimpleNamespace(call=Mock(return_value=1200))
        self.grid.canvas.tk = interpreter
        self.view.show('failure', 0)
        size = self.grid.canvas.items[self.view._items[-1]]['font'][1]
        self.assertLess(size, 40)
        interpreter.call.assert_called_once()
        self.view.repaint()
        interpreter.call.assert_called_once()  # No per-frame font measurement.
        self.grid.canvas.width = 400
        self.view.repaint()
        resized = self.grid.canvas.items[self.view._items[-1]]['font'][1]
        self.assertLess(resized, size)
        self.assertEqual(interpreter.call.call_count, 2)

    def test_ritual_does_not_mutate_hype_document_history_selection_or_frame_values(self):
        document = EditorDocument()
        document.set_text(self.grid.model.to_text())
        self.grid.selection.move_to(1, 1, extend=True)
        before = (dict(document.__dict__), self.grid.model.to_text(),
                  self.grid.selection.anchor, self.grid.selection.active, self.grid.selection.bounds,
                  self.effects.hype._value, self.effects.hype._at,
                  self.editor.frame_status.cget('text'))
        self.editor.undo, self.editor.redo = ['prior'], ['future']
        for event in ('start', 'build', 'tension', '3', '2', '1', 'drop', 'success'):
            self.view.show(event, .8)
        self.assertEqual(before, (dict(document.__dict__), self.grid.model.to_text(),
                                  self.grid.selection.anchor, self.grid.selection.active, self.grid.selection.bounds,
                                  self.effects.hype._value, self.effects.hype._at,
                                  self.editor.frame_status.cget('text')))
        self.assertEqual((self.editor.undo, self.editor.redo), (['prior'], ['future']))
        self.assertEqual(self.grid.canvas.focus_count, 0)

    def test_ritual_preview_rings_preserve_resolved_values_and_previous_three_frames(self):
        preview = DopagakiStickPreview.__new__(DopagakiStickPreview)
        preview._effects = weakref.ref(self.effects)
        preview.plots = [ParticleCanvas(180, 126), ParticleCanvas(180, 126)]
        preview.values = [Widget(), Widget()]
        preview.winfo_ismapped = lambda: True
        preview.frame = 3
        state = StickState(16384, 32767, .75, 90)
        preview.samples = tuple(StickFrame(frame, state, state) for frame in (3, 2, 1, 0))
        for column, canvas in enumerate(preview.plots):
            self.effects.particles.register(f'stick{column}', canvas)
            preview._draw(column)
        self.editor.stick_preview = preview
        before = preview.frame, preview.samples, [widget.cget('text') for widget in preview.values]
        for event in ('tension', '1', 'success'):
            self.view.show(event, .9)
            for column in range(2):
                preview._draw(column)
        self.assertEqual(before, (preview.frame, preview.samples, [widget.cget('text') for widget in preview.values]))
        self.assertEqual(tuple(sample.frame for sample in preview.samples), (3, 2, 1, 0))

    def test_cancel_removes_only_ritual_particles_and_leaves_micro_feedback(self):
        self.effects.interaction('palette', origin=(250, 200))
        ordinary = list(self.effects.particles.particles)
        self.view.show('1', 1)
        self.assertTrue(any(particle.owner == PARTICLE_OWNER for particle in self.effects.particles.particles))
        self.view.clear()
        self.assertEqual(self.effects.particles.particles, ordinary)
        self.idle()

    def test_cancel_keeps_user_feedback_that_replaced_a_ritual_pulse(self):
        self.view.show('tension', .8)
        ritual_page = weakref.ref(self.effects.effect_for('page'))
        self.assertIsNotNone(self.effects.effect_for('frame'))
        self.effects.pulse_widget('page', self.editor._palette_page_label, 'page', ink=True)
        user_page = self.effects.effect_for('page')
        self.view.clear()
        self.assertIsNone(self.effects.effect_for('frame'))
        self.assertIs(self.effects.effect_for('page'), user_page)
        gc.collect()
        self.assertIsNone(ritual_page())
        self.idle()

    def test_rapid_replacements_do_not_finish_new_stamp_or_retain_items(self):
        refs = []
        for _ in range(100):
            self.view.show('3', .9)
            facade = self.effects.effect_for('juice')
            refs.append(weakref.ref(facade))
            self.grid.clock.now += .8
            self.view.show('1', 1)
            self.assertEqual(self.view._stamp, '1')
            self.assertLessEqual(len(self.grid.canvas.items), 190)
            self.assertEqual(len(self.grid.scheduler.jobs), 1)
        del facade
        self.view.clear()
        self.idle()
        gc.collect()
        self.assertTrue(all(ref() is None for ref in refs))

    def test_static_build_has_no_motion_ticks_and_scroll_repositions_border(self):
        self.view.show('start', 0)
        self.idle()
        self.assertFalse(self.grid.scheduler.jobs)
        self.grid.canvas.origin_x = 140
        self.grid.canvas.origin_y = 100
        self.view.repaint()
        border = next(item for item in self.grid.canvas.items.values() if item.get('tags') == STATIC_TAG)
        self.assertEqual(border['coords'][:2], (142, 102))
        self.assertFalse(self.grid.scheduler.jobs)

    def test_late_success_decorations_finish_even_without_remaining_phase_callback(self):
        ritual = ConvertRitual(self.grid, self.view, clock=self.grid.clock)
        token = ritual.start()
        self.grid.clock.now += DROP_SECONDS
        self.grid.after_cancel(ritual._job)
        ritual._wake(ritual.generation, ritual._ticket)
        self.assertFalse(ritual.pending)
        self.idle()
        self.assertIsNone(self.view.stage)
        ritual.result(token, True)
        self.assertEqual(self.view._stamp, 'CONVERTED')
        self.idle()
        self.assertIsNone(self.view.stage)
        self.assertEqual(self.view._banner_text, '')
        self.assertFalse(any(item.get('tags') in (STAMP_TAG, STATIC_TAG)
                             for item in self.grid.canvas.items.values()))
        ritual.close()

    def test_destroyed_tcl_canvas_commands_do_not_interrupt_cleanup(self):
        self.view.show('1', 1)
        self.grid.canvas.winfo_exists = Mock(side_effect=TclError('application destroyed'))
        self.view.clear()
        self.assertFalse(self.effects.particles.particles)
        self.assertFalse(self.effects.motion.pending)

    def test_off_and_failure_cleanup_do_not_emit_success_particles(self):
        self.effects.set_intensity(Intensity.OFF)
        self.view.level = Intensity.OFF
        self.view.show('1', 1)
        self.assertFalse(self.grid.scheduler.jobs)
        self.view.level = Intensity.FULL
        self.effects.set_intensity(Intensity.FULL)
        self.view.show('failure', 0)
        self.assertFalse(self.effects.particles.particles)
        self.assertEqual(self.view._stamp, 'CHECK OUTPUT')
        self.idle()

    def test_destroy_mid_countdown_collects_editor_view_ritual_and_managers(self):
        ritual = ConvertRitual(self.grid, self.view, clock=self.grid.clock)
        ritual.start()
        self.view.show('1', 1)
        receiver = ritual.receiver()
        stale = [callback for _delay, callback in self.grid.scheduler.jobs.values()]
        refs = [weakref.ref(value) for value in (self.editor, self.view, ritual, self.effects)]
        ritual.close()
        self.view.close()
        self.grid.close_effects()
        for callback in stale:
            callback()
        self.assertFalse(self.grid.scheduler.jobs)
        del ritual
        self.editor, self.view, self.effects = None, None, None
        gc.collect()
        self.assertTrue(all(ref() is None for ref in refs))
        receiver(True)
        # tearDown handles an already closed view/manager.
        self.view = SimpleNamespace(close=lambda: None)


class IntegrationTests(unittest.TestCase):
    def test_editor_off_cancels_phase_audio_and_motion_without_changing_document(self):
        scheduler, clock, view, backend = Scheduler(), Clock(), View(), Backend()
        ritual = ConvertRitual(scheduler, view, backend=backend, clock=clock)
        ritual.start()
        grid = headless_grid()
        document = EditorDocument()
        before = dict(document.__dict__)
        editor = Editor(ritual=ritual, ritual_view=SimpleNamespace(level=Intensity.MID, repaint=lambda: None),
                        table_grid=grid, settings=SimpleNamespace(update=Mock()), document=document,
                        _motion_intensity=SimpleNamespace(get=lambda: 'OFF'))
        DopagakiEditorWindow._intensity_changed(editor)
        self.assertFalse(scheduler.jobs)
        self.assertFalse(backend.playing)
        self.assertEqual(before, document.__dict__)
        ritual.close()
        grid.close_effects()

    def test_converter_request_starts_before_audio_and_preserves_arguments(self):
        calls = []
        app = SimpleNamespace(observe_conversion=lambda callback: calls.append(('observe', callback)))
        editor = DopagakiEditorWindow.__new__(DopagakiEditorWindow)
        editor.master = app
        editor.table_grid = SimpleNamespace(effects=SimpleNamespace(motion=SimpleNamespace(intensity=Intensity.MID)))
        editor._normal_convert = lambda path, **kwargs: calls.append(('converter', path, kwargs)) or True
        editor.ritual = Mock(start=Mock(side_effect=lambda *_: calls.append(('ritual',))), receiver=Mock(return_value=object()))
        self.assertTrue(editor._convert_with_ritual('saved snapshot.tsv'))
        self.assertEqual(calls[0], ('converter', 'saved snapshot.tsv', {'send_ftp': False}))
        self.assertEqual([call[0] for call in calls], ['converter', 'ritual', 'observe'])
        editor.ritual.reset_mock()
        calls.clear()
        self.assertTrue(editor._convert_with_ritual('saved snapshot.tsv', send_ftp=True))
        self.assertEqual(calls, [('converter', 'saved snapshot.tsv', {'send_ftp': True})])
        editor.ritual.start.assert_not_called()
        editor._normal_convert = Mock(return_value=False)
        self.assertFalse(editor._convert_with_ritual('cancelled.tsv'))
        editor.ritual.start.assert_not_called()

    def test_result_observer_is_one_shot_and_runs_before_existing_result_dialog(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source.tsv'
            source.write_text('1\ta\n')
            values = (str(source), directory, 'result', 'nxtas', False, False, False)
            app = DopagakiApp.__new__(DopagakiApp)
            app.language, app.words, app.base_dir = 'en', TEXT['en'], Path(directory)
            app._events, app._last_successful_output = SimpleQueue(), None
            app.convert_btn = SimpleNamespace(config=Mock())
            app.log, app.after = Mock(), Mock()
            callback, dialogs = Mock(), []
            app.observe_conversion(callback)

            def execute(argv, **_kwargs):
                self.assertEqual(argv, build_commands(*values, base_dir=Path(directory))[0])
                Path(argv[-1]).write_text('output fixture')
                return subprocess.CompletedProcess(argv, 0, '', '')

            def dialog(*_args):
                callback.assert_called_once()
                dialogs.append('success')

            with patch('python_to_exe.converter_gui.subprocess.run', side_effect=execute), \
                 patch('python_to_exe.converter_gui.messagebox.showinfo', side_effect=dialog):
                app.convert(values, ())
                app._drain_events()
            self.assertEqual(dialogs, ['success'])
            self.assertIs(callback.call_args.args[0], True)
            self.assertEqual(app._last_successful_output, Path(directory)/'result.txt')
            self.assertIsNone(app._ritual_result_callback)
            app._conversion_result_received(False, 'later unrelated result')
            callback.assert_called_once()


if __name__ == '__main__':
    unittest.main()
