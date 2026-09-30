"""Literal reader for the bundled converter's Debug CSV; no TAS evaluation."""

import csv
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


# Exact field names in the current stas-dev Debug CSV. Additional fields survive.
SUMMARY_FIELDS = ("Frame", "2ndPlayer", "Buttons", "ButtonsOn", "ButtonsOff",
                  "ls.theta", "ls.x", "ls.y", "rs.theta", "rs.x", "rs.y",
                  "Command")


@dataclass(frozen=True)
class DebugFrames:
    headers: tuple
    rows: tuple
    first_row_by_frame: dict
    total_frames: int

    def row_for_frame(self, frame):
        return self.first_row_by_frame.get(frame)

    def detail(self, row_index):
        return dict(zip(self.headers, self.rows[row_index]))

    def summary(self, row_index):
        values = self.detail(row_index)
        return tuple(("2P" if values[field] == "True" else "1P")
                     if field == "2ndPlayer" else values[field]
                     for field in SUMMARY_FIELDS)


def _debug_records(source):
    """Shared literal CSV validation for full details and the preview-only reader."""
    reader = csv.reader(source, strict=True)
    try:
        headers = tuple(next(reader))
    except StopIteration:
        raise ValueError("Debug CSV is empty (missing header)") from None
    if len(headers) != len(set(headers)) or any(not field for field in headers):
        raise ValueError("Debug CSV has duplicate or empty header fields")
    missing = set(SUMMARY_FIELDS).difference(headers)
    if missing:
        raise ValueError("Debug CSV is missing required fields: " + ", ".join(sorted(missing)))

    frame_index = headers.index("Frame")
    player_index = headers.index("2ndPlayer")

    def records():
        for csv_row_number, fields in enumerate(reader, start=2):
            if not fields:
                # Legacy Windows CRCRLF produces zero-field records.
                continue
            if len(fields) != len(headers):
                raise ValueError(f"Debug CSV row {csv_row_number} has {len(fields)} fields; "
                                 f"expected {len(headers)}")
            try:
                frame = int(fields[frame_index])
            except ValueError:
                raise ValueError(f"Debug CSV row {csv_row_number} has an invalid Frame") from None
            if frame < 0:
                raise ValueError(f"Debug CSV row {csv_row_number} has a negative Frame")
            if fields[player_index] not in ("True", "False"):
                raise ValueError(f"Debug CSV row {csv_row_number} has an invalid 2ndPlayer")
            yield frame, fields

    return headers, records()


def parse_debug_csv(source):
    """Keep every field, sharing repeated strings within this CSV only."""
    headers, records = _debug_records(source)
    rows = []
    first_row_by_frame = {}
    highest = -1
    shared = {}
    for frame, fields in records:
        first_row_by_frame.setdefault(frame, len(rows))
        highest = max(highest, frame)
        # Motion/command constants often repeat on every frame. A bounded local
        # pool avoids their string copies without global interning or data loss.
        # Each literal is both the lookup key and the unchanged fallback value.
        if len(shared) < 4096:
            rows.append(tuple(map(shared.setdefault, fields, fields)))
        else:
            rows.append(tuple(map(shared.get, fields, fields)))
    return DebugFrames(headers, tuple(rows), first_row_by_frame, highest + 1)


def load_debug_csv(path):
    with Path(path).open("r", encoding="utf-8", newline="") as source:
        return parse_debug_csv(source)


@dataclass(frozen=True)
class StickState:
    # Explicit slots keep the existing Python 3.9-compatible dataclass API.
    __slots__ = ("x", "y", "radius", "angle")

    x: Optional[float]
    y: Optional[float]
    radius: Optional[float]
    angle: Optional[float]


@dataclass(frozen=True)
class StickFrame:
    __slots__ = ("frame", "left", "right")

    frame: int
    left: StickState
    right: StickState


@dataclass(frozen=True)
class StickFrames:
    rows: dict[int, StickFrame]

    def history(self, frame):
        """Current and up to three preceding exact CSV frames; never fill gaps."""
        return tuple(self.rows[index] for index in range(frame, frame - 4, -1)
                     if index in self.rows)


def _stick_frames(headers, records):
    """Index only 1P controller values already resolved by the converter.

    The current CSV calls the LS radius field 'lx.r' (not 'ls.r'). Coordinates
    are the converter's signed 32767-scale values; angles are degrees. Missing
    or non-finite numeric fields remain unavailable instead of being evaluated.
    """
    columns = {name: index for index, name in enumerate(headers)}

    @lru_cache(maxsize=512)
    def finite_number(text):
        # Repeated resolved values share immutable floats within this read.
        try:
            value = float(text)
        except ValueError:
            return None
        return value if math.isfinite(value) else None

    def number(row, field):
        index = columns.get(field)
        return finite_number(row[index]) if index is not None else None

    rows = {}
    for frame, row in records:
        if row[columns["2ndPlayer"]] != "False":
            continue
        rows[frame] = StickFrame(
            frame, StickState(*(number(row, field) for field in
                                ("ls.x", "ls.y", "lx.r", "ls.theta"))),
            StickState(*(number(row, field) for field in
                         ("rs.x", "rs.y", "rs.r", "rs.theta"))))
    return StickFrames(rows)


def resolved_sticks(frames):
    """Read already-loaded Inspector data with the same preview projection."""
    index = frames.headers.index("Frame")
    return _stick_frames(frames.headers, ((int(row[index]), row) for row in frames.rows))


def load_stick_csv(path):
    """Stream and validate all CSV rows, retaining only resolved 1P stick values."""
    with Path(path).open("r", encoding="utf-8", newline="") as source:
        headers, records = _debug_records(source)
        return _stick_frames(headers, records)
