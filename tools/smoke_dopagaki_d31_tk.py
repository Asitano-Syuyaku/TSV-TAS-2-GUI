"""Opt-in D3.1 native audio checks: short representative cases, one full run.

Uses existing local WAV and Windows PowerShell only. --production adds ONE
29.506s production timeline. No installs, media generation or user settings
writes. Requires WSLg/Windows audio. Process verification cannot certify hearing.
"""

import argparse
import base64
import gc
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch
import weakref

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_logic import build_commands
from python_to_exe.dopagaki_app import DopagakiApp
from python_to_exe.editor.dopagaki.audio import AudioConfig, create_audio_backend
from python_to_exe.editor.dopagaki.ritual import RitualTimeline, RitualState
from python_to_exe.editor.dopagaki.ui import DopagakiEditorWindow


def query(script):
    # Get-Process with an absent PID is an expected empty result, not an audit
    # failure. Force exit 0 for that query; handle PowerShell's locale stderr.
    script = "$ProgressPreference='SilentlyContinue'; " + script
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                            capture_output=True, timeout=10)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    return result.stdout.decode('utf-8-sig').strip()


def windows_pid(process):
    command = process.args[-1]  # Fixed encoded SoundPlayer command, safe base64.
    data = query("Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | "
                 f"Where-Object {{ $_.CommandLine -and $_.CommandLine.Contains('{command}') }} | "
                 'Select-Object -ExpandProperty ProcessId')
    pids = [int(line) for line in data.splitlines() if line.strip()]
    assert len(pids) == 1, f'expected one owned SoundPlayer, found {pids}'
    return pids[0]


def assert_stopped(process, pid):
    assert process.returncode is not None, 'WSL child was not reaped'
    assert not query(f'$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; '
                     'if ($null -ne $p) { $p.Id }; exit 0'), f'Windows player {pid} remained'


