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

After a successful conversion, the dialog and log show the output file path. The log also lists the Debug CSV and intermediate TSV generated from `.txt` input, when enabled or applicable, and indicates when FTP transfer was attempted. Editor F5/F8 use the same result display. **Open Output Folder／出力フォルダーを開く** beside Output Directory opens the currently specified folder, even before conversion. An empty or missing folder produces an error.

### Recent files and preferences

Editor File → **Recent Files／最近使ったファイル** lists up to 10 `.tsv`/`.txt` paths, newest first, from Open, Save, Save As, Editor conversion, and Converter Input Browse. Reusing a path moves it to the top. Selecting an entry opens it in the current Editor and asks about any unsaved changes. Selecting a deleted file shows an error and removes its entry; **Clear Recent Files／履歴を消去** clears the list. Startup does not open a file automatically.

Recent files, output format, Debug, and the last Input/Output browse directories are saved to `settings.json` in the user config directory below. Browse dialogs start in a saved directory only if it still exists.

- Windows: `%APPDATA%/TSV-TAS-2-GUI/settings.json`; if APPDATA is unavailable, `~/AppData/Roaming/TSV-TAS-2-GUI/settings.json`.
- Linux/WSL: `$XDG_CONFIG_HOME/TSV-TAS-2-GUI/settings.json`; if unset, `~/.config/TSV-TAS-2-GUI/settings.json`.

The Editor also saves its window size, resized table column widths, Raw/Table preference, and Input Palette Basic/Advanced page to the same user settings, restoring them when an Editor next opens. The first-run size is 1200×700. Size changes are saved after about 400 ms without another resize; column widths are saved when dragging ends. `.txt` always opens in Raw Text without clearing a Table preference. Workspace settings do not store screen position, document content, selection, cursor/scroll position, Undo history, or Frame data. They are separate from existing Recovery snapshots.

Corrupt JSON, unsupported schemas, and invalid values fall back to defaults; a settings save failure does not stop editing or conversion. Document contents, Undo history, analysis results, and FTP connection details are not stored in these settings. FTP credentials keep the existing `ftp_config.json` behavior. The FTP checkbox is not persisted and starts OFF each time. Explicit FTP sending with F8 remains available.

### Unsaved recovery

Modified `.tsv`/`.txt` and untitled documents receive a separate Recovery snapshot for each Editor after about one second without changes, in the user config directory. This is **not autosave to the actual TSV/TXT** and does not overwrite the original file. A pending Table cell value without TABs or newlines is also included without committing the edit, changing selection, or adding an Undo step.

- Windows: `%APPDATA%/TSV-TAS-2-GUI/recovery/`; if APPDATA is unavailable, `~/AppData/Roaming/TSV-TAS-2-GUI/recovery/`.
- Linux/WSL: `$XDG_CONFIG_HOME/TSV-TAS-2-GUI/recovery/`; if unset, `~/.config/TSV-TAS-2-GUI/recovery/`.

On startup after an abnormal exit, the app shows each document's name and timestamp and asks to **restore / discard / cancel (keep for later)**. Restore only opens an unsaved Editor buffer retaining the original path. Untitled buffers request Save As when saved. If the original file differs from its saved baseline or is missing, the app warns without automatically merging or overwriting it.

Recovery remains after restoration. It is deleted after a successful Save / Save As / F5 / F8 save, or after an explicit discard and successful Close / New / Open replacement. Cancel keeps it. Multiple Editors have independent snapshots even for the same original path. Unreadable Recovery records and read/write failures are reported in the log without stopping editing. Document contents and local paths are stored **only in local user config**, never in the Git repository. Recovery does not include FTP connection settings or Undo history.

### Built-in editor

Use **Edit...／編集...** beside Input to open a `.tsv` or `.txt` file. With no input selected, it opens an empty editor. After saving, the saved path appears in the converter's Input field. The File menu has New, Open, Save, Save As, Save & Convert, Save, Convert & Send, Validate, Analyze Frames, and Close. Shortcuts are `Ctrl+N`, `Ctrl+O`, `Ctrl+S`, `Ctrl+Shift+S`, `F5`, `F6`, `F7`, and `F8`. New, Open, and Close ask what to do with unsaved changes.

Before saving to the same path, the Editor compares disk content with the Open / last-save baseline using a hash. It asks before overwriting an externally changed file or recreating a deleted one. Choosing No keeps the buffer, Undo, and Recovery, and stops F5/F8 conversion and FTP sending. If the contents cannot be checked, saving stops with an error. The same protection uses the old baseline after Recovery restoration. Save As to a different path is unaffected by changes to the original; overwrite confirmation for an existing destination stays with the file dialog. Save As to the same path uses the normal save guard.

