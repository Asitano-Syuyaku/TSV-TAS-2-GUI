"""Private, per-document recovery snapshots; never write original script files."""

import copy
import json
import logging
import math
import os
import re
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .file_state import disk_status, text_hash


VERSION = 1
DEBOUNCE_MS = 1000
_ID = re.compile(r"[0-9a-f]{32}\Z")


@dataclass(frozen=True)
class RecoverySnapshot:
    document_id: str
    original_path: Optional[str]
    display_name: str
    text: str
    saved_raw: str
    saved_text_hash: str
    source_kind: str
    timestamp: float

    @classmethod
    def capture(cls, document_id, document, display_name, text=None):
        # Serialize a copy, including any pending cell, without changing the buffer.
        preview = copy.copy(document)
        if text is not None:
            preview.set_text(text)
        if not document.modified and not preview.modified:
            return None
        return cls(document_id, str(document.path) if document.path else None,
                   display_name, preview._serialize(), document._saved_raw,
                   text_hash(document._saved_raw),
                   "txt" if document.path and document.path.suffix.lower() == ".txt" else "tsv",
                   time.time())

    def external_status(self):
        if self.original_path is None:
            return None
        status = disk_status(self.original_path, self.saved_text_hash)
        return None if status == "unchanged" else status

    def restore(self, document):
        document.restore(self.original_path, self.text, self.saved_raw)


class RecoveryStore:
    def __init__(self, directory, report=None):
        self.directory = Path(directory) if directory is not None else None
        self.report = report or logging.getLogger(__name__).warning
        self.active_ids = set()

    @classmethod
    def from_settings(cls, settings, report=None):
        # Explicit test settings can isolate recovery too; production uses user config.
        return cls(settings.path.parent / "recovery" if settings.path is not None else None, report)

    def new_id(self):
        identifier = uuid.uuid4().hex
        self.active_ids.add(identifier)
        return identifier

    def release(self, identifier):
        self.active_ids.discard(identifier)

    def _path(self, identifier):
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise ValueError("Invalid recovery ID")
        return self.directory / (identifier + ".json") if self.directory is not None else None

    def write(self, snapshot):
        target = self._path(snapshot.document_id)
        if target is None:
            self.report("Recovery unavailable: no user config directory")
            return False
        temporary = None
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".recovery-", dir=self.directory)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as file:
                json.dump({"version": VERSION, **asdict(snapshot)}, file, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
            return True
        except (OSError, ValueError) as error:
            self.report(f"Recovery write failed: {error}")
            return False
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                except OSError as error:
                    self.report(f"Recovery temporary cleanup failed: {error}")

    def delete(self, identifier):
        target = self._path(identifier)
        if target is None:
            return True
        try:
            target.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError as error:
            self.report(f"Recovery removal failed: {error}")
            return False

    def load(self):
        if self.directory is None:
            return ()
        try:
            paths = tuple(self.directory.glob("*.json"))
        except OSError as error:
            self.report(f"Recovery scan failed: {error}")
            return ()
        snapshots = []
        for path in paths:
            if path.stem in self.active_ids:
                continue
            try:
                with path.open("r", encoding="utf-8") as file:
                    values = json.load(file)
                snapshots.append(self._decode(path.stem, values))
            except (OSError, ValueError, TypeError, OverflowError, RecursionError) as error:
                # Do not log recovered text, or delete an unreadable record.
                self.report(f"Recovery ignored ({path.name}): {type(error).__name__}")
        return tuple(sorted(snapshots, key=lambda item: item.timestamp, reverse=True))

    @staticmethod
    def _decode(identifier, values):
        if (not _ID.fullmatch(identifier) or not isinstance(values, dict) or
                type(values.get("version")) is not int or values["version"] != VERSION or
                values.get("document_id") != identifier):
            raise ValueError("Invalid recovery version or ID")
        for key in ("display_name", "text", "saved_raw", "saved_text_hash", "source_kind"):
            if not isinstance(values.get(key), str):
                raise ValueError("Invalid recovery field")
        if not values["display_name"] or values["source_kind"] not in ("tsv", "txt"):
            raise ValueError("Invalid recovery kind or display name")
        original = values.get("original_path")
        if "original_path" not in values or (original is not None and (
                not isinstance(original, str) or "\0" in original or not Path(original).is_absolute() or
                Path(original).suffix.lower() != "." + values["source_kind"])):
            raise ValueError("Invalid original path")
        timestamp = values.get("timestamp")
        if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp <= 0:
            raise ValueError("Invalid timestamp")
        datetime.fromtimestamp(timestamp)  # Also ensure it can be displayed on this platform.
        if text_hash(values["saved_raw"]) != values["saved_text_hash"]:
            raise ValueError("Invalid saved baseline hash")
        return RecoverySnapshot(identifier, original, values["display_name"], values["text"],
                                values["saved_raw"], values["saved_text_hash"],
                                values["source_kind"], timestamp)
