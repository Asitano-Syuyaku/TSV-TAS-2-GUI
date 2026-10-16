"""Windows display setup: DPI awareness, readable fonts and the pixel scale."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from python_to_exe import display
from python_to_exe.editor import theme


class DisplayTests(unittest.TestCase):
    def tearDown(self):
        theme.set_ui_scale(1.0)

    def test_everything_is_a_no_op_off_windows(self):
        self.assertEqual(display.enable_dpi_awareness("linux"), "not-windows")
        self.assertFalse(display.configure_root(object(), "linux"))
        self.assertEqual(theme.px(400), 400)

    def test_scale_follows_windows_dpi_and_never_shrinks(self):
        root = SimpleNamespace(winfo_fpixels=lambda length: 144.0)  # 150% display.
        fonts = {}
        with patch("tkinter.font.families", return_value=("Meiryo UI", "Arial")), \
             patch("tkinter.font.nametofont",
                   side_effect=lambda name, root: SimpleNamespace(
                       configure=lambda **options: fonts.__setitem__(name, options))):
            self.assertTrue(display.configure_root(root, "win32"))
        self.assertEqual((theme.px(400), theme.px(26), theme.px(1)), (600, 39, 2))
        self.assertEqual(fonts["TkDefaultFont"], {"family": "Meiryo UI", "size": 9})
        self.assertEqual(fonts["TkFixedFont"], {"family": "Meiryo UI", "size": 10})
        theme.set_ui_scale(0.5)  # Below 96 DPI: never smaller than the design.
        self.assertEqual(theme.px(400), 400)

    def test_display_setup_failure_never_blocks_startup(self):
        def broken(_length):
            raise RuntimeError("no display")

        self.assertFalse(display.configure_root(SimpleNamespace(winfo_fpixels=broken), "win32"))
        self.assertEqual(theme.px(400), 400)
        with patch("tkinter.font.families", return_value=("Arial",)), \
             patch("tkinter.font.nametofont") as rename:
            self.assertTrue(display.configure_root(
                SimpleNamespace(winfo_fpixels=lambda length: 120.0), "win32"))
            rename.assert_not_called()  # Without Meiryo UI the OS fonts stay.
        self.assertEqual(theme.px(400), 500)
