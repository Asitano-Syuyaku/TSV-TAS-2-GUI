"""Shared Tk interface for the Japanese and English launchers."""

import os
import shlex
import subprocess
import threading
import tkinter as tk
import traceback
import weakref
from datetime import datetime
from queue import Empty, SimpleQueue
from tkinter import filedialog, messagebox

if __package__:
    from .app_settings import AppSettings
    from .background import hold_gc, resume_gc, resume_gc_soon
    from .display import configure_root
    from .editor.theme import (COLORS, button_options, choice_options, entry_options,
                               label_options)
    from .editor.dopa.outcome import FAILED, SEND_UNVERIFIED, classify_conversion
    from .editor.dopa.words import WORDS as DOPA_WORDS
    from .converter_logic import (FORMATS, build_commands, conversion_outputs, load_ftp_config,
                                  open_output_folder, save_ftp_config, scripts_dir,
                                  utf8_subprocess_kwargs)
else:
    from app_settings import AppSettings
    from background import hold_gc, resume_gc, resume_gc_soon
    from display import configure_root
    from editor.theme import COLORS, button_options, choice_options, entry_options, label_options
    from editor.dopa.outcome import FAILED, SEND_UNVERIFIED, classify_conversion
    from editor.dopa.words import WORDS as DOPA_WORDS
    from converter_logic import (FORMATS, build_commands, conversion_outputs, load_ftp_config,
                                 open_output_folder, save_ftp_config, scripts_dir,
                                 utf8_subprocess_kwargs)


