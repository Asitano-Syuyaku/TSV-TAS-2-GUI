# Dopagaki3 Design Specification — 「1F FEVER」

- branch: `dopagaki3`（base: `main` `e35c3e4`。作成時点で `main` と同一）
- design authority: Claude Opus 5.5
- 最優先 guidance: `.claude/skills/dopagaki-ui/`（`SKILL.md`、`references/patterns.md`、`references/styles.md`、`assets/dopa-juice.js`）
- 本書は設計仕様のみ。UI実装はまだ行わない。
- 旧dopagaki / dopagaki2、他modelの案、過去のdesign documentは一切参照していない。通常版 `main` の現行Editorだけを調査対象とした。

---

## 0. 一言で

**TASを作るのは、1フレームを積み上げる作業である。だから1フレームを積むたびに、Editorが祭りで返す。**

ドパガキ仕様の対象はTAS作者（大人）であり、手加減しない。暗い作業台の上に、ネオン・警告テープ・叩きつけ文字・パチンコ構造の確定演出を載せる。ただし、Editorが扱う**データ**（frame位置・stick値・変換結果）は、1ピクセルも1フレームも偽らない。演出は常に「事実が確定したこと」を祝うだけで、事実を先取りしたり、盛ったりしない。

> 演出は嘘をつかない。だから全力で祝ってよい。

---

## 1. 調査した主要箇所（`main` の現行Editor）

| 箇所 | 内容 | 設計への意味 |
|---|---|---|
| `python_to_exe/converter_gui.py` `TASConverterApp` | 親のConverter画面（Tk root、固定サイズ、素のTk widget）。変換は`threading`＋`SimpleQueue`、`_drain_events`が`log`/`success`/`error`/`validation`/`analysis`/`done`を処理 | F5/F8の**真の結果**は親の`_drain_events`にしか届かない |
| 同 `_convert_editor_file` → `start_conversion(ftp_override)` | Editorには「開始できたか」（bool）しか返らない。成功は`messagebox.showinfo`、失敗は`showerror`、詳細はlog | 結果演出には、Editorへ結果を届ける**新しいhook**が必要（§10） |
| 同 `convert()` | converterのstdoutはlogに流すだけで、結果には含めない | F8の「送信確定」はstdoutから判定する必要がある（§9.4） |
| `tsv-tas.py` L1859–1877 | FTP: 接続・login失敗は例外で非0終了。ただし`STOR`の応答が`"226 OK"`以外の場合は`print("FTP error")`して**終了コード0** | 「終了コード0 = 送信成功」ではない。送信の成否は3値で扱う |
| `editor/window.py` `EditorWindow` | menu / view_bar（Raw・Table切替、Validate、+行/+列、Frame表示、Go to）/ 本体（Raw: `tk.Text`＋行番号Canvas、Table: `TableGrid`＋入力パレット400px）/ status / Problems | 画面構成の土台 |
| 同 `_position_unavailable_message` / `_update_frame_info` / `_update_stick_preview` | Frame表示とStick Previewの状態（確定 / 更新中 / 未確定 / TSV-TASのみ）を一か所で決める。編集中・debounce中・worker実行中・key不一致なら「更新中」 | **溜め（更新中）→確定**という真の状態遷移が既にある。演出はこれに乗る |
| 同 `_position_document_changed` → 500ms debounce → `analyze_positions(-m -d)` → `_poll_position_analysis` | background解析。revisionが一致した時だけ結果を採用する | 「解析確定」の唯一の発火点 |
| `editor/grid.py` `TableGrid` | Canvasを毎回描き直す（tag `"grid"`だけ削除、約3ms）。編集はセル1つ分の`tk.Entry`、補完は`tk.Listbox` | FX用のitemは別tag `"fx"`で共存できる。描画頻度の予算に注意 |
| 同 `_type_to_edit` / `begin_edit` / `_bind_entry_navigation` | ASCIIはすぐに編集開始。IMEはF2/ダブルクリックで開くEntryを使う。Tab/Enterの扱いは補完popupの開閉で変わる | FXはfocusを動かさず、Entryに触れず、key eventを奪わない |
| 同 `_apply_editor_value` / `_apply_model` | セル確定と表操作は`on_change`/`on_transform`経由で`tk.Text`のundo stackと同期する | 中心の1動作（セル確定）を検出する場所 |
| `editor/stick_preview.py` | 1PのLS/RSを単位円で描く。現在点と1〜3f前（実在するframeだけ）。`show()`はkeyで重複描画を抑える | 点は補間・tweenしない |
| `editor/frame_inspector.py` | 別Toplevel。theme未使用で色を直接指定 | skinの対象 |
| `editor/theme.py` | Editor専用のtoken（`COLORS`/`SPACING`/`SIZES`/`SYNTAX_COLORS`/`ROW_HINTS`/`TRAIL_COLORS`）。import時にtkinterを読まない | ネオンtokenに置き換える |
| `editor/tsv_syntax.py` | 補完候補、パレットのページ構成、行・セルの分類（入力支援のみ） | 色分けの意味はそのまま維持 |
| `app_settings.py` | `settings.json`（version 1）。`_clean`で厳密に検証 | ドパ設定を追加する場所 |
| `assets/icons/source/*.svg` | 24pxの単色線画（stroke `#202020`） | 暗い背景用のlight variantが必要 |
| `tests/`（309件、全て成功） | パレット幅400px、`frame_status`の文言、`_problems_title`の文言、`stick_preview.status`、色は`#rrggbb`、`theme`のimportでtkinterを読まない、など | 既存のwidgetとtextは**データ契約**として残す |
| 環境 | Python 3.12 / Tk 8.6。音は`bell()`のみ。commercial audioなし | 音は合成で作る（§13） |

---

## 2. Truth Contract（演出の憲法）

hard constraintsを、実装者が迷わない規則に落とす。**この章は他のどの演出判断よりも優先する。**

| # | 規則 | 具体例 |
|---|---|---|
| T1 | **データは回さない。叩きつける。** frame位置・stick値・総frame数などconverter由来の値は、確定値を即座に表示する。count-up・補間・tweenはしない | Start/Len/End/Totalは新しい値に一瞬で切り替わり、文字の大きさの punch だけで強調する。stickの点は新しい位置に瞬間移動し、輪だけが広がる |
| T2 | **確定していない値を確定の見た目で出さない。** 更新中は数字を消し、「解析中」の表示にする。古い値を確定色で残さない | 更新中は`- - -`＋点滅lamp。古い値を薄く残すこともしない |
| T3 | **祝うのは事実の後。** 成功演出は、§9の表にある真の発火点からしか出さない。「開始」や「押した」は成功ではない | F8を押した時点では「実行中」まで。「転送確定!!」は送信成功の行がstdoutに出た後だけ |
| T4 | **事実の文言は変えない。** converterのメッセージ、ダイアログ、Problemsの本文、`frame_status`・`_problems_title`・`stick_preview.status`のtextは現行のまま。ドパガキの言葉は**別のwidget・別のcanvas item**に出す | 「おしい!」は飾りのcanvas文字。Problems本文はconverterの出力そのまま |
| T5 | **演出は入力を奪わない。** `focus_set`・`grab`・modal・`"break"`をFXから行わない。コマンドの実行を遅らせない。大演出は任意のkey/clickで即座に閉じ、そのkeyは本来の宛先にそのまま届く | IMEの変換中にFXが走っても、Entryには一切触れない |
| T6 | **ゲームの数字は文書の外。** DOPA・HEAT・COMBO・ROUNDはsession内のメモリだけに置く。文書・Undo・Recovery・settingsには入れない（settingsには演出の好みだけを保存する） | — |
| T7 | **失敗は隠さない。** 失敗時に成功演出を出さない。既存のエラーダイアログ・log・Problemsは現行どおり、同じタイミングで出す | — |
| T8 | **converter/parser/document semanticsに触れない。** `tsv-tas.py`、`nx-tas-to-tsv-tas.py`、command builder、`EditorDocument`、`TableModel`の意味は変えない | stdoutは**読むだけ** |
| T9 | **結果の表示を演出で遅らせない。** 真の結果が出たら、その瞬間に事実（ダイアログ・log・結果カードの文言）を出す。演出はその周りで並行して流す | 親の`messagebox`は今と同じタイミング。FXはその背後で動く（Tkのnested event loop中も`after`は動く） |

---

## 3. Design direction

### 3.1 コンセプト：「1F FEVER」

