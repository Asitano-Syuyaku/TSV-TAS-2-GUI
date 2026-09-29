"""Small raw-text editor window shared by both GUI languages."""

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox

from .document import EditorDocument
from .text_ops import (file_kind, find_next as next_match, find_previous as previous_match,
                       line_column, replace_all as replace_every, replace_current as replace_match)


LABELS = {
    "en": {
        "title": "TSV-TAS Editor", "untitled": "Untitled", "file": "File",
        "new": "New", "open": "Open...", "save": "Save", "save_as": "Save As...",
        "save_convert": "Save & Convert",
        "close": "Close", "unsaved": "Save changes before continuing?",
        "error": "Editor error", "edit": "Edit", "undo": "Undo", "redo": "Redo",
        "cut": "Cut", "copy": "Copy", "paste": "Paste", "select_all": "Select All",
        "search": "Search", "find": "Find...", "replace": "Replace...",
        "next": "Find Next", "previous": "Find Previous", "find_text": "Find:",
        "replace_text": "Replace with:", "replace_current": "Replace",
        "replace_all": "Replace All", "not_found": "Not found", "saved": "Unmodified",
        "modified": "Modified", "line": "Line", "column": "Column",
    },
    "ja": {
        "title": "TSV-TAS エディター", "untitled": "無題", "file": "ファイル",
        "new": "新規", "open": "開く...", "save": "保存", "save_as": "名前を付けて保存...",
        "save_convert": "保存して変換",
        "close": "閉じる", "unsaved": "変更を保存してから続行しますか？",
        "error": "エディターのエラー", "edit": "編集", "undo": "元に戻す",
        "redo": "やり直す", "cut": "切り取り", "copy": "コピー",
        "paste": "貼り付け", "select_all": "すべて選択", "search": "検索",
        "find": "検索...", "replace": "置換...", "next": "次を検索",
        "previous": "前を検索", "find_text": "検索:", "replace_text": "置換後:",
        "replace_current": "置換", "replace_all": "すべて置換",
        "not_found": "見つかりません", "saved": "未編集", "modified": "編集済み",
        "line": "行", "column": "列",
    },
}


