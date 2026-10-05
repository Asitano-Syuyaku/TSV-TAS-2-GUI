"""Connect true Editor events to HEAT and FX (dopagaki3.md §7, §9.1, §10).

Every entry point is called only after the Editor's own work succeeded; the
director never changes documents, selection, focus or Undo (T5). Phase 3
adds Validate / F5 / F7 / F8 results; Phase 4 adds sound.
"""

import time
import tkinter as tk

from ..theme import COLORS, HEAT_RAMP, button_options
from .audio import AudioService
from .choreo import F5Choreography
from .fonts import FontBook
from .cover import SendCover
from .fx import (Ambient, Burst, FxEngine, Later, LockOn, Pop, Punch, Ring, Sparks, Tween, NEON,
                 cycle, mix, ramp)
from .heat import COMBO_WINDOW, HeatState
from .outcome import FAILED, SEND_CONFIRMED, SEND_UNVERIFIED, SUCCESS, round_settles
from .hud import FeverHUD
from .words import COMMON, WORDS


TABLE_CAP = 90
HUD_CAP = 40
CELL_GROUND = COLORS["cell_background"]


class DopaDirector:
    def __init__(self, editor, language, motion=100, flashes=True, clock=time.monotonic,
                 sound=True, volume=2, audio=None):
        self.editor = editor
        self.words = WORDS[language]
        self.clock = clock
        self.heat = HeatState()
        self.fonts = FontBook(editor)
        self.fx = FxEngine(editor, motion=motion / 100, flashes=flashes)
        self.hud = FeverHUD(editor.meter_canvas, editor.reward_canvas, language, self.fonts, self.fx)
        self._punch_meter = False
        self._pending_delta = None
        self._combo_job = None
        self._rim_cycle = None
        self._closed = False
        self.cover = None
        self._converting = None  # None, or whether the running conversion sends.
        # Audio (§13): decoration only; silence never changes any result.
        if audio is None:
            path = getattr(getattr(editor, "settings", None), "path", None)
            audio = AudioService.for_root(editor._root(), path.parent if path else None)
        self.audio = audio
        self.sound, self.volume = sound, volume
        self.choreo = None
        self._choreo_effect = None
        self._last_pip = -1.0
        if sound:
            self.audio.prepare()
        self._apply_rim()

    # Settings (§12) -------------------------------------------------------

    def set_settings(self, motion, flashes, sound=None, volume=None):
        self.fx.motion, self.fx.flashes = motion / 100, flashes
        self.hud.set_level(self.heat.intensity, self.heat.extra)
        self._apply_rim()
        if volume is not None and volume != self.volume:
            self.volume = volume
            self.audio.set_level(self, volume)
        if sound is not None and sound != self.sound:
            self.sound = sound
            if sound:
                self.audio.prepare()
            else:  # Muted mid-sting: nothing waits for a track that stopped.
                self._end_choreo(fade=0.15)
                self.audio.stop(self, fade=0.15)

    # Sound effects -----------------------------------------------------------

    def sfx(self, name, delay=0.0):
        """Play a synthesized effect; silent when muted or unavailable."""
        if not self.sound or self._closed or not self.audio.available:
            return
        if delay > 0:
            self.fx.add(Later(delay, lambda: self.sfx(name)))
            return
        self.audio.effect(name, self, self.volume)

    def _pip(self, combo):
        now = self.clock()
        if now - self._last_pip >= 0.06:  # Rapid commits must not smear (§13).
            self._last_pip = now
            self.sfx(f"pip{min(7, max(0, combo - 1))}")

    # Core action (§7) ------------------------------------------------------

    def cell_committed(self, cell, direction, active):
        """A Table cell really changed (after on_change succeeded)."""
        grid = self.editor.table_grid
        grid.fx_layer = True
        canvas = grid.canvas
        reward = self._productive()
        box = grid._cell_box(*cell)
        heat = reward.intensity
        reduced = self.fx.reduced
        self.fx.add(Punch(canvas, box, CELL_GROUND, rainbow=heat >= 1.0, reduced=reduced))
        x1, y1, x2, y2 = box
        center = (x1 + x2) / 2, (y1 + y2) / 2
        if heat >= 0.2 and not reduced:
            self.fx.add(Ring(canvas, center, (8, 46), COLORS["accent"], CELL_GROUND))
        count = self.fx.particle_count(6 + 14 * heat, canvas, TABLE_CAP)
        if count:
            origin = self._edge(box, direction)
            self.fx.add(Sparks(canvas, origin, direction, count, CELL_GROUND, stars=heat >= 0.6))
        if heat >= 0.8:
            confetti = self.fx.particle_count(10, canvas, TABLE_CAP)
            if confetti:
                self.fx.add(Burst(canvas, (center[0], y1), confetti, CELL_GROUND,
                                  power=0.6, duration=0.8))
        self.fx.add(Pop(canvas, (x2 - 4, y1 + 8), f"+{reward.gain:,}", COLORS["neon_yellow"],
                        self.fonts.get("meter", 13), CELL_GROUND, rise=0 if reduced else 28))
        self._pip(reward.combo)
        if active is not None and active != tuple(cell) and not reduced:
            self.fx.add(LockOn(canvas, grid._cell_box(*active), COLORS["neon_yellow"]))
        self._reward_feedback(reward)

    def table_transformed(self):
        """Paste / clear / row and column edits that changed the document."""
        grid = self.editor.table_grid
        grid.fx_layer = True
        canvas = grid.canvas
        reward = self._productive()
        top, bottom, left, right = grid._selection_bounds()
        x1, y1, _, _ = grid._cell_box(top, left)
        _, _, x2, y2 = grid._cell_box(bottom, right)
        # Clip to the visible area: a whole-column selection can span 10,000 rows.
        view_x, view_y = canvas.canvasx(0), canvas.canvasy(0)
        x1, y1 = max(x1, view_x), max(y1, view_y)
        x2 = min(x2, view_x + canvas.winfo_width())
        y2 = min(y2, view_y + canvas.winfo_height())
        if x1 < x2 and y1 < y2:
            self.fx.add(Punch(canvas, (x1, y1, x2, y2), CELL_GROUND, rainbow=reward.intensity >= 1,
                              reduced=self.fx.reduced))
        ax1, ay1, ax2, _ = grid._cell_box(*grid.selected)
        self.fx.add(Pop(canvas, (ax2 - 4, ay1 + 8), f"+{reward.gain:,}", COLORS["neon_yellow"],
                        self.fonts.get("meter", 13), CELL_GROUND,
                        rise=0 if self.fx.reduced else 28))
        self._pip(reward.combo)
        self._reward_feedback(reward)

    def raw_line_committed(self, line):
        """Raw view: Return after a non-blank line that really inserted a newline."""
        gutter = self.editor.line_numbers
        reward = self._productive()
        tag = f"line{line}"
        box = gutter.bbox(tag)
        muted, yellow = COLORS["muted_text"], COLORS["neon_yellow"]
        current = getattr(self.editor, "_cursor_line", None)

        def sink(progress):
            gutter.itemconfigure(tag, fill=yellow if line == current else mix(yellow, muted, progress))

        self.fx.add(Tween(0.35, sink))
        if box is not None:
            count = self.fx.particle_count(4 + 6 * reward.intensity, gutter, 30)
            if count:
                self.fx.add(Sparks(gutter, (box[2], (box[1] + box[3]) / 2), None, count,
                                   COLORS["panel_background"]))
        self._pip(reward.combo)
        self._reward_feedback(reward)

    def history(self):
        """Undo/Redo: a small REWIND only. Not productive; HEAT never drops."""
        self.hud.rewind()
        self.sfx("rewind")

    # Saves and checks (§9.1-§9.2) ----------------------------------------

    def saved(self):
        """_save_to really wrote the file."""
        self.hud.stamp(COMMON["save_stamp"])
        self.sfx("save")

    def deck_pressed(self, button):
        """F5/F8 accepted: the deck button flashes once (§9.3 stage 0)."""
        if self.fx.reduced:
            return
        normal = button.cget("background")

        def flash(progress):
            button.configure(background=mix("#ffffff", normal, progress),
                             activebackground=mix("#ffffff", normal, progress))

        self.fx.add(Tween(0.2, flash))

    def check_started(self):
        """Validate / F7 really running: SCAN beside the lamp, for that time only."""
        self.hud.process(COMMON["scan"])

    def validation_result(self, success, current):
        self.hud.process(None)
        if not current:
            return  # Stale: the factual message only (§9.2).
        if success:
            self.hud.shout(self.words["no_errors"], 3)
            self._confetti(("#39ff14", "#7cff4f", "#bfffd0"))
            self.sfx("clear")
        else:
            self._oshii()

    def analysis_result(self, success, current, total=None):
        self.hud.process(None)
        if not current:
            return
        if success:
            self.hud.shout(self.words["scanned"].format(n=f"{total:,}"), 2)
            self.sfx("clear")
        else:
            self._oshii()

    # Conversion (§9.3-§9.4) ----------------------------------------------

    def conversion_started(self, send):
        """on_convert returned True: the run is real from here on (never delayed)."""
        self._converting = send
        self._end_choreo(fade=0.08)  # A second F5 replaces the previous sting.
        self.hud.process(COMMON["converting"])
        if not send:
            self.hud.process_rays(True)
            self._start_choreo()
        elif not self.fx.reduced:
            self._close_cover()
            self.cover = SendCover(self.editor, self.fonts, self.fx, self.words,
                                   started=self.clock(), clock=self.clock,
                                   on_closed=self._cover_closed, sfx=self.sfx)

    def conversion_result(self, outcome, output_name=None, output_format=None, started=True):
        """The parent Converter's own result event, classified by outcome.py.

        Facts first, at this moment: the HUD result line (and the Editor's
        Problems panel for failures). Celebrations may follow the music.
        """
        send = bool(self._converting)
        self._converting = None
        self.hud.process(None)
        self.hud.process_rays(False)
        self.hud.fact(self._fact_text(outcome, output_name, started), outcome)
        cover = self.cover
        choreo = self.choreo if not send else None
        if choreo is not None:
            choreo.result(outcome, self.clock())
        if outcome == FAILED:
            if cover is not None:
                cover.resolve(FAILED, None, None)
                self.heat.reset_combo()
                self.hud.fade_combo()
            else:
                self._oshii()
            return
        if choreo is not None:
            return  # The climax lands with the music (choreo_climax).
        format_label = self.words["formats"].get(output_format, output_format or "")
        if cover is not None and outcome in (SEND_CONFIRMED, SEND_UNVERIFIED):
            cover.resolve(outcome, output_name, format_label)
            if outcome == SEND_CONFIRMED:  # 決着 after the card and its stars.
                self.fx.add(Later(1.0, self._settle_with_flash))
                self.sfx("fanfare", delay=1.0)
                self.sfx("coins", delay=1.1)
            return
        # F5, or F8 whose COVER is closed / not shown (Effects 0%): HUD only.
        steps = COMMON["steps"]
        if outcome == SUCCESS:
            self.hud.shout(self.words["converted"], 4)
            self.hud.caption(f"{steps[0]} ★  {steps[1]} ★")
            self._coins()
            self.sfx("fanfare_s")
        elif outcome == SEND_CONFIRMED:
            self.hud.shout(self.words["sent"], 4)
            self.hud.caption(f"{steps[0]} ★  {steps[1]} ★  {steps[2]} ★")
            self._coins()
            self.sfx("fanfare")
        elif outcome == SEND_UNVERIFIED:
            self.hud.shout(self.words["built"], 1, color=COLORS["neon_orange"])
            self.hud.caption(self.words["send_unverified"])
            self.sfx("chime")
        if round_settles(outcome):
            self._settle_with_flash()

    def _fact_text(self, outcome, output_name, started):
        words = self.words
        if outcome == FAILED:
            return words["fact_failed" if started else "fact_not_started"]
        if outcome == SEND_UNVERIFIED:
            return words["fact_unverified"]
        key = "fact_sent" if outcome == SEND_CONFIRMED else "fact_output"
        return words[key].format(name=output_name or "")

    # F5 x Let's Go (§13.3) ------------------------------------------------------

    def _start_choreo(self):
        if not self.sound or not self.audio.available or not self.audio.music_ready:
            return  # No track: P3's immediate peak, with synthesized effects.
        voice = self.audio.track(self, self.volume)
        if voice is None:
            return
        self.choreo = F5Choreography(voice, self.clock(), self, hold_visuals=not self.fx.reduced)
        ticker = Ambient(lambda now: self._tick_choreo())
        ticker.ambient = False  # Full frame rate while a sting plays: the drop lands within ~16 ms.
        self._choreo_effect = self.fx.add(ticker)

    def _tick_choreo(self):
        choreo = self.choreo
        if choreo is None or not choreo.tick(self.clock()):
            if self._choreo_effect is not None:
                effect, self._choreo_effect = self._choreo_effect, None
                self.fx.stop(effect)
            if choreo is not None and (choreo.ended or choreo.outcome is not None):
                self.choreo = None

    def _end_choreo(self, fade=0.08, celebrate=True):
        choreo, self.choreo = self.choreo, None
        if choreo is not None:
            choreo.cancel(self.clock(), fade, celebrate)
        if self._choreo_effect is not None:
            effect, self._choreo_effect = self._choreo_effect, None
            self.fx.stop(effect)

    def choreo_beat(self, remaining):
        """Build-up: the RIM breathes on every beat. Music only, never progress."""
        rim, color = self.editor._rim, self._rim_color()
        lift = 0.5 if remaining <= 4 else 0.3
        self.fx.add(Tween(0.14, lambda progress: rim.configure(
            highlightbackground=mix(mix(color, "#ffffff", lift), color, progress))))

    def choreo_hold(self):
        """The track's own breath before the drop: the rays stop for one beat."""
        self.hud.process_rays(False)

    def choreo_drop(self):
        """Drop with the run still going: energy, but no success words (Truth)."""
        if self._converting is False:
            self.hud.process_rays(True)
        self.hud.shake(1.0)

    def choreo_climax(self, on_drop=False):
        """F5 success, landed with the music. The facts were shown already."""
        steps = COMMON["steps"]
        self.hud.shout(self.words["converted"], 4)
        self.hud.caption(f"{steps[0]} ★  {steps[1]} ★")
        self._coins()
        self.sfx("coins", delay=0.1)  # The track's own drop carries the hit.
        self._settle_with_flash()

    def _settle_with_flash(self):
        if self._closed:
            return
        if self.fx.flash_allowed():
            self._flash_rim()
        bonus = self.heat.settle()
        self.hud.settle(bonus)
        self._show_heat(animate=True)

    def _cover_closed(self, cover):
        if self.cover is cover:
            self.cover = None

    def _close_cover(self):
        if self.cover is not None:
            self.cover.close(immediate=True)
            self.cover = None

    def _oshii(self):
        """Failure keeps HEAT and DOPA; only the combo resets (§7.3)."""
        self.heat.reset_combo()
        self.hud.shout(self.words["oshii"], 1, color=COLORS["neon_orange"])
        self.hud.fade_combo()
        self.sfx("oshii")

    def _target_canvas(self):
        editor = self.editor
        if getattr(editor, "_view", "raw") == "table":
            editor.table_grid.fx_layer = True
            canvas = editor.table_grid.canvas
            origin = (canvas.canvasx(canvas.winfo_width() / 2),
                      canvas.canvasy(editor.table_grid.header_height))
            return canvas, origin, CELL_GROUND, TABLE_CAP
        return editor.reward_canvas, self.hud.shout_center, COLORS["panel_background"], HUD_CAP

    def _confetti(self, colors):
        canvas, origin, ground, cap = self._target_canvas()
        count = self.fx.particle_count(36, canvas, cap)
        if count:
            self.fx.add(Burst(canvas, origin, count, ground, kinds=("confetti",), power=0.9,
                              duration=1.1, colors=colors))

    def _coins(self):
        canvas, origin, ground, cap = self._target_canvas()
        count = self.fx.particle_count(50, canvas, cap)
        if count:
            self.fx.add(Burst(canvas, origin, count, ground, kinds=("coin", "confetti", "coin"),
                              power=1.0, duration=1.2))

    # Frame data (§6.1) ---------------------------------------------------

    def positions_confirmed(self, total):
        confirmation = self.heat.confirmed_total(total)
        self.sfx("lock")
        self._punch_meter = True
        self._pending_delta = confirmation.delta or None
        if confirmation.milestone is not None:
            self._milestone(confirmation.milestone)

    def meter(self, model):
        punch = self._punch_meter and model[0] == "confirmed"
        self._punch_meter = False
        self.hud.set_meter(model, punch=punch)
        delta, self._pending_delta = self._pending_delta, None
        if delta and model[0] == "confirmed":
            self.hud.delta(delta)

    def document_replaced(self):
        self.heat.document_replaced()
        self._punch_meter, self._pending_delta = False, None
        self._show_heat(animate=False)

    def stick_ring(self, canvas, point, color):
        if not self.fx.reduced:
            self.fx.add(Ring(canvas, point, (7, 16), color, COLORS["preview_background"], width=2))

    # Palette (§8.3) --------------------------------------------------------

    def palette_pressed(self, button, color):
        # Theme values, not cget(): a second press mid-flash must not keep flash colors.
        normal = button_options("palette")
        if self.fx.reduced:
            return

        def flash(progress):
            # Hold the category color 80ms, then return over 120ms.
            amount = 0.0 if progress < 0.4 else (progress - 0.4) / 0.6
            button.configure(background=mix(color, normal["background"], amount),
                             activebackground=mix(color, normal["activebackground"], amount),
                             foreground=COLORS["on_neon"] if amount < 0.5 else normal["foreground"],
                             activeforeground=(COLORS["on_neon"] if amount < 0.5
                                               else normal["activeforeground"]))

        self.fx.add(Tween(0.2, flash))

    def grow_rules(self, rules):
        if self.fx.reduced:
            return
        for rule in rules:
            self.fx.add(Tween(0.12, lambda progress, item=rule:
                              item.configure(width=max(1, round(28 * progress)))))

    # Internals -------------------------------------------------------------

    def _productive(self):
        return self.heat.productive(self.clock())

    def _reward_feedback(self, reward):
        self._show_heat(animate=True, level_up=reward.level_up)
        if reward.shout is not None:
            self.hud.shout(self.words["ladder"][reward.shout], reward.shout)
            if reward.shout >= 2:
                self.sfx(f"shout{reward.shout}")
            if reward.shout >= 6 and self.fx.flash_allowed():
                self._flash_rim()
        if self._combo_job is not None:
            self.editor.after_cancel(self._combo_job)
        self._combo_job = self.editor.after(int(COMBO_WINDOW * 1000) + 50, self._combo_check)

    def _combo_check(self):
        self._combo_job = None
        if not self.heat.combo_alive(self.clock()):
            self.hud.fade_combo()

    def _show_heat(self, animate=True, level_up=False):
        heat = self.heat
        self.hud.set_reward(heat.dopa, heat.combo, heat.multiplier, heat.intensity, heat.segments,
                            heat.round, heat.extra, animate=animate, level_up=level_up,
                            combo_alive=heat.combo_alive(self.clock()))
        self._apply_rim()

    def _rim_color(self):
        return ramp(HEAT_RAMP, min(1.0, self.heat.intensity))

    def _apply_rim(self):
        rim = self.editor._rim
        if self.heat.extra and not self.fx.reduced:
            if self._rim_cycle is None:
                ring = HEAT_RAMP + HEAT_RAMP[-2:0:-1]
                self._rim_cycle = self.fx.add(Ambient(lambda now: rim.configure(
                    highlightbackground=cycle(ring, now, 0.25))))
            return
        if self._rim_cycle is not None:
            self.fx.stop(self._rim_cycle)
            self._rim_cycle = None
        color = self._rim_color()
        rim.configure(highlightbackground=color, highlightcolor=color)

    def _flash_rim(self):
        rim, color = self.editor._rim, self._rim_color()
        self.fx.add(Tween(0.24, lambda progress: rim.configure(
            highlightbackground=mix("#ffffff", color, progress))))

    def _milestone(self, mark):
        text = self.words["milestones"][mark]
        self.hud.shout(text, 3)
        self.sfx("stamp")
        self.sfx("coins", delay=0.12)
        if mark in (3600, 18000):
            self.hud.caption(COMMON["fps_tag"])
        canvas, origin, ground, cap = self._target_canvas()
        count = self.fx.particle_count(30, canvas, cap)
        if count:
            self.fx.add(Burst(canvas, origin, count, ground, kinds=("coin", "star", "coin"),
                              power=0.9, duration=1.1))

    @staticmethod
    def _edge(box, direction):
        x1, y1, x2, y2 = box
        if direction is None:
            return x2, y1
        rows, columns = direction
        if columns > 0:
            return x2, (y1 + y2) / 2
        if columns < 0:
            return x1, (y1 + y2) / 2
        if rows > 0:
            return (x1 + x2) / 2, y2
        return (x1 + x2) / 2, y1

    def destroy(self):
        if self._closed:
            return
        self._end_choreo(fade=0.0, celebrate=False)
        self.audio.stop(self)
        self._closed = True
        if self.cover is not None:
            self.cover.close(immediate=True)
            self.cover = None
        # Runs inside the Editor's <Destroy>: canvases may already be gone, and
        # nothing here may stop the Editor's own cleanup that follows.
        if self._combo_job is not None:
            try:
                self.editor.after_cancel(self._combo_job)
            except tk.TclError:
                pass
            self._combo_job = None
        self.fx.close()
        self.hud.destroy()
        self.fonts.clear()