- **中心の1動作は「セル確定」。** TAS作者が何千回も繰り返す行為は、durationと入力をセルに打って、Tab/Enterで確定すること。ドパガキ化の9割はこの1動作への返しで決まる（skill §3-1）。
- **真の溜め→確定がもう存在する。** 編集すると500msのdebounceの後にconverterが走り、Frame位置が確定する。この「更新中→確定」を、パチンコの「溜め→確定」としてそのまま見せる。**演出のための偽の待ち時間はゼロ**で、Editorに元からある待ちを祭りに変える。
- **大きな山はF5とF8。** 1ラウンド（保存と保存の間の編集）の締めとして、F5は中くらいの山、F8（実機へ送信）は唯一のフルパチンコ構造にする。山は最大で3つ（F5 / F8 / Validateノーミス）。全部を確定演出にしない。

### 3.2 スタイル

skillの4スタイルから、**B. ネオン・タイムライン**を地に、**C. 静→爆**の構造をF8に使う。

- **本物のUIは暗いまま残す**（B）。TAS作業は長時間で、セルの文字は常に読めなければならない。地は黒に近い紫、データはニュートラルな白、ネオンは**状態と報酬**だけに使う。
- **F8だけは落差で見せる**（C）。実行中は暗転して光の玉が1つ脈打つ（＝実際に転送を待っている時間）。成功が確定した瞬間に虹の放射線が爆発する。
- **ピクセル・キャンディ系は採らない。** 対象は大人のTAS作者で、題材はフレーム単位の精密作業。かわいさより「計器・照準・ロックオン」の気持ちよさを優先する。

### 3.3 3つの層

| 層 | 役割 | 常時の動き |
|---|---|---|
| **WORK**（表・テキスト・パレット・Stick Preview） | 中身。常に読める | なし（返しの粒子だけ） |
| **HUD**（上部のFEVER BAR） | 計器（FRAME METER）と報酬（HEAT/COMBO/DOPA/叫び文字） | 解析中のlamp、高HEAT時の警告テープ |
| **COVER**（F8のときだけ本体を覆う） | 大きな山 | 結果が出るまで／任意の入力で即終了 |

叫び文字は**HUDの中**で叩きつける。表のセルの上には出さない（中身を殺さない、skill 原則9）。

---

## 4. Visual system

### 4.1 色（`theme.py`の`COLORS`を全面的に置き換える）

地は「VOID」、データはニュートラル、ネオンは意味を固定して使う。

| token | 値 | 用途 |
|---|---|---|
| `app_background` | `#07060D` | window地（VOID） |
| `panel_background` | `#0F0D1A` | パレット・HUD・status・Problems |
| `secondary_background` | `#1C1832` | toolbar button・行番号gutter・header |
| `cell_background`（新） | `#141124` | 表のセル・テキスト地 |
| `virtual_cell`（新） | `#0C0B16` | 文書外の仮想行・仮想列（保存されない空セル）。実データとの区別を見えるようにする |
| `border` | `#3A3260` | 強い境界 |
| `subtle_border` | `#2A2445` | grid線 |
| `text` | `#F2EEFF` | 本文（セル上 16.2:1） |
| `muted_text` | `#9A92BF` | 補助（セル上 6.4:1） |
| `accent` | `#19D3F0` | **CYAN**：選択・focus・LS・リンク |
| `accent_hover` | `#5FE3F6` | — |
| `selection_background` | `#182C40` | 範囲選択 |
| `active_cell` | `#10364A` | active cell |
| `active_selection_outline` | `#19D3F0` | — |
| `header_background` | `#1C1832` | — |
| `header_selected` | `#2C2352` | — |
| `duration_background` | `#191530` | A列（duration）の地 |
| `neon_yellow`（新） | `#FFE600` | **YELLOW**：確定したframeデータ・ロックオン・DOPA・F5 |
| `neon_magenta`（新） | `#FF2D8A` | **MAGENTA**：HEAT・COMBO・RS・F8 |
| `neon_green`（新） | `#39FF14` | **GREEN**：確定lamp・成功 |
| `neon_purple`（新） | `#A35BFF` | STAS command |
| `neon_orange`（新） | `#FF8A1F` | **おしい**・注意 |
| `success` | `#39FF14` | — |
| `warning` | `#FF8A1F` | — |
| `error` | `#FF5C7A` | 事実としてのエラー（セル上 6.2:1）。全面の赤点滅には使わない |
| `palette_button` | `#1C1832` | — |
| `palette_hover` | `#2C2352` | — |
| `palette_text` | `#F2EEFF` | — |
| `preview_axis` | `#2A2445` | — |
| `preview_circle` | `#3A3260` | 単位円（ネオンの輪は別に重ねる） |
| `preview_center` | `#9A92BF` | — |

- **ネオン文字の背景は暗い地に限る。** magenta/purpleは本文には使わず、装飾・太字の短いラベルに限定する（4.5:1前後のため）。
- **ネオン地のボタンには暗い文字**を載せる（`#0B0A12` on yellow 15.5:1、on magenta 5.6:1）。
- テストの条件（必須token・`#rrggbb`・`app_background≠panel_background`）は満たす。

**SYNTAX_COLORS（テキスト／表の文字色）**

| kind | 値 | 意図 |
|---|---|---|
| `duration` | `#FFE600` | durationはTASの心臓。確定データと同じ黄 |
| `input` | `#8FE9FF` | 入力は淡いcyan |
| `command` | `#C69BFF` | STAS commandは紫 |
| `variable` | `#FFB547` | 変数は琥珀 |
| `comment` | `#7FC29B` | コメントは落ち着いた緑 |

**ROW_HINTS（行番号横の4pxバー）**：`input #19D3F0` / `control #FF2D8A` / `command #A35BFF` / `variable #FF8A1F` / `comment #3FAF6F` / `blank #2A2445`

**Stick色**：LS = CYAN、RS = MAGENTA。軌跡は地に向かって沈む4段階。
- LS：`#19D3F0`, `#138FA6`, `#0E5F70`, `#0A3A45`
- RS：`#FF2D8A`, `#B42263`, `#771843`, `#451029`

**HEAT ramp**（ゲージと縁の発光）：E 0→1で `#19D3F0` → `#A35BFF` → `#FF2D8A` → `#FF8A1F` → `#FFE600`。EXTRAでは虹色が循環する。

### 4.2 文字

Tkでは外部fontを読み込まない（同梱もしない）。起動時に`tkfont.families()`から最初に見つかったfamilyを使う。

| role | 候補（先頭から） | 用途 |
|---|---|---|
| `ui` | 現行の`TkDefaultFont` copies | ボタン・ラベル（OSの日本語fallbackを維持） |
| `mono` | `TkFixedFont`（現行） | 表・テキスト・Problems。**変えない**（列の揃いとIME） |
| `meter` | `Bahnschrift` → `Consolas` → `DejaVu Sans Mono` → `TkFixedFont` | FRAME METERの数字。Bold、22px |
| `shout` | `Yu Gothic UI` → `Meiryo` → `Noto Sans CJK JP` → `IPAGothic` → `TkDefaultFont` | 叫び文字。Bold |
| `caps` | `Bahnschrift` → `Segoe UI` → `DejaVu Sans` | `START` `HEAT`などの小さな英字ラベル。8px、字間は空白で広げる |

**縁取り文字**：Tkのcanvas textにはstrokeがないため、輪郭色（`#0B0A12`）の文字を8方向へ±2pxずらして描き、その上に本体を重ね、さらに右下(+3,+3)にずれた影を置く（skill §5の「太い縁取り＋ずらした影」）。1文字列あたり10 item。canvas textの`angle`（Tk 8.6）で−4〜−10°傾ける。

叫び文字のサイズは事前に作ったfont（6段）から選ぶ。animationの途中でfontを作らない。

### 4.3 形

- **ロックオン・ブラケット**：active cellの四隅に、黄色のL字（各6px、太さ2px）。HUD枠の四隅にも同じ形を置く（skill Bの「四隅のL字ブラケット」）。
- **警告テープ**：黄×黒の斜線帯。中に`1F ✦ FEVER ✦ TAS ✦`の単語を流す。HEATが上がった時のHUDと、F8のCOVERだけで使う。
- **RIM**：本体（表／テキスト＋パレット）を囲む2pxの縁。色はHEAT rampに従い、山場で光る（全画面フラッシュの代わり、§12）。
- 角丸は使わない（Tkでは汚くなる）。直線と斜め45°で揃える。

### 4.4 アイコン

現行のPNGは`#202020`の線画なので、暗い地では見えない。`assets/icons/render_png.py`に`--stroke`と`--output-dir`を指定して、`#F2EEFF`の線のvariantを**`assets/icons/png/neon/`**へ生成し、commitする（SVGは自前の原本なので問題ない）。

