"""Source-line positions emitted by the converter; no TSV duration parsing here."""

import csv
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .validation import _run_commands

if __package__ == "editor":
    from converter_logic import build_commands
else:
    from ..converter_logic import build_commands


FIELDS = ("SourceLine", "StartFrame", "Duration", "EndFrame", "TotalFrames")


@dataclass(frozen=True)
class LinePosition:
    start: int
    duration: int
    end: Optional[int]


@dataclass(frozen=True)
class LinePositions:
    rows: dict[int, LinePosition]
    total_frames: int

    def for_line(self, line):
        return self.rows.get(line)

    def for_range(self, first, last):
        """Summarize contiguous positive converter intervals in selected source rows."""
        first, last = sorted((first, last))
        positions = [self.rows.get(line) for line in range(first, last + 1)]
        if not positions or any(row is None or row.duration < 0 for row in positions):
            return None
        positive = [row for row in positions if row.duration > 0]
        if not positive:
            return (LinePosition(positions[0].start, 0, None)
                    if all(row.start == positions[0].start for row in positions) else None)
        start = expected = positive[0].start
        for row in positions:
            if row.start != expected:
                return None
            if row.duration > 0:
                if row.end is None:
                    return None
                expected = row.end + 1
        return LinePosition(start, expected - start, expected - 1)


@dataclass(frozen=True)
class PositionResult:
    positions: Optional[LinePositions] = None
    error: str = ""

    @property
    def success(self):
        return self.positions is not None


def parse_line_positions(source):
    reader = csv.reader(source, strict=True)
    if tuple(next(reader, ())) != FIELDS:
        raise ValueError("Invalid converter source-line map header")
    rows = {}
    total_frames = None
    for record in reader:
        if len(record) != len(FIELDS):
            raise ValueError("Invalid converter source-line map row")
        try:
            line, start, duration = map(int, record[:3])
            end = int(record[3]) if record[3] else None
            total = int(record[4])
        except ValueError:
            raise ValueError("Invalid converter source-line map value") from None
        if (line != len(rows) + 1 or start < 0 or total < 0 or
                (duration > 0 and end is None) or (duration <= 0 and end is not None) or
                (total_frames is not None and total != total_frames)):
            raise ValueError("Inconsistent converter source-line map")
        rows[line] = LinePosition(start, duration, end)
        total_frames = total
    if total_frames is None:
        raise ValueError("Converter source-line map has no rows")
    return LinePositions(rows, total_frames)


def analyze_positions(snapshot, base_dir=None, runner=None):
    """Compile an unsaved UTF-8 TSV snapshot in isolation with the converter's -m mode."""
    try:
        with tempfile.TemporaryDirectory(prefix="tas-positions-") as folder:
            source = Path(folder) / "snapshot.tsv"
            with source.open("w", encoding="utf-8", newline="") as file:
                file.write(snapshot)
            commands = build_commands(source, folder, "positions", "binary", line_map=True,
                                      debug=False, ftp=False, base_dir=base_dir)
            report = _run_commands(commands, base_dir, runner, True)
            if not report.success:
                return PositionResult(error=report.stderr or report.stdout)
            mapping = Path(commands[-1][-1] + "-lines.csv")
            if not mapping.is_file():
                return PositionResult(error="Converter source-line map was not generated")
            with mapping.open("r", encoding="utf-8", newline="") as file:
                return PositionResult(parse_line_positions(file))
    except (OSError, ValueError, RuntimeError, csv.Error) as error:
        return PositionResult(error=str(error))
