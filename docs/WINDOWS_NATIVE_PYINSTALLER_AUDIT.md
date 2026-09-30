## 1. 監査結果とWindowsリスク

対象は `6803605fc8438556a111cb0557ca6b8fd91e9dbf`。**読み取り調査のみ実施し、変更・commit・pushはしていません。** Windows実機での動作確認は今回行っていません。

| 優先度 | リスク・確認事項 | 現行実装／判断 |
|---|---|---|
| 高 | 通常変換の文字encoding | Validate／Analyze／Frame解析は `PYTHONUTF8=1` を指定しますが、通常変換は指定しません。converterの通常入力はlocale依存なので、UTF-8日本語を含む文書で確認系だけ成功し、F5／F8が失敗・文字化けする可能性があります。 |
| 高 | frozen exeから外部Pythonを起動 | 外部Python選択自体は適切ですが、PyInstallerが変更するDLL検索設定を戻す処理はありません。異なるPython環境での起動を確認する必要があります。 |
| 高 | Microsoft IMEとEntry binding | EntryのEnter／Tab／Escapeを独自処理しています。IME変換確定より先にcell commitやnavigationが起きないか、実機確認が必要です。 |
| 中 | 外部handleによる保存失敗 | アプリ自身のhandleは閉じています。他Editor・preview handler・AV等の共有設定によって、置換やbackup rotationが拒否される可能性があります。 |
| 中 | read-only属性とtemp cleanup | 元file modeをtemp／backupへコピーします。Windowsではread-only属性がcleanupのunlinkを妨げ、tempが残る可能性があります。 |
| 中 | `--noconsole`での診断 | 独自のTk callback error loggerはありません。stderrがないexeでは、予期しないcallback例外の調査が難しくなります。 |
| 中 | DPIと保存済みpixel値 | window size、Palette幅、列幅、PNGサイズにpixel値があります。DPI変更後の表示・hit testingは未確認です。 |
| 中 | 強制終了中のworker | Recoveryの完成済みsnapshotは残りますが、解析tempのcleanupやconverter子processの停止までは保証されません。 |

