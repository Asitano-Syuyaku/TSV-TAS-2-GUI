"""Windows display setup: crisp, readable text at 125% / 150% scaling.

- Before any Tk window: declare the process System-DPI-aware, so Windows stops
  bitmap-stretching the whole UI at 125% / 150% (that stretch was the blur).
  Per-Monitor V2 was considered and not used: Tk 8.6 does not react to
  WM_DPICHANGED, so a second monitor with another DPI would get wrong sizes.
- After the root exists: use Meiryo UI, which renders Japanese and Latin evenly
  at small sizes (Yu Gothic UI is faint; Latin-only fonts fall back to a heavy
  Japanese face in Tk), and publish DPI / 96 as the scale for pixel geometry.
Everything here is a no-op off Windows.
"""

import sys

if __package__:
    from .editor.theme import set_ui_scale
else:
    from editor.theme import set_ui_scale


UI_FAMILY = "Meiryo UI"
# Named font -> points. The TSV text (TkFixedFont) keeps its previous 10 pt.
NAMED_FONTS = {"TkDefaultFont": 9, "TkTextFont": 9, "TkHeadingFont": 9, "TkCaptionFont": 9,
               "TkSmallCaptionFont": 9, "TkTooltipFont": 9, "TkIconFont": 9,
               "TkMenuFont": 9, "TkFixedFont": 10}


def enable_dpi_awareness(platform=None):
    """Call before creating the Tk root. Returns the mode that was set."""
    if not (platform or sys.platform).startswith("win"):
        return "not-windows"
    try:
        import ctypes
    except ImportError:
        return "unavailable"
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
        return "system"
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "system-legacy"
    except (AttributeError, OSError):
        return "unavailable"


def configure_root(root, platform=None):
    """After the root exists: readable fonts and the pixel scale (Windows only)."""
    if not (platform or sys.platform).startswith("win"):
        return False
    from tkinter import font
    try:
        set_ui_scale(root.winfo_fpixels("1i") / 96.0)
        families = set(font.families(root))
    except Exception:
        return False  # A nicety: never block startup over display setup.
    if UI_FAMILY in families:
        for name, points in NAMED_FONTS.items():
            try:
                font.nametofont(name, root=root).configure(family=UI_FAMILY, size=points)
            except Exception:
                continue
    return True