- 置き場所を`png/`の下にしたのは、既存のPyInstaller `--add-data "assets/icons/png:assets/icons/png"`がそのまま同梱するため。READMEのbuild手順は変えない。
- `palette_icon_path(key)`は現行のまま元のPNGを返す。Editorは`neon_icon_path(palette_icon_path(key))`で`neon/`の同名ファイルを読む。
- neonが無い・読めない場合は**文字だけの表示**にする。元の暗いPNGへはfallbackしない（暗い地では読めないため）。

再生成：`python assets/icons/render_png.py --stroke "#F2EEFF" --output-dir assets/icons/png/neon`

---

## 5. 画面構成

### 5.1 Editor全体（Table表示）

```
┌ File Edit Search Table ドパ ───────────────────────────────────────────── (native menu)
├ COMMAND DECK ───────────────────────────────────────────────────────────────────────
│ [テキスト|表]  [+行][+列]   [検証 F6][解析 F7]          [保存して変換 F5][変換してSEND F8]
├ FEVER HUD (Canvas 76px) ─────────────────────────────────────────────────────────────
│┏●LOCKED━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓          ┏ HEAT ▰▰▰▰▰▰▱▱▱▱  R2 · EX1 ┓
│┃ START   LEN    END    TOTAL         ┃  ナイス!  ┃ 12 COMBO ×1.60             ┃
│┃  120f   18f   137f   4,212f  1:10.20┃  (叫び)   ┃       38,420 DOPA          ┃
│┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛ GO▶[____][移動]┗━━━━━━━━━━━━━━━━━━━━━━━━━━┛
├ RIM ─────────────────────────────────────────────────────────────────────────────────
│ ┌───┬────────────┬────────┬────────┬─────┐  ┌ 入力パレット ◀ 1/2 ▶ ─────┐
│ │   │A·フレーム数│B·LS    │C·RS    │D·ボタン│ │▌ボタン                   │
│ │ 1▌│ 5          │ls(90)  │        │     │  │ [Ⓐ A ] [Ⓑ B ]            │
│ │ 2▌│ 1        ⌜ │rs(0)  ⌝│ a      │     │  │ ...                      │
│ │ 3▌│ 3        ⌞ │       ⌟│        │     │  │▌スティックプレビュー (1P) │
│ │ … │(仮想行は更に暗い)                 │  │  (LS cyan)   (RS magenta) │
│ └───┴────────────┴────────┴────────┴─────┘  └──────────────────────────┘
├ Problems（必要な時だけ）─────────────────────────────────────────────────────────
├ STATUS  行 2, 列 3 | ● 編集済み | TSV-TAS                 [演出 100%] [♪ ON] ─────────
```

- **COMMAND DECK**（`tk.Frame`、高さ約36px、`panel_background`）
  - 左：`テキスト|表`のsegmented（選択中はcyan地に暗い文字）、`+行` `+列`（Table時のみ、現行どおり）。
  - 中：`検証 F6` `解析 F7`（secondary）。
  - 右：**`保存して変換 F5`**（黄地・暗い文字）と**`変換してSEND F8`**（magenta地・暗い文字、一番大きい）。既存のmenu/shortcutと同じcommandを呼ぶだけの**入口の追加**で、機能は変えない。F5/F8はこのEditorのラウンドを締める動作なので、画面上で一番目立つ位置に置く。
  - **幅が足りない時**（最小幅800pxの英語など）：F8→F5の順に先にpackし、狭い時に削られるのは左のグループにする。全ラベルの必要幅を下回ったら**compact表記**へ切り替える（F6/F7/F5/F8のショートカット表記を外す：`検証` `解析` `保存して変換` `変換してSEND` / `Validate` `Analyze` `Save & Convert` `Convert & SEND`）。同時にグループ間の余白を詰め、F8の内側余白も詰める。F8は常に一番大きいまま。
- **FEVER HUD**（`tk.Canvas`、高さ76px、§6）
  - **P1の暫定形**：HUDはまだcanvasではなく1行の`tk.Frame`。`frame_status`（現行の文言のまま、frame_info font）と`移動`欄を左から並べる。**converterが確定した値の時だけ文字をYELLOW**にし、更新中・未確定・TSV-TASのみの時はmutedにする（T2）。P2でFRAME METERに置き換え、Labelは§5.2のとおり小さな読み出しになる。
- **RIM**：本体を包む`tk.Frame`（`highlightthickness=2`）
- **本体**：現行どおり。Tableは左、パレットは右（幅400pxは固定、テストあり）
- **STATUS**：現行のlabel textはそのまま。右端に`[演出 100%]` `[♪ ON]`のチップ（クリックで切替、§12）

Raw表示でも同じ構成（本体が`tk.Text`＋gutterになり、パレットは現行どおり非表示）。

### 5.2 既存widgetの扱い（データ契約）

| 既存 | Dopagaki3での扱い |
|---|---|
| `view_bar`内の`frame_status`（Label） | **textは現行の計算・文言のまま毎回更新する**（テスト・データ契約）。表示は**FRAME METER**（canvas）が担い、Label自体はHUDの下端に1行の小さな読み出しとして残す（コピーできる平文。見た目はmuted、mono、8px相当）。METERとLabelは**同じ構造化データ**から描く。Labelの文字列をparseしない |
| `frame_entry` / `frame_go_button` / `_frame_jump_feedback` | 同じwidgetを、HUDのMETER右下の`GO▶`の位置に配置する（`create_window`ではなく、HUDの右に並ぶ実widget）。Ctrl+G・Escape・Enterの挙動は現行どおり。feedbackの文言も現行どおり（orange） |
| `_raw_button` / `_table_button` / Validate | COMMAND DECKへ移す（同じcommand） |
| `table_tools`（+行/+列） | COMMAND DECKへ移す（Table時だけ表示） |
| `status` | 現行のtextのまま。地と文字色だけ変える |
| `_problems_panel` / `_problems_title` / `_problems_text` | textは現行どおり。飾りは別widget（§8.6） |
| `input_palette`（幅400px） | 構造はそのまま、skinだけ変える |
| `stick_preview`（`status`・`samples`・`show()`） | APIとtextはそのまま、描画だけ変える |

---

## 6. FEVER HUD

HUDは「計器」と「報酬」を左右に分ける。**左がデータ（嘘をつかない）、右がゲーム（盛ってよい）。** この左右の分離そのものが、Truth Contractを目に見えるようにしている。

### 6.0 HUDの構造（P2で確定）

- HUDの左列：**METER canvas**（幅470px〜、高さ54px。値が非常に長い時だけ広がる）の下に、`frame_status`の小さなmutedの読み出しと`移動`欄を1行で並べる。
- HUDの右：**REWARD canvas**（残りの幅、高さ76px）。SHOUT ZONE・HEAT・COMBO・DOPA・背景のrays/テープはすべてここだけに描く。
- **shake・背景のmotionはREWARD canvasだけ**。METERはデータなので、揺らさず、背景も持たない（Truth Contractを見た目にも分ける）。
- METERの`START` `LEN` `END` `TOTAL`は日英とも英字caps（計器の見た目）。値は3桁区切り。

### 6.1 FRAME METER（左・データ）

```
●LOCKED                                         ←lamp＋状態語
START    LEN     END     TOTAL
 120f    18f    137f    4,212f   ≈1:10.20 @60fps
```

- 4つの欄。英字のcapsラベル（muted、8px）と、数字（`meter` font 22px、YELLOW）、単位`f`（muted、12px）。
- `≈1:10.20 @60fps`はTOTALを60で割った**換算値**で、小さくmutedで添える（SMOは60fps。換算であることを明記する）。
- 範囲選択時は現行の`for_range`の結果を同じ4欄に出す。値が無い欄は`—`。

**状態**（`_position_unavailable_message`と1対1）

| 状態 | lamp | 数字 | 動き |
|---|---|---|---|
| 確定 | GREEN `●LOCKED` / `●確定` | YELLOWで表示 | 確定した瞬間にpunch（§7.2） |
| 更新中 | YELLOWが600ms周期で脈打つ `◐解析中` | **全欄を`- - -`（muted）にする。古い値は残さない（T2）** | lampの脈動だけ。motion 0%では静止 |
| 未確定（解析失敗） | ORANGE `○未確定` | `- - -` | なし |
| `.txt` | GREY `○TSV-TASのみ` | 非表示 | なし |

### 6.2 REWARD（右・ゲーム）

