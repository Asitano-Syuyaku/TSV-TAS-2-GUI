"""Text editor with a literal TSV table view, shared by both GUI languages."""

import sys
import threading
import tkinter as tk
from pathlib import Path
import traceback
from queue import Empty, SimpleQueue
from tkinter import filedialog, font as tkfont, messagebox

from .document import EditorDocument
from .file_state import ExternalFileConflict
from .recovery import DEBOUNCE_MS, RecoverySnapshot, RecoveryStore
from .resources import neon_icon_path, palette_icon_path
from .snapshot import ScriptSnapshot
from .text_ops import (file_kind, find_next as next_match, find_previous as previous_match,
                       line_column, replace_all as replace_every, replace_current as replace_match)
from .theme import (CATEGORY_COLORS, COLORS, FONTS, HEAT_RAMP, SIZES, SPACING, SYNTAX_COLORS,
                    button_options, editor_fonts, entry_options, label_options, menu_options, px)
from .tsv_syntax import CANDIDATES, PALETTE_PAGES, syntax_spans
from .dopa.words import MOTION_LEVELS, WORDS as DOPA_WORDS

if __package__ == "editor":
    from app_settings import AppSettings, EDITOR_SIZE_DEFAULT, EDITOR_SIZE_MIN, EDITOR_SIZE_MAX
    from background import hold_gc, resume_gc, resume_gc_soon
else:
    from ..app_settings import AppSettings, EDITOR_SIZE_DEFAULT, EDITOR_SIZE_MIN, EDITOR_SIZE_MAX
    from ..background import hold_gc, resume_gc, resume_gc_soon


HIGHLIGHT_COLORS = SYNTAX_COLORS


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
        "stick_preview": "Stick Preview (1P)",
        "preview_updating": "Updating...", "preview_unavailable": "Unavailable",
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
        "go_to_frame": "Go to Frame", "go_to": "Go to:",
        "frame_range": "Enter 0–{last}", "no_frames": "No valid frames",
        "frame_no_source": "No source row for this frame",
        "frame_commit_failed": "Finish the cell edit first",
        # Command deck entry points (dopagaki3.md §5.1); same commands as the menu.
        "deck_validate": "Validate  F6", "deck_analyze": "Analyze  F7",
        "deck_convert": "Save & Convert  F5", "deck_send": "Convert & SEND  F8",
        "deck_validate_compact": "Validate", "deck_analyze_compact": "Analyze",
        "deck_convert_compact": "Save & Convert", "deck_send_compact": "Convert & SEND",
        # Decorative Dopagaki words only; factual messages above stay unchanged.
        "dopa_oshii": "SO CLOSE!", "dopa_clear": "✔",
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
        "stick_preview": "スティックプレビュー (1P)",
        "preview_updating": "更新中...", "preview_unavailable": "未確定",
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
        "go_to_frame": "フレームへ移動", "go_to": "移動:",
        "frame_range": "0～{last}を入力", "no_frames": "有効なフレームなし",
        "frame_no_source": "対応する元の行がありません",
        "frame_commit_failed": "セルの編集を完了してください",
        "deck_validate": "検証  F6", "deck_analyze": "解析  F7",
        "deck_convert": "保存して変換  F5", "deck_send": "変換してSEND  F8",
        "deck_validate_compact": "検証", "deck_analyze_compact": "解析",
        "deck_convert_compact": "保存して変換", "deck_send_compact": "変換してSEND",
        "dopa_oshii": "おしい!", "dopa_clear": "✔",
    },
}


