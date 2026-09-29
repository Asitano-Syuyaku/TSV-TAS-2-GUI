"""Render the standalone 24x24 SVG sources as transparent PNGs.

Run: python assets/icons/render_png.py
Requires CairoSVG (python -m pip install CairoSVG) or gdk-pixbuf-thumbnailer.
"""

from argparse import ArgumentParser
from pathlib import Path
import shutil
import subprocess


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "png",
        help="PNG destination (default: assets/icons/png)",
    )
    args = parser.parse_args()

    try:
        import cairosvg
    except ImportError:
        cairosvg = None
    thumbnailer = shutil.which("gdk-pixbuf-thumbnailer")
    if cairosvg is None and thumbnailer is None:
        parser.error("Install CairoSVG (python -m pip install CairoSVG) or gdk-pixbuf-thumbnailer")

    source_dir = Path(__file__).resolve().parent / "source"
    sources = sorted(source_dir.glob("*.svg"))
    if not sources:
        parser.error(f"No SVG icons found in {source_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for source in sources:
        destination = args.output_dir / f"{source.stem}.png"
        if cairosvg is not None:
            cairosvg.svg2png(
                url=str(source),
                write_to=str(destination),
                output_width=24,
                output_height=24,
            )
        else:
            subprocess.run([thumbnailer, "-s", "24", str(source), str(destination)], check=True)
        print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