encoding未指定の`open()`はlocale依存です。[Python公式仕様](https://docs.python.org/3/library/functions.html#open)  
PyInstallerはWindowsでDLL検索設定を変更し、子processにも影響すると説明しています。また、`--noconsole`では標準streamが`None`になります。[PyInstaller公式の注意事項](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html)

### 修正候補の優先順位

1. **通常変換のUTF-8実行契約を確認系と揃える最小修正を推奨。**  
   対象は [converter_gui.py:448](/home/asitano_syuyaku/TSV-TAS-2-GUI/python_to_exe/converter_gui.py:448) と [validation.py:74](/home/asitano_syuyaku/TSV-TAS-2-GUI/python_to_exe/editor/validation.py:74)。converterのsyntax変更は不要です。子processのencodingと親側のstdout/stderr decodingを一緒に整理する必要があります。
2. **onefile診断buildで外部Python起動を確認し、DLL境界処理と例外記録を配布前に判断。**  
   `SetDllDirectoryW`はprocess全体へ影響するため、workerごとに無計画に変更する案は避けます。
3. **read-only／共有lockのnative再現後にcleanup改善を判断。**
4. **DPI／IME修正は実測後。現時点でDPI APIやIME独自処理を追加する根拠は不足。**

**自動retryは現時点では追加不要です。** 自前handleの閉じ忘れは見つかりませんでした。AV等の一時的なsharing violationが再現した場合だけ、失敗した個別I/O操作への限定retryを検討します。rotation済みのSave全体を再試行すると、保存失敗でも世代がさらに進むため不適切です。

## 2. 静的調査で適切だった箇所

### Editor save／backup

[document.py:109](/home/asitano_syuyaku/TSV-TAS-2-GUI/python_to_exe/editor/document.py:109)、[save_backups.py:20](/home/asitano_syuyaku/TSV-TAS-2-GUI/python_to_exe/editor/save_backups.py:20) を確認しました。

- 新内容はsame-directory tempfileへ書き、flush／fsync後にcloseしています。
- backupは実際のtargetをbinaryで読み、sourceとsnapshotの両handleを閉じてからrotationします。
- rotationは大きい番号から`os.replace`。primaryをrenameしてbackupへ移す処理ではありません。
- backup成功後にprimaryを置換し、その後だけbaselineを更新します。
- external guardでNo／unreadableならbackupへ進みません。
- backup／保存失敗は既存error経路へ戻り、F5／F8を停止します。
- `Path.read_bytes()`による外部変更確認も、handleを保持し続ける設計ではありません。

ただし、**rotationはtransactionではありません**。後半で失敗するとprimaryは旧内容のままでもbackup履歴は一部進むことがあります。これは現行設計の明示された制限です。

Windowsの`chmod`は主にread-only属性の扱いであり、POSIX modeやACLの完全保存ではありません。`fsync`はWindowsでも利用できます。[Python os仕様](https://docs.python.org/3/library/os.html)

### Recovery／settings

[app_settings.py:24](/home/asitano_syuyaku/TSV-TAS-2-GUI/python_to_exe/app_settings.py:24)、[recovery.py:84](/home/asitano_syuyaku/TSV-TAS-2-GUI/python_to_exe/editor/recovery.py:84) を確認しました。

- `%APPDATA%/TSV-TAS-2-GUI/settings.json`と`recovery/`を使用。
- APPDATAが使えなければ`~/AppData/Roaming/TSV-TAS-2-GUI/`へfallback。
- JSONのread/write handleは`with`でcloseし、atomic replacement前に閉じます。
- 同一processの複数Editorはsettingsを共有し、RecoveryはUUIDごとに独立します。
- 復元直後はRecoveryを残し、実ファイルを書き換えません。
- 正常Save／明示Discardで削除、Cancelでは保持します。

task killで復元できるのは、**最後にdebounceが完了して書かれたsnapshotまで**です。連続入力中や書き込み前の内容まで保証する仕様ではありません。複数のGUI process間のsettings競合制御はありません。

## 3. PyInstaller／path／Python起動

| 対象 | source実行 | frozen実行 |
|---|---|---|
| PNG | repo rootの`assets/icons/png/` | `_MEIPASS/assets/icons/png/` |
| converter `.py` | repo root | exeの隣 |
| `ftp_config.json` | converterの隣 | exe／converterの隣 |
| settings／Recovery | user config | 同じuser config |
| converter実行cwd | converter配置directory | exe配置directory |

[resources.py:7](/home/asitano_syuyaku/TSV-TAS-2-GUI/python_to_exe/editor/resources.py:7)、[converter_logic.py:59](/home/asitano_syuyaku/TSV-TAS-2-GUI/python_to_exe/converter_logic.py:59) の分離は適切です。PNG欠損時のtext fallbackとPhotoImage参照保持もあります。

READMEの`--add-data "assets/icons/png:assets/icons/png"`は現在のPyInstaller仕様と一致します。tracked spec／独自build scriptはなく、README commandがbuild基準です。Windows exeはWindows上でbuildしてください。[PyInstaller build仕様](https://pyinstaller.org/en/stable/usage.html)、[bundle path仕様](https://pyinstaller.org/en/stable/runtime-information.html)

Python選択は次の順です。

- source：`sys.executable`
- Windows frozen：PATHから見つかった`py -3`
- 次に`python`／`python3`
- GUI exe自身はconverter用Pythonに選びません

引数はlistで渡し、`shell=True`は使っていません。`list2cmdline()`はlog表示用です。空白・日本語pathのために手動quoteを追加する必要はありません。[Python subprocess仕様](https://docs.python.org/3/library/subprocess.html)

残る確認点：

- `py`は存在するがPython 3が使えない場合、別Pythonへの自動fallbackはありません。
- PATH上のPythonのversion／実行可能性を事前probeしていません。
- FTP設定を書き込むため、exe配置directoryには書き込み権限が必要です。
- resourceはcwd非依存ですが、GUIへ**手入力した相対Input／Output path**は起動cwd基準です。

## 4. Windows native acceptance checklist

まず通常ユーザー権限の検証用directoryで実施し、Python／Tk／PyInstallerのversionを記録してください。JP／ENとsource／onefileを確認対象にします。

| 順序 | 操作 | 期待結果 | 問題時に確認する場所 |
|---|---|---|---|
| **A. launch／build** | 別cwd、空白・日本語directoryからJP／EN起動。`py`あり／PATH Pythonのみも確認 | Editor・iconsが開く。外部converterを発見。Python不足は明示error | `converter_logic.py::scripts_dir/python_command`、`resources.py` |
| **B. Editor basic** | New、Open、Save As、Recent、未保存CloseのSave／Discard／Cancel。TSV／TXT、Unicode名 | buffer・path・modifiedが正しい。TXTはRawのみ。dialogの上書き確認が機能 | `window.py::open_file/_save_to`、`document.py` |
| **C. Table editing** | direct typing、F2、double click、150回以上Tab／Enter、drag／Shift選択、paste、列resize、10,000行scroll | freezeなし。Entry再利用。virtual cell移動だけでは文書不変 | `grid.py::begin_edit/_entry_move/_move`、`column_layout.py` |
| **D. IME** | F2／double clickから日本語入力。composition中Enter／Tab／Escape、確定後commit、Ctrl+C/V。autocomplete開閉も確認 | IME確定とcell移動が混同されず、文字消失なし。Raw／Find／Replaceも正常 | `grid.py::_bind_entry_navigation/_completion_or_move`、`window.py::show_find` |
| **E. Palette／icons** | Basic／Advanced切替、16 icons、template挿入、Palette上のwheel | 2列330px、文字との重なりなし。Table selection保持。Table側scrollを奪わない | `window.py::_build_input_palette/_palette_wheel`、`resources.py` |
| **F. Frame／Ctrl+G** | 上下・複数行selection、Ctrl+G、Enter、Escape、invalid frame、pending cellありのGo | 0-based表示、cached mapでjump。stale時は停止。左右移動では同じ行情報 | `line_positions.py`、`window.py::go_to_frame` |
| **G. Validate／Analyze** | 未保存・UntitledでF6／F7。解析中edit／Close、Problems jump | diskを保存せずFTPなし。古い結果を適用しない。CSV空行にも対応 | `snapshot.py`、`validation.py`、`debug_csv.py` |
| **H. Save safety** | 下記backup手順に加え、外部削除のYes／No、read-only、Save As同一path | guard後に保存。失敗時buffer／Recovery保持、Convert停止 | `file_state.py`、`document.py`、`save_backups.py` |
| **I. Recovery** | TSV／TXT／Untitled／pending cellを変更し、snapshot完成後に対象GUIをtask kill。再起動でRestore／Discard／Cancel、複数件・元file外部変更 | pathと未保存内容を復元。disk自動上書きなし。復元後Saveにもguard | `recovery.py`、`window.py::_schedule_recovery`、`converter_gui.py::_check_recovery` |
| **J. F5／F8／Converter** | 3形式、TXT二段階、Debug、nx専用`-e`。F5はFTP ON、F8はOFFでも試す。busy中連打／Close | F5 local、F8 send要求。出力path表示。二重起動なし。終了時の子process挙動も記録 | `converter_gui.py::start_conversion/convert`、`window.py::save_and_convert` |
| **K. settings** | size、列幅、view、page、format／Debug変更後に再起動。複数Editorも確認 | preferences復元、TXTの一時RawでTable preference消失なし、FTPはOFF開始 | `app_settings.py`、`window.py::_remember_workspace` |
| **L. DPI** | 100／125／150／200%で起動・resize・再起動。他DPIで保存したgeometryも復元 | Frame欄・menu・dialog・親GUIが欠けない。icons／row／Entry／列境界が一致 | `window.py`のview bar／Palette／geometry、`grid.py`のfont metrics／座標 |

アプリcodeに明示的なDPI awareness設定はありません。実exeのmanifestとTkの状態も確認してください。保存済みsize／列幅はDPIに応じて正規化されないため、scale変更後の同じpixel値が同じ使いやすさを保証するものではありません。

### Tk eventの重点確認

現行bindingは次のとおりです。

- wheel：Table／Palette／Inspectorに`<MouseWheel>`とLinux用Button-4/5。
- Table wheelはdeltaの**符号だけ**、Paletteは120単位と小deltaを扱います。
- 横wheel専用bindingはありません。横scrollbarは別途確認してください。
- Ctrl shortcuts、Shift+Tab、Shift+Enter、B1 drag、double click、Button-3 context menuあり。
- Closeは`WM_DELETE_WINDOW`、cleanupは`<Destroy>`。Windows終了通知専用の処理はありません。
- F2後のEntryは再利用し、編集終了時はhideします。文字入力はASCII direct typing、日本語はEntry内の標準IMEを使用します。

wheel／Shift-wheel／focusのplatform差はTk公式仕様にもあります。[Tk bind仕様](https://www.tcl-lang.org/man/tcl8.6/TkCmd/bind.htm)

## 5. Backupの具体的なWindows確認手順

検証先例：`C:\TAS Audit 日本語\`。versionを区別するため、文書先頭に`// V0`などを置きます。

1. 外部で`test.tsv`を作成してOpen。Openだけではbackupなし。
2. `V1`へ変更してCtrl+S。primary＝V1、before1＝V0を確認。
3. V2～V12を順に保存。
4. primary＝V12、before1＝V11、before10＝V2、before11なしを確認。
5. CRLF／mixed newlineを含む旧disk版がbackupでbyte一致することを確認。
6. 外部Editorでdiskを`EXTERNAL1`へ変更。
7. GUIのoverwrite確認でYes。before1＝EXTERNAL1を確認。
8. 再び外部変更し、GUIでNo。
9. primary・全backupがNo直前と同じで、buffer・Undo・Recoveryが残ることを確認。
10. Save Asで既存`other.tsv`を選択。OS確認後、旧other版がother.before1になることを確認。source側履歴は不変。
11. Save Asで新しいTSVへ保存。初回backupなしを確認。
12. 編集してF5。backup後にlocal出力。親FTP ONでも送信なし。
13. **無効なFTP Portを設定してF8**。Save／backup成功後、FTP設定errorでconverter・送信前に停止することを確認。
14. 空白path・日本語path・日本語filenameで繰り返す。
15. Explorerで選択中、preview pane OFF／ONそれぞれで保存。
16. 別text editorで開いたまま保存。単に画面で開いている状態と、handleを保持する状態を分ける。
17. primaryおよびbeforeNを共有lockしてSave。error時にprimary不変・modified保持・F5/F8停止を確認。lock解除後に再保存。
18. 外部削除のNo／Yes、read-only file／backupでも確認。

共有lockは、別PowerShellで例えば次のように作れます。

```powershell
$lock = [System.IO.File]::Open(
  'C:\TAS Audit 日本語\test.tsv',
  [System.IO.FileMode]::Open,
  [System.IO.FileAccess]::Read,
  [System.IO.FileShare]::Read
)
# GUIでSaveを試した後、必ず解除
$lock.Dispose()
```

Explorer選択や別Editorの表示だけでは、排他的handleを保持しているとは限りません。rename／deleteを許す共有flagで結果が変わります。[Microsoftの共有handle仕様](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)

**guardでNoならbackup不変ですが、I/O失敗ではrotationが一部進む場合があります。** この二つを同じ期待結果にしないでください。

## 6. 自動テストの分類

今回は再実行せず、280件の構成を調査しました。

| 分類 | 件数／内容 |
|---|---|
| 実Tk window不要 | **206件**。純粋helper、tempdir I/O、実converter subprocess、Tk stubを含む |
| 実Tk必要 | **74件**。Editor、Palette、Recovery、workspace、navigation、save workflow等 |
| platform依存 | 上記と重複。POSIX modeの**2件はWindowsでskip**。filesystem・encoding・Python探索はnativeでも再実行が必要 |
| native Windowsのみの実測 | IME、DPI、Explorer、sharing lock、onefile、Windows task killは既存自動テストで未保証 |

特に：

- [test_table_grid.py:188](/home/asitano_syuyaku/TSV-TAS-2-GUI/tests/test_table_grid.py:188) の35件はTk stubです。
- [test_palette_icons.py:59](/home/asitano_syuyaku/TSV-TAS-2-GUI/tests/test_palette_icons.py:59) はbuild commandの文字列検査で、実bundle検証ではありません。
- Python探索テストはmock中心で、nativeの`py -3`やPATH aliasの実動作は未確認です。
- GitignoreテストにはWindows側のGitが必要です。
- Tkテストの一部はbinding callbackを直接呼ぶため、実keyboard／IME／focusの確認を代替しません。
- GUIが開けないため74件がskipした結果は、native acceptance成功として扱えません。

## 7. 推奨commands

Windows側repository rootで実行します。最初はUTF-8環境を強制せず、通常環境で確認してください。

```powershell
py -3 --version
py -3 -m tkinter
py -3 -m unittest discover -s tests -v
py -3 -m unittest discover -s tests -p "test_save_backups*.py" -v
py -3 -m PyInstaller --version
```

まず診断用console build、その後READMEどおりの配布buildを推奨します。

```powershell
py -3 -m PyInstaller --console --onefile --name main_jp_audit --add-data "assets/icons/png:assets/icons/png" python_to_exe/main_jp.py

py -3 -m PyInstaller --noconsole --onefile --add-data "assets/icons/png:assets/icons/png" python_to_exe/main_jp.py
py -3 -m PyInstaller --noconsole --onefile --add-data "assets/icons/png:assets/icons/png" python_to_exe/main_en.py
```

exeは外部converter二本と`ftp_config.json`の隣へ配置し、上のmanual checklistを実施します。実FTP転送は最後にWindows／Switchで別途確認してください。

## 8. git status

```text
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

HEADは `6803605fc8438556a111cb0557ca6b8fd91e9dbf` のままです。
