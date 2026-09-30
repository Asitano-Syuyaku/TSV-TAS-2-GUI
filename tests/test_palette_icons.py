"""Palette icon resources and their real Tk presentation."""

import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.editor.resources import palette_icon_path
from python_to_exe.editor.tsv_syntax import CANDIDATES, insert_template
from python_to_exe.editor.window import EditorWindow


BUTTON_KEYS = {
    "a": "button_a", "b": "button_b", "x": "button_x", "y": "button_y",
    "l": "button_l", "r": "button_r", "zl": "button_zl", "zr": "button_zr",
    "plus": "button_plus", "minus": "button_minus",
    "dp-u": "dpad_up", "dp-d": "dpad_down",
    "dp-l": "dpad_left", "dp-r": "dpad_right",
    "ls": "stick_left_click", "rs": "stick_right_click",
}


def buttons_in(widget):
    for child in widget.winfo_children():
        if isinstance(child, tk.Button):
            yield child
        yield from buttons_in(child)


class PaletteAssetTests(unittest.TestCase):
    def test_all_button_icons_keep_original_insertion_values(self):
        buttons = [item for item in CANDIDATES if item.category == "buttons"]
        self.assertEqual({item.text: item.icon_key for item in buttons}, BUTTON_KEYS)
        for item in buttons:
            self.assertEqual(insert_template("", 0, 0, item)[0], item.text)
            self.assertTrue(palette_icon_path(item.icon_key).is_file())
        self.assertEqual((BUTTON_KEYS["plus"], BUTTON_KEYS["minus"]),
                         ("button_plus", "button_minus"))
        self.assertEqual({item.text: item.short_label for item in buttons
                          if item.text in ("ls", "rs")},
                         {"ls": "stick", "rs": "stick"})
        self.assertTrue(all(item.icon_key is None for item in CANDIDATES
                            if item.category != "buttons"))

    def test_source_and_frozen_paths_are_independent_of_cwd(self):
        source = Path(__file__).resolve().parents[1] / "assets/icons/png/button_a.png"
        self.assertEqual(palette_icon_path("button_a"), source)
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(sys, "_MEIPASS", folder, create=True):
                self.assertEqual(palette_icon_path("button_a"), source)
                with patch.object(sys, "frozen", True, create=True):
                    self.assertEqual(palette_icon_path("button_a"),
                                     Path(folder) / "assets/icons/png/button_a.png")
        self.assertEqual(palette_icon_path("button_a"), source)

    def test_documented_pyinstaller_commands_bundle_only_png(self):
        root = Path(__file__).resolve().parents[1]
        for readme in ("README.md", "README_EN.md"):
            lines = (root / readme).read_text(encoding="utf-8").splitlines()
            builds = [line for line in lines if "python -m PyInstaller" in line]
            self.assertEqual(len(builds), 2)
            for line in builds:
                self.assertIn('--add-data "assets/icons/png:assets/icons/png"', line)
                self.assertNotIn("assets/icons/source", line)
                self.assertNotIn("render_png.py", line)


class PaletteTkTests(unittest.TestCase):
    def make_root(self):
        settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(settings_dir.cleanup)
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        root.withdraw()
        root._tas_app_settings = AppSettings(Path(settings_dir.name) / "settings.json")
        self.addCleanup(root.destroy)
        return root

    def test_japanese_and_english_show_all_sixteen_icons_in_two_columns(self):
        root = self.make_root()
        for language in ("ja", "en"):
            editor = EditorWindow(root, language=language)
            try:
                self.assertEqual(set(editor._palette_icons), set(BUTTON_KEYS.values()))
                self.assertTrue(editor.show_table())
                root.update()
                self.assertEqual(editor.input_palette.cget("width"), 330)
                self.assertEqual(editor.input_palette.winfo_manager(), "pack")
                self.assertEqual(editor.input_palette.winfo_width(), 330)
                palette_buttons = list(buttons_in(editor.input_palette))
                icon_buttons = []
                for item in (item for item in CANDIDATES if item.category == "buttons"):
                    button = next(button for button in palette_buttons
                                  if button.cget("image") == str(editor._palette_icons[item.icon_key]))
                    icon_buttons.append(button)
                    self.assertEqual(button.cget("text"), item.short_label)
                    self.assertEqual(button.cget("image"), str(editor._palette_icons[item.icon_key]))
                    self.assertEqual(button.cget("compound"), "left")
                    self.assertIn(int(button.grid_info()["column"]), (0, 1))
                    self.assertGreaterEqual(button.winfo_height(), 24)
                self.assertEqual(len({button.winfo_height() for button in icon_buttons}), 1)
                self.assertTrue(all(icon.width() == icon.height() == 24
                                    for icon in editor._palette_icons.values()))
                self.assertTrue(any(isinstance(child, tk.Scrollbar)
                                    for child in editor.palette_canvas.master.winfo_children()))
                self.assertTrue(editor.show_raw())
                self.assertTrue(editor.show_table())
                self.assertEqual(len(editor._palette_icons), 16)
            finally:
                editor.destroy()

    def test_missing_or_corrupt_icon_falls_back_without_blocking_editor(self):
        root = self.make_root()
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "button_a.png"
            bad.write_bytes(b"not a PNG")
            with patch.dict(EditorWindow._load_palette_icons.__globals__,
                            {"palette_icon_path": lambda key: (
                                Path(folder) / f"{key}.png"
                                if key in ("button_a", "button_plus") else palette_icon_path(key))}):
                editor = EditorWindow(root, language="en")
            try:
                self.assertEqual(set(editor._palette_icons),
                                 set(BUTTON_KEYS.values()) - {"button_a", "button_plus"})
                self.assertTrue(editor.show_table())
                root.update()
                palette_buttons = list(buttons_in(editor.input_palette))
                self.assertTrue(any(button.cget("text") == "a" and
                                    not button.cget("image") for button in palette_buttons))
                self.assertTrue(any(button.cget("text") == "plus" and
                                    not button.cget("image") for button in palette_buttons))
                self.assertTrue(any(button.cget("text") == "B" and
                                    button.cget("image") for button in palette_buttons))
            finally:
                editor.destroy()