- **HEAT**：10セグメントのバー。点灯しているセグメントの色はHEAT rampに従う。横に`R2`（ラウンド）と`EX1`（EXTRA段）。
- **COMBO**：`12 COMBO ×1.60`。combo 2以上で表示し、comboが切れたらfadeで消す。
- **DOPA**：`38,420 DOPA`（YELLOW、大）。**これはゲームの数字なのでcount-upしてよい**（T1の対象外）。JAは`Dopa.fmt`と同じく万/億、ENはK/M。
- **SHOUT ZONE**：METERとREWARDの間。叫び文字はここに叩きつける（§7.4）。

### 6.3 HUDの背景

| E | 背景 |
|---|---|
| <0.4 | 無地（`panel_background`）＋四隅のブラケット |
| 0.4〜 | 中央からごく淡い放射線（24本、`#151225`/`#120F20`の交互）。40秒で1周 |
| 0.6〜 | 上下の縁に細い警告テープ（高さ6px）が流れる。速さはEに比例 |
| 0.8〜 | 放射線がネオン色の淡いtint（地との差が小さい明度）になり、20秒で1周 |
| 1.0 / EX | `FEVER`の帯：テープの単語が`1F FEVER ✦ EX n ✦`になる |

放射線とテープは**HUDの中だけ**に描き、WORK層には出さない。

---

## 7. 中心の1動作：セル確定のカスケード

### 7.1 何を「確定」と数えるか

**「productive action」＝文書を実際に変えた操作。** 文書が変わらない移動は数えない（褒め言葉の価値を守るため）。

| 操作 | 数えるか | 検出点 |
|---|---|---|
| セル確定（Tab/Enter/Shift+…/クリックで値が変わった） | ✔ | `TableGrid._apply_editor_value`で`on_change`が成功した時 |
| パレットから挿入して確定 | ✔（上と同じ経路） | 同上 |
| 貼り付け・消去・行/列の追加・削除・複製 | ✔ | `_apply_model`で`on_transform`が成功した時 |
| Raw表示で、内容のある行を確定してReturn | ✔ | `tk.Text`の`<Return>`の後、直前の行が空でなく、文書が変わった時 |
| Undo/Redo | ✘（`REWIND`の小さな演出だけ） | `window.undo/redo`の成功時 |
| 選択の移動だけ | ✘ | — |

### 7.2 タイムライン（Table、E≈0.5の例）

| 時刻 | WORK層（表canvasの`"fx"` item） | HUD | 音 |
|---|---|---|---|
| 0ms | 既存の確定処理が終わった**同じtick**で、確定したセルに**PUNCH枠**を出す（黄3px、セル枠の1.18倍） | COMBOの数字がpunch（大きいfontから通常へ） | `pip`（comboに応じた音程） |
| 0〜120ms | PUNCH枠がセル枠まで縮み、黄→cyan→地の色へ沈む | DOPAのcount-upが始まる（300ms） | — |
| 0〜240ms | **SPARK**：セルの移動方向の辺から火花（Tabなら右、Enterなら下、Shift系なら逆）。本数は`6 + 14E`。移動方向を粒子で示す | — | — |
| 30〜630ms | `+N`（Nは加算したDOPA）がセル右上から28px上へ浮かんで消える | — | — |
| 0〜90ms | 移動先の新しいactive cellに、ロックオン・ブラケットが1.4倍から1倍へ吸い付く | — | — |
| combo節目 | — | 叫び文字（§7.4） | `shout` |
| 確定後500ms〜（真の解析完了時） | — | METER：lampがGREENに、数字が**新しい値で一度に出現**し、`meter` fontの大きいサイズ→通常へ100msでpunch。TOTALの右に`Δ+12f`／`Δ−3f`のpopが浮かぶ（**直前の確定値と新しい確定値の、両方が確定している時だけ**） | `lock` |
| 同時 | Stick Previewの現在点に輪が広がる（§8.4） | — | — |

- **Eが上がると種類が増える**（skill §2）：
  - E≥0.2：PUNCHに加えて輪（ring）。
  - E≥0.6：SPARKに星形が混ざる。
  - E≥0.8：確定のたびにセル上方へ小さな紙吹雪。
  - E≥1.0：PUNCH枠が虹色に循環する。
- **Raw表示**：WORK層はgutterだけを使う。確定した行の行番号が黄→muted へ沈み、gutterの右端から小さな火花が出る。HUDの反応はTableと同じ。数えるのは「Returnで**実際に改行が入り**、直前の行が空でない時」だけ（IMEの確定Returnなど、改行が入らないReturnは数えない）。
- **効果の座標**：表canvasの効果はcanvas座標に置くので、scrollに追従する。表の再描画後は`"fx"`を最前面に上げる（一度でも効果を描いた表だけ）。embedded widget（編集Entry・補完popup）は常にその上にある。
- **編集中（Entryが開いている間）はWORK層を静かにする。** キーごとの演出は出さず、確定の瞬間にまとめて返す。打鍵中の画面は落ち着かせる（skill 原則6の溜め）。

### 7.3 数字（DOPA・COMBO・HEAT）

```
COMBO：前の productive action から 3.0秒以内なら +1。超えたら 0（表示だけ fade out）
mult  = 1 + 0.05 × min(COMBO, 60)            # ×1.00 〜 ×4.00
gain  = round(10 × mult × (1 + 2E) × (1 + 0.5 × EXtier))
DOPA += gain                                  # +N のpopに出す値
HEAT：i = このラウンドの productive action 数、N = 30
      E = 0.08 + 0.92 × (min(i, N−1)/(N−1))^1.3      # skill の Dopa.E
      i ≥ N なら EXTRA：k = i − N、E = 1 + min(0.5, floor(k/10) × 0.1)
      （Editorは1動作が細かいため、skillの3問ごとではなく10確定ごとにEXを1段上げる）
ROUND：F5/F8の成功（§9の真の発火点）で精算 → ROUND+1、i=0
```

- **HEATはラウンド中は下がらない**（ラチェット）。失敗しても、Undoしても下がらない。
- ラウンドの精算はF5/F8の山の中で行う：`ROUND BONUS +3,200`がcount-upされ、HEATゲージが中央へ吸い込まれて空になる。落差は山の爆発で隠れ、次のラウンドは静かに始まる（メリハリ）。
- **新規／開く**：ラウンドをリセットする（DOPAは残す）。
- **節目スタンプ**（sessionで各1回、**確定したTOTALだけ**で判定）：
  - `1000F突破!!`（1,000f）
  - `1分突破!!`（3,600f、`@60fps`を小さく添える）
  - `5分突破!!`（18,000f）
  - `1万F突破!!`（10,000f）
  - `10万F突破!!`（100,000f）
  - HUDでtier 3の叫び文字＋コインの粒子（Table表示なら表canvasの上端から、Rawなら REWARD canvas）＋`stamp`音（P4）。
  - **基準値**：New/Open後の最初の確定TOTALは基準になるだけで、スタンプも`Δf`も出さない（長いscriptを開くことは達成ではない）。一度に複数を越えたら一番大きいものだけを出す。
- **`Δf`の色**：増加はGREEN、減少はCYAN（減少も失敗ではない）。
- **表の構造編集**（貼り付け・消去・行/列の追加削除）：選択範囲の**見えている部分**にPUNCH、active cellに`+N`。

### 7.4 叫び文字（HUDのSHOUT ZONE）

comboの節目でだけ出す。毎回は出さない。

| combo | tier | JA | EN |
|---|---|---|---|
| 5 | 0 | `ナイス!` | `NICE!` |
| 10 | 1 | `キレてる!` | `SHARP!` |
| 20 | 2 | `フレーム単位!!` | `FRAME BY FRAME!!` |
| 30 | 3 | `1F精度!!` | `1F PRECISION!!` |
| 50 | 4 | `人間やめた!!!` | `INHUMAN!!!` |
| 75 | 5 | `ツールアシスト!!!` | `TOOL-ASSISTED!!!` |
| 100, 以後50ごと | 6 | `完全制御!!!` | `TOTAL CONTROL!!!` |

- 叩きつけのタイミングはskillどおり：
  - 0%：不透明度0、2.8倍
  - 9%：0.88倍
  - 15%：1.08倍
  - 21%：1倍
  - 82%まで保持し、そこから1.45倍に広がりながら沈む（Tkでは不透明度の代わりに地の色へ補間する）
  - 保持時間は`520 + tier×90 ms`
- 大きさ：tier 0 = 18px 〜 tier 6 = 44px（HUDの高さ内）。角度は−4°〜−10°。
- tier 0〜1は白、tier 2はmagenta、tier 3はcyan、tier 4以上は虹色が60msごとに循環する。
- tier 4以上はHUDのshake、tier 6はRIMフラッシュを伴う（§12の制限内）。
- 同じ言葉が続かないよう、comboの節目は段を上げる方向にしか出さない。

