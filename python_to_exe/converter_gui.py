"""Shared Tk interface for the Japanese and English launchers."""

import os
import shlex
import subprocess
import threading
import tkinter as tk
import traceback
from datetime import datetime
from queue import Empty, SimpleQueue
from tkinter import filedialog, messagebox

if __package__:
    from .app_settings import AppSettings
    from .display import configure_root
    from .editor.theme import (COLORS, FONTS, SPACING, button_options, choice_options,
                               entry_options, label_options)
    from .converter_logic import (FORMATS, build_commands, conversion_outputs, load_ftp_config,
                                  open_output_folder, save_ftp_config, scripts_dir,
                                  utf8_subprocess_kwargs)
else:
    from app_settings import AppSettings
    from display import configure_root
    from editor.theme import (COLORS, FONTS, SPACING, button_options, choice_options,
                              entry_options, label_options)
    from converter_logic import (FORMATS, build_commands, conversion_outputs, load_ftp_config,
                                 open_output_folder, save_ftp_config, scripts_dir,
                                 utf8_subprocess_kwargs)


TEXT = {
    "en": {
        "title": "TAS Scripts Converter Tool", "input": "Input Script File (.txt or .tsv):",
        "output": "Output Directory:", "name": "Output File Name (without extension):",
        "browse": "Browse...", "open_editor": "Open Editor", "format": "Output format:",
        "open_output": "Open Output Folder",
        "files": "Files", "settings": "Output settings", "log": "Log",
        "recovery_title": "Unsaved recovery",
        "recovery_found": "Unsaved editing content was found.",
        "recovery_choices": "Yes: Restore\nNo: Discard\nCancel: Keep for a later startup",
        "recovery_changed": "The original file has changed since the saved recovery baseline.",
        "recovery_missing": "The original file no longer exists.",
        "recovery_unreadable": "The original file cannot be read to check for changes.",
        "recovery_warning": "Recovery will open in a separate Editor buffer. The original file is not overwritten.",
        "binary": "LunaKit binary", "stas": "STAS", "nxtas": "nx-TAS",
        "skip": "Skip empty frames (nx-TAS only)", "debug": "Debug output (CSV)",
        "ftp": "Send via FTP (SMO/tas/scripts)", "ip": "FTP IP:",
        "port": "Port:", "user": "Username:", "password": "Password:",
        "start": "Start Conversion", "running": "Running: ",
        "success": "Conversion completed successfully.", "success_title": "Success",
        "result_output": "Output", "result_debug": "Debug CSV",
        "result_intermediate": "Intermediate TSV", "result_ftp": "FTP transfer was attempted.",
        "output_missing": "Expected output file was not generated: {path}",
        "error_title": "Error",
        "editor_local": "Editor: local conversion",
        "editor_send": "Editor: convert + FTP",
        "preflight_failed": "Conversion did not start; no new output was generated.",
    },
    "ja": {
        "title": "TAS scripts 変換ツール", "input": "入力スクリプトファイル (.txt または .tsv):",
        "output": "出力ディレクトリ:", "name": "出力ファイル名 (拡張子なし):",
        "browse": "参照...", "open_editor": "エディターを開く", "format": "出力形式:",
        "open_output": "出力フォルダーを開く",
        "files": "ファイル", "settings": "出力設定", "log": "ログ",
        "recovery_title": "未保存内容の復旧",
        "recovery_found": "保存されていない編集内容が見つかりました。",
        "recovery_choices": "はい: 復元\nいいえ: 破棄\nキャンセル: 次回起動まで保留",
        "recovery_changed": "元ファイルはRecoveryの保存基準から変更されています。",
        "recovery_missing": "元ファイルが見つかりません。",
        "recovery_unreadable": "元ファイルを読み取れず、変更を確認できません。",
        "recovery_warning": "復旧内容を別のEditor bufferで開きます。元ファイルは上書きしません。",
        "binary": "LunaKit バイナリ", "stas": "STAS", "nxtas": "nx-TAS",
        "skip": "空フレームを省略 (nx-TAS のみ)", "debug": "Debug 出力 (CSV)",
        "ftp": "FTPで送信 (SMO/tas/scripts)", "ip": "FTP IP:",
        "port": "ポート:", "user": "ユーザー:", "password": "パスワード:",
        "start": "変換実行", "running": "実行: ",
        "success": "変換が正常に完了しました。", "success_title": "成功",
        "result_output": "出力", "result_debug": "Debug CSV",
        "result_intermediate": "中間TSV", "result_ftp": "FTP送信を実行しました。",
        "output_missing": "生成されるはずの出力ファイルが見つかりません: {path}",
        "error_title": "エラー",
        "editor_local": "Editor: ローカル変換",
        "editor_send": "Editor: 変換 + FTP送信",
        "preflight_failed": "変換は開始されていません。新しい出力は生成されていません。",
    },
}

