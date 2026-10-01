"""F5 presentation in existing Canvas surfaces, without input/focus bindings."""

import math
import weakref
from tkinter import TclError

from . import theme
from .micro import ValuePulses, WidgetPulse, duration_for
from .motion import Intensity


STATIC_TAG = "dopagaki_ritual_static"
STAMP_TAG = "dopagaki_ritual_stamp"
PARTICLE_OWNER = "f5_ritual"


class RitualView:
    """Static edges + short stamp inside D2's juice slot, never a ninth loop.

    Grid hit testing is coordinate-based and these items have no bindings.
    The editing Entry is a raised widget above the Canvas. A small status-bar
    Canvas keeps Raw-mode countdown/pending visible without overlaying Text.
    Only effect item coordinates shake; fonts of normal widgets never change.
    """

    def __init__(self, editor, *, banner=None, family="TkDefaultFont"):
        self._editor = weakref.ref(editor)
        self._effects = weakref.ref(editor.table_grid.effects)
        self._canvas = weakref.ref(editor.table_grid.canvas)
        self._banner = weakref.ref(banner) if banner is not None else None
        self._family = family
        self.level = editor.table_grid.effects.motion.intensity
        self.stage = None
        self.progress = 0.0
        self._stamp = None
        self._born = self._until = self._flash_until = 0.0
        self._tone = theme.RITUAL_COLORS["start"]
        self._flash_strength = 1.0
        self._items = []
        self._painted = []
        self._font_fit_key = None
        self._font_fit_base = 0.0
        self._signature = None
        self._last_drop = -math.inf
        self._banner_text = ""
        self._micro_effects = {}

    @property
    def deadline(self):
        return max(self._until, self._flash_until)

    def _status(self, text):
        self._banner_text = text
        banner = self._banner() if self._banner is not None else None
        if banner is not None:
            try:
                banner.delete("all")
                if text:
                    banner.place(relx=1, rely=0.5, anchor="e", width=190, height=18)
                    banner.create_text(185, 9, anchor="e", text=text,
                                       font=(self._family, 9, "bold"), fill=self._tone)
                else:
                    banner.place_forget()
            except TclError:
                self._banner = None

    def show(self, event, progress, *, pending=False):
        effects = self._effects()
        if effects is None or self.level == Intensity.OFF:
            return
        now = effects._clock()
        self.progress = min(1.0, max(0.0, progress))
        if event == "ready":
            self._status("F5 · OUTPUT READY")
            return
        if event == "pending":
            self._status("F5 · CHARGING...")
            return
        if event == "settle":
            self.clear()
            if pending:
                self._status("F5 · CHARGING...")
            return
        old = effects.effect_for("juice")
        if old is not None:
            # Detach the old facade before creating a new stamp. Its expired
            # deadline must not finish the replacement during another pulse.
            old.handoff()
            effects.remove("juice")
        if event in ("start", "build", "tension"):
            self.stage = event
            self._tone = theme.RITUAL_COLORS[event]
            self._status("F5 · " + ("BUILD" if event != "tension" else "DROP INCOMING"))
        elif event in ("3", "2", "1"):
            self.stage = "tension"
            self._tone = theme.RITUAL_COLORS[{"3": "start", "2": "build", "1": "tension"}[event]]
            self._impact(event, now)
            self._status("F5 · " + event)
        elif event == "drop":
            self.stage = "drop"
            self._tone = theme.RITUAL_COLORS["white"]
            self._last_drop = now
            self._impact("LET'S GO!!", now)
        elif event == "success":
            self.stage = "drop"
            self._tone = theme.RITUAL_COLORS["success"]
            # At the drop, show both independently truthful messages together.
            text = "LET'S GO!!\nCONVERTED" if now - self._last_drop < 0.05 else "CONVERTED"
            self._impact(text, now)
            self._status("F5 · CONVERTED")
        elif event == "failure":
            self.stage = None
            self._tone = theme.RITUAL_COLORS["failure"]
            self._impact("CHECK OUTPUT", now, failure=True)
            self._status("F5 · CHECK OUTPUT")
        self._flash_until = now + (0.180 if self.level == Intensity.LOW else 0.320)
        self._flash_strength = {"start": 0.35, "build": 0.55, "tension": 0.75,
                                "spark": 0.55, "3": 0.60, "2": 0.80}.get(event, 1.0)
        if event != "failure":
            self._burst(event, now)
        if event in ("build", "tension", "1", "success", "failure"):
            self._micro(event)
        self.repaint()
        effects.refresh_visual()

    def _impact(self, text, now, *, failure=False):
        self.finish_animation()
        self._stamp = text
        self._born = now
        self._until = now + (0.280 if failure else theme.RITUAL_STAMP_SECONDS[self.level.value])

    def _micro(self, event):
        editor, effects = self._editor(), self._effects()
        if editor is None or effects is None:
            return
        if event == "failure":
            # Keep existing Problems/log text and error handling; color only.
            target = (editor._problems_title if editor._problems_panel.winfo_ismapped()
                      else getattr(editor.master, "log_text", None))
            if target is not None:
                effects.pulse_widget("page", target, "page", ink=True)
                self._own_micro("page")
            return
        effects.pulse_widget("page", editor._palette_page_label, "page", ink=True)
        self._own_micro("page")
        labels = getattr(editor.frame_status, "value_labels", ())
        if labels:
            effects.remove("frame")
            effects.play_effect("frame", ValuePulses([
                WidgetPulse(label, effects.micro_strength(), duration_for(self.level, "frame"), ink=True)
                for label in labels]))
            self._own_micro("frame")
        if event in ("tension", "1", "success") and editor.stick_preview.winfo_ismapped():
            from ..stick_preview import PLOT_HEIGHT
            for column, canvas in enumerate(editor.stick_preview.plots):
                effects.pulse_ring(column, canvas, PLOT_HEIGHT)
                self._own_micro(f"stick{column}")

    def _own_micro(self, key):
        effect = self._effects().effect_for(key)
        if effect is not None:
            self._micro_effects[key] = weakref.ref(effect)

    def _burst(self, event, now):
        effects, canvas = self._effects(), self._canvas()
        if effects is None or effects.particles is None or canvas is None:
            return
        amount = {"LOW": 5, "MID": 16, "FULL": 34}[self.level.value]
        count = round(amount * (0.22 + 0.78 * self.progress))
        if event == "success":
            count = {"LOW": 10, "MID": 48, "FULL": 96}[self.level.value]
        elif event == "start":
            count = {"LOW": 2, "MID": 4, "FULL": 8}[self.level.value]
        pool = effects.particles
        grid = pool.surfaces.get("grid")
        viewport = grid.viewport() if grid is not None else None
        if viewport is not None:
            x, y, width, height = viewport
            origins = [((x + grid.left + 10, y + grid.top + 10), (1, 1)),
                       ((x + width - 10, y + height - 10), (-1, -1))]
            for index, (origin, direction) in enumerate(origins):
                pool.spawn("grid", origin, count // 2 + (count % 2 if index == 0 else 0),
                           self.level, self.progress, now, direction=direction, owner=PARTICLE_OWNER)
        else:
            # Raw mode retains its own Text/caret and uses only the status strip.
            return
        if event in ("1", "success"):
            for name in ("stick0", "stick1"):
                surface = pool.surfaces.get(name)
                viewport = surface.viewport() if surface is not None else None
                if viewport is not None:
                    x, y, width, height = viewport
                    pool.spawn(name, (x + width / 2, y + height / 2 - 15), max(1, count // 8),
                               self.level, self.progress, now, owner=PARTICLE_OWNER)

    def repaint(self):
        effects = self._effects() if self._effects is not None else None
        if effects is not None and effects._clock is not None:
            self.render(effects._clock())

    def render(self, now):
        canvas = self._canvas() if self._canvas is not None else None
        effects = self._effects() if self._effects is not None else None
        if canvas is None or effects is None:
            return
        try:
            if not canvas.winfo_exists() or not canvas.winfo_ismapped():
                return
        except TclError:
            return
        surface = effects.particles.surfaces["grid"]
        x, y = canvas.canvasx(0), canvas.canvasy(0)
        width, height = canvas.winfo_width(), canvas.winfo_height()
        flash = max(0.0, min(1.0, (self._flash_until - now) / 0.320))
        shade = round(flash * 8)
        signature = x, y, width, height, self.stage, self.level, self._tone, shade, self._flash_strength
        if signature != self._signature:
            canvas.delete(STATIC_TAG)
            if self.stage is not None or flash:
                color = theme.blend_color(theme.TABLE_COLORS["active_selection_outline"], self._tone,
                                          self.level.multiplier * (0.22 + 0.78 * flash))
                canvas.create_rectangle(x + 2, y + 2, x + width - 3, y + height - 3,
                                        outline=color, width=1 + 3 * self.level.multiplier * flash * self._flash_strength,
                                        fill="", tags=STATIC_TAG)
                if self.stage == "tension" and self.level != Intensity.LOW:
                    for offset in range(8, 89, 12):
                        canvas.create_line(x + width - offset, y + 2, x + width - offset + 6, y + 7,
                                           fill=color, width=2, tags=STATIC_TAG)
            self._signature = signature
        canvas.tag_raise(STATIC_TAG)
        if self._stamp is not None and now < self._until:
            elapsed = now - self._born
            phase = max(0.0, elapsed / (self._until - self._born))
            if not self._items:
                for _ in range(2):
                    self._items.append(canvas.create_text(0, 0, text=self._stamp, justify="center", tags=STAMP_TAG))
                self._painted = [None, None]
            center_x = x + surface.left + (width - surface.left) / 2
            center_y = y + surface.top + (height - surface.top) * 0.42
            shake = ((3 if self.level == Intensity.FULL else 1) * math.sin(elapsed * 75) * (1 - phase)
                     if self.level != Intensity.LOW and self._stamp in ("1", "LET'S GO!!", "CHECK OUTPUT") else 0)
            base = theme.RITUAL_FONT_SIZES[self.level.value]
            base *= {"3": 0.80, "2": 0.90}.get(self._stamp, 1.0)
            if len(self._stamp) > 3:
                fit_key = self._stamp, self.level, width, surface.left
                if self._font_fit_key != fit_key:
                    peak_size = math.ceil(base * 1.08)
                    lines = self._stamp.splitlines()
                    interpreter = getattr(canvas, "tk", None)
                    measured = (max(int(interpreter.call("font", "measure", (self._family, peak_size, "bold"), line))
                                    for line in lines) if interpreter is not None
                                else max(len(line) for line in lines) * peak_size * 1.4)
                    room = max(1, width - surface.left - 20)
                    self._font_fit_base = base * min(1.0, room / max(1, measured))
                    self._font_fit_key = fit_key
                base = self._font_fit_base
            size = round(base * (0.90 + 0.18 * math.sin(math.pi * phase)))
            size = max(1, size)
            fade = max(0, (phase - 0.45) / 0.55)
            for index, item in enumerate(self._items):
                coords = center_x + shake + (2 if index == 0 else 0), center_y + (2 if index == 0 else 0)
                color = theme.RITUAL_COLORS["build"] if index == 0 else self._tone
                if self._stamp == "2" and index == 1:
                    color = theme.RITUAL_COLORS["start"]
                elif self._stamp == "1" and index == 0:
                    color = theme.RITUAL_COLORS["white"]
                font = self._family, size, "bold"
                fill = theme.blend_color(color, surface.background, fade)
                previous = self._painted[index]
                if previous is None or coords != previous[0]:
                    canvas.coords(item, *coords)
                options = {}
                if previous is None or font != previous[1]:
                    options["font"] = font
                if previous is None or fill != previous[2]:
                    options["fill"] = fill
                if options:
                    canvas.itemconfigure(item, **options)
                self._painted[index] = coords, font, fill
            canvas.tag_raise(STAMP_TAG)
        elif self._stamp is not None:
            canvas.delete(STAMP_TAG)
            self._items.clear()
            self._painted.clear()
            self._stamp = None

    def finish_animation(self):
        canvas = self._canvas() if self._canvas is not None else None
        if canvas is not None:
            try:
                canvas.delete(STAMP_TAG)
            except TclError:
                pass
        self._items.clear()
        self._painted.clear()
        self._font_fit_key = None
        self._stamp = None
        self._until = self._flash_until = 0.0
        self.repaint()
        if self.stage is None and self._banner_text == "F5 · CHECK OUTPUT":
            self._status("")

    def complete_animation(self):
        # A completed/evicted facade must return drop/finale decoration to
        # ordinary editing, even for success arriving long after audio ends.
        if self.stage == "drop":
            self.stage = None
            if self._banner_text == "F5 · CONVERTED":
                self._status("")
        self.finish_animation()

    def clear(self):
        self.stage = None
        self.finish_animation()
        self._signature = None
        canvas = self._canvas() if self._canvas is not None else None
        if canvas is not None:
            try:
                canvas.delete(STATIC_TAG)
            except TclError:
                pass
        try:
            self._status("")
        except TclError:
            pass
        effects = self._effects() if self._effects is not None else None
        if effects is not None and effects.particles is not None:
            for key, reference in self._micro_effects.items():
                if reference() is not None and effects.effect_for(key) is reference():
                    effects.remove(key)
            self._micro_effects.clear()
            effects.particles.clear_owner(PARTICLE_OWNER)
            effects.refresh_visual()
        self._last_drop = -math.inf

    def close(self):
        self.clear()
        self._editor = self._effects = self._canvas = self._banner = None
