"""HUD font roles (dopagaki3.md §4.2): OS families only, nothing bundled."""

from tkinter import font as tkfont

from ..theme import UI_SCALE


ROLES = {
    "meter": ("Bahnschrift", "Consolas", "DejaVu Sans Mono"),
    # Meiryo UI renders Japanese and Latin evenly on Windows; Latin-only faces
    # make Tk fall back to a heavy Japanese font for state words (readability fix).
    "shout": ("Meiryo UI", "Yu Gothic UI", "Noto Sans CJK JP", "IPAGothic"),
    "caps": ("Meiryo UI", "Segoe UI", "DejaVu Sans"),
}
FALLBACK = {"meter": "TkFixedFont", "shout": "TkDefaultFont", "caps": "TkDefaultFont"}


class FontBook:
    """Per-Editor cache. Sizes are pixels; fonts are created once, never per frame."""

    def __init__(self, master):
        self._master = master
        available = set(tkfont.families(master))
        self.families = {}
        for role, candidates in ROLES.items():
            family = next((name for name in candidates if name in available), None)
            if family is None:
                family = tkfont.nametofont(FALLBACK[role], root=master).actual("family")
            self.families[role] = family
        self._cache = {}

    def get(self, role, pixels, bold=True):
        pixels = max(6, int(round(pixels * UI_SCALE["value"])))  # Sizes are 96-DPI pixels.
        key = role, pixels, bold
        found = self._cache.get(key)
        if found is None:
            found = self._cache[key] = tkfont.Font(
                root=self._master, family=self.families[role], size=-pixels,
                weight="bold" if bold else "normal")
        return found

    def clear(self):
        # Called on the Tk thread at Editor destroy (Tk objects die there).
        self._cache.clear()
