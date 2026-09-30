"""Exact disk snapshots, bounded rotation, and atomic primary-save failures."""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.editor.document import EditorDocument
from python_to_exe.editor.file_state import ExternalFileConflict
from python_to_exe.editor.save_backups import BACKUP_COUNT, backup_path, create_save_backup


ROOT = Path(__file__).resolve().parents[1]


class SaveBackupTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="tas backup 日本語 ")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.target = self.folder / "route with spaces 日本語.tsv"
        self.document = EditorDocument()

    def history(self, target=None):
        target = target or self.target
        return {file.name: file.read_bytes()
                for file in target.parent.glob(target.name + ".before*")}

    def open_modified(self):
        self.target.write_bytes(b"1\ta\r\n")
        self.document.open(self.target)
        self.document.set_text("1\tb\n")
        return self.document.__dict__.copy()

    def assert_no_temporary_files(self):
        self.assertEqual(list(self.folder.glob(".tas-editor-*")), [])
        self.assertEqual(list(self.folder.glob(".tas-backup-*")), [])

    def test_names_and_generation_limits(self):
        self.assertEqual(BACKUP_COUNT, 10)
        self.assertEqual(backup_path(self.target, 1).name, self.target.name + ".before1")
        self.assertEqual(backup_path(self.target, 10).name, self.target.name + ".before10")
        for invalid in (0, 11, -1, True, "1", None):
            with self.assertRaises(ValueError):
                backup_path(self.target, invalid)

    def test_first_second_third_save_and_unchanged_explicit_save(self):
        self.document.set_text("A")
        self.document.save(self.target)
        self.assertEqual(self.history(), {})
        self.document.set_text("B")
        self.document.save()
        self.assertEqual(backup_path(self.target, 1).read_bytes(), b"A")
        self.document.set_text("C")
        self.document.save()
        self.assertEqual(backup_path(self.target, 1).read_bytes(), b"B")
        self.assertEqual(backup_path(self.target, 2).read_bytes(), b"A")
        self.document.save()  # Ctrl+S still backs up an unmodified existing target.
        self.assertEqual(backup_path(self.target, 1).read_bytes(), b"C")
        self.assertEqual(backup_path(self.target, 2).read_bytes(), b"B")
        self.assertFalse(self.document.modified)

    def test_more_than_ten_saves_keep_exactly_latest_ten_generations(self):
        for value in range(16):
            self.document.set_text(str(value))
            self.document.save(self.target)
        self.assertEqual(self.target.read_bytes(), b"15")
        self.assertEqual(len(self.history()), 10)
        for generation in range(1, 11):
            self.assertEqual(backup_path(self.target, generation).read_bytes(),
                             str(15 - generation).encode())
        self.assertFalse(Path(str(self.target) + ".before11").exists())
        self.assert_no_temporary_files()

    def test_raw_crlf_mixed_endings_empty_bytes_and_unicode_are_preserved(self):
        for raw in (b"1\ta\r\n2\tb\r\n", b"1\ta\r\n\n2\tb\r", b"",
                    "// 日本語\r\n1\ta\t\n".encode("utf-8")):
            with self.subTest(raw=raw):
                self.target.write_bytes(raw)
                self.document.open(self.target)
                self.document.set_text("1\tx\n")
                self.document.save()
                self.assertEqual(backup_path(self.target, 1).read_bytes(), raw)
        self.assert_no_temporary_files()

    @unittest.skipUnless(os.name == "posix", "POSIX file modes only")
    def test_primary_and_backup_keep_original_mode(self):
        self.open_modified()
        self.target.chmod(0o640)
        self.document.save()
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
        self.assertEqual(stat.S_IMODE(backup_path(self.target, 1).stat().st_mode), 0o640)

    def test_txt_saves_do_not_create_or_rotate_backups(self):
        target = self.folder / "script.txt"
        target.write_bytes(b"old nx-TAS\r\n")
        Path(str(target) + ".before1").write_bytes(b"existing history")
        self.document.open(target)
        self.document.set_text("new nx-TAS\n")
        with patch("python_to_exe.editor.document.create_save_backup") as backup:
            self.document.save()
            self.document.save()
            backup.assert_not_called()
        self.assertEqual(self.history(target), {target.name + ".before1": b"existing history"})

    def test_save_as_backs_up_only_the_overwritten_target_not_source(self):
        self.open_modified()
        backup_path(self.target, 1).write_bytes(b"source history")
        source_history = self.history()
        fresh = self.folder / "new copy.tsv"
        self.document.save(fresh)
        self.assertEqual(self.history(fresh), {})
        self.assertEqual(self.history(), source_history)
        self.assertEqual(self.target.read_bytes(), b"1\ta\r\n")
        existing = self.folder / "existing copy.tsv"
        existing.write_bytes(b"external destination\xff\r\n")
        backup_path(existing, 1).write_bytes(b"older destination")
        self.document.save(existing)
        self.assertEqual(backup_path(existing, 1).read_bytes(), b"external destination\xff\r\n")
        self.assertEqual(backup_path(existing, 2).read_bytes(), b"older destination")
        self.assertEqual(self.history(), source_history)
        self.assertEqual(self.document.path, existing)
        self.document.save(str(existing.parent) + "/./" + existing.name)
        self.assertEqual(backup_path(existing, 1).read_bytes(), existing.read_bytes())

    def test_external_guard_refusal_has_no_rotation_and_yes_copies_actual_external_bytes(self):
        before = self.open_modified()
        backup_path(self.target, 1).write_bytes(b"older history")
        history = self.history()
        external = b"external version\xff\r\n\t\n"
        self.target.write_bytes(external)
        with patch("python_to_exe.editor.document.create_save_backup", wraps=create_save_backup) as backup:
            with self.assertRaises(ExternalFileConflict):
                self.document.save()
            backup.assert_not_called()
            self.assertEqual(self.history(), history)
            self.assertEqual(self.document.__dict__, before)
            self.document.save(overwrite_external=True)
            backup.assert_called_once_with(self.target)
        self.assertEqual(backup_path(self.target, 1).read_bytes(), external)
        self.assertEqual(backup_path(self.target, 2).read_bytes(), b"older history")
        self.assertNotEqual(backup_path(self.target, 1).read_bytes(), before["_saved_raw"].encode())
        self.assertFalse(self.document.modified)

    def test_missing_target_refusal_and_recreation_do_not_touch_existing_history(self):
        before = self.open_modified()
        for generation in (1, 3, 10):
            backup_path(self.target, generation).write_bytes(str(generation).encode())
        history = self.history()
        self.target.unlink()
        with self.assertRaises(ExternalFileConflict):
            self.document.save()
        self.assertEqual(self.document.__dict__, before)
        self.assertEqual(self.history(), history)
        self.assertFalse(self.target.exists())
        self.document.save(overwrite_external=True)
        self.assertEqual(self.target.read_bytes(), b"1\tb\r\n")
        self.assertEqual(self.history(), history)

    def test_unreadable_guard_precedes_all_backup_io(self):
        before = self.open_modified()
        with patch("python_to_exe.editor.document.disk_status", return_value="unreadable"), \
             patch("python_to_exe.editor.document.create_save_backup") as backup:
            with self.assertRaises(ExternalFileConflict):
                self.document.save(overwrite_external=True)
            backup.assert_not_called()
        self.assertEqual(self.document.__dict__, before)
        self.assertEqual(self.target.read_bytes(), b"1\ta\r\n")
        self.assertEqual(self.history(), {})

    def test_new_file_preparation_failure_never_starts_backup(self):
        before = self.open_modified()
        with patch("python_to_exe.editor.document.os.fsync", side_effect=OSError("disk full")), \
             patch("python_to_exe.editor.document.create_save_backup") as backup:
            with self.assertRaises(OSError):
                self.document.save()
            backup.assert_not_called()
        self.assertEqual(self.target.read_bytes(), b"1\ta\r\n")
        self.assertEqual(self.document.__dict__, before)
        self.assert_no_temporary_files()

    def test_snapshot_copy_sync_or_creation_failure_keeps_primary_baseline_and_history(self):
        original_mkstemp = tempfile.mkstemp

        def cannot_create_backup(**options):
            if options.get("prefix") == ".tas-backup-":
                raise PermissionError("backup directory unavailable")
            return original_mkstemp(**options)

        for failure in ("copy", "fsync", "create"):
            with self.subTest(failure=failure):
                before = self.open_modified()
                backup_path(self.target, 1).write_bytes(b"history")
                history = self.history()
                if failure == "copy":
                    fault = patch("python_to_exe.editor.save_backups.shutil.copyfileobj",
                                  side_effect=OSError("backup disk full"))
                elif failure == "fsync":
                    fault = patch("python_to_exe.editor.save_backups.os.fsync",
                                  side_effect=[None, OSError("backup sync failed")])
                else:
                    fault = patch("python_to_exe.editor.save_backups.tempfile.mkstemp",
                                  side_effect=cannot_create_backup)
                with fault, patch("python_to_exe.editor.save_backups.rotate_backups") as rotate:
                    with self.assertRaises(OSError):
                        self.document.save()
                    rotate.assert_not_called()
                self.assertEqual(self.target.read_bytes(), b"1\ta\r\n")
                self.assertEqual(self.document.__dict__, before)
                self.assertEqual(self.history(), history)
                self.assert_no_temporary_files()

    def test_rotation_is_descending_after_preparation_and_before_primary_replacement(self):
        self.open_modified()
        for generation in range(1, 11):
            backup_path(self.target, generation).write_bytes(str(generation).encode())
        original_replace = os.replace
        events, handles = [], []
        original_open = Path.open

        def track_open(path, *args, **kwargs):
            handle = original_open(path, *args, **kwargs)
            handles.append(handle)
            return handle

        def replace(source, target):
            source, target = Path(source), Path(target)
            self.assertTrue(all(file.closed for file in handles))
            if target == self.target:
                self.assertEqual(backup_path(target, 1).read_bytes(), b"1\ta\r\n")
                self.assertEqual(source.read_bytes(), b"1\tb\r\n")
            else:
                # The prepared new file exists throughout backup processing.
                prepared = list(self.folder.glob(".tas-editor-*"))
                self.assertEqual(len(prepared), 1)
                self.assertEqual(prepared[0].read_bytes(), b"1\tb\r\n")
                self.assertEqual(self.target.read_bytes(), b"1\ta\r\n")
            events.append((source.name, target.name))
            return original_replace(source, target)

        with patch.object(Path, "open", track_open), \
             patch("python_to_exe.editor.save_backups.os.replace", side_effect=replace):
            self.document.save()
        expected = [(backup_path(self.target, n).name, backup_path(self.target, n + 1).name)
                    for n in range(9, 0, -1)]
        self.assertEqual(events[:9], expected)
        self.assertTrue(events[9][0].startswith(".tas-backup-"))
        self.assertEqual(events[9][1], backup_path(self.target, 1).name)
        self.assertEqual(events[10][1], self.target.name)
        self.assertEqual(backup_path(self.target, 10).read_bytes(), b"9")
        self.assert_no_temporary_files()

    def test_rotation_snapshot_install_and_final_replace_failures_keep_primary(self):
        original_replace = os.replace
        for failure in ("rotate", "snapshot", "primary"):
            with self.subTest(failure=failure):
                before = self.open_modified()
                backup_path(self.target, 9).write_bytes(b"older")

                def replace(source, target):
                    source, target = Path(source), Path(target)
                    if ((failure == "rotate" and source == backup_path(self.target, 9)) or
                            (failure == "snapshot" and source.name.startswith(".tas-backup-")) or
                            (failure == "primary" and target == self.target)):
                        raise PermissionError("locked backup or target")
                    return original_replace(source, target)

                with patch("python_to_exe.editor.save_backups.os.replace", side_effect=replace):
                    with self.assertRaises(OSError):
                        self.document.save()
                self.assertEqual(self.target.read_bytes(), b"1\ta\r\n")
                self.assertEqual(self.document.__dict__, before)
                self.assert_no_temporary_files()

    def test_rotation_gaps_expire_old_tenth_generation(self):
        self.open_modified()
        backup_path(self.target, 1).write_bytes(b"one")
        backup_path(self.target, 3).write_bytes(b"three")
        backup_path(self.target, 10).write_bytes(b"expired")
        self.document.save()
        self.assertEqual(self.history(), {self.target.name + ".before1": b"1\ta\r\n",
                                          self.target.name + ".before2": b"one",
                                          self.target.name + ".before4": b"three"})

    def test_backups_are_rejected_as_editor_documents_recent_files_and_ignored_by_git(self):
        self.open_modified()
        self.document.save()
        backup = backup_path(self.target, 1)
        settings = AppSettings(self.folder / "settings.json")
        settings.add_recent(backup)
        self.assertEqual(settings.recent_files, ())
        with self.assertRaises(ValueError):
            EditorDocument().open(backup)
        paths = "route.tsv.before1\nroute.tsv.before10\nroute.TSV.before1\nroute.tsv\nroute.txt\n"
        result = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"], cwd=ROOT,
                                input=paths, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), paths.splitlines()[:3])


if __name__ == "__main__":
    unittest.main()
