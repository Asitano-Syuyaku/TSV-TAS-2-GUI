"""Opt-in representative D3 Tk check; fake time by default, temporary files only.

--realtime runs ONE full 21.506s visual/audio timeline. Missing ffplay falls
back normally. No download/install or media rewrite is performed. Optional
capture(editor, level, phase) can be supplied by a local screenshot probe.
"""

import argparse
import gc
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import weakref

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_logic import build_commands
from python_to_exe.dopagaki_app import DopagakiApp
from python_to_exe.editor.dopagaki import ui
from python_to_exe.editor.dopagaki.effects import CellEffects
from python_to_exe.editor.dopagaki.motion import Intensity
from python_to_exe.editor.dopagaki.ritual import ConvertRitual, RitualState, DROP_SECONDS
from python_to_exe.editor.dopagaki.ritual_view import STAMP_TAG, STATIC_TAG
from python_to_exe.editor.dopagaki.ui import DopagakiEditorWindow
from tools.smoke_dopagaki_d1_tk import descendants


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def snapshot(app):
    gc.collect()
    rss = None
    if Path('/proc/self/status').exists():
        rss = int(next(line for line in Path('/proc/self/status').read_text().splitlines()
                       if line.startswith('VmRSS:')).split()[1])
    return dict(objects=len(gc.get_objects()), commands=len(app.tk.call('info', 'commands')),
                images=len(app.tk.call('image', 'names')), rss_kib=rss)


