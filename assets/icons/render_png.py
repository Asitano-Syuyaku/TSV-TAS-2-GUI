"""Render the standalone 24x24 SVG sources as transparent PNGs.

Run: python assets/icons/render_png.py
Dopagaki3 neon variant (light strokes for the dark Editor):
  python assets/icons/render_png.py --stroke "#F2EEFF" --output-dir assets/icons/png/neon
Requires CairoSVG (python -m pip install CairoSVG) or gdk-pixbuf-thumbnailer.
"""

from argparse import ArgumentParser
from pathlib import Path
import shutil
import subprocess
import tempfile

SOURCE_COLOR = "#202020"


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "png",
        help="PNG destination (default: assets/icons/png)",
    )
    parser.add_argument(
        "--stroke",
        default=SOURCE_COLOR,
        help=f"Replace the sources' single ink color {SOURCE_COLOR} (default: unchanged)",
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
    recolor = tempfile.TemporaryDirectory() if args.stroke != SOURCE_COLOR else None
    for source in sources:
        if recolor is not None:
            # The sources use one ink color for stroke and fill; recolor only that literal.
            recolored = Path(recolor.name) / source.name
            recolored.write_text(source.read_text(encoding="utf-8").replace(SOURCE_COLOR, args.stroke),
                                 encoding="utf-8")
            source = recolored
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
    if recolor is not None:
        recolor.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
