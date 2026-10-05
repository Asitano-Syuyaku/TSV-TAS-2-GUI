"""F8 COVER (dopagaki3.md §9.4): the only full pachinko sequence.

The wait it dramatizes is the real conversion + FTP run: the caption shows
real elapsed seconds and nothing claims a result before the parent Converter
reports one. The card holds facts only (output name, format, destination);
its stars mark steps that already happened. The COVER never takes focus: any
key closes it through a bindtag placed in front of the focused widget's own
tags, and that key continues to its normal bindings (T5).
"""

import math
import tkinter as tk

from ..theme import COLORS, px
from .fx import Ambient, Burst, Later, Shout, Tween, NEON, cycle, ease_out, ease_out_back, mix
from .outcome import FAILED, SEND_CONFIRMED, SEND_UNVERIFIED
from .words import COMMON


VOID = "#05010f"
STRIPE_RED, STRIPE_YELLOW = "#e8202a", "#ffd400"
BAND = 26
STRIPE = 40
PRE_PHASE = 1.2
CLOSE_AFTER = {SEND_CONFIRMED: 1.6, SEND_UNVERIFIED: 2.4, FAILED: 0.5}
CARD = {SEND_CONFIRMED: ("#2a1a5e", "#ffd400"), SEND_UNVERIFIED: ("#24180a", "#ff8a1f")}
RAYS = ("#ff2d8a", "#111111", "#ffd400", "#111111", "#19d3f0", "#111111", "#a35bff", "#111111")


