"""Bounded, asset-free Canvas particles with analytic elapsed-time motion."""

import math
import random
import weakref
from tkinter import TclError

from .hype import curve
from .theme import PARTICLE_COLORS, blend_color


CAPS = {"OFF": 0, "LOW": 30, "MID": 90, "FULL": 180}
HARD_CEILING = 260
KINDS = ("square", "dot", "diamond", "spark")
COUNTS = {
    "commit": ((1, 2), (3, 5), (6, 10)),
    "palette": ((1, 3), (4, 7), (8, 14)),
    "stick": ((1, 3), (4, 7), (8, 12)),
    "page": ((0, 1), (1, 3), (2, 5)),
    "jump": ((1, 2), (3, 5), (6, 9)),
    "operation": ((1, 3), (4, 7), (8, 14)),
}


def spawn_count(event, level, heat):
    if level.value == "OFF":
        return 0
    if event == "cell":
        if heat < 0.65 or level.value == "LOW":
            return 0
        return 1 + int(level.value == "FULL" and heat >= 0.85)
    low, high = COUNTS[event][{"LOW": 0, "MID": 1, "FULL": 2}[level.value]]
    return low + int((high - low) * curve(heat) + 0.5)


class Particle:
    __slots__ = ("x", "y", "origin_x", "origin_y", "vx", "vy", "born_at",
                 "lifetime", "size", "kind", "color", "gravity", "surface",
                 "item", "shade", "__weakref__")

    def __init__(self, surface, x, y, vx, vy, born_at, lifetime, size, kind, color):
        self.surface = surface
        self.x = self.origin_x = x
        self.y = self.origin_y = y
        self.vx, self.vy = vx, vy
        self.born_at, self.lifetime = born_at, lifetime
        self.size, self.kind, self.color = size, kind, color
        self.gravity = 65.0
        self.item, self.shade = None, -1


class Surface:
    def __init__(self, canvas, left, top, background, *, dark):
        self.canvas = weakref.ref(canvas)
        self.left, self.top = left, top
        self.background = background
        self.colors = PARTICLE_COLORS["dark" if dark else "light"]
        self.signature = None

    def viewport(self):
        canvas = self.canvas()
        if canvas is None or not canvas.winfo_exists() or not canvas.winfo_ismapped():
            return None
        return (canvas.canvasx(0), canvas.canvasy(0), canvas.winfo_width(), canvas.winfo_height())