---

## 8. 各部のskin

### 8.1 Table（`grid.py`）

- セルの地は`cell_background`、grid線は`subtle_border`。A列（入力行）は`duration_background`。
- **仮想行・仮想列**（`row >= model.row_count`、または`column >= model.column_count`）は`virtual_cell`。保存されない領域が一目で分かる。
- header：`header_background`、文字`#C9C2EA`。A列のheaderには黄の下線2px。現行のguide文言（`A · フレーム数`など）はそのまま。
- gutter：行番号はmuted。active行の行番号は黄。ROW_HINTSのバー（4px）は現行の分類のまま、ネオン色にする。
- active cell：`active_cell`地、cyanの2px枠、黄のロックオン・ブラケット。ブラケットは**4本のpolyline**で描き、cyan枠の内側に重ならない位置へinsetする（1回の再描画のrectangle数を増やさない。既存testの描画予算＝可視範囲でrectangle 30未満を守る）。
- 範囲選択：`selection_background`地、cyanの2px外枠。
- 編集Entry：地`active_cell`、文字`text`、caretは黄（`insertwidth=2`）、枠はcyan 2px。**Entryの生成・bind・IMEの経路は変えない。**
- 補完Listbox：地`panel_background`、文字`text`、選択はmagenta地に暗い文字。
- FX：tagは`"fx"`。`_draw_visible`の最後で`canvas.tag_raise("fx")`を呼ぶ。`delete("grid")`はfxを消さない。FX itemはcanvas座標で置くので、scrollに追従する。
- 右クリックmenu：Linuxでは地と文字色を合わせる（Windowsではnativeのまま）。

### 8.2 Raw（`tk.Text`）

- 地は`cell_background`、文字は`text`、caretは黄で2px、選択は`#2C2352`。
- **カーソル行**：`cursor_line` tag（地`#1A1630`）を、syntaxのtag（前景色だけ）より下に置く。
- gutter：地`panel_background`。カーソル行の番号は黄。

### 8.3 入力パレット

- 地は`panel_background`。**カテゴリ見出しの文字をカテゴリ色**にし、見出しの直下に**28×2pxの同色のrule**を置く（当初の「見出しの左に3pxの色バー」から変更。見出しは「page contentの直接の子のLabel」というデータ契約（既存test）があり、Tk Labelの横に色バーを置くとgeometryが崩れるため）：
  - ボタン = YELLOW
  - 左スティック = CYAN
  - 右スティック = MAGENTA
  - STASコマンド = PURPLE
  - Cappy = GREEN
  - 加速度／ジャイロ = ORANGE
  - 記法 = muted
- ボタン：地`palette_button`、文字`text`、アイコンは`png/neon/`。hoverは`palette_hover`。
- **押した時**（P2、motion）：80msだけカテゴリの色の地に暗い文字になり、120msでhoverの色に戻る（Tkのsquash代わりの「光る押し込み」）。`pady`も1px沈める。挿入結果は§7の経路で表に返る。
- ページ切替`◀ 1/2 ▶`：数字はcaps。切替時に見出しのruleが左から伸びる（P2、120ms）。
- 幅400px・2列・各ページのscrollは現行どおり。

### 8.4 Stick Preview

- canvasの地は`#0B0A14`。単位円は`preview_circle`の上に、ネオンの輪（LS cyan / RS magenta、2px）を重ねる。半径0.5の補助円は点線（`dash=(2,4)`）。軸は`preview_axis`。
- 点：
  - 現在点：白い芯（r=4）＋stick色の輪（r=7）
  - 1〜3f前：stick色の4段階rampで小さく
  - **位置は現行の`point_position`の値そのまま。点の間の補間・tweenはしない（T1）。**
- 新しい確定sample（`show()`のkeyが変わり、frameが有る時）：現在点の位置で、輪がr 7→16に広がって沈む（300ms）。
- `x / y / r / θ`の値：mono、各stickの色。状態文（`更新中...` / `未確定`）は現行のlabelのまま、横にlampの点（黄の脈動 / orange）を付ける。
- plotのサイズ（160×126）と`status`・`samples`のAPIは現行どおり。

### 8.5 STATUS

- 地`panel_background`、文字muted。`編集済み`の時は、label textの左に別widgetでmagentaの`●`を出す（textは現行のまま）。
- 右端のチップ：`[演出 100%]`（クリックで100→75→50→25→0と切り替え）、`[♪ ON]`（クリックでmute切替）。

### 8.6 Problems

- 地`panel_background`。`_problems_title`のtextは現行どおり。
- 失敗時は、panelの最上部に**全幅の警告テープ帯（高さ6px、黒地にorangeの斜線）**を出し、titleの左に別widgetで`おしい!` / `SO CLOSE!`のバッジ（orange）を出す。成功時はテープ無しで**GREENの`✔`バッジ**。実行中・staleの時はどちらも出さない。
- 本文（converterのメッセージ）はmono、`text`色。jumpできる行はcyanの下線（現行のtag）。本文は1文字も変えない。

### 8.7 Frame Inspector / 検索ダイアログ / Converter画面

- **Frame Inspector**：同じtokenでskinする（直接書かれた色をtokenに置き換える）。選択行はcyan地。`総フレーム数`のlabel textは現行のまま、右に大きな数字（meter font、YELLOW）を表示し、開いた瞬間にpunchする（確定値なのでcount-upしない）。
- **検索ダイアログ**：tokenでskinするだけ。
- **Converter画面**：Phase 5でskinする（§15）。地はVOID、`変換実行`は黄の大ボタン。Converter自身の変換結果にも§9の分類を使い、log欄の上に結果バッジ（`変換成功!!` / `おしい!`）を出す。messageboxは現行どおり。

### 8.8 scrollbar・menu

- scrollbarは`ttk.Scrollbar`＋`clam`系のcustom style（つまみ`#3A3260`、溝`#0F0D1A`）に置き換える。Converterはttkを使っていないので、ttk themeの切替の影響はない（実装時に再確認）。
- Windowsのmenubarとmessageboxはnativeのまま（変えられないし、変えない）。X11/macOSではmenubar・各menu・右クリックmenuにも同じskinを当てる。
- **実装メモ（P1）**：ttkの`theme_use`はinterpreter全体に効くため切り替えない。clamの`trough`/`thumb` elementを現在のthemeへ`element create ... from clam`で複製し、`Dopa.Vertical.TScrollbar` / `Dopa.Horizontal.TScrollbar`だけがそれを使う（`editor/widgets.py`）。

---

## 9. 真の発火点と山

### 9.1 Source of truth

| 演出 | 真の発火点（これ以外では出さない） |
|---|---|
| セル確定のカスケード | `on_change` / `on_transform`がTrueを返し、文書が実際に変わった |
| METERの確定punch・`Δf` | `_poll_position_analysis`でrevisionが一致し、`result.success`が真 |
| 節目スタンプ | 上記の確定TOTALが閾値を初めて越えた |
| Stick Previewの輪 | `StickPreview.show(frame, samples)`で、確定したframeが有る状態でkeyが変わった |
| `SAVE` | `_save_to`がTrueを返した |
| Validate `ノーミス!!` | `ValidationResult.success`が真、かつ`_inspection_is_current`が真 |
| Validate `おしい!` | 上の検証が失敗、かつ結果がcurrent |
| F7 解析完了 | `AnalyzeResult.success`が真、かつcurrent（Inspectorが開く／更新される時） |
| F5 `変換成功!!` | 親の`convert()`が`success`イベントを出した（全commandが終了コード0、かつ期待した出力ファイルが存在する） |
| F8 `転送確定!!` | 上に加え、converterのstdoutに`Script successfully uploaded`の行がある |
| F8 `生成OK／送信未確認` | 終了コード0で出力も存在するが、上の行が無い（`FTP error`の行がある場合を含む） |
| 失敗 `おしい!` | 親の`error`イベント |

### 9.2 Validate（F6）：小さな山

- 実行中：Problemsのtitleは現行の`検証中...`。HUDのlampの横に`SCAN`のバーが左右に往復する（実行中だけ。真の待ち）。
- 成功：
  - HUD：叫び文字`ノーミス!!` / `NO ERRORS!!`（tier 3）
  - 表canvas：上端から緑の紙吹雪
  - 音：`clear`
  - Problems：GREENの`✔`バッジ
- 失敗：
  - HUD：叫び文字`おしい!` / `SO CLOSE!`（orange、tier 1、ポヨンと弾む）
  - COMBOだけ0にする（HEAT・DOPAは維持）
  - 音：`oshii`
  - Problems：現行の本文
