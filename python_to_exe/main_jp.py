import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import os
import json
import threading
import sys

class TASConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TAS scripts 変換ツール")
        self.resizable(False, False)

        # 入力スクリプトファイル
        tk.Label(self, text="入力スクリプトファイル (.txt または .tsv):").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.input_entry = tk.Entry(self, width=50)
        self.input_entry.grid(row=0, column=1, padx=5, pady=5)
        tk.Button(self, text="参照...", command=self.browse_input).grid(row=0, column=2, padx=5, pady=5)

        # 出力ディレクトリ
        tk.Label(self, text="出力ディレクトリ:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.output_entry = tk.Entry(self, width=50)
        self.output_entry.grid(row=1, column=1, padx=5, pady=5)
        tk.Button(self, text="参照...", command=self.browse_output).grid(row=1, column=2, padx=5, pady=5)

        # 出力ファイル名（拡張子なし）
        tk.Label(self, text="出力ファイル名:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.outname_entry = tk.Entry(self, width=50)
        self.outname_entry.grid(row=2, column=1, columnspan=2, padx=5, pady=5)

        # FTPオプション
        self.ftp_var = tk.BooleanVar()
        tk.Checkbutton(self, text="FTPで送信 (sdmc:/smo/tas/scripts)", variable=self.ftp_var, command=self.toggle_ftp).grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="w")

        # FTP設定フレーム
        self.ftp_frame = tk.Frame(self)
        tk.Label(self.ftp_frame, text="FTP IP:").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.ip_entry = tk.Entry(self.ftp_frame)
        self.ip_entry.grid(row=0, column=1, padx=5, pady=2)
        tk.Label(self.ftp_frame, text="ポート:").grid(row=0, column=2, padx=5, pady=2, sticky="e")
        self.port_entry = tk.Entry(self.ftp_frame)
        self.port_entry.grid(row=0, column=3, padx=5, pady=2)
        tk.Label(self.ftp_frame, text="ユーザー:").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.user_entry = tk.Entry(self.ftp_frame)
        self.user_entry.grid(row=1, column=1, padx=5, pady=2)
        tk.Label(self.ftp_frame, text="パスワード:").grid(row=1, column=2, padx=5, pady=2, sticky="e")
        self.pass_entry = tk.Entry(self.ftp_frame, show="*")
        self.pass_entry.grid(row=1, column=3, padx=5, pady=2)
        self.ftp_frame.grid(row=4, column=0, columnspan=3)
        self.ftp_frame.grid_remove()

        # 初期FTP設定の読み込み
        base_dir = self.get_base_dir()
        cfg_path = os.path.join(base_dir, 'ftp_config.json')
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self.ip_entry.insert(0, cfg.get('ip', ''))
                self.port_entry.insert(0, cfg.get('port', ''))
                self.user_entry.insert(0, cfg.get('user', ''))
                self.pass_entry.insert(0, cfg.get('passwd', ''))
            except Exception:
                pass

        # 変換ボタン
        self.convert_btn = tk.Button(self, text="変換実行", command=self.start_conversion)
        self.convert_btn.grid(row=5, column=1, padx=5, pady=10)

        # ログ表示
        self.log_text = tk.Text(self, height=10, width=80, state='disabled')
        self.log_text.grid(row=6, column=0, columnspan=3, padx=5, pady=5)

    def get_base_dir(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def browse_input(self):
        file = filedialog.askopenfilename(filetypes=[("スクリプトファイル", "*.txt;*.tsv")])
        if file:
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, file)
            # .txt/.tsv に応じて出力名を自動設定
            base = os.path.splitext(os.path.basename(file))[0]
            self.outname_entry.delete(0, tk.END)
            self.outname_entry.insert(0, base)

    def browse_output(self):
        directory = filedialog.askdirectory()
        if directory:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, directory)

    def toggle_ftp(self):
        if self.ftp_var.get():
            self.ftp_frame.grid()
        else:
            self.ftp_frame.grid_remove()

    def log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def start_conversion(self):
        self.convert_btn.config(state='disabled')
        threading.Thread(target=self.convert).start()

    def convert(self):
        try:
            input_path = self.input_entry.get().strip()
            output_dir = self.output_entry.get().strip()
            base_name = self.outname_entry.get().strip()
            if not input_path or not output_dir or not base_name:
                raise ValueError("入力ファイル、出力先ディレクトリ、ファイル名を指定してください。")

            cwd = os.getcwd()
            base_dir = self.get_base_dir()
            self.log(f"カレントディレクトリ: {cwd}")
            self.log(f"スクリプト配置ディレクトリ: {base_dir}")

            # 入力ファイルの拡張子で処理分岐
            ext = os.path.splitext(input_path)[1].lower()
            if ext == '.tsv':
                # TSV 選択時はスキップ
                tsv_path = input_path
                self.log("TSVファイルが選択されたため、TXT→TSV 変換をスキップします。")
            else:
                # TXT→TSV 変換
                tsv_path = os.path.join(output_dir, f"{base_name}.tsv")
                nx_script = os.path.join(base_dir, "nx-tas-to-tsv-tas.py")
                cmd1 = ["python", nx_script, input_path, tsv_path]
                self.log("実行: " + " ".join(cmd1))
                res1 = subprocess.run(cmd1, capture_output=True, text=True)
                if res1.returncode != 0:
                    self.log("【エラー】nx-tas-to-tsv-tas.py に失敗")
                    self.log(res1.stderr)
                    raise RuntimeError("nx-tas-to-tsv-tas.py の実行に失敗しました。")
                self.log(res1.stdout)

            # バイナリ生成 (TSV→TAS)
            tsv_script = os.path.join(base_dir, "tsv-tas.py")
            if self.ftp_var.get():
                cfg = {"ip": self.ip_entry.get(), "port": self.port_entry.get(),
                       "user": self.user_entry.get(), "passwd": self.pass_entry.get()}
                tempf = os.path.join(base_dir, 'ftp_config.json')
                with open(tempf, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False)
                cmd2 = ["python", tsv_script, "-f", tsv_path, os.path.join(output_dir, base_name)]
            else:
                cmd2 = ["python", tsv_script, tsv_path, os.path.join(output_dir, base_name)]

            self.log("実行: " + " ".join(cmd2))
            res2 = subprocess.run(cmd2, capture_output=True, text=True)
            if res2.returncode != 0:
                self.log("【エラー】tsv-tas.py に失敗")
                self.log(res2.stderr)
                raise RuntimeError("tsv-tas.py の実行に失敗しました。")
            self.log(res2.stdout)

            self.log("変換が正常に完了しました。")
            messagebox.showinfo("成功", "変換が正常に完了しました。")
        except Exception as e:
            messagebox.showerror("エラー", str(e))
        finally:
            self.convert_btn.config(state='normal')

if __name__ == '__main__':
    app = TASConverterApp()
    app.mainloop()