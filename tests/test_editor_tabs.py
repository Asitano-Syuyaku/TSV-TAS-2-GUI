"""Browser-style tabs: one Editor window, one document per tab."""

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp


class EditorTabsTkTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="tas tabs 日本語 ")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.settings = AppSettings(self.folder / "settings.json")
        self.settings.update(editor_maximized=False)

    def make_app(self):
        try:
            app = TASConverterApp("en", settings=self.settings)
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(lambda: app.destroy() if app._tclCommands is not None else None)
        app.update()
        return app

    def file(self, name, text="1\ta\n"):
        path = self.folder / name
        path.write_text(text, encoding="utf-8")
        return path

    @staticmethod
    def names(editor):
        return [tab.chip.name.cget("text") for tab in editor._tabs]

    def test_tabs_keep_their_own_document_undo_and_view(self):
        app = self.make_app()
        first, second = self.file("first.tsv"), self.file("second.tsv", "2\tb\n")
        editor = app._create_editor(initial_path=first)
        app.update()
        self.assertEqual(self.names(editor), ["first.tsv"])
        editor.text.insert("end-1c", "// first edit")
        editor._on_modified()
        first_tab = editor._tab
        self.assertTrue(editor.open_file(second))
        self.assertTrue(editor.show_table())
        app.update()
        self.assertEqual(self.names(editor), ["first.tsv", "second.tsv"])
        self.assertEqual(first_tab.chip.dot.cget("text"), "●")  # Unsaved, in the background.
        self.assertEqual(editor._tab.chip.dot.cget("text"), "")
        self.assertEqual((editor.document.path, editor._view), (second, "table"))

        self.assertTrue(editor._activate_tab(first_tab))
        app.update()
        self.assertEqual((editor.document.path, editor._view), (first, "raw"))
        self.assertIn("// first edit", editor.text.get("1.0", "end-1c"))
        self.assertTrue(editor.document.modified)
        self.assertTrue(editor.undo())  # The first tab's own history.
        self.assertEqual(editor.text.get("1.0", "end-1c"), "1\ta\n")
        self.assertIn(first.name, editor.title())

        editor._next_tab(1)
        app.update()
        self.assertEqual((editor.document.path, editor._view), (second, "table"))
        self.assertTrue(editor.table_grid.winfo_ismapped())
        editor._next_tab(1)
        self.assertIs(editor._tab, first_tab)

    def test_open_shows_an_open_file_and_close_tab_asks_then_last_closes_window(self):
        app = self.make_app()
        first, second = self.file("first.tsv"), self.file("second.tsv")
        editor = app._create_editor(initial_path=first)
        app.update()
        first_tab = editor._tab
        self.assertTrue(editor.open_file(second))
        self.assertTrue(editor.open_file(first))  # Already open: no duplicate tab.
        self.assertIs(editor._tab, first_tab)
        self.assertEqual(len(editor._tabs), 2)

        editor.text.insert("end-1c", "// unsaved")
        editor._on_modified()
        with patch("python_to_exe.editor.window.messagebox.askyesnocancel", return_value=None) as ask:
            self.assertFalse(editor.close_tab())
            ask.assert_called_once()
        self.assertEqual(len(editor._tabs), 2)
        with patch("python_to_exe.editor.window.messagebox.askyesnocancel", return_value=False):
            self.assertTrue(editor.close_tab())  # Discard: the neighbour shows.
        self.assertEqual(self.names(editor), ["second.tsv"])
        self.assertEqual(editor.document.path, second)
        self.assertEqual(first.read_text(encoding="utf-8"), "1\ta\n")

        self.assertTrue(editor.new_document())
        self.assertEqual(self.names(editor), ["second.tsv", "Untitled"])
        self.assertEqual(editor._shortcut(editor.close_tab), "break")  # Ctrl+W.
        self.assertEqual(self.names(editor), ["second.tsv"])
        self.assertTrue(editor.close_tab())  # The last tab closes the Editor.
        app.update()
        self.assertFalse(editor.winfo_exists())

    def test_converter_opens_files_as_tabs_of_the_open_editor(self):
        app = self.make_app()
        first, second = self.file("first.tsv"), self.file("second.tsv")
        app._set_input_path(first)
        editor = app.open_editor()
        app.update()
        app._set_input_path(second)
        self.assertIs(app.open_editor(), editor)
        app.update()
        windows = [child for child in app.winfo_children() if hasattr(child, "open_tab")]
        self.assertEqual(windows, [editor])
        self.assertEqual(self.names(editor), ["first.tsv", "second.tsv"])
        self.assertEqual(editor.document.path, second)
        app._set_input_path(first)
        app.open_editor()
        self.assertEqual(editor.document.path, first)
        self.assertEqual(len(editor._tabs), 2)

    def test_background_tab_result_waits_until_the_tab_is_shown(self):
        app = self.make_app()
        first, second = self.file("first.tsv"), self.file("second.tsv")
        editor = app._create_editor(initial_path=first)
        app.update()
        requests = []
        editor.on_validate = lambda snapshot, receive: requests.append(receive) or True
        editor.can_validate = lambda: True
        self.assertTrue(editor.validate())
        first_tab = editor._tab
        self.assertTrue(editor.open_file(second))
        requests[0](SimpleNamespace(success=True, text="", problems=lambda lines: ()))
        app.update()
        self.assertFalse(editor._problems_panel.winfo_ismapped())  # Not on this tab.
        self.assertTrue(first_tab.state["_validation_pending"])
        self.assertTrue(editor._activate_tab(first_tab))
        app.update()
        self.assertFalse(editor._validation_pending)
        self.assertTrue(editor._problems_panel.winfo_ismapped())
        self.assertEqual(editor._problems_title.cget("text"), editor.words["no_errors"])
        editor._next_tab(1)
        app.update()
        self.assertFalse(editor._problems_panel.winfo_ismapped())  # Problems are per tab.


if __name__ == "__main__":
    unittest.main()
