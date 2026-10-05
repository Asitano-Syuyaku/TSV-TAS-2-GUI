"""Canvas FX engine for the 1F FEVER layer (dopagaki3.md §11).

One `after` ticker per Editor runs only while effects exist. Effects use
closed-form motion (position as a function of time), so any frame can be
stepped deterministically with an injected clock. Effects draw on canvases
with the "fx" tag or tween widget options; they never focus, grab, or bind
input, and never touch document widgets' contents (T5).
"""

import math
import random
import time
import tkinter as tk


TICK_MS = 16
AMBIENT_MS = 40
TICK_BUDGET = 0.003  # Seconds per tick, shared with the ~3ms Table redraw (§11.1).
FLASH_GAP = 0.4      # Under 3 flashes per second (§12.3).
FX_TAG = "fx"
NEON = ("#ff2d8a", "#ffe600", "#19d3f0", "#39ff14", "#a35bff", "#ff8a1f")


def _rgb(color):
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def mix(first, second, amount):
    """Linear blend; Tk canvas items have no opacity, so fades blend to the ground."""
    amount = max(0.0, min(1.0, amount))
    a, b = _rgb(first), _rgb(second)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def ramp(colors, position):
    position = max(0.0, min(1.0, position)) * (len(colors) - 1)
    index = min(int(position), len(colors) - 2)
    return mix(colors[index], colors[index + 1], position - index)


def ease_out(value):
    return 1 - (1 - value) ** 3


def ease_out_back(value):
    c1 = 1.70158
    return 1 + (c1 + 1) * (value - 1) ** 3 + c1 * (value - 1) ** 2


def cycle(colors, now, period=0.06):
    return colors[int(now / period) % len(colors)]


class Effect:
    ambient = False
    particles = 0
    canvas = None

    def __init__(self, duration=None, delay=0.0):
        self.duration = duration
        self.delay = delay
        self.items = []
        self.engine = None
        self._started = False

    def begin(self, engine, now):
        self.engine = engine
        self.t0 = now + self.delay
        if self.delay <= 0:
            self._start(now)

    def _start(self, now):
        self._started = True
        self.setup()
        self.render(0.0, now)

    def update(self, now):
        if now < self.t0:
            return True
        if not self._started:
            self._start(now)
        if self.duration is None:
            self.render(0.0, now)
            return True
        progress = (now - self.t0) / self.duration
        if progress >= 1:
            return False
        self.render(progress, now)
        return True

    def setup(self):
        pass

    def render(self, progress, now):
        pass

    def finish(self):
        for canvas, item in self.items:
            try:
                canvas.delete(item)
            except tk.TclError:
                pass
        self.items.clear()

    def _item(self, canvas, kind, *coords, **options):
        item = getattr(canvas, "create_" + kind)(*coords, tags=(FX_TAG,), **options)
        self.items.append((canvas, item))
        return item


class FxEngine:
    def __init__(self, widget, motion=1.0, flashes=True, clock=time.perf_counter):
        self.widget = widget
        self.motion = motion
        self.flashes = flashes
        self.clock = clock
        self.scale = 1.0
        self._effects = []
        self._job = None
        self._closed = False
        self._overruns = 0
        self._last_flash = -math.inf

    @property
    def reduced(self):
        """Effects 0% (work focus): no motion, particles, shake or flash (§12.2)."""
        return self.motion <= 0

    @property
    def active(self):
        return tuple(self._effects)

    def add(self, effect):
        if self._closed:
            return None
        effect.begin(self, self.clock())
        self._effects.append(effect)
        self._schedule()
        return effect

    def stop(self, effect):
        if effect in self._effects:
            self._effects.remove(effect)
            effect.finish()

    def step(self, now=None):
        """Advance every effect to `now`; tests call this for frame-by-frame checks."""
        now = self.clock() if now is None else now
        for effect in tuple(self._effects):
            try:
                alive = effect.update(now)
            except tk.TclError:  # Its canvas was destroyed.
                alive = False
            if not alive and effect in self._effects:
                self._effects.remove(effect)
                effect.finish()

    def particle_count(self, requested, canvas, cap):
        if self.reduced:
            return 0
        alive = sum(effect.particles for effect in self._effects if effect.canvas is canvas)
        wanted = int(requested * max(0.15, self.motion) * self.scale)
        return max(0, min(wanted, cap - alive))

    def flash_allowed(self):
        now = self.clock()
        if not self.flashes or self.reduced or now - self._last_flash < FLASH_GAP:
            return False
        self._last_flash = now
        return True

    def close(self):
        self._closed = True
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        for effect in tuple(self._effects):
            self._effects.remove(effect)
            effect.finish()
        self.widget = None

    def _schedule(self):
        if self._job is not None or self._closed or not self._effects:
            return
        interval = AMBIENT_MS if all(effect.ambient for effect in self._effects) else TICK_MS
        self._job = self.widget.after(interval, self._tick)

    def _tick(self):
        self._job = None
        if self._closed:
            return
        started = time.perf_counter()
        self.step()
        if time.perf_counter() - started > TICK_BUDGET:
            self._overruns += 1
            if self._overruns >= 3:  # Degrade: fewer particles from now on.
                self.scale = max(0.25, self.scale / 2)
                self._overruns = 0
        else:
            self._overruns = 0
        self._schedule()


