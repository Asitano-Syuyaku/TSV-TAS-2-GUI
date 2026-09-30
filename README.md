# TSV-TAS-2-GUI

[English](README_EN.md) | 日本語

Super Mario Odyssey のTAS用スクリプトを変換する、[xiivler/TSV-TAS-2](https://github.com/xiivler/TSV-TAS-2/tree/stas-dev) のGUI forkです。converterはupstream **`stas-dev` の commit `245d5600c8ccc5dd97857b135341e6ba2cbe86e6`** を基準とし、GUIは同梱のPythonスクリプトをsubprocessで実行します。高度な書式は [TSV-TAS-2 Documentation](https://docs.google.com/document/d/1vW-swF3k96YxaIJqXbtRXbQ54mKKgeWfPFlW2hYBa_Q/edit?usp=sharing) を参照してください。

## 出力形式と必要環境

| GUIの選択肢 | 出力 | 用途 |
| --- | --- | --- |
| LunaKit binary | 拡張子なし | 従来のLunaKit用バイナリ。CLIの既定値 |
| STAS | `.stas` | 新しいLunaKit用のSTAS形式。後述のscript commandを出力可能 |
| nx-TAS | `.txt` | smo-practice用のテキスト形式。空フレームの省略に対応 |

Python 3とTkinterが必要です。GUI exeもconverterを動かすために別途Python 3が必要です。Windows exeを作る場合だけPyInstallerが必要です。生成ファイルをSwitchで使うには、選んだ形式に対応するmodが必要です。FTP送信にはSwitch側のFTPサーバーと接続情報が必要です。

## まず1本作る

1. 表計算ソフトまたはテキストエディターで `sample.tsv` を作ります。**列はタブで区切り**、1列目をduration（フレーム数）、2列目以降を同時に行う入力にします。次は実際のタブ区切りの例です。

   ```text
   $angle = 90
   // 最初のコメント行
   5	ls($angle)
   1	a	rs(0)
   3
   4	b	ls(0)/ls(90)
   6	ls(0)->ls(50)
   ```

2. repositoryのルートで `python3 python_to_exe/main_jp.py`（日本語）または `python3 python_to_exe/main_en.py`（English）を起動します。Windowsでは `python` または `py -3` でも実行できます。
3. Inputに `sample.tsv` を選びます。Output Directoryが空なら入力ファイルと同じフォルダーが自動設定されます。必要なら変更し、Output File Nameに拡張子なしの名前（例: `sample`）を指定します。形式を選び、**Start Conversion／変換実行**を押します。
4. 選んだ形式に応じて `sample`、`sample.stas`、または `sample.txt` が保存先にできます。まずはDebugを有効にして `sample-debug.csv`（STASなら `sample.stas-debug.csv`）でフレームを確認できます。

この例は最初に左スティックを5フレーム上方向へ倒し、次にAボタンと右スティックを1フレーム入力し、3フレーム待機します。ループとスティック補間の詳細は下の早見表にあります。

## GUIの項目

| 項目 | 使い方 |
| --- | --- |
| Input Script File／入力スクリプトファイル | `.tsv` は直接コンパイル。`.txt` はnx-TAS入力として先にTSVへ変換 |
| Output Directory／出力ディレクトリ | 空欄ならInput選択時にそのファイルのフォルダーを自動設定。指定済みの出力先は上書きしない。`.txt` 入力の中間 `.tsv` もここに保存 |
| Output File Name／出力ファイル名 | 拡張子やフォルダーを含まないベース名。形式に応じた拡張子をGUIが付加 |
| Output format／出力形式 | LunaKit binary、STAS、nx-TASから選択 |
| Skip empty frames／空フレームを省略 | nx-TASを選んだ場合だけ有効。upstreamの `-e` |
| Debug output／Debug出力 | upstreamの `-d`。出力ファイル名に `-debug.csv` を加えたCSVを保存 |
| Send via FTP／FTPで送信 | upstreamの `-f`。ローカル出力後、`SMO/tas/scripts/` へ送信 |

日本語版と英語版は表示言語以外、同じ変換処理を使います。`-l` は対話的に再生成するCLI専用オプションで、GUIにはありません。

変換成功後は出力ファイルのpathをダイアログとログに表示します。Debug CSVと `.txt` 入力から生成した中間TSVのpath、FTP送信を実行した旨もログで確認できます。EditorのF5／F8も同じ結果表示を使います。Output Directory横の **出力フォルダーを開く／Open Output Folder** は、現在指定しているフォルダーを開きます。変換前でも利用でき、空欄や存在しないフォルダーはエラーになります。

### 最近使ったファイルと設定

EditorのFile → **最近使ったファイル／Recent Files** は、開く・保存・名前を付けて保存・Editorからの変換・ConverterでのInput参照で使った `.tsv`／`.txt` を最大10件、新しい順に表示します。同じpathは先頭へ移動します。選ぶと現在のEditorで開き、未保存の変更があれば保存確認を行います。削除済みのファイルは選択時に通知して履歴から除き、**履歴を消去／Clear Recent Files** で全履歴を消せます。起動時にファイルを自動で開きません。

履歴、出力形式、Debug、最後のInput／Output参照directoryは、次のuser configに `settings.json` として保存します。参照ダイアログは保存されたdirectoryが存在する場合だけそこから開始します。

- Windows: `%APPDATA%/TSV-TAS-2-GUI/settings.json`。APPDATAが使えなければ `~/AppData/Roaming/TSV-TAS-2-GUI/settings.json`。
- Linux／WSL: `$XDG_CONFIG_HOME/TSV-TAS-2-GUI/settings.json`。未設定なら `~/.config/TSV-TAS-2-GUI/settings.json`。

Editorのウィンドウサイズ、変更した表の列幅、Raw／Tableの表示preference、Input PaletteのBasic／Advancedページも同じuser settingsへ保存し、次回Editor起動時に復元します。初回サイズは1200×700です。サイズ変更は約400ms待って保存し、列幅はdrag終了時に保存します。`.txt`は常にRaw表示となりますが、そのためにTable preferenceは消しません。画面上の位置、文書内容、選択・cursor・scroll位置、Undo履歴、Frame情報はworkspace設定に保存しません。既存のRecovery snapshotとは別の仕組みです。

壊れたJSON・非対応schema・不正な値は既定値へ戻し、設定の保存に失敗しても操作を続けられます。文書内容、Undo履歴、解析結果、FTP接続情報はこの設定に保存しません。FTP credentialは従来の `ftp_config.json` のままで、FTPチェックは保存せず起動ごとにOFFになります。F8による明示的なFTP送信は従来どおり利用できます。

### 未保存内容の復旧

変更中の `.tsv`／`.txt` と無題の文書は、約1秒操作が止まるとEditorごとのRecovery snapshotをuser config内へ保存します。これは**実TSV／TXTへのautosaveではなく**、元ファイルを上書きしません。表で入力中のセルも、TABや改行を含まない通常のセル値なら、編集確定・選択変更・Undo追加なしでsnapshotへ含めます。

- Windows: `%APPDATA%/TSV-TAS-2-GUI/recovery/`。APPDATAが使えなければ `~/AppData/Roaming/TSV-TAS-2-GUI/recovery/`。
- Linux／WSL: `$XDG_CONFIG_HOME/TSV-TAS-2-GUI/recovery/`。未設定なら `~/.config/TSV-TAS-2-GUI/recovery/`。

異常終了後の起動時は、文書名と時刻を示して、各snapshotの**復元／破棄／キャンセル（次回まで保留）**を確認します。復元は元pathを保持した未保存のEditor bufferとして開くだけです。無題なら保存時にSave Asを求めます。元ファイルが保存基準から外部変更されていたり、見つからなかったりする場合は警告し、自動mergeや上書きを行いません。

Recoveryは復元直後も残し、Save／Save As／F5／F8の保存成功、またはClose／New／Openでの明示的な破棄・置換が完了した時に削除します。キャンセル時は保持します。複数Editorは同じ元pathでも独立したsnapshotを持ちます。壊れたRecoveryや読み書きの失敗はログで通知し、編集を続けられます。文書内容とlocal pathは**local user configだけ**に保存され、Git repositoryには保存されません。FTP接続情報やUndo履歴はRecoveryへ含めません。

### 内蔵エディター

Input欄の **Edit...／編集...** から `.tsv`・`.txt` を開けます。入力ファイルが未選択なら空のeditorが開きます。保存すると、そのpathがconverterのInput欄に反映されます。Fileメニューには New、Open、Save、Save As、Save & Convert、保存・変換してFTP送信、Validate、フレーム解析、Close があり、`Ctrl+N`、`Ctrl+O`、`Ctrl+S`、`Ctrl+Shift+S`、`F5`、`F6`、`F7`、`F8` も使えます。未保存の変更があるままNew・Open・Closeを選ぶと保存確認が出ます。

同じpathへの保存前には、disk内容をOpen／最後の保存時の内容とhashで比較します。Editor外で変更されていた場合は上書き、削除されていた場合は再作成を確認します。「いいえ」ならbuffer・Undo・Recoveryを保持し、F5／F8の変換やFTP送信も開始しません。内容を確認できない場合は保存せず、エラーを表示します。Recovery復元後も旧baselineを使って同じ保護を行います。別pathへのSave Asは元ファイルの外部変更に妨げられず、既存の保存先の上書き確認はファイルダイアログに従います。同じpathのSave Asには通常の保存と同じ保護を適用します。

**Save & Convert**（`F5`）はセル編集を確定して保存し、そのEditorで開いているファイルをConverterのInputとしてローカル変換します。親GUIのFTPチェックがONでも、FTP送信しません。新規ファイルはSave Asで保存先を指定し、キャンセルすれば変換しません。Save As後はInputが新しいpathへ切り替わります。Output Directory／Output File Nameが空欄ならファイルのフォルダー／拡張子を除いた名前を設定し、指定済みなら保持します。出力形式、空フレーム省略（nx-TASのみ）、DebugはConverterで現在選んでいる設定を使います。converterの標準出力・標準エラーは従来のログに表示され、変換失敗はダイアログでも通知されます。

**保存・変換してFTP送信／Save, Convert & Send**（`F8`）は同じ保存・Input同期・ローカル変換に加えて、FTP送信を行います。親GUIのFTPチェックがOFFでも送信し、現在入力されているIP／Port／Username／Passwordを使います。新規文書はSave Asが必要で、キャンセルすれば送信しません。FTP設定の保存に失敗した場合は変換開始前に停止し、新しい出力を生成しません。転送時の失敗ではローカル出力が既に生成されている場合があります。親GUIの **Start Conversion／変換実行** は従来どおりFTPチェックに従います。F5／F8はチェック状態を書き換えず、実行種別をログに表示します。

**Validate**（`F6`）は現在のセル編集を確定し、未保存のEditor内容を一時snapshotとして、現在選択中の出力形式で既存converterへ渡します。実ファイルは保存せず、無題の新規文書でもSave Asなしで検証できます。modified状態とUndo履歴も保持します。成功時は「エラーなし」、失敗時は下部のProblemsにconverterのメッセージをそのまま表示します。明示的な行番号があるメッセージをダブルクリックすると、その行へ移動します。行番号を特定できないエラーや、`.txt` から変換した中間TSVのエラーには推測でジャンプ先を付けません。検証中に内容を変更した場合は再検証を案内します。ValidateはConverterの出力設定を変更せず、FTP送信とDebug CSV生成も行いません。保存して通常の出力を作る場合は引き続き **Save & Convert** を使ってください。

上部右側には、選択中のTSV行の**開始／長さ／終了／全体**frameを表示します。開始・終了は0-basedのframe index、長さ・全体はframe個数です。例えば18fなら `開始: 0f | 長さ: 18f | 終了: 17f | 全体: 18f` です。表では選択範囲の上端～下端の行を集計し、単一行ならその行を表示します。テキストではcursor行が対象です。完全な空行（TABや空白だけの行を含む）もconverterでは既定の1fを消費します。A列が空でも他のcellに入力がある行も既定の1fです。編集後は約0.5秒の待機を挟んで、未保存の内容を一時TSVとして既存converterでbackground解析し、結果を自動更新します。保存やFTP送信は行いません。値はconverterが確定した行のdurationと総frame数に基づき、更新中・解析失敗時は未確定として表示します。選択範囲を変えるだけなら再解析せず、結果をすぐ切り替えます。`.txt` は対象外です。

Frame表示のすぐ横にある常設の**移動**欄へ0-basedのframe番号を入力し、Enterまたは**移動**で、そのframeを生成する元TSV行へ移動できます。`Ctrl+G` は入力欄へfocusし、EscapeはEditorへ戻ります。表では現在列を保持し、テキストでは行頭へ移動します。既存converterのcached source-line mapだけを使い、移動のための再解析は行いません。更新中・解析失敗時や対応する確定行がない場合は移動せず、入力欄の横に案内を表示します。セルの未確定編集は移動実行時に確定し、内容が変わった場合は自動解析の完了後に再度移動してください。`.txt`（nx-TAS）は対象外です。

詳細なDebug CSVを見る場合は、Fileメニューの**フレーム解析**（`F7`）から別ウィンドウのFrame Inspectorを開けます。この操作も無題を含む現在の未保存内容を一時snapshotとして解析し、既存converterでDebug CSVを一時生成します。実ファイルを保存せず、modified状態とUndo履歴を保持します。ConverterのDebugチェック状態や出力設定は変えず、FTP送信もしません。上部の**総フレーム数**はCSVの最大`Frame`番号＋1です。同じframeの1P／2P行を二重に数えません。一覧にはボタン、LS／RS、commandなどを表示し、行を選ぶと加速度・ジャイロを含むCSVの全項目を詳細欄で確認できます。frame番号を入力して**移動**できます。解析中に編集した場合は旧結果を適用せず、再解析を案内します。解析失敗時はProblemsにエラーを表示し、以前のInspector結果には旧結果である旨を表示します。現行Debug CSVには確実な元TSV行情報がないため、このInspectorではframeから元の行へのジャンプは行いません。

編集メニューにはUndo／Redo、Cut／Copy／Paste、Select Allがあります。ショートカットは `Ctrl+Z`／`Ctrl+Y`、`Ctrl+X`／`Ctrl+C`／`Ctrl+V`／`Ctrl+A` です。`Ctrl+F` で検索、`Ctrl+H` で置換を開けます。`F3`／`Shift+F3` で次／前を検索でき、ダイアログでは現在の一致箇所または全一致箇所を置換できます。検索は大文字小文字を区別します。行番号と、行・列・編集状態・ファイル種別（TSV-TAS／nx-TAS）を示すステータスバーも表示します。

`.tsv` と未保存の新規文書では **テキスト／表** を切り替えられます。表は各行を単純にTABで区切って表示し、空セル・空行・行末のTABも保持します。新規表にはA～G列を初期表示し、A「フレーム数」、B「LS」、C「RS」、D～G「ボタン」と案内します。これらは入力の目安で、列の意味を強制しません。H列以降も移動・貼り付け・列追加で使えます。セル境界、行番号、active cellと選択範囲の強調表示があります。単クリックは選択、Shift+クリックとドラッグは範囲選択です。選択中にASCII文字を打つと既存セルを置き換えて入力を開始します。F2／ダブルクリックなら既存値を保持して編集でき、編集中の左右キーやHome／Endは文字カーソルを動かします。候補popupが閉じている時、編集中のTab／Shift+Tabは確定して右／左、Enter／Shift+Enterは確定して下／上のセルを選択し、Escapeは変更を破棄します。選択中のTab／Shift+Tab／Enter／Shift+Enter／矢印キーはセル移動だけを行い、Shift+矢印キーで範囲を広げます。日本語IMEはF2／ダブルクリックで開く入力欄を使ってください。変更を加えず表示を切り替えるだけならファイル内容や編集状態は変わりません。`.txt`（nx-TAS）はテキスト表示のみです。Undo／Redo、保存、保存して変換は表での編集にも使えます。

表で範囲を選んだ状態の `Ctrl+C`／`Ctrl+X`／`Ctrl+V` は、TABと改行を使ってセル範囲をコピー・切り取り・貼り付けます。セル内の文字を編集中は通常の文字編集になり、TABまたは改行を含む貼り付けは表へ展開します。外部Spreadsheetからコピーした複数行・複数列も、選択範囲の左上から貼り付けられ、必要な行・列が増えます。Delete／Backspaceは選択セルを空にします。行番号または列名をクリックすると行・列全体、Shift+クリックで複数行・列を選択できます。セル・行番号・列名の右クリックメニューから切り取り／コピー／貼り付けや行・列操作ができ、**表**メニューにも行を上／下へ追加、行の複製・削除、列を左／右へ追加・削除があります。表の横の **+ 行**／**+ 列** は現在の行の下／列の右に追加します。複数行・列をヘッダーで選んで削除すると選択分をまとめて削除します。これらの表操作はそれぞれ1回のUndoで戻せます。

列ヘッダーの右端をドラッグすると、その列だけの幅を変更できます。境界から離れた位置をクリックすると従来どおり列を選択します。列幅はテキスト／表を切り替えても保持され、次回Editor起動時も復元します。列幅変更はファイル内容やUndo履歴に影響しません。

最終行でEnterまたは下矢印を押すと、未保存の仮想行へ移動できます。移動だけでは空行を追加しません。その行へ文字を入力して確定したとき、必要な行だけ追加します。TabやEnterで移動した後はセル選択状態のままで、次の文字をそのまま打ち込めます。表は画面の余白にも空セルを表示し、一度広げた表示範囲は別セルを選んでも残ります。表示上の空セルだけでは保存内容は増えません。

表のセルを編集中に `l` や `/` などを入力すると、ボタン、スティック、加速度／ジャイロ、2P入力、STAS commandなどの候補が表示されます。上下キーで候補を選び、Tab／Enterまたはクリックで挿入すると、セル編集を続けられます。Escapeはまず候補だけを閉じます。括弧や引数を含む候補は値を選択したtemplateとして入り、そのまま値を打ち替えられます。表の右側には **入力パレット** が常時表示され、よく使うボタン、左右スティック、STAS commandを選べます。選んだ項目は現在セルへ挿入され、編集中ならカーソル位置へ挿入されます。左右スティック候補はそれぞれ角度だけの形を先頭に表示します。`.tsv` のテキスト表示ではコメント・command・変数・入力を色で、表では先頭列をdurationの目安として薄い背景で区別し、行番号横の色で通常入力・コメント・command・変数・loop/control風・空行を見分けられます。commandやコメント行の先頭列をdurationとして扱いません。色や行分類は**入力支援**であり、構文の正否判定ではありません。STAS commandの実際の処理はSTAS出力時にconverterが行います。

入力パレットは2列表示です。上部の◀／▶で、Page 1 **Basic**（Buttons／Left Stick／Right Stick／STAS Commands）とPage 2 **Advanced**（Cappy／Accel／Gyro／Notation）を切り替えます。初回はPage 1で、次回は最後のページを復元します。切替は文書や選択範囲、Undo履歴に影響しません。各ページはパレット内のマウスホイールまたはスクロールバーで縦スクロールできます。左右スティックでは `ls(angle)`／`rs(angle)` が各カテゴリ最上段の大きなボタン、半径＋角度／XY形式が次段の左右に並びます。16種類のボタン候補にはコントローラーアイコンと文字を併記します。画像が読めない場合は文字だけで表示します。表示と挿入するTSV文字列は別に管理しています。

表はTSV-TAS構文を解釈せず、保存時の独自整形もしません。列操作はcommandやcommentを含むすべての行に適用されます。テキスト表示も含めてUTF-8と元の改行を可能な限り保持します。TSV-TASの解釈は引き続き `tsv-tas.py` が担当します。

### FTP設定

FTPを有効にするとIP、port、user、passwordの入力欄が表示されます。GUIはconverterと同じフォルダーの `ftp_config.json` に `ip`（文字列）、`port`（整数）、`user`（文字列）、`passwd`（文字列）を保存します。CLIで `-f` を使う場合も、このファイルを設定して**repositoryのルートから**実行してください。秘密情報が入るため、設定後のファイルをcommit・共有しないでください。FTPは選択した3形式のどれとも組み合わせられます。実機転送の成否はSwitch側の環境で確認してください。

## TSV-TASの基本書式

| 書式 | 例と意味 |
| --- | --- |
| duration | `5` は5フレーム。duration欄を空にすると1フレーム。`3` だけの行は3フレーム待機 |
| ボタン | `1<TAB>a<TAB>zl` はAとZLを同じ1フレームで入力。`a`、`b`、`x`、`y`、`zl`、`zr` などを使用 |
| スティック | `ls(90)` は左スティックを半径1、90度へ。`rs(0.5; 180)` は右スティックを半径0.5、180度へ。角度の単位は度 |
| 2P／Cappy | 例: `$is_two_player = true` を独立行に置き、`1<TAB>ca<TAB>cls(45)` で2P側のAと左スティックを入力。詳細と対象modの制限はDocumentationを参照 |
| ループ | `6<TAB>a/b` はA、Bを交互に6フレーム入力。`/` で同じセル内の入力を区切る |
| スティック補間 | `6<TAB>ls(0)->ls(50)` は6フレームで左スティックを0度から50度へ補間 |
| 式と変数 | `$angle = 90` を独立行に置き、`4<TAB>ls($angle + 45)` のように利用。加減乗除に対応 |
| コメント | duration欄を `//` で始めた行は実行しない。例: `// 説明` |

上の `<TAB>` は説明用の記号です。ファイル内では**実際のタブ文字**に置き換えてください。1行に複数の入力を書けます。スティックの座標指定、局所duration、sequence、motionやgyroなどは [Documentation](https://docs.google.com/document/d/1vW-swF3k96YxaIJqXbtRXbQ54mKKgeWfPFlW2hYBa_Q/edit?usp=sharing) を参照してください。

### STASのscript command（実験的）

commandはduration欄の先頭に `/` を付けて独立行に書きます。現在のconverterは**STAS出力時**に次のcommandを処理します。command行そのものは余分なlogical frameを追加しません。新しいcommandの引数は現在の `tsv-tas.py` に合わせています。

| command | 現在の実装での指定 |
| --- | --- |
| `/tp x y z`、`/ctp x y z` | Mario／Cappyの座標を指定。回転を含む形はDocumentationを参照 |
| `/absStick on`、`/absStick off` | absolute stickの有効／無効を指定 |
| `/speed 2` | speedを整数 **1～10** で指定 |
| `/pause` | pause commandを出力。引数なし |
| `/loadFile 1` | save-file IDを整数で指定してload commandを出力 |
| `/reloadFile` | reload commandを出力。引数なし |
| `/demo on`、`/demo off` | demo flagの有効／無効を指定 |

たとえば `1<TAB>a` の次に `/pause`、その次に `1<TAB>b` を書くと、2行目の入力開始時点にcommandが配置されます。`/absStick`、`/demo` の有効値として `true`、`1`、`on`、`y`、`yes` を受け付けます。commandのSwitch上での効果は対応するLunaKitで確認してください。

## nx-TASからTSV-TASへ

GUIでnx-TASの `.txt` を選ぶと、まず `nx-tas-to-tsv-tas.py` が保存先に同名の `.tsv` を作り、そのTSVを選択した形式へコンパイルします。TSVへの変換だけならCLIで次を実行します。

```text
python3 nx-tas-to-tsv-tas.py input.txt output.tsv
```

この逆変換はupstream由来で、すべてのnx-TAS要素の完全な往復変換は保証されません。元の `.txt` を出力で上書きしない名前・保存先を選んでください。

## CLI

repositoryのルートから実行します。outputは**ローカルファイルのpath**です。

```text
python3 tsv-tas.py input.tsv output
python3 tsv-tas.py -s input.tsv output.stas
python3 tsv-tas.py -ne input.tsv output.txt
python3 tsv-tas.py -fsd input.tsv output.stas
```

| option | 動作 |
| --- | --- |
| `-f` | `ftp_config.json` を使用して出力をFTP送信 |
| `-n` | nx-TASテキストを生成 |
| `-s` | STASを生成 |
| `-e` | nx-TASで空フレームを省略 |
| `-l` | Enter入力のたびに再生成（CLI専用） |
| `-d` | `<output>-debug.csv` を生成 |
| `-m` | このGUI fork専用。`<output>-lines.csv` にconverterが確定したsource行のframe位置を出力（Editorの自動表示で使用） |

optionは `-ne` のように1つのハイフンの後へまとめます。`-n` と `-s` は別々の出力形式なので、同時に指定しないでください。`-e` は `-n` と組み合わせてください。

## Windows exeの作成と配置

WindowsでPython 3とPyInstallerを用意し、repositoryのルートで実行します。

```text
python -m pip install pyinstaller
python -m PyInstaller --noconsole --onefile --add-data "assets/icons/png:assets/icons/png" python_to_exe/main_jp.py
python -m PyInstaller --noconsole --onefile --add-data "assets/icons/png:assets/icons/png" python_to_exe/main_en.py
```

できた `dist/main_jp.exe` または `dist/main_en.exe` を、`tsv-tas.py`、`nx-tas-to-tsv-tas.py`、`ftp_config.json` と**同じフォルダー**へ置きます。exeはGUIとPNGアイコンを内包し、converterは同じフォルダーの `.py` を起動します。Windowsでは `py -3`、次にPATH上のPythonを探すため、利用時にもPython 3をインストールしてください。pathに空白があってもGUIは引数を分けて渡します。

## repository構成とupstreamとの差分

| path | 役割 |
| --- | --- |
| `tsv-tas.py` | `stas-dev` ベースのTSV-TAS converter。GUI固有のFTP変更ではremote名にローカルpathのbasenameだけを使用 |
| `nx-tas-to-tsv-tas.py` | upstreamと同じnx-TAS→TSV-TAS converter |
| `python_to_exe/main_jp.py`、`main_en.py` | 日本語／Englishの起動スクリプト |
| `python_to_exe/converter_gui.py`、`converter_logic.py` | 共通GUI、引数生成、Python探索、FTP設定 |
| `python_to_exe/app_settings.py` | user config内の非機密設定と共有Recent Files履歴 |
| `python_to_exe/editor/` | テキスト／表の編集画面、ファイル状態、検索・置換、入力支援、Validation、Debug CSV解析とFrame Inspector |
| `python_to_exe/editor/recovery.py` | user config内の文書別Recovery snapshot、復元、元ファイルの変更検出 |
| `ftp_config.json` | FTP接続設定。実credentialをcommitしないこと |
| `tests/test_conversion.py` | ローカル変換とGUI引数のテスト |

GUI固有機能はファイル選択、3形式の選択、Debug・FTP・空フレーム省略の切り替え、日英表示、ログ表示、PyInstaller起動です。scriptの構文、motion、gyro、STASの生成はupstream converterに委ねています。

## 注意事項・既知の制限

- GUIは `.txt` をnx-TAS入力として扱います。タブ区切りのTSV-TASを `.txt` で保存した場合は `.tsv` に改名するかCLIで直接変換してください。
- upstream compilerは `.csv` 拡張子を認識しますが、現在の行解析はタブで分割するためCSV入力は信頼できません。GUIは `.csv` を選択対象にしていません。
- `-e` はnx-TAS専用です。STAS commandは実験的で、対象modでの動作確認が必要です。
- GUI exeのWindows実行と実機FTP転送は利用環境で確認してください。READMEの例はローカルconverterで確認しています。
