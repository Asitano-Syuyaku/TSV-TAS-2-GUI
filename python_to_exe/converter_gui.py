"""Shared Tk interface for the Japanese and English launchers."""

import os
import shlex
import subprocess
import threading
import tkinter as tk
import traceback
from queue import Empty, SimpleQueue
from tkinter import filedialog, messagebox

if __package__:
    from .converter_logic import build_commands, load_ftp_config, save_ftp_config, scripts_dir
else:
    from converter_logic import build_commands, load_ftp_config, save_ftp_config, scripts_dir


TEXT = {
    "en": {
        "title": "TAS Scripts Converter Tool", "input": "Input Script File (.txt or .tsv):",
        "output": "Output Directory:", "name": "Output File Name (without extension):",
        "browse": "Browse...", "edit": "Edit...", "format": "Output format:",
        "binary": "LunaKit binary", "stas": "STAS", "nxtas": "nx-TAS",
        "skip": "Skip empty frames (nx-TAS only)", "debug": "Debug output (CSV)",
        "ftp": "Send via FTP (SMO/tas/scripts)", "ip": "FTP IP:",
        "port": "Port:", "user": "Username:", "password": "Password:",
        "start": "Start Conversion", "running": "Running: ",
        "success": "Conversion completed successfully.", "success_title": "Success",
        "error_title": "Error",
        "editor_local": "Editor: local conversion",
        "editor_send": "Editor: convert + FTP",
        "preflight_failed": "Conversion did not start; no new output was generated.",
    },
    "ja": {
        "title": "TAS scripts 変換ツール", "input": "入力スクリプトファイル (.txt または .tsv):",
        "output": "出力ディレクトリ:", "name": "出力ファイル名 (拡張子なし):",
        "browse": "参照...", "edit": "編集...", "format": "出力形式:",
        "binary": "LunaKit バイナリ", "stas": "STAS", "nxtas": "nx-TAS",
        "skip": "空フレームを省略 (nx-TAS のみ)", "debug": "Debug 出力 (CSV)",
        "ftp": "FTPで送信 (SMO/tas/scripts)", "ip": "FTP IP:",
        "port": "ポート:", "user": "ユーザー:", "password": "パスワード:",
        "start": "変換実行", "running": "実行: ",
        "success": "変換が正常に完了しました。", "success_title": "成功",
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
    def __init__(self, language="en"):
        super().__init__()
        self.language = language
        self.words = TEXT[language]
        self.title(self.words["title"])
        self.resizable(False, False)
        self.base_dir = scripts_dir()
        self._events = SimpleQueue()
        self._conversion_running = False
        self._validation_running = False
        self._analysis_running = False

        tk.Label(self, text=self.words["input"]).grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.input_entry = tk.Entry(self, width=50)
        self.input_entry.grid(row=0, column=1, padx=5, pady=5)
        input_buttons = tk.Frame(self)
        input_buttons.grid(row=0, column=2, padx=5, pady=5)
        tk.Button(input_buttons, text=self.words["browse"], command=self.browse_input).pack(side="left")
        tk.Button(input_buttons, text=self.words["edit"], command=self.open_editor).pack(side="left")

        tk.Label(self, text=self.words["output"]).grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.output_entry = tk.Entry(self, width=50)
        self.output_entry.grid(row=1, column=1, padx=5, pady=5)
        tk.Button(self, text=self.words["browse"], command=self.browse_output).grid(row=1, column=2, padx=5, pady=5)

        tk.Label(self, text=self.words["name"]).grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.outname_entry = tk.Entry(self, width=50)
        self.outname_entry.grid(row=2, column=1, columnspan=2, padx=5, pady=5)

        tk.Label(self, text=self.words["format"]).grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.format_var = tk.StringVar(value="binary")
        format_frame = tk.Frame(self)
        format_frame.grid(row=3, column=1, columnspan=2, sticky="w")
        for key in ("binary", "stas", "nxtas"):
            tk.Radiobutton(format_frame, text=self.words[key], value=key,
                           variable=self.format_var, command=self.toggle_skip).pack(side="left")

        self.skip_var = tk.BooleanVar()
        self.skip_check = tk.Checkbutton(self, text=self.words["skip"], variable=self.skip_var)
        self.skip_check.grid(row=4, column=0, columnspan=3, padx=5, sticky="w")
        self.toggle_skip()

        self.debug_var = tk.BooleanVar()
        tk.Checkbutton(self, text=self.words["debug"], variable=self.debug_var).grid(
            row=5, column=0, columnspan=3, padx=5, sticky="w")

        self.ftp_var = tk.BooleanVar()
        tk.Checkbutton(self, text=self.words["ftp"], variable=self.ftp_var,
                       command=self.toggle_ftp).grid(row=6, column=0, columnspan=3, padx=5, sticky="w")

        self.ftp_frame = tk.Frame(self)
        self.ip_entry = self._ftp_field("ip", 0, 0)
        self.port_entry = self._ftp_field("port", 0, 2)
        self.user_entry = self._ftp_field("user", 1, 0)
        self.pass_entry = self._ftp_field("password", 1, 2, show="*")
        self.ftp_frame.grid(row=7, column=0, columnspan=3)
        self.ftp_frame.grid_remove()
        config = load_ftp_config(self.base_dir)
        for entry, key in ((self.ip_entry, "ip"), (self.port_entry, "port"),
                           (self.user_entry, "user"), (self.pass_entry, "passwd")):
            entry.insert(0, str(config.get(key, "")))

        self.convert_btn = tk.Button(self, text=self.words["start"], command=self.start_conversion)
        self.convert_btn.grid(row=8, column=1, padx=5, pady=10)
        self.log_text = tk.Text(self, height=10, width=80, state="disabled")
        self.log_text.grid(row=9, column=0, columnspan=3, padx=5, pady=5)

    def _ftp_field(self, key, row, column, **kwargs):
        tk.Label(self.ftp_frame, text=self.words[key]).grid(row=row, column=column, padx=5, pady=2, sticky="e")
        entry = tk.Entry(self.ftp_frame, **kwargs)
        entry.grid(row=row, column=column + 1, padx=5, pady=2)
        return entry

    def browse_input(self):
        path = filedialog.askopenfilename(filetypes=[("Script files", "*.txt *.tsv")])
        if path:
            self._set_input_path(path)

    def _set_input_path(self, path, preserve_output_name=False):
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, str(path))
        if not preserve_output_name or not self.outname_entry.get().strip():
            self.outname_entry.delete(0, tk.END)
            self.outname_entry.insert(0, os.path.splitext(os.path.basename(path))[0])
        if not self.output_entry.get().strip():
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, os.path.dirname(os.path.abspath(path)))

    def _editor_saved(self, path):
        self._set_input_path(path, preserve_output_name=True)

    def _convert_editor_file(self, path, send_ftp=False):
        if self._busy():
            return False
        # Re-select the requesting editor's file; another editor may have saved since.
        self._editor_saved(path)
        return self.start_conversion(ftp_override=send_ftp)

    def open_editor(self):
        # Import on demand so conversion-only startup does not load editor widgets.
        if __package__:
            from .editor.window import EditorWindow
        else:
            from editor.window import EditorWindow
        EditorWindow(self, language=self.language,
                     initial_path=self.input_entry.get().strip() or None,
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
        path = filedialog.askdirectory()
        if path:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, path)

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
                messagebox.showinfo(self.words["success_title"], message)
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

    def convert(self, values, ftp_values):
        started = False
        try:
            commands = build_commands(*values, base_dir=self.base_dir)
            if values[6]:
                save_ftp_config(self.base_dir, *ftp_values)
            for command in commands:
                display = subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
                self._events.put(("log", self.words["running"] + display))
                started = True
                result = subprocess.run(command, cwd=self.base_dir, capture_output=True,
                                        text=True, errors="replace",
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if result.stdout:
                    self._events.put(("log", result.stdout.rstrip()))
                if result.stderr:
                    self._events.put(("log", result.stderr.rstrip()))
                if result.returncode:
                    script = next((os.path.basename(part) for part in command if part.endswith(".py")), command[0])
                    if self.language == "ja":
                        raise RuntimeError(f"{script} は終了コード {result.returncode} で失敗しました。")
                    raise RuntimeError(f"{script} exited with status {result.returncode}")
            self._events.put(("log", self.words["success"]))
            self._events.put(("success", self.words["success"]))
        except Exception as error:
            if not started:
                self._events.put(("log", self.words["preflight_failed"]))
            detail = ERROR_JA.get(str(error), str(error)) if self.language == "ja" else str(error)
            self._events.put(("error", detail))
        finally:
            self._events.put(("done", None))