- 結果がstale：現行の文言だけを出し、演出はしない。

### 9.3 F5 保存して変換：中くらいの山（HUDの中だけで完結）

| 段 | 発火 | 内容 |
|---|---|---|
| 0 | F5 | COMMAND DECKのF5ボタンが光る押し込み。保存がキャンセル・conflict・失敗なら**ここで静かに終わる** |
| 1 | 保存成功 | HUDに小さな`SAVE ★`スタンプ |
| 2 | 変換開始（`on_convert`がTrue） | HUDの放射線が回り始め、lampの横に`CONVERTING`。**実際の実行時間だけ**続く。偽の待ちは入れない |
| 3a | 成功 | HUD：`変換成功!!` / `CONVERTED!!`（tier 4、虹色）、`SAVE ★ CONVERT ★`、RIMのフラッシュ1回、表canvasの上端中央からコインと紙吹雪、音`fanfare_s`。続けてラウンドの精算（§7.3）。親の成功messageboxは同じ瞬間に出る（T9） |
| 3b | 失敗 | `おしい!`（tier 1、orange）、音`oshii`、COMBOは0。親のエラーダイアログは同じ瞬間に出る |

### 9.4 F8 変換してSEND：唯一のフルパチンコ

送信は「実機に届く」瞬間で、このEditorで最も大きな出来事。**溜めは、実際に変換と転送を待っている時間そのもの。**

| 段 | 発火・長さ | COVER（本体を覆うcanvas） | HUD | 音 |
|---|---|---|---|---|
| 予告 | F8→保存成功 | — | `SAVE ★`スタンプ | `save` |
| 激アツ | 変換開始（真）〜結果まで | 120msでfade in。上下に赤×黄のストライプ帯が流れる（**全面の赤点滅はしない**。帯だけ）。中央に`激アツ!!`（tier 5、1回だけ叩きつけて保持）、下に事実の字幕`変換＋FTP送信を実行中… 2.4s`（**実際の経過秒**） | lampが黄で脈打つ | `alarm`（1回）→無音 |
| 溜め | 結果まで（実時間） | 1.2秒後、ストライプが引き、暗転の中で光の玉が1つ脈打つ（260ms周期） | — | 無音 |
| 確定 | `転送確定`（§9.1） | 暗転80ms → 虹の放射線が中心から爆発。`転送確定!!` / `SENT!!`（虹色）、`キュイーン!!` | — | `kyuin` |
| 結果 | 確定直後から | 結果カードが上から落ちてくる。**内容は事実だけ**：出力ファイル名、形式（LunaKit / STAS / nx-TAS）、送信先`SMO/tas/scripts/<name>`。下に3つの★：`SAVE ★` `CONVERT ★` `SEND ★`。170msごとに1つずつ灯る（全て既に事実） | — | ★ごとに音程が上がる |
| 決着 | 結果の後 | RIMのフラッシュ1回、コインと紙吹雪、`ROUND BONUS`の精算 | DOPAのcount-up | `fanfare`, `coins` |
| 閉じる | 確定から1.6秒、または任意の入力 | 260msでfade out | — | — |

**分岐**

- **生成OK／送信未確認**：
  - 放射線・`確定`は出さない。
  - 琥珀のカード：`生成OK` / `BUILT`、★は`SAVE ★ CONVERT ★ SEND ☆`（3つ目は灰色）、`送信: 未確認（ログを確認）` / `SEND: UNVERIFIED (see log)`。
  - 音は落ち着いた`chime`。2.4秒で閉じる。
  - 親のmessageboxは現行の文言（「FTP送信を実行しました」）のまま。
- **失敗**：
  - ストライプが中央へ潰れ、`おしい!`がポヨンと弾む（orange）。500msで閉じる。
  - 親のエラーダイアログは同じ瞬間に出る。
  - COMBOだけ0にする。
- **結果が来る前にCOVERを閉じた**：実行は続く。結果が出た時、HUDだけで上の分岐の小さな版（スタンプと叫び文字）を出す。
- **実行が8秒を超えた**：字幕の経過秒は回り続ける（事実）。光の玉は脈打ち続ける。演出の言葉は増やさない。

### 9.5 P3で確定した実装上の判断

- **SAVE ★**：Ctrl+Sを含む、`_save_to`が成功したすべての保存で出す。F5/F8のdeckボタンの光は、`can_convert`が通った時だけ（busyで何も起きない時は光らない）。
- **実行中の表示**：METERのlampの右に`SCAN`（Validate / F7）・`CONVERTING`（F5/F8）と、左右に往復する小さなblockを出す。進捗率ではなく「動いている」ことだけを示す。結果・stale・開始失敗で必ず消す。
- **F7**：成功かつcurrentなら、Debug CSVの実際の総frame数で`{n}F 全解析!!` / `{n}F SCANNED!!`（tier 2）。失敗は`おしい!`とCOMBOのリセット（Validateと同じ）。
- **ROUND BONUS**：`round(このラウンドで得たDOPA × (0.5 + E))`。精算するのは`SUCCESS`（F5）と`SEND_CONFIRMED`だけ。`SEND_UNVERIFIED`は送信が事実ではないので精算しない。productive actionが0のラウンドは精算しない。
- **演出の強さ0%**：COVERを出さず、結果はHUDの叫び文字（fadeのみ）とcaptionで出す。
- **COVERの座標**：canvasの原点を中心に置き（scrollregion）、resizeではviewだけを動かす。上下の帯だけが新しい高さに追従する。カードは常に粒子より前面（事実が読める）。
- **COVERの開閉**：fade inの代わりに帯が120msで滑り込む（Tkはalphaを持たない）。時間での終了は260msの虹彩wipe、入力での終了は即時。失敗時は`おしい!`（hold 0.3s）を出し、500ms後にwipeを始める。
- **形式の表示**：カードの形式は、出力ファイルの拡張子から推測せず、Converterがその実行で使った出力形式を受け取る。

**COVERの技術条件**（T5）

- 本体（RIMの内側）に`place`で重ねる`tk.Canvas`。`takefocus=False`。`focus_set`しない。
- 閉じる操作：COVERへのクリック、または**専用bindtag**の`<KeyPress>`。Toplevelのbindtagに`<KeyPress>`を足すと、同じtagの`<F5>`などのより具体的なbindingが優先されて発火しないため、COVERの間だけfocus中のwidget（と`tk.Text`・Table canvas・セルEntry・Go欄）のbindtagsの先頭に専用tagを入れる。`"break"`は返さず、閉じる処理は`after_idle`で行う。focusは元のwidgetに残ったままなので、押したkeyは本来どおり処理される。
- Python 3.12の`bind_class`はrootにcallbackを登録するため、削除もrootで行う（`root.deletecommand`）。
- 親のmessageboxが出ている間も、COVERのanimationは`after`で動き続ける。

---

## 10. 必要なengineering hook（実装時の指示）

Editor側の真のイベントを、1つのdispatcher（`DopaDirector`、Editorごとに1つ）へ通知する。**既存処理の結果を読むだけで、既存処理の順序・戻り値・副作用を変えない。**

| hook | 場所 | 追加内容 |
|---|---|---|
| `cell_committed(row, col, direction, kind)` | `grid.py` `_entry_move` / `commit_edit`経路 | `_apply_editor_value`が真で、かつ`new_line != old_line`の時だけ。directionは`_entry_move`の`(row_delta, column_delta)` |
| `table_transformed(kind)` | `grid.py` `_apply_model` | `current != previous`で成功した時 |
| `fx layer` | `grid.py` `_draw_visible`の末尾 | `canvas.tag_raise("fx")` |
| `positions_pending()` / `positions_confirmed(old_total, new_total)` / `positions_failed()` | `window.py` `_position_document_changed` / `_poll_position_analysis` | revisionが一致した時だけconfirmed |
| `frame_meter_model` | `window.py` `_update_frame_info` | 文字列とは別に`(state, start, duration, end, total)`を作り、Labelの文字列とMETERの描画の両方に渡す |
| `history(kind)` | `window.py` `undo` / `redo` | 成功時 |
| `saved(path)` | `window.py` `_save_to` | Trueの直前 |
| `validation_result(success, current)` | `window.py` `validate.receive` | — |
| `analysis_result(success, current, total)` | `window.py` `analyze_frames.receive` | — |
| `conversion_started(send)` | `window.py` `save_and_convert` | `on_convert`がTrueを返した時 |
| `conversion_result(report)` | `converter_gui.py` | `_create_editor`がEditorごとのclosureを`on_convert`に渡し、`_convert_editor_file(..., requester=editor)`で要求元を`weakref`として記録する（Editorからの`on_convert(path, send_ftp=...)`の呼び方は変えない）。`_drain_events`の`success`/`error`では**既存のdialogの直前**に通知し、`done`で消す。listenerが閉じている・例外を出す場合も、dialogとlogは必ず出す |
| `ConversionReport` | `converter_gui.py` `convert()` | 各commandのstdoutを連結し、`success`の直前に**別のqueue event**（`("stdout", text)`）として送る。既存の`("success", outputs)`のpayload、log、messageboxは変えない（既存testの契約） |
| `classify_conversion(report, send)` | 新規・pure | `SUCCESS` / `SEND_CONFIRMED` / `SEND_UNVERIFIED` / `FAILED`を返す。§9.1の判定をここに集約する |

