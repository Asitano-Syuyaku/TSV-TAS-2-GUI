"""Basic/Advanced palette layout, state isolation and real Tk interaction."""

import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from python_to_exe.app_settings import AppSettings
from python_to_exe.editor.tsv_syntax import (CANDIDATES, PALETTE_CATEGORIES, PALETTE_PAGES,
                                             candidates_for, palette_items)
from python_to_exe.editor.window import EditorWindow


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class PalettePageDefinitionTests(unittest.TestCase):
    def test_pages_and_existing_advanced_templates(self):
        self.assertEqual(PALETTE_PAGES, (
            ("buttons", "motion", "left_stick", "right_stick", "stick_preview"),
            ("commands", "script_info", "cappy", "accel", "gyro", "notation"),
        ))
        self.assertEqual(PALETTE_CATEGORIES,
                         tuple(category for page in PALETTE_PAGES for category in page
                               if category != "stick_preview"))
        self.assertFalse(set(PALETTE_PAGES[0]) & set(PALETTE_PAGES[1]))
        advanced = [item for category in PALETTE_PAGES[1] for item in palette_items(category)]
        self.assertEqual([(item.text, item.select) for item in advanced], [
            ("/tp 0 0 0", (4, 9)), ("/absStick on", (10, 12)), ("/absStick off", (10, 13)),
            ("/speed 10", (7, 9)), ("/section TASer", (9, 14)),
            ("$stage = StageName", (9, 18)), ("$entrance = EntranceName", (12, 24)),
            ("$scenario = 1", (12, 13)), ("$pos = (0;0;0)", (8, 13)),
            ("$is2p = true", (8, 12)), ("$author = name", (10, 14)),
            ("ca", None), ("cb", None), ("cx", None), ("cy", None),
            ("cls(0)", (4, 5)), ("crs(0)", (4, 5)),
            ("la(0; 0; 0)", (3, 4)), ("ra(0; 0; 0)", (3, 4)),
            ("lg(0; 0; 0)", (3, 4)), ("rg(0; 0; 0)", (3, 4)),
            ("// ", None), ("$name = ", None), ("a/b", None), ("a|b", None),
            ("ls(0)->ls(90)", None), ("[2]a", None),
        ])
        self.assertEqual([item.label for item in advanced[:11]], [
            "/tp x y z", "/absStick on", "/absStick off", "/speed 10", "/section TASer",
            "$stage = StageName", "$entrance = EntranceName", "$scenario = 1",
            "$pos = (0;0;0)", "$is2p = true", "$author = name"])
        self.assertTrue(all(item.own_row for item in advanced[:11]))
        self.assertFalse(any(item.own_row for item in advanced[11:]))

    def test_commands_left_off_the_palette_still_complete(self):
        hidden = [item.text for item in CANDIDATES
                  if item.category == "commands" and not item.palette]
        self.assertEqual(hidden, ["/ctp 0 0 0", "/pause", "/loadFile 1", "/reloadFile", "/demo on"])
        completed = [item.text for item in candidates_for("/", 1, 0)]
        for text in hidden + ["/tp 0 0 0", "/absStick off", "/speed 10"]:
            self.assertIn(text, completed)


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
                self.assertEqual(editor.input_palette.winfo_width(), 400)
                page, canvas = editor._palette_pages[number - 1]
                content = canvas.winfo_children()[0]
                # The preview heading shares a nested row with its Pending label.
                headings = []
                for child in content.winfo_children():
                    if isinstance(child, tk.Label):
                        headings.append(child.cget("text"))
                # Dopagaki3 §8.4: Stick Preview is docked below the Basic page's scroll viewport.
                if editor.stick_preview.master is page:
                    headings.append(editor.stick_preview.title.cget("text"))
                self.assertEqual(headings, [editor.words[category] for category in categories])
                self.assertTrue(page.winfo_ismapped())
                self.assertFalse(editor._palette_pages[2 - number][0].winfo_ismapped())
                buttons = [child for child in descendants(page) if isinstance(child, tk.Button)]
                expected = [item for category in categories for item in palette_items(category)]
                self.assertEqual(len(buttons), len(expected))
                for button, candidate in zip(buttons, expected):
                    self.assertEqual(button.cget("text"),
                                     (candidate.short_label or candidate.display_label)
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
        expected = [item for category in PALETTE_PAGES[1] for item in palette_items(category)]
        for button, candidate in zip(buttons, expected):
            with self.subTest(candidate=candidate.label):
                grid = editor.table_grid
                grid.selected = (0, 1)
                button.invoke()
                self.assertEqual(grid._editor.get(), candidate.text)
                if candidate.select:
                    self.assertEqual((grid._editor.index("sel.first"), grid._editor.index("sel.last")),
                                     candidate.select)
                # Commands and settings: column A of the free row; the rest: the active cell.
                self.assertEqual(grid.selected, (0, 0) if candidate.own_row else (0, 1))
                self.assertFalse(editor.document.modified)
                grid.cancel_edit()
        # A commit participates in the shared Raw/Table Undo/Redo history.
        cappy = buttons[next(index for index, item in enumerate(expected) if item.text == "ca")]
        cappy.invoke()
        editor.table_grid.commit_edit()
        self.assertEqual(editor.document.text, "\tca")
        self.assertTrue(editor.document.modified)
        editor.undo()
        self.assertEqual(editor.document.text, "")
        self.assertFalse(editor.document.modified)
        editor.redo()
        self.assertEqual(editor.document.text, "\tca")

    def table_with(self, root, value, language="en"):
        editor = self.make_editor(root, language=language)
        editor.show_raw()
        editor.text.insert("1.0", value)
        editor.text.edit_separator()
        root.update()
        editor.show_table()
        editor._palette_next.invoke()
        root.update()
        page, _canvas = editor._palette_pages[1]
        buttons = {child.cget("text"): child for child in descendants(page)
                   if isinstance(child, tk.Button)}
        return editor, editor.table_grid, buttons

    def test_advanced_groups_two_columns_with_wide_rows(self):
        root = self.make_root()
        for language in ("ja", "en"):
            editor, _grid, buttons = self.table_with(root, "", language)
            layout = {label: (int(button.grid_info()["row"]), int(button.grid_info()["column"]),
                              int(button.grid_info()["columnspan"]))
                      for label, button in buttons.items()}
            self.assertEqual([layout[item.label] for item in palette_items("commands")],
                             [(0, 0, 2), (1, 0, 1), (1, 1, 1), (2, 0, 1), (2, 1, 1)])
            self.assertEqual([layout[item.label] for item in palette_items("script_info")],
                             [(0, 0, 2), (1, 0, 2), (2, 0, 1), (2, 1, 1), (3, 0, 1), (3, 1, 1)])
            self.assertEqual(buttons["/absStick on"].master, buttons["/absStick off"].master)
            self.assertEqual(editor.words["script_info"],
                             {"ja": "STAS設定", "en": "STAS Settings"}[language])

    def test_own_row_goes_below_a_written_row_only_on_commit(self):
        root = self.make_root()
        value = "1\ta\n2\tb"
        editor, grid, buttons = self.table_with(root, value)
        grid.selected = (0, 1)
        buttons["/tp x y z"].invoke()
        entry = grid._editor
        self.assertEqual(grid.selected, (1, 0))
        self.assertEqual(grid.model.to_text(), "1\ta\n\n2\tb")  # Shown, not yet written.
        self.assertEqual(editor.document.text, value)
        self.assertEqual((entry.get(), entry.index("sel.first"), entry.index("sel.last")),
                         ("/tp 0 0 0", 4, 9))
        self.assertEqual(grid.snapshot_text(), "1\ta\n/tp 0 0 0\n2\tb")
        entry.delete("sel.first", "sel.last")
        entry.insert("insert", "-600 250 8150")
        self.assertTrue(grid.commit_edit())
        self.assertEqual(editor.document.text, "1\ta\n/tp -600 250 8150\n2\tb")
        editor.undo()  # Row and text are one step.
        self.assertEqual(editor.document.text, value)
        editor.redo()
        self.assertEqual(editor.document.text, "1\ta\n/tp -600 250 8150\n2\tb")
        editor.undo()

        # Escape, or an emptied value, leaves no blank row (a blank row is a frame).
        for finish in ("escape", "empty"):
            with self.subTest(finish=finish):
                grid.selected = (0, 1)
                buttons["$stage = StageName"].invoke()
                self.assertEqual(grid.model.to_text(), "1\ta\n\n2\tb")
                if finish == "escape":
                    grid.cancel_edit()
                else:
                    grid._editor.delete(0, "end")
                    self.assertEqual(grid.snapshot_text(), value)
                    self.assertTrue(grid.commit_edit())
                self.assertEqual(grid.model.to_text(), value)
                self.assertEqual(editor.document.text, value)
                self.assertEqual(grid.selected, (0, 1))

        # Clicks in a row stack in click order, each below the last.
        grid.selected = (0, 1)
        buttons["/absStick on"].invoke()
        buttons["/absStick off"].invoke()
        self.assertTrue(grid.commit_edit())
        self.assertEqual(editor.document.text, "1\ta\n/absStick on\n/absStick off\n2\tb")
        self.assertEqual(grid.selected, (2, 0))

    def test_own_row_uses_a_free_row_in_place(self):
        root = self.make_root()
        editor, grid, buttons = self.table_with(root, "1\ta\n")
        grid.selected = (1, 2)
        buttons["$pos = (0;0;0)"].invoke()
        self.assertEqual(grid.selected, (1, 0))
        self.assertEqual((grid._editor.index("sel.first"), grid._editor.index("sel.last")), (8, 13))
        grid._editor.delete("sel.first", "sel.last")
        grid._editor.insert("insert", "-600;250;8150")
        self.assertTrue(grid.commit_edit())
        self.assertEqual(editor.document.text, "1\ta\n$pos = (-600;250;8150)")
        grid.selected = (1, 1)
        buttons["/speed 10"].invoke()  # Row 1 is written now: a new row below it.
        self.assertTrue(grid.commit_edit())
        self.assertEqual(editor.document.text, "1\ta\n$pos = (-600;250;8150)\n/speed 10")

    def test_click_below_a_dropped_row_selects_the_row_shown_there(self):
        root = self.make_root()
        editor, grid, buttons = self.table_with(root, "1\ta\n2\tb\n3\tc")
        grid.selected = (0, 1)
        buttons["$author = name"].invoke()
        grid._editor.delete(0, "end")
        root.update()
        x1, y1, x2, y2 = grid._cell_box(3, 1)  # "c", shown one row lower meanwhile.
        x, y = x1 - grid.canvas.canvasx(0) + 4, y1 - grid.canvas.canvasy(0) + 4
        grid.canvas.event_generate("<ButtonPress-1>", x=int(x), y=int(y))
        grid.canvas.event_generate("<ButtonRelease-1>", x=int(x), y=int(y))
        self.assertEqual(grid.selected, (2, 1))
        self.assertEqual(grid.model.cell(*grid.selected), "c")
        self.assertEqual(editor.document.text, "1\ta\n2\tb\n3\tc")

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
