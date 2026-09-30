"""Basic/Advanced palette layout, state isolation and real Tk interaction."""

import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from python_to_exe.app_settings import AppSettings
from python_to_exe.editor.tsv_syntax import CANDIDATES, PALETTE_CATEGORIES, PALETTE_PAGES
from python_to_exe.editor.window import EditorWindow


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class PalettePageDefinitionTests(unittest.TestCase):
    def test_pages_and_existing_advanced_templates(self):
        self.assertEqual(PALETTE_PAGES, (
            ("buttons", "left_stick", "right_stick", "commands"),
            ("cappy", "accel", "gyro", "notation"),
        ))
        self.assertEqual(PALETTE_CATEGORIES,
                         tuple(category for page in PALETTE_PAGES for category in page))
        self.assertFalse(set(PALETTE_PAGES[0]) & set(PALETTE_PAGES[1]))
        advanced = [item for category in PALETTE_PAGES[1]
                    for item in CANDIDATES if item.category == category]
        self.assertEqual([(item.text, item.select) for item in advanced], [
            ("ca", None), ("cb", None), ("cx", None), ("cy", None),
            ("cls(0)", (4, 5)), ("crs(0)", (4, 5)),
            ("la(0; 0; 0)", (3, 4)), ("ra(0; 0; 0)", (3, 4)),
            ("lg(0; 0; 0)", (3, 4)), ("rg(0; 0; 0)", (3, 4)),
            ("// ", None), ("$name = ", None), ("a/b", None), ("a|b", None),
            ("ls(0)->ls(90)", None), ("[2]a", None),
        ])


