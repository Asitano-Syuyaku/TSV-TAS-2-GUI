"""Literal reader for the bundled converter's Debug CSV; no TAS evaluation."""

import csv
import math
from dataclasses import dataclass
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


def parse_debug_csv(source):
    """Read one converter CSV stream, including unknown future detail columns."""
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
    rows = []
    first_row_by_frame = {}
    highest = -1
    for csv_row_number, fields in enumerate(reader, start=2):
        if not fields:
            # Legacy Windows output used csv.writer with a text stream that
            # translated CRLF a second time, leaving empty CSV records.
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
        first_row_by_frame.setdefault(frame, len(rows))
        highest = max(highest, frame)
        rows.append(tuple(fields))
    return DebugFrames(headers, tuple(rows), first_row_by_frame, highest + 1)


def load_debug_csv(path):
    with Path(path).open("r", encoding="utf-8", newline="") as source:
        return parse_debug_csv(source)


@dataclass(frozen=True)
class StickState:
    x: Optional[float]
    y: Optional[float]
    radius: Optional[float]
    angle: Optional[float]


@dataclass(frozen=True)
class StickFrame:
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


def resolved_sticks(frames):
    """Index only 1P controller values already resolved by the converter.

    The current CSV calls the LS radius field 'lx.r' (not 'ls.r'). Coordinates
    are the converter's signed 32767-scale values; angles are degrees. Missing
    or non-finite numeric fields remain unavailable instead of being evaluated.
    """
    columns = {name: index for index, name in enumerate(frames.headers)}

    def number(row, field):
        if field not in columns:
            return None
        try:
            value = float(row[columns[field]])
        except ValueError:
            return None
        return value if math.isfinite(value) else None

    rows = {}
    for row in frames.rows:
        if row[columns["2ndPlayer"]] != "False":
            continue
        frame = int(row[columns["Frame"]])
        rows[frame] = StickFrame(
            frame, StickState(*(number(row, field) for field in
                                ("ls.x", "ls.y", "lx.r", "ls.theta"))),
            StickState(*(number(row, field) for field in
                         ("rs.x", "rs.y", "rs.r", "rs.theta"))))
    return StickFrames(rows)