### 10.1 新規module（`python_to_exe/editor/dopa/`）

| module | 内容 | Tk依存 |
|---|---|---|
| `heat.py` | HEAT / COMBO / DOPA / ROUND / 節目の状態機械。時刻は引数で受け取る | なし（unit test可能） |
| `outcome.py` | `classify_conversion`、Validate/Analyzeの分類 | なし |
| `words.py` | 演出用の文言（JA/EN）。事実の文言はここに置かない | なし |
| `fonts.py` | family候補の解決と、サイズ別fontのcache | Tk |
| `fx.py` | 共通ticker（`after(16)`、FXが動いている間だけ回る）、canvas上の粒子・輪・punch・pop・縁取り文字 | Tk |
| `hud.py` | FEVER HUD（METER・REWARD・SHOUT・背景） | Tk |
| `cover.py` | F8のCOVER | Tk |
| `sound.py` | 合成・cache・再生（§13） | なし（再生はOS依存） |
| `director.py` | hookを受け取り、heat/outcomeとFX/HUD/soundをつなぐ | Tk |

`theme.py`はtoken（色・サイズ・HEAT ramp・stick ramp）だけを持ち、import時にtkinterを読まない（テスト条件）。

---

## 11. Motion仕様

### 11.1 ticker

- Editorごとに1つの`after(16)` loop。FXが1つも無ければ止める（idle時のCPUは0）。
- 1tickの予算は**3ms**（表の再描画が約3msなので、それと合わせて1 frame 16msに収める）。3tick続けて超えたら、粒子数の上限を半分にする（自動劣化）。
- 粒子の上限：表canvasは90、HUDは40、COVERは160。
- 表の全体再描画をFXのために呼ばない。FX itemは`coords` / `itemconfigure` / `move`だけで動かす。

### 11.2 easing（Tkでの近似）

| 名前 | 用途 | 定義 |
|---|---|---|
| `slam` | 叫び文字・スタンプ | 2.8→0.88→1.08→1.0（0/9/15/21%）、事前に作ったfontの段で近似 |
| `punch` | METERの数字・COMBO | 1.3→1.0、100ms、ease-out |
| `sink` | 退場 | 色を地の色へ線形補間（Tkはitemの不透明度を持たないため） |
| `lockon` | ブラケット | 1.4→1.0、90ms、ease-out-back（小さく行き過ぎる） |
| `pulse` | lamp | 明度の正弦波、600ms周期 |

### 11.3 Tk threadでのGC（P1で追加）

FXを足すとallocationの量とタイミングが変わる。`main`には、破棄済みのTk object（別testのinterpreter、Variable、image、font）が循環参照に残り、**background workerのallocationがGCを起こすと、そのfinalizerがworker threadからTclを呼んで落ちる**（`Tcl_AsyncDelete`でabort）という潜在的な問題があった（GCの閾値を下げると`main`のままでも再現する）。

- `python_to_exe/background.py`：Tk threadが`Thread.start()`の**前に**`hold_gc()`でautomatic GCを止め、workerは終了時にholdを返すだけで**自分では再開しない**（再開した直後の自分のallocationで、溜まったGCがworker上で走るため）。
- 再開はTk threadの`resume_gc()`だけ。holdが残っている間、または**holdを返したworker threadがまだ終了していない間**は再開しない（返した直後のthread teardownもPythonを実行するため）。
- 結果はworkerがholdを返す前に届くことがあるため、結果を受け取った側（`_poll_position_analysis`、`_drain_events`）とEditorのdestroyは`resume_gc_soon(root)`で、Tk thread上の`after`による再試行を1本だけ走らせる。破棄済みのwidgetならその再試行は終わり、次の呼び出しが引き継ぐ。`_update_status`も安価な`resume_gc()`を呼ぶ。
- main threadでholdを返した場合（直接の`convert()`呼び出しなど）は、その場で再開を試みる。
- 対象のworker：Frame位置解析、Validate、Frame解析（F7）、変換（F5/F8/Start Conversion）。
- 明示的な`gc.collect()`は止めない。UI threadで毎回full collectionする案は、1万行で約19msかかるため採らない。

### 11.4 粒子の種類（canvas polygon / oval）

- 紙吹雪：回転する長方形（polygonの4点を毎tick計算）
- 星：縁取りあり
- コイン：楕円の横幅をcosで縮めて回転を見せる
- 火花：線（`create_line`、長さは速度に比例）
- 1回の放出で2種類以上を混ぜる（skill §9）。重力・抵抗はskillの`dopa-juice.js`と同じ係数。

---

## 12. 安全と設定

### 12.1 ドパ menu（`ドパ` / `Dopa`）

| 項目 | 値 | 既定 |
|---|---|---|
| 演出の強さ / Effects | 100% / 75% / 50% / 25% / 0%（radio） | 100% |
| 音 / Sound | ON / OFF（check） | ON |
| 音量 / Volume | 大 / 中 / 小 | 中 |
| フラッシュ / Flashes | ON / OFF（check） | ON |

- shortcut：`Ctrl+Shift+D`で演出の強さを1段ずつ巡回、`Ctrl+Shift+M`でmute。既存のbindと衝突しないことを実装時に確認する。
- STATUSのチップからも同じ切替ができる（§8.5）。設定の変更は、開いている全Editorへ即座に反映する。
- `settings.json`に`dopa_motion`（0/25/50/75/100）、`dopa_sound`（bool）、`dopa_volume`（1〜3）、`dopa_flash`（bool）を追加する。`_clean`で厳密に検証し、不正な値は既定値に戻す。
- **P2の範囲**：`演出の強さ`・`フラッシュ`・`[演出 n%]`チップ・`Ctrl+Shift+D`・`dopa_motion`/`dopa_flash`だけを実装する。**音が存在しないうちに`♪ ON`や音量を出すと嘘のUIになる**ため、`音`・`音量`・`[♪ ON]`チップ・`Ctrl+Shift+M`・`dopa_sound`/`dopa_volume`はP4で音と同時に追加する。

### 12.2 演出の強さ0%（作業集中）

skillのreduced-motionの扱いに合わせる。

- **止めるもの**：揺れ、粒子、フラッシュ、放射線、テープ、slam。
- **残すもの**：DOPA・COMBO・HEATの数字（count-upはせず即値）、スタンプと叫び文字（その場にfadeだけで出す）、lamp（脈動はせず色だけ）、F8の結果カード（COVERは出さず、HUDに静的に出す）。
- 報酬の段階と数字は残し、動きだけを消す。

### 12.3 制限

- **フラッシュはRIMとHUDだけ。** 全画面は光らせない。400msに1回まで（3Hz未満）、1つの山で最大2回。色は白か黄で、**赤の点滅はしない**。
- HUDのshakeは振幅3px以下、260ms以内で、**REWARD canvasだけ**（canvasのviewをずらし、itemの座標は動かさない）。**WORK層もMETERも揺らさない。**
- 叫び文字は同時に1つまで。新しいものが来たら前のものはすぐに沈める。
- OSのアニメーション無効設定：Windowsでは`SystemParametersInfo(SPI_GETCLIENTAREAANIMATION)`がFalseなら、初回起動時の既定を25%にする（任意。失敗したら無視する）。**P2では未実装**（Windows実機で確認できる段階、P5で扱う）。

---

## 13. 音

**commercial audio assetは使わない。repositoryに音声ファイルをcommitしない。** 音は`sound.py`がPython標準の`wave`と`math`で合成し、user configのcacheへWAVとして書き出す。