def run(folder, *, production=False, standalone=True):
    records = []

    def launched(backend, case):
        process = backend.process
        assert process is not None and backend.poll(), backend.last_error
        pid = windows_pid(process)
        record = dict(case=case, backend=backend.name, linux_pid=process.pid, windows_pid=pid,
                      launched_at=backend.launched_at)
        records.append(record)
        print(json.dumps(record), flush=True)
        return process, pid, record

    def stopped(process, pid, record):
        record['stop_observed_at'] = time.monotonic()
        assert_stopped(process, pid)
        record.update(observed_lifetime_seconds=record['stop_observed_at']-record['launched_at'],
                      reaped_returncode=process.returncode, windows_process_remaining=False)
        print(json.dumps(record), flush=True)

    if standalone:
        backend = create_audio_backend(AudioConfig())
        try:
            assert backend.play(AudioConfig().media_path), backend.last_error
            process, pid, record = launched(backend, 'A standalone')
            time.sleep(2)  # The only short standalone survival check.
            assert backend.poll(), backend.last_error
            assert backend.stop()
            stopped(process, pid, record)
        finally:
            backend.close()

    source = folder/'D31 日本語.tsv'
    source.write_text('1\tls(0)\trs(90)\ta\n2\tls(90)\trs(180)\tb\n' * 10)
    settings = AppSettings(folder/'settings.json')
    settings.update(output_format='nxtas')
    app = DopagakiApp('en', settings=settings)
    app.withdraw()
    errors, refs, phases = [], [], []
    app.report_callback_exception = lambda kind, value, _trace: errors.append(f'{kind.__name__}: {value}')

    def pump():
        app.update()
        assert not errors, errors

    def wait(condition, seconds=5):
        deadline = time.monotonic()+seconds
        while not condition():
            pump()
            assert time.monotonic() < deadline, 'representative check timed out'
            time.sleep(.010)

    def editor_for(language):
        editor = DopagakiEditorWindow(app, language=language, initial_path=source,
                                      on_saved=app._editor_saved, on_convert=app._convert_editor_file,
                                      can_convert=lambda: not app._busy())
        editor.show_table()
        pump()
        return editor

    def close_editor(editor):
        refs.extend(weakref.ref(value) for value in (editor, editor.ritual, editor.ritual_view,
                                                   editor.table_grid.effects))
        editor.destroy()
        pump()

    try:
        with patch('python_to_exe.converter_gui.messagebox.showinfo'), \
             patch('python_to_exe.converter_gui.messagebox.showerror'):
            editor = editor_for('ja')
            grid = editor.table_grid
            grid.jump_to_row(0, 3)
            grid.begin_edit()
            grid._editor.delete(0, 'end')
            grid._editor.insert(0, 'x')
            grid._editor.focus_force()
            pump()
            editor.ritual.timeline = RitualTimeline(drop=1.2, countdown_step=.2,
                                                    build_events=((.12, 'build'), (.3, 'tension')))
            grid._editor.event_generate('<F5>')
            assert grid._editor is None and not editor.document.modified
            assert editor.document.text == source.read_text()
            process, pid, record = launched(editor.ritual.backend, 'B F5 short cancel')
            editor.ritual.cancel()
            stopped(process, pid, record)
            assert not editor.ritual.pending
            # The actual edit commit has ordinary D1 feedback. Cancelling F5
            # intentionally leaves that independent pulse to finish naturally.
            wait(lambda: not grid.effects.motion.pending)
            wait(lambda: not app._conversion_running)
            assert editor.ritual.state == RitualState.CANCELLED

            editor.ritual.timeline = RitualTimeline()
            assert editor.save_and_convert()
            first, first_pid, first_record = launched(editor.ritual.backend, 'D first F5')
            wait(lambda: not app._conversion_running)
            assert editor.save_and_convert()
            stopped(first, first_pid, first_record)
            second, second_pid, second_record = launched(editor.ritual.backend, 'D second F5 / E close')
            assert second.poll() is None and first.returncode is not None
            close_editor(editor)
            stopped(second, second_pid, second_record)
            del editor, grid
            wait(lambda: not app._conversion_running)

            editor = editor_for('en')
            editor._motion_intensity.set('OFF')
            editor._intensity_changed()
            assert editor.save_and_convert()
            assert not editor.ritual.audio_playing and editor.ritual.backend.process is None
            assert not editor.ritual.pending and not editor.table_grid.effects.motion.pending
            wait(lambda: not app._conversion_running)

            output = app._last_successful_output.read_bytes()
            reference = build_commands(str(source), str(folder), 'reference', 'nxtas', False, False, False,
                                       base_dir=app.base_dir)[0]
            subprocess.run(reference, cwd=app.base_dir, capture_output=True, check=True)
            assert output == (folder/'reference.txt').read_bytes()

            if production:
                editor._motion_intensity.set('FULL')
                editor._intensity_changed()
                ritual = editor.ritual
                reference = weakref.ref(ritual)
                original_show = editor.ritual_view.show
                done = tk.BooleanVar(app, value=False)

                def recorded(event, progress, **options):
                    current = reference()
                    phases.append(dict(event=event, elapsed=time.monotonic()-current._started_at))
                    original_show(event, progress, **options)
                    if event == 'settle':
                        done.set(True)

                editor.ritual_view.show = recorded
                document = editor.document.text, editor.document.modified
                selection = editor.table_grid.selection.anchor, editor.table_grid.selection.active
                hype = editor.table_grid.effects.hype._value, editor.table_grid.effects.hype._at
                assert editor.save_and_convert()
                process, pid, record = launched(ritual.backend, 'C production')
                record['ritual_started_at'] = ritual._started_at
                record['launch_after_ritual_ms'] = (record['launched_at']-ritual._started_at)*1000
                wait(lambda: not app._conversion_running)
                assert ritual.state == RitualState.SUCCESS_READY
                print(json.dumps(dict(production='started', windows_pid=pid, drop=21.506, tail=29.506)), flush=True)
                watchdog = app.after(35000, lambda: done.set(True))
                app.wait_variable(done)
                app.after_cancel(watchdog)
                assert not errors, errors
                names = [phase['event'] for phase in phases]
                assert all(names.count(event) == 1 for event in ('3', '2', '1', 'drop', 'success', 'settle')), names
                assert ritual.backend.process is None and not ritual.pending
                assert not editor.table_grid.effects.motion.pending
                assert not editor.table_grid.effects.particles.particles
                assert document == (editor.document.text, editor.document.modified)
                assert selection == (editor.table_grid.selection.anchor, editor.table_grid.selection.active)
                assert hype == (editor.table_grid.effects.hype._value, editor.table_grid.effects.hype._at)
                stopped(process, pid, record)
                editor.ritual_view.show = original_show
                del original_show, recorded, ritual, reference, done
            close_editor(editor)
            del editor
            gc.collect()
            assert all(ref() is None for ref in refs), [type(ref()).__name__ for ref in refs if ref() is not None]
    finally:
        app.destroy()

    report = dict(audio_launches=len(records), players=records, production_runs=int(production), phases=phases,
                  tk_sessions=1, editor_closes=2, jp_en=True, simultaneous_players_max=1,
                  weakrefs_collected=True, converter_output_equivalent=True, errors=errors,
                  sync_offset_ms=0, auditory_calibration='pending user verification')
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', action='store_true')
    parser.add_argument('--skip-standalone', action='store_true', help='do not repeat an already verified case A')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='dopagaki-d31-tk-') as directory:
        report = run(Path(directory), production=args.production, standalone=not args.skip_standalone)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2)+'\n')
