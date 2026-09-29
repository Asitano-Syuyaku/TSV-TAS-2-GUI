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

    def winfo_exists(self):
        return True


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

    def edit_reset(self):
        self.reset_count = getattr(self, "reset_count", 0) + 1

    def edit_undo(self):
        self.value = self.undo_value

    def edit_redo(self):
        self.value = self.redo_value

    def index(self, name):
        return "1.0"


class FakeStatus:
    def config(self, **kwargs):
        self.value = kwargs["text"]


class EditorWindowHeadlessTests(unittest.TestCase):
    def test_save_and_convert_saves_first_and_stops_on_cancel_or_failure(self):
        fake_tk = types.ModuleType("tkinter")
        fake_tk.Toplevel = FakeToplevel
        fake_tk.filedialog = types.SimpleNamespace()
        fake_tk.font = types.SimpleNamespace()
        errors = []
        fake_tk.messagebox = types.SimpleNamespace(showerror=lambda *args, **kwargs: errors.append(args))
        with patch.dict(sys.modules, {"tkinter": fake_tk}):
            sys.modules.pop("python_to_exe.editor.window", None)
            module = importlib.import_module("python_to_exe.editor.window")
            window = module.EditorWindow.__new__(module.EditorWindow)
            window.words = module.LABELS["en"]
            window.document = module.EditorDocument()
            window.text = FakeText()
            window.status = FakeStatus()
            window._schedule_line_numbers = lambda: None
            events = []
            window.on_saved = lambda path: events.append(("saved", path))
            window.on_convert = lambda path: events.append(("convert", path, Path(path).read_bytes())) or True
            window.can_convert = lambda: True

            with tempfile.TemporaryDirectory(prefix="tas editor 日本語 ") as folder:
                existing = Path(folder) / "script with spaces.tsv"
                existing.write_bytes(b"1\ta\n")
                window.document.open(existing)
                window.text.value = window.document.text
                self.assertTrue(window.save_and_convert())
                self.assertEqual(events, [("convert", existing, b"1\ta\n")])

                window.can_convert = lambda: False
                window.text.value = "1\tbusy\n"
                self.assertFalse(window.save_and_convert())
                self.assertEqual(existing.read_bytes(), b"1\ta\n")
                self.assertEqual(events, [("convert", existing, b"1\ta\n")])
                window.can_convert = lambda: True

                events.clear()
                window.text.value = "1\tb\n"
                self.assertTrue(window.save_and_convert())
                self.assertEqual(events, [("saved", existing), ("convert", existing, b"1\tb\n")])
                self.assertFalse(window.document.modified)

                events.clear()
                window.on_convert = lambda path: events.append(("failed conversion", path)) or False
                window.text.value = "1\tstill here\n"
                self.assertFalse(window.save_and_convert())
                self.assertEqual(existing.read_bytes(), b"1\tstill here\n")
                self.assertEqual(window.document.text, "1\tstill here\n")
                self.assertEqual(events[-1], ("failed conversion", existing))
                window.on_convert = lambda path: events.append(("convert", path, Path(path).read_bytes())) or True

                renamed = Path(folder) / "renamed 日本語.tsv"
                fake_tk.filedialog.asksaveasfilename = lambda **kwargs: str(renamed)
                events.clear()
                self.assertTrue(window.save_as())
                self.assertEqual(events, [("saved", renamed)])
                self.assertTrue(window.save_and_convert())
                self.assertEqual(events[-1], ("convert", renamed, b"1\tstill here\n"))
                self.assertEqual(window.document.path, renamed)

                created = Path(folder) / "新規 with spaces.tsv"
                fake_tk.filedialog.asksaveasfilename = lambda **kwargs: str(created)
                window.document.new()
                window.text.value = "1\tc\n"
                events.clear()
                self.assertTrue(window.save_and_convert())
                self.assertEqual(events, [("saved", created), ("convert", created, b"1\tc\n")])
                self.assertEqual(window.document.path, created)

                fake_tk.filedialog.asksaveasfilename = lambda **kwargs: ""
                window.document.new()
                window.text.value = "1\td\n"
                events.clear()
                self.assertFalse(window.save_and_convert())
                self.assertEqual(events, [])
                self.assertIsNone(window.document.path)

                fake_tk.filedialog.asksaveasfilename = lambda **kwargs: str(Path(folder) / "missing" / "bad.tsv")
                self.assertFalse(window.save_and_convert())
                self.assertEqual(events, [])
                self.assertTrue(window.document.modified)
                self.assertEqual(len(errors), 1)
        sys.modules.pop("python_to_exe.editor.window", None)

    def test_find_and_replace_actions_share_document_state(self):
        fake_tk = types.ModuleType("tkinter")
        fake_tk.Toplevel = FakeToplevel
        fake_tk.filedialog = types.SimpleNamespace()
        fake_tk.font = types.SimpleNamespace()
        fake_tk.messagebox = types.SimpleNamespace()
        with patch.dict(sys.modules, {"tkinter": fake_tk}):
            sys.modules.pop("python_to_exe.editor.window", None)
            module = importlib.import_module("python_to_exe.editor.window")

            class SearchText:
                value = "猫\t犬\t猫"
                cursor = 0
                selection = None

                def offset(self, index):
                    if index == "1.0":
                        return 0
                    if index == "end-1c":
                        return len(self.value)
                    if index == "end":
                        return len(self.value)
                    if index == "insert":
                        return self.cursor
                    if index.startswith("1.0+"):
                        return int(index[4:-1])
                    return int(index.split(".")[1])

                def index(self, index):
                    return f"1.{self.offset(index)}"

                def get(self, start, end):
                    return self.value[self.offset(start):self.offset(end)]

                def tag_ranges(self, name):
                    return tuple(f"1.{index}" for index in self.selection) if self.selection else ()

                def tag_remove(self, name, start, end):
                    self.selection = None

                def tag_add(self, name, start, end):
                    self.selection = (self.offset(start), self.offset(end))

                def mark_set(self, name, index):
                    self.cursor = self.offset(index)

                def see(self, index):
                    pass

                def edit_separator(self):
                    pass

                def delete(self, start, end):
                    first, last = self.offset(start), self.offset(end)
                    self.value = self.value[:first] + self.value[last:]
                    self.cursor = first

                def insert(self, index, value):
                    position = self.offset(index)
                    self.value = self.value[:position] + value + self.value[position:]
                    self.cursor = position + len(value)

            window = module.EditorWindow.__new__(module.EditorWindow)
            window.words = module.LABELS["ja"]
            window.document = module.EditorDocument()
            window.text = SearchText()
            window.status = FakeStatus()
            window.find_query = types.SimpleNamespace(get=lambda: "猫")
            window.replace_value = types.SimpleNamespace(get=lambda: "鳥")
            window._find_dialog = None
            window._schedule_line_numbers = lambda: None
            window._sync_text()

            self.assertTrue(window.find_next())
            self.assertEqual(window.text.selection, (0, 1))
            self.assertTrue(window.find_previous())
            self.assertEqual(window.text.selection, (4, 5))
            self.assertTrue(window.find_next())
            self.assertEqual(window.text.selection, (0, 1))
            self.assertTrue(window.replace_current())
            self.assertEqual(window.text.value, "鳥\t犬\t猫")
            self.assertEqual(window.text.selection, (4, 5))
            self.assertEqual(window.replace_all(), 1)
            self.assertEqual(window.document.text, "鳥\t犬\t鳥")
            self.assertTrue(window.document.modified)
        sys.modules.pop("python_to_exe.editor.window", None)

    def test_line_numbers_only_draw_visible_lines(self):
        fake_tk = types.ModuleType("tkinter")
        fake_tk.Toplevel = FakeToplevel
        fake_tk.filedialog = types.SimpleNamespace()
        fake_tk.font = types.SimpleNamespace()
        fake_tk.messagebox = types.SimpleNamespace()
        with patch.dict(sys.modules, {"tkinter": fake_tk}):
            sys.modules.pop("python_to_exe.editor.window", None)
            module = importlib.import_module("python_to_exe.editor.window")
            window = module.EditorWindow.__new__(module.EditorWindow)
            window._gutter_job = "scheduled"
            window._fixed_font = types.SimpleNamespace(measure=lambda value: len(value) * 8)

            class VisibleText:
                def index(self, name):
                    if name == "end-1c":
                        return "1000000.0"
                    if name == "@0,0":
                        return "999991.0"
                    return f"{int(name.split('.')[0]) + 1}.0"

                def dlineinfo(self, index):
                    line = int(index.split(".")[0])
                    return (0, (line - 999991) * 20, 80, 20) if line <= 1000000 else None

            class Gutter:
                width = 40

                def __init__(self):
                    self.lines = []

                def cget(self, name):
                    return self.width

                def configure(self, **kwargs):
                    self.width = kwargs["width"]

                def delete(self, tag):
                    self.lines.clear()

                def create_text(self, x, y, **kwargs):
                    self.lines.append(kwargs["text"])

            window.text = VisibleText()
            window.line_numbers = Gutter()
            window._draw_line_numbers()
            self.assertEqual(window.line_numbers.lines, [str(n) for n in range(999991, 1000001)])
            self.assertEqual(window.line_numbers.width, 68)
            self.assertIsNone(window._gutter_job)
        sys.modules.pop("python_to_exe.editor.window", None)

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
            window.status = FakeStatus()
            window._gutter_job = None
            window._schedule_line_numbers = lambda: None
            window.destroyed = False
            window.text.value = "1\ta"
            window._sync_text()
            self.assertIn("Untitled *", window.window_title)
            window._update_status()
            self.assertIn("Modified", window.status.value)

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
            self.assertEqual(window.text.reset_count, 1)

            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "example.txt"
                source.write_text("0\tKEY_A", encoding="utf-8")
                self.assertTrue(window.open_file(source))
                self.assertEqual(window.text.value, "0\tKEY_A")
                self.assertIn("example.txt", window.window_title)
                window._update_status()
                self.assertIn("nx-TAS", window.status.value)
                window.text.value = "0\tKEY_A extra"
                window._sync_text()
                self.assertTrue(window.document.modified)
                window.text.undo_value = "0\tKEY_A"
                window.text.redo_value = "0\tKEY_A extra"
                self.assertTrue(window.undo())
                self.assertFalse(window.document.modified)
                self.assertIn("Unmodified", window.status.value)
                self.assertTrue(window.redo())
                self.assertTrue(window.document.modified)
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
