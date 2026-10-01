"""Opt-in real Tk D2 representative cap/lifecycle checks and profiling.

Uses the existing clock injection to simulate long idle periods without
waiting minutes. Every particle item, widget and cancellation is real Tk.
Regular interaction latency uses the separate unmodified monotonic clock.
High repetition belongs in the deterministic headless suite, not this driver.
"""

import gc
import argparse
import json
from pathlib import Path
import random
import statistics
import sys
import tempfile
import time
import tracemalloc
from unittest.mock import patch
import weakref

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python_to_exe.app_settings import AppSettings
from python_to_exe.dopagaki_app import DopagakiApp
from python_to_exe.editor.dopagaki.effects import CellEffects
from python_to_exe.editor.dopagaki.hype import Hype
from python_to_exe.editor.dopagaki.motion import Intensity
from python_to_exe.editor.dopagaki.particles import CAPS, Particle
from python_to_exe.editor.dopagaki.ui import DopagakiEditorWindow
from python_to_exe.editor.dopagaki import ui


class ManualClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def rss_kib():
    path = Path("/proc/self/status")
    if not path.exists():
        return None
    return int(next(line for line in path.read_text().splitlines() if line.startswith("VmRSS:")).split()[1])


def snapshot(app):
    gc.collect()
    return dict(objects=len(gc.get_objects()),
                particles=sum(isinstance(obj, Particle) for obj in gc.get_objects()),
                rss_kib=rss_kib(), images=len(app.tk.call("image", "names")),
                commands=len(app.tk.call("info", "commands")))


def motion_jobs(app):
    return [job for job in app.tk.call("after", "info")
            if str(app.tk.call("after", "info", job)[0]).endswith("tick")]


