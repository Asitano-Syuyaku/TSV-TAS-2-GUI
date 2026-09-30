"""Text editor with a literal TSV table view, shared by both GUI languages."""

import threading
import tkinter as tk
from pathlib import Path
import traceback
from queue import Empty, SimpleQueue
from tkinter import filedialog, font as tkfont, messagebox

from .document import EditorDocument
from .file_state import ExternalFileConflict
from .recovery import DEBOUNCE_MS, RecoverySnapshot, RecoveryStore
from .resources import palette_icon_path
from .snapshot import ScriptSnapshot
from .text_ops import (file_kind, find_next as next_match, find_previous as previous_match,
                       line_column, replace_all as replace_every, replace_current as replace_match)
from .tsv_syntax import CANDIDATES, PALETTE_PAGES, syntax_spans

if __package__ == "editor":
    from app_settings import AppSettings
else:
    from ..app_settings import AppSettings


HIGHLIGHT_COLORS = {"comment": "#53805a", "command": "#8741a8",
                    "variable": "#9a621f", "duration": "#295fa3",
                    "input": "#234a84"}


LABELS = {
    "en": {
        "title": "TSV-TAS Editor", "untitled": "Untitled", "file": "File",
        "new": "New", "open": "Open...", "save": "Save", "save_as": "Save As...",
        "save_convert": "Save & Convert",
        "save_convert_send": "Save, Convert & Send",
        "recent_files": "Recent Files", "clear_recent": "Clear Recent Files",
        "no_recent": "(Empty)", "missing_recent": "File no longer exists:",
        "close": "Close", "unsaved": "Save changes before continuing?",
        "external_title": "File changed outside the Editor",
        "external_changed": "This file has changed outside the Editor.\nOverwrite it with the current Editor contents?",
        "external_missing": "The original file has been deleted.\nRecreate it at the same location?",
        "external_unreadable": "Cannot check the current file contents. The file was not saved.\nCheck permissions or use Save As to a different path.",
        "external_retry": "The file changed after the save check. It was not saved.\nTry Save again to confirm the current disk state.",
        "error": "Editor error", "edit": "Edit", "undo": "Undo", "redo": "Redo",
        "cut": "Cut", "copy": "Copy", "paste": "Paste", "select_all": "Select All",
        "search": "Search", "find": "Find...", "replace": "Replace...",
        "next": "Find Next", "previous": "Find Previous", "find_text": "Find:",
        "replace_text": "Replace with:", "replace_current": "Replace",
        "replace_all": "Replace All", "not_found": "Not found", "saved": "Unmodified",
        "modified": "Modified", "line": "Line", "column": "Column",
        "raw_view": "Raw Text", "table_view": "Table",
        "table_menu": "Table", "add_row": "+ Row", "add_column": "+ Column",
        "insert_row_above": "Insert Row Above", "insert_row_below": "Insert Row Below",
        "delete_row": "Delete Row", "duplicate_row": "Duplicate Row",
        "insert_column_left": "Insert Column Left",
        "insert_column_right": "Insert Column Right",
        "delete_column": "Delete Column",
        "clear_cells": "Clear Cells",
        "input_palette": "Input Palette", "buttons": "Buttons",
        "left_stick": "Left Stick", "right_stick": "Right Stick",
        "commands": "STAS Commands",
        "cappy": "Cappy", "accel": "Accel", "gyro": "Gyro", "notation": "Notation",
        "validate": "Validate", "validating": "Validating...",
        "no_errors": "No errors", "problems": "Problems",
        "jump_hint": "Double-click a line message to jump",
        "stale_validation": "Document changed; validate again",
        "duration_header": "Duration",
        "button_header": "Button",
        "analyze": "Analyze Frames", "analyzing": "Analyzing frames...",
        "frame_inspector": "Frame Inspector", "total_frames": "Total Frames",
        "frame_number": "Frame:", "go": "Go", "frame_details": "All Debug CSV fields",
        "invalid_frame": "Enter a frame number", "frame_not_found": "Frame not found",
        "previous_frames": "Previous analysis; run Analyze Frames again",
        "stale_analysis": "Document changed; analyze again",
        "frame_updating": "Frame: updating...", "frame_error": "Frame: unavailable",
        "frame_unavailable": "Frame: TSV-TAS only",
        "frame_start": "Start", "frame_duration": "Duration",
        "frame_end": "End", "frame_total": "Total",
    },
    "ja": {
        "title": "TSV-TAS エディター", "untitled": "無題", "file": "ファイル",
        "new": "新規", "open": "開く...", "save": "保存", "save_as": "名前を付けて保存...",
        "save_convert": "保存して変換",
        "save_convert_send": "保存・変換してFTP送信",
        "recent_files": "最近使ったファイル", "clear_recent": "履歴を消去",
        "no_recent": "（履歴なし）", "missing_recent": "ファイルが見つかりません:",
        "close": "閉じる", "unsaved": "変更を保存してから続行しますか？",
        "external_title": "Editor外のファイル変更",
        "external_changed": "このファイルはEditor外で変更されています。\n現在のEditor内容で上書きしますか？",
        "external_missing": "元ファイルが削除されています。\n同じ場所へ再作成しますか？",
        "external_unreadable": "現在のファイル内容を確認できないため、保存しませんでした。\nアクセス権を確認するか、別pathへ名前を付けて保存してください。",
        "external_retry": "保存確認後にファイルが変更されたため、保存しませんでした。\n再度保存してdiskの状態を確認してください。",
        "error": "エディターのエラー", "edit": "編集", "undo": "元に戻す",
        "redo": "やり直す", "cut": "切り取り", "copy": "コピー",
        "paste": "貼り付け", "select_all": "すべて選択", "search": "検索",
        "find": "検索...", "replace": "置換...", "next": "次を検索",
        "previous": "前を検索", "find_text": "検索:", "replace_text": "置換後:",
        "replace_current": "置換", "replace_all": "すべて置換",
        "not_found": "見つかりません", "saved": "未編集", "modified": "編集済み",
        "line": "行", "column": "列",
        "raw_view": "テキスト", "table_view": "表",
        "table_menu": "表", "add_row": "+ 行", "add_column": "+ 列",
        "insert_row_above": "上に行を追加", "insert_row_below": "下に行を追加",
        "delete_row": "行を削除", "duplicate_row": "行を複製",
        "insert_column_left": "左に列を追加",
        "insert_column_right": "右に列を追加",
        "delete_column": "列を削除",
        "clear_cells": "セルを消去",
        "input_palette": "入力パレット", "buttons": "ボタン",
        "left_stick": "左スティック", "right_stick": "右スティック",
        "commands": "STASコマンド",
        "cappy": "Cappy", "accel": "加速度", "gyro": "ジャイロ", "notation": "記法",
        "validate": "検証", "validating": "検証中...",
        "no_errors": "エラーなし", "problems": "問題",
        "jump_hint": "行を含むメッセージをダブルクリックで移動",
        "stale_validation": "文書が変更されました。再度検証してください",
        "duration_header": "フレーム数",
        "button_header": "ボタン",
        "analyze": "フレーム解析", "analyzing": "フレーム解析中...",
        "frame_inspector": "フレームインスペクター", "total_frames": "総フレーム数",
        "frame_number": "フレーム:", "go": "移動", "frame_details": "Debug CSVの全項目",
        "invalid_frame": "フレーム番号を入力してください", "frame_not_found": "フレームが見つかりません",
        "previous_frames": "以前の解析結果です。再度フレーム解析してください",
        "stale_analysis": "文書が変更されました。再度解析してください",
        "frame_updating": "Frame: 更新中...", "frame_error": "Frame: 未確定",
        "frame_unavailable": "Frame: TSV-TASのみ",
        "frame_start": "開始", "frame_duration": "長さ",
        "frame_end": "終了", "frame_total": "全体",
    },
}