Each Editor save of an existing `.tsv` keeps **up to 10 backups of the file before saving**, in the same folder. `route.tsv.before1` is the immediately preceding disk version; `route.tsv.before10` is the oldest. Rotation proceeds from the oldest generations downward. Backups preserve bytes without changing newlines or encoding, including the external disk version when you approve overwriting an external change. The first save of a new file and `.txt` files are excluded. Save As backs up the overwritten destination; F5/F8 use the same process when they actually save a TSV. If backup creation fails, the original TSV is not replaced and conversion/FTP sending does not start. This is separate from Recovery in user config, and backups are not automatically added to Recent Files. `.tsv.beforeN` files inside the repository are ignored by Git.

**Save & Convert** (`F5`) commits the current cell edit, saves it, and converts the file open in that Editor locally as the Converter's Input. It never sends by FTP, even when the parent GUI's FTP checkbox is on. For a new file, Save As asks where to save it; canceling stops conversion. After Save As, Input switches to the new path. If Output Directory or Output File Name is empty, it fills from the file's folder or stem; existing values are kept. Conversion uses the Converter's current output format, skip-empty (nx-TAS only), and Debug settings. Converter stdout and stderr appear in the existing log; conversion failures also show a dialog.

**Save, Convert & Send** (`F8`) uses the same save, Input synchronization, and local conversion workflow, then sends by FTP. It sends even when the parent GUI's FTP checkbox is off, using the current IP / Port / Username / Password fields. A new document requires Save As; canceling stops the send. If saving the FTP settings fails, conversion stops before starting and generates no new output. A transfer failure may occur after local output has already been generated. The parent GUI's **Start Conversion** still follows its FTP checkbox. F5/F8 leave the checkbox unchanged and identify the action in the log.

**Validate** (`F6`) commits the current cell edit and passes the current unsaved Editor buffer to the bundled converter as a temporary snapshot, using the selected output format. It does not save the actual file; untitled documents can be validated without Save As. The modified state and Undo history are preserved. Success shows “No errors”; failure shows the converter's unchanged message in Problems below the editor. Double-click a message with an explicit source line number to jump there. Errors without a reliable line number, including errors in the intermediate TSV made from `.txt`, have no guessed jump target. If you edit during validation, the Editor asks you to validate again. Validate leaves Converter output settings unchanged and does not upload by FTP or generate a Debug CSV. Use **Save & Convert** to save the file and create the normal output.

The upper right shows the selected TSV rows' **Start / Duration / End / Total** frames. Start and End are zero-based frame indices; Duration and Total are frame counts. For 18 frames, it shows `Start: 0f | Duration: 18f | End: 17f | Total: 18f`. In Table, it summarizes all rows from the top to the bottom of the selection; a single-row selection shows that row. In Raw Text, it follows the cursor's line. A completely empty row (including TAB-only or whitespace-only rows) consumes the converter's default 1f. A row with an empty first cell but input elsewhere also uses the default 1f. About 0.5 seconds after an edit, a background run of the bundled converter analyzes a temporary TSV snapshot and updates the display automatically. It does not save the document or upload by FTP. The values come from the converter's resolved row duration and total frame count; while updating or after an error, they are shown as unavailable. Changing the selection only looks up cached results. `.txt` is not supported here.

Enter a zero-based frame number in the permanent **Go to** field beside the Frame display, then press Enter or **Go** to navigate to the TSV source row that generates that frame. `Ctrl+G` focuses the field; Escape returns to the editor. Table keeps the current column; Raw Text moves to the start of the line. Navigation uses only the bundled converter's cached source-line map, without running another analysis. While updating, after an analysis failure, or when no resolved source row matches, it stays put and shows feedback beside the field. A pending cell edit is committed when Go runs; if its content changes, wait for automatic analysis and try Go again. `.txt` (nx-TAS) is not supported.

For detailed Debug CSV data, use **Analyze Frames** (`F7`) in the File menu to open a separate Frame Inspector window. This operation also analyzes the current unsaved buffer, including untitled documents, as a temporary snapshot and generates a temporary Debug CSV with the bundled converter. It does not save the actual file and preserves the modified state and Undo history. It leaves the Converter's Debug checkbox and output settings unchanged and never uploads by FTP. **Total Frames** is the largest CSV `Frame` number plus one, so 1P/2P rows for the same frame are not counted twice. The list shows buttons, LS/RS, commands, and other key fields; selecting a row shows every CSV field, including acceleration and gyro, in the detail area. Enter a frame number and choose **Go** to select it. If you edit during analysis, stale results are not applied and the Editor asks you to analyze again. If analysis fails, Problems shows the error and any earlier Inspector result is marked as previous. The current Debug CSV has no reliable source TSV line information, so the Inspector does not jump back to source rows.