class SendCover:
    def __init__(self, editor, fonts, engine, words, started, clock, on_closed, sfx=None):
        self.editor, self.fonts, self.engine, self.words = editor, fonts, engine, words
        self.sfx = sfx or (lambda name, delay=0.0: None)
        self.started, self.clock, self.on_closed = started, clock, on_closed
        self.outcome = None
        self.closed = False
        self._effects = []
        host = editor._rim
        self.canvas = canvas = tk.Canvas(host, background=VOID, highlightthickness=0,
                                         borderwidth=0, takefocus=False)
        inset = int(host.cget("highlightthickness"))
        canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.band = px(BAND)
        self.width = max(200, host.winfo_width() - 2 * inset)
        self.height = max(160, host.winfo_height() - 2 * inset)
        # Origin at the canvas center: a resize keeps everything centered by moving
        # the view, not the items. Only the edge bands follow the new height.
        self._recenter(self.width, self.height)
        canvas.bind("<Configure>", self._resized)
        canvas.bind("<Button-1>", lambda event: self.close(immediate=True))
        self._install_key_tag()
        self._build_pre()

    def _recenter(self, width, height):
        self.canvas.configure(scrollregion=(-width / 2, -height / 2, width / 2, height / 2))
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def _resized(self, event):
        if self.closed or (event.width, event.height) == (self.width, self.height):
            return
        shift = (event.height - self.height) / 2
        self.canvas.move("band_top", 0, -shift)
        self.canvas.move("band_bottom", 0, shift)
        self.width, self.height = event.width, event.height
        self._recenter(event.width, event.height)

    # Input: any key closes; the key still reaches its widget -------------------

    def _install_key_tag(self):
        self._tag = f"DopaCover{id(self)}"
        # Deferred: never edit bindtags while Tk is still dispatching this key.
        self._key_command = self.editor.bind_class(
            self._tag, "<KeyPress>",
            lambda event: self.editor.after_idle(lambda: self.close(immediate=True)))
        self._tagged = []
        grid = getattr(self.editor, "table_grid", None)
        candidates = [self.editor.focus_get(), self.editor.text,
                      grid.canvas if grid is not None else None,
                      getattr(grid, "_editor", None), self.editor.frame_entry]
        for widget in candidates:
            if widget is None or widget in self._tagged:
                continue
            try:
                tags = widget.bindtags()
            except tk.TclError:
                continue
            widget.bindtags((self._tag,) + tuple(tags))
            self._tagged.append(widget)

    def _remove_key_tag(self):
        for widget in self._tagged:
            try:
                if widget.winfo_exists():
                    widget.bindtags(tuple(tag for tag in widget.bindtags() if tag != self._tag))
            except tk.TclError:
                pass
        self._tagged = []
        try:
            # bind_class registers on the root (and lists it there for cleanup).
            root = self.editor._root()
            root.unbind_class(self._tag, "<KeyPress>")
            root.deletecommand(self._key_command)
        except tk.TclError:
            pass

    # Phases ---------------------------------------------------------------------

    def _add(self, effect):
        effect = self.engine.add(effect)
        if effect is not None:
            self._effects.append(effect)
        return effect

    @property
    def center(self):
        return 0.0, 0.0

    def _build_pre(self):
        """激アツ: stripe bands, one slam, and the factual running caption."""
        canvas, (cx, cy) = self.canvas, self.center
        band, stripe = self.band, px(STRIPE)
        half, reach = self.height / 2, self.width + px(400)  # Wide enough for a later resize.
        for top, tag in ((-half, "band_top"), (half - band, "band_bottom")):
            canvas.create_rectangle(-reach, top, reach, top + band,
                                    fill=STRIPE_RED, outline="", tags=("pre", "band", tag))
            for x in range(-reach - stripe, reach + stripe, stripe):
                canvas.create_polygon(x, top + band, x + band, top, x + band + stripe / 2, top,
                                      x + stripe / 2, top + band, fill=STRIPE_YELLOW, outline="",
                                      tags=("pre", "band", "stripes", tag))
        # 120ms: bands slide in from the edges instead of an (unavailable) alpha fade.
        canvas.move("band_top", 0, -band)
        canvas.move("band_bottom", 0, band)
        offsets = {"band": float(band)}  # Current displacement off-screen.

        def slide(progress):
            target = band * (1 - ease_out(progress))
            delta = offsets["band"] - target
            canvas.move("band_top", 0, delta)
            canvas.move("band_bottom", 0, -delta)
            offsets["band"] = target

        self._add(Tween(0.12, slide))
        self.sfx("alarm")  # Once; then silence is the 溜め (§9.4).
        self._add(Shout(canvas, (cx, cy - px(18)), self.words["gekiatsu"], self.fonts, 64,
                        COLORS["text"], COLORS["on_neon"], VOID, angle=-8, hold=0.85,
                        reduced=self.engine.reduced))
        self.caption = canvas.create_text(cx, cy + px(58), text="", tags=("pre",),
                                          font=self.fonts.get("caps", 14),
                                          fill=COLORS["muted_text"])
        self.orb = None
        state = {"stripes": 0.0, "phase": "bands"}

        def tick(now):
            elapsed = max(0.0, self.clock() - self.started)  # Real seconds since start.
            canvas.itemconfigure(self.caption, text=self.words["sending"].format(s=elapsed))
            if state["phase"] == "bands":
                offset = (now * px(60)) % stripe
                canvas.move("stripes", offset - state["stripes"], 0)
                state["stripes"] = offset
                if elapsed >= PRE_PHASE:
                    state["phase"] = "orb"
                    self._retract_bands()
            elif self.orb is not None:
                scale = 1.0 + 0.4 * math.sin(now * 2 * math.pi / 0.52)
                for item, radius in self.orb:
                    canvas.coords(item, cx - radius * scale, cy - radius * scale,
                                  cx + radius * scale, cy + radius * scale)

        self._pre = self._add(Ambient(tick))

    def _retract_bands(self):
        """溜め: the bands leave; one pulsing orb in the dark."""
        canvas, (cx, cy) = self.canvas, self.center
        moved = {"value": 0.0}

        def retract(progress):
            target = (self.band + px(4)) * ease_out(progress)
            delta = target - moved["value"]
            canvas.move("band_top", 0, -delta)
            canvas.move("band_bottom", 0, delta)
            moved["value"] = target

        self._add(Tween(0.2, retract))
        glow = canvas.create_oval(cx, cy, cx, cy, outline="#7cff4f", width=3, tags=("pre",))
        core = canvas.create_oval(cx, cy, cx, cy, fill="#bfffd0", outline="", tags=("pre",))
        self.orb = ((glow, px(20)), (core, px(11)))

    def resolve(self, outcome, output_name, format_label):
        """The parent Converter reported a result; show exactly that result."""
        if self.closed or self.outcome is not None:
            return
        self.outcome = outcome
        if self._pre is not None:
            self.engine.stop(self._pre)
            self._pre = None
        if outcome == FAILED:
            self._collapse()
        else:
            self.canvas.delete("pre")
            self._result(outcome, output_name, format_label)
        self._add(Later(CLOSE_AFTER[outcome], self.close))

    def _collapse(self):
        """Failure: the bands squeeze to the middle and おしい! bounces."""
        canvas, (cx, cy) = self.canvas, self.center
        canvas.delete(self.caption)
        for item, _ in self.orb or ():
            canvas.delete(item)
        moved = {"value": 0.0}

        def squeeze(progress):
            target = (self.height / 2 - self.band) * ease_out(progress)
            delta = target - moved["value"]
            canvas.move("band_top", 0, delta)
            canvas.move("band_bottom", 0, -delta)
            moved["value"] = target

        self._add(Tween(0.3, squeeze))
        self.sfx("oshii")
        self._add(Shout(canvas, (cx, cy), self.words["oshii"], self.fonts, 48,
                        COLORS["neon_orange"], COLORS["on_neon"], VOID, angle=-6, hold=0.3,
                        reduced=self.engine.reduced))

    def _result(self, outcome, output_name, format_label):
        canvas, (cx, cy) = self.canvas, self.center
        confirmed = outcome == SEND_CONFIRMED
        if confirmed:
            self._add(Later(0.08, self._explode))
            self.sfx("kyuin", delay=0.08)
        else:
            self.sfx("chime")
            self._add(Shout(canvas, (cx, -self.height * 0.37), self.words["sent"], self.fonts, 54,
                            COLORS["text"], COLORS["on_neon"], VOID, angle=-6, hold=1.3,
                            rainbow=True, reduced=self.engine.reduced))
            self._add(Shout(canvas, (cx, self.height * 0.37), self.words["kyuin"], self.fonts, 30,
                            COLORS["text"], COLORS["on_neon"], VOID, angle=-4, hold=0.7,
                            reduced=self.engine.reduced))
        fill, edge = CARD[outcome]
        width, height = px(340), px(196)
        top = cy - height / 2
        canvas.create_rectangle(cx - width / 2, top, cx + width / 2, top + height, fill=fill,
                                outline=edge, width=4, tags=("card",))
        caps, small = self.fonts.get("caps", 11), self.fonts.get("caps", 12, bold=False)
        lines = []
        if not confirmed:
            lines.append((self.words["built"], self.fonts.get("shout", 22), COLORS["neon_orange"]))
        lines += [(self.words["output"], caps, COLORS["muted_text"]),
                  (output_name, self.fonts.get("meter", 17), COLORS["neon_yellow"]),
                  (format_label, small, COLORS["text"]),
                  (f"{self.words['destination']}  " + COMMON["remote"].format(name=output_name),
                   small, COLORS["text"])]
        if not confirmed:
            lines.append((self.words["send_unverified"], small, COLORS["neon_orange"]))
        y = top + px(20)
        for index, (text, font, color) in enumerate(lines):
            canvas.create_text(cx, y, text=text, font=font, fill=color, tags=("card",))
            y += px(30) if index == 0 and not confirmed else px(22) if font is not caps else px(17)
        star_y = top + height - px(22)
        self.stars = []
        for index, step in enumerate(COMMON["steps"]):
            x = cx + (index - 1) * px(104)
            label = canvas.create_text(x - px(8), star_y, text=step, anchor="e", font=caps,
                                       fill=COLORS["muted_text"], tags=("card",))
            star = canvas.create_text(x - px(4), star_y, text=COMMON["star_off"], anchor="w",
                                      font=self.fonts.get("shout", 16), fill=COLORS["muted_text"],
                                      tags=("card",))
            self.stars.append((label, star))
        # The card falls in (380ms), then each already-true step lights (170ms apart).
        drop = self.height / 2 + height
        fallen = {"value": -drop}
        canvas.move("card", 0, fallen["value"])

        def fall(progress):
            target = -drop * (1 - ease_out_back(progress))
            canvas.move("card", 0, target - fallen["value"])
            fallen["value"] = target

        self._add(Tween(0.38, fall, delay=0.08))
        lit = 3 if confirmed else 2  # Unverified: SEND stays ☆ (§9.4).
        for index in range(lit):
            self._add(Later(0.46 + 0.17 * index, lambda item=self.stars[index]: self._light(item)))

    def _light(self, item):
        label, star = item
        self.sfx(f"star{self.stars.index(item)}")
        self.canvas.itemconfigure(label, fill=COLORS["text"])
        self.canvas.itemconfigure(star, text=COMMON["star"], fill="#ffd400")
        if not self.engine.reduced:
            self._add(Tween(0.16, lambda progress: self.canvas.itemconfigure(
                star, font=self.fonts.get("shout", 16 + 14 * (1 - ease_out(progress))))))

    def _explode(self):
        """確定: rays burst from the center, then coins and confetti."""
        if self.engine.reduced:
            return
        canvas, (cx, cy) = self.canvas, self.center
        radius = math.hypot(self.width, self.height)
        rays = [canvas.create_polygon(cx, cy, cx, cy, cx, cy, outline="",
                                      fill=RAYS[index % len(RAYS)], tags=("rays",))
                for index in range(40)]
        canvas.tag_lower("rays")
        born = self.clock()

        def turn(now):
            grow = min(1.0, (self.clock() - born) / 0.26)
            reach = radius * (0.1 + 0.9 * ease_out(grow))
            spin = 2 * math.pi * (now / 6.0 % 1)
            for index, ray in enumerate(rays):
                a, b = spin + index * math.pi / 20, spin + (index + 1) * math.pi / 20
                canvas.coords(ray, cx, cy, cx + math.cos(a) * reach, cy + math.sin(a) * reach,
                              cx + math.cos(b) * reach, cy + math.sin(b) * reach)

        self._add(Ambient(turn))
        count = self.engine.particle_count(70, canvas, 160)
        if count:
            self._add(Burst(canvas, (cx, cy), count, VOID, kinds=("coin", "confetti", "star"),
                            power=1.3, duration=1.2))
        canvas.tag_raise("card")  # Facts stay readable above every particle.

    # Closing --------------------------------------------------------------------

    def close(self, immediate=False):
        """Input closes at once; a timed close wipes over 260ms, then reveals the body."""
        if self.closed:
            return
        if immediate or self.engine.reduced:
            self._finish()
            return
        canvas, (cx, cy) = self.canvas, self.center
        iris = canvas.create_oval(cx, cy, cx, cy, fill=VOID, outline="")
        reach = math.hypot(self.width, self.height) / 2 + 4

        def wipe(progress):
            radius = reach * ease_out(progress)
            canvas.coords(iris, cx - radius, cy - radius, cx + radius, cy + radius)
            if progress >= 1:
                self._finish()

        self._add(Tween(0.26, wipe))

    def _finish(self):
        if self.closed:
            return
        self.closed = True
        for effect in self._effects:
            self.engine.stop(effect)
        self._effects = []
        self._remove_key_tag()
        try:
            self.canvas.destroy()
        except tk.TclError:
            pass
        callback, self.on_closed = self.on_closed, None
        if callback is not None:
            callback(self)