class PalettePageTkTests(unittest.TestCase):
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

    def make_editor(self, root, **options):
        editor = EditorWindow(root, **options)
        self.addCleanup(editor.destroy)
        editor.show_table()
        root.update()
        return editor

    def test_jp_en_page_order_layout_and_navigation_limits(self):
        root = self.make_root()
        for language in ("ja", "en"):
            editor = self.make_editor(root, language=language)
            self.assertEqual(editor._palette_page, 1)
            self.assertEqual(editor._palette_previous.cget("state"), "disabled")
            self.assertEqual(editor._palette_next.cget("state"), "normal")
            for number, categories in enumerate(PALETTE_PAGES, start=1):
                editor._show_palette_page(number)
                root.update()
                self.assertEqual(editor._palette_page_label.cget("text"), f"{number} / 2")
                self.assertEqual(editor.input_palette.winfo_width(), 330)
                page, canvas = editor._palette_pages[number - 1]
                content = canvas.winfo_children()[0]
                headings = [child.cget("text") for child in content.winfo_children()
                            if isinstance(child, tk.Label)]
                self.assertEqual(headings, [editor.words[category] for category in categories])
                self.assertTrue(page.winfo_ismapped())
                self.assertFalse(editor._palette_pages[2 - number][0].winfo_ismapped())
                buttons = [child for child in descendants(page) if isinstance(child, tk.Button)]
                expected = [item for category in categories
                            for item in CANDIDATES if item.category == category]
                self.assertEqual(len(buttons), len(expected))
                for button, candidate in zip(buttons, expected):
                    self.assertEqual(button.cget("text"), candidate.short_label
                                     if candidate.icon_key else candidate.display_label)
                    self.assertLessEqual(button.winfo_reqwidth(), button.winfo_width())
                    if candidate.category in ("gyro", "notation"):
                        self.assertEqual(int(button.grid_info()["columnspan"]), 2)
                    if number == 2:
                        self.assertFalse(button.cget("image"))
            self.assertEqual(editor._palette_next.cget("state"), "disabled")
            editor._palette_next.invoke()
            self.assertEqual(editor._palette_page, 2)
            editor._palette_previous.invoke()
            self.assertEqual(editor._palette_page, 1)
            editor._palette_previous.invoke()
            self.assertEqual(editor._palette_page, 1)
            editor._show_palette_page(0)
            editor._show_palette_page(3)
            self.assertEqual(editor._palette_page, 1)

    def test_page_switch_preserves_document_selection_history_and_pending_entry(self):
        root = self.make_root()
        editor = self.make_editor(root)
        editor.show_raw()
        value = "1\told\t\n1\t日本語"
        editor.text.insert("1.0", value)
        editor.text.edit_separator()
        root.update()
        editor.show_table()
        grid = editor.table_grid
        grid.selection.move_to(0, 1)
        grid.selection.move_to(1, 2, extend=True)
        state = (grid.selection.anchor, grid.selection.active, grid.selection.bounds,
                 editor.document.text, editor.document.modified, editor._position_revision)
        pages = tuple(editor._palette_pages)
        images = tuple(editor._palette_icons.values())
        for _ in range(20):
            editor._palette_next.invoke()
            editor._palette_previous.invoke()
        self.assertEqual(state, (grid.selection.anchor, grid.selection.active, grid.selection.bounds,
                                 editor.document.text, editor.document.modified, editor._position_revision))
        self.assertEqual(tuple(editor._palette_pages), pages)
        self.assertEqual(tuple(editor._palette_icons.values()), images)
        editor.undo()
        self.assertEqual(editor.document.text, "")
        editor.redo()
        self.assertEqual(editor.document.text, value)
        grid.selected = (0, 1)
        grid.begin_edit()
        entry = grid._editor
        entry.delete(0, "end")
        entry.insert(0, "pending")
        entry.select_range(1, 3)
        entry.icursor(3)
        entry.focus_force()
        root.update()
        selection = (grid.selection.anchor, grid.selection.active)
        editor._palette_next.event_generate("<Enter>")
        editor._palette_next.event_generate("<ButtonPress-1>", x=4, y=4)
        editor._palette_next.event_generate("<ButtonRelease-1>", x=4, y=4)
        root.update()
        self.assertEqual(editor._palette_page, 2)
        self.assertIs(grid._editor, entry)
        self.assertEqual(entry.get(), "pending")
        self.assertEqual((entry.index("sel.first"), entry.index("sel.last"), entry.index("insert")),
                         (1, 3, 3))
        self.assertEqual((grid.selection.anchor, grid.selection.active), selection)
        self.assertIs(editor.focus_get(), entry)
        self.assertEqual(editor.document.text, value)
        self.assertTrue(editor.document.modified)
        grid.cancel_edit()

    def test_advanced_buttons_insert_into_active_cell_and_keep_template_selection(self):
        root = self.make_root()
        editor = self.make_editor(root)
        editor._palette_next.invoke()
        root.update()
        page, _canvas = editor._palette_pages[1]
        buttons = [child for child in descendants(page) if isinstance(child, tk.Button)]
        expected = [item for category in PALETTE_PAGES[1]
                    for item in CANDIDATES if item.category == category]
        for button, candidate in zip(buttons, expected):
            with self.subTest(candidate=candidate.label):
                grid = editor.table_grid
                grid.selected = (0, 1)
                button.invoke()
                self.assertEqual(grid._editor.get(), candidate.text)
                if candidate.select:
                    self.assertEqual((grid._editor.index("sel.first"), grid._editor.index("sel.last")),
                                     candidate.select)
                self.assertEqual(grid.selected, (0, 1))
                self.assertFalse(editor.document.modified)
                grid.cancel_edit()
        # A commit participates in the shared Raw/Table Undo/Redo history.
        buttons[0].invoke()
        editor.table_grid.commit_edit()
        self.assertEqual(editor.document.text, "\tca")
        self.assertTrue(editor.document.modified)
        editor.undo()
        self.assertEqual(editor.document.text, "")
        self.assertFalse(editor.document.modified)
        editor.redo()
        self.assertEqual(editor.document.text, "\tca")

    def test_page_state_survives_document_and_converter_actions(self):
        root = self.make_root()
        calls = []
        editor = self.make_editor(root, on_convert=lambda path, send_ftp=False: calls.append(path) or True,
                                  on_validate=lambda _path, _receive: True)
        editor._show_palette_page(2)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "script 日本語.tsv"
            path.write_text("1\ta", encoding="utf-8")
            self.assertTrue(editor.open_file(path))
            self.assertEqual(editor._palette_page, 2)
            self.assertTrue(editor.save())
            self.assertTrue(editor.validate())
            self.assertTrue(editor.save_and_convert())
            self.assertEqual(calls, [path])
            self.assertEqual(editor._palette_page, 2)
            self.assertTrue(editor.new_document())
            self.assertEqual(editor._palette_page, 2)
            editor.show_table()
            editor.show_raw()
            editor.show_table()
            self.assertEqual(editor._palette_page, 2)

    def test_wheel_is_local_and_each_page_remembers_scroll(self):
        root = self.make_root()
        editor = self.make_editor(root)
        editor.geometry("1200x400")
        root.update()
        basic = editor.palette_canvas
        table_view = editor.table_grid.canvas.yview()
        button = next(child for child in descendants(editor._palette_pages[0][0])
                      if isinstance(child, tk.Button))
        button.event_generate("<MouseWheel>", delta=-120)
        root.update()
        basic_view = basic.yview()
        self.assertGreater(basic_view[0], 0)
        self.assertEqual(editor.table_grid.canvas.yview(), table_view)
        editor._palette_next.invoke()
        root.update()
        advanced = editor.palette_canvas
        advanced.event_generate("<Button-5>")
        self.assertGreater(advanced.yview()[0], 0)
        advanced.event_generate("<Button-4>")
        self.assertEqual(advanced.yview()[0], 0)
        editor._palette_previous.invoke()
        root.update()
        self.assertEqual(basic.yview(), basic_view)
        self.assertFalse(editor.document.modified)