The Edit menu provides Undo/Redo, Cut/Copy/Paste, and Select All. Shortcuts are `Ctrl+Z`/`Ctrl+Y` and `Ctrl+X`/`Ctrl+C`/`Ctrl+V`/`Ctrl+A`. Open Find with `Ctrl+F` or Replace with `Ctrl+H`; `F3`/`Shift+F3` searches next/previous. The dialog can replace the current match or all matches. Search is case-sensitive. Line numbers and a status bar show the line, column, modified state, and file kind (TSV-TAS/nx-TAS).

For `.tsv` files and new unsaved documents, switch between **Raw Text** and **Table**. Table splits each line only at TAB characters and preserves empty cells, blank lines, and trailing TABs. A new table initially shows columns A–G, labeled A “Duration,” B “LS,” C “RS,” and D–G “Button.” These are input guides and do not enforce column meaning. Navigation, paste, and column insertion still reach H and later columns. Table shows cell borders, row numbers, and highlights for the active cell and selected range. A single click selects a cell; Shift+click and drag select a range. Typing an ASCII character into a selected cell starts editing and replaces its previous value. F2 or double-click edits the existing value; Left/Right and Home/End then move the text caret. With no suggestion popup open, Tab/Shift+Tab commits and selects the right/left cell, Enter/Shift+Enter commits and selects the cell below/above, and Escape discards the edit. While only selecting, Tab/Shift+Tab/Enter/Shift+Enter/arrow keys move between cells, and Shift+arrow keys extend the range. For Japanese IME input, open the cell editor with F2 or double-click. Switching views without editing does not change the file content or modified state. `.txt` (nx-TAS) remains Raw Text only. Undo/Redo, Save, and Save & Convert also work after table edits.

With a range selected in Table, `Ctrl+C`/`Ctrl+X`/`Ctrl+V` copies, cuts, or pastes cells using TABs and newlines. While editing text inside a cell, these shortcuts edit text normally; a paste containing TABs or newlines expands into the table. You can paste multiple rows and columns copied from an external spreadsheet; pasting starts at the selection's top-left cell and expands rows or columns as needed. Delete/Backspace clears selected cells. Click a row number or column heading to select the whole row or column; Shift+click selects multiple rows or columns. Right-click a cell, row number, or column heading for cut/copy/paste and structural actions. The **Table** menu also inserts rows above/below, duplicates or deletes rows, and inserts columns left/right or deletes them. **+ Row**/**+ Column** beside Table inserts below the active row or right of the active column. Deleting multiple rows or columns selected through their headers removes the whole selection. Each table operation takes one Undo step.

Drag the right edge of a column header to resize that column. Click away from an edge to select the column as before. Column widths remain across Raw Text/Table switches and are restored when an Editor next opens. Resizing does not change file content or Undo history.

At the last row, Enter or Down moves to an unsaved virtual row. Moving alone adds no blank line. Entering and committing text there adds only the needed rows. After Tab or Enter navigation, the cell remains selected so you can type the next value directly. The table also draws empty cells across unused viewport space and keeps an expanded display range when you select another cell. Displayed empty cells alone do not add saved content.

While editing a Table cell, typing `l` or `/` can show suggestions for buttons, sticks, acceleration/gyro, 2P input, and STAS commands. Use Up/Down to select, then Tab/Enter or a click to insert a suggestion and continue editing. Escape first closes only the popup. The **Input Palette** is always visible to the right of the table and offers common buttons, left/right sticks, and STAS commands. Selecting an item starts editing the selected cell or inserts at the caret while editing. Left and right stick suggestions each show the simple angle form first. Candidates with parentheses or arguments insert a template with its value selected, ready to replace. Raw Text for `.tsv` colors comments, commands, variables, and inputs. In Table, a subtle background hints that the first column is often duration, while a color beside row numbers distinguishes ordinary input, comment, command, variable, loop/control-like, and blank rows. The first cell of a command or comment row is not treated as duration. Colors and row categories are **editing aids**, not syntax validation. The converter processes STAS commands when producing STAS output.