def profile(folder, capture=None):
    source = folder / "profile 日本語.tsv"
    source.write_text("1\tls(0)\trs(90)\ta\n2\tls(90)\trs(180)\tb\n" * 60)
    clock = ManualClock()
    app = DopagakiApp("en", settings=AppSettings(folder / "profile-settings.json"))
    app.withdraw()
    errors = []
    app.report_callback_exception = lambda kind, value, _trace: errors.append(f"{kind.__name__}: {value}")

    def new_editor(language="en"):
        with patch.object(ui, "CellEffects", lambda scheduler, canvas:
                          CellEffects(scheduler, canvas, clock=clock)):
            editor = DopagakiEditorWindow(app, language=language, initial_path=source)
        editor.show_table()
        app.update()
        assert not errors, errors
        return editor

    def step(editor, seconds):
        clock.now += seconds
        controller = editor.table_grid.effects.motion
        if controller.pending:
            # Consume the real Tcl timer before invoking its elapsed-time tick.
            # Leaving it scheduled would produce an orphan synthetic callback.
            editor.table_grid.after_cancel(controller._job)
            started = time.perf_counter()
            controller._tick(controller._generation)
            elapsed = (time.perf_counter() - started) * 1000
        else:
            elapsed = 0.0
        assert len(motion_jobs(app)) <= 1
        return elapsed

    def idle(editor):
        step(editor, 60)
        app.update_idletasks()
        effects = editor.table_grid.effects
        assert not effects.motion.pending and not effects.particles.particles
        assert not motion_jobs(app)
        for surface in effects.particles.surfaces.values():
            assert not surface.canvas().find_withtag("dopagaki_particle")

    def seed(effects, value):
        effects.motion.clear()
        effects.hype.close()
        effects.hype = Hype(clock)
        effects.hype._value = value  # Benchmark-only heat, no document mutation.

    def close_and_collect(editor):
        effects = editor.table_grid.effects
        references = [weakref.ref(value) for value in
                      (editor, editor.table_grid, effects, effects.hype, effects.particles, editor.hype_meter)]
        editor.destroy()
        assert not effects.motion.pending
        del effects
        return references

    try:
        editor = new_editor()
        deadline = time.monotonic() + 10
        while editor._positions is None or editor._position_worker_active:
            app.update()
            if time.monotonic() >= deadline:
                raise AssertionError("Frame analysis did not finish")
            time.sleep(.005)
        effects = editor.table_grid.effects
        pool = effects.particles
        pool.rng = random.Random(24)
        original = editor.document.text
        history = tuple(editor.tk.call(editor.text._w, "edit", action) for action in ("canundo", "canredo"))
        selected = editor.table_grid.selection.bounds
        idle(editor)
        before = snapshot(app)
        results = [dict(case="idle", callbacks=0, particles=0, objects=before["objects"], rss_kib=before["rss_kib"])]
        effects.set_intensity(Intensity.OFF)
        effects.interaction("palette", origin=(350, 200))
        assert not effects.motion.pending and not pool.particles
        results.append(dict(case="OFF", callbacks=0, particles=0))
        for level in (Intensity.LOW, Intensity.MID, Intensity.FULL):
            effects.set_intensity(level)
            app.update()
            for heat in (0.0, 0.5, 1.0):
                for at_cap in (False, True):
                    seed(effects, heat)
                    count = CAPS[level.value] if at_cap else (3 if level == Intensity.LOW else 7 if level == Intensity.MID else 14)
                    pool.spawn("grid", (350, 200), count, level, heat, clock())
                    effects._refresh_juice(clock())
                    peak = len(pool.particles)
                    items = len(editor.table_grid.canvas.find_all())
                    all_items = sum(len(surface.canvas().find_all()) for surface in pool.surfaces.values())
                    objects_active = len(gc.get_objects())
                    refs = [weakref.ref(value) for value in pool.particles]
                    # Flush real Canvas paints as well as measuring Tcl tick
                    # work. idletasks does not dispatch the scheduled timer.
                    app.update_idletasks()
                    samples, paints, totals = [], [], []
                    while effects.motion.pending:
                        tick = step(editor, .016)
                        started = time.perf_counter()
                        app.update_idletasks()
                        paint = (time.perf_counter() - started) * 1000
                        samples.append(tick)
                        paints.append(paint)
                        totals.append(tick + paint)
                    gc.collect()
                    assert all(reference() is None for reference in refs)
                    assert not pool.particles and not motion_jobs(app)
                    timings = {}
                    for name, values in (("tick", samples), ("paint", paints), ("tick_and_paint", totals)):
                        ordered = sorted(values)
                        timings.update({f"{name}_ms_median": round(statistics.median(values), 3),
                                        f"{name}_ms_p95": round(ordered[int(len(ordered) * .95)], 3),
                                        f"{name}_ms_max": round(max(values), 3)})
                    del samples, paints, totals, values, ordered, refs
                    gc.collect()
                    result = dict(case=f"{level.value}:H={heat}:{'cap' if at_cap else 'burst'}",
                                  **timings, particles_peak=peak, grid_items_peak=items,
                                  canvas_items_peak=all_items, objects_active=objects_active,
                                  objects_after=len(gc.get_objects()),
                                  rss_kib=rss_kib(), idle_callbacks=0)
                    results.append(result)
                    print(json.dumps(result), flush=True)
        # Expensive allocation tracing is separate from tick/latency profiling.
        tracemalloc.start(5)
        traced_before = tracemalloc.get_traced_memory()[0]
        effects.set_intensity(Intensity.FULL)
        app.update()
        for _ in range(3):
            seed(effects, 0)
            for _ in range(17):
                effects.interaction("palette", origin=(350, 200))
            assert effects.hype.value() == 1
            idle(editor)
            assert effects.hype.value() == 0
            effects.interaction("palette", origin=(350, 200))
            assert effects.hype.value() == .06
            idle(editor)
        for _ in range(3):
            seed(effects, 1)
            pool.spawn("grid", (350, 200), CAPS["FULL"] + 1, Intensity.FULL, 1, clock())
            effects._refresh_juice(clock())
            assert len(pool.particles) == 180
            assert len(editor.table_grid.canvas.find_withtag("dopagaki_particle")) == 180
            app.update_idletasks()
            idle(editor)
        for index in range(8):
            effects.interaction("palette", origin=(350, 200))
            level = tuple(Intensity)[index % 4]
            editor._motion_intensity.set(level.value)
            editor._intensity_changed()
            assert not pool.particles and not motion_jobs(app)
        assert editor.document.text == original and not editor.document.modified
        assert editor.table_grid.selection.bounds == selected
        assert tuple(editor.tk.call(editor.text._w, "edit", action) for action in ("canundo", "canredo")) == history
        assert "hype" not in (folder / "profile-settings.json").read_text().lower()
        idle(editor)
        gc.collect()
        traced_after, traced_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        after = snapshot(app)
        assert after["particles"] == 0
        assert after["commands"] == before["commands"]
        assert after["images"] == before["images"]
        references = close_and_collect(editor)
        del editor, effects, pool
        app.update()
        gc.collect()
        assert all(reference() is None for reference in references)
        lifecycle_before = snapshot(app)
        for mid_particle in (False, True):
            for index in range(3):
                editor = new_editor("ja" if index % 2 == 0 else "en")
                effects = editor.table_grid.effects
                effects.set_intensity(Intensity.FULL)
                editor.table_grid.begin_edit()
                if mid_particle:
                    for _ in range(17):
                        effects.interaction("palette", origin=(350, 200))
                    assert effects.particles.particles and effects.motion.pending
                else:
                    idle(editor)
                references = close_and_collect(editor)
                del editor, effects
                app.update()
                gc.collect()
                assert all(reference() is None for reference in references)
                assert not motion_jobs(app)
            print(json.dumps(dict(editor_cycles=3, mid_particle=mid_particle)), flush=True)
        lifecycle_after = snapshot(app)
        assert lifecycle_after["images"] == lifecycle_before["images"]
        assert lifecycle_after["commands"] == lifecycle_before["commands"]
        assert lifecycle_after["particles"] == 0
        assert not errors, errors
        report = dict(cases=results, lifecycle=dict(hype_cycles=3, cap_cycles=3, intensity_switches=8,
                                                  editor_cycles=3, mid_particle_destroy=3),
                      before=before, after=after, lifecycle_before=lifecycle_before,
                      lifecycle_after=lifecycle_after, traced_before=traced_before,
                      traced_after=traced_after, traced_peak=traced_peak,
                      callback_cap=1, idle_callbacks=0, weakrefs_collected=True)
        print(json.dumps(report), flush=True)
        return report
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        app.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save the measured report as JSON")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="dopagaki-d2-profile-") as directory:
        result = profile(Path(directory))
    if arguments.output is not None:
        arguments.output.write_text(json.dumps(result, indent=2) + "\n")
