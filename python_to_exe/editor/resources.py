"""Paths for editor assets in source and PyInstaller builds."""

import sys
from pathlib import Path


def palette_icon_path(icon_key):
    bundle_root = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
    root = Path(bundle_root) if bundle_root else Path(__file__).resolve().parents[2]
    return root / "assets" / "icons" / "png" / f"{icon_key}.png"
