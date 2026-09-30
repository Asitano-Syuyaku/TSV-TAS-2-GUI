"""Recovery records and debounce without Tk or writes to real user config."""

import json
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp, TEXT
from python_to_exe.editor.document import EditorDocument
from python_to_exe.editor.grid import TableGrid
from python_to_exe.editor.recovery import DEBOUNCE_MS, RecoverySnapshot, RecoveryStore
from python_to_exe.editor.table_model import CellSelection, TableModel
from python_to_exe.editor.window import EditorWindow, LABELS


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tas recovery 日本語 ")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.settings = AppSettings(self.work / "config" / "settings.json")
        self.report = Mock()
        self.store = RecoveryStore.from_settings(self.settings, self.report)

    def snapshot(self, path=None, text="1\t日本語\t\n"):
        document = EditorDocument()
        if path is not None:
            document.open(path)
        document.set_text(text)
        snapshot = RecoverySnapshot.capture(self.store.new_id(), document, path.name if path else "Untitled")
        return document, snapshot

    def records(self):
        return RecoveryStore(self.store.directory, self.report).load()

    def test_unmodified_document_does_not_create_recovery_directory(self):
        document = EditorDocument()
        self.assertIsNone(RecoverySnapshot.capture(self.store.new_id(), document, "Untitled"))
        source = self.work / "plain.tsv"
        source.write_bytes(b"1\ta\r\n")
        document.open(source)
        self.assertIsNone(RecoverySnapshot.capture(self.store.new_id(), document, source.name))
        self.assertFalse(self.store.directory.exists())

    def test_modified_tsv_txt_utf8_tabs_and_newline_round_trip(self):
        for suffix in (".tsv", ".txt"):
            for raw in ("1\ta\t\n\n", "1\ta\t\r\n\r\n", "1\ta\t\r\n// 日本語\n2\tb\r"):
                with self.subTest(suffix=suffix, raw=raw):
                    source = self.work / ("input with spaces 日本語" + suffix)
                    source.write_bytes(raw.encode("utf-8"))
                    document = EditorDocument()
                    document.open(source)
                    document.set_text(document.text.replace("a", "日本語", 1))
                    before = document.__dict__.copy()
                    snapshot = RecoverySnapshot.capture(self.store.new_id(), document, source.name)
                    self.assertEqual(snapshot.text, raw.replace("a", "日本語", 1))
                    self.assertEqual(snapshot.saved_raw, raw)
                    self.assertEqual(snapshot.source_kind, suffix[1:])
                    self.assertIsNone(snapshot.external_status())
                    self.assertTrue(self.store.write(snapshot))
                    self.assertEqual(document.__dict__, before)
                    loaded = next(item for item in self.records() if item.document_id == snapshot.document_id)
                    restored = EditorDocument()
                    loaded.restore(restored)
                    self.assertEqual(restored.path, source)
                    self.assertTrue(restored.modified)
                    self.assertEqual(restored._serialize(), snapshot.text)
                    self.assertEqual(source.read_bytes(), raw.encode("utf-8"))
                    restored.save(self.work / ("saved copy" + suffix))
                    self.assertEqual(restored.path.read_bytes(), snapshot.text.encode("utf-8"))
                    self.assertFalse(restored.modified)

    def test_untitled_restore_keeps_recovery_and_has_no_disk_path(self):
        document, snapshot = self.snapshot()
        self.assertTrue(self.store.write(snapshot))
        restored = EditorDocument()
        self.records()[0].restore(restored)
        self.assertIsNone(restored.path)
        self.assertTrue(restored.modified)
        self.assertEqual(restored.text, document.text)
        self.assertEqual(self.records()[0].text, document.text)
        self.assertEqual(list(self.work.glob("*.tsv")), [])
        # Restore alone is not a save or cleanup, and another restart sees it again.
        self.assertEqual(len(RecoveryStore(self.store.directory).load()), 1)

    def test_recovered_mixed_endings_remain_anchors_for_further_edits(self):
        source = self.work / "mixed.tsv"
        source.write_bytes(b"one\r\ntwo\nthree\r\n")
        document, snapshot = self.snapshot(source, "one\n\ntwo\nthree\n")
        restored = EditorDocument()
        snapshot.restore(restored)
        self.assertEqual(restored._serialize(), snapshot.text)
        restored.set_text(restored.text.replace("two", "日本語"))
        self.assertEqual(restored._serialize(), snapshot.text.replace("two", "日本語"))
        self.assertEqual(restored._saved_raw, "one\r\ntwo\nthree\r\n")

    def test_external_change_and_missing_original_never_overwrite_file(self):
        source = self.work / "original.tsv"
        source.write_bytes(b"1\ta\r\n")
        _, snapshot = self.snapshot(source, "1\tb\n")
        self.assertIsNone(snapshot.external_status())
        source.write_bytes(b"external edit\n")
        self.assertEqual(snapshot.external_status(), "changed")
        restored = EditorDocument()
        snapshot.restore(restored)
        self.assertEqual(source.read_bytes(), b"external edit\n")
        source.unlink()
        self.assertEqual(snapshot.external_status(), "missing")
        snapshot.restore(restored)
        self.assertEqual(restored.path, source)
        self.assertFalse(source.exists())
        with patch.object(Path, "read_bytes", side_effect=PermissionError("denied")):
            self.assertEqual(snapshot.external_status(), "unreadable")

    def test_multiple_sessions_for_same_original_are_independent_and_live_ids_are_excluded(self):
        source = self.work / "same.tsv"
        source.write_bytes(b"1\ta")
        _, first = self.snapshot(source, "1\tb")
        _, second = self.snapshot(source, "1\tx")
        self.assertNotEqual(first.document_id, second.document_id)
        self.store.write(first)
        self.store.write(second)
        self.assertEqual({item.text for item in self.records()}, {"1\tb", "1\tx"})
        self.assertEqual(self.store.load(), ())
        self.store.release(first.document_id)
        self.assertEqual(self.store.load(), (first,))
        self.store.delete(first.document_id)
        self.assertEqual(self.records(), (second,))
        self.assertEqual(source.read_bytes(), b"1\ta")

    def test_atomic_write_closes_file_before_replace_and_cleans_failed_write(self):
        _, snapshot = self.snapshot()
        replace = os.replace

        def verify(source, target):
            self.assertEqual(Path(source).parent, self.store.directory)
            self.assertEqual(json.loads(Path(source).read_text(encoding="utf-8"))["text"], snapshot.text)
            replace(source, target)

        with patch("python_to_exe.editor.recovery.os.replace", side_effect=verify), \
             patch("python_to_exe.editor.recovery.os.fsync", wraps=os.fsync) as fsync:
            self.assertTrue(self.store.write(snapshot))
            fsync.assert_called_once()
        original = self.store._path(snapshot.document_id).read_bytes()
        with patch("python_to_exe.editor.recovery.os.replace", side_effect=OSError("denied")):
            self.assertFalse(self.store.write(snapshot))
        self.assertEqual(self.store._path(snapshot.document_id).read_bytes(), original)
        self.assertEqual(len(tuple(self.store.directory.iterdir())), 1)
        self.report.assert_called()

    def test_directory_creation_and_delete_failures_are_nonfatal(self):
        _, snapshot = self.snapshot()
        self.store.directory.parent.mkdir()
        self.store.directory.touch()
        self.assertFalse(self.store.write(snapshot))
        self.store.directory.unlink()
        self.assertTrue(self.store.write(snapshot))
        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            self.assertFalse(self.store.delete(snapshot.document_id))
        self.assertEqual(self.records(), (snapshot,))

    def test_corrupt_versions_fields_and_hashes_are_ignored_without_deletion(self):
        _, snapshot = self.snapshot()
        self.store.write(snapshot)
        target = self.store._path(snapshot.document_id)
        base = {"version": 1, **asdict(snapshot)}
        invalid = [None, [], {**base, "version": 99}, {**base, "version": True},
                   {**base, "text": None}, {key: value for key, value in base.items() if key != "text"},
                   {**base, "original_path": "relative.tsv"}, {**base, "original_path": 42},
                   {**base, "timestamp": float("nan")}, {**base, "timestamp": True},
                   {**base, "timestamp": 1e300}, {**base, "saved_text_hash": "bad"},
                   {**base, "source_kind": "unknown"}, {**base, "display_name": []}]
        for values in invalid:
            with self.subTest(values=values):
                target.write_text(json.dumps(values), encoding="utf-8")
                self.assertEqual(self.records(), ())
                self.assertTrue(target.exists())
        for raw in (b"{broken", b"\xff"):
            target.write_bytes(raw)
            self.assertEqual(self.records(), ())
        self.report.assert_called()
        # Unknown fields are ignored and never propagated into subsequent writes.
        target.write_text(json.dumps({**base, "password": "not retained"}), encoding="utf-8")
        loaded = self.records()[0]
        self.store.write(loaded)
        self.assertNotIn("password", json.loads(target.read_text(encoding="utf-8")))

    def test_private_location_and_missing_config_do_not_fall_back_to_cwd(self):
        self.assertEqual(self.store.directory, self.settings.path.parent / "recovery")
        self.settings.path = None
        disabled = RecoveryStore.from_settings(self.settings, self.report)
        _, snapshot = self.snapshot()
        self.assertIsNone(disabled.directory)
        self.assertFalse(disabled.write(snapshot))
        self.assertEqual(disabled.load(), ())
        with self.assertRaises(ValueError):
            self.store.delete("../original.tsv")

    def test_debounce_coalesces_edits_and_unmodified_state_cancels_write(self):
        window = EditorWindow.__new__(EditorWindow)
        window.document = EditorDocument()
        window._recovery_store, window._recovery_id = self.store, self.store.new_id()
        window._recovery_job, window._closed, window._frame_edit_pending = None, False, False
        window._view, window.words = "raw", LABELS["en"]
        window.text = SimpleNamespace(get=lambda *_: window.document.text)
        jobs, count = {}, []

        def after(delay, callback):
            identifier = str(len(count))
            count.append(delay)
            jobs[identifier] = callback
            return identifier

        window.after, window.after_cancel = after, lambda identifier: jobs.pop(identifier)
        for index in range(150):
            window.document.set_text(str(index))
            window._schedule_recovery()
        self.assertEqual(set(count), {DEBOUNCE_MS})
        self.assertEqual(len(jobs), 1)
        self.assertFalse(self.store.directory.exists())
        jobs.pop(window._recovery_job)()
        self.assertEqual(self.records()[0].text, "149")
        window.document.set_text("")
        window._schedule_recovery()
        self.assertEqual(jobs, {})
        self.assertIsNone(window._recovery_job)
        self.assertEqual(self.records(), ())

    def test_pending_cell_preview_preserves_model_and_virtual_empty_cells(self):
        grid = TableGrid.__new__(TableGrid)
        grid.model = TableModel("1\ta\t\n// 日本語")
        grid.selection = CellSelection((0, 1))
        grid._editor = SimpleNamespace(get=lambda: "新しい値")
        original = grid.model.to_text()
        self.assertEqual(grid.snapshot_text(), "1\t新しい値\t\n// 日本語")
        self.assertEqual(grid.model.to_text(), original)
        grid.selection.move_to(9, 9)
        preview = grid.snapshot_text()
        self.assertEqual(preview.split("\n")[9], "\t" * 9 + "新しい値")
        self.assertEqual(grid.model.to_text(), original)
        grid._editor.get = lambda: ""
        self.assertEqual(grid.snapshot_text(), original)
        grid._editor.get = lambda: "invalid\tvalue"
        self.assertEqual(grid.snapshot_text(), original)

    def test_startup_cancel_preserves_files_and_individual_choices(self):
        _, first = self.snapshot(text="1\ta")
        _, second = self.snapshot(text="1\tb")
        self.store.write(first)
        self.store.write(second)
        app = TASConverterApp.__new__(TASConverterApp)
        app.words, app.recovery_store, app._create_editor = TEXT["en"], RecoveryStore(self.store.directory), Mock()
        with patch("python_to_exe.converter_gui.messagebox.askyesnocancel", return_value=None) as ask:
            app._check_recovery()
            ask.assert_called_once()
        self.assertEqual(len(self.records()), 2)
        with patch("python_to_exe.converter_gui.messagebox.askyesnocancel", side_effect=[True, False]):
            app._check_recovery()
        app._create_editor.assert_called_once_with(recovery=second)
        self.assertEqual(self.records(), (second,))
