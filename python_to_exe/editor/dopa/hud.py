"""FEVER HUD (dopagaki3.md §6): FRAME METER (data) and REWARD (game).

The left METER only shows converter-confirmed numbers, snapped in place (T1);
while pending/unavailable it shows dashes, never older values (T2). The right
REWARD canvas holds game numbers, which may roll, slam and shake. Only the
REWARD canvas ever shakes or gets background motion.
"""

import math

from ..theme import COLORS, HEAT_RAMP
from .fx import Ambient, Pop, Shake, Shout, Tween, NEON, ease_out, mix, ramp
from .heat import format_dopa, frames_as_time
from .words import COMMON, WORDS


GROUND = COLORS["panel_background"]
METER_HEIGHT = 54
METER_MIN_WIDTH = 470
LAMPS = {"confirmed": ("●", COLORS["neon_green"], "meter_locked"),
         "pending": ("◐", COLORS["neon_yellow"], "meter_pending"),
         "unavailable": ("○", COLORS["neon_orange"], "meter_unavailable"),
         "tsv_only": ("○", COLORS["muted_text"], "meter_tsv_only")}
SHOUT_PIXELS = (18, 22, 26, 30, 35, 40, 44)
SHOUT_ANGLES = (-4, -6, -7, -8, -8, -9, -10)
SHOUT_COLORS = (COLORS["text"], COLORS["text"], COLORS["neon_magenta"], COLORS["accent"])
# Background levels (§6.3): faint rays, neon-tinted rays.
RAYS = {1: ("#151225", "#120f20", 40.0), 2: ("#1d1236", "#101a2c", 20.0)}


