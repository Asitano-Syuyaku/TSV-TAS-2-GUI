"""D2 deterministic heat/particle tests; no display or wall-clock assertions."""

import gc
import random
import unittest
import weakref
from types import SimpleNamespace
from unittest.mock import patch

from test_dopagaki import Canvas, Clock, Scheduler, headless_grid
from test_dopagaki_micro import Widget, frame_values
from test_table_grid import EntryStub
from python_to_exe.editor.document import EditorDocument
from python_to_exe.editor.debug_csv import StickFrame, StickState
from python_to_exe.editor.dopagaki.effects import CellEffects
from python_to_exe.editor.dopagaki.hype import Hype, GAINS, THRESHOLDS, curve
from python_to_exe.editor.dopagaki.motion import Intensity
from python_to_exe.editor.dopagaki.particles import CAPS, HARD_CEILING, KINDS, ParticleSystem, spawn_count
from python_to_exe.editor.dopagaki.ui import DopagakiEditorWindow
from python_to_exe.editor.dopagaki.widgets import DopagakiStickPreview
from python_to_exe.editor.tsv_syntax import CANDIDATES, CompletionState
from python_to_exe.editor.window import EditorWindow


class ParticleCanvas(Canvas):
    create_oval = create_polygon = Canvas.create_rectangle

    def __init__(self, width=800, height=500, background="#ffffff"):
        super().__init__()
        self.width, self.height = width, height
        self.background = background
        self.mapped = self.exists = True

    def cget(self, name):
        return self.background

    def winfo_exists(self):
        return self.exists

    def winfo_ismapped(self):
        return self.mapped

    def delete(self, tag):
        if tag == "all":
            self.items.clear()
        else:
            super().delete(tag)

    def tag_raise(self, tag):
        if isinstance(tag, str):
            return
        super().tag_raise(tag)


class Meter(ParticleCanvas):
    def __init__(self):
        super().__init__(400, 14, "#19233b")
        self.last = None

    def paint(self, value, level, reward=False):
        self.last = value, level, reward

    def set_level(self, level):
        self.mapped = level != Intensity.OFF


def enable(grid):
    grid.close_effects()
    grid.canvas = ParticleCanvas()
    grid.effects = CellEffects(grid, grid.canvas, clock=grid.clock)
    meter, border = Meter(), Widget()
    grid.effects.attach_juice(meter, border, left=grid.gutter_width, top=grid.header_height)
    grid.effects.particles.rng = random.Random(42)
    return meter, border


class HypeTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.hype = Hype(self.clock)

    def test_meaningful_gains_clamp_and_curve(self):
        for event, gain in GAINS.items():
            model = Hype(self.clock)
            value, _thresholds, admitted = model.add(event)
            self.assertAlmostEqual(value, gain)
            self.assertTrue(admitted)
        for _ in range(1000):
            self.hype.add("palette")
        self.assertEqual(self.hype.value(), 1.0)
        self.assertEqual(curve(0), 0.08)
        self.assertEqual(curve(1), 1.0)
        self.assertAlmostEqual(curve(.5), .08 + .92 * .5 ** 1.3)
        self.assertEqual(curve(-1), curve(0))
        self.assertEqual(curve(2), curve(1))

    def test_lazy_half_life_and_next_event_use_elapsed_time(self):
        for _ in range(30):
            self.hype.add("commit")
        self.clock.now += 5
        self.assertEqual(self.hype.value(), .5)
        self.clock.now += 5
        self.assertEqual(self.hype.value(), .25)
        self.assertAlmostEqual(self.hype.add("page")[0], .265)
        self.clock.now += 100
        self.assertEqual(self.hype.value(), 0)
        self.assertEqual(self.hype.add("palette")[0], .06)

    def test_autorepeat_cannot_instantly_fill_hype_or_reach_high_equilibrium(self):
        for _ in range(3000):
            self.hype.add("cell")
        self.assertEqual(self.hype.value(), .006)
        for _ in range(3000):
            self.clock.now += .020
            self.hype.add("cell")
        self.assertLess(self.hype.value(), .40)
        for _ in range(15):
            self.hype.add("palette")
        self.assertEqual(self.hype.value(), 1)

    def test_thresholds_latch_and_rearm_only_below_hysteresis_band(self):
        rewards = []
        for _ in range(20):
            rewards.extend(self.hype.add("palette")[1])
        self.assertEqual(rewards, list(THRESHOLDS))
        self.assertFalse(self.hype.add("palette")[1])
        # Cross 0.90 again without cooling beneath its 0.82 rearm boundary.
        self.clock.now += 1.0
        self.assertGreater(self.hype.value(), .82)
        rewards = self.hype.add("palette")[1]
        self.assertNotIn(.90, rewards)
        self.clock.now += 3.0
        self.assertLess(self.hype.value(), .82)
        rewards = []
        for _ in range(10):
            rewards.extend(self.hype.add("palette")[1])
        self.assertIn(.90, rewards)
        self.assertEqual(len(rewards), len(set(rewards)))

    def test_closed_model_releases_clock_and_has_no_new_events(self):
        self.hype.close()
        self.hype.close()
        self.assertEqual(self.hype.value(), 0)
        self.assertEqual(self.hype.add("commit"), (0, (), False))
        with self.assertRaises(ValueError):
            Hype(half_life=0)


class ParticleTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.canvas = ParticleCanvas()
        self.plot = ParticleCanvas(180, 126, "#19233b")
        self.pool = ParticleSystem(rng=random.Random(1))
        self.pool.register("grid", self.canvas, left=48, top=24, background="#ffffff", dark=False)
        self.pool.register("stick0", self.plot)

    def tearDown(self):
        self.pool.close()

    def test_spawn_counts_scale_by_heat_and_level_and_moves_are_sparse(self):
        for event in ("commit", "palette", "stick", "page", "jump", "operation"):
            counts = [spawn_count(event, level, 1) for level in (Intensity.LOW, Intensity.MID, Intensity.FULL)]
            self.assertEqual(counts, sorted(counts))
            for level in (Intensity.LOW, Intensity.MID, Intensity.FULL):
                self.assertLessEqual(spawn_count(event, level, 0), spawn_count(event, level, 1))
                self.assertEqual(spawn_count(event, Intensity.OFF, 1), 0)
        self.assertEqual(spawn_count("cell", Intensity.LOW, 1), 0)
        self.assertEqual(spawn_count("cell", Intensity.FULL, .5), 0)
        self.assertEqual(spawn_count("cell", Intensity.FULL, 1), 2)

    def test_hard_caps_global_across_surfaces_and_slots_are_small(self):
        for level in Intensity:
            self.pool.clear()
            self.pool.spawn("grid", (250, 200), 1000, level, 1, self.clock())
            self.pool.spawn("stick0", (90, 63), 1000, level, 1, self.clock())
            self.pool.render(self.clock())
            self.assertEqual(len(self.pool.particles), CAPS[level.value])
            self.assertLessEqual(len(self.pool.particles), HARD_CEILING)
            self.assertEqual(len(self.canvas.items) + len(self.plot.items), CAPS[level.value])
            if self.pool.particles:
                self.assertFalse(hasattr(self.pool.particles[0], "__dict__"))
                self.assertEqual({particle.kind for particle in self.pool.particles}, set(KINDS))

    def test_analytic_frame_skip_and_expiry_delete_all_items_and_records(self):
        self.pool.spawn("grid", (250, 200), 8, Intensity.FULL, 1, self.clock())
        self.pool.render(self.clock())
        particle = self.pool.particles[0]
        self.clock.now += .12
        self.pool.render(self.clock())
        self.assertAlmostEqual(particle.x, particle.origin_x + particle.vx * .12)
        self.assertAlmostEqual(particle.y, particle.origin_y + particle.vy * .12 + .5 * particle.gravity * .12 ** 2)
        references = [weakref.ref(value) for value in self.pool.particles]
        del particle
        self.clock.now += 100
        self.pool.render(self.clock())
        gc.collect()
        self.assertFalse(self.pool.particles)
        self.assertFalse(self.canvas.items)
        self.assertTrue(all(reference() is None for reference in references))

    def test_viewport_changes_cancel_only_that_surface(self):
        self.pool.spawn("grid", (250, 200), 4, Intensity.FULL, 1, self.clock())
        self.pool.spawn("stick0", (90, 63), 4, Intensity.FULL, 1, self.clock())
        self.pool.render(self.clock())
        self.canvas.origin_y = 24
        self.pool.render(self.clock())
        self.assertFalse(self.canvas.items)
        self.assertEqual(len(self.plot.items), 4)
        self.canvas.width -= 50
        self.pool.render(self.clock())
        self.plot.mapped = False
        self.pool.render(self.clock())
        self.assertFalse(self.pool.particles)
        self.assertFalse(self.plot.items)

    def test_plot_delete_all_recreates_only_particle_items_and_does_not_reset_births(self):
        self.pool.spawn("stick0", (90, 63), 10, Intensity.FULL, 1, self.clock())
        self.pool.render(self.clock())
        births = [particle.born_at for particle in self.pool.particles]
        self.pool.invalidate("stick0")
        self.plot.delete("all")
        self.pool.render(self.clock(), only="stick0")
        self.assertEqual(len(self.plot.items), 10)
        self.assertEqual([particle.born_at for particle in self.pool.particles], births)

    def test_four_surfaces_max_and_dead_canvas_collects(self):
        for name in ("stick1", "meter"):
            self.pool.register(name, self.canvas)
        with self.assertRaises(ValueError):
            self.pool.register("fifth", self.canvas)
        target = ParticleCanvas()
        self.pool.register("grid", target)
        self.pool.spawn("grid", (250, 200), 10, Intensity.FULL, 1, self.clock())
        reference = weakref.ref(target)
        del target
        gc.collect()
        self.assertIsNone(reference())
        self.pool.render(self.clock())
        self.assertFalse(self.pool.particles)