ERROR_JA = {
    "Unknown output format": "出力形式が不明です。",
    "Input file, output directory and output name are required": "入力ファイル、出力先、出力名を指定してください。",
    "Output name must be a file name without a directory": "出力名にはディレクトリを含めないでください。",
    "Input file does not exist": "入力ファイルが見つかりません。",
    "Output directory does not exist": "出力ディレクトリが見つかりません。",
    "Output directory is required": "出力ディレクトリを指定してください。",
    "Input must be a .txt or .tsv file": "入力ファイルは .txt または .tsv にしてください。",
    "Skip empty frames is available only for nx-TAS": "空フレームの省略は nx-TAS のみ利用できます。",
    "Intermediate TSV would overwrite the input file": "中間 TSV が入力ファイルを上書きします。",
    "Output file would overwrite the input file": "出力ファイルが入力ファイルを上書きします。",
    "FTP port must be an integer": "FTP ポートには整数を指定してください。",
    "FTP port must be between 1 and 65535": "FTP ポートは 1～65535 にしてください。",
    "Python 3 is required to run the companion converter scripts.":
        "converter script の実行には Python 3 が必要です。",
}


class TASConverterApp(tk.Tk):
    def __init__(self, language="en", settings=None):
        super().__init__()
        configure_root(self)  # Windows: readable fonts and DPI scale (no-op elsewhere).
        self.language = language
        self.words = TEXT[language]
        self.settings = settings if settings is not None else AppSettings()
        self.title(self.words["title"])
        self.resizable(False, False)
        self.base_dir = scripts_dir()
        self._events = SimpleQueue()
        self._conversion_running = False
        self._last_successful_output = None
        self._validation_running = False
        self._analysis_running = False

        # Light theme shared with the Editor: two cards, one primary action, the log.
        self.config(background=COLORS["app_background"])
        self.grid_columnconfigure(0, weight=1)
        row = {"padx": SPACING["gap"], "pady": SPACING["row_y"]}
        text = label_options()
        entry = entry_options()

        files = self._card(0, self.words["files"])
        tk.Label(files, text=self.words["input"], **text).grid(row=1, column=0, sticky="w", **row)
        self.input_entry = tk.Entry(files, width=50, **entry)
        self.input_entry.grid(row=1, column=1, ipady=3, **row)
        input_buttons = tk.Frame(files, background=COLORS["panel_background"])
        input_buttons.grid(row=1, column=2, sticky="w", **row)
        tk.Button(input_buttons, text=self.words["browse"], command=self.browse_input,
                  **button_options()).pack(side="left")

        tk.Label(files, text=self.words["output"], **text).grid(row=2, column=0, sticky="w", **row)
        self.output_entry = tk.Entry(files, width=50, **entry)
        self.output_entry.grid(row=2, column=1, ipady=3, **row)
        output_buttons = tk.Frame(files, background=COLORS["panel_background"])
        output_buttons.grid(row=2, column=2, sticky="w", **row)
        tk.Button(output_buttons, text=self.words["browse"], command=self.browse_output,
                  **button_options()).pack(side="left")
        tk.Button(output_buttons, text=self.words["open_output"], command=self.open_output_folder,
                  **button_options()).pack(side="left", padx=(SPACING["gap"], 0))

        tk.Label(files, text=self.words["name"], **text).grid(row=3, column=0, sticky="w", **row)
        self.outname_entry = tk.Entry(files, width=50, **entry)
        self.outname_entry.grid(row=3, column=1, ipady=3, **row)

        options = self._card(1, self.words["settings"])
        tk.Label(options, text=self.words["format"], **text).grid(row=1, column=0, sticky="w", **row)
        self.format_var = tk.StringVar(value=self.settings.get("output_format"))
        format_frame = tk.Frame(options, background=COLORS["panel_background"])
        format_frame.grid(row=1, column=1, sticky="w", **row)
        for key in FORMATS:
            tk.Radiobutton(format_frame, text=self.words[key], value=key,
                           variable=self.format_var, command=self._format_changed,
                           **choice_options()).pack(side="left", padx=(0, SPACING["card_x"]))

        # Options line up under the formats they modify.
        self.skip_var = tk.BooleanVar()
        self.skip_check = tk.Checkbutton(options, text=self.words["skip"], variable=self.skip_var,
                                         **choice_options())
        self.skip_check.grid(row=2, column=1, sticky="w", padx=SPACING["gap"])
        self.toggle_skip()

        self.debug_var = tk.BooleanVar(value=self.settings.get("debug_enabled"))
        tk.Checkbutton(options, text=self.words["debug"], variable=self.debug_var,
                       command=self._save_preferences, **choice_options()).grid(
            row=3, column=1, sticky="w", padx=SPACING["gap"])

        self.ftp_var = tk.BooleanVar()
        tk.Checkbutton(options, text=self.words["ftp"], variable=self.ftp_var,
                       command=self.toggle_ftp, **choice_options()).grid(
            row=4, column=1, sticky="w", padx=SPACING["gap"])

        self.ftp_frame = tk.Frame(options, background=COLORS["panel_background"])
        self.ip_entry = self._ftp_field("ip", 0, 0)
        self.port_entry = self._ftp_field("port", 0, 2)
        self.user_entry = self._ftp_field("user", 1, 0)
        self.pass_entry = self._ftp_field("password", 1, 2, show="*")
        self.ftp_frame.grid(row=5, column=1, sticky="w", padx=(SPACING["card_x"], 0),
                            pady=(0, SPACING["row_y"]))
        self.ftp_frame.grid_remove()
        config = load_ftp_config(self.base_dir)
        for entry_widget, key in ((self.ip_entry, "ip"), (self.port_entry, "port"),
                                  (self.user_entry, "user"), (self.pass_entry, "passwd")):
            entry_widget.insert(0, str(config.get(key, "")))

        # What this window is for, side by side: write in the Editor, then convert.
        # Same size; only conversion is the filled primary, the Editor is outlined.
        actions = tk.Frame(self, background=COLORS["app_background"])
        actions.grid(row=2, column=0, sticky="ew", padx=SPACING["window"], pady=SPACING["gap"])
        bold = {"standard": FONTS["heading"]}
        self.editor_btn = tk.Button(actions, text=self.words["open_editor"], command=self.open_editor,
                                    **{**button_options("palette", fonts=bold), "padx": 18, "pady": 6,
                                       "highlightthickness": 1,
                                       "highlightbackground": COLORS["accent"]})
        self.editor_btn.pack(side="left", padx=(0, SPACING["section"]))
        self.convert_btn = tk.Button(actions, text=self.words["start"], command=self.start_conversion,
                                     **{**button_options("primary", fonts=bold), "padx": 24, "pady": 6})
        self.convert_btn.pack(side="left", fill="x", expand=True)
        log = self._card(3, self.words["log"], last=True)
        log.grid_columnconfigure(0, weight=1)
        self.log_text = tk.Text(log, height=10, width=80, state="disabled", font="TkFixedFont",
                                padx=SPACING["gap"], pady=SPACING["gap"], **entry)
        self.log_text.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(SPACING["gap"], 0))
        if __package__:
            from .editor.recovery import RecoveryStore
        else:
            from editor.recovery import RecoveryStore
        self.recovery_store = RecoveryStore.from_settings(self.settings, report=self.log)
        self.protocol("WM_DELETE_WINDOW", self._close_app)
        self._recovery_check_job = self.after_idle(self._check_recovery)

    def destroy(self):
        job = getattr(self, "_recovery_check_job", None)
        if job is not None:
            self.after_cancel(job)
            self._recovery_check_job = None
        super().destroy()

    def _check_recovery(self):
        self._recovery_check_job = None
        snapshots = self.recovery_store.load()
        for index, snapshot in enumerate(snapshots, start=1):
            date = datetime.fromtimestamp(snapshot.timestamp).isoformat(sep=" ", timespec="seconds")
            description = (f"{self.words['recovery_found']}\n\n"
                           f"{index} / {len(snapshots)}: {snapshot.display_name}\n{date}\n\n"
                           f"{self.words['recovery_choices']}")
            choice = messagebox.askyesnocancel(self.words["recovery_title"], description, parent=self)
            if choice is None:
                break
            if choice:
                status = snapshot.external_status()
                if status:
                    messagebox.showwarning(self.words["recovery_title"],
                                           self.words["recovery_" + status] + "\n\n" +
                                           self.words["recovery_warning"], parent=self)
                self._create_editor(recovery=snapshot)
            else:
                self.recovery_store.delete(snapshot.document_id)

    def _save_preferences(self, **chosen):
        self.settings.update(output_format=self.format_var.get(), debug_enabled=self.debug_var.get(),
                             **chosen)

    def _format_changed(self):
        self.toggle_skip()
        self._save_preferences(output_format_chosen=True)

    def _close_app(self):
        for child in tuple(self.winfo_children()):
            close = getattr(child, "close_editor", None)
            if close is not None and not close():
                return False
        self._save_preferences()
        directory = self.output_entry.get().strip()
        if directory and os.path.isdir(directory):
            self.settings.update(last_output_directory=os.path.abspath(directory))
        self.destroy()

    def _card(self, row, title, last=False):
        """A white section on the app background, headed by an accent title."""
        card = tk.Frame(self, background=COLORS["panel_background"], highlightthickness=1,
                        highlightbackground=COLORS["subtle_border"],
                        padx=SPACING["card_x"], pady=SPACING["card_y"])
        card.grid(row=row, column=0, sticky="ew", padx=SPACING["window"],
                  pady=(SPACING["window"] if row == 0 else SPACING["gap"],
                        SPACING["window"] if last else SPACING["gap"]))
        tk.Label(card, text=title, **{**label_options(role="heading"),
                                      "foreground": COLORS["accent"]}).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=SPACING["gap"],
            pady=(0, SPACING["row_y"]))
        return card

    def _ftp_field(self, key, row, column, **kwargs):
        tk.Label(self.ftp_frame, text=self.words[key], **label_options()).grid(
            row=row, column=column, padx=SPACING["gap"], pady=2, sticky="w")
        entry = tk.Entry(self.ftp_frame, **{**entry_options(), **kwargs})
        entry.grid(row=row, column=column + 1, padx=SPACING["gap"], pady=2, ipady=2)
        return entry

    def browse_input(self):
        path = filedialog.askopenfilename(filetypes=[("Script files", "*.txt *.tsv")],
                                          **self.settings.dialog_options("last_input_directory"))
        if path:
            self._set_input_path(path)
            self.settings.add_recent(path)

    @staticmethod
    def _same_file(first, second):
        if not first or not second:
            return False
        normalize = lambda path: os.path.normcase(os.path.abspath(str(path)))
        return normalize(first) == normalize(second)

    def _set_input_path(self, path, preserve_output_name=False):
        # An output name belongs to its input: a typed name survives saves and F5/F8
        # of the same file, but switching files (b.tsv after a.tsv) brings b's name.
        previous = self.input_entry.get().strip()
        switched = bool(previous) and not self._same_file(previous, path)
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, str(path))
        if not preserve_output_name or switched or not self.outname_entry.get().strip():
            self.outname_entry.delete(0, tk.END)
            self.outname_entry.insert(0, os.path.splitext(os.path.basename(path))[0])
        if not self.output_entry.get().strip():
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, os.path.dirname(os.path.abspath(path)))

    def _editor_saved(self, path):
        self._set_input_path(path, preserve_output_name=True)
        self.settings.add_recent(path)

    def _convert_editor_file(self, path, send_ftp=False):
        if self._busy():
            return False
        # Re-select the requesting editor's file; another editor may have saved since.
        self._editor_saved(path)
        return self.start_conversion(ftp_override=send_ftp)

    def open_editor(self):
        return self._create_editor(initial_path=self.input_entry.get().strip() or None)

    def _create_editor(self, initial_path=None, recovery=None):
        # Import on demand so conversion-only startup does not load editor widgets.
        if __package__:
            from .editor.window import EditorWindow
        else:
            from editor.window import EditorWindow
        return EditorWindow(self, language=self.language,
                     initial_path=initial_path, recovery=recovery,
                     on_saved=self._editor_saved, on_convert=self._convert_editor_file,
                     can_convert=lambda: not self._busy(),
                     on_validate=self._validate_editor_snapshot,
                     can_validate=lambda: not self._busy(),
                     on_analyze=self._analyze_editor_snapshot,
                     can_analyze=lambda: not self._busy())

    def _busy(self):
        return self._conversion_running or self._validation_running or self._analysis_running

    def _validate_editor_snapshot(self, snapshot, callback):
        if self._busy():
            return False
        if __package__:
            from .editor.validation import ValidationResult, validate_script
        else:
            from editor.validation import ValidationResult, validate_script
        output_format = self.format_var.get()
        skip_empty = self.skip_var.get() if output_format == "nxtas" else False
        self._validation_running = True
        self.convert_btn.config(state="disabled")

        def worker():
            try:
                result = validate_script(snapshot, output_format, skip_empty, self.base_dir)
            except Exception:
                # Unexpected worker failures remain visible in stderr and Problems.
                traceback.print_exc()
                result = ValidationResult(False, stderr=traceback.format_exc(),
                                          source_is_tsv=snapshot.suffix == ".tsv")
            self._events.put(("validation", (callback, result)))

        try:
            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            self._validation_running = False
            self.convert_btn.config(state="normal")
            raise
        self.after(50, self._drain_events)
        return True

    def _analyze_editor_snapshot(self, snapshot, callback):
        if self._busy():
            return False
        if __package__:
            from .editor.validation import AnalyzeResult, ValidationResult, analyze_script
        else:
            from editor.validation import AnalyzeResult, ValidationResult, analyze_script
        output_format = self.format_var.get()
        skip_empty = self.skip_var.get() if output_format == "nxtas" else False
        self._analysis_running = True
        self.convert_btn.config(state="disabled")

        def worker():
            try:
                result = analyze_script(snapshot, output_format, skip_empty, self.base_dir)
            except Exception:
                traceback.print_exc()
                report = ValidationResult(False, stderr=traceback.format_exc(),
                                          source_is_tsv=snapshot.suffix == ".tsv")
                result = AnalyzeResult(report)
            self._events.put(("analysis", (callback, result)))

        try:
            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            self._analysis_running = False
            self.convert_btn.config(state="normal")
            raise
        self.after(50, self._drain_events)
        return True

    def browse_output(self):
        path = filedialog.askdirectory(**self.settings.dialog_options("last_output_directory"))
        if path:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, path)
            self.settings.update(last_output_directory=os.path.abspath(path))

    def open_output_folder(self):
        try:
            open_output_folder(self.output_entry.get().strip())
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            detail = ERROR_JA.get(str(error), str(error)) if self.language == "ja" else str(error)
            messagebox.showerror(self.words["error_title"], detail)

    def toggle_skip(self):
        enabled = self.format_var.get() == "nxtas"
        if not enabled:
            self.skip_var.set(False)
        self.skip_check.config(state="normal" if enabled else "disabled")

    def toggle_ftp(self):
        if self.ftp_var.get():
            self.ftp_frame.grid()
        else:
            self.ftp_frame.grid_remove()

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def start_conversion(self, ftp_override=None):
        if self._busy():
            return False
        # Read Tk widgets on the main thread; the worker only handles files and subprocesses.
        output_format = self.format_var.get()
        ftp = self.ftp_var.get() if ftp_override is None else bool(ftp_override)
        values = (self.input_entry.get().strip(), self.output_entry.get().strip(),
                  self.outname_entry.get().strip(), output_format,
                  self.skip_var.get() if output_format == "nxtas" else False,
                  self.debug_var.get(), ftp)
        ftp_values = (self.ip_entry.get().strip(), self.port_entry.get().strip(),
                      self.user_entry.get(), self.pass_entry.get())
        self._conversion_running = True
        self.convert_btn.config(state="disabled")
        if ftp_override is not None:
            self._events.put(("log", self.words["editor_send" if ftp else "editor_local"]))
        try:
            threading.Thread(target=self.convert, args=(values, ftp_values), daemon=True).start()
        except Exception:
            self._conversion_running = False
            self.convert_btn.config(state="normal")
            raise
        self.after(50, self._drain_events)
        return True

    def _drain_events(self):
        logs = []
        while True:
            try:
                kind, message = self._events.get_nowait()
            except Empty:
                break
            if kind == "log":
                logs.append(message)
                continue
            if logs:
                self.log("\n".join(logs))
                logs.clear()
            if kind == "success":
                self._show_conversion_result(message)
            elif kind == "error":
                messagebox.showerror(self.words["error_title"], message)
            elif kind == "validation":
                callback, result = message
                self._validation_running = False
                self.convert_btn.config(state="normal")
                callback(result)
                return
            elif kind == "analysis":
                callback, result = message
                self._analysis_running = False
                self.convert_btn.config(state="normal")
                callback(result)
                return
            elif kind == "done":
                self._conversion_running = False
                self.convert_btn.config(state="normal")
                return
        if logs:
            self.log("\n".join(logs))
        self.after(50, self._drain_events)

    def _show_conversion_result(self, outputs):
        self._last_successful_output = outputs.primary
        lines = [self.words["success"], f"{self.words['result_output']}: {outputs.primary}"]
        for key, path in (("result_debug", outputs.debug_csv),
                          ("result_intermediate", outputs.intermediate_tsv)):
            if path is not None:
                lines.append(f"{self.words[key]}: {path}")
        message = f"{self.words['success']}\n\n{self.words['result_output']}:\n{outputs.primary}"
        if outputs.ftp_requested:
            lines.append(self.words["result_ftp"])
            message += "\n\n" + self.words["result_ftp"]
        self.log("\n".join(lines))
        messagebox.showinfo(self.words["success_title"], message)

    def convert(self, values, ftp_values):
        started = False
        try:
            commands = build_commands(*values, base_dir=self.base_dir)
            outputs = conversion_outputs(*values[:4], debug=values[5], ftp=values[6])
            if values[6]:
                save_ftp_config(self.base_dir, *ftp_values)
            for index, command in enumerate(commands):
                display = subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
                self._events.put(("log", self.words["running"] + display))
                started = True
                result = subprocess.run(command, cwd=self.base_dir, capture_output=True,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                        **utf8_subprocess_kwargs())
                if result.stdout:
                    self._events.put(("log", result.stdout.rstrip()))
                if result.stderr:
                    self._events.put(("log", result.stderr.rstrip()))
                if result.returncode:
                    script = next((os.path.basename(part) for part in command if part.endswith(".py")), command[0])
                    if self.language == "ja":
                        raise RuntimeError(f"{script} は終了コード {result.returncode} で失敗しました。")
                    raise RuntimeError(f"{script} exited with status {result.returncode}")
                expected = outputs.intermediate_tsv if index < len(commands) - 1 else outputs.primary
                if not expected.is_file():
                    raise RuntimeError(self.words["output_missing"].format(path=expected))
            if outputs.debug_csv is not None and not outputs.debug_csv.is_file():
                raise RuntimeError(self.words["output_missing"].format(path=outputs.debug_csv))
            self._events.put(("success", outputs))
        except Exception as error:
            if not started:
                self._events.put(("log", self.words["preflight_failed"]))
            detail = ERROR_JA.get(str(error), str(error)) if self.language == "ja" else str(error)
            self._events.put(("error", detail))
        finally:
            self._events.put(("done", None))
