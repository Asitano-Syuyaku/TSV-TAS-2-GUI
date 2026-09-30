"""Content-based save protection without Tk or converter parsing."""

import ntpath
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe.editor.document import EditorDocument
from python_to_exe.editor.file_state import ExternalFileConflict, disk_status, same_path, text_hash
from python_to_exe.editor.recovery import RecoverySnapshot


class FileGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tas guard 日本語 ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.path = self.folder / "input with spaces.tsv"
        self.original = "1\ta\t\r\n// 日本語\n2\tb\r"
        self.path.write_bytes(self.original.encode("utf-8"))
        self.document = EditorDocument()
        self.document.open(self.path)
        self.document.set_text(self.document.text.replace("a", "x", 1))

    def test_unchanged_and_mtime_only_change_save_without_conflict(self):
        self.assertEqual(self.document.external_status(), "unchanged")
        stamp = self.path.stat().st_mtime
        os.utime(self.path, (stamp + 60, stamp + 60))
        self.assertEqual(self.document.external_status(), "unchanged")
        self.document.save()
        expected = self.original.replace("a", "x", 1)
        self.assertEqual(self.path.read_bytes(), expected.encode("utf-8"))
        self.assertEqual(self.document._saved_raw, expected)
        self.assertFalse(self.document.modified)
        self.document.save()  # The second save compares against the updated baseline.
        self.assertEqual(self.document.external_status(), "unchanged")

    def test_changed_is_blocked_until_explicit_overwrite_with_exact_content_comparison(self):
        stat = self.path.stat()
        for external in (b"external edit\r\n", b"\xff\xfe"):
            with self.subTest(external=external):
                self.path.write_bytes(external)
                os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                self.assertEqual(self.document.external_status(), "changed")
                before = self.document.__dict__.copy()
                with self.assertRaises(ExternalFileConflict) as conflict:
                    self.document.save()
                self.assertEqual(conflict.exception.status, "changed")
                self.assertEqual(self.path.read_bytes(), external)
                self.assertEqual(self.document.__dict__, before)
        self.document.save(overwrite_external=True)
        self.assertEqual(self.path.read_bytes(), self.original.replace("a", "x", 1).encode("utf-8"))
        self.assertFalse(self.document.modified)
        self.assertEqual(self.document.external_status(), "unchanged")

    def test_missing_is_not_recreated_without_explicit_consent(self):
        self.path.unlink()
        before = self.document.__dict__.copy()
        self.assertEqual(self.document.external_status(), "missing")
        with self.assertRaises(ExternalFileConflict) as conflict:
            self.document.save()
        self.assertEqual(conflict.exception.status, "missing")
        self.assertFalse(self.path.exists())
        self.assertEqual(self.document.__dict__, before)
        self.document.save(overwrite_external=True)
        self.assertEqual(self.document.external_status(), "unchanged")
        self.assertFalse(self.document.modified)

    def test_unreadable_cannot_be_overridden(self):
        before = self.document.__dict__.copy()
        with patch("python_to_exe.editor.file_state.Path.read_bytes", side_effect=PermissionError("denied")), \
             patch("python_to_exe.editor.document.os.replace") as replace:
            self.assertEqual(self.document.external_status(), "unreadable")
            for consent in (False, True):
                with self.assertRaises(ExternalFileConflict) as conflict:
                    self.document.save(overwrite_external=consent)
                self.assertEqual(conflict.exception.status, "unreadable")
            replace.assert_not_called()
        self.assertEqual(self.document.__dict__, before)
        self.assertEqual(self.path.read_bytes(), self.original.encode("utf-8"))

    def test_unresolvable_path_identity_is_unreadable(self):
        for error in (PermissionError("denied"), RuntimeError("symlink loop")):
            with self.subTest(error=type(error)), \
                 patch("python_to_exe.editor.document.same_path", side_effect=error):
                self.assertEqual(self.document.external_status(), "unreadable")
                with self.assertRaises(ExternalFileConflict) as conflict:
                    self.document.save(overwrite_external=True)
                self.assertEqual(conflict.exception.status, "unreadable")
        self.assertEqual(self.path.read_bytes(), self.original.encode("utf-8"))

    def test_save_as_different_path_ignores_original_conflict_but_same_alias_is_guarded(self):
        self.path.write_bytes(b"external edit")
        alias = self.path.parent / "unused" / ".." / self.path.name
        self.assertTrue(same_path(alias, self.path))
        self.assertEqual(self.document.external_status(alias), "changed")
        with self.assertRaises(ExternalFileConflict):
            self.document.save(alias)
        target = self.folder / "別ファイル.txt"
        self.assertEqual(self.document.external_status(target), "unchanged")
        self.document.save(target)
        self.assertEqual(self.path.read_bytes(), b"external edit")
        self.assertEqual(self.document.path, target)
        self.assertEqual(self.document.external_status(), "unchanged")
        self.assertEqual(target.read_bytes(), self.original.replace("a", "x", 1).encode("utf-8"))

    def test_failed_atomic_save_keeps_old_baseline_external_file_and_buffer(self):
        self.path.write_bytes(b"external edit")
        before = self.document.__dict__.copy()
        with patch("python_to_exe.editor.document.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaises(OSError):
                self.document.save(overwrite_external=True)
        self.assertEqual(self.document.__dict__, before)
        self.assertEqual(self.path.read_bytes(), b"external edit")
        self.assertEqual(self.document.external_status(), "changed")
        self.assertEqual(list(self.folder.glob(".tas-editor-*")), [])

    def test_recovery_keeps_original_baseline_and_shared_disk_comparison(self):
        snapshot = RecoverySnapshot.capture("a" * 32, self.document, self.path.name)
        self.assertEqual(snapshot.saved_text_hash, text_hash(self.original))
        restored = EditorDocument()
        for external in (b"new disk content", None):
            with self.subTest(external=external):
                if external is None:
                    self.path.unlink()
                else:
                    self.path.write_bytes(external)
                snapshot.restore(restored)
                expected = "missing" if external is None else "changed"
                self.assertEqual(snapshot.external_status(), expected)
                self.assertEqual(restored.external_status(), expected)
                self.assertEqual(restored._saved_raw, self.original)
                self.assertTrue(restored.modified)
                with self.assertRaises(ExternalFileConflict):
                    restored.save()
                self.assertEqual(self.path.exists(), external is not None)
        target = self.folder / "recovered.tsv"
        restored.save(target)
        self.assertEqual(restored.external_status(), "unchanged")
        self.assertEqual(restored._saved_raw, snapshot.text)

    def test_path_case_rules_and_disk_status_are_pure_helpers(self):
        upper = self.folder / "INPUT WITH SPACES.TSV"
        with patch("python_to_exe.editor.file_state.os.path.normcase", side_effect=ntpath.normcase):
            self.assertTrue(same_path(self.path, upper))
            self.assertFalse(same_path(self.path, self.folder / "other.tsv"))
        self.assertEqual(disk_status(self.path, text_hash(self.original)), "unchanged")
        self.assertEqual(disk_status(self.path, text_hash("different")), "changed")
        self.assertEqual(disk_status(self.folder / "missing.tsv", text_hash("")), "missing")
        self.assertEqual(EditorDocument().external_status(), "unchanged")


if __name__ == "__main__":
    unittest.main()
