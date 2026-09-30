"""Version-1 workspace preferences, validation, and sparse pure column geometry."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.editor.column_layout import ColumnLayout, clean_column_widths


class WorkspaceSettingsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="tas workspace 日本語 ")
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "settings.json"

    def load(self, **values):
        self.path.write_text(json.dumps(dict(version=1, **values)), encoding="utf-8")
        return AppSettings(self.path)

    def test_defaults_and_existing_version_one_preferences(self):
        for settings in (AppSettings(self.path), self.load(output_format="stas", debug_enabled=True)):
            self.assertEqual((settings.get("editor_width"), settings.get("editor_height")), (1200, 700))
            self.assertEqual(settings.get("editor_view"), "raw")
            self.assertEqual(settings.get("editor_palette_page"), 0)
            self.assertEqual(settings.get("editor_column_widths"), {})
        self.assertEqual(settings.get("output_format"), "stas")
        self.assertTrue(settings.get("debug_enabled"))

    def test_valid_workspace_fields_preserve_recent_output_and_debug(self):
        path = str(self.path.parent / "script.tsv")
        settings = self.load(editor_width=1350, editor_height=810, editor_view="table",
                             editor_palette_page=1, editor_column_widths={"0": 90, "100": 230},
                             recent_files=[path], output_format="nxtas", debug_enabled=True)
        self.assertEqual((settings.get("editor_width"), settings.get("editor_height")), (1350, 810))
        self.assertEqual(settings.get("editor_view"), "table")
        self.assertEqual(settings.get("editor_palette_page"), 1)
        self.assertEqual(settings.get("editor_column_widths"), {"0": 90, "100": 230})
        self.assertEqual(settings.recent_files, (path,))
        settings.save()
        self.assertEqual(AppSettings(self.path).get("output_format"), "nxtas")
        self.assertTrue(AppSettings(self.path).get("debug_enabled"))
        self.assertEqual(json.loads(self.path.read_text())["version"], 1)

    def test_size_invalid_fields_fall_back_independently(self):
        for value in (None, True, "1000", 1000.0, [], {}, 0, 799, 999999):
            with self.subTest(value=value):
                settings = self.load(editor_width=value, editor_height=800, output_format="stas")
                self.assertEqual(settings.get("editor_width"), 1200)
                self.assertEqual(settings.get("editor_height"), 800)
                self.assertEqual(settings.get("output_format"), "stas")
        for value in (None, False, "600", 600.0, [], {}, 499, 999999):
            with self.subTest(value=value):
                settings = self.load(editor_width=1400, editor_height=value, debug_enabled=True)
                self.assertEqual(settings.get("editor_width"), 1400)
                self.assertEqual(settings.get("editor_height"), 700)
                self.assertTrue(settings.get("debug_enabled"))

    def test_view_and_page_validation(self):
        for view in ("raw", "table"):
            self.assertEqual(self.load(editor_view=view).get("editor_view"), view)
        for page in (0, 1):
            self.assertEqual(self.load(editor_palette_page=page).get("editor_palette_page"), page)
        for invalid in (None, True, 2, -1, 1.0, "1", [], {}):
            with self.subTest(invalid=invalid):
                settings = self.load(editor_palette_page=invalid, editor_view="table")
                self.assertEqual(settings.get("editor_palette_page"), 0)
                self.assertEqual(settings.get("editor_view"), "table")
        for invalid in (None, True, 1, "spreadsheet", "TABLE", [], {}):
            with self.subTest(invalid=invalid):
                settings = self.load(editor_view=invalid, editor_palette_page=1)
                self.assertEqual(settings.get("editor_view"), "raw")
                self.assertEqual(settings.get("editor_palette_page"), 1)

    def test_sparse_widths_validate_each_field_and_return_a_copy(self):
        values = {"0": 90, "001": 130, "50": 230, "-1": 100, "invalid": 120,
                  "1.5": 100, "2": True, "3": 47, "4": 2001, "5": "100", "6": 90.0,
                  "7": None, "8": [], "9": {}, "10": 48, "11": 2000}
        expected = {"0": 90, "1": 130, "50": 230, "10": 48, "11": 2000}
        self.assertEqual(clean_column_widths(values), expected)
        self.assertEqual(clean_column_widths({1.5: 90, True: 90}), {})
        settings = self.load(editor_column_widths=values, editor_view="table")
        self.assertEqual(settings.get("editor_column_widths"), expected)
        copied = settings.get("editor_column_widths")
        copied.clear()
        self.assertEqual(settings.get("editor_column_widths"), expected)
        for invalid in (None, "widths", [], 1, True):
            self.assertEqual(self.load(editor_column_widths=invalid).get("editor_column_widths"), {})

    def test_memory_update_can_be_debounced_without_stale_state(self):
        settings = AppSettings(self.path)
        settings.save()
        before = self.path.read_bytes()
        with patch.object(settings, "save", wraps=settings.save) as save:
            settings.update(editor_width=1400, editor_height=800, persist=False)
            self.assertEqual(settings.get("editor_width"), 1400)
            self.assertEqual(self.path.read_bytes(), before)
            save.assert_not_called()
            settings.update(editor_palette_page=1)
            save.assert_called_once()
        self.assertEqual(AppSettings(self.path).get("editor_width"), 1400)
        self.assertEqual(AppSettings(self.path).get("editor_palette_page"), 1)

    def test_runtime_document_and_sensitive_fields_are_never_saved(self):
        settings = AppSettings(self.path)
        settings.update(editor_width=1400, editor_x=123, editor_y=456, cursor="10.3",
                        scroll=[1, 2], selection=[3, 4], undo=["secret"], recovery="secret",
                        go_frame=120, problems="secret", frame_cache="secret", password="secret")
        saved = json.loads(self.path.read_text())
        self.assertFalse(set(saved) & {"editor_x", "editor_y", "cursor", "scroll", "selection",
                                      "undo", "recovery", "go_frame", "problems", "frame_cache", "password"})
        self.assertNotIn("secret", self.path.read_text())


class ColumnPreferenceTests(unittest.TestCase):
    def test_export_only_overrides_including_future_columns(self):
        columns = ColumnLayout(160, default_widths={0: 112, 1: 148})
        self.assertEqual(columns.export_widths(), {})
        columns.set_width(0, 112)
        columns.set_width(50, 160)
        self.assertEqual(columns.export_widths(), {})
        columns.set_width(0, 90)
        columns.set_width(10000, 230)
        self.assertEqual(columns.export_widths(), {"0": 90, "10000": 230})
        self.assertEqual(columns.width(10000), 230)
        self.assertEqual(len(columns._edges), 1)  # No geometry for invisible future columns.
        columns.set_width(0, 112)
        self.assertEqual(columns.export_widths(), {"10000": 230})

    def test_import_resets_cached_edges_preserves_guides_and_ignores_invalid_fields(self):
        columns = ColumnLayout(160, default_widths={0: 112, 1: 148})
        self.assertEqual(columns.edge(3), 420)
        columns.import_widths({"0": 112, "1": 130, "7": 240, "x": 100, "2": -100})
        self.assertEqual(columns.export_widths(), {"1": 130, "7": 240})
        self.assertEqual(columns.edge(3), 402)
        self.assertEqual(columns.width(0), 112)
        self.assertEqual(columns.width(7), 240)
        columns.import_widths({})
        self.assertEqual(columns.edge(3), 420)
        self.assertEqual(columns.export_widths(), {})


if __name__ == "__main__":
    unittest.main()
