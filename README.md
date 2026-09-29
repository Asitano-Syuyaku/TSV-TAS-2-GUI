# TSV-TAS-2-GUI

This repository is a GUI wrapper and fork of [xiivler/TSV-TAS-2](https://github.com/xiivler/TSV-TAS-2). The converter scripts are based on upstream **`stas-dev`**, commit `245d5600c8ccc5dd97857b135341e6ba2cbe86e6` (not upstream `main`). The GUI runs the companion Python scripts as subprocesses; it does not reimplement script parsing, motion, gyro, or STAS output.

`tsv-tas.py` compiles TSV-TAS scripts to LunaKit binary (default), STAS for newer LunaKit, or nx-TAS for smo-practice. `nx-tas-to-tsv-tas.py` converts nx-TAS text to TSV-TAS. For the script format, see the [upstream documentation](https://docs.google.com/document/d/1vW-swF3k96YxaIJqXbtRXbQ54mKKgeWfPFlW2hYBa_Q/edit?usp=sharing).

## GUI

Run `python3 python_to_exe/main_en.py` for English or `python3 python_to_exe/main_jp.py` for Japanese. Python 3 with Tkinter is required. Both launchers use the same interface and conversion logic; only labels and messages differ.

Choose an input, output directory and base name, then select LunaKit binary, STAS or nx-TAS. The GUI gives STAS output a `.stas` extension and nx-TAS output a `.txt` extension; LunaKit binary keeps the entered base name without an extension. `.tsv` input goes directly to the compiler. As in the previous GUI, `.txt` input is treated as nx-TAS and first converted to an intermediate `.tsv` file in the output directory. For a tab-separated TSV-TAS script saved as `.txt`, use the CLI directly or rename it `.tsv`.

**Skip empty frames** enables upstream `-e` only for nx-TAS output. **Debug output** enables `-d` and writes `<output file>-debug.csv` beside the output. **Send via FTP** enables `-f` for the selected output format and uses the settings entered in the GUI. The GUI saves `ip` (string), `port` (integer), `user` (string), and `passwd` (string) in `ftp_config.json` beside the converter scripts. The upstream compiler reads that file from its working directory. Keep credentials out of commits and shared copies of the repository.

The GUI writes local output first. FTP then uploads the generated file to `SMO/tas/scripts/` on the Switch. A Switch and working FTP server are required to verify transfer.

## CLI

Run from the repository root:

```text
python3 tsv-tas.py [options] input.tsv output
python3 nx-tas-to-tsv-tas.py input.txt output.tsv
```

The compiler also accepts tab-separated `.txt` input. Upstream recognizes a `.csv` suffix, but its current row parser still splits on tabs, so CSV rows are not reliable; the GUI does not offer CSV input. Options can be combined after one hyphen, for example `-ne` or `-fsd`:

| Option | Upstream behavior |
| --- | --- |
| `-f` | Upload the output file via FTP using `ftp_config.json` |
| `-n` | Generate nx-TAS text |
| `-s` | Generate STAS for newer LunaKit |
| `-e` | Skip empty frames in nx-TAS output |
| `-l` | Recompile in a loop after pressing Enter (CLI only) |
| `-d` | Generate `<output file>-debug.csv` |

With no format option, output is LunaKit binary. For FTP, configure `ftp_config.json` before running the CLI. The output argument is a local path; the GUI supplies the extension for STAS and nx-TAS. The upstream parser also recognizes `-p` for an output path based on the input, but the GUI supplies an explicit output path.

## Build Windows executables

Install Python 3, Tkinter and PyInstaller, then run these commands from the repository root:

```text
python -m pip install pyinstaller
python -m PyInstaller --noconsole --onefile python_to_exe/main_en.py
python -m PyInstaller --noconsole --onefile python_to_exe/main_jp.py
```

Place each resulting `dist/main_en.exe` or `dist/main_jp.exe` in the same folder as `tsv-tas.py`, `nx-tas-to-tsv-tas.py`, and `ftp_config.json`. The GUI executable bundles the interface only. Its companion scripts still require an installed Python 3; on Windows it uses the `py -3` launcher when available, then a Python executable on `PATH`. Source runs use the current Python interpreter. Input and output paths may contain spaces.

## Changes from upstream

The GUI adds Japanese and English launchers, file selection, output format and option controls, FTP settings, conversion logs, and PyInstaller entry points. `tsv-tas.py` otherwise follows upstream `stas-dev`; its one local FTP adjustment uploads the output file's basename so a local absolute output path does not become part of the remote path. `nx-tas-to-tsv-tas.py` matches the upstream version, including removal of an unused NumPy import.