class EditorWindow(tk.Toplevel):
    def __init__(self, master, language="en", initial_path=None, on_saved=None,
                 on_convert=None, can_convert=None, on_validate=None, can_validate=None,
                 on_analyze=None, can_analyze=None, settings=None, recovery=None):
        super().__init__(master)
        self.words = LABELS[language]
        self._language = language
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
        self._stick_frames = None
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
        self._workspace_job = None
        self._workspace_size = (self.settings.get("editor_width"),
                                self.settings.get("editor_height"))
        self.geometry("{}x{}".format(*self._fitted_size(*self._workspace_size)))
        self.minsize(*self._fitted_size(px(EDITOR_SIZE_MIN[0]), px(EDITOR_SIZE_MIN[1])))
        self.configure(background=COLORS["app_background"])
        self._theme_fonts = editor_fonts(self)

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
            ("go_to_frame", self.focus_frame_entry, "Ctrl+G"),
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
        dopa_menus = self._build_dopa_menu(menu)
        if self._windowingsystem != "win32":
            # Windows menus stay native (§8.8); X11/macOS Tk menus take the skin.
            for themed in (menu, file_menu, self._recent_menu, edit_menu, search_menu, table_menu,
                           *dopa_menus):
                themed.configure(**menu_options())
        self.config(menu=menu)

        from .widgets import scrollbar

        self._build_command_deck()
        # FEVER HUD (§6): left FRAME METER (data) over the factual readout and Go
        # field; right REWARD canvas (game numbers, shouts, background motion).
        hud = tk.Frame(self, background=COLORS["panel_background"],
                       highlightthickness=1, highlightbackground=COLORS["subtle_border"])
        hud.pack(fill="x", padx=SPACING["outer"], pady=(SPACING["gap"], 0))
        self.hud_row = hud
        meter_column = tk.Frame(hud, background=COLORS["panel_background"])
        meter_column.pack(side="left", fill="y")
        self.meter_canvas = tk.Canvas(meter_column, width=px(470), height=px(58), highlightthickness=0,
                                      background=COLORS["panel_background"], takefocus=False)
        self.meter_canvas.pack(side="top", anchor="w")
        readout = tk.Frame(meter_column, background=COLORS["panel_background"])
        readout.pack(side="top", fill="x", pady=(0, SPACING["gap"]))
        # The factual text stays exactly as before, now a small muted caption (§5.2).
        self.frame_status = tk.Label(readout, anchor="w", padx=SPACING["section"],
                                     **label_options("panel_background", "small", self._theme_fonts))
        self.frame_status.pack(side="left")
        frame_navigation = tk.Frame(readout, background=COLORS["panel_background"])
        frame_navigation.pack(side="left", padx=SPACING["deck_group"])
        tk.Label(frame_navigation, text=self.words["go_to"],
                 **label_options(role="small", fonts=self._theme_fonts)).pack(side="left")
        self.frame_entry = tk.Entry(frame_navigation, width=7, exportselection=False,
                                    font=self._theme_fonts["standard"], **entry_options())
        self.frame_entry.pack(side="left", padx=SPACING["gap"])
        self.frame_go_button = tk.Button(frame_navigation, text=self.words["go"],
                                         command=self.go_to_frame, **button_options("primary"))
        self.frame_go_button.pack(side="left")
        self._frame_jump_feedback = tk.Label(frame_navigation, anchor="w",
                                             **label_options(role="small", fonts=self._theme_fonts))
        self._frame_jump_feedback.configure(foreground=COLORS["warning"])
        self.frame_entry.bind("<Return>", lambda event: self._shortcut(self.go_to_frame))
        self.frame_entry.bind("<Escape>", lambda event: self._shortcut(self._focus_editor))
        self.reward_canvas = tk.Canvas(hud, height=px(76), highlightthickness=0, takefocus=False,
                                       background=COLORS["panel_background"])
        self.reward_canvas.pack(side="left", fill="both", expand=True)

        # RIM (§4.3): the WORK layer's neon edge. Without HEAT yet, it uses E's first stop.
        self._rim = tk.Frame(self, background=COLORS["app_background"],
                             highlightthickness=SPACING["rim"],
                             highlightbackground=HEAT_RAMP[0], highlightcolor=HEAT_RAMP[0])
        self._rim.pack(fill="both", expand=True, padx=SPACING["outer"], pady=(SPACING["gap"], 0))
        frame = tk.Frame(self._rim, background=COLORS["app_background"])
        frame.pack(fill="both", expand=True)
        self.raw_frame = frame
        fixed_font = tkfont.nametofont("TkFixedFont")
        self._fixed_font = fixed_font
        self.line_numbers = tk.Canvas(frame, width=40, highlightthickness=0,
                                       background=COLORS["panel_background"])
        self.text = tk.Text(frame, wrap="none", font=fixed_font, undo=True,
                            exportselection=False,
                            tabs=(fixed_font.measure(" " * 8),), **entry_options())
        self.text.configure(highlightthickness=0)
        vertical = scrollbar(frame, orient="vertical", command=self.text.yview)
        horizontal = scrollbar(frame, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=lambda first, last: self._on_scroll(vertical, first, last),
                            xscrollcommand=horizontal.set)
        for kind, color in HIGHLIGHT_COLORS.items():
            self.text.tag_configure("syntax_" + kind, foreground=color)
        # Cursor line (§8.2) sits below selection; syntax tags only set foreground.
        self.text.tag_configure("cursor_line", background=COLORS["cursor_line"])
        self.text.tag_lower("cursor_line")
        self._cursor_line = None
        self.line_numbers.grid(row=0, column=0, sticky="ns")
        self.text.grid(row=0, column=1, sticky="nsew")
        vertical.grid(row=0, column=2, sticky="ns")
        horizontal.grid(row=1, column=1, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        # Import lazily so file/document logic remains usable without Tk widgets.
        from .grid import TableGrid
        self.table_area = tk.Frame(self._rim, background=COLORS["app_background"])
        self.table_grid = TableGrid(self.table_area, fixed_font, self._table_cell_changed,
                                    self._table_text_changed, self._update_status,
                                    self.undo, self.redo, self.words,
                                    on_edit_change=self._table_edit_pending,
                                    on_column_resize=self._remember_column_width,
                                    on_effect=self._table_effect)
        self.table_grid.columns.import_widths(self.settings.get("editor_column_widths"))
        self.table_grid._update_region()
        self._load_palette_icons()
        self._build_input_palette()
        self.table_grid.pack(side="left", fill="both", expand=True)
        status_row = tk.Frame(self, background=COLORS["panel_background"])
        # Reserved from the bottom before the expanding work area: a short window
        # shrinks the Table, never the status row (mute / effects chips).
        status_row.pack(side="bottom", fill="x", pady=(SPACING["gap"], 0), before=self._rim)
        self._status_row = status_row
        # Separate widget: the status text itself stays exactly as before.
        self._modified_dot = tk.Label(status_row, text="", width=2, anchor="e",
                                      **label_options("panel_background", "small", self._theme_fonts))
        self._modified_dot.configure(foreground=COLORS["neon_magenta"])
        self._modified_dot.pack(side="left", padx=(SPACING["gap"], 0))
        self.status = tk.Label(status_row, anchor="w", padx=SPACING["gap"],
                               **label_options("panel_background", "small", self._theme_fonts))
        self.status.configure(pady=SPACING["status_y"])
        self.status.pack(side="left", fill="x", expand=True)
        # Always-reachable effects strength (§12.1); a click cycles 100 -> 0%.
        self._dopa_chip = tk.Label(status_row, cursor="hand2", padx=SPACING["section"],
                                   **label_options("secondary_background", "small", self._theme_fonts))
        self._dopa_chip.pack(side="right", padx=SPACING["gap"], pady=1)
        self._dopa_chip.bind("<Button-1>", lambda event: self._cycle_dopa_motion())
        # Mute is always one click (or Ctrl+Shift+M) away (§12.1).
        self._sound_chip = tk.Label(status_row, cursor="hand2", padx=SPACING["section"],
                                    **label_options("secondary_background", "small", self._theme_fonts))
        self._sound_chip.pack(side="right", padx=(SPACING["gap"], 0), pady=1)
        self._sound_chip.bind("<Button-1>", lambda event: self._toggle_sound())
        self._problems_panel = tk.Frame(self, background=COLORS["panel_background"],
                                        highlightthickness=1, highlightbackground=COLORS["border"])
        # Hazard tape (§8.6): shown only above a failed result.
        self._problems_tape = tk.Canvas(self._problems_panel, height=6, highlightthickness=0,
                                        background=COLORS["on_neon"])
        self._problems_tape.bind("<Configure>", self._draw_problems_tape)
        problems_header = tk.Frame(self._problems_panel, background=COLORS["panel_background"])
        problems_header.pack(fill="x")
        self._problems_header = problems_header
        self._problems_badge = tk.Label(problems_header, padx=SPACING["section"],
                                        **label_options(role="heading", fonts=self._theme_fonts))
        self._problems_title = tk.Label(problems_header, anchor="w",
                                         **label_options(role="heading", fonts=self._theme_fonts))
        self._problems_title.pack(side="left", fill="x", expand=True)
        self._problems_text = tk.Text(self._problems_panel, height=4, wrap="word",
                                      state="disabled", takefocus=False,
                                      font=fixed_font, **entry_options())
        self._problems_text.configure(highlightthickness=0)
        self._problems_text.tag_configure("jump", foreground=COLORS["accent"], underline=True)
        self._problems_text.bind("<Double-Button-1>", self._problem_double_click)
        self._problem_rows = {}
        self._problem_snapshot = None
        self._update_view_button()

        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<KeyRelease>", self._update_status)
        self.text.bind("<ButtonRelease-1>", self._update_status)
        self.text.bind("<Configure>", self._on_text_configure)
        for sequence in ("<KeyPress-Return>", "<KeyPress-KP_Enter>"):
            self.text.bind(sequence, self._raw_return, add="+")
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
            ("<Control-g>", self.focus_frame_entry),
            ("<F3>", self.find_next), ("<Shift-F3>", self.find_previous),
            ("<Control-Shift-D>", self._cycle_dopa_motion),
            ("<Control-Shift-d>", self._cycle_dopa_motion),
            ("<Control-Shift-M>", self._toggle_sound),
            ("<Control-Shift-m>", self._toggle_sound),
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
            ("<Control-g>", self.focus_frame_entry),
            ("<F3>", self.find_next),
            ("<Shift-F3>", self.find_previous),
            ("<Control-Shift-D>", self._cycle_dopa_motion),
            ("<Control-Shift-d>", self._cycle_dopa_motion),
            ("<Control-Shift-M>", self._toggle_sound),
            ("<Control-Shift-m>", self._toggle_sound),
        ):
            self.bind(sequence, lambda event, action=command: self._shortcut(action))
        self.protocol("WM_DELETE_WINDOW", self.close_editor)
        self.bind("<Destroy>", self._on_destroy)
        self.bind("<Configure>", self._workspace_resized)
        from .dopa.director import DopaDirector
        self._dopa = DopaDirector(self, self._language, motion=self.settings.get("dopa_motion"),
                                  flashes=self.settings.get("dopa_flash"),
                                  sound=self.settings.get("dopa_sound"),
                                  volume=self.settings.get("dopa_volume"),
                                  audio=self._audio_service())
        self.stick_preview.effects = self._dopa
        self._update_dopa_chip()
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
            self._restore_editor_view()

    def _fit_density(self, height):
        """Short windows trade duplicates and spare lines for Table rows, never font size."""
        compact = height / px(100) * 100 < 600  # Logical (96-DPI) pixels.
        if compact == getattr(self, "_compact_height", None):
            return
        self._compact_height = compact
        # The caption repeats the FRAME METER's values: optional when space is short.
        if compact:
            self.frame_status.pack_forget()
        else:
            self.frame_status.pack(side="left", before=self.frame_entry.master)
        self._problems_text.configure(height=2 if compact else 4)

    def _fitted_size(self, width, height):
        """Scale the never-saved default with the display, and always fit the screen."""
        if (width, height) == EDITOR_SIZE_DEFAULT:
            width, height = px(width), px(height)
        if not sys.platform.startswith("win"):
            return width, height  # X11 window managers place and constrain on their own.
        try:
            screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        except tk.TclError:
            return width, height
        return min(width, max(640, screen_w - 40)), min(height, max(400, screen_h - 80))

    def _build_command_deck(self):
        """COMMAND DECK (§5.1): entry points that call the existing commands."""
        deck = tk.Frame(self, background=COLORS["panel_background"])
        deck.pack(fill="x")
        tk.Frame(self, height=1, background=COLORS["subtle_border"]).pack(fill="x")
        self.command_deck = deck
        pad = {"pady": SPACING["deck_y"]}
        heading = self._theme_fonts["heading"]
        # Pack F8 then F5 first: pack gives earlier widgets space first, so a
        # narrow window squeezes the left groups, never the round-ending actions.
        self._send_button = tk.Button(deck, command=self.save_convert_and_send,
                                      **button_options("send", fonts={"standard": heading}))
        self._send_button.configure(padx=SPACING["deck_group"], pady=SPACING["gap"])
        self._send_button.pack(side="right", padx=(SPACING["gap"], SPACING["outer"]), **pad)
        self._convert_button = tk.Button(deck, command=self.save_and_convert,
                                         **button_options("convert", fonts={"standard": heading}))
        self._convert_button.pack(side="right", padx=SPACING["gap"], **pad)
        # Segmented Raw | Table: the selected half is CYAN with dark text.
        toggle = tk.Frame(deck, background=COLORS["subtle_border"])
        toggle.pack(side="left", padx=(SPACING["outer"], 0), **pad)
        self._view_toggle = toggle
        self._raw_button = tk.Button(toggle, text=self.words["raw_view"],
                                     command=self.show_raw, **button_options())
        self._raw_button.pack(side="left", padx=(1, 0), pady=1)
        self._table_button = tk.Button(toggle, text=self.words["table_view"],
                                       command=self.show_table, **button_options())
        self._table_button.pack(side="left", padx=1, pady=1)
        self.table_tools = tk.Frame(deck, background=COLORS["panel_background"])
        tk.Button(self.table_tools, text=self.words["add_row"],
                  command=lambda: self._table_action("insert_row_below"),
                  **button_options()).pack(side="left", padx=SPACING["button_gap"])
        tk.Button(self.table_tools, text=self.words["add_column"],
                  command=lambda: self._table_action("insert_column_right"),
                  **button_options()).pack(side="left", padx=SPACING["button_gap"])
        checks = tk.Frame(deck, background=COLORS["panel_background"])
        checks.pack(side="left", padx=SPACING["deck_group"], **pad)
        self._validate_button = tk.Button(checks, command=self.validate, **button_options())
        self._validate_button.pack(side="left", padx=SPACING["button_gap"])
        self._analyze_button = tk.Button(checks, command=self.analyze_frames, **button_options())
        self._analyze_button.pack(side="left", padx=SPACING["button_gap"])
        # (button, full label key, compact label key); compact drops the shortcut suffix.
        self._deck_checks = checks
        self._deck_labels = ((self._validate_button, "deck_validate"),
                             (self._analyze_button, "deck_analyze"),
                             (self._convert_button, "deck_convert"),
                             (self._send_button, "deck_send"))
        self._deck_compact = None
        self._deck_full_width = None
        self._set_deck_compact(False)
        deck.bind("<Configure>", self._fit_command_deck)

    def _set_deck_compact(self, compact):
        if compact == self._deck_compact:
            return
        self._deck_compact = compact
        for button, key in self._deck_labels:
            button.configure(text=self.words[key + "_compact" if compact else key])
        # Compact also tightens group gaps; F8 stays the widest button.
        gap = SPACING["gap"] if compact else SPACING["deck_group"]
        self._deck_checks.pack_configure(padx=gap)
        self._send_button.configure(padx=SPACING["button_x"] if compact else SPACING["deck_group"])

    def _fit_command_deck(self, event):
        # Full labels' required width is known after the first layout pass.
        if self._deck_full_width is None and not self._deck_compact:
            self._deck_full_width = self.command_deck.winfo_reqwidth()
        if self._deck_full_width is not None:
            self._set_deck_compact(event.width < self._deck_full_width)

    # 1F FEVER (dopagaki3.md §7, §12) -----------------------------------------

    def _build_dopa_menu(self, menubar):
        words = DOPA_WORDS[self._language]
        menu = tk.Menu(menubar, tearoff=False)
        levels = tk.Menu(menu, tearoff=False)
        self._dopa_motion_var = tk.IntVar(self, value=self.settings.get("dopa_motion"))
        self._dopa_flash_var = tk.BooleanVar(self, value=self.settings.get("dopa_flash"))
        for level in MOTION_LEVELS:
            levels.add_radiobutton(
                label=words["effects_level"].format(n=level) if level else words["effects_off"],
                value=level, variable=self._dopa_motion_var,
                command=lambda: self._set_dopa(motion=self._dopa_motion_var.get()))
        menu.add_cascade(label=words["effects"], menu=levels, accelerator="Ctrl+Shift+D")
        menu.add_checkbutton(label=words["flashes"], variable=self._dopa_flash_var,
                             command=lambda: self._set_dopa(flash=self._dopa_flash_var.get()))
        # Sound items exist because sound exists (P4); disabled where it cannot play.
        audible = "normal" if self._audio_service().available else "disabled"
        self._dopa_sound_var = tk.BooleanVar(self, value=self.settings.get("dopa_sound"))
        self._dopa_volume_var = tk.IntVar(self, value=self.settings.get("dopa_volume"))
        menu.add_separator()
        menu.add_checkbutton(label=words["sound"], variable=self._dopa_sound_var,
                             accelerator="Ctrl+Shift+M", state=audible,
                             command=lambda: self._set_dopa(sound=self._dopa_sound_var.get()))
        volumes = tk.Menu(menu, tearoff=False)
        for level in (3, 2, 1):
            volumes.add_radiobutton(label=words["volume_levels"][level], value=level,
                                    variable=self._dopa_volume_var,
                                    command=lambda: self._set_dopa(volume=self._dopa_volume_var.get()))
        menu.add_cascade(label=words["volume"], menu=volumes, state=audible)
        menubar.add_cascade(label=words["menu"], menu=menu)
        return menu, levels, volumes

    def _audio_service(self):
        from .dopa.audio import AudioService
        path = getattr(self.settings, "path", None)
        return AudioService.for_root(self._root(), path.parent if path else None)

    def _toggle_sound(self):
        if self._audio_service().available:
            self._set_dopa(sound=not self.settings.get("dopa_sound"))

    def _cycle_dopa_motion(self):
        current = self.settings.get("dopa_motion")
        index = MOTION_LEVELS.index(current) if current in MOTION_LEVELS else 0
        self._set_dopa(motion=MOTION_LEVELS[(index + 1) % len(MOTION_LEVELS)])

    def _set_dopa(self, motion=None, flash=None, sound=None, volume=None):
        values = {}
        if motion is not None:
            values["dopa_motion"] = motion
        if flash is not None:
            values["dopa_flash"] = bool(flash)
        if sound is not None:
            values["dopa_sound"] = bool(sound)
        if volume is not None:
            values["dopa_volume"] = volume
        self._remember_workspace(**values)
        # Every open Editor shares these effect preferences.
        for widget in self.master.winfo_children():
            apply = getattr(widget, "_apply_dopa_settings", None)
            if apply is not None and getattr(widget, "_dopa", None) is not None:
                apply()

    def _apply_dopa_settings(self):
        settings = self.settings
        motion, flash = settings.get("dopa_motion"), settings.get("dopa_flash")
        sound, volume = settings.get("dopa_sound"), settings.get("dopa_volume")
        self._dopa_motion_var.set(motion)
        self._dopa_flash_var.set(flash)
        self._dopa_sound_var.set(sound)
        self._dopa_volume_var.set(volume)
        self._dopa.set_settings(motion, flash, sound=sound, volume=volume)
        self._update_dopa_chip()

    def _update_dopa_chip(self):
        chip = getattr(self, "_dopa_chip", None)
        if chip is not None:
            motion = self.settings.get("dopa_motion")
            chip.configure(text=DOPA_WORDS[self._language]["chip"].format(n=motion),
                           foreground=COLORS["neon_yellow"] if motion else COLORS["muted_text"])
        sound_chip = getattr(self, "_sound_chip", None)
        if sound_chip is not None:
            words = DOPA_WORDS[self._language]
            if not self._audio_service().available:
                text, color = words["chip_none"], COLORS["muted_text"]
            elif self.settings.get("dopa_sound"):
                text, color = words["chip_on"], COLORS["neon_magenta"]
            else:
                text, color = words["chip_off"], COLORS["muted_text"]
            sound_chip.configure(text=text, foreground=color)

    def _table_effect(self, kind, info):
        director = getattr(self, "_dopa", None)
        if director is None or self._closed:
            return
        if kind == "commit":
            director.cell_committed(info["cell"], info["direction"], info["active"])
        elif kind == "transform":
            director.table_transformed()

    def _raw_return(self, _event=None):
        # Runs before the Text class binding inserts the newline; check afterwards.
        lines = int(self.text.index("end-1c").split(".")[0])
        self.after_idle(lambda: self._raw_return_done(lines))

    def _raw_return_done(self, lines_before):
        director = getattr(self, "_dopa", None)
        if director is None or self._closed or self._view != "raw":
            return
        if int(self.text.index("end-1c").split(".")[0]) <= lines_before:
            return  # No newline was inserted (e.g. an IME confirmation).
        line = int(self.text.index("insert").split(".")[0]) - 1
        if line >= 1 and self.text.get(f"{line}.0", f"{line}.0 lineend").strip():
            director.raw_line_committed(line)

    def _draw_problems_tape(self, _event=None):
        tape = self._problems_tape
        tape.delete("all")
        width, height, step = tape.winfo_width(), 6, 12
        for x in range(-step, width + step, step):
            tape.create_polygon(x, height, x + step / 2, 0, x + step, 0, x + step / 2, height,
                                fill=COLORS["neon_orange"], outline="")

    def _set_problem_badge(self, kind=None):
        """Decorative badge/tape beside the factual Problems title (§8.6)."""
        badge = getattr(self, "_problems_badge", None)
        if badge is None:
            return
        if kind is None:
            badge.pack_forget()
            self._problems_tape.pack_forget()
            return
        failed = kind == "oshii"
        badge.configure(text=self.words["dopa_oshii" if failed else "dopa_clear"],
                        foreground=COLORS["neon_orange" if failed else "neon_green"])
        badge.pack(side="left", before=self._problems_title)
        if failed:
            self._problems_tape.pack(fill="x", before=self._problems_header)
        else:
            self._problems_tape.pack_forget()

    def _load_palette_icons(self):
        for candidate in CANDIDATES:
            if candidate.category != "buttons" or not candidate.icon_key:
                continue
            path = neon_icon_path(palette_icon_path(candidate.icon_key))
            try:
                if not path.is_file():
                    continue
                self._palette_icons[candidate.icon_key] = tk.PhotoImage(master=self, file=str(path))
            except (OSError, tk.TclError):
                # One missing or unreadable icon must not prevent editor startup.
                continue

    def _build_input_palette(self):
        from .stick_preview import StickPreview

        fonts = getattr(self, "_theme_fonts", FONTS)
        self.input_palette = tk.Frame(self.table_area, width=px(SIZES["palette_width"]),
                                      background=COLORS["panel_background"],
                                      highlightthickness=1, highlightbackground=COLORS["subtle_border"])
        self.input_palette.pack_propagate(False)
        self.input_palette.pack(side="right", fill="y")
        header = tk.Frame(self.input_palette, background=COLORS["panel_background"])
        header.pack(fill="x", padx=SPACING["section"], pady=SPACING["gap"])
        tk.Label(header, text=self.words["input_palette"], anchor="w",
                 **label_options(role="heading", fonts=fonts)).pack(side="left")
        self._palette_next = tk.Button(
            header, text="▶", width=2, takefocus=False,
            command=lambda: self._show_palette_page(self._palette_page + 1), **button_options())
        self._palette_next.pack(side="right")
        self._palette_page_label = tk.Label(header, **label_options(role="small", fonts=fonts))
        self._palette_page_label.pack(side="right", padx=SPACING["gap"])
        self._palette_previous = tk.Button(
            header, text="◀", width=2, takefocus=False,
            command=lambda: self._show_palette_page(self._palette_page - 1), **button_options())
        self._palette_previous.pack(side="right")
        body = tk.Frame(self.input_palette, background=COLORS["panel_background"])
        body.pack(fill="both", expand=True)
        self._palette_pages = []
        for categories in PALETTE_PAGES:
            page = tk.Frame(body, background=COLORS["panel_background"])
            docked = "stick_preview" in categories
            # The Basic page docks Stick Preview below its own scroll viewport (§8.4),
            # so a short window scrolls the buttons, never the preview.
            viewport = tk.Frame(page, background=COLORS["panel_background"]) if docked else page
            canvas = tk.Canvas(viewport, highlightthickness=0, yscrollincrement=20,
                               background=COLORS["panel_background"])
            scrollbar = self._make_scrollbar(viewport, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            if docked:
                viewport.pack(side="top", fill="x")
            content = tk.Frame(canvas, background=COLORS["panel_background"])
            content_id = canvas.create_window((0, 0), window=content, anchor="nw")
            content.bind("<Configure>", lambda event, parts=(page, canvas, content, docked):
                         self._palette_content_changed(*parts))
            canvas.bind("<Configure>", lambda event, target=canvas, item=content_id:
                        target.itemconfigure(item, width=event.width))
            rules = []
            for category in categories:
                if category == "stick_preview":
                    self.stick_preview = StickPreview(page, fonts=fonts,
                                                       title=self.words[category])
                    self.stick_preview.pack(side="top", fill="x", padx=SPACING["gap"])
                    continue
                # Category color (§8.3) on the heading text plus a short rule;
                # headings stay direct Label children of the page content.
                color = CATEGORY_COLORS.get(category, COLORS["muted_text"])
                heading = tk.Label(content, text=self.words[category], anchor="w",
                                   **label_options(role="heading", fonts=fonts))
                heading.configure(foreground=color)
                heading.pack(fill="x", padx=SPACING["section"],
                             pady=(SPACING["category_top"], 0))
                rule = tk.Frame(content, width=28, height=2, background=color)
                rule.pack(anchor="w", padx=SPACING["section"], pady=(1, SPACING["category_bottom"] + 2))
                rules.append(rule)
                group = tk.Frame(content, background=COLORS["panel_background"])
                group.pack(fill="x", padx=SPACING["gap"])
                buttons = [(self._palette_button(group, candidate), self._palette_span(candidate))
                           for candidate in CANDIDATES if candidate.category == category]
                self._grid_palette_group(group, buttons, 2)
                if category == "buttons":
                    self._palette_fold, self._palette_fold_columns = (group, buttons), 2
            if docked:
                page.bind("<Configure>", lambda event, parts=(page, canvas, content):
                          self._fit_docked_page(*parts))
            self._bind_palette_scroll(page, canvas)
            self._palette_rules = getattr(self, "_palette_rules", []) + [rules]
            self._palette_pages.append((page, canvas))
        settings = getattr(self, "settings", None)
        self._show_palette_page(settings.get("editor_palette_page", 0) + 1 if settings else 1,
                                remember=False)

    def _grid_palette_group(self, group, buttons, columns, previous=None):
        """Lay buttons out in `columns`; `previous` clears a former layout's extra tracks."""
        for column in range(max(columns, previous or 0)):
            used = column < columns
            group.grid_columnconfigure(column, weight=int(used), uniform="palette" if used else "")
        slot = 0
        for button, span in buttons:
            if span == 2 and slot % 2:
                slot += 1
            row, column = divmod(slot, columns)
            button.grid(row=row, column=column, columnspan=span,
                        sticky="ew", padx=SPACING["button_gap"], pady=SPACING["palette_grid_y"])
            slot += span
        rows = (slot + columns - 1) // columns
        for row in range(len(buttons) if previous else rows):
            group.grid_rowconfigure(row, minsize=px(SIZES["palette_row"]) if row < rows else 0)

    def _palette_content_changed(self, page, canvas, content, docked):
        canvas.configure(scrollregion=canvas.bbox("all"))
        if docked:
            self._fit_docked_page(page, canvas, content)

    def _fit_docked_page(self, page, canvas, content):
        """Responsive density for the Basic page (§8.3/§8.4), never smaller text.

        The buttons viewport takes what the docked Stick Preview leaves. If the
        2-column buttons would not fit there, the icon buttons fold into 4 columns
        (same order: two pairs per row). Whatever still does not fit scrolls.
        """
        available = page.winfo_height() - self.stick_preview.winfo_reqheight()
        if available <= 1:
            return
        group, buttons = self._palette_fold
        rows = (len(buttons) + self._palette_fold_columns - 1) // self._palette_fold_columns
        row_height = group.winfo_reqheight() / rows
        wide_rows = (len(buttons) + 1) // 2
        wide_height = content.winfo_reqheight() + (wide_rows - rows) * row_height
        columns = 4 if wide_height > available else 2
        current = self._palette_fold_columns
        if columns != current:
            self._palette_fold_columns = columns
            self._grid_palette_group(group, buttons, columns, previous=current)
            content.update_idletasks()
        height = max(1, min(content.winfo_reqheight(), available))
        if canvas.winfo_reqheight() != height:
            canvas.configure(height=height)

    @staticmethod
    def _make_scrollbar(master, **options):
        from .widgets import scrollbar

        return scrollbar(master, **options)

    def _show_palette_page(self, number, *, remember=True):
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
        if remember:
            self._remember_workspace(editor_palette_page=number - 1)
            director = getattr(self, "_dopa", None)
            if director is not None:
                director.grow_rules(self._palette_rules[number - 1])

    def _remember_workspace(self, **values):
        settings = getattr(self, "settings", None)
        if settings is not None:
            settings.update(**values)

    def _remember_column_width(self, column):
        # Merge just the dragged column with shared state. Another Editor's newer
        # widths must not be replaced by this window's older local layout.
        widths = self.settings.get("editor_column_widths")
        key = str(column)
        overrides = self.table_grid.columns.export_widths()
        if key in overrides:
            widths[key] = overrides[key]
        else:
            widths.pop(key, None)
        self._remember_workspace(editor_column_widths=widths)

    def _workspace_resized(self, event):
        if event.widget is not self or self._closed:
            return
        self._fit_density(event.height)
        size = event.width, event.height
        if (size == self._workspace_size or
                not all(low <= value <= high for value, low, high in
                        zip(size, EDITOR_SIZE_MIN, EDITOR_SIZE_MAX))):
            return
        self._workspace_size = size
        # Keep only the changed fields in the shared state now. Debounce the disk
        # write, not a stale per-window copy of all workspace preferences.
        self.settings.update(editor_width=size[0], editor_height=size[1], persist=False)
        if self._workspace_job is not None:
            self.after_cancel(self._workspace_job)
        self._workspace_job = self.after(400, self._flush_workspace)

    def _flush_workspace(self):
        job = getattr(self, "_workspace_job", None)
        if job is not None:
            self.after_cancel(job)
            self._workspace_job = None
            self.settings.save()

    def _restore_editor_view(self):
        settings = getattr(self, "settings", None)
        if settings is not None and settings.get("editor_view") == "table" and self._table_available():
            self.show_table(remember=False)

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
        options = {**button_options("palette"),
                   "text": (candidate.short_label or candidate.display_label)
                   if image is not None else candidate.display_label,
                   "anchor": "w"}
        if image is not None:
            options.update(image=image, compound="left")
        holder = []

        def press(item=candidate):
            self.table_grid.insert_candidate(item)  # The real action first.
            director = getattr(self, "_dopa", None)
            if director is not None and holder:
                director.palette_pressed(holder[0], CATEGORY_COLORS.get(
                    item.category, COLORS["muted_text"]))

        button = tk.Button(parent, command=press, **options)
        holder.append(button)
        return button

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
            # A cancelled poller must not leave GC paused; the root outlives us.
            resume_gc_soon(self._root())
            self._flush_workspace()
            self._closed = True
            # Release Tk images on the UI thread, before background CSV parsing
            # can collect a destroyed Editor's cyclic references.
            self._palette_icons.clear()
            director = getattr(self, "_dopa", None)
            if director is not None:
                director.destroy()  # Stops its ticker; releases its fonts here.
            getattr(self, "_theme_fonts", {}).clear()
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
        self.line_numbers.delete("line")  # Keep in-flight "fx" items.
        index = self.text.index("@0,0")
        current = getattr(self, "_cursor_line", None)
        while True:
            details = self.text.dlineinfo(index)
            if details is None:
                break
            line = int(index.split(".")[0])
            if line > last_line:
                break
            self.line_numbers.create_text(width - 5, details[1] + details[3] / 2,
                                          text=str(line), anchor="e", font=self._fixed_font,
                                          fill=COLORS["neon_yellow" if line == current
                                                     else "muted_text"],
                                          tags=("line", f"line{line}"))
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
            self._mark_cursor_line(line)
        state = self.words["modified"] if self.document.modified else self.words["saved"]
        self.status.config(text=f"{self.words['line']} {line}, {self.words['column']} {column}"
                                f"  |  {state}  |  {file_kind(self.document.path)}")
        resume_gc()  # Cheap Tk-thread fallback if a worker's poller was cancelled.
        dot = getattr(self, "_modified_dot", None)
        if dot is not None:
            dot.configure(text="●" if self.document.modified else "")
        if hasattr(self, "frame_status"):
            self._update_frame_info(line)

    def _mark_cursor_line(self, line):
        """Raw cursor-line band and yellow gutter number (§8.2); display only."""
        if not hasattr(self, "_cursor_line"):
            return
        # Edits move or widen the tagged range, so clear by its actual ranges.
        ranges = self.text.tag_ranges("cursor_line")
        if ranges:
            self.text.tag_remove("cursor_line", ranges[0], ranges[-1])
        self.text.tag_add("cursor_line", f"{line}.0", f"{line + 1}.0")
        previous, self._cursor_line = self._cursor_line, line
        if previous != line:
            if previous is not None:
                self.line_numbers.itemconfigure(f"line{previous}", fill=COLORS["muted_text"])
            self.line_numbers.itemconfigure(f"line{line}", fill=COLORS["neon_yellow"])

    def _position_unavailable_message(self):
        """Use the same cached-mapping readiness for display and navigation."""
        if not self._table_available():
            return self.words["frame_unavailable"]
        if (self._frame_edit_pending or self._position_job is not None or
                self._position_worker_active or
                self._position_key != (True, self.document.text)):
            return self.words["frame_updating"]
        if self._positions is None:
            return self.words["frame_error"]
        return ""

    def _update_frame_info(self, line):
        message = self._position_unavailable_message()
        if not message:
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
            # The METER renders this same structured result, never the string (§5.2).
            model = ("confirmed", position.start if position else None,
                     position.duration if position else None,
                     position.end if position else None, self._positions.total_frames)
        else:
            model = ({self.words["frame_unavailable"]: "tsv_only",
                      self.words["frame_updating"]: "pending"}.get(message, "unavailable"),
                     None, None, None, None)
        self.frame_status.configure(text=message)
        director = getattr(self, "_dopa", None)
        if director is not None:
            director.meter(model)
        if hasattr(self, "stick_preview"):
            self._update_stick_preview(line)

    def _update_stick_preview(self, line):
        unavailable = self._position_unavailable_message()
        if unavailable:
            pending = unavailable == self.words["frame_updating"]
            message = self.words["preview_updating" if pending else "preview_unavailable"]
            self.stick_preview.show(message=message, lamp="pending" if pending else "unavailable")
            return
        position = self._positions.for_line(line)
        if position is None or self._stick_frames is None:
            self.stick_preview.show(message=self.words["preview_unavailable"])
            return
        self.stick_preview.show(position.start, self._stick_frames.history(position.start))

    def focus_frame_entry(self):
        # Focusing this field does not commit or cancel a pending Table edit.
        self.frame_entry.focus_set()
        self.frame_entry.selection_range(0, "end")

    def _focus_editor(self):
        if self._view == "table":
            (self.table_grid._editor or self.table_grid.canvas).focus_set()
        else:
            self.text.focus_set()

    def _frame_jump_message(self, message):
        self._frame_jump_feedback.configure(text=message)
        if message:
            self._frame_jump_feedback.pack(side="left", padx=4)
        else:
            self._frame_jump_feedback.pack_forget()
        return False

    def go_to_frame(self):
        if not self._table_available():
            return self._frame_jump_message(self.words["frame_unavailable"])
        # Only Go commits. A changed cell invalidates the mapping through the usual
        # document-change path; never jump using the mapping from before that edit.
        if not self._commit_table_edit():
            return self._frame_jump_message(self.words["frame_commit_failed"])
        self._sync_text()
        message = self._position_unavailable_message()
        if message:
            return self._frame_jump_message(message)
        positions = self._positions
        if positions.total_frames == 0:
            return self._frame_jump_message(self.words["no_frames"])
        value = self.frame_entry.get().strip()
        try:
            if not value.isdecimal():
                raise ValueError
            frame = int(value)
        except ValueError:
            frame = -1
        if not 0 <= frame < positions.total_frames:
            return self._frame_jump_message(
                self.words["frame_range"].format(last=positions.total_frames - 1))
        line = positions.line_for_frame(frame)
        if line is None:
            return self._frame_jump_message(self.words["frame_no_source"])
        column = self.table_grid.selected[1] if self._view == "table" else 0
        if not self.jump_to_line(line, column=column):
            return self._frame_jump_message(self.words["frame_no_source"])
        self._frame_jump_message("")
        self.frame_entry.selection_range(0, "end")
        return True

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
        self._stick_frames = None
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
        results = self._position_queue
        self._position_worker_active = True
        self._position_waiting = False
        # CSV parsing allocates heavily; never let it finalize Tk garbage.
        gc_hold = hold_gc()

        def worker():
            with gc_hold:
                try:
                    result = analyze_positions(snapshot, base_dir=base_dir, include_sticks=True)
                except Exception as error:
                    traceback.print_exc()
                    result = PositionResult(error=str(error))
                # The worker keeps only plain data and its queue, not Tk widgets.
                results.put((revision, result))

        try:
            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            gc_hold.release()
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
        # Retry on the root: the result may arrive before the worker releases.
        resume_gc_soon(self._root())
        if revision == self._position_revision:
            self._positions = result.positions if result.success else None
            self._stick_frames = result.sticks if result.success else None
            director = getattr(self, "_dopa", None)
            if director is not None and self._positions is not None:
                director.positions_confirmed(self._positions.total_frames)
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
                state="normal" if self._table_available() else "disabled",
                **button_options(selected=getattr(self, "_view", "raw") == "table"))
        if hasattr(self, "_raw_button"):
            self._raw_button.configure(**button_options(selected=self._view == "raw"))

    def show_raw(self, *, remember=True):
        if getattr(self, "_view", "raw") == "table":
            if not self._commit_table_edit():
                return False
            self.table_area.pack_forget()
            if hasattr(self, "table_tools"):
                self.table_tools.pack_forget()
            self.raw_frame.pack(fill="both", expand=True)
            self._view = "raw"
            self._update_status()
            self.text.focus_set()
            self._schedule_highlight()
        if remember:
            self._remember_workspace(editor_view="raw")
        self._update_view_button()
        return True

    def show_table(self, *, remember=True):
        if not self._table_available():
            return False
        if remember:
            self._remember_workspace(editor_view="table")
        if getattr(self, "_view", "raw") == "table":
            return True
        self._sync_text()
        self.table_grid.set_text(self.document.text)
        self.raw_frame.pack_forget()
        self.table_area.pack(fill="both", expand=True)
        if hasattr(self, "table_tools"):
            # The Raw | Table toggle is its own segmented container in the deck.
            self.table_tools.pack(side="left", padx=(SPACING["gap"], 0),
                                  after=getattr(self, "_view_toggle", self._table_button))
        self._view = "table"
        self._update_view_button()
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
            self.raw_frame.pack(fill="both", expand=True)
            self._view = "raw"
        if hasattr(self, "table_grid"):
            self.table_grid.selected = (0, 0)
        if hasattr(self, "_cursor_line"):
            self._cursor_line = None
        director = getattr(self, "_dopa", None)
        if director is not None:
            director.document_replaced()
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
        self._restore_editor_view()

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
        director = getattr(self, "_dopa", None)
        if director is not None:
            director.history()
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
        director = getattr(self, "_dopa", None)
        if director is not None:
            director.history()
        return True

    def cut(self):
        if getattr(self, "_view", "raw") == "table":
            return self.table_grid.clipboard_action("Cut")
        if not self.show_raw(remember=False):
            return
        self.text.event_generate("<<Cut>>")

    def copy(self):
        if getattr(self, "_view", "raw") == "table":
            return self.table_grid.clipboard_action("Copy")
        if not self.show_raw(remember=False):
            return
        self.text.event_generate("<<Copy>>")

    def paste(self):
        if getattr(self, "_view", "raw") == "table":
            return self.table_grid.clipboard_action("Paste")
        if not self.show_raw(remember=False):
            return
        self.text.event_generate("<<Paste>>")

    def select_all(self):
        if not self.show_raw(remember=False):
            return
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "end-1c")
        self.text.see("insert")
        self._update_status()

    def show_find(self, replace=False):
        if not self.show_raw(remember=False):
            return
        if self._find_dialog is None or not self._find_dialog.winfo_exists():
            dialog = tk.Toplevel(self, background=COLORS["panel_background"])
            dialog.title(self.words["search"])
            dialog.transient(self)
            self._find_dialog = dialog
            fonts = self._theme_fonts
            pad = {"padx": SPACING["gap"], "pady": SPACING["gap"]}
            for row, key, variable in ((0, "find_text", self.find_query),
                                       (1, "replace_text", self.replace_value)):
                tk.Label(dialog, text=self.words[key], **label_options(fonts=fonts)).grid(
                    row=row, column=0, sticky="e", **pad)
                entry = tk.Entry(dialog, textvariable=variable, width=32,
                                 font=fonts["standard"], **entry_options())
                entry.grid(row=row, column=1, columnspan=4, sticky="ew", **pad)
                if row == 0:
                    self._find_entry = entry
                else:
                    self._replace_entry = entry
            for column, key, command in (
                (0, "next", self.find_next), (1, "previous", self.find_previous),
                (2, "replace_current", self.replace_current), (3, "replace_all", self.replace_all),
            ):
                tk.Button(dialog, text=self.words[key], command=command,
                          **button_options("primary" if column == 0 else "toolbar")).grid(
                    row=2, column=column, **pad)
            self._find_feedback = tk.Label(dialog, anchor="w", **label_options(fonts=fonts))
            self._find_feedback.configure(foreground=COLORS["warning"])
            self._find_feedback.grid(row=3, column=0, columnspan=5, sticky="ew", **pad)
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
        if not self.show_raw(remember=False):
            return False
        query = self.find_query.get()
        if not query:
            self.show_find()
            return False
        selected = self._selection_offsets()
        start = selected[1] if selected else self._cursor_offset()
        return self._select_match(next_match(self.text.get("1.0", "end-1c"), query, start))

    def find_previous(self):
        if not self.show_raw(remember=False):
            return False
        query = self.find_query.get()
        if not query:
            self.show_find()
            return False
        selected = self._selection_offsets()
        start = selected[0] if selected else self._cursor_offset()
        return self._select_match(previous_match(self.text.get("1.0", "end-1c"), query, start))

    def replace_current(self):
        if not self.show_raw(remember=False):
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
        if not self.show_raw(remember=False):
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
        director = getattr(self, "_dopa", None)
        button = getattr(self, "_send_button" if send_ftp else "_convert_button", None)
        if director is not None and button is not None:
            director.deck_pressed(button)
        self._sync_text()
        # Table may contain a pending Entry value not yet in document.text.
        if (self.document.path is None or self.document.modified or
                getattr(self, "_view", "raw") == "table" or
                self.document.external_status() != "unchanged") and not self.save():
            return False
        self._record_recent(self.document.path)
        started = bool(self.on_convert(self.document.path, send_ftp=send_ftp))
        if started and director is not None:
            self._conversion_send = send_ftp
            director.conversion_started(send_ftp)
        return started

    def conversion_finished(self, succeeded, outputs=None, stdout="", output_format=None,
                            error=None, stderr="", started=True):
        """The parent Converter's own result for this Editor's F5/F8 (§10, §9.6).

        Returns True when the result is presented here without a modal dialog:
        the HUD/COVER, the factual result line, and Problems for anything that
        needs checking. The Converter log keeps every line as before.
        """
        director = getattr(self, "_dopa", None)
        if director is None or self._closed:
            return False
        from .dopa.outcome import FAILED, SEND_UNVERIFIED, classify_conversion
        send = (outputs.ftp_requested if outputs is not None
                else bool(getattr(self, "_conversion_send", False)))
        outcome = classify_conversion(succeeded, send, stdout)
        director.conversion_result(outcome,
                                   outputs.primary.name if outputs is not None else None,
                                   output_format, started=started)
        if outcome in (FAILED, SEND_UNVERIFIED):
            # Exact converter / Converter text; nothing rewritten (T4).
            lines = [error] if error else []
            if not started:
                lines.append(self.master.words["preflight_failed"]
                             if hasattr(self.master, "words") else "")
            if stderr:
                lines.append(stderr.rstrip())
            from .validation import ValidationResult
            self._show_validation_result(ValidationResult(
                False, stdout=stdout or "", stderr="\n".join(line for line in lines if line)))
        return True

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
            current = self._inspection_is_current(identity)
            if current:
                self._show_validation_result(result)
            else:
                self._show_stale_result(self.words["stale_validation"])
            director = getattr(self, "_dopa", None)
            if director is not None:
                director.validation_result(result.success, current)

        try:
            started = self.on_validate(snapshot, receive)
        except Exception:
            self._validation_pending = False
            self._problems_panel.pack_forget()
            raise
        if not started:
            self._validation_pending = False
            self._problems_panel.pack_forget()
        elif self._validation_pending and getattr(self, "_dopa", None) is not None:
            self._dopa.check_started()
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
            current = self._inspection_is_current(identity)
            director = getattr(self, "_dopa", None)
            if director is not None:
                director.analysis_result(result.success, current,
                                         result.frames.total_frames if result.success else None)
            if not current:
                self._show_stale_result(self.words["stale_analysis"])
            elif result.success:
                self._problems_panel.pack_forget()
                self._problem_rows = {}
                self._problem_snapshot = None
                from .frame_inspector import FrameInspector
                if self._frame_inspector is None or not self._frame_inspector.winfo_exists():
                    self._frame_inspector = FrameInspector(
                        self, self.words, result.frames, source_name,
                        on_close=self._frame_inspector_closed)
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
        elif self._analysis_pending and getattr(self, "_dopa", None) is not None:
            self._dopa.check_started()
        return bool(started)

    def _frame_inspector_closed(self, inspector):
        if self._frame_inspector is inspector:
            self._frame_inspector = None
            self._inspector_snapshot = None

    def _inspection_snapshot(self):
        suffix = self.document.path.suffix.lower() if self.document.path else ".tsv"
        snapshot = ScriptSnapshot(self.document.text, suffix)
        identity = (getattr(self, "_document_revision", 0), self.document.path)
        return snapshot, identity

    def _inspection_is_current(self, identity):
        # An in-progress Entry has not reached the document revision yet.
        return (identity == (getattr(self, "_document_revision", 0), self.document.path)
                and not getattr(self, "_frame_edit_pending", False))

    def _show_problem_title(self, title, badge=None):
        self._problems_title.config(text=title)
        self._set_problem_badge(badge)
        rim = getattr(self, "_rim", None)
        if rim is not None:  # Above the status row, also reserved before the work area.
            self._problems_panel.pack(side="bottom", fill="x", before=rim)
        else:
            self._problems_panel.pack(fill="x", before=getattr(self, "_status_row", self.status))

    def _show_stale_result(self, title):
        self._problem_rows = {}
        self._problem_snapshot = None
        self._problems_text.pack_forget()
        self._show_problem_title(title)

    def _show_validation_result(self, result):
        self._problem_snapshot = self.document.text
        self._show_problem_title(self.words["no_errors"] if result.success else
                                 self.words["problems"] + " — " + self.words["jump_hint"],
                                 badge="clear" if result.success else "oshii")
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

    def jump_to_line(self, line, column=0):
        if not 1 <= line <= self.document.text.count("\n") + 1:
            return False
        if self._view == "table":
            if not self._commit_table_edit():
                return False
            self.table_grid.jump_to_row(line - 1, column=column)
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
            self.show_raw(remember=False)
        self._update_view_button()
        self._record_recent(saved_path)
        if self.on_saved:
            self.on_saved(saved_path)
        director = getattr(self, "_dopa", None)
        if director is not None:
            director.saved()
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
