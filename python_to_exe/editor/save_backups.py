"""Bounded, byte-preserving save history beside an existing TSV target."""

import os
import shutil
import stat
import tempfile
from pathlib import Path


BACKUP_COUNT = 10


def backup_path(target, generation):
    if type(generation) is not int or not 1 <= generation <= BACKUP_COUNT:
        raise ValueError(f"Backup generation must be from 1 to {BACKUP_COUNT}")
    target = Path(target)
    return target.with_name(f"{target.name}.before{generation}")


def rotate_backups(target):
    """Make room for before1, ageing existing generations from highest to lowest."""
    try:
        os.unlink(backup_path(target, BACKUP_COUNT))
    except FileNotFoundError:
        pass
    for generation in range(BACKUP_COUNT - 1, 0, -1):
        try:
            os.replace(backup_path(target, generation), backup_path(target, generation + 1))
        except FileNotFoundError:
            # Gaps are allowed; other I/O failures must stop the primary save.
            pass


def create_save_backup(target):
    """Prepare a disk snapshot before rotating; never move or write the primary.

    The caller has already approved external changes and prepared its new file.
    All handles close before replacement (including on Windows). Rotation is not
    transactional, but an error propagates before the caller replaces its target.
    """
    target = Path(target)
    try:
        source = target.open("rb")
    except FileNotFoundError:
        # First save/recreation: leave all existing backup generations untouched.
        return False
    snapshot = None
    try:
        with source:
            mode = stat.S_IMODE(os.fstat(source.fileno()).st_mode)
            descriptor, snapshot = tempfile.mkstemp(prefix=".tas-backup-", dir=target.parent)
            with os.fdopen(descriptor, "wb") as file:
                shutil.copyfileobj(source, file)
                file.flush()
                os.fsync(file.fileno())
        os.chmod(snapshot, mode)
        rotate_backups(target)
        os.replace(snapshot, backup_path(target, 1))
        return True
    finally:
        if snapshot is not None:
            try:
                os.unlink(snapshot)
            except FileNotFoundError:
                pass
