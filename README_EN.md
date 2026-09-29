# TSV-TAS-2-GUI

English | [日本語](README.md)

A GUI fork of [xiivler/TSV-TAS-2](https://github.com/xiivler/TSV-TAS-2/tree/stas-dev) for converting Super Mario Odyssey TAS scripts. The converters are based on upstream **`stas-dev` commit `245d5600c8ccc5dd97857b135341e6ba2cbe86e6`**. The GUI runs the companion Python scripts as subprocesses. For advanced syntax, see the [TSV-TAS-2 Documentation](https://docs.google.com/document/d/1vW-swF3k96YxaIJqXbtRXbQ54mKKgeWfPFlW2hYBa_Q/edit?usp=sharing).

## Output formats and requirements

| GUI choice | Output | Intended use |
| --- | --- | --- |
| LunaKit binary | No extension | Binary for the earlier LunaKit format; CLI default |
| STAS | `.stas` | STAS format for newer LunaKit; supports the script commands below |
| nx-TAS | `.txt` | Text format for smo-practice; can skip empty frames |

Python 3 and Tkinter are required. The GUI exe also requires a separate Python 3 installation to run the converter scripts. PyInstaller is needed only to build Windows executables. To use the generated file on a Switch, install the mod that supports the selected format. FTP transfer also requires an FTP server on the Switch and its connection settings.

## Make your first script

1. Create `sample.tsv` in a spreadsheet or text editor. **Separate columns with tabs**: the first column is the duration in frames, and later columns contain simultaneous inputs. This example uses real tab separators.

   ```text
   $angle = 90
   // First comment line
   5	ls($angle)
   1	a	rs(0)
   3
   4	b	ls(0)/ls(90)
   6	ls(0)->ls(50)
   ```

2. From the repository root, run `python3 python_to_exe/main_en.py` (English) or `python3 python_to_exe/main_jp.py` (Japanese). On Windows, `python` or `py -3` also works.
3. Select `sample.tsv` as Input. If Output Directory is empty, it fills with the input file's folder. Change it if needed, and set Output File Name to a name without an extension (for example, `sample`). Choose a format and click **Start Conversion／変換実行**.
4. The destination will contain `sample`, `sample.stas`, or `sample.txt`, depending on the format. You can enable Debug first and inspect `sample-debug.csv` (or `sample.stas-debug.csv` for STAS) to see the frames.

This example holds the left stick upward for five frames, then inputs A and the right stick for one frame, and waits three frames. The reference table below explains the loop and stick interpolation.

## GUI fields

| Field | How to use it |
| --- | --- |
| Input Script File／入力スクリプトファイル | `.tsv` compiles directly. `.txt` is treated as nx-TAS and converted to TSV first |
| Output Directory／出力ディレクトリ | If empty, fills with the input file's folder when Input is selected. An existing destination is not overwritten. An intermediate `.tsv` from `.txt` input is also saved here |
| Output File Name／出力ファイル名 | Enter a base name without an extension or folder. The GUI adds the format's extension |
| Output format／出力形式 | Choose LunaKit binary, STAS, or nx-TAS |
| Skip empty frames／空フレームを省略 | Available only for nx-TAS; upstream `-e` |
| Debug output／Debug出力 | Upstream `-d`; writes a CSV by appending `-debug.csv` to the output filename |
| Send via FTP／FTPで送信 | Upstream `-f`; uploads to `SMO/tas/scripts/` after creating local output |

The Japanese and English launchers use the same conversion behavior; only displayed language differs. `-l` is an interactive CLI option for repeated compilation and is not in the GUI.

### Built-in editor (Phase 2A)

Use **Edit...／編集...** beside Input to open a `.tsv` or `.txt` file. With no input selected, it opens an empty editor. After saving, the saved path appears in the converter's Input field. The File menu has New, Open, Save, Save As, and Close. Shortcuts are `Ctrl+N`, `Ctrl+O`, `Ctrl+S`, and `Ctrl+Shift+S`. New, Open, and Close ask what to do with unsaved changes.

The Edit menu provides Undo/Redo, Cut/Copy/Paste, and Select All. Shortcuts are `Ctrl+Z`/`Ctrl+Y` and `Ctrl+X`/`Ctrl+C`/`Ctrl+V`/`Ctrl+A`. Open Find with `Ctrl+F` or Replace with `Ctrl+H`; `F3`/`Shift+F3` searches next/previous. The dialog can replace the current match or all matches. Search is case-sensitive. Line numbers and a status bar show the line, column, modified state, and file kind (TSV-TAS/nx-TAS).

For now, this is a **raw text editor** that preserves tabs, UTF-8, and original line endings. It does not offer a spreadsheet view, interpret TSV-TAS syntax, or reformat files on save. `tsv-tas.py` remains responsible for interpreting scripts.

### FTP setup

Enabling FTP shows IP, port, user, and password fields. The GUI saves `ip` (string), `port` (integer), `user` (string), and `passwd` (string) to `ftp_config.json` beside the converter scripts. To use `-f` in the CLI, configure that file and run the command **from the repository root**. The file can contain secrets: do not commit or share it after entering credentials. FTP can be combined with any of the three output formats. Verify actual transfer in your Switch environment.

## TSV-TAS syntax essentials

| Syntax | Example and meaning |
| --- | --- |
| Duration | `5` means five frames. An empty duration field means one frame. A row containing only `3` waits three frames |
| Buttons | `1<TAB>a<TAB>zl` inputs A and ZL in the same frame. Supported names include `a`, `b`, `x`, `y`, `zl`, and `zr` |
| Sticks | `ls(90)` sets the left stick to radius 1 at 90 degrees. `rs(0.5; 180)` sets the right stick to radius 0.5 at 180 degrees. Angles are in degrees |
| 2P/Cappy | Put `$is_two_player = true` on its own row, then use `1<TAB>ca<TAB>cls(45)` for player two's A button and left stick. See the Documentation for details and target-mod limits |
| Loops | `6<TAB>a/b` alternates A and B for six frames. `/` separates inputs within one cell |
| Stick interpolation | `6<TAB>ls(0)->ls(50)` interpolates the left stick from 0 to 50 degrees over six frames |
| Expressions and variables | Put `$angle = 90` on its own row, then use `4<TAB>ls($angle + 45)`. Addition, subtraction, multiplication, and division are supported |
| Comments | A row whose duration field begins with `//` is ignored; for example, `// Explanation` |

`<TAB>` in the table is notation. Replace it with an **actual tab character** in the file. A row may have several input columns. For Cartesian stick coordinates, local durations, sequences, motion, gyro, and other advanced features, see the [Documentation](https://docs.google.com/document/d/1vW-swF3k96YxaIJqXbtRXbQ54mKKgeWfPFlW2hYBa_Q/edit?usp=sharing).

### STAS script commands (experimental)

Put a command on its own row, beginning with `/` in the duration column. The current converter processes the following commands **for STAS output**. A command row itself does not add a logical frame. Arguments for the newer commands are based on the current `tsv-tas.py` implementation.

| Command | Accepted form in the current implementation |
| --- | --- |
| `/tp x y z`, `/ctp x y z` | Set Mario's/Cappy's position. See the Documentation for forms with rotation |
| `/absStick on`, `/absStick off` | Enable/disable absolute stick mode |
| `/speed 2` | Set speed to an integer from **1 to 10** |
| `/pause` | Emit a pause command; no arguments |
| `/loadFile 1` | Supply an integer save-file ID and emit a load command |
| `/reloadFile` | Emit a reload command; no arguments |
| `/demo on`, `/demo off` | Enable/disable the demo flag |

For example, placing `/pause` between `1<TAB>a` and `1<TAB>b` puts the command at the start of the second input row. `/absStick` and `/demo` accept `true`, `1`, `on`, `y`, or `yes` as enabled values. Check the effects of commands on a Switch with a compatible LunaKit version.

## Convert nx-TAS to TSV-TAS

When you choose an nx-TAS `.txt` in the GUI, `nx-tas-to-tsv-tas.py` first creates a same-base-name `.tsv` in the destination, then compiles that TSV to the selected output format. To produce only the TSV, use the CLI:

```text
python3 nx-tas-to-tsv-tas.py input.txt output.tsv
```

This reverse converter comes from upstream and does not guarantee a complete round trip for every nx-TAS feature. Choose a destination/name that will not overwrite the source `.txt`.

## CLI

Run from the repository root. The output argument is a **local file path**.

```text
python3 tsv-tas.py input.tsv output
python3 tsv-tas.py -s input.tsv output.stas
python3 tsv-tas.py -ne input.tsv output.txt
python3 tsv-tas.py -fsd input.tsv output.stas
```

| Option | Behavior |
| --- | --- |
| `-f` | Upload the output via FTP using `ftp_config.json` |
| `-n` | Generate nx-TAS text |
| `-s` | Generate STAS |
| `-e` | Skip empty frames for nx-TAS |
| `-l` | Recompile each time Enter is pressed (CLI only) |
| `-d` | Generate `<output>-debug.csv` |

Combine options after one hyphen, such as `-ne`. `-n` and `-s` select different output formats, so do not combine them. Use `-e` with `-n`.

## Build and place Windows executables

Install Python 3 and PyInstaller on Windows, then run from the repository root:

```text
python -m pip install pyinstaller
python -m PyInstaller --noconsole --onefile python_to_exe/main_jp.py
python -m PyInstaller --noconsole --onefile python_to_exe/main_en.py
```

Place `dist/main_jp.exe` or `dist/main_en.exe` in the **same folder** as `tsv-tas.py`, `nx-tas-to-tsv-tas.py`, and `ftp_config.json`. The exe bundles the GUI only and launches the companion `.py` files. Keep Python 3 installed for use: on Windows the GUI looks for `py -3`, then a Python executable on `PATH`. The GUI passes paths containing spaces as separate arguments.

## Repository layout and differences from upstream

| Path | Role |
| --- | --- |
| `tsv-tas.py` | TSV-TAS converter based on `stas-dev`. The local FTP adjustment uses only the output path's basename as its remote name |
| `nx-tas-to-tsv-tas.py` | nx-TAS→TSV-TAS converter matching upstream |
| `python_to_exe/main_jp.py`, `main_en.py` | Japanese/English launchers |
| `python_to_exe/converter_gui.py`, `converter_logic.py` | Shared GUI, argument construction, Python discovery, and FTP settings |
| `python_to_exe/editor/` | Independent raw text editor window, file state, and find/replace operations |
| `ftp_config.json` | FTP connection settings; do not commit real credentials |
| `tests/test_conversion.py` | Local conversion and GUI argument tests |

The GUI adds file selection, three output formats, Debug/FTP/skip-empty controls, Japanese and English labels, logs, and PyInstaller entry points. Script syntax, motion, gyro, and STAS generation remain in the upstream converter.

## Notes and known limits

- The GUI treats `.txt` as nx-TAS input. Rename a tab-separated TSV-TAS script saved as `.txt` to `.tsv`, or compile it directly with the CLI.
- The upstream compiler recognizes the `.csv` suffix, but its current row parser still splits on tabs, so CSV input is unreliable. The GUI does not offer `.csv` input.
- `-e` is for nx-TAS only. STAS commands are experimental and need testing with the target mod.
- Verify Windows GUI exe behavior and real Switch FTP transfer in your own environment. The README examples were checked with the local converter.