class FeverHUD:
    def __init__(self, meter, reward, language, fonts, engine):
        self.meter, self.reward = meter, reward
        self.words, self.language = WORDS[language], language
        self.fonts, self.engine = fonts, engine
        self._model = None
        self._value_pixels = 22
        self._punch = None
        self._lamp_pulse = None
        self._dopa_shown = 0
        self._dopa_tween = None
        self._shout = None
        self._combo_tween = None
        self._background = {}
        self._level = None
        self._heat = (0, 0, 1)
        self._build_meter()
        reward.configure(confine=False)
        reward.bind("<Configure>", lambda event: self._layout_reward())
        self._build_reward()

    # FRAME METER ---------------------------------------------------------

    def _build_meter(self):
        meter, caps = self.meter, self.fonts.get("caps", 10)
        self.lamp = meter.create_text(10, 8, anchor="w", font=caps)
        self.state = meter.create_text(24, 8, anchor="w", font=caps)
        self.labels, self.values, self.units = [], [], []
        for name in COMMON["fields"]:
            self.labels.append(meter.create_text(0, 23, anchor="w", text=name, font=self.fonts.get(
                "caps", 9), fill=COLORS["muted_text"]))
            self.values.append(meter.create_text(0, 41, anchor="w", fill=COLORS["neon_yellow"],
                                                 font=self.fonts.get("meter", 22)))
            self.units.append(meter.create_text(0, 44, anchor="w", text="f", fill=COLORS["muted_text"],
                                                font=self.fonts.get("meter", 12, bold=False)))
        self.note = meter.create_text(0, 44, anchor="w", fill=COLORS["muted_text"],
                                      font=self.fonts.get("caps", 10, bold=False))

    def set_meter(self, model, punch=False):
        """model: (state, start, duration, end, total); numbers only when confirmed."""
        state = model[0]
        symbol, color, key = LAMPS[state]
        self.meter.itemconfigure(self.lamp, text=symbol, fill=color)
        self.meter.itemconfigure(self.state, text=self.words[key], fill=color)
        if state == "confirmed":
            texts = [f"{value:,}" if value is not None else "—" for value in model[1:]]
            note = COMMON["fps_note"].format(time=frames_as_time(model[4]))
            fill = COLORS["neon_yellow"]
        elif state == "tsv_only":
            texts, note, fill = ["", "", "", ""], "", COLORS["muted_text"]
        else:  # T2: no stale or guessed numbers while not confirmed.
            texts, note, fill = ["- - -"] * 4, "", COLORS["muted_text"]
        for value, unit, text in zip(self.values, self.units, texts):
            self.meter.itemconfigure(value, text=text, fill=fill)
            self.meter.itemconfigure(unit, text="f" if text and state == "confirmed" else "")
        self.meter.itemconfigure(self.note, text=note)
        self._model = model
        self._pulse_lamp(state == "pending")
        if punch and state == "confirmed" and not self.engine.reduced:
            if self._punch is not None:
                self.engine.stop(self._punch)
            self._punch = self.engine.add(Tween(0.1, self._punch_frame))
        else:
            self._layout_meter(22)

    def _punch_frame(self, progress):
        self._layout_meter(22 + 7 * (1 - ease_out(progress)))

    def _layout_meter(self, pixels):
        meter = self.meter
        font = self.fonts.get("meter", pixels)
        x = 12
        for label, value, unit in zip(self.labels, self.values, self.units):
            meter.coords(label, x, 23)
            meter.coords(value, x, 41)
            meter.itemconfigure(value, font=font)
            right = (meter.bbox(value) or (x, 0, x, 0))[2]
            meter.coords(unit, right + 1, 44)
            unit_right = (meter.bbox(unit) or (right, 0, right, 0))[2]
            label_right = (meter.bbox(label) or (x, 0, x, 0))[2]
            x = max(x + 80, unit_right, label_right) + 16
        meter.coords(self.note, x - 8, 44)
        note_right = (meter.bbox(self.note) or (x, 0, x, 0))[2]
        needed = max(METER_MIN_WIDTH, note_right + 10)
        if pixels == 22 and needed > int(meter.cget("width")):
            meter.configure(width=needed)  # Only grows for very long scripts.

    def total_anchor(self):
        box = self.meter.bbox(self.units[3]) or self.meter.bbox(self.values[3]) or (0, 0, 0, 0)
        return box[2] + 4, 26

    def delta(self, frames):
        if not frames:
            return
        text = f"{'+' if frames > 0 else '−'}{abs(frames):,}f"
        color = COLORS["neon_green"] if frames > 0 else COLORS["accent"]
        self.engine.add(Pop(self.meter, self.total_anchor(), text, color,
                            self.fonts.get("meter", 13), GROUND, anchor="w",
                            rise=0 if self.engine.reduced else 16, duration=0.7, delay=0))

    def _pulse_lamp(self, on):
        if on and self._lamp_pulse is None and not self.engine.reduced:
            dim = mix(COLORS["neon_yellow"], GROUND, 0.7)

            def pulse(now):
                level = 0.5 + 0.5 * math.sin(now * 2 * math.pi / 0.6)
                self.meter.itemconfigure(self.lamp, fill=mix(dim, COLORS["neon_yellow"], level))

            self._lamp_pulse = self.engine.add(Ambient(pulse))
        elif not on and self._lamp_pulse is not None:
            self.engine.stop(self._lamp_pulse)
            self._lamp_pulse = None

    # REWARD --------------------------------------------------------------

    def _build_reward(self):
        reward = self.reward
        self.brackets = [reward.create_line(0, 0, 0, 0, 0, 0, fill=COLORS["neon_yellow"], width=2,
                                            tags=("frame",)) for _ in range(4)]
        self.heat_label = reward.create_text(0, 12, anchor="w", text=COMMON["heat"],
                                             font=self.fonts.get("caps", 9), fill=COLORS["muted_text"])
        self.segments = [reward.create_rectangle(0, 0, 0, 0, outline="", fill=COLORS["subtle_border"])
                         for _ in range(10)]
        self.round_text = reward.create_text(0, 12, anchor="e", font=self.fonts.get("caps", 10),
                                             fill=COLORS["muted_text"])
        self.combo = reward.create_text(0, 31, anchor="e", text="", fill=COLORS["neon_magenta"],
                                        font=self.fonts.get("shout", 15))
        self.dopa_label = reward.create_text(0, 54, anchor="e", text=COMMON["dopa"],
                                             font=self.fonts.get("caps", 10), fill=COLORS["muted_text"])
        self.dopa = reward.create_text(0, 52, anchor="e", text="0", fill=COLORS["neon_yellow"],
                                       font=self.fonts.get("meter", 22))
        self._layout_reward()

    def _layout_reward(self):
        reward = self.reward
        width = max(int(reward.winfo_width()), int(reward.cget("width")), 120)
        height = max(int(reward.winfo_height()), int(reward.cget("height")), METER_HEIGHT)
        arm, inset = 10, 3
        for line, (x, y, sx, sy) in zip(self.brackets, ((inset, inset, 1, 1),
                                                        (width - inset, inset, -1, 1),
                                                        (inset, height - inset, 1, -1),
                                                        (width - inset, height - inset, -1, -1))):
            reward.coords(line, x + sx * arm, y, x, y, x, y + sy * arm)
        right = width - 14
        block = min(300, width - 24)
        step = max(8, min(17, (block - 92) / 10))
        left = right - block
        reward.coords(self.heat_label, left, 12)
        for index, segment in enumerate(self.segments):
            x = left + 40 + index * step
            reward.coords(segment, x, 8, x + step - 4, 16)
        reward.coords(self.round_text, right, 12)
        reward.coords(self.combo, right, 31)
        reward.coords(self.dopa_label, right, 54)
        label_width = self.fonts.get("caps", 10).measure(COMMON["dopa"])
        reward.coords(self.dopa, right - label_width - 6, 52)
        zone_right = left - 16
        self.shout_center = ((12 + zone_right) / 2 if zone_right - 12 >= 160 else width / 2,
                             height / 2)
        self._size = width, height
        self._redraw_background()

    def set_reward(self, dopa, combo, multiplier, heat, segments, round_number, extra,
                   animate=True, level_up=False, combo_alive=True):
        reduced = self.engine.reduced
        if self._dopa_tween is not None:
            self.engine.stop(self._dopa_tween)
            self._dopa_tween = None
        start = self._dopa_shown
        self._dopa_shown = dopa
        if animate and not reduced and dopa != start:
            def roll(progress):
                shown = start + (dopa - start) * ease_out(progress)
                self.reward.itemconfigure(self.dopa, text=format_dopa(shown, self.language))
            self._dopa_tween = self.engine.add(Tween(0.3, roll))
        else:
            self.reward.itemconfigure(self.dopa, text=format_dopa(dopa, self.language))
        text = (COMMON["combo"].format(n=combo, m=multiplier) if combo >= 2 and combo_alive else "")
        self.reward.itemconfigure(self.combo, text=text, fill=COLORS["neon_magenta"])
        if text and animate and not reduced:
            if self._combo_tween is not None:
                self.engine.stop(self._combo_tween)
            self._combo_tween = self.engine.add(Tween(0.1, lambda progress: self.reward.itemconfigure(
                self.combo, font=self.fonts.get("shout", 15 + 6 * (1 - ease_out(progress))))))
        round_text = COMMON["round"].format(n=round_number)
        if extra:
            round_text += " · " + COMMON["extra"].format(n=extra)
        self.reward.itemconfigure(self.round_text, text=round_text,
                                  fill=COLORS["neon_magenta"] if extra else COLORS["muted_text"])
        for index, segment in enumerate(self.segments):
            lit = index < segments
            self.reward.itemconfigure(segment, fill=ramp(HEAT_RAMP, index / 9) if lit
                                      else COLORS["subtle_border"])
        if level_up and segments and not reduced:
            segment, color = self.segments[segments - 1], ramp(HEAT_RAMP, (segments - 1) / 9)
            self.engine.add(Tween(0.2, lambda progress: self.reward.itemconfigure(
                segment, fill=mix("#ffffff", color, progress))))
        self._heat = (heat, extra, round_number)
        self.set_level(heat, extra)

    def fade_combo(self):
        if self.engine.reduced:
            self.reward.itemconfigure(self.combo, text="")
            return

        def fade(progress):
            self.reward.itemconfigure(self.combo, fill=mix(COLORS["neon_magenta"], GROUND, progress))
            if progress >= 1:
                self.reward.itemconfigure(self.combo, text="", fill=COLORS["neon_magenta"])

        self.engine.add(Tween(0.3, fade))

    def shout(self, text, tier, color=None, hold=None, pixels=None, angle=None):
        """One shout at a time in the SHOUT ZONE (§7.4); never over the WORK layer."""
        if self._shout is not None:
            self.engine.stop(self._shout)
        tier = max(0, min(6, tier))
        rainbow = tier >= 4 and color is None
        self._shout = self.engine.add(Shout(
            self.reward, self.shout_center, text, self.fonts,
            pixels or SHOUT_PIXELS[tier], color or SHOUT_COLORS[min(tier, 3)],
            COLORS["on_neon"], GROUND, angle=SHOUT_ANGLES[tier] if angle is None else angle,
            hold=0.52 + tier * 0.09 if hold is None else hold, rainbow=rainbow,
            reduced=self.engine.reduced))
        if tier >= 4 and not self.engine.reduced:
            self.engine.add(Shake(self.reward, 0.6 + 0.2 * (tier - 4)))

    def caption(self, text, offset=24):
        """Small note under the shout (e.g. "@60fps" on time milestones)."""
        x, y = self.shout_center
        self.engine.add(Pop(self.reward, (x, y + offset), text, COLORS["muted_text"],
                            self.fonts.get("caps", 10), GROUND, rise=0, duration=1.0,
                            delay=0.1, anchor="center"))

    def rewind(self):
        self.shout(COMMON["rewind"], 0, color=COLORS["accent"], hold=0.3, pixels=16, angle=0)

    # Background (§6.3) -----------------------------------------------------

    def set_level(self, heat, extra):
        if self.engine.reduced:
            level = (0, False, False)
        else:
            level = (2 if heat >= 0.8 else 1 if heat >= 0.4 else 0, heat >= 0.6, heat >= 1.0)
        if (level, extra) == self._level:
            return
        self._level = level, extra
        self._redraw_background()

    def _stop_background(self):
        for effect in self._background.values():
            self.engine.stop(effect)
        self._background.clear()
        self.reward.delete("bg", "tape")

    def _redraw_background(self):
        self._stop_background()
        if not self._level:
            return
        (rays, tapes, fever), extra = self._level
        heat = self._heat[0]
        if rays:
            self._background["rays"] = self.engine.add(Ambient(self._ray_painter(*RAYS[rays])))
        if tapes:
            self._background["tapes"] = self.engine.add(
                Ambient(self._tape_painter(heat, fever, extra)))
        self.reward.tag_lower("tape")
        self.reward.tag_lower("bg")

    def _ray_painter(self, first, second, period):
        width, height = self._size
        cx, cy = self.shout_center
        radius = math.hypot(width, height)
        rays = [self.reward.create_polygon(cx, cy, cx, cy, cx, cy, outline="",
                                           fill=first if index % 2 == 0 else second, tags=("bg",))
                for index in range(24)]

        def paint(now):
            turn = 2 * math.pi * (now / period % 1)
            for index, ray in enumerate(rays):
                a, b = turn + index * math.pi / 12, turn + (index + 1) * math.pi / 12
                self.reward.coords(ray, cx, cy, cx + math.cos(a) * radius, cy + math.sin(a) * radius,
                                   cx + math.cos(b) * radius, cy + math.sin(b) * radius)

        return paint

    def _tape_painter(self, heat, fever, extra):
        reward, (width, height) = self.reward, self._size
        bottom = 12 if fever else 5
        for top, size in ((0, 5), (height - bottom, bottom)):
            reward.create_rectangle(-24, top, width + 24, top + size, fill=COLORS["on_neon"],
                                    outline="", tags=("tape",))
        for x in range(-24, width + 24, 12):
            reward.create_polygon(x, 5, x + 6, 0, x + 12, 0, x + 6, 5, fill=COLORS["neon_yellow"],
                                  outline="", tags=("tape", "stripes"))
            if not fever:
                reward.create_polygon(x, height, x + 6, height - 5, x + 12, height - 5, x + 6, height,
                                      fill=COLORS["neon_yellow"], outline="", tags=("tape", "stripes"))
        period = 12
        if fever:
            reward.create_rectangle(-24, height - bottom, width + 24, height,
                                    fill=COLORS["neon_yellow"], outline="", tags=("tape",))
            unit = (COMMON["tape_extra"].format(n=extra) if extra else COMMON["tape"])
            font = self.fonts.get("caps", 9)
            period = max(1, font.measure(unit))
            copies = int((width + 2 * period) / period) + 1
            reward.create_text(-period, height - bottom / 2, anchor="w", text=unit * copies,
                               font=font, fill=COLORS["on_neon"], tags=("tape", "words"))
        speed = 10 + 30 * min(1.0, heat)
        state = {"stripes": 0.0, "words": 0.0}

        def paint(now):
            for tag, length in (("stripes", 12), ("words", period)):
                offset = (now * speed) % length
                reward.move(tag, offset - state[tag], 0)
                state[tag] = offset

        return paint

    def destroy(self):
        for effect in self._background.values():
            self.engine.stop(effect)
        self._background.clear()  # Items died with the canvas; never touch it here.
