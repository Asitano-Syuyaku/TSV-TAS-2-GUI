"""Small raw-text editor window shared by both GUI languages."""

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox

from .document import EditorDocument


LABELS = {
    "en": {
        "title": "TSV-TAS Editor", "untitled": "Untitled", "file": "File",
        "new": "New", "open": "Open...", "save": "Save", "save_as": "Save As...",
        "close": "Close", "unsaved": "Save changes before continuing?",
        "error": "Editor error",
    },
    "ja": {
        "title": "TSV-TAS エディター", "untitled": "無題", "file": "ファイル",
        "new": "新規", "open": "開く...", "save": "保存", "save_as": "名前を付けて保存...",
        "close": "閉じる", "unsaved": "変更を保存してから続行しますか？",
        "error": "エディターのエラー",
    },
}


class EditorWindow(tk.Toplevel):
    def __init__(self, master, language="en", initial_path=None, on_saved=None):
        super().__init__(master)
        self.words = LABELS[language]
        self.document = EditorDocument()
        self.on_saved = on_saved
        self.geometry("800x520")

        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        for key, command, shortcut in (
            ("new", self.new_document, "Ctrl+N"),
            ("open", self.open_file, "Ctrl+O"),
            ("save", self.save, "Ctrl+S"),
            ("save_as", self.save_as, "Ctrl+Shift+S"),
            ("close", self.close_editor, ""),
        ):
            file_menu.add_command(label=self.words[key], command=command, accelerator=shortcut)
        menu.add_cascade(label=self.words["file"], menu=file_menu)
        self.config(menu=menu)

        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True)
        fixed_font = tkfont.nametofont("TkFixedFont")
        self.text = tk.Text(frame, wrap="none", font=fixed_font,
                            tabs=(fixed_font.measure(" " * 8),))
        vertical = tk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        horizontal = tk.Scrollbar(frame, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        self.text.bind("<<Modified>>", self._on_modified)
        for sequence, command in (
            ("<Control-n>", self.new_document),
            ("<Control-o>", self.open_file),
            ("<Control-s>", self.save),
            ("<Control-Shift-S>", self.save_as),
            ("<Control-Shift-s>", self.save_as),
        ):
            self.bind(sequence, lambda event, action=command: self._shortcut(action))
        self.protocol("WM_DELETE_WINDOW", self.close_editor)
        self._update_title()
        if initial_path:
            self.open_file(initial_path)

    @staticmethod
    def _shortcut(action):
        action()
        return "break"

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

    def _show_document(self):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.document.text)
        self.text.edit_modified(False)
        self._update_title()

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
        if self.on_saved:
            self.on_saved(saved_path)
        return True

    def close_editor(self):
        if self._confirm_discard():
            self.destroy()
            return True
        return False