TEXT = {
    "en": {
        "title": "TAS Scripts Converter Tool", "input": "Input Script File (.txt or .tsv):",
        "output": "Output Directory:", "name": "Output File Name (without extension):",
        "browse": "Browse...", "edit": "Edit...", "format": "Output format:",
        "open_output": "Open Output Folder",
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
        "browse": "参照...", "edit": "編集...", "format": "出力形式:",
        "open_output": "出力フォルダーを開く",
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
        # The Editor whose F5/F8 started the running conversion (display only).
        self._conversion_listener = None
        self._conversion_stdout = ""
        self._conversion_format = None

        # Dopagaki3 neon skin (§8.7): constructor options only; behavior unchanged.
        self.config(background=COLORS["app_background"])
        ground = {"background": COLORS["app_background"]}
        text = label_options("app_background")
        entry = {**entry_options(), "highlightthickness": 1}

        tk.Label(self, text=self.words["input"], **text).grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.input_entry = tk.Entry(self, width=50, **entry)
        self.input_entry.grid(row=0, column=1, padx=5, pady=5)
        input_buttons = tk.Frame(self, **ground)
        input_buttons.grid(row=0, column=2, padx=5, pady=5)
        tk.Button(input_buttons, text=self.words["browse"], command=self.browse_input,
                  **button_options()).pack(side="left")
        tk.Button(input_buttons, text=self.words["edit"], command=self.open_editor,
                  **button_options("primary")).pack(side="left", padx=(4, 0))

        tk.Label(self, text=self.words["output"], **text).grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.output_entry = tk.Entry(self, width=50, **entry)
        self.output_entry.grid(row=1, column=1, padx=5, pady=5)
        output_buttons = tk.Frame(self, **ground)
        output_buttons.grid(row=1, column=2, padx=5, pady=5)
        tk.Button(output_buttons, text=self.words["browse"], command=self.browse_output,
                  **button_options()).pack(side="left")
        tk.Button(output_buttons, text=self.words["open_output"], command=self.open_output_folder,
                  **button_options()).pack(side="left", padx=(4, 0))

        tk.Label(self, text=self.words["name"], **text).grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.outname_entry = tk.Entry(self, width=50, **entry)
        self.outname_entry.grid(row=2, column=1, columnspan=2, padx=5, pady=5)

        tk.Label(self, text=self.words["format"], **text).grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.format_var = tk.StringVar(value=self.settings.get("output_format"))
        format_frame = tk.Frame(self, **ground)
        format_frame.grid(row=3, column=1, columnspan=2, sticky="w")
        for key in FORMATS:
            tk.Radiobutton(format_frame, text=self.words[key], value=key,
                           variable=self.format_var, command=self._format_changed,
                           **choice_options()).pack(side="left", padx=(0, 8))

        self.skip_var = tk.BooleanVar()
        self.skip_check = tk.Checkbutton(self, text=self.words["skip"], variable=self.skip_var,
                                         **choice_options())
        self.skip_check.grid(row=4, column=0, columnspan=3, padx=5, sticky="w")
        self.toggle_skip()

        self.debug_var = tk.BooleanVar(value=self.settings.get("debug_enabled"))
        tk.Checkbutton(self, text=self.words["debug"], variable=self.debug_var,
                       command=self._save_preferences, **choice_options()).grid(
            row=5, column=0, columnspan=3, padx=5, sticky="w")

        self.ftp_var = tk.BooleanVar()
        tk.Checkbutton(self, text=self.words["ftp"], variable=self.ftp_var,
                       command=self.toggle_ftp, **choice_options()).grid(
            row=6, column=0, columnspan=3, padx=5, sticky="w")

        self.ftp_frame = tk.Frame(self, **ground)
        self.ip_entry = self._ftp_field("ip", 0, 0)
        self.port_entry = self._ftp_field("port", 0, 2)
        self.user_entry = self._ftp_field("user", 1, 0)
        self.pass_entry = self._ftp_field("password", 1, 2, show="*")
        self.ftp_frame.grid(row=7, column=0, columnspan=3)
        self.ftp_frame.grid_remove()
        config = load_ftp_config(self.base_dir)
        for entry_widget, key in ((self.ip_entry, "ip"), (self.port_entry, "port"),
                                  (self.user_entry, "user"), (self.pass_entry, "passwd")):
            entry_widget.insert(0, str(config.get(key, "")))

        self.convert_btn = tk.Button(self, text=self.words["start"], command=self.start_conversion,
                                     **button_options("convert", fonts={"standard": "TkHeadingFont"}))
        self.convert_btn.config(padx=18, pady=5)
        self.convert_btn.grid(row=8, column=1, padx=5, pady=10)
        # Factual result badge for the latest conversion (§8.7, §9.1 classes).
        self.result_badge = tk.Label(self, text="", **label_options("app_background", "heading"))
        self.result_badge.grid(row=8, column=2, padx=5, sticky="w")
        self.log_text = tk.Text(self, height=10, width=80, state="disabled", **entry_options())
        self.log_text.grid(row=9, column=0, columnspan=3, padx=5, pady=5)
        if __package__:
            from .editor.recovery import RecoveryStore
        else:
            from editor.recovery import RecoveryStore
        self.recovery_store = RecoveryStore.from_settings(self.settings, report=self.log)
        self.protocol("WM_DELETE_WINDOW", self._close_app)
        self._recovery_check_job = self.after_idle(self._check_recovery)

    def destroy(self):
        resume_gc()
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
                editor = self._editor_window()
                if editor is not None:  # Each restored document is one more tab.
                    editor.restore_tab(snapshot)
                else:
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

    def _ftp_field(self, key, row, column, **kwargs):
        tk.Label(self.ftp_frame, text=self.words[key], **label_options("app_background")).grid(
            row=row, column=column, padx=5, pady=2, sticky="e")
        entry = tk.Entry(self.ftp_frame, **entry_options(), **kwargs)
        entry.grid(row=row, column=column + 1, padx=5, pady=2)
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

    def _convert_editor_file(self, path, send_ftp=False, requester=None):
        if self._busy():
            return False
        # Re-select the requesting editor's file; another editor may have saved since.
        self._editor_saved(path)
        started = self.start_conversion(ftp_override=send_ftp)
        if started and requester is not None:
            self._conversion_listener = weakref.ref(requester)
            self._conversion_stdout = ""
            self._conversion_report = None
            self._conversion_format = self.format_var.get()
        return started

    def _editor_window(self):
        """The open Editor; files open there as tabs instead of in new windows."""
        try:
            children = self.winfo_children()
        except Exception:  # No usable Tk window (startup, tests): no Editor either.
            return None
        for child in children:
            if (getattr(child, "open_tab", None) is not None and not getattr(child, "_closed", False)
                    and child.winfo_exists()):
                return child
        return None

    def open_editor(self):
        path = self.input_entry.get().strip() or None
        editor = self._editor_window()
        if editor is not None:
            editor.open_tab(path)
            return editor
        return self._create_editor(initial_path=path)

    def _create_editor(self, initial_path=None, recovery=None):
        # Import on demand so conversion-only startup does not load editor widgets.
        if __package__:
            from .editor.window import EditorWindow
        else:
            from editor.window import EditorWindow
        requester = []

        def convert(path, send_ftp=False):
            # Remember which Editor asked, so only it shows the real result.
            return self._convert_editor_file(path, send_ftp=send_ftp,
                                             requester=requester[0] if requester else None)

        editor = EditorWindow(self, language=self.language,
                     initial_path=initial_path, recovery=recovery,
                     on_saved=self._editor_saved, on_convert=convert,
                     can_convert=lambda: not self._busy(),
                     on_validate=self._validate_editor_snapshot,
                     can_validate=lambda: not self._busy(),
                     on_analyze=self._analyze_editor_snapshot,
                     can_analyze=lambda: not self._busy())
        requester.append(editor)
        return editor

    def _notify_editor_result(self, succeeded, outputs=None, error=None):
        """Tell the requesting Editor first. True: it presented the result itself.

        Dopagaki3 Editors show F5/F8 results without a modal dialog (HUD, COVER,
        Problems, log). Without such an Editor the dialog appears as before.
        """
        # Instance state only: Tk.__getattr__ would forward misses to the interpreter.
        state = self.__dict__
        listener = state.get("_conversion_listener")
        self._conversion_listener = None
        editor = listener() if listener is not None else None
        if editor is None:
            return False
        stdout, stderr, started = state.get("_conversion_report") or ("", "", True)
        try:
            if editor.winfo_exists():
                return bool(editor.conversion_finished(
                    succeeded, outputs, state.get("_conversion_stdout", "") or stdout,
                    state.get("_conversion_format"), error=error, stderr=stderr,
                    started=started))
        except Exception:
            # A display failure must never hide the result: fall back to the dialog.
            traceback.print_exc()
        return False

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
        gc_hold = hold_gc()

        def worker():
            with gc_hold:
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
            gc_hold.release()
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
        gc_hold = hold_gc()

        def worker():
            with gc_hold:
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
            gc_hold.release()
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
        gc_hold = hold_gc()
        try:
            threading.Thread(target=self.convert, args=(values, ftp_values, gc_hold),
                             daemon=True).start()
        except Exception:
            gc_hold.release()
            self._conversion_running = False
            self.convert_btn.config(state="normal")
            raise
        self.after(50, self._drain_events)
        return True

    def _drain_events(self):
        resume_gc()
        logs = []
        while True:
            try:
                kind, message = self._events.get_nowait()
            except Empty:
                break
            if kind == "log":
                logs.append(message)
                continue
            if kind == "stdout":
                self._conversion_stdout = message
                continue
            if kind == "report":
                self._conversion_report = message
                continue
            if logs:
                self.log("\n".join(logs))
                logs.clear()
            if kind == "success":
                self._show_badge(True, message)
                presented = self._notify_editor_result(True, message)
                self._show_conversion_result(message, dialog=not presented)
            elif kind == "error":
                self._show_badge(False)
                if not self._notify_editor_result(False, error=message):
                    messagebox.showerror(self.words["error_title"], message)
            elif kind == "validation":
                callback, result = message
                self._validation_running = False
                self.convert_btn.config(state="normal")
                resume_gc_soon(self)  # The worker may still be releasing its hold.
                callback(result)
                return
            elif kind == "analysis":
                callback, result = message
                self._analysis_running = False
                self.convert_btn.config(state="normal")
                resume_gc_soon(self)
                callback(result)
                return
            elif kind == "done":
                self._conversion_running = False
                self._conversion_listener = None
                self._conversion_stdout = ""
                self._conversion_report = None
                self.convert_btn.config(state="normal")
                resume_gc_soon(self)
                return
        if logs:
            self.log("\n".join(logs))
        self.after(50, self._drain_events)

    def _show_badge(self, succeeded, outputs=None):
        """Same truth classes as the Editor: a send counts only with the upload line."""
        badge = self.__dict__.get("result_badge")
        if badge is None:
            return
        words = DOPA_WORDS[self.language]
        send = bool(outputs is not None and outputs.ftp_requested)
        outcome = classify_conversion(succeeded, send, self.__dict__.get("_conversion_stdout", ""))
        if outcome == FAILED:
            text, color = words["oshii"], COLORS["neon_orange"]
        elif outcome == SEND_UNVERIFIED:
            text, color = f"{words['built']} · {words['send_unverified']}", COLORS["neon_orange"]
        else:
            text, color = words["sent" if send else "converted"], COLORS["neon_green"]
        badge.config(text=text, foreground=color)

    def _show_conversion_result(self, outputs, dialog=True):
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
        if dialog:
            messagebox.showinfo(self.words["success_title"], message)

    def convert(self, values, ftp_values, gc_hold=None):
        with gc_hold if gc_hold is not None else hold_gc():
            self._convert(values, ftp_values)

    def _convert(self, values, ftp_values):
        started = False
        stdout, stderr = [], []
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
                    stdout.append(result.stdout)
                    self._events.put(("log", result.stdout.rstrip()))
                if result.stderr:
                    stderr.append(result.stderr)
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
            # Read-only copy for the Editor's send check (§9.1); log text is unchanged.
            self._events.put(("stdout", "".join(stdout)))
            self._events.put(("success", outputs))
        except Exception as error:
            if not started:
                self._events.put(("log", self.words["preflight_failed"]))
            # Read-only copy of the converter's own text for the Editor's Problems.
            self._events.put(("report", ("".join(stdout), "".join(stderr), started)))
            detail = ERROR_JA.get(str(error), str(error)) if self.language == "ja" else str(error)
            self._events.put(("error", detail))
        finally:
            self._events.put(("done", None))