class D2IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.grid = headless_grid()
        self.meter, self.border = enable(self.grid)
        self.effects = self.grid.effects
        self.effects.set_intensity(Intensity.FULL)

    def tearDown(self):
        self.grid.close_effects()

    def idle(self):
        self.grid.clock.now += 10
        for _ in range(10):
            if not self.grid.scheduler.jobs:
                break
            self.grid.scheduler.run_next()
            self.grid.clock.now += 1
        self.assertFalse(self.grid.scheduler.jobs)
        self.assertIsNone(self.effects.motion.effect)
        self.assertFalse(self.effects.particles.particles)
        self.assertFalse(any(item.get("tags") == "dopagaki_particle" for item in self.grid.canvas.items.values()))

    def test_changed_commit_gains_once_and_noop_rejected_commit_do_not_gain(self):
        self.grid._editor = SimpleNamespace(get=lambda: "2", bell=lambda: None)
        self.grid.on_change = lambda *_: True
        self.assertTrue(self.grid._apply_editor_value())
        self.assertAlmostEqual(self.effects.hype.value(), GAINS["commit"])
        heat = self.effects.hype.value()
        self.assertTrue(self.grid._apply_editor_value())
        self.assertEqual(self.effects.hype.value(), heat)
        self.grid.on_change = lambda *_: False
        self.grid._editor.get = lambda: "3"
        self.assertFalse(self.grid._apply_editor_value())
        self.assertEqual(self.effects.hype.value(), heat)
        self.idle()

    def test_repeat_transfers_absolute_births_without_retaining_facades(self):
        self.effects.interaction("palette", origin=(250, 200))
        old_particles = list(self.effects.particles.particles)
        references = []
        for _ in range(100):
            references.append(weakref.ref(self.effects.effect_for("juice")))
            self.grid.clock.now += .001
            self.effects.interaction("palette", origin=(250, 200))
            self.assertEqual(len(self.grid.scheduler.jobs), 1)
            self.assertLessEqual(len(self.effects.particles.particles), CAPS["FULL"])
            self.assertLessEqual(len(self.effects.motion.effect.tracks), 8)
        self.assertTrue(all(particle.born_at == 50 for particle in old_particles))
        self.idle()
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))

    def test_off_and_intensity_changes_are_independent_of_heat_and_clean_particles(self):
        self.effects.interaction("palette", origin=(250, 200))
        heat = self.effects.hype.value()
        self.effects.set_intensity("OFF")
        self.effects.interaction("palette", origin=(250, 200))
        self.assertEqual(self.effects.hype.value(), heat)
        self.assertFalse(self.meter.mapped)
        self.assertFalse(self.effects.particles.particles)
        self.assertFalse(self.grid.scheduler.jobs)
        for level in (Intensity.LOW, Intensity.MID, Intensity.FULL):
            self.effects.set_intensity(level)
            self.assertTrue(self.meter.mapped)
            self.assertEqual(self.effects.motion.intensity.multiplier, level.multiplier)
            self.assertEqual(self.effects.hype.value(), heat)

    def test_animation_preserves_document_history_selection_and_exact_frame_strings(self):
        document = EditorDocument()
        document.set_text(self.grid.model.to_text())
        state = dict(document.__dict__), self.grid.model.to_text(), self.grid.selection.bounds
        display = frame_values(self.effects)
        text = "Start: 1f | Duration: 2f | End: 2f | Total: 3f"
        display.configure(text=text)
        for event in GAINS:
            self.effects.interaction(event, origin=(250, 200))
        self.idle()
        self.assertEqual((dict(document.__dict__), self.grid.model.to_text(), self.grid.selection.bounds), state)
        self.assertEqual(display.cget("text"), text)

    def test_palette_text_placeholder_icon_remain_exact_with_hype_and_particles(self):
        self.grid._completion, self.grid._popup = CompletionState(), None
        self.grid._editor = EntryStub(None)
        self.grid.selected = (0, 3)
        editor = DopagakiEditorWindow.__new__(DopagakiEditorWindow)
        editor.table_grid = self.grid
        editor.stick_preview = SimpleNamespace(pulse=lambda column:
                                               self.effects.interaction("stick", origin=(250, 200)))
        for candidate in CANDIDATES:
            self.grid._editor.delete(0, "end")
            self.grid._editor.selection_clear()
            button = Widget()
            button.tk = SimpleNamespace(call=lambda _command: self.grid.insert_candidate(candidate))
            with patch.object(EditorWindow, "_palette_button", return_value=button):
                editor._palette_button(None, candidate)
            button.cget("command")()
            self.assertEqual(self.grid._editor.get(), candidate.text)
            self.assertEqual(self.grid._editor.selected_range, candidate.select)
            self.assertEqual(button.cget("image"), "original-icon")
        self.idle()

    def test_idle_heat_above_zero_requires_no_callback(self):
        for _ in range(17):
            self.effects.interaction("palette", origin=(250, 200))
        self.grid.clock.now += 1
        self.grid.scheduler.run_next()
        self.assertGreater(self.effects.hype.value(), 0)
        self.assertFalse(self.grid.scheduler.jobs)
        self.grid.clock.now += 100
        self.assertEqual(self.effects.hype.value(), 0)
        self.assertFalse(self.grid.scheduler.jobs)

    def test_many_heat_cap_expiry_cycles_return_to_idle_without_retained_particles(self):
        original = self.grid.model.to_text(), self.grid.selection.bounds
        for _ in range(100):
            self.grid.clock.now += 60
            self.assertEqual(self.effects.hype.value(), 0)
            for _ in range(17):
                self.effects.interaction("palette", origin=(250, 200))
            self.assertEqual(self.effects.hype.value(), 1)
            self.effects.particles.spawn("grid", (250, 200), 1000,
                                         Intensity.FULL, 1, self.grid.clock())
            self.effects._refresh_juice(self.grid.clock())
            self.assertEqual(len(self.effects.particles.particles), CAPS["FULL"])
            self.assertEqual(len(self.grid.scheduler.jobs), 1)
            references = [weakref.ref(particle) for particle in self.effects.particles.particles]
            facade = weakref.ref(self.effects.effect_for("juice"))
            self.idle()
            self.assertTrue(all(reference() is None for reference in references))
            self.assertIsNone(facade())
        self.assertEqual((self.grid.model.to_text(), self.grid.selection.bounds), original)

    def test_many_intensity_switches_cancel_generation_and_restore_presentation(self):
        original = self.grid.model.to_text(), self.grid.selection.bounds
        for index in range(100):
            self.effects.interaction("palette", origin=(250, 200))
            stale = (next(iter(self.grid.scheduler.jobs.values()))[1]
                     if self.grid.scheduler.jobs else None)
            heat = self.effects.hype.value()
            self.effects.set_intensity(tuple(Intensity)[index % 4])
            if stale is not None:
                stale()
            self.assertEqual(self.effects.hype.value(), heat)
            self.assertFalse(self.grid.scheduler.jobs)
            self.assertFalse(self.effects.particles.particles)
            self.assertIsNone(self.effects.motion.effect)
        self.assertEqual((self.grid.model.to_text(), self.grid.selection.bounds), original)

    def test_successful_jump_only_gains_after_the_shared_path_succeeds(self):
        editor = DopagakiEditorWindow.__new__(DopagakiEditorWindow)
        editor.table_grid = self.grid
        with patch.object(EditorWindow, "go_to_frame", return_value=False):
            self.assertFalse(editor.go_to_frame())
        self.assertEqual(self.effects.hype.value(), 0)
        with patch.object(EditorWindow, "go_to_frame", return_value=True):
            self.assertTrue(editor.go_to_frame())
        self.assertAlmostEqual(self.effects.hype.value(), GAINS["jump"])
        self.idle()

    def test_paste_and_duplicate_wrap_shared_operations_and_noop_paste_does_not_gain(self):
        self.grid.on_transform = lambda *_: True
        original = self.grid.model.to_text()
        rows = self.grid.model.row_count
        self.assertTrue(self.grid.paste_text("1"))
        self.assertEqual(self.effects.hype.value(), 0)
        self.assertTrue(self.grid.paste_text("9"))
        self.assertAlmostEqual(self.effects.hype.value(), GAINS["operation"])
        self.assertTrue(self.grid.duplicate_row())
        self.assertAlmostEqual(self.effects.hype.value(), 2 * GAINS["operation"])
        self.assertEqual(self.grid.model.row_count, rows + 1)
        self.assertNotEqual(self.grid.model.to_text(), original)
        self.idle()

    def test_grid_redraw_does_not_delete_particles_or_use_item_hit_testing(self):
        self.grid._draw_visible()
        self.effects.interaction("palette", origin=(250, 200))
        particle_ids = {value.item for value in self.effects.particles.particles}
        self.grid._draw_visible()
        self.assertTrue(particle_ids.issubset(self.grid.canvas.items))
        # Hit-testing remains coordinate based, even over an effect item.
        event = SimpleNamespace(x=250, y=40)
        self.assertEqual(self.grid._hit_cell(event), (0, 1))
        self.idle()

    def test_stick_redraw_particles_and_rings_preserve_values_and_previous_three_frames(self):
        preview = DopagakiStickPreview.__new__(DopagakiStickPreview)
        preview._effects = weakref.ref(self.effects)
        preview.plots = [ParticleCanvas(180, 126), ParticleCanvas(180, 126)]
        preview.values = [Widget(), Widget()]
        preview.winfo_ismapped = lambda: True
        preview.frame = 3
        state = StickState(16384, 32767, .75, 90)
        preview.samples = tuple(StickFrame(frame, state, state) for frame in (3, 2, 1, 0))
        for column, canvas in enumerate(preview.plots):
            self.effects.particles.register(f"stick{column}", canvas)
            preview._draw(column)
        original = preview.frame, preview.samples, [dict(widget.options) for widget in preview.values]
        for index in range(300):
            column = index % 2
            preview.pulse(column)
            preview._draw(column)
            samples = [item for item in preview.plots[column].items.values()
                       if isinstance(item.get("tags"), tuple)]
            self.assertEqual(len(samples), 4)
            self.assertLessEqual(len(self.effects.particles.particles), CAPS["FULL"])
        self.assertEqual((preview.frame, preview.samples,
                          [dict(widget.options) for widget in preview.values]), original)
        self.idle()

    def test_micro_visibility_and_timing_are_preserved_at_zero_and_high_hype(self):
        for level in (Intensity.LOW, Intensity.MID, Intensity.FULL):
            self.effects.set_intensity(level)
            self.assertGreaterEqual(self.effects.micro_strength(), level.multiplier)
            self.effects.hype._value = 1
            self.assertLessEqual(self.effects.micro_strength(), 1)
            self.assertGreaterEqual(self.effects.micro_strength(), level.multiplier)
            self.effects.pulse_widget("palette", self.border, "palette")
            self.assertEqual(self.effects.effect_for("palette").duration,
                             {Intensity.LOW: .120, Intensity.MID: .160, Intensity.FULL: .190}[level])

    def test_destroy_mid_effect_releases_models_targets_and_stale_callback(self):
        references = []
        for _ in range(30):
            grid = headless_grid()
            meter, border = enable(grid)
            grid.effects.interaction("palette", origin=(250, 200))
            references.extend(weakref.ref(obj) for obj in
                              (grid, grid.effects, grid.effects.hype, grid.effects.particles, meter, border))
            stale = next(iter(grid.scheduler.jobs.values()))[1]
            grid.close_effects()
            stale()
            self.assertFalse(grid.scheduler.jobs)
            del grid, meter, border
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))


if __name__ == "__main__":
    unittest.main()