- cache：`<config>/TSV-TAS-2-GUI/sound-cache/v1/<event>-<volume>.wav`（初回使用時に生成。合計数百KB以内）
- **user override**：`<config>/TSV-TAS-2-GUI/sounds/<event>.wav`があれば、それを優先する。ユーザーが自分で用意した音を使えるが、repositoryには入らない。
- 再生：
  - Windows：`winsound.PlaySound(path, SND_FILENAME | SND_ASYNC | SND_NODEFAULT)`。同時発音は1つなので、優先度が高い音が低い音を上書きし、低い音は高い音が鳴っている間は捨てる。
  - Linux/WSL：`paplay`、無ければ`aplay`を非同期の`Popen`で起動する。どちらも無ければ無音。
  - 失敗しても例外を表に出さない。
- `pip`は60ms以上の間隔に制限する（連打で濁らせない）。

| event | 長さ | 設計 |
|---|---|---|
| `pip` | 45ms | 矩形波＋短いdecay。E majorのペンタトニック（E5 F#5 G#5 B5 C#6 E6…）をcomboに応じて1段ずつ上がる。HEATが上がると1オクターブ上の倍音を足す |
| `lock` | 90ms | 2音「チャキッ」（B5→E6、間20ms）。解析確定の音 |
| `save` | 120ms | 下から上へのnoise sweep（シャキン） |
| `clear` | 300ms | 長三和音のarpeggio（E→G#→B→E） |
| `fanfare_s` | 450ms | `clear`＋上のE、最後にsquareの和音 |
| `alarm` | 400ms | 2音の交互（パトランプ風）、音量は控えめ |
| `kyuin` | 500ms | 400Hz→3.2kHzの指数sweep＋vibrato（キュイーン） |
| `fanfare` | 800ms | 主和音→IV→V→I、最後に高いE |
| `coins` | 250ms | 高音のpingを不規則に5つ |
| `stamp` | 200ms | 低いthump＋高いclick（ドンッ） |
| `oshii` | 220ms | 音程が下がってから上がる（ポヨン）。**長調の音で、短調の失敗音にはしない** |
| `rewind` | 150ms | 下降sweep（Undo） |
| `chime` | 300ms | 単音のベル（送信未確認） |

本章は、dopagaki-music skillが無い状態で設計した。**その後`.claude/skills/`にdopagaki-music skillが追加された**ため、P4の開始時にそのskillを読み、本章（event・音色・長さ・調）をskillに沿って見直してから実装する。commercial audio assetを使わない・repositoryへ音声ファイルを入れない、という制約は変えない。

---

## 14. 文言（演出用だけ。事実の文言は現行のまま）

| key | JA | EN |
|---|---|---|
| `meter_locked` | 確定 | LOCKED |
| `meter_pending` | 解析中 | ANALYZING |
| `meter_unavailable` | 未確定 | UNAVAILABLE |
| `meter_tsv_only` | TSV-TASのみ | TSV-TAS ONLY |
| `fps_note` | ≈{time} @60fps | ≈{time} @60fps |
| `combo` | {n} COMBO ×{m} | {n} COMBO ×{m} |
| `dopa` | {n} DOPA | {n} DOPA |
| `round` | R{n} | R{n} |
| `extra` | EX{n} | EX{n} |
| `save_stamp` | SAVE ★ | SAVE ★ |
| `converting` | CONVERTING | CONVERTING |
| `converted` | 変換成功!! | CONVERTED!! |
| `gekiatsu` | 激アツ!! | HOT!! |
| `sending_caption` | 変換＋FTP送信を実行中… {s}s | Converting + sending… {s}s |
| `sent` | 転送確定!! | SENT!! |
| `kyuin` | キュイーン!! | KYUIIIN!! |
| `built_unverified` | 生成OK | BUILT |
| `send_unverified` | 送信: 未確認（ログを確認） | SEND: UNVERIFIED (see log) |
| `no_errors_shout` | ノーミス!! | NO ERRORS!! |
| `oshii` | おしい! | SO CLOSE! |
| `rewind` | REWIND | REWIND |
| `round_bonus` | ROUND BONUS +{n} | ROUND BONUS +{n} |
| `fever` | 1F FEVER | 1F FEVER |
| `milestones` | 1000F突破!! / 1分突破!! / 5分突破!! / 1万F突破!! / 10万F突破!! | 1,000F!! / 1 MINUTE!! / 5 MINUTES!! / 10,000F!! / 100,000F!! |
| `tape` | 1F ✦ FEVER ✦ TAS ✦ FRAME ✦ | 同左 |
| `menu` | ドパ | Dopa |
| `effects` | 演出の強さ | Effects |
| `sound` | 音 | Sound |
| `volume` | 音量 | Volume |
| `flashes` | フラッシュ | Flashes |

叫び文字のはしごは§7.4。

---

## 15. 実装フェーズ

各フェーズで既存の309件のテストを全て通すこと。見た目・体感の判断はClaudeが行う。hookやtickerなどengineeringが重い部分は、本仕様を制約としてCodexに委ねてよい（taste-sensitiveな判断は委ねない）。

| Phase | 範囲 | 完了条件 |
|---|---|---|
| **P1 Neon skin**（実装済み） | `theme.py`のtoken、Table / Raw / パレット / Stick Preview / STATUS / Problems / ttk scrollbar / `png/neon/`アイコン、COMMAND DECKの再配置、Tk threadでのGC（§11.3）。motionなし | 全画面がネオン地で読める。既存の操作が全て同じに動く |
| **P2 FX engine＋HUD**（実装済み） | `dopa/heat.py`・`fx.py`・`hud.py`・`fonts.py`・`words.py`・`director.py`、FRAME METER、REWARD、セル確定のカスケード、叫び文字、ドパmenu／チップ／settings（音関係はP4、§12.1） | §7のタイムラインがコマ送りで確認できる。IME・補完・Undoへの影響が無い |
| **P3 真の山**（実装済み） | §10のhook、`outcome.py`、Validate / F5 / F7 / F8、COVER（§9.5） | §9の全分岐を、成功・送信未確認・失敗のfixtureで確認できる |
| **P4 音** | `sound.py`、合成、override、再生 | Windows / Linux / 無音環境でエラーにならない |
| **P5 周辺＋計測** | Frame Inspector / 検索 / Converter画面のskin、性能の計測（`docs/EDITOR_PERFORMANCE.md`の方法で、FX有り／無しのredraw・選択・scroll・typing） | FX有りでも、選択とscrollの中央値の悪化が2ms以内 |

### 15.1 追加するテスト

- `heat.py`：ラチェット（失敗・Undoで下がらない）、combo window、EXTRA、精算、節目が1回だけ出ること。
- `outcome.py`：rc≠0 → FAILED。rc=0＋`Script successfully uploaded` → SEND_CONFIRMED。rc=0＋`FTP error` → SEND_UNVERIFIED。送信なし → SUCCESS。
- Tk smoke：
  - FXの実行の前後で、`document.text`、undo stack、selection、`focus_get()`、Entryの中身が変わらない。
  - `frame_status`・`_problems_title`・`stick_preview.status`のtextが現行と同じ。
  - 更新中のMETERに数字が出ない。
  - COVERの表示中に押したkeyが、Text / Table に届く。
- settings：`dopa_*`の検証と既定値。
- `theme`：import時にtkinterを読まないこと、追加tokenが`#rrggbb`であること。

---

## 16. 仕上がりの確認リスト

**ドパガキ（skill §7を、このEditorに合わせたもの）**

- [ ] セル確定に100ms以内の反応（PUNCH・pip）があり、250〜750msの連鎖（SPARK・`+N`・DOPA）があり、真の解析完了で`LOCKED`の確定が来る
- [ ] 操作中は、2秒以上何も変わらない瞬間が無い（idle時の静けさは意図した溜め）
- [ ] HEATはラウンド中に上がる一方。F5/F8の山で精算し、落差を作る
- [ ] 失敗しても、HEAT・DOPAは下がらない。言葉は「おしい!」
- [ ] DOPAは回り、浮かび、万/億へインフレする
- [ ] F8の大きな山は任意の入力でスキップできる
- [ ] セル・テキスト・Problems本文は、どの瞬間でも読める（WORK層は揺れない、上に重ならない）
- [ ] 演出の強さ・mute・作業集中（0%）・フラッシュの制限がある

**Truth Contract**

- [ ] frame/stickの値はcount-upも補間もしない
- [ ] 更新中・未確定の時に、数字を確定の見た目で出さない
- [ ] 成功演出は§9.1の発火点からしか出ない。F8の`転送確定`は送信成功の行がある時だけ
- [ ] 既存のダイアログ・log・Problems・label textは、文言もタイミングも現行どおり
- [ ] FXはfocus・grab・`"break"`を行わない。IME・補完・Undo/Redo・selectionは現行どおり
- [ ] converter / parser / document semanticsは無変更
- [ ] 音声ファイルをrepositoryにcommitしていない
- [ ] `main`は無変更
