"""User config paths, strict non-sensitive schema, and atomic persistence."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe.app_settings import APP_NAME, AppSettings, settings_path


class SettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tas settings 日本語 ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.path = self.folder / "config" / "settings.json"

    def write(self, values):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(values), encoding="utf-8")

    def test_missing_file_defaults_without_creating_file(self):
        settings = AppSettings(self.path)
        self.assertEqual(settings.recent_files, ())
        self.assertEqual(settings.get("output_format"), "binary")
        self.assertIs(settings.get("debug_enabled"), False)
        self.assertEqual(settings.get("last_input_directory"), "")
        self.assertEqual(settings.get("last_output_directory"), "")
        self.assertFalse(self.path.exists())

    def test_valid_load_does_not_stat_recent_files_and_ignores_unknown_fields(self):
        source = self.folder / "missing 日本語.tsv"
        self.write(dict(version=1, recent_files=[str(source)], output_format="stas",
                        debug_enabled=True, last_input_directory=str(self.folder),
                        last_output_directory=str(self.folder), unknown="ignored"))
        with patch.object(Path, "is_file", side_effect=AssertionError("startup stat")), \
             patch.object(Path, "is_dir", side_effect=AssertionError("startup stat")):
            settings = AppSettings(self.path)
        self.assertEqual(settings.recent_files, (str(source),))
        self.assertEqual(settings.get("output_format"), "stas")
        self.assertTrue(settings.get("debug_enabled"))
        self.assertEqual(settings.get("last_input_directory"), str(self.folder))
        self.assertEqual(settings.get("last_output_directory"), str(self.folder))
        self.assertIsNone(settings.get("unknown"))
        copied = settings.get("recent_files")
        copied.clear()
        self.assertEqual(settings.recent_files, (str(source),))

    def test_corrupt_json_encoding_and_old_schema_fall_back(self):
        self.path.parent.mkdir()
        for data in (b"{broken", b"\xff", b"null", b"[]",
                     b'{"version": 0, "output_format": "stas"}',
                     b'{"version": true, "debug_enabled": true}',
                     b'{"output_format": "nxtas"}'):
            with self.subTest(data=data):
                self.path.write_bytes(data)
                settings = AppSettings(self.path)
                self.assertEqual(settings.get("output_format"), "binary")
                self.assertFalse(settings.get("debug_enabled"))
                self.assertEqual(settings.recent_files, ())

    def test_invalid_types_formats_and_paths_fall_back_independently(self):
        for invalid in (None, 1, True, [], {}, "unknown"):
            with self.subTest(invalid=invalid):
                self.write(dict(version=1, output_format=invalid, debug_enabled="false",
                                recent_files="not a list", last_input_directory=42,
                                last_output_directory="relative/path"))
                settings = AppSettings(self.path)
                self.assertEqual(settings.get("output_format"), "binary")
                self.assertFalse(settings.get("debug_enabled"))
                self.assertEqual(settings.recent_files, ())
                self.assertEqual(settings.get("last_input_directory"), "")
                self.assertEqual(settings.get("last_output_directory"), "")
        self.write(dict(version=1, output_format="nxtas", debug_enabled=1,
                        recent_files=[None, 42, "relative.tsv", "\0.tsv", str(self.folder / "x.png")]))
        settings = AppSettings(self.path)
        self.assertEqual(settings.get("output_format"), "nxtas")
        self.assertFalse(settings.get("debug_enabled"))
        self.assertEqual(settings.recent_files, ())

    def test_config_paths_windows_xdg_and_home_fallback_ignore_cwd_and_bundle(self):
        home = self.folder / "home"
        appdata = self.folder / "Roaming"
        xdg = self.folder / "xdg"
        for platform, environment, expected in (
            ("win32", {"APPDATA": str(appdata)}, appdata),
            ("win32", {}, home / "AppData" / "Roaming"),
            ("win32", {"APPDATA": "relative"}, home / "AppData" / "Roaming"),
            ("linux", {"XDG_CONFIG_HOME": str(xdg)}, xdg),
            ("linux", {}, home / ".config"),
            ("linux", {"XDG_CONFIG_HOME": "relative"}, home / ".config"),
            ("linux", {"XDG_CONFIG_HOME": "\0"}, home / ".config"),
        ):
            with self.subTest(platform=platform, environment=environment), \
                 patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "_MEIPASS", "bundle", create=True), \
                 patch("os.getcwd", side_effect=AssertionError("CWD dependency")):
                self.assertEqual(settings_path(platform, environment, home),
                                 expected / APP_NAME / "settings.json")
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(xdg)}), \
             patch("python_to_exe.app_settings.sys.platform", "linux"):
            self.assertEqual(AppSettings().path, xdg / APP_NAME / "settings.json")

    def test_recent_normalization_deduplication_limit_and_clear_persist(self):
        settings = AppSettings(self.path)
        paths = [self.folder / f"file {i} 日本語.tsv" for i in range(12)]
        for path in paths:
            settings.add_recent(path)
        self.assertEqual(settings.recent_files, tuple(str(p) for p in reversed(paths[2:])))
        equivalent = self.folder / "child" / ".." / paths[5].name
        settings.add_recent(equivalent)
        self.assertEqual(settings.recent_files[0], str(paths[5]))
        self.assertEqual(settings.recent_files.count(str(paths[5])), 1)
        self.assertEqual(settings.get("last_input_directory"), str(self.folder))
        settings.remove_recent(paths[5])
        self.assertNotIn(str(paths[5]), AppSettings(self.path).recent_files)
        settings.clear_recent()
        self.assertEqual(AppSettings(self.path).recent_files, ())
        self.assertEqual(settings.get("last_input_directory"), str(self.folder))

    def test_recent_native_case_normalization(self):
        settings = AppSettings(self.path)
        with patch("python_to_exe.app_settings.os.path.normcase", side_effect=lambda path: path.lower()):
            settings.add_recent(self.folder / "FIRST.tsv")
            settings.add_recent(self.folder / "first.tsv")
            self.assertEqual(settings.recent_files, (str(self.folder / "first.tsv"),))

    def test_only_whitelisted_fields_are_saved(self):
        settings = AppSettings(self.path)
        settings.update(output_format="stas", debug_enabled=True, ftp_enabled=True,
                        password="not stored", ip="not stored", username="not stored",
                        port=5000, document="not stored", undo=["not stored"], frames=[1])
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(set(saved), {"version", "recent_files", "output_format", "debug_enabled",
                                      "last_input_directory", "last_output_directory",
                                      "editor_width", "editor_height", "editor_view",
                                      "editor_palette_page", "editor_column_widths",
                                      "dopagaki_intensity"})
        self.assertEqual(saved["version"], 1)
        self.assertNotIn("not stored", self.path.read_text(encoding="utf-8"))

    def test_atomic_replace_receives_complete_closed_file(self):
        settings = AppSettings(self.path)
        original_replace = os.replace
        observed = []

        def replace(source, target):
            self.assertEqual(Path(source).parent, self.path.parent)
            observed.append(json.loads(Path(source).read_text(encoding="utf-8")))
            # Opening/removing this file is also possible on Windows: fdopen has closed it.
            original_replace(source, target)

        with patch("python_to_exe.app_settings.os.replace", side_effect=replace):
            settings.update(debug_enabled=True)
        self.assertTrue(observed[0]["debug_enabled"])
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_save_failure_keeps_old_file_and_shared_memory_usable(self):
        settings = AppSettings(self.path)
        self.assertTrue(settings.save())
        original = self.path.read_bytes()
        with patch("python_to_exe.app_settings.os.replace", side_effect=OSError("read only")):
            settings.update(debug_enabled=True)
            self.assertFalse(settings.save())
        self.assertTrue(settings.get("debug_enabled"))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        with patch("python_to_exe.app_settings.settings_path", side_effect=RuntimeError("no home")):
            unavailable = AppSettings()
        unavailable.add_recent(self.folder / "new.tsv")
        self.assertIsNone(unavailable.path)
        self.assertFalse(unavailable.save())

    def test_dialog_initialdir_only_for_existing_directory(self):
        settings = AppSettings(self.path)
        settings.update(last_input_directory=str(self.folder),
                        last_output_directory=str(self.folder / "missing"))
        self.assertEqual(settings.dialog_options("last_input_directory"),
                         {"initialdir": str(self.folder)})
        self.assertEqual(settings.dialog_options("last_output_directory"), {})
        with patch.object(Path, "is_dir", side_effect=OSError("access denied")):
            self.assertEqual(settings.dialog_options("last_input_directory"), {})