class Tween(Effect):
    """Animate widget options; setter(progress) gets 0..1 and always ends at 1."""

    def __init__(self, duration, setter, delay=0.0):
        super().__init__(duration, delay)
        self.setter = setter

    def render(self, progress, now):
        self.setter(progress)

    def finish(self):
        try:
            self.setter(1.0)
        except tk.TclError:
            pass
        super().finish()


class Ambient(Effect):
    """Runs until stopped; setter(now). Keeps the ticker at the slower ambient rate."""
    ambient = True

    def __init__(self, setter, cleanup=None):
        super().__init__(None)
        self.setter = setter
        self.cleanup = cleanup

    def render(self, progress, now):
        self.setter(now)

    def finish(self):
        if self.cleanup is not None:
            try:
                self.cleanup()
            except tk.TclError:
                pass
        super().finish()


class Punch(Effect):
    """Committed-cell frame: 1.18x to the cell, YELLOW -> CYAN -> ground (§7.2)."""

    def __init__(self, canvas, box, ground, rainbow=False, reduced=False):
        super().__init__(0.22)
        self.canvas, self.box, self.ground = canvas, box, ground
        self.rainbow, self.reduced = rainbow, reduced

    def setup(self):
        self.rect = self._item(self.canvas, "rectangle", *self.box, outline=NEON[1], width=3)

    def render(self, progress, now):
        x1, y1, x2, y2 = self.box
        grow = 0.0 if self.reduced else 0.18 * (1 - ease_out(min(1, progress / 0.55)))
        dx, dy = (x2 - x1) * grow / 2, (y2 - y1) * grow / 2
        if progress < 0.55:
            color = cycle(NEON, now) if self.rainbow else mix(NEON[1], NEON[2], progress / 0.55)
        else:
            color = mix(NEON[2], self.ground, (progress - 0.55) / 0.45)
        self.canvas.coords(self.rect, x1 - dx, y1 - dy, x2 + dx, y2 + dy)
        self.canvas.itemconfigure(self.rect, outline=color)


class LockOn(Effect):
    """New active cell's corners snap in from 1.4x (§7.2); the grid keeps the static ones."""

    def __init__(self, canvas, box, color, arm=6):
        super().__init__(0.09)
        self.canvas, self.box, self.color, self.arm = canvas, box, color, arm

    def setup(self):
        self.lines = [self._item(self.canvas, "line", 0, 0, 0, 0, 0, 0, fill=self.color, width=2)
                      for _ in range(4)]

    def render(self, progress, now):
        x1, y1, x2, y2 = self.box
        grow = 0.4 * (1 - ease_out_back(progress))
        dx, dy = (x2 - x1) * grow / 2, (y2 - y1) * grow / 2
        x1, y1, x2, y2 = x1 - dx, y1 - dy, x2 + dx, y2 + dy
        arm = self.arm
        for line, (x, y, sx, sy) in zip(self.lines, ((x1, y1, 1, 1), (x2, y1, -1, 1),
                                                    (x1, y2, 1, -1), (x2, y2, -1, -1))):
            self.canvas.coords(line, x + sx * arm, y, x, y, x, y + sy * arm)