def run(folder, capture=None, *, realtime=False, close_cycles=3):
    source = folder / 'D3 日本語.tsv'
    source.write_text('1\tls(0)\trs(90)\ta\n2\tls(90)\trs(180)\tb\n' * 40)
    settings = AppSettings(folder / 'settings.json')
    settings.update(output_format='nxtas')
    app = DopagakiApp('en', settings=settings)
    app.withdraw()
    errors, reports, refs = [], [], []
    ticks, phases, cell_latencies = [], [], []
    app.report_callback_exception = lambda kind, value, _trace: errors.append(f'{kind.__name__}: {value}')

    def pump():
        app.update()
        assert not errors, errors

    def wait(condition, seconds=5):
        deadline = time.monotonic() + seconds
        while not condition():
            pump()
            assert time.monotonic() < deadline, 'representative check timed out'
            time.sleep(.003)

    def history(editor):
        return tuple(editor.tk.call(editor.text._w, 'edit', action) for action in ('canundo', 'canredo'))

    def check_jobs(editor):
        effects = editor.table_grid.effects
        jobs = app.tk.call('after', 'info')
        for job in (effects.motion._job, editor.ritual._job):
            if job is not None:
                assert job in jobs
        assert sum(str(app.tk.call('after', 'info', job)[0]).endswith('tick') for job in jobs) <= 1
        assert sum(str(app.tk.call('after', 'info', job)[0]).endswith('wake') for job in jobs) <= 1
        assert len(effects.particles.particles) <= {'OFF': 0, 'LOW': 30, 'MID': 90, 'FULL': 180}[effects.motion.intensity.value]
        if effects.motion.effect is not None:
            assert len(effects.motion.effect.tracks) <= 8

    with patch('python_to_exe.converter_gui.messagebox.showinfo'), \
         patch('python_to_exe.converter_gui.messagebox.showerror'):
        for language in ('en', 'ja'):
            clock = Clock()
            with patch.object(ui, 'CellEffects', lambda scheduler, canvas: CellEffects(scheduler, canvas, clock=clock)), \
                 patch.object(ui, 'ConvertRitual', lambda scheduler, view, **kw: ConvertRitual(scheduler, view, clock=clock, **kw)):
                editor = DopagakiEditorWindow(app, language=language, initial_path=source,
                                              on_saved=app._editor_saved, on_convert=app._convert_editor_file,
                                              can_convert=lambda: not app._busy())
            editor.show_table()
            wait(lambda: editor._positions is not None)
            grid, effects = editor.table_grid, editor.table_grid.effects
            editor.lift()
            grid.jump_to_row(0, 3)
            grid.begin_edit()
            grid._editor.delete(0, 'end')
            grid._editor.insert(0, 'x')
            grid._editor.focus_force()
            pump()
            grid._editor.event_generate('<F5>')
            assert editor.ritual._started_at is not None
            assert grid._editor is None and not editor.document.modified
            assert source.read_text() == editor.document.text
            wait(lambda: not app._conversion_running)
            assert editor.ritual.state == RitualState.SUCCESS_READY
            assert not grid.canvas.find_withtag(STAMP_TAG)
            output = app._last_successful_output.read_bytes()
            reference = build_commands(str(source), str(folder), 'reference', 'nxtas', False, False, False,
                                       base_dir=app.base_dir)[0]
            subprocess.run(reference, cwd=app.base_dir, capture_output=True, check=True)
            assert output == (folder / 'reference.txt').read_bytes()
            saved_snapshot = editor.document.text

            def tick():
                if effects.motion.pending:
                    grid.after_cancel(effects.motion._job)
                    started = time.perf_counter()
                    effects.motion._tick(effects.motion._generation)
                    app.update_idletasks()
                    ticks.append((time.perf_counter() - started) * 1000)
                check_jobs(editor)

            def step(elapsed):
                clock.now = editor.ritual._started_at + elapsed
                if editor.ritual.pending:
                    editor.after_cancel(editor.ritual._job)
                    started = time.perf_counter()
                    editor.ritual._wake(editor.ritual.generation, editor.ritual._ticket)
                    phases.append((time.perf_counter() - started) * 1000)
                tick()
                app.update_idletasks()

            # Native F5 result is already available, but its visual reward waits.
            step(DROP_SECONDS)
            assert editor.ritual.state == RitualState.SUCCESS_FINALE
            assert editor.ritual_view._stamp == "LET'S GO!!\nCONVERTED"
            if capture:
                capture(editor, 'MID', 'early-success')

            # Further runs use the existing request signature with a controlled
            # result; no additional converter processes are required for tuning.
            editor._normal_convert = lambda path, send_ftp=False: True
            for level in ('LOW', 'MID', 'FULL'):
                editor._motion_intensity.set(level)
                editor._intensity_changed()
                assert editor.save_and_convert()
                origin = editor.ritual._started_at
                step(6)
                if level == 'MID':
                    for index in range(30):
                        grid.canvas.focus_force()
                        started = time.perf_counter()
                        grid.canvas.event_generate('<Right>' if index % 2 == 0 else '<Left>')
                        pump()
                        cell_latencies.append((time.perf_counter() - started) * 1000)
                    grid.jump_to_row(0, 3)
                    grid.begin_edit()
                    entry = grid._editor
                    entry.delete(0, 'end')
                    entry.insert(0, 'b')
                    entry.focus_force()
                    pump()
                    entry.event_generate('<Tab>')
                    pump()
                    assert editor.document.modified
                    buttons = [widget for widget in descendants(editor._palette_pages[0][0])
                               if widget.winfo_class() == 'Button']
                    candidate = next(button for button in buttons if button.cget('text') == 'ls(angle)')
                    grid.jump_to_row(1, 1)
                    candidate.invoke()
                    entry = grid._editor
                    pending = entry.get(), entry.index('sel.first'), entry.index('sel.last'), entry.place_info()
                    editor._show_palette_page(1)
                    editor._show_palette_page(0)
                    assert pending == (entry.get(), entry.index('sel.first'), entry.index('sel.last'), entry.place_info())
                    grid.cancel_edit()
                    assert editor.undo()
                    assert editor.redo()
                    assert editor.show_raw()
                    step(12)
                    assert editor.ritual._job is not None and editor.ritual_view._banner_text
                    assert editor.show_table()
                    grid.canvas.yview_moveto(.15)
                    grid._draw_visible()
                    editor.geometry('1000x650')
                    pump()
                    editor.geometry('1200x700')
                    pump()
                    grid.selection.move_to(2, 3, extend=True)
                    grid._draw_visible()
                step(18.506)
                step(19.506)
                grid.jump_to_row(10, 3)
                grid.begin_edit()
                entry = grid._editor
                entry.delete(0, 'end')
                entry.insert(0, 'y')
                entry.select_range(0, 1)
                entry.focus_force()
                pump()
                caret_state = (entry.get(), entry.index('sel.first'), entry.index('sel.last'),
                               entry.winfo_x(), entry.winfo_y(), entry.winfo_width(), entry.winfo_height())
                focus_name = str(app.focus_get())
                step(20.506)
                assert editor.ritual_view._stamp == '1'
                assert str(app.focus_get()) == focus_name
                assert caret_state == (entry.get(), entry.index('sel.first'), entry.index('sel.last'),
                                       entry.winfo_x(), entry.winfo_y(), entry.winfo_width(), entry.winfo_height())
                if capture:
                    capture(editor, level, 'countdown-1')
                before = editor.document.text, editor.document.modified, history(editor), grid.selection.anchor, grid.selection.active
                step(DROP_SECONDS)
                assert editor.ritual.state == RitualState.WAITING_FOR_CONVERTER
                assert editor.ritual_view._stamp == "LET'S GO!!"
                assert editor.ritual_view._banner_text == 'F5 · CHARGING...'
                clock.now += .2
                editor.ritual.receiver()(True)
                assert editor.ritual_view._stamp == 'CONVERTED'
                assert grid._editor is entry and entry.get() == 'y'
                assert before == (editor.document.text, editor.document.modified, history(editor), grid.selection.anchor, grid.selection.active)
                for index in range(45):
                    clock.now += .016
                    tick()
                assert not effects.motion.pending and not effects.particles.particles
                assert not grid.canvas.find_withtag(STAMP_TAG)
                step(DROP_SECONDS + 8)
                assert not editor.ritual.pending
                assert not grid.canvas.find_withtag(STATIC_TAG)
                assert editor.ritual.backend.process is None
                reports.append(dict(language=language, level=level, output_equivalent=True,
                                    converter_snapshot_survives_edit=saved_snapshot != editor.document.text if level != 'LOW' else True,
                                    idle_motion_callbacks=0, idle_ritual_callbacks=0,
                                    idle_particles=0, audio_backend_error=editor.ritual.backend.last_error))

            assert editor.save_and_convert()
            stale = editor.ritual.receiver()
            assert editor.save_and_convert()  # replace old scheduled run
            stale(True)
            assert editor.ritual.state == RitualState.PRELUDE
            editor.ritual.receiver()(False)
            assert editor.ritual.state == RitualState.FAILED
            assert not editor.ritual.pending
            app.update_idletasks()
            if capture:
                capture(editor, 'FULL', 'failure')
            editor.ritual.cancel()
            assert editor.save_and_convert()
            editor._motion_intensity.set('OFF')
            editor._intensity_changed()
            assert not editor.ritual.pending and not effects.motion.pending
            assert editor.save_and_convert()
            assert not editor.ritual.pending and not effects.motion.pending
            editor._motion_intensity.set('FULL')
            editor._intensity_changed()
            assert editor.save_and_convert()
            refs.extend(weakref.ref(value) for value in (editor, grid, effects, editor.ritual, editor.ritual_view, effects.hype, effects.particles))
            editor.destroy()
            pump()
            del editor, grid, effects, entry, buttons, candidate, pending
            gc.collect()
            assert all(ref() is None for ref in refs), [type(ref()).__name__ for ref in refs if ref() is not None]
            print(json.dumps(dict(language=language, representative_check='passed')), flush=True)

        warm = snapshot(app)
        for index in range(close_cycles):
            editor = DopagakiEditorWindow(app, language='en' if index % 2 else 'ja', initial_path=source)
            editor.show_table()
            pump()
            editor.ritual.start(Intensity.MID)
            refs.extend(weakref.ref(value) for value in (editor, editor.ritual, editor.ritual_view))
            editor.destroy()
            pump()
            del editor
        gc.collect()
        assert all(ref() is None for ref in refs)
        after = snapshot(app)
        assert after['commands'] == warm['commands'] and after['images'] == warm['images'], (warm, after)

        if realtime:
            editor = DopagakiEditorWindow(app, language='en', initial_path=source,
                                          on_convert=lambda path, send_ftp=False: True)
            editor.show_table()
            editor._motion_intensity.set('FULL')
            editor._intensity_changed()
            pump()
            editor.save_and_convert()
            editor.ritual.receiver()(True)
            print(json.dumps(dict(realtime='one full timeline started', drop=DROP_SECONDS,
                                  audio_playing=editor.ritual.audio_playing)), flush=True)
            wait(lambda: editor.ritual.state == RitualState.SUCCESS_FINALE, seconds=26)
            if capture:
                capture(editor, 'FULL', 'realtime-drop')
            wait(lambda: not editor.table_grid.effects.motion.pending)
            assert not editor.table_grid.effects.particles.particles
            editor.destroy()
            pump()

    app.destroy()
    result = dict(representative=reports, editor_closes=2 + close_cycles + int(realtime),
                  warm=warm, after=after, weakrefs_collected=True,
                  motion_tick_and_paint_median_ms=statistics.median(ticks),
                  motion_tick_and_paint_p95_ms=sorted(ticks)[int(len(ticks)*.95)],
                  phase_callback_median_ms=statistics.median(phases),
                  cell_latency_median_ms=statistics.median(cell_latencies),
                  full_realtime_runs=int(realtime), errors=errors)
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--realtime', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='dopagaki-d3-tk-') as directory:
        report = run(Path(directory), realtime=args.realtime)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