class EditorWindow(tk.Toplevel):
    def __init__(self, master, language="en", initial_path=None, on_saved=None,
                 on_convert=None, can_convert=None):
        super().__init__(master)
        self.words = LABELS[language]
        self.document = EditorDocument()
        self.on_saved = on_saved
        self.on_convert = on_convert
        self.can_convert = can_convert
        self.find_query = tk.StringVar(self)
        self.replace_value = tk.StringVar(self)
        self._find_dialog = None
        self._gutter_job = None
        self.geometry("800x520")

        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        for key, command, shortcut in (
            ("new", self.new_document, "Ctrl+N"),
            ("open", self.open_file, "Ctrl+O"),
            ("save", self.save, "Ctrl+S"),
            ("save_as", self.save_as, "Ctrl+Shift+S"),
            ("save_convert", self.save_and_convert, "F5"),
            ("close", self.close_editor, ""),
        ):
            file_menu.add_command(label=self.words[key], command=command, accelerator=shortcut)
        menu.add_cascade(label=self.words["file"], menu=file_menu)
        edit_menu = tk.Menu(menu, tearoff=False)
        for key, command, shortcut in (
            ("undo", self.undo, "Ctrl+Z"), ("redo", self.redo, "Ctrl+Y"),
            ("cut", self.cut, "Ctrl+X"), ("copy", self.copy, "Ctrl+C"),
            ("paste", self.paste, "Ctrl+V"), ("select_all", self.select_all, "Ctrl+A"),
        ):
            edit_menu.add_command(label=self.words[key], command=command, accelerator=shortcut)
        menu.add_cascade(label=self.words["edit"], menu=edit_menu)
        search_menu = tk.Menu(menu, tearoff=False)
        for key, command, shortcut in (
            ("find", self.show_find, "Ctrl+F"), ("replace", self.show_replace, "Ctrl+H"),
            ("next", self.find_next, "F3"), ("previous", self.find_previous, "Shift+F3"),
        ):
            search_menu.add_command(label=self.words[key], command=command, accelerator=shortcut)
        menu.add_cascade(label=self.words["search"], menu=search_menu)
        self.config(menu=menu)

        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True)
        fixed_font = tkfont.nametofont("TkFixedFont")
        self._fixed_font = fixed_font
        self.line_numbers = tk.Canvas(frame, width=40, highlightthickness=0)
        self.text = tk.Text(frame, wrap="none", font=fixed_font, undo=True,
                            exportselection=False,
                            tabs=(fixed_font.measure(" " * 8),))
        vertical = tk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        horizontal = tk.Scrollbar(frame, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=lambda first, last: self._on_scroll(vertical, first, last),
                            xscrollcommand=horizontal.set)
        self.line_numbers.grid(row=0, column=0, sticky="ns")
        self.text.grid(row=0, column=1, sticky="nsew")
        vertical.grid(row=0, column=2, sticky="ns")
        horizontal.grid(row=1, column=1, sticky="ew")
        self.status = tk.Label(frame, anchor="w")
        self.status.grid(row=2, column=0, columnspan=3, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<KeyRelease>", self._update_status)
        self.text.bind("<ButtonRelease-1>", self._update_status)
        self.text.bind("<Configure>", self._schedule_line_numbers)
        for sequence, command in (
            ("<Control-n>", self.new_document), ("<Control-o>", self.open_file),
            ("<Control-s>", self.save), ("<Control-Shift-S>", self.save_as),
            ("<Control-Shift-s>", self.save_as),
            ("<F5>", self.save_and_convert),
            ("<Control-z>", self.undo), ("<Control-y>", self.redo),
            ("<Control-x>", self.cut), ("<Control-c>", self.copy),
            ("<Control-v>", self.paste), ("<Control-a>", self.select_all),
            ("<Control-f>", self.show_find), ("<Control-h>", self.show_replace),
            ("<F3>", self.find_next), ("<Shift-F3>", self.find_previous),
        ):
            self.text.bind(sequence, lambda event, action=command: self._shortcut(action))
        for sequence, command in (
            ("<Control-n>", self.new_document),
            ("<Control-o>", self.open_file),
            ("<Control-s>", self.save),
            ("<Control-Shift-S>", self.save_as),
            ("<Control-Shift-s>", self.save_as),
            ("<F5>", self.save_and_convert),
            ("<Control-f>", self.show_find),
            ("<Control-h>", self.show_replace),
            ("<F3>", self.find_next),
            ("<Shift-F3>", self.find_previous),
        ):
            self.bind(sequence, lambda event, action=command: self._shortcut(action))
        self.protocol("WM_DELETE_WINDOW", self.close_editor)
        self._update_title()
        self._update_status()
        self._schedule_line_numbers()
        if initial_path:
            self.open_file(initial_path)

    @staticmethod
    def _shortcut(action):
        action()
        return "break"

    def _on_scroll(self, scrollbar, first, last):
        scrollbar.set(first, last)
        self._schedule_line_numbers()

    def _schedule_line_numbers(self, _event=None):
        if self._gutter_job is None:
            self._gutter_job = self.after_idle(self._draw_line_numbers)

    def _draw_line_numbers(self):
        self._gutter_job = None
        if not self.winfo_exists():
            return
        last_line = int(self.text.index("end-1c").split(".")[0])
        width = self._fixed_font.measure(str(last_line)) + 12
        if int(self.line_numbers.cget("width")) != width:
            self.line_numbers.configure(width=width)
        self.line_numbers.delete("all")
        index = self.text.index("@0,0")
        while True:
            details = self.text.dlineinfo(index)
            if details is None:
                break
            line = int(index.split(".")[0])
            if line > last_line:
                break
            self.line_numbers.create_text(width - 5, details[1] + details[3] / 2,
                                          text=str(line), anchor="e", font=self._fixed_font)
            following = self.text.index(f"{index}+1line")
            if following == index:
                break
            index = following

    def _update_status(self, _event=None):
        line, column = line_column(self.text.index("insert"))
        state = self.words["modified"] if self.document.modified else self.words["saved"]
        self.status.config(text=f"{self.words['line']} {line}, {self.words['column']} {column}"
                                f"  |  {state}  |  {file_kind(self.document.path)}")

    def _update_title(self):
        name = self.document.path.name if self.document.path else self.words["untitled"]
        mark = " *" if self.document.modified else ""
        self.title(f"{name}{mark} — {self.words['title']}")

    def _sync_text(self):
        self.document.set_text(self.text.get("1.0", "end-1c"))
        self._update_title()

    def _on_modified(self, _event=None):
        if self.text.edit_modified():
            self._sync_text()
            self.text.edit_modified(False)
            self._update_status()
            self._schedule_line_numbers()

    def _show_document(self):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.document.text)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self._update_title()
        self._update_status()
        self._schedule_line_numbers()

    def undo(self):
        try:
            self.text.edit_undo()
        except tk.TclError:
            return False
        self._sync_text()
        self._update_status()
        self._schedule_line_numbers()
        return True

    def redo(self):
        try:
            self.text.edit_redo()
        except tk.TclError:
            return False
        self._sync_text()
        self._update_status()
        self._schedule_line_numbers()
        return True

    def cut(self):
        self.text.event_generate("<<Cut>>")

    def copy(self):
        self.text.event_generate("<<Copy>>")

    def paste(self):
        self.text.event_generate("<<Paste>>")

    def select_all(self):
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "end-1c")
        self.text.see("insert")
        self._update_status()

    def show_find(self, replace=False):
        if self._find_dialog is None or not self._find_dialog.winfo_exists():
            dialog = tk.Toplevel(self)
            dialog.title(self.words["search"])
            dialog.transient(self)
            self._find_dialog = dialog
            tk.Label(dialog, text=self.words["find_text"]).grid(row=0, column=0, sticky="e")
            self._find_entry = tk.Entry(dialog, textvariable=self.find_query, width=32)
            self._find_entry.grid(row=0, column=1, columnspan=4, sticky="ew")
            tk.Label(dialog, text=self.words["replace_text"]).grid(row=1, column=0, sticky="e")
            self._replace_entry = tk.Entry(dialog, textvariable=self.replace_value, width=32)
            self._replace_entry.grid(row=1, column=1, columnspan=4, sticky="ew")
            for column, key, command in (
                (0, "next", self.find_next), (1, "previous", self.find_previous),
                (2, "replace_current", self.replace_current), (3, "replace_all", self.replace_all),
            ):
                tk.Button(dialog, text=self.words[key], command=command).grid(row=2, column=column)
            self._find_feedback = tk.Label(dialog, anchor="w")
            self._find_feedback.grid(row=3, column=0, columnspan=5, sticky="ew")
            self._find_entry.bind("<Return>", lambda event: self._shortcut(self.find_next))
            self._replace_entry.bind("<Return>", lambda event: self._shortcut(self.replace_current))
            dialog.bind("<F3>", lambda event: self._shortcut(self.find_next))
            dialog.bind("<Shift-F3>", lambda event: self._shortcut(self.find_previous))
            dialog.bind("<Escape>", lambda event: dialog.destroy())
        else:
            self._find_dialog.lift()
        (self._replace_entry if replace else self._find_entry).focus_set()

    def show_replace(self):
        self.show_find(replace=True)

    def _selection_offsets(self):
        selected = self.text.tag_ranges("sel")
        if len(selected) != 2:
            return None
        return tuple(len(self.text.get("1.0", index)) for index in selected)

    def _cursor_offset(self):
        return len(self.text.get("1.0", "insert"))

    def _select_match(self, match):
        if match is None:
            if self._find_dialog is not None and self._find_dialog.winfo_exists():
                self._find_feedback.config(text=self.words["not_found"])
            else:
                self.bell()
            return False
        start, end = match
        first = self.text.index(f"1.0+{start}c")
        last = self.text.index(f"1.0+{end}c")
        self.text.tag_remove("sel", "1.0", "end")
        self.text.tag_add("sel", first, last)
        self.text.mark_set("insert", last)
        self.text.see(first)
        if self._find_dialog is not None and self._find_dialog.winfo_exists():
            self._find_feedback.config(text="")
        self._update_status()
        return True

    def find_next(self):
        query = self.find_query.get()
        if not query:
            self.show_find()
            return False
        selected = self._selection_offsets()
        start = selected[1] if selected else self._cursor_offset()
        return self._select_match(next_match(self.text.get("1.0", "end-1c"), query, start))

    def find_previous(self):
        query = self.find_query.get()
        if not query:
            self.show_find()
            return False
        selected = self._selection_offsets()
        start = selected[0] if selected else self._cursor_offset()
        return self._select_match(previous_match(self.text.get("1.0", "end-1c"), query, start))

    def replace_current(self):
        query = self.find_query.get()
        selection = self._selection_offsets()
        original = self.text.get("1.0", "end-1c")
        replacement = self.replace_value.get()
        if replace_match(original, query, replacement, selection) is None:
            return self.find_next()
        first, last = self.text.tag_ranges("sel")
        self.text.edit_separator()
        self.text.delete(first, last)
        self.text.insert(first, replacement)
        self.text.edit_separator()
        self.text.tag_remove("sel", "1.0", "end")
        self._sync_text()
        self._update_status()
        self._schedule_line_numbers()
        self.find_next()
        return True

    def replace_all(self):
        query = self.find_query.get()
        original = self.text.get("1.0", "end-1c")
        updated, count = replace_every(original, query, self.replace_value.get())
        if count == 0:
            if query:
                self._select_match(None)
            return 0
        if updated != original:
            cursor = self._cursor_offset()
            self.text.edit_separator()
            self.text.delete("1.0", "end")
            self.text.insert("1.0", updated)
            self.text.edit_separator()
            self.text.mark_set("insert", f"1.0+{min(cursor, len(updated))}c")
            self.text.tag_remove("sel", "1.0", "end")
            self._sync_text()
            self._update_status()
            self._schedule_line_numbers()
        return count

    def _confirm_discard(self):
        self._sync_text()
        if not self.document.modified:
            return True
        choice = messagebox.askyesnocancel(self.words["title"], self.words["unsaved"], parent=self)
        if choice is None:
            return False
        return self.save() if choice else True

    def new_document(self):
        if not self._confirm_discard():
            return False
        self.document.new()
        self._show_document()
        return True

    def open_file(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(parent=self, filetypes=[("TSV/TXT", "*.tsv *.txt")])
        if not path:
            return False
        if not self._confirm_discard():
            return False
        try:
            self.document.open(path)
        except (OSError, UnicodeError, ValueError) as error:
            messagebox.showerror(self.words["error"], str(error), parent=self)
            return False
        self._show_document()
        return True

    def save(self):
        if self.document.path is None:
            return self.save_as()
        return self._save_to(self.document.path)

    def save_and_convert(self):
        if self.on_convert is None:
            return False
        if self.can_convert is not None and not self.can_convert():
            return False
        self._sync_text()
        if (self.document.path is None or self.document.modified) and not self.save():
            return False
        return bool(self.on_convert(self.document.path))

    def save_as(self):
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=self.document.path.suffix if self.document.path else ".tsv",
            initialfile=self.document.path.name if self.document.path else "untitled.tsv",
            filetypes=[("TSV", "*.tsv"), ("Text", "*.txt")],
        )
        return self._save_to(path) if path else False

    def _save_to(self, path):
        self._sync_text()
        try:
            saved_path = self.document.save(path)
        except (OSError, UnicodeError, ValueError) as error:
            messagebox.showerror(self.words["error"], str(error), parent=self)
            return False
        self._update_title()
        self._update_status()
        if self.on_saved:
            self.on_saved(saved_path)
        return True

    def close_editor(self):
        if self._confirm_discard():
            if self._gutter_job is not None:
                self.after_cancel(self._gutter_job)
            self.destroy()
            return True
        return False
