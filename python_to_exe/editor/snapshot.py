"""Immutable editor buffers and disposable converter input/output workspaces."""

import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScriptSnapshot:
    text: str
    suffix: str = ".tsv"


@contextmanager
def script_workspace(source):
    """Close the UTF-8 snapshot before running a converter; remove all outputs on exit.

    Existing paths are accepted for callers that already have a saved script.
    Snapshot extensions retain the TSV or nx-TAS command-builder pipeline.
    """
    with tempfile.TemporaryDirectory(prefix="tas-editor-") as folder:
        destination = Path(folder)
        if isinstance(source, ScriptSnapshot):
            suffix = source.suffix.lower()
            if suffix not in (".tsv", ".txt"):
                raise ValueError("Snapshot must be a .tsv or .txt script")
            path = destination / ("snapshot" + suffix)
            with path.open("w", encoding="utf-8", newline="") as file:
                file.write(source.text)
        else:
            path = Path(source)
        yield path, destination
