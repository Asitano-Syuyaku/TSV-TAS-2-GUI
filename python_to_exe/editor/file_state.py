"""Content-based disk comparison, shared by normal saving and recovery."""

import hashlib
import os
from pathlib import Path


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def disk_status(path, baseline_hash):
    try:
        actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unreadable"
    return "unchanged" if actual == baseline_hash else "changed"


def same_path(first, second):
    """Resolve aliases and use the host's case rules (case-insensitive on Windows)."""
    return (os.path.normcase(str(Path(first).expanduser().resolve())) ==
            os.path.normcase(str(Path(second).expanduser().resolve())))


class ExternalFileConflict(OSError):
    def __init__(self, path, status):
        self.path, self.status = path, status
        super().__init__(f"Cannot save {path}: external file is {status}")
