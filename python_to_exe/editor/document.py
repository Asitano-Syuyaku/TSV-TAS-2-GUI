"""UTF-8 file state; no TSV-TAS parsing or formatting lives here."""

import os
import re
import stat
import tempfile
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from .file_state import ExternalFileConflict, disk_status, same_path, text_hash


_NEWLINES = re.compile(r"\r\n|\r|\n")
_SUFFIXES = {".tsv", ".txt"}


class EditorDocument:
    def __init__(self):
        self.new()

    def new(self):
        self.path = None
        self.text = ""
        self._saved_text = ""
        self._saved_raw = ""
        self._recovered_unsaved = False
        self._raw_text = ""
        self._endings = []

    @property
    def modified(self):
        return self._recovered_unsaved or self.text != self._saved_text

    @staticmethod
    def _path(path):
        target = Path(path).expanduser().resolve()
        if target.suffix.lower() not in _SUFFIXES:
            raise ValueError("Choose a .tsv or .txt file")
        return target

    def open(self, path):
        target = self._path(path)
        with target.open("r", encoding="utf-8", newline="") as file:
            raw = file.read()
        endings = _NEWLINES.findall(raw)
        text = _NEWLINES.sub("\n", raw)
        # Commit state only after a complete read and successful decode.
        self.path = target
        self.text = self._saved_text = text
        self._saved_raw = raw
        self._recovered_unsaved = False
        self._raw_text = raw
        self._endings = endings

    def set_text(self, text):
        self.text = text

    def restore(self, original_path, raw, saved_raw):
        """Restore into memory, retaining the old disk baseline and exact snapshot endings."""
        self.path = Path(original_path) if original_path is not None else None
        self.text = _NEWLINES.sub("\n", raw)
        self._saved_text = _NEWLINES.sub("\n", saved_raw)
        self._saved_raw = saved_raw
        self._raw_text = raw
        self._endings = _NEWLINES.findall(raw)
        self._recovered_unsaved = True

    def external_status(self, path=None):
        # A different Save As target has no baseline; its dialog handles overwrite.
        if self.path is None:
            return "unchanged"
        try:
            target = self._path(path if path is not None else self.path)
            if not same_path(target, self.path):
                return "unchanged"
        except (OSError, RuntimeError):
            # If path identity cannot be resolved, do not bypass the save guard.
            return "unreadable"
        return disk_status(self.path, text_hash(self._saved_raw))

    def _serialize(self):
        # Normally _raw_text is the saved text; after recovery it anchors snapshot endings.
        serialized_text = _NEWLINES.sub("\n", self._raw_text)
        if self.text == serialized_text:
            return self._raw_text
        lines = self.text.split("\n")
        preferred = Counter(self._endings).most_common(1)[0][0] if self._endings else "\n"
        endings = self._endings
        saved_lines = serialized_text.split("\n")
        if len(lines) != len(saved_lines) and len(set(endings)) > 1:
            # When rows move, keep mixed line endings with matching source rows.
            aligned = [None] * (len(lines) - 1)
            for kind, old_start, old_end, new_start, new_end in SequenceMatcher(
                    None, saved_lines, lines).get_opcodes():
                if kind not in ("equal", "replace"):
                    continue
                for offset in range(min(old_end - old_start, new_end - new_start)):
                    old, new = old_start + offset, new_start + offset
                    if old < len(endings) and new < len(aligned):
                        aligned[new] = endings[old]
            endings = [ending or preferred for ending in aligned]
        return "".join(
            line + (endings[i] if i < len(endings) else preferred)
            for i, line in enumerate(lines[:-1])
        ) + lines[-1]

    def save(self, path=None, *, overwrite_external=False):
        if path is None and self.path is None:
            raise ValueError("Choose a file name before saving")
        target = self._path(path if path is not None else self.path)
        status = self.external_status(target)
        if status == "unreadable" or (status != "unchanged" and not overwrite_external):
            raise ExternalFileConflict(target, status)
        # This content check is not an OS lock: another writer can still race with
        # the atomic replacement below. Explicit consent permits changed/missing
        # targets, never an unreadable target.
        raw = self._serialize()
        # Write beside the target so replacement does not expose a partial file.
        descriptor, temporary = tempfile.mkstemp(prefix=".tas-editor-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as file:
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
            if target.exists():
                os.chmod(temporary, stat.S_IMODE(target.stat().st_mode))
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.path = target
        self._saved_text = self.text
        self._saved_raw = raw
        self._recovered_unsaved = False
        self._raw_text = raw
        self._endings = _NEWLINES.findall(raw)
        return target