class ParticleSystem:
    """One global list/cap across four weak Canvas surfaces.

    Normal grid redraw deletes only its own tag; these use dopagaki_particle.
    Scroll/resize cancels particles from the changed surface. Plot adapters
    invalidate/repaint particle IDs around their inherited delete-all redraw.
    No widgets, images, callbacks, document references or animation history.
    """

    def __init__(self, *, rng=None):
        self.particles = []
        self.surfaces = {}
        self.rng = random.Random() if rng is None else rng
        self._last_render = -math.inf

    def register(self, name, canvas, *, left=0, top=0, background="#19233b", dark=True):
        if name not in self.surfaces and len(self.surfaces) >= 4:
            raise ValueError("at most four particle surfaces")
        self.clear_surface(name)
        self.surfaces[name] = Surface(canvas, left, top, background, dark=dark)

    def _viewport(self, name):
        surface = self.surfaces[name]
        try:
            signature = surface.viewport()
        except TclError:
            signature = None
        if signature != surface.signature:
            self.clear_surface(name)
            surface.signature = signature
        return signature

    def sync_viewport(self, name):
        self._viewport(name)

    def raise_surface(self, name):
        canvas = self.surfaces[name].canvas()
        if canvas is not None:
            try:
                canvas.tag_raise("dopagaki_particle")
            except TclError:
                pass

    def spawn(self, name, origin, count, level, heat, now, *, direction=(0.8, -1.0)):
        self.expire(now)
        if name not in self.surfaces or self._viewport(name) is None:
            return 0
        available = min(CAPS[level.value], HARD_CEILING) - len(self.particles)
        count = min(max(0, int(count)), max(0, available))
        surface = self.surfaces[name]
        intensity = level.multiplier * curve(heat)
        angle = math.atan2(direction[1], direction[0])
        for _ in range(count):
            heading = angle + self.rng.uniform(-0.65, 0.65)
            speed = (35 + 90 * intensity) * self.rng.uniform(0.75, 1.20)
            color = blend_color(surface.background, self.rng.choice(surface.colors), 0.38 + 0.62 * intensity)
            self.particles.append(Particle(
                surface, *origin, math.cos(heading) * speed, math.sin(heading) * speed, now,
                self.rng.uniform(0.22, 0.40 + 0.12 * intensity),
                self.rng.uniform(1.0, 1.8 + 1.7 * intensity), self.rng.choice(KINDS), color))
        return count

    @property
    def deadline(self):
        return max((particle.born_at + particle.lifetime for particle in self.particles), default=0.0)

    @staticmethod
    def _delete(particle):
        canvas = particle.surface.canvas()
        if particle.item is not None and canvas is not None:
            try:
                canvas.delete(particle.item)
            except TclError:
                pass
        particle.item = None

    def expire(self, now):
        alive = []
        for particle in self.particles:
            if now >= particle.born_at + particle.lifetime or particle.surface.canvas() is None:
                self._delete(particle)
            else:
                alive.append(particle)
        self.particles[:] = alive

    def render(self, now, *, only=None):
        viewports = {surface: self._viewport(name) for name, surface in self.surfaces.items()}
        self.expire(now)
        # Coalesced events can render the batch multiple times within one Tk
        # frame. Existing positions need not be sent to Tcl again within 12ms;
        # new items still appear immediately. A late tick jumps analytically.
        full = now - self._last_render >= 0.012
        if full and only is None:
            self._last_render = now
        alive = []
        target = self.surfaces.get(only) if only is not None else None
        for particle in self.particles:
            surface = particle.surface
            viewport = viewports[surface]
            if viewport is None:
                self._delete(particle)
                continue
            if only is not None and surface is not target:
                alive.append(particle)
                continue
            if not full and particle.item is not None and only is None:
                alive.append(particle)
                continue
            age = max(0.0, now - particle.born_at)
            particle.x = particle.origin_x + particle.vx * age
            particle.y = particle.origin_y + particle.vy * age + 0.5 * particle.gravity * age ** 2
            x, y, size = particle.x, particle.y, particle.size * (1 - 0.35 * age / particle.lifetime)
            x0, y0, width, height = viewport
            if not (x0 + surface.left + size <= x <= x0 + width - size and
                    y0 + surface.top + size <= y <= y0 + height - size):
                self._delete(particle)
                continue
            canvas = surface.canvas()
            shade = min(12, int(age / particle.lifetime * 12))
            if particle.item is None or particle.shade != shade:
                color = blend_color(particle.color, surface.background, shade / 12)
            if particle.kind == "diamond":
                coords = (x, y - size, x + size, y, x, y + size, x - size, y)
                create = canvas.create_polygon
            elif particle.kind == "spark":
                coords = (x - particle.vx * 0.025, y - particle.vy * 0.025, x, y)
                create = canvas.create_line
            else:
                coords = (x - size, y - size, x + size, y + size)
                create = canvas.create_rectangle if particle.kind == "square" else canvas.create_oval
            try:
                if particle.item is None:
                    options = dict(fill=color, tags="dopagaki_particle")
                    options.update(width=1.5) if particle.kind == "spark" else options.update(outline="")
                    particle.item = create(*coords, **options)
                else:
                    canvas.coords(particle.item, *coords)
                    if particle.shade != shade:
                        canvas.itemconfigure(particle.item, fill=color)
                particle.shade = shade
            except TclError:
                self._delete(particle)
                continue
            alive.append(particle)
        self.particles[:] = alive

    def invalidate(self, name):
        surface = self.surfaces.get(name)
        for particle in self.particles:
            if particle.surface is surface:
                self._delete(particle)

    def clear_surface(self, name):
        surface = self.surfaces.get(name)
        alive = []
        for particle in self.particles:
            if particle.surface is surface:
                self._delete(particle)
            else:
                alive.append(particle)
        self.particles[:] = alive

    def clear(self):
        for particle in self.particles:
            self._delete(particle)
        self.particles.clear()
        self._last_render = -math.inf

    def close(self):
        self.clear()
        self.surfaces.clear()
        self.rng = None