class EditorWindow(tk.Toplevel):
    def __init__(self, master, language="en", initial_path=None, on_saved=None,
                 on_convert=None, can_convert=None, on_validate=None, can_validate=None,
                 on_analyze=None, can_analyze=None, settings=None, recovery=None):
        super().__init__(master)
        self.words = LABELS[language]
        self.settings = settings if settings is not None else getattr(master, "settings", None)
        if self.settings is None:
            self.settings = getattr(master, "_tas_app_settings", None)
            if self.settings is None:
                self.settings = master._tas_app_settings = AppSettings()
        self.document = EditorDocument()
        self._recovery_store = getattr(master, "recovery_store", None)
        if self._recovery_store is None:
            self._recovery_store = getattr(master, "_tas_recovery_store", None)
            if self._recovery_store is None:
                self._recovery_store = master._tas_recovery_store = RecoveryStore.from_settings(self.settings)
        self._recovery_id = recovery.document_id if recovery is not None else self._recovery_store.new_id()
        self._recovery_store.active_ids.add(self._recovery_id)
        self._recovery_job = None
        self.on_saved = on_saved
        self.on_convert = on_convert
        self.can_convert = can_convert
        self.on_validate = on_validate
        self.can_validate = can_validate
        self.on_analyze = on_analyze
        self.can_analyze = can_analyze
        self._validation_pending = False
        self._analysis_pending = False
        self._frame_inspector = None
        self._inspector_snapshot = None
        self._positions = None
        self._position_key = None
        self._position_revision = 0
        self._document_revision = 0
        self._closed = False
        self._position_job = None
        self._position_poll_job = None
        self._position_worker_active = False
        self._position_waiting = False
        self._frame_edit_pending = False
        self._position_queue = SimpleQueue()
        self.find_query = tk.StringVar(self)
        self.replace_value = tk.StringVar(self)
        self._find_dialog = None
        self._gutter_job = None
        self._highlight_job = None
        self._highlight_range = None
        self._palette_icons = {}  # Keep PhotoImage references alive for Tk buttons.
        self._view = "raw"
        self.geometry("1200x700")

        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        for key, command, shortcut in (
            ("new", self.new_document, "Ctrl+N"),
            ("open", self.open_file, "Ctrl+O"),
            ("save", self.save, "Ctrl+S"),
            ("save_as", self.save_as, "Ctrl+Shift+S"),
            ("save_convert", self.save_and_convert, "F5"),
            ("save_convert_send", self.save_convert_and_send, "F8"),
            ("validate", self.validate, "F6"),
            ("analyze", self.analyze_frames, "F7"),
            ("close", self.close_editor, ""),
        ):
            file_menu.add_command(label=self.words[key], command=command, accelerator=shortcut)
            if key == "open":
                self._recent_menu = tk.Menu(file_menu, tearoff=False,
                                            postcommand=self._refresh_recent_menu)
                file_menu.add_cascade(label=self.words["recent_files"], menu=self._recent_menu)
                self._refresh_recent_menu()
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
        table_menu = tk.Menu(menu, tearoff=False)
        for key, action in (("insert_row_above", "insert_row_above"),
                            ("insert_row_below", "insert_row_below"),
                            ("delete_row", "delete_row"),
                            ("duplicate_row", "duplicate_row"),
                            ("insert_column_left", "insert_column_left"),
                            ("insert_column_right", "insert_column_right"),
                            ("delete_column", "delete_column"),
                            ("clear_cells", "clear_selection")):
            table_menu.add_command(label=self.words[key],
                                   command=lambda name=action: self._table_action(name))
        menu.add_cascade(label=self.words["table_menu"], menu=table_menu)
        self.config(menu=menu)

        view_bar = tk.Frame(self)
        view_bar.pack(fill="x")
        tk.Button(view_bar, text=self.words["raw_view"], command=self.show_raw).pack(side="left")
        self._table_button = tk.Button(view_bar, text=self.words["table_view"],
                                       command=self.show_table)
        self._table_button.pack(side="left")
        tk.Button(view_bar, text=self.words["validate"], command=self.validate).pack(side="left")
        self.frame_status = tk.Label(view_bar, anchor="e")
        self.frame_status.pack(side="right", padx=8)
        self.table_tools = tk.Frame(view_bar)
        tk.Button(self.table_tools, text=self.words["add_row"],
                  command=lambda: self._table_action("insert_row_below")).pack(side="left")
        tk.Button(self.table_tools, text=self.words["add_column"],
                  command=lambda: self._table_action("insert_column_right")).pack(side="left")

        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True)
        self.raw_frame = frame
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
        for kind, color in HIGHLIGHT_COLORS.items():
            self.text.tag_configure("syntax_" + kind, foreground=color)
        self.line_numbers.grid(row=0, column=0, sticky="ns")
        self.text.grid(row=0, column=1, sticky="nsew")
        vertical.grid(row=0, column=2, sticky="ns")
        horizontal.grid(row=1, column=1, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        # Import lazily so file/document logic remains usable without Tk widgets.
        from .grid import TableGrid
        self.table_area = tk.Frame(self)
        self.table_grid = TableGrid(self.table_area, fixed_font, self._table_cell_changed,
                                    self._table_text_changed, self._update_status,
                                    self.undo, self.redo, self.words,
                                    on_edit_change=self._table_edit_pending)
        self._load_palette_icons()
        self._build_input_palette()
        self.table_grid.pack(side="left", fill="both", expand=True)
        self.status = tk.Label(self, anchor="w")
        self.status.pack(fill="x")
        self._problems_panel = tk.Frame(self, relief="groove", borderwidth=1)
        self._problems_title = tk.Label(self._problems_panel, anchor="w")
        self._problems_title.pack(fill="x")
        self._problems_text = tk.Text(self._problems_panel, height=4, wrap="word",
                                      state="disabled", takefocus=False)
        self._problems_text.tag_configure("jump", foreground="#075ca8", underline=True)
        self._problems_text.bind("<Double-Button-1>", self._problem_double_click)
        self._problem_rows = {}
        self._problem_snapshot = None
        self._update_view_button()

        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<KeyRelease>", self._update_status)
        self.text.bind("<ButtonRelease-1>", self._update_status)
        self.text.bind("<Configure>", self._on_text_configure)
        for sequence, command in (
            ("<Control-n>", self.new_document), ("<Control-o>", self.open_file),
            ("<Control-s>", self.save), ("<Control-Shift-S>", self.save_as),
            ("<Control-Shift-s>", self.save_as),
            ("<F5>", self.save_and_convert),
            ("<F8>", self.save_convert_and_send),
            ("<F6>", self.validate),
            ("<F7>", self.analyze_frames),
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
            ("<F8>", self.save_convert_and_send),
            ("<F6>", self.validate),
            ("<F7>", self.analyze_frames),
            ("<Control-f>", self.show_find),
            ("<Control-h>", self.show_replace),
            ("<F3>", self.find_next),
            ("<Shift-F3>", self.find_previous),
        ):
            self.bind(sequence, lambda event, action=command: self._shortcut(action))
        self.protocol("WM_DELETE_WINDOW", self.close_editor)
        self.bind("<Destroy>", self._on_destroy)
        self._update_title()
        self._update_status()
        self._schedule_line_numbers()
        self._schedule_highlight()
        if recovery is not None:
            recovery.restore(self.document)
            self._show_document()
            self._schedule_recovery()
        elif initial_path:
            self.open_file(initial_path)
        else:
            self._position_document_changed()

    def _load_palette_icons(self):
        for candidate in CANDIDATES:
            if candidate.category != "buttons" or not candidate.icon_key:
                continue
            path = palette_icon_path(candidate.icon_key)
            try:
                if not path.is_file():
                    continue
                self._palette_icons[candidate.icon_key] = tk.PhotoImage(master=self, file=str(path))
            except (OSError, tk.TclError):
                # One missing or unreadable icon must not prevent editor startup.
                continue

    def _build_input_palette(self):
        self.input_palette = tk.Frame(self.table_area, width=330, relief="groove",
                                      borderwidth=1)
        self.input_palette.pack_propagate(False)
        self.input_palette.pack(side="right", fill="y")
        header = tk.Frame(self.input_palette)
        header.pack(fill="x", padx=6, pady=4)
        tk.Label(header, text=self.words["input_palette"], anchor="w").pack(side="left")
        self._palette_next = tk.Button(
            header, text="▶", width=2, padx=0, takefocus=False,
            command=lambda: self._show_palette_page(self._palette_page + 1))
        self._palette_next.pack(side="right")
        self._palette_page_label = tk.Label(header)
        self._palette_page_label.pack(side="right", padx=3)
        self._palette_previous = tk.Button(
            header, text="◀", width=2, padx=0, takefocus=False,
            command=lambda: self._show_palette_page(self._palette_page - 1))
        self._palette_previous.pack(side="right")
        body = tk.Frame(self.input_palette)
        body.pack(fill="both", expand=True)
        self._palette_pages = []
        for categories in PALETTE_PAGES:
            page = tk.Frame(body)
            canvas = tk.Canvas(page, highlightthickness=0, yscrollincrement=20)
            scrollbar = tk.Scrollbar(page, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            content = tk.Frame(canvas)
            content_id = canvas.create_window((0, 0), window=content, anchor="nw")
            content.bind("<Configure>", lambda event, target=canvas:
                         target.configure(scrollregion=target.bbox("all")))
            canvas.bind("<Configure>", lambda event, target=canvas, item=content_id:
                        target.itemconfigure(item, width=event.width))
            for category in categories:
                tk.Label(content, text=self.words[category], anchor="w").pack(
                    fill="x", padx=6, pady=(5, 1))
                group = tk.Frame(content)
                group.pack(fill="x", padx=3)
                for column in (0, 1):
                    group.grid_columnconfigure(column, weight=1, uniform="palette")
                slot = 0
                candidates = (item for item in CANDIDATES if item.category == category)
                for candidate in candidates:
                    span = self._palette_span(candidate)
                    if span == 2 and slot % 2:
                        slot += 1
                    row, column = divmod(slot, 2)
                    group.grid_rowconfigure(row, minsize=30)
                    self._palette_button(group, candidate).grid(
                        row=row, column=column, columnspan=span,
                        sticky="ew", padx=2, pady=1)
                    slot += span
            self._bind_palette_scroll(page, canvas)
            self._palette_pages.append((page, canvas))
        self._show_palette_page(1)

    def _show_palette_page(self, number):
        if not 1 <= number <= len(self._palette_pages):
            return
        for index, (page, canvas) in enumerate(self._palette_pages, start=1):
            if index == number:
                page.pack(fill="both", expand=True)
                self.palette_canvas = canvas
            else:
                page.pack_forget()
        self._palette_page = number
        self._palette_page_label.configure(text=f"{number} / {len(self._palette_pages)}")
        self._palette_previous.configure(state="disabled" if number == 1 else "normal")
        self._palette_next.configure(state="disabled" if number == len(self._palette_pages) else "normal")

    def _bind_palette_scroll(self, widget, canvas):
        # Widget-local bindings also cover buttons; Table keeps its own wheel events.
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(sequence, lambda event, target=canvas: self._palette_wheel(event, target))
        for child in widget.winfo_children():
            self._bind_palette_scroll(child, canvas)

    @staticmethod
    def _palette_wheel(event, canvas):
        direction = getattr(event, "num", None)
        if direction in (4, 5):
            units = -1 if direction == 4 else 1
        else:
            delta = getattr(event, "delta", 0)
            if not delta:
                return "break"
            units = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        first, last = canvas.yview()
        if last - first < 1:
            canvas.yview_scroll(units * 3, "units")
        return "break"

    @staticmethod
    def _palette_span(candidate):
        return 2 if (candidate.category in ("gyro", "notation") or
                     candidate.label in ("ls(angle)", "rs(angle)")) else 1

    def _palette_button(self, parent, candidate):
        image = getattr(self, "_palette_icons", {}).get(candidate.icon_key)
        options = {"text": (candidate.short_label or candidate.display_label)
                   if image is not None else candidate.display_label,
                   "anchor": "w",
                   "command": lambda item=candidate: self.table_grid.insert_candidate(item)}
        if image is not None:
            options.update(image=image, compound="left", padx=4)
        return tk.Button(parent, **options)

    @staticmethod
    def _shortcut(action):
        action()
        return "break"

    def _on_scroll(self, scrollbar, first, last):
        scrollbar.set(first, last)
        self._schedule_line_numbers()
        self._schedule_highlight()

    def _on_text_configure(self, _event=None):
        self._schedule_line_numbers()
        self._schedule_highlight()

    def _schedule_highlight(self):
        if self._view == "raw" and self._highlight_job is None:
            self._highlight_job = self.after_idle(self._draw_highlight)

    def _draw_highlight(self):
        self._highlight_job = None
        if self._view != "raw" or not self.winfo_exists():
            return
        if self._highlight_range is not None:
            for kind in HIGHLIGHT_COLORS:
                self.text.tag_remove("syntax_" + kind,
                                     "_tas_highlight_start", "_tas_highlight_end")
        if not self._table_available():
            self._highlight_range = None
            return
        first = int(self.text.index("@0,0").split(".")[0])
        last = int(self.text.index(f"@0,{max(0, self.text.winfo_height() - 1)}").split(".")[0])
        self._highlight_range = first, last
        self.text.mark_set("_tas_highlight_start", f"{first}.0")
        self.text.mark_set("_tas_highlight_end", f"{last + 1}.0")
        self.text.mark_gravity("_tas_highlight_start", "left")
        self.text.mark_gravity("_tas_highlight_end", "right")
        for line in range(first, last + 1):
            value = self.text.get(f"{line}.0", f"{line}.0 lineend")
            for kind, start, end in syntax_spans(value):
                self.text.tag_add("syntax_" + kind,
                                  f"{line}.0+{start}c", f"{line}.0+{end}c")

    def _schedule_line_numbers(self, _event=None):
        if self._gutter_job is None:
            self._gutter_job = self.after_idle(self._draw_line_numbers)

    def _on_destroy(self, event):
        if event.widget is self:
            self._closed = True
            for name in ("_gutter_job", "_highlight_job", "_position_job",
                         "_position_poll_job", "_recovery_job"):
                job = getattr(self, name, None)
                if job is not None:
                    self.after_cancel(job)
                    setattr(self, name, None)
            if getattr(self, "_recovery_store", None) is not None:
                # Direct destruction/forced shutdown cancels timers but retains recovery.
                self._recovery_store.release(self._recovery_id)

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
        if getattr(self, "_view", "raw") == "table":
            row, cell = self.table_grid.selected
            line, column = row + 1, cell + 1
        else:
            line, column = line_column(self.text.index("insert"))
        state = self.words["modified"] if self.document.modified else self.words["saved"]
        self.status.config(text=f"{self.words['line']} {line}, {self.words['column']} {column}"
                                f"  |  {state}  |  {file_kind(self.document.path)}")
        if hasattr(self, "frame_status"):
            self._update_frame_info(line)

    def _update_frame_info(self, line):
        if not self._table_available():
            message = self.words["frame_unavailable"]
        elif self._frame_edit_pending:
            message = self.words["frame_updating"]
        elif self._positions is None:
            message = (self.words["frame_updating"] if self._position_job is not None or
                       self._position_worker_active else self.words["frame_error"])
        else:
            if self._view == "table":
                top, bottom = self.table_grid.selection.bounds[:2]
                position = (self._positions.for_line(top + 1) if top == bottom else
                            self._positions.for_range(top + 1, bottom + 1))
            else:
                position = self._positions.for_line(line)
            start = f"{position.start}f" if position else "—"
            duration = f"{position.duration}f" if position else "—"
            end = f"{position.end}f" if position and position.end is not None else "—"
            message = (f"{self.words['frame_start']}: {start} | "
                       f"{self.words['frame_duration']}: {duration} | "
                       f"{self.words['frame_end']}: {end} | "
                       f"{self.words['frame_total']}: {self._positions.total_frames}f")
        self.frame_status.configure(text=message)

    def _table_edit_pending(self, changed):
        self._frame_edit_pending = changed
        self._update_frame_info(self._current_line())
        self._schedule_recovery()

    def _schedule_recovery(self):
        if getattr(self, "_recovery_store", None) is None or getattr(self, "_closed", False):
            return
        if self._recovery_job is not None:
            self.after_cancel(self._recovery_job)
            self._recovery_job = None
        if self.document.modified or self._frame_edit_pending:
            self._recovery_job = self.after(DEBOUNCE_MS, self._write_recovery)
        else:
            self._recovery_store.delete(self._recovery_id)

    def _write_recovery(self):
        self._recovery_job = None
        if self._closed:
            return
        text = (self.table_grid.snapshot_text() if self._view == "table"
                else self.text.get("1.0", "end-1c"))
        name = self.document.path.name if self.document.path else self.words["untitled"]
        snapshot = RecoverySnapshot.capture(self._recovery_id, self.document, name, text)
        if snapshot is None:
            self._recovery_store.delete(self._recovery_id)
        else:
            self._recovery_store.write(snapshot)

    def _discard_recovery(self, replace_document=False):
        if getattr(self, "_recovery_store", None) is None:
            return
        if self._recovery_job is not None:
            self.after_cancel(self._recovery_job)
            self._recovery_job = None
        self._recovery_store.delete(self._recovery_id)
        if replace_document:
            self._recovery_store.release(self._recovery_id)
            self._recovery_id = self._recovery_store.new_id()

    def _position_document_changed(self):
        key = (self._table_available(), self.document.text)
        if key == self._position_key:
            return
        self._position_key = key
        self._position_revision += 1
        self._positions = None
        if self._position_job is not None:
            self.after_cancel(self._position_job)
            self._position_job = None
        if key[0] and key[1]:
            self._position_job = self.after(500, self._start_position_analysis)
        self._update_frame_info(self._current_line())

    def _current_line(self):
        if self._view == "table":
            return self.table_grid.selected[0] + 1
        return int(self.text.index("insert").split(".")[0])

    def _start_position_analysis(self):
        self._position_job = None
        if not self._position_key[0] or not self._position_key[1]:
            return
        if self._position_worker_active:
            self._position_waiting = True
            return
        from .line_positions import PositionResult, analyze_positions
        revision = self._position_revision
        snapshot = self.document.text
        base_dir = getattr(self.master, "base_dir", None)
        self._position_worker_active = True
        self._position_waiting = False

        def worker():
            try:
                result = analyze_positions(snapshot, base_dir=base_dir)
            except Exception as error:
                traceback.print_exc()
                result = PositionResult(error=str(error))
            self._position_queue.put((revision, result))

        try:
            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            self._position_worker_active = False
            raise
        if self._position_poll_job is None:
            self._position_poll_job = self.after(50, self._poll_position_analysis)

    def _poll_position_analysis(self):
        self._position_poll_job = None
        try:
            revision, result = self._position_queue.get_nowait()
        except Empty:
            self._position_poll_job = self.after(50, self._poll_position_analysis)
            return
        self._position_worker_active = False
        if revision == self._position_revision:
            self._positions = result.positions if result.success else None
            self._update_frame_info(self._current_line())
        if self._position_waiting and self._position_job is None:
            self._start_position_analysis()

    def _update_title(self):
        name = self.document.path.name if self.document.path else self.words["untitled"]
        mark = " *" if self.document.modified else ""
        self.title(f"{name}{mark} — {self.words['title']}")

    def _sync_text(self):
        before = self.document.text
        self.document.set_text(self.text.get("1.0", "end-1c"))
        if self.document.text != before:
            self._document_revision = getattr(self, "_document_revision", 0) + 1
            if hasattr(self, "frame_status"):
                self._position_document_changed()
            self._schedule_recovery()
        self._update_title()

    def _commit_table_edit(self):
        return (getattr(self, "_view", "raw") != "table" or
                self.table_grid.commit_edit())

    def _table_available(self):
        return (self.document.path is None or
                self.document.path.suffix.lower() == ".tsv")

    def _update_view_button(self):
        if hasattr(self, "_table_button"):
            self._table_button.configure(
                state="normal" if self._table_available() else "disabled")

    def show_raw(self):
        if getattr(self, "_view", "raw") == "table":
            if not self._commit_table_edit():
                return False
            self.table_area.pack_forget()
            if hasattr(self, "table_tools"):
                self.table_tools.pack_forget()
            self.raw_frame.pack(fill="both", expand=True, before=self.status)
            self._view = "raw"
            self._update_status()
            self.text.focus_set()
            self._schedule_highlight()
        return True

    def show_table(self):
        if not self._table_available():
            return False
        if getattr(self, "_view", "raw") == "table":
            return True
        self._sync_text()
        self.table_grid.set_text(self.document.text)
        self.raw_frame.pack_forget()
        self.table_area.pack(fill="both", expand=True, before=self.status)
        if hasattr(self, "table_tools"):
            self.table_tools.pack(side="left", after=self._table_button)
        self._view = "table"
        self._update_status()
        self.table_grid.canvas.focus_set()
        return True

    def _table_cell_changed(self, row, old_line, new_line):
        first = f"{row + 1}.0"
        last = f"{row + 1}.0 lineend"
        if self.text.get(first, last) != old_line:
            return False
        self._replace_table_text(first, last, new_line)
        return True

    def _replace_table_text(self, first, last, value):
        automatic = self.text.cget("autoseparators")
        self.text.configure(autoseparators=False)
        try:
            self.text.edit_separator()
            self.text.delete(first, last)
            self.text.insert(first, value)
            self.text.edit_separator()
        finally:
            self.text.configure(autoseparators=automatic)
        self._sync_text()
        self._update_status()
        self._schedule_line_numbers()
        self._schedule_highlight()

    def _table_text_changed(self, original, updated):
        if self.text.get("1.0", "end-1c") != original:
            return False
        prefix = 0
        while prefix < min(len(original), len(updated)) and original[prefix] == updated[prefix]:
            prefix += 1
        suffix = 0
        while (suffix < min(len(original), len(updated)) - prefix and
               original[len(original) - suffix - 1] == updated[len(updated) - suffix - 1]):
            suffix += 1
        first = f"1.0+{prefix}c"
        last = f"1.0+{len(original) - suffix}c"
        self._replace_table_text(first, last, updated[prefix:len(updated) - suffix])
        return True

    def _table_action(self, name):
        if getattr(self, "_view", "raw") != "table":
            return False
        return getattr(self.table_grid, name)()

    def _on_modified(self, _event=None):
        if self.text.edit_modified():
            self._sync_text()
            if (getattr(self, "_problem_snapshot", None) is not None and
                    self.document.text != self._problem_snapshot):
                self._problems_panel.pack_forget()
                self._problem_rows = {}
                self._problem_snapshot = None
            if (getattr(self, "_inspector_snapshot", None) is not None and
                    self.document.text != self._inspector_snapshot and
                    self._frame_inspector is not None and self._frame_inspector.winfo_exists()):
                self._frame_inspector.mark_stale()
            self.text.edit_modified(False)
            self._update_status()
            self._schedule_line_numbers()
            self._schedule_highlight()

    def _show_document(self):
        self._document_revision = getattr(self, "_document_revision", 0) + 1
        if hasattr(self, "_problems_panel"):
            self._problems_panel.pack_forget()
            self._problem_rows = {}
            self._problem_snapshot = None
        if (getattr(self, "_frame_inspector", None) is not None and
                self._frame_inspector.winfo_exists()):
            self._frame_inspector.mark_stale()
        if getattr(self, "_view", "raw") == "table":
            self.table_area.pack_forget()
            if hasattr(self, "table_tools"):
                self.table_tools.pack_forget()
            self.raw_frame.pack(fill="both", expand=True, before=self.status)
            self._view = "raw"
        if hasattr(self, "table_grid"):
            self.table_grid.selected = (0, 0)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.document.text)
        self.text.edit_reset()
        self.text.edit_modified(False)
        if hasattr(self, "frame_status"):
            self._position_document_changed()
        self._update_title()
        self._update_status()
        self._update_view_button()
        self._schedule_line_numbers()
        self._schedule_highlight()

    def undo(self):
        if not self._commit_table_edit():
            return False
        try:
            self.text.edit_undo()
        except tk.TclError:
            return False
        self._sync_text()
        if getattr(self, "_view", "raw") == "table":
            self.table_grid.set_text(self.document.text)
        self._update_status()
        self._schedule_line_numbers()
        self._schedule_highlight()
        return True

    def redo(self):
        if not self._commit_table_edit():
            return False
        try:
            self.text.edit_redo()
        except tk.TclError:
            return False
        self._sync_text()
        if getattr(self, "_view", "raw") == "table":
            self.table_grid.set_text(self.document.text)
        self._update_status()
        self._schedule_line_numbers()
        self._schedule_highlight()
        return True

    def cut(self):
        if getattr(self, "_view", "raw") == "table":
            return self.table_grid.clipboard_action("Cut")
        if not self.show_raw():
            return
        self.text.event_generate("<<Cut>>")

    def copy(self):
        if getattr(self, "_view", "raw") == "table":
            return self.table_grid.clipboard_action("Copy")
        if not self.show_raw():
            return
        self.text.event_generate("<<Copy>>")

    def paste(self):
        if getattr(self, "_view", "raw") == "table":
            return self.table_grid.clipboard_action("Paste")
        if not self.show_raw():
            return
        self.text.event_generate("<<Paste>>")

    def select_all(self):
        if not self.show_raw():
            return
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "end-1c")
        self.text.see("insert")
        self._update_status()

    def show_find(self, replace=False):
        if not self.show_raw():
            return
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
        if not self.show_raw():
            return False
        query = self.find_query.get()
        if not query:
            self.show_find()
            return False
        selected = self._selection_offsets()
        start = selected[1] if selected else self._cursor_offset()
        return self._select_match(next_match(self.text.get("1.0", "end-1c"), query, start))

    def find_previous(self):
        if not self.show_raw():
            return False
        query = self.find_query.get()
        if not query:
            self.show_find()
            return False
        selected = self._selection_offsets()
        start = selected[0] if selected else self._cursor_offset()
        return self._select_match(previous_match(self.text.get("1.0", "end-1c"), query, start))

    def replace_current(self):
        if not self.show_raw():
            return False
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
        if not self.show_raw():
            return 0
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
        if not self._commit_table_edit():
            return False
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
        self._discard_recovery(replace_document=True)
        self._show_document()
        return True

    def _refresh_recent_menu(self):
        if not hasattr(self, "_recent_menu"):
            return
        self._recent_menu.delete(0, "end")
        recent = self.settings.recent_files
        for index, path in enumerate(recent, start=1):
            self._recent_menu.add_command(label=f"{index} {path}",
                                          command=lambda selected=path: self._open_recent(selected))
        if not recent:
            self._recent_menu.add_command(label=self.words["no_recent"], state="disabled")
        self._recent_menu.add_separator()
        self._recent_menu.add_command(label=self.words["clear_recent"], command=self._clear_recent)

    def _record_recent(self, path):
        if getattr(self, "settings", None) is not None:
            self.settings.add_recent(path)
            self._refresh_recent_menu()

    def _clear_recent(self):
        self.settings.clear_recent()
        self._refresh_recent_menu()

    def _open_recent(self, path):
        try:
            exists = Path(path).is_file()
        except OSError as error:
            messagebox.showerror(self.words["error"], str(error), parent=self)
            return False
        if not exists:
            self.settings.remove_recent(path)
            self._refresh_recent_menu()
            messagebox.showerror(self.words["error"], self.words["missing_recent"] + "\n" + path,
                                 parent=self)
            return False
        return self.open_file(path)

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
        self._discard_recovery(replace_document=True)
        self._show_document()
        self._record_recent(self.document.path)
        return True

    def save(self):
        if self.document.path is None:
            return self.save_as()
        return self._save_to(self.document.path)

    def save_and_convert(self, send_ftp=False):
        """Save the requesting Editor's file, then request local output or FTP."""
        if self.on_convert is None:
            return False
        if self.can_convert is not None and not self.can_convert():
            return False
        self._sync_text()
        # Table may contain a pending Entry value not yet in document.text.
        if (self.document.path is None or self.document.modified or
                getattr(self, "_view", "raw") == "table" or
                self.document.external_status() != "unchanged") and not self.save():
            return False
        self._record_recent(self.document.path)
        return bool(self.on_convert(self.document.path, send_ftp=send_ftp))

    def save_convert_and_send(self):
        return self.save_and_convert(send_ftp=True)

    def validate(self):
        if (self.on_validate is None or self._validation_pending or
                self.can_validate is not None and not self.can_validate()):
            return False
        if not self._commit_table_edit():
            return False
        self._sync_text()
        snapshot, identity = self._inspection_snapshot()
        self._validation_pending = True
        self._show_problem_title(self.words["validating"])

        def receive(result):
            if getattr(self, "_closed", False) or not self.winfo_exists():
                return
            self._validation_pending = False
            self._sync_text()
            if self._inspection_is_current(identity):
                self._show_validation_result(result)
            else:
                self._show_stale_result(self.words["stale_validation"])

        try:
            started = self.on_validate(snapshot, receive)
        except Exception:
            self._validation_pending = False
            self._problems_panel.pack_forget()
            raise
        if not started:
            self._validation_pending = False
            self._problems_panel.pack_forget()
        return bool(started)

    def analyze_frames(self):
        if (self.on_analyze is None or self._analysis_pending or
                self.can_analyze is not None and not self.can_analyze()):
            return False
        if not self._commit_table_edit():
            return False
        self._sync_text()
        snapshot, identity = self._inspection_snapshot()
        source_name = self.document.path.name if self.document.path else self.words["untitled"]
        self._analysis_pending = True
        self._show_problem_title(self.words["analyzing"])
        if self._frame_inspector is not None and self._frame_inspector.winfo_exists():
            self._frame_inspector.mark_stale()

        def receive(result):
            if getattr(self, "_closed", False) or not self.winfo_exists():
                return
            self._analysis_pending = False
            self._sync_text()
            if not self._inspection_is_current(identity):
                self._show_stale_result(self.words["stale_analysis"])
            elif result.success:
                self._problems_panel.pack_forget()
                self._problem_rows = {}
                self._problem_snapshot = None
                from .frame_inspector import FrameInspector
                if self._frame_inspector is None or not self._frame_inspector.winfo_exists():
                    self._frame_inspector = FrameInspector(self, self.words, result.frames, source_name)
                else:
                    self._frame_inspector.set_data(result.frames, source_name)
                    self._frame_inspector.lift()
                self._inspector_snapshot = snapshot.text
            else:
                report = result.report
                if report.stderr:
                    # Debug mode can print every parsed input line to stdout.
                    # Keep Problems focused on the exact converter error text.
                    from .validation import ValidationResult
                    report = ValidationResult(False, stderr=report.stderr,
                                              source_is_tsv=report.source_is_tsv)
                self._show_validation_result(report)

        try:
            started = self.on_analyze(snapshot, receive)
        except Exception:
            self._analysis_pending = False
            self._problems_panel.pack_forget()
            raise
        if not started:
            self._analysis_pending = False
            self._problems_panel.pack_forget()
        return bool(started)

    def _inspection_snapshot(self):
        suffix = self.document.path.suffix.lower() if self.document.path else ".tsv"
        snapshot = ScriptSnapshot(self.document.text, suffix)
        identity = (getattr(self, "_document_revision", 0), self.document.path)
        return snapshot, identity

    def _inspection_is_current(self, identity):
        # An in-progress Entry has not reached the document revision yet.
        return (identity == (getattr(self, "_document_revision", 0), self.document.path)
                and not getattr(self, "_frame_edit_pending", False))

    def _show_problem_title(self, title):
        self._problems_title.config(text=title)
        self._problems_panel.pack(fill="x", before=self.status)

    def _show_stale_result(self, title):
        self._problem_rows = {}
        self._problem_snapshot = None
        self._problems_text.pack_forget()
        self._show_problem_title(title)

    def _show_validation_result(self, result):
        self._problem_snapshot = self.document.text
        self._show_problem_title(self.words["no_errors"] if result.success else
                                 self.words["problems"] + " — " + self.words["jump_hint"])
        self._problems_text.config(state="normal")
        self._problems_text.delete("1.0", "end")
        self._problem_rows = {}
        if result.success:
            self._problems_text.pack_forget()
        else:
            message = result.text or self.words["problems"]
            self._problems_text.insert("1.0", message)
            for display_row, problem in enumerate(
                    result.problems(self.document.text.count("\n") + 1), start=1):
                if problem.line is not None:
                    self._problem_rows[display_row] = problem.line
                    self._problems_text.tag_add("jump", f"{display_row}.0",
                                                f"{display_row}.0 lineend")
            self._problems_text.pack(fill="x")
        self._problems_text.config(state="disabled")

    def _problem_double_click(self, event):
        if self._problem_snapshot != self.document.text:
            return "break"
        display_row = int(self._problems_text.index(f"@{event.x},{event.y}").split(".")[0])
        line = self._problem_rows.get(display_row)
        if line is not None:
            self.jump_to_line(line)
        return "break"

    def jump_to_line(self, line):
        if not 1 <= line <= self.document.text.count("\n") + 1:
            return False
        if self._view == "table":
            if not self._commit_table_edit():
                return False
            self.table_grid.jump_to_row(line - 1)
        else:
            self.text.mark_set("insert", f"{line}.0")
            self.text.see(f"{line}.0")
            self.text.focus_set()
        self._update_status()
        return True

    def save_as(self):
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=self.document.path.suffix if self.document.path else ".tsv",
            initialfile=self.document.path.name if self.document.path else "untitled.tsv",
            filetypes=[("TSV", "*.tsv"), ("Text", "*.txt")],
        )
        return self._save_to(path) if path else False

    def _save_to(self, path):
        try:
            status = self.document.external_status(path)
            overwrite_external = status in ("changed", "missing")
            if status == "unreadable":
                raise ExternalFileConflict(path, status)
            if overwrite_external and not messagebox.askyesno(
                    self.words["external_title"], self.words["external_" + status] + "\n\n" + str(path),
                    parent=self, icon="warning", default="no"):
                return False
            # Refusing a conflict does not even commit a pending cell or touch Undo.
            if not self._commit_table_edit():
                return False
            self._sync_text()
            saved_path = self.document.save(path, overwrite_external=overwrite_external)
        except (OSError, UnicodeError, ValueError) as error:
            if isinstance(error, ExternalFileConflict):
                key = "external_unreadable" if error.status == "unreadable" else "external_retry"
                detail = self.words[key] + "\n\n" + str(error.path)
            else:
                detail = str(error)
            messagebox.showerror(self.words["error"], detail, parent=self)
            return False
        self._discard_recovery()
        self._update_title()
        if hasattr(self, "frame_status"):
            self._position_document_changed()
        self._update_status()
        if getattr(self, "_view", "raw") == "table" and saved_path.suffix.lower() != ".tsv":
            self.show_raw()
        self._update_view_button()
        self._record_recent(saved_path)
        if self.on_saved:
            self.on_saved(saved_path)
        return True

    def close_editor(self):
        if self._confirm_discard():
            self._discard_recovery()
            if self._gutter_job is not None:
                self.after_cancel(self._gutter_job)
                self._gutter_job = None
            self.destroy()
            return True
        return False
