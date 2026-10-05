"""Paths for editor assets in source and PyInstaller builds."""

import sys
from pathlib import Path


def palette_icon_path(icon_key):
    bundle_root = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
    root = Path(bundle_root) if bundle_root else Path(__file__).resolve().parents[2]
    return root / "assets" / "icons" / "png" / f"{icon_key}.png"


def neon_icon_path(path):
    """Light-stroke variant for the dark Editor (dopagaki3.md §4.4).

    It lives under the bundled PNG folder, so the existing PyInstaller
    `assets/icons/png` add-data also ships it. A missing variant means text only:
    the dark-ink originals would be unreadable on the neon theme.
    """
    return path.parent / "neon" / path.name
