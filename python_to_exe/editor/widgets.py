"""Tk widget factories for the Editor skin; import lazily (needs a Tk display)."""

from tkinter import ttk

from .theme import COLORS


_ELEMENTS = {"vertical": ("trough", "thumb"), "horizontal": ("trough", "thumb")}


def _style_name(orient):
    return f"Dopa.{orient.capitalize()}.TScrollbar"


def _ensure_scrollbar_style(master):
    """Clone clam's colorable elements into the current theme.

    `theme_use` is global to the interpreter, so the Converter's widgets and any
    native dialogs keep their theme; only this named style uses the clones.
    """
    style = ttk.Style(master)
    theme = style.theme_use()
    registry = getattr(master, "_dopa_scrollbar_themes", None)
    if registry is None:
        registry = master._dopa_scrollbar_themes = set()
    if theme in registry:
        return
    names = set(style.element_names())
    for orient, parts in _ELEMENTS.items():
        prefix = f"Dopa.{orient.capitalize()}.Scrollbar"
        for part in parts:
            name = f"{prefix}.{part}"
            if name not in names:
                style.element_create(name, "from", "clam", part)
        sticky = "ns" if orient == "vertical" else "ew"
        style.layout(_style_name(orient), [(f"{prefix}.trough", {
            "sticky": sticky,
            "children": [(f"{prefix}.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure(_style_name(orient), troughcolor=COLORS["panel_background"],
                        background=COLORS["border"], bordercolor=COLORS["panel_background"],
                        lightcolor=COLORS["border"], darkcolor=COLORS["border"],
                        gripcount=0, arrowsize=10)
        style.map(_style_name(orient),
                  background=[("pressed", COLORS["accent"]), ("active", COLORS["muted_text"])],
                  lightcolor=[("pressed", COLORS["accent"]), ("active", COLORS["muted_text"])],
                  darkcolor=[("pressed", COLORS["accent"]), ("active", COLORS["muted_text"])])
    registry.add(theme)


def scrollbar(master, orient="vertical", **options):
    """Dark neon scrollbar (§8.8) with the tk.Scrollbar command/set protocol."""
    # Styles belong to the interpreter, so remember them on the root window.
    _ensure_scrollbar_style(master._root())
    return ttk.Scrollbar(master, orient=orient, style=_style_name(orient), **options)
