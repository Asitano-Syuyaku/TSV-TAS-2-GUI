"""UTF-8 file state; no TSV-TAS parsing or formatting lives here."""

import os
import re
import stat
import tempfile
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


_NEWLINES = re.compile(r"\r\n|\r|\n")
_SUFFIXES = {".tsv", ".txt"}


class EditorDocument:
    def __init__(self):
        self.new()

    def new(self):
        self.path = None
        self.text = ""
        self._saved_text = ""
        self._raw_text = ""
        self._endings = []

    @property
    def modified(self):
        return self.text != self._saved_text

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
        self._raw_text = raw
        self._endings = endings

    def set_text(self, text):
        self.text = text

    def _serialize(self):
        if not self.modified:
            return self._raw_text
        lines = self.text.split("\n")
        preferred = Counter(self._endings).most_common(1)[0][0] if self._endings else "\n"
        endings = self._endings
        saved_lines = self._saved_text.split("\n")
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

    def save(self, path=None):
        if path is None and self.path is None:
            raise ValueError("Choose a file name before saving")
        target = self._path(path if path is not None else self.path)
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
        self._raw_text = raw
        self._endings = _NEWLINES.findall(raw)
        return target