class Sparks(Effect):
    """Line sparks leaving the committed cell in the move direction (§7.2)."""

    def __init__(self, canvas, origin, direction, count, ground, stars=False, seed=None):
        super().__init__(0.42)
        self.canvas, self.origin, self.direction = canvas, origin, direction
        self.count, self.ground, self.stars = count, ground, stars
        self.particles = count
        self.random = random.Random(seed)

    def setup(self):
        if self.direction is None:
            base, spread = -math.pi / 2, math.pi / 3
        else:
            rows, columns = self.direction
            base, spread = math.atan2(rows, columns), math.radians(35)
        self.sparks = []
        for index in range(self.count):
            angle = base + self.random.uniform(-spread, spread)
            speed = self.random.uniform(180, 420)
            star = self.stars and index % 3 == 0
            color = self.random.choice(NEON)
            kind = "polygon" if star else "line"
            coords = (0, 0, 0, 0, 0, 0) if star else (0, 0, 0, 0)
            options = {"fill": color} if star else {"fill": color, "width": 2}
            if star:
                options["outline"] = ""
            item = self._item(self.canvas, kind, *coords, **options)
            self.sparks.append((item, math.cos(angle) * speed, math.sin(angle) * speed,
                                color, star))

    def render(self, progress, now):
        elapsed = progress * self.duration
        x0, y0 = self.origin
        fade = max(0.0, (progress - 0.4) / 0.6)
        for item, vx, vy, color, star in self.sparks:
            x = x0 + vx * elapsed
            y = y0 + vy * elapsed + 300 * elapsed ** 2
            shade = mix(color, self.ground, fade)
            if star:
                size = 4
                points = []
                for corner in range(10):
                    radius = size if corner % 2 == 0 else size * 0.45
                    angle = corner * math.pi / 5 - math.pi / 2
                    points += [x + math.cos(angle) * radius, y + math.sin(angle) * radius]
                self.canvas.coords(item, *points)
                self.canvas.itemconfigure(item, fill=shade)
            else:
                tail = 0.03
                self.canvas.coords(item, x, y, x - vx * tail, y - vy * tail)
                self.canvas.itemconfigure(item, fill=shade)


class Burst(Effect):
    """Confetti / coins / stars flung upward, then falling (§11.4)."""

    def __init__(self, canvas, origin, count, ground, kinds=("confetti", "star"),
                 power=1.0, duration=1.0, seed=None):
        super().__init__(duration)
        self.canvas, self.origin, self.count, self.ground = canvas, origin, count, ground
        self.kinds, self.power = kinds, power
        self.particles = count
        self.random = random.Random(seed)

    def setup(self):
        self.bits = []
        for index in range(self.count):
            kind = self.kinds[index % len(self.kinds)]
            angle = self.random.uniform(-math.pi * 0.85, -math.pi * 0.15)
            speed = self.random.uniform(220, 520) * self.power
            color = "#ffc21a" if kind == "coin" else self.random.choice(NEON)
            size = self.random.uniform(4, 7)
            if kind == "coin":
                item = self._item(self.canvas, "oval", 0, 0, 0, 0, fill=color, outline="#8a5200")
            else:
                item = self._item(self.canvas, "polygon", 0, 0, 0, 0, 0, 0, fill=color, outline="")
            self.bits.append((item, kind, math.cos(angle) * speed, math.sin(angle) * speed,
                              color, size, self.random.uniform(-9, 9),
                              self.random.uniform(6, 14)))

    def render(self, progress, now):
        elapsed = progress * self.duration
        x0, y0 = self.origin
        fade = max(0.0, (progress - 0.75) / 0.25)
        for item, kind, vx, vy, color, size, spin, flip in self.bits:
            x = x0 + vx * elapsed
            y = y0 + vy * elapsed + 450 * elapsed ** 2
            shade = mix(color, self.ground, fade)
            if kind == "coin":
                width = abs(math.cos(flip * elapsed)) * size + 1
                self.canvas.coords(item, x - width, y - size, x + width, y + size)
                self.canvas.itemconfigure(item, fill=shade)
                continue
            angle = spin * elapsed
            if kind == "star":
                points = []
                for corner in range(10):
                    radius = size if corner % 2 == 0 else size * 0.45
                    theta = corner * math.pi / 5 - math.pi / 2 + angle
                    points += [x + math.cos(theta) * radius, y + math.sin(theta) * radius]
            else:  # Confetti: a flipping rectangle.
                squash = abs(math.cos(flip * elapsed))
                cos, sin = math.cos(angle), math.sin(angle)
                points = []
                for px, py in ((-size, -size * 0.45 * squash), (size, -size * 0.45 * squash),
                               (size, size * 0.45 * squash), (-size, size * 0.45 * squash)):
                    points += [x + px * cos - py * sin, y + px * sin + py * cos]
            self.canvas.coords(item, *points)
            self.canvas.itemconfigure(item, fill=shade)


class Pop(Effect):
    """Floating "+N" (§7.2): rises 28px and sinks into the ground."""

    def __init__(self, canvas, position, text, color, font, ground, rise=28,
                 duration=0.6, delay=0.03, anchor="e"):
        super().__init__(duration, delay)
        self.canvas, self.position, self.text, self.color = canvas, position, text, color
        self.font, self.ground, self.rise, self.anchor = font, ground, rise, anchor

    def setup(self):
        self.label = self._item(self.canvas, "text", *self.position, text=self.text,
                                fill=self.color, font=self.font, anchor=self.anchor)

    def render(self, progress, now):
        x, y = self.position
        self.canvas.coords(self.label, x, y - self.rise * ease_out(progress))
        self.canvas.itemconfigure(
            self.label, fill=mix(self.color, self.ground, max(0.0, (progress - 0.7) / 0.3)))


