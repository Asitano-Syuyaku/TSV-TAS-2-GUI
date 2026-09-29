"""Literal reader for the bundled converter's Debug CSV; no TAS evaluation."""

import csv
from dataclasses import dataclass
from pathlib import Path


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
