import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class FakeToplevel:
    def title(self, value):
        self.window_title = value

    def destroy(self):
        self.destroyed = True


class FakeText:
    def __init__(self):
        self.value = ""
        self.modified = False

    def get(self, start, end):
        return self.value

    def delete(self, start, end):
        self.value = ""

    def insert(self, start, value):
        self.value = value

    def edit_modified(self, value=None):
        if value is None:
            return self.modified
        self.modified = value


class EditorWindowHeadlessTests(unittest.TestCase):
    def test_unsaved_prompts_title_and_open(self):
        fake_tk = types.ModuleType("tkinter")
        fake_tk.Toplevel = FakeToplevel
        fake_tk.filedialog = types.SimpleNamespace()
        fake_tk.font = types.SimpleNamespace()
        fake_tk.messagebox = types.SimpleNamespace(askyesnocancel=lambda *args, **kwargs: None)
        with patch.dict(sys.modules, {"tkinter": fake_tk}):
            sys.modules.pop("python_to_exe.editor.window", None)
            module = importlib.import_module("python_to_exe.editor.window")
            window = module.EditorWindow.__new__(module.EditorWindow)
            window.words = module.LABELS["en"]
            window.document = module.EditorDocument()
            window.text = FakeText()
            window.destroyed = False
            window.text.value = "1\ta"
            window._sync_text()
            self.assertIn("Untitled *", window.window_title)

            fake_tk.filedialog.askopenfilename = lambda **kwargs: ""
            fake_tk.messagebox.askyesnocancel = lambda *args, **kwargs: self.fail(
                "Canceling the file dialog must not ask to discard changes")
            self.assertFalse(window.open_file())
            fake_tk.messagebox.askyesnocancel = lambda *args, **kwargs: None
            self.assertFalse(window.new_document())
            self.assertEqual(window.text.value, "1\ta")
            self.assertFalse(window.close_editor())
            self.assertFalse(window.destroyed)

            fake_tk.messagebox.askyesnocancel = lambda *args, **kwargs: False
            self.assertTrue(window.new_document())
            self.assertFalse(window.document.modified)
            self.assertEqual(window.text.value, "")

            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "example.txt"
                source.write_text("0\tKEY_A", encoding="utf-8")
                self.assertTrue(window.open_file(source))
                self.assertEqual(window.text.value, "0\tKEY_A")
                self.assertIn("example.txt", window.window_title)
                window.text.value = "changed"
                fake_tk.messagebox.askyesnocancel = lambda *args, **kwargs: True
                window.save = lambda: False
                self.assertFalse(window.close_editor())
                self.assertFalse(window.destroyed)
                window.save = lambda: True
                self.assertTrue(window.close_editor())
                self.assertTrue(window.destroyed)
        sys.modules.pop("python_to_exe.editor.window", None)


if __name__ == "__main__":
    unittest.main()