The Input Palette uses two columns in a 400px sidebar. Use the top ◀/▶ buttons to switch between Page 1 **Basic** (Buttons / Left Stick / Right Stick / Stick Preview) and Page 2 **Advanced** (STAS Commands / Cappy / Accel / Gyro / Notation). The first Editor starts on Page 1; later Editors restore the last page. Switching pages does not affect the document, selection, or Undo history. Scroll each page vertically with the mouse wheel inside the palette or its scrollbar. In each stick category, `ls(angle)` or `rs(angle)` occupies a wide first-row button; radius-plus-angle and XY forms sit left and right on the next row. The 16 button candidates show controller icons alongside text. If an image cannot be read, the button shows text alone. Display labels and inserted TSV text are managed separately.

**Stick Preview** at the bottom of Page 1 shows 1P LS/RS side by side on unit circles. It uses the active row's zero-based StartFrame: red marks the current position, and progressively lighter red marks the previous 1–3 frames. It also displays x/y (Debug coordinates normalized from the converter's 32767 scale), radius, and angle in degrees. A single run of the existing background converter analysis produces both the source-line map and Debug CSV; selection changes only read the cache. Pending edits, updates, and analysis failures show no confirmed values, and missing frames are not filled in. This is read-only: it does not change the document, Undo history, or Converter settings, save the source file, or send by FTP.

Table does not interpret TSV-TAS syntax or apply its own formatting on save. Column operations affect every row, including command and comment lines. Both views preserve UTF-8 and original line endings where possible. `tsv-tas.py` still interprets scripts.

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
| `-m` | Specific to this GUI fork. Write converter-resolved source-line frame positions to `<output>-lines.csv` (used by the Editor's automatic display) |

Combine options after one hyphen, such as `-ne`. `-n` and `-s` select different output formats, so do not combine them. Use `-e` with `-n`.

## Build and place Windows executables

Install Python 3 and PyInstaller on Windows, then run from the repository root:

```text
python -m pip install pyinstaller
python -m PyInstaller --noconsole --onefile --add-data "assets/icons/png:assets/icons/png" python_to_exe/main_jp.py
python -m PyInstaller --noconsole --onefile --add-data "assets/icons/png:assets/icons/png" python_to_exe/main_en.py
```

Place `dist/main_jp.exe` or `dist/main_en.exe` in the **same folder** as `tsv-tas.py`, `nx-tas-to-tsv-tas.py`, and `ftp_config.json`. The exe bundles the GUI and PNG icons, and launches the companion `.py` files. Keep Python 3 installed for use: on Windows the GUI looks for `py -3`, then a Python executable on `PATH`. The GUI passes paths containing spaces as separate arguments.

## Repository layout and differences from upstream

| Path | Role |
| --- | --- |
| `tsv-tas.py` | TSV-TAS converter based on `stas-dev`. The local FTP adjustment uses only the output path's basename as its remote name |
| `nx-tas-to-tsv-tas.py` | nx-TAS→TSV-TAS converter matching upstream |
| `python_to_exe/main_jp.py`, `main_en.py` | Japanese/English launchers |
| `python_to_exe/converter_gui.py`, `converter_logic.py` | Shared GUI, argument construction, Python discovery, and FTP settings |
| `python_to_exe/app_settings.py` | Non-sensitive preferences and shared Recent Files in user config |
| `python_to_exe/editor/` | Raw Text/Table editor, file state, find/replace, input hints, validation, Debug CSV parsing, and Frame Inspector |
| `python_to_exe/editor/recovery.py` | Per-document Recovery snapshots in user config, restoration, and original-file change detection |
| `ftp_config.json` | FTP connection settings; do not commit real credentials |
| `tests/test_conversion.py` | Local conversion and GUI argument tests |

The GUI adds file selection, three output formats, Debug/FTP/skip-empty controls, Japanese and English labels, logs, and PyInstaller entry points. Script syntax, motion, gyro, and STAS generation remain in the upstream converter.

## Notes and known limits

- The GUI treats `.txt` as nx-TAS input. Rename a tab-separated TSV-TAS script saved as `.txt` to `.tsv`, or compile it directly with the CLI.
- The upstream compiler recognizes the `.csv` suffix, but its current row parser still splits on tabs, so CSV input is unreliable. The GUI does not offer `.csv` input.
- `-e` is for nx-TAS only. STAS commands are experimental and need testing with the target mod.
- Verify Windows GUI exe behavior and real Switch FTP transfer in your own environment. The README examples were checked with the local converter.
