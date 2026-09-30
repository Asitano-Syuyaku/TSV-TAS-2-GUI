"""Headless safeguards for Editor-only presentation helpers."""

import subprocess
import sys
import unittest
from unittest.mock import patch

from python_to_exe.editor import theme


class EditorThemeTests(unittest.TestCase):
    def test_theme_import_is_display_independent_and_has_shared_tokens(self):
        result = subprocess.run(
            [sys.executable, "-c", "import sys; from python_to_exe.editor import theme; "
             "assert 'tkinter' not in sys.modules"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        required = {"app_background", "panel_background", "secondary_background", "border",
                    "subtle_border", "text", "muted_text", "accent", "accent_hover",
                    "selection_background", "active_selection_outline", "success", "warning", "error"}
        self.assertTrue(required.issubset(theme.COLORS))
        for color in theme.COLORS.values():
            self.assertRegex(color, r"^#[0-9a-fA-F]{6}$")
        self.assertTrue({"standard", "small", "heading"}.issubset(theme.FONTS))
        self.assertNotEqual(theme.COLORS["app_background"], theme.COLORS["panel_background"])
        self.assertLess(theme.LINE_WIDTHS["grid"], theme.LINE_WIDTHS["active"])

    def test_style_helpers_do_not_supply_document_or_action_state(self):
        for options in (theme.button_options(), theme.button_options("palette"),
                        theme.button_options(selected=True), theme.entry_options(),
                        theme.label_options(role="small")):
            self.assertTrue({"text", "command", "state", "textvariable", "variable",
                             "undo", "width", "height"}.isdisjoint(options))
        before = theme.button_options("palette")
        changed = theme.button_options("palette")
        changed["background"] = "other"
        self.assertEqual(theme.button_options("palette"), before)

    def test_fonts_are_local_copies_without_mutating_shared_named_fonts(self):
        for size in (10, -16):
            copies = []

            class FontCopy:
                def __init__(self, **options):
                    # Match Font's source-font behavior: other constructor style
                    # options are ignored and must be applied with configure().
                    self.options = {key: value for key, value in options.items()
                                    if key in ("root", "font")}
                    copies.append(self)

                def actual(self, _key):
                    return size

                def configure(self, **options):
                    self.options.update(options)

            master = object()
            with patch("tkinter.font.Font", FontCopy):
                fonts = theme.editor_fonts(master)
            self.assertEqual(fonts["standard"], theme.FONTS["standard"])
            self.assertEqual(len(copies), 2)
            self.assertTrue(all(copy.options["root"] is master for copy in copies))
            self.assertEqual(fonts["heading"].options["weight"], "bold")
            self.assertLess(abs(fonts["small"].options["size"]), abs(size))
            self.assertEqual(fonts["small"].options["size"] > 0, size > 0)


if __name__ == "__main__":
    unittest.main()