class Ring(Effect):
    def __init__(self, canvas, center, radii, color, ground, width=3, duration=0.3):
        super().__init__(duration)
        self.canvas, self.center, self.radii = canvas, center, radii
        self.color, self.ground, self.width = color, ground, width

    def setup(self):
        self.oval = self._item(self.canvas, "oval", 0, 0, 0, 0, outline=self.color,
                               width=self.width)

    def render(self, progress, now):
        x, y = self.center
        start, end = self.radii
        radius = start + (end - start) * ease_out(progress)
        self.canvas.coords(self.oval, x - radius, y - radius, x + radius, y + radius)
        self.canvas.itemconfigure(self.oval, outline=mix(self.color, self.ground, progress),
                                  width=max(1, round(self.width * (1 - progress * 0.6))))


SLAM = ((0.0, 2.8), (0.09, 0.88), (0.15, 1.08), (0.21, 1.0), (0.82, 1.02), (1.0, 1.45))


def slam_scale(progress):
    for (start, low), (end, high) in zip(SLAM, SLAM[1:]):
        if progress <= end:
            return low + (high - low) * (progress - start) / (end - start)
    return SLAM[-1][1]


class Shout(Effect):
    """Outlined slam text (§7.4): 2.8 -> 0.88 -> 1.08 -> 1, hold, 1.45x sink."""

    OUTLINE = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))

    def __init__(self, canvas, center, text, fonts, pixels, color, ink, ground,
                 angle=-6, hold=0.52, rainbow=False, reduced=False):
        super().__init__(hold + 0.36)
        self.canvas, self.center, self.text, self.fonts = canvas, center, text, fonts
        self.pixels, self.color, self.ink, self.ground = pixels, color, ink, ground
        self.angle, self.rainbow, self.reduced = angle, rainbow, reduced

    def setup(self):
        options = {"text": self.text, "angle": self.angle, "anchor": "center"}
        self.outline = [self._item(self.canvas, "text", 0, 0, fill=self.ground, **options)
                        for _ in self.OUTLINE]
        self.shadow = self._item(self.canvas, "text", 0, 0, fill=self.ground, **options)
        self.face = self._item(self.canvas, "text", 0, 0, fill=self.ground, **options)

    def render(self, progress, now):
        if self.reduced:
            scale = 1.0
            presence = min(1.0, progress / 0.15) if progress < 0.8 else (1 - progress) / 0.2
        else:
            scale = slam_scale(progress)
            presence = (progress / 0.09 if progress < 0.09 else
                        1.0 if progress < 0.82 else (1 - progress) / 0.18)
        font = self.fonts.get("shout", self.pixels * scale)
        offset = max(1, round(self.pixels * 0.06 * scale))
        x, y = self.center
        face = cycle(NEON, now) if self.rainbow else self.color
        for item, (sx, sy) in zip(self.outline, self.OUTLINE):
            self.canvas.coords(item, x + sx * offset, y + sy * offset)
            self.canvas.itemconfigure(item, font=font, fill=mix(self.ground, self.ink, presence))
        shadow = offset + 2
        self.canvas.coords(self.shadow, x + shadow, y + shadow)
        self.canvas.itemconfigure(self.shadow, font=font, fill=mix(self.ground, self.ink, presence))
        self.canvas.coords(self.face, x, y)
        self.canvas.itemconfigure(self.face, font=font, fill=mix(self.ground, face, presence))


class Shake(Effect):
    """Shift a canvas *view* (not its items) with decaying jitter (§12.3: <=3px)."""

    def __init__(self, canvas, power=1.0, duration=0.26, seed=None):
        super().__init__(duration)
        self.canvas, self.power = canvas, power
        self.random = random.Random(seed)
        self.offset = (0, 0)

    def setup(self):
        self.canvas.configure(xscrollincrement=1, yscrollincrement=1)

    def _move_to(self, x, y):
        dx, dy = x - self.offset[0], y - self.offset[1]
        if dx:
            self.canvas.xview_scroll(dx, "units")
        if dy:
            self.canvas.yview_scroll(dy, "units")
        self.offset = (x, y)

    def render(self, progress, now):
        amplitude = 3 * self.power * (1 - progress)
        self._move_to(round(self.random.uniform(-amplitude, amplitude)),
                      round(self.random.uniform(-amplitude, amplitude)))

    def finish(self):
        try:
            self._move_to(0, 0)
        except tk.TclError:
            pass
        super().finish()
