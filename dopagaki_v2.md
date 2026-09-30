# Dopagaki UI Specification — TSV-TAS-2-GUI

> **Status:** design / implementation contract for the `dopagaki` branch  
> **Target:** existing Tkinter/Tk TSV-TAS-2-GUI editor  
> **Purpose:** make the editor deliberately excessive, fast-reacting, game-like, and celebratory **without changing TAS semantics or reducing editor usability**.

---

## 0. この文書の役割

この文書は、`dopagaki` branch での実装判断の基準です。

Codex / Sol 6.1 は、単に「派手に」「ネオンに」と解釈せず、ここに書かれた以下の優先順位に従って実装してください。

1. **TSV-TAS editorとしての機能を壊さない**
2. **通常版 `main` のconverter / document / frame semanticsを尊重する**
3. **入力や成功操作に対して即座に視覚的フィードバックを返す**
4. **演出は段階的にインフレする**
5. **演出は高密度でも、編集対象・caret・数値を読めなくしない**
6. **animation / particle / callback は必ず有限寿命にする**
7. **見た目のためにmemory leak・常時CPU負荷・converter再実行を増やさない**

「ドパガキ」はこの文書では**刺激密度の高いUI演出を示すプロジェクト内の俗称**として扱います。医学的な意味やユーザー状態の判定には使いません。

---

# 1. Branch / architecture policy

## 1.1 Branch

通常版は `main` に残し、ドパガキ版は専用branchで開発します。

```bash
git switch main
git pull --ff-only
git switch -c dopagaki
```

以後、ドパガキ仕様の実装は原則 `dopagaki` branch 上で行います。

## 1.2 通常版を壊さない

以下は**共通logic**として扱い、見た目の都合で独自実装しません。

- `tsv-tas.py`
- `nx-tas-to-tsv-tas.py`
- converter command building
- TSV syntax / semantics
- line-map semantics
- Debug CSV semantics
- document text / newline / encoding preservation
- Undo / Redo
- rectangular selection
- row / column operations
- Raw / Table
- autocomplete
- Input Palette candidate text
- Validation
- Frame Position
- frame jump
- Stick Preview resolved data
- Save / Save As / F5 / F8
- Recovery
- backup
- recent files
- FTP
- LunaKit / STAS / nx-TAS output

**ドパガキ版のためにparserを複製しない。**

## 1.3 UI分離

可能ならドパガキ固有コードを次のように分離します。

```text
python_to_exe/
  editor/
    ... existing editor logic ...
    theme.py
    dopagaki/
      __init__.py
      theme.py
      motion.py
      effects.py
      hud.py
      particles.py
```

実際のファイル構成は既存コードへ合わせて簡略化してよいですが、`window.py` に色・animation式・particle処理を大量直書きしないでください。

## 1.4 Entry point

branch専用でも、通常UIとの比較・回帰確認がしやすいように、可能なら専用entry pointを持たせます。

```text
python_to_exe/main_dopagaki_jp.py
python_to_exe/main_dopagaki_en.py
```

通常の `main_jp.py` / `main_en.py` を壊さないこと。

---

# 2. 参考例と採用する設計原理

## 2.1 高信頼・実装確認済み

### A. ドパドリル

- Repository: https://github.com/grmchn/dopa-drill
- Specification: https://github.com/grmchn/dopa-drill/blob/main/docs/SPEC.md

採用する核心:

- 進行に応じて演出を強くする
- 基本演出強度:
  ```text
  E = 0.08 + 0.92 × progress^1.3
  ```
- 後半ほど背景・粒子・揺れ・観客・電飾などを積み上げる
- 誤りで全報酬を没収しない
- 動きの強度設定を持つ
- 演出カテゴリを積み重ねる
- 結果 / finale は通常操作より明確に強くする
- 強度0では主要な大移動・揺れ・閃光を抑える

このプロジェクトでは学習ゲームの進捗ではなく、後述する **Hype値** にこのカーブを適用します。

### B. 『ドパガキ氷つくってみた』

参考:
- unityroom
- Game*Spark 紹介記事  
  https://www.gamespark.jp/article/2026/08/05/170236.html

採用する核心:

- 通常取得 → レア取得 → 完成で**演出階層を明確に変える**
- レア度に応じて光・効果音・集中線を増やす
- 大きな完了イベントでは画面全体のflashと巨大文字を使う
- 日常操作とfinaleを同じ強さにしない

### C. DopaMINE

- https://unityroom.com/games/dopamine

採用する核心:

- 開封という単純操作自体を「報酬イベント」にする
- visual reward と数値成長を連動させる
- 大量オブジェクトは描画負荷につながり得るため、**量だけで盛らずpool / capを持つ**

### D. ブレインロットをつなげて消そう！

- https://unityroom.com/games/puipui_brainrot

採用する核心:

- 通常操作
- chain / merge
- gauge
- fever
- skillによる盤面一掃

という**通常 → 蓄積 → 発火 → 大演出**のレイヤ構造。

TSV Editorではこれを

```text
編集操作 → Hype蓄積 → milestone → Convert/Send finale
```

として読み替えます。

### E. DDD (Dopagaki Driven Development)

- https://topaz.dev/projects/b0f19491c654d6783bb5

採用する核心:

- コーディングツール自体に短い刺激単位を持ち込む発想
- 長い作業を、小さな反応が連続するUIにする

ただしTSV editorでは**編集操作をswipe式に置き換えない**。既存Spreadsheet操作を維持した上でfeedbackだけ増やします。

---

## 2.2 ユーザー提供の視覚参考

以下は方向性の参考として保持しますが、この文書作成時点では自動取得・内容確認できなかったため、**仕様の唯一の根拠にはしません**。

- @posi_posi8  
  https://x.com/posi_posi8/status/2103660010719129995
- @unsu0707 Sonnet / Sol comparison  
  https://x.com/unsu0707/status/2104957450751549744
- @unsu0707 Opus single HTML example  
  https://x.com/unsu0707/status/2105305211543965809
- dopagaki-game  
  https://dopagaki-game.vercel.app

視覚確認できる環境では、以下だけ抽出してください。

- color density
- stamp typography
- border treatment
- shake / bounce timing
- particle density
- reward frequency
- background treatment

モデル比較の感想そのものは実装要件にしません。

---

# 3. Dopagaki版のデザイン原則

## 3.1 一言で表す

> **精密なTAS editorの上に、アーケード・パチンコ・ガチャ結果画面・音ゲーのfeedback密度を被せる。**

ただし、Table自体は読めること。

## 3.2 「派手」より重要なもの

ドパガキ感は単純な彩度ではなく、次の組み合わせで作ります。

```text
即時反応
× 頻繁な小報酬
× 蓄積
× インフレ
× 節目の爆発
× 一瞬で消える巨大feedback
```

画面を常時ネオンで埋めるだけでは不十分です。

## 3.3 情報層と演出層を分ける

### 情報層 — 常に読める

- TSV cells
- current selection
- cell editor Entry
- row number
- headers
- Start / Duration / End / Total
- Stick Preview数値
- Problems
- status
- menu
- dialog

### 演出層 — 一時的

- glow
- pulse
- particles
- impact text
- streak
- confetti
- screen-edge flash
- scanline
- warning stripe
- trail
- shake

**演出層が情報層を永続的に隠さないこと。**

---

# 4. Visual language

## 4.1 Color

ベース候補:

```text
Near-black / dark navy background
Neon Cyan
Hot Pink
Electric Yellow
Acid Green
Purple
White
Success Green
Error Magenta / Purple
```

ただしTableのcell backgroundは極端に暗くしなくてよい。

推奨:

- application chrome / side panel: dark
- table editing surface: light or neutral
- active cell outline: cyan / electric blue
- active effect: neon gradient風の複数色
- success stamp: yellow + white + cyan edge
- warning: magenta / purple
- trail: cyan → pink
- current Stick point: bright red / hot pink

TkはCSS gradientを持たないため、細線を複数重ねる・Canvas rectangleを分割する・色補間で擬似的に表現します。

## 4.2 Border

通常の1px borderだけでなく、重要イベントでは

```text
dark base
→ bright inner border
→ colored outer border
→ temporary glow-like duplicated line
```

を使います。

Tkのshadowは疑似表現でよい。

## 4.3 Typography

巨大impact textは短い単語を使います。

例:

```text
INPUT!
LOCK!
VALID!
CLEAN!
CONVERT!
SENT!
FRAME!
COMBO ×12
HYPE UP!
LET'S GO!!
```

日本語例:

```text
入力！
確定！
検証OK！
変換完了！
送信！
フレーム！
連続 ×12
激アツ！
```

注意:

- 実際に成功していない操作へ `SUCCESS` を出さない
- Validate失敗時に「成功」演出を出さない
- converter結果を誤認させる文言を使わない

## 4.4 Caution tape / cyber grid

背景装飾として使用可。

ただし:

- Table cell上へ常時斜線を重ねない
- caret付近へ動くgridを出さない
- margin / toolbar / Palette / effect HUDを主戦場にする

---

# 5. Hype / intensity model

## 5.1 2種類の強度を分ける

### User level

```text
OFF
LOW
MID
FULL
```

### Runtime Hype

```text
H ∈ [0, 1]
```

UI設定と、現在の操作連続度を分離します。

## 5.2 基準式

ドパドリルのカーブを流用します。

```text
curve(H) = 0.08 + 0.92 × H^1.3
```

最終強度:

```text
I = level_multiplier × curve(H)
```

初期案:

```text
OFF  = 0.00
LOW  = 0.28
MID  = 0.62
FULL = 1.00
```

この値はvisual tuningで変更可。

## 5.3 Hypeの蓄積

Hypeは**保存データではない**一時UI stateです。

初期調整値の例:

| Event | Hype加算 |
|---|---:|
| active cell move | +0.01 |
| edit begin | +0.02 |
| edit commit | +0.04 |
| Palette insert | +0.07 |
| row duplicate / paste | +0.08 |
| frame jump success | +0.08 |
| Validate success | +0.16 |
| Convert success | +0.28 |
| Convert & Send success | +0.40 |

これは固定仕様ではなく初期tuning値。

## 5.4 Decay

無操作中はHypeを徐々に下げます。

重要:

- Hype decayだけのために永遠に16ms timerを回さない
- effectがある時だけtickする
- 次event時に経過時間からHを計算してもよい

例:

```text
half-life: 3〜6秒
```

## 5.5 Failure

エラー時:

- Hypeを0にしない
- combo visualを完全消去しない
- 赤一色の「罰」画面にしない
- brief glitch / purple shake程度
- Problemsを読みやすくする
- focusは問題箇所へ維持

「勢いを維持する」と「成功扱いする」は別です。

---

# 6. Event tiers

## Tier 0 — passive

常時表示。

- cyber frame
- subtle scanning accent
- static diagonal tape
- neon separators

**animation不要。**

## Tier 1 — micro juice

頻繁な操作。

対象:

- cell selection
- typing commit
- Palette click
- page switch
- frame jump

演出:

- 100〜220ms pulse
- outline expand / contract
- tiny spark 2〜6個
- number tick
- icon pop

ユーザー操作から**100ms以内に開始**を目標。

## Tier 2 — medium reward

対象:

- paste range
- duplicate rows
- successful Find/Replace all
- Validate success
- large selection change

演出:

- 250〜450ms
- brief impact text
- 10〜30 particles
- edge flash
- small screen shake
- Hype meter jump

## Tier 3 — major reward

対象:

- Save & Convert成功
- Frame Analyze成功
- meaningful milestone

演出:

- 500〜900ms
- giant text
- radial burst
- confetti
- strong border pulse
- numeric counter jump
- color cycle

入力は止めない。

## Tier 4 — finale

対象:

- Convert & Send成功
- manual FEVER trigger
- Hype maximum
- optional milestone

演出:

- 800〜1600ms
- large stamp
- layered burst
- screen-edge warning tape
- confetti + stars + coins/pixels
- temporary palette/table border overdrive
- short shake
- countdown cleanup

長時間画面をブロックしない。

---

# 7. Motion primitives

実装はまず少数のprimitiveを再利用します。

## 7.1 Pop

```text
scale: 0.92 → 1.10 → 1.00
duration: 140〜240ms
```

Tk widgetそのものをscaleしにくい場合:

- font size
- padding
- Canvas icon/text size
- outline thickness

で代替。

## 7.2 Pulse

```text
accent A → bright → accent A
```

対象:

- selection outline
- Palette button
- frame info value

## 7.3 Impact stamp

```text
opacity-like: stipple / color blend
position: center or effect HUD
scale-like: font size 0.7 → 1.25 → 1
shake: optional
lifetime: 300〜700ms
```

## 7.4 Shake

UI全体を移動するのではなく、原則**effect layer / border / stampだけ**をshake。

Tableのactual coordinate systemを揺らしてcell hit-testを壊さない。

## 7.5 Trail

Stick Preview:

- current resolved position
- previous 1〜3f
- visual motion interpolationは**見た目だけ**
- resolved Debug CSV値は変更しない

## 7.6 Particle

最低属性:

```text
x, y
vx, vy
age
lifetime
size
kind
color
```

可能ならslots / small record。

---

# 8. Particle system

## 8.1 必須ルール

- active particle上限を持つ
- lifespanを持つ
- expired objectを必ず削除またはreuse
- idle時にtimerを止める
- full redrawを避ける
- document objectをparticle closureから保持しない

## 8.2 初期cap

目安:

```text
LOW:   30
MID:   90
FULL: 180
Finale temporary hard cap: 260
```

実測で重ければ下げる。

**個数を増やすことより、速度・サイズ・shapeの差を使う。**

## 8.3 Shapes

assetを増やさずCanvasで作れるもの:

- square pixel
- circle
- star風polygon
- diamond
- line spark
- ring
- coin-like ellipse
- tiny plus
- confetti rectangle

著作権のあるゲーム素材をコピーしない。

---

# 9. TSV-TAS-specific juice mapping

## 9.1 Cell selection

- cyan outline pulse
- 2〜4 small pixel spark
- Hype低増加
- selection semanticsは不変

## 9.2 Edit commit

セル確定時:

- outline flash
- tiny `LOCK!`
- contentが変わった場合のみHype増加
- modified / Undoは既存処理に完全依存

## 9.3 Palette insert

Buttons:

- controller icon pop
- matching letter stamp
- small radial spark

LS / RS:

- Stick Preview側でring pulse
- LS/RS label highlight

## 9.4 Stick Preview

通常版の

- current frame
- previous 3f
- x/y/r/θ

を維持。

Dopagaki visual:

- current pointにouter ring
- movement distanceが大きい時だけstrong trail
- Hypeが高い時だけring / scan effect
- 数値は常に読める

## 9.5 Frame Position

Start / Duration / End / Total:

- active row change時にvalueだけbrief tick
- duration大変更時は数字がpop
- 0-based semanticsは絶対に変えない

## 9.6 Validate

### success

- green/cyan flash
- `VALID!`
- 20〜40 particles
- Hype + medium

### failure

- purple glitch
- `CHECK!`
- Problemsへ視線誘導
- Hypeを完全resetしない
- success confettiは出さない

## 9.7 Save & Convert

成功:

```text
CONVERT!
```

- giant stamp
- radial burst
- strong border
- Hype大増加

失敗:

- short glitch
- Problems / logを強調
- false success演出禁止

## 9.8 Convert & Send

このbranchで最も強い通常event候補。

成功:

```text
SENT!!
LET'S GO!!
```

- finale class
- confetti
- pixel burst
- border chase
- optional short audio later

FTP failure時に成功finaleを出さない。

---

# 10. Combo / streak

## 10.1 目的

ゲーム上のコンボではなく、**UI演出用の連続操作カウンタ**。

保存しない。

例:

- edit commit
- palette insert
- row operation
- frame jump

を一定時間内に続けると上昇。

## 10.2 表示

常時大きく表示しない。

threshold例:

```text
5
10
20
30
50
```

で

```text
COMBO ×10
HYPE UP!
```

を短時間表示。

## 10.3 Failure

converter errorやvalidation errorでゼロにしなくてもよい。

ただし意味が紛らわしいなら名称を `JUICE` / `HYPE` にする。

---

# 11. FEVER

## 11.1 Trigger

Hypeが一定値以上に達したとき。

例:

```text
H >= 0.88
```

## 11.2 Duration

2〜6秒程度。

## 11.3 Effects

- border chase
- denser particles
- neon color cycle
- Palette category heading pulse
- Stick Preview ring
- frame info glow
- occasional tiny stamps

## 11.4 禁止

- converterを勝手に走らせる
- textを自動変更
- selectionを移動
- scrollを勝手に動かす
- input latencyを増やす
- caretを隠す

---

# 12. Intensity control

Dopagaki branchには必ずmotion intensityを持たせます。

```text
OFF / LOW / MID / FULL
```

### OFF

- motionなし
- particlesなし
- shakeなし
- static Dopagaki themeのみ

### LOW

- micro pulse
- 低particle
- major stampは控えめ
- shakeほぼなし

### MID

- 標準Dopagaki
- particles
- impact
- occasional shake

### FULL

- intended experience
- all effect layers
- FEVER
- finale

設定値はdocumentとは別にuser configへ保存してよい。

通常EditorのTSV内容へ書き込まない。

---

# 13. Audio policy

Audioは**Phase後半**。

Tkinter標準だけではcross-platform音響合成に向かないため、初期phaseでWeb Audio前提の設計を持ち込まない。

候補:

- Windows: `winsound` の軽いfeedback
- optional external wav assets
- platform abstraction
- mute必須

新規依存を追加する場合は別途判断。

AudioなしでもDopagaki感を成立させる。

---

# 14. Tkinter implementation rules

## 14.1 Time based animation

frame count基準ではなく:

```python
time.monotonic()
```

基準。

## 14.2 after()

- active effectがある時のみschedule
- window destroy時cancel
- stale callbackはidentity / generationで無効化
- callbackからEditor全体を不要にclosure保持しない

## 14.3 Target timing

理想:

```text
16〜20ms tick
```

ただしTkが遅れた場合:

- elapsed timeで位置を進める
- 遅れたframeを全部再生しない
- skipして最終状態へ追いつく

## 14.4 No always-on redraw

禁止:

```text
常時60fpsでTable全体を再描画
```

effect Canvasだけ更新。

## 14.5 Canvas item strategy

最初は単純実装可。

profileでcreate/deleteが問題になった場合のみpool化。

前回通常版profileではTable redraw自体は十分高速だったため、通常gridをeffectのために改造しない。

---

# 15. Memory / performance budget

通常版でDebug CSV memoryを大幅削減した直後なので、Dopagaki branchでも無制限にmemoryを使わない。

## 15.1 Invariants

- effect終了後に大型listを残さない
- closed Editorをeffect managerが保持しない
- PhotoImageをイベントごとに複製しない
- particle historyを永続保存しない
- animation historyをUndoへ入れない
- Hype / comboをRecoveryへ保存しない

## 15.2 Idle

何も動いていない時:

- animation tick 0
- particle 0
- effect callback 0

が理想。

## 15.3 Stress test

最低限:

- cell移動1000回
- Palette insert 300回
- page切替100回
- Validate 30回
- Frame Inspector open/close 30回
- effect finale 100回
- Editor open/close 30回

後に大型effect objectが積み上がらないこと。

RSSが完全に戻らない場合はPython object leakとallocator retentionを分ける。

---

# 16. Usability invariants

Dopagaki版でも以下は絶対に守る。

- F2 / double click編集
- Tab / Shift+Tab
- Enter / Shift+Enter
- arrow navigation
- rectangular selection
- IME entry
- Ctrl+Z / Ctrl+Y
- Ctrl+C/X/V
- Find / Replace
- drag column resize
- Palette scroll
- Raw/Table switch
- Problems line jump
- Frame jump
- active cell visibility
- horizontal / vertical scroll
- JP/EN

Animation中でも同じ。

---

# 17. Accessibility / motion safety

Dopagaki branchの目的は過剰演出だが、**止められること**は必須。

- intensity OFF
- motion OFF
- audio mute
- flashingをOFFにできる構造
- keyboard focusを奪わない
- modal popupを演出目的だけで増やさない

高速点滅を常時使わない。

特にfull-screen flashは短時間・低頻度にする。

---

# 18. Mascot

任意。

採用する場合:

- original design
- SVG / Canvasで描ける単純shape
- Mario / Cappy等の公式画像をコピーしない
- gameplay stateを誤認させない
- editorの主要領域を隠さない

反応候補:

- input
- validate
- convert
- error
- fever
- send

---

# 19. Implementation phases

## Phase D0 — Branch + foundation

目的:  
**normal logicを維持しつつDopagaki effectを載せる基盤。**

実装:

- `dopagaki` branch
- Dopagaki theme
- intensity setting
- MotionController
- effect lifecycle
- active-cell pulse 1種類
- cleanup tests

まだparticle祭りにしない。

## Phase D1 — Micro Juice

- selection pulse
- edit commit pop
- Palette icon reaction
- LS/RS ring
- Frame Position tick
- page switch accent

## Phase D2 — Particles + Hype

- Hype state
- decay
- particle system
- combo / threshold
- LOW/MID/FULL density
- edge flash

## Phase D3 — Validation / Convert reward

- Validate success
- Validate error
- Save & Convert
- Convert & Send finale
- truthfulness invariant

## Phase D4 — FEVER

- Hype threshold
- border chase
- color cycle
- dense particle
- temporary stamps
- strict performance caps

## Phase D5 — Audio

必要なら。

- mute
- Windows / platform handling
- no required external service

## Phase D6 — polish

- typography
- timing
- saturation
- shake amount
- JP/EN
- DPI
- PyInstaller
- native Windows profiling

---

# 20. Test requirements

既存testは維持。

追加するべきtest:

## Logic isolation

- Dopagaki eventでdocument text不変
- modified不変
- Undo stack不変
- selection不変（演出自身は移動させない）
- converter args不変
- line map不変
- Debug CSV不変

## Lifecycle

- animation complete後callback 0
- destroy後callback実行なし
- Editor close後weakref回収
- particle lifespan完了後0
- repeated finaleでobject増加なし

## Intensity

- OFFでmotionなし
- LOW/MID/FULLでdensity差
- level変更でdocument不変

## Failure

- Validate failureでsuccess effectなし
- Convert failureでfinaleなし
- FTP failureでSENT表示なし

## Real Tk

毎変更で何度も開かない。

各phase最後に1回程度:

- JP
- EN
- 125% / 150% Windows DPIはnative確認
- selection
- typing
- Palette
- Stick Preview
- scroll
- Validate
- Convert

---

# 21. Anti-patterns

以下は禁止。

### A. 「とりあえず全部常時動かす」

idle CPUが増える。

### B. Table全体を毎frame再描画

編集性能を壊す。

### C. animationからdocument logicを呼ぶ

見た目がsemanticsへ侵入する。

### D. particleごとにTk widgetを作る

Canvas itemを使う。

### E. 数千particle

量ではなくlayeringで盛る。

### F. successとfailureを同じpartyにする

意味が壊れる。

### G. font / colorを各ファイルへ乱立

themeへ集約。

### H. Web向けlibraryを持ち込む

Framer Motion / GSAP / Anime.js / Web Audio はこのTkinter projectには直接適用しない。

### I. normal UIの可読性を捨てる

「読みづらくても派手さ優先」はこのEditorでは採用しない。

**派手さは情報層の外・瞬間演出・余白で稼ぐ。**

---

# 22. Definition of Done

Dopagaki版は次を満たした時に完成扱い。

1. TSV-TASの出力・converter結果が通常版と同一
2. 日常操作へ即時feedbackがある
3. Hypeで演出密度が上昇する
4. Convert / Sendは明確なfinaleになる
5. intensity OFFがある
6. effectがfocus / selection / Undoを壊さない
7. idle時にanimation loopが止まる
8. memory leakがない
9. JP/ENで破綻しない
10. Windows nativeでDPI / IME / PyInstaller確認済み

---

# 23. Codex / Sol 6.1 operating instructions

この文書を渡された実装agentは、以下の順で行動してください。

1. `dopagaki.md` を最初に読む
2. current branch / HEAD / statusを確認
3. `dopagaki` branch上であることを確認
4. 対象phaseを宣言
5. 既存実装を読む
6. effectをlogicから分離
7. headless tests
8. 最後に必要なら実Tkを1回
9. performance / lifecycleを確認
10. commit / push
11. 実装内容と次phase候補を報告

勝手に別phaseの機能を大量追加しない。

---

# 24. Codexへ渡す基本prompt

```text
repositoryの `dopagaki.md` を最初から最後まで読み、
その文書を今回の実装仕様として扱ってください。

現在は `dopagaki` branchで作業します。
mainへ直接commitしないでください。

まず:
- git branch --show-current
- git status
- HEAD
- dopagaki.md
- 関連する現行コード

を確認してください。

TSV parser / converter semantics / document / Undo / selection / frame analysisは
見た目のために変更しないでください。

今回の対象phase:
Phase D0 — Branch + foundation

実装:
- Dopagaki固有theme
- OFF / LOW / MID / FULL intensity
- time.monotonic + Tk after()ベースの軽量MotionController
- animationがない時はtimer停止
- Editor destroy時cleanup
- active cell移動時の短いpulseをDopagaki版だけに実装
- normal entrypointのappearance / behaviorを維持
- modified / Undo / selection / converter結果へ影響させない

まだ:
- 大量particle
- FEVER
- audio
- giant finale
- mascot

は実装しないでください。

既存testsをすべて維持し、
lifecycle / OFF / cleanup / document invariantsのtestを追加してください。

開発中に何度もTkを開かず、
headless中心で進めてください。
最後に必要ならWSLg real Tkを1回だけ確認。

問題なければdopagaki branchへcommit/push。

最後に:
- architecture
- theme分離
- MotionController
- sample pulse
- intensity
- cleanup
- tests
- real Tk
- commit SHA
- git status

を報告してください。
```

---

# 25. Solへ「もっと盛れ」と指示する時の基準

曖昧に「もっと派手に」ではなく、足りない軸を指定する。

例:

```text
particle密度ではなくimpact typographyを2倍強くする
```

```text
micro feedbackの開始をもっと即時にする
```

```text
Hype 0.8以降だけborder / trail / stampを一段追加する
```

```text
Convert成功をTier 3、Send成功をTier 4として明確に差別化する
```

```text
Tableの可読性はそのままで、外周とPalette側の刺激密度を上げる
```

```text
常時animationを増やさず、event直後300msの密度を上げる
```

この方が「ただネオンを増やす」失敗を防げます。

---

# 26. 最終デザイン思想

通常版:

> 落ち着いて長時間TASを編集できる Playful Utility

Dopagaki版:

> 正確なTAS編集機能はそのままに、操作するたび短い報酬が返り、連続操作で画面の熱量が上がり、Validate / Convert / Sendで爆発する arcade editor

最重要なのは以下。

```text
Dopagaki ≠ 常時うるさい
Dopagaki = 反応が速い + 報酬が多い + 蓄積する + 節目で爆発する
```

これを実装判断の基準にしてください。


---

# 27. F5 Convert Ritual — “Let’s Go” synchronization

## 27.1 目的

Dopagaki版では **Save & Convert (`F5`) を通常の保存操作ではなく、短い「発射シーケンス」**として演出する。

ユーザーがF5を押した瞬間から:

```text
Save
→ Convert開始
→ 楽曲のサビ直前を再生
→ countdown
→ Hype / border / particleを段階的に増幅
→ converter成功結果を待つ
→ サビ / drop位置で LET'S GO!!
→ Convert成功finale
```

という流れを基本とする。

重要:

- **保存・converter処理自体は従来通り即時開始する**
- 演出のためにconverter開始を遅らせない
- outputを演出のために改変しない
- UI countdownをconverterのETAとして表示しない
- converterが失敗した場合に成功finaleを出さない

---

## 27.2 ユーザー提供曲

想定曲:

```text
JAXSON GAMBLE - Let's Go
```

ユーザー提供の現在のaudio sample:

```text
Let's Go [Ba9LOr4lySs].webm
```

確認できたmedia情報:

```text
container: WebM
audio codec: Opus
sample rate: 48 kHz
channels: stereo
duration: 約127.341秒
```

波形の音量変化だけから見ると、**約51.4〜51.5秒付近に大きな立ち上がり**がある。

これはサビ / drop候補として有力だが、波形解析だけでは楽曲構成を断定しない。

初期tuning候補:

```text
music_source_start ≈ 47.8 s
major_drop          ≈ 51.45 s
lead_time           ≈ 3.65 s
```

Windows nativeで実際に耳で確認し、最終cueは設定値として調整する。

**timestampをconverter logicへhard-codeしない。**

---

# 28. F5 timeline

## 28.1 基本timeline

初期案:

```text
T+0.00   F5
         active cell commit
         normal Save開始
         normal Convert worker開始
         music cue開始
         effect HUD ON

T+0.30   "READY"
         outer border pulse

T+0.65   countdown 3
         particles level 1

T+1.65   countdown 2
         particles level 2
         cyber grid / warning stripe強化

T+2.65   countdown 1
         particles level 3
         Stick Preview / Frame Info glow

T+3.65   music drop target
         converter成功済み:
             LET'S GO!!
             CONVERT!!
             Tier 4 finale
         converter処理中:
             CHARGING...
             success表示はまだ出さない

converter成功時:
         drop前なら結果をlatchしてdropまで待つ
         drop後なら即時success finale

converter失敗時:
         countdown / pending successをcancel
         success stamp禁止
         short glitch
         Problems / logを強調
```

具体時間はmusic cue確定後に微調整可。

---

## 28.2 Result latch

音楽とconverter完了は別タイミングなので、**演出と真実の状態を分離**する。

状態例:

```text
IDLE
PRELUDE
WAITING_FOR_DROP
WAITING_FOR_CONVERTER
SUCCESS_READY
SUCCESS_FINALE
FAILED
CANCELLED
```

### Converterがdropより早い

成功結果を内部で保持する。

```text
converter success
→ outputは既に完成
→ UIだけdropまでprelude継続
→ dropでfinale
```

この待ち時間中もEditorをblockしない。

### Dropがconverterより早い

絶対に成功表示を出さない。

表示候補:

```text
CHARGING...
BUILDING...
HOLD IT...
```

converter成功が届いた瞬間にfinaleへ移る。

### Converter failure

- musicを停止または短くfade相当で切る
- countdown cancel
- `LET'S GO!!` / `CONVERT!!` / confetti禁止
- purple / magenta glitch
- Problems / converter logを見やすくする

---

# 29. Countdown design

countdownは単なる数字ではなく、段階ごとに画面の熱量を上げる。

## 3

```text
large "3"
cyan
outer frame pulse
small pixels
```

## 2

```text
larger "2"
cyan + pink
warning tape
particle増量
```

## 1

```text
largest "1"
yellow / white
short shake
ring burst
```

## Drop

```text
LET'S GO!!
```

または日本語UIでも固有演出文字として英語のまま使用可。

さらに:

```text
CONVERT COMPLETE
```

等を重ねてもよい。

ただし巨大文字は **200〜800ms程度の短時間表示**とし、Tableを長時間隠さない。

---

# 30. F5 visual choreography

F5 preludeでは、既存Dopagaki primitivesを積み上げる。

## Layer 1 — immediate

F5押下から100ms以内。

- toolbar F5/Convert area flash
- Frame Position value pulse
- thin neon border
- tiny particle

## Layer 2 — build

音楽のpre-chorus中。

- cyber grid強化
- diagonal warning strips
- side-panel pulse
- Stick Preview outer ring
- Palette icon small pop
- Hype meter rise

## Layer 3 — countdown

- center impact number
- screen edge chase
- particle density上昇
- mild shake
- color shift

## Layer 4 — success finale

- `LET'S GO!!`
- radial burst
- confetti
- stars / pixel fragments
- thick neon outer frame
- Frame Position / Palette / Stick Preview simultaneous pulse
- temporary FULL intensity override

完了後は0.8〜1.5秒で通常編集状態へ戻す。

---

# 31. F5中もEditorを使えること

F5 ritualは原則**non-modal**。

演出中でも:

- cell選択
- scroll
- typing
- Palette操作
- Raw/Table
- menu

を可能にする。

ただし既存仕様でConvert中に禁止されている重複Convert等はその制約を維持。

演出overlayは:

- hit-testを奪わない
- focusを奪わない
- Entry caretを隠し続けない

こと。

---

# 32. 通常作業中のDopagakiとF5の差

作業中にもDopagaki feedbackは常時利用する。

ただし **F5は別格** にする。

## 通常作業

```text
cell move
edit commit
Palette insert
frame jump
row operation
```

→ 100〜400msのmicro / medium juice

## Validate

→ Tier 2〜3

## F5 Save & Convert

→ music prelude付き Tier 4 ritual

## F8 Save, Convert & Send

将来はF5よりさらに上位。

候補:

```text
F5: CONVERT / LET'S GO
F8: SENT / LAUNCH / OVERDRIVE
```

F8でも同じ曲を毎回再生するか、別finaleにするかは後で決める。

---

# 33. Audio implementation policy

## 33.1 著作権assetをrepositoryへcommitしない

ユーザー提供の商用楽曲ファイルは、public repositoryへそのまま追加しない。

推奨:

```text
local_media/
  lets_go.webm
```

等のlocal-only pathを用意し、`.gitignore`対象にする。

またはuser settingsで外部pathを指定する。

Dopagaki branchのGitには:

- playback code
- cue configuration
- fallback behavior

のみを置く。

## 33.2 TkinterはWebMをnative playbackしない

Tk/Tkinter単体にはWebM/Opusのseek付き再生機能がない。

実装候補は次の順で検討する。

### Option A — local ffplay backend

長所:

- WebM/Opusをそのまま再生可能
- `-ss`でcue位置から開始しやすい
- prototypeが速い

短所:

- ffplay / FFmpeg dependency
- PyInstaller配布時の扱いが必要

Dopagaki開発初期には最も簡単。

### Option B — pre-cut WAV + Windows `winsound`

Windows専用完成版候補。

サビ前から始まる短いclipをユーザーがlocal生成しておき:

```text
cue clip start = desired pre-chorus
```

として再生する。

長所:

- Python標準library
- runtime seek不要
- 実装が単純

短所:

- Windows限定
- WAVが大きい
- cue変更には再生成が必要

### Option C — optional audio library

必要なら後phaseで検討。

新規dependency導入は、PyInstaller / Windows compatibilityを確認してから。

## 33.3 Audio failure

音源なし / backendなしでもF5は必ず動く。

```text
audio unavailable
→ visual-only ritual
→ converterは通常通り
```

audio errorがSave/Convert失敗の原因になってはいけない。

---

# 34. Audio configuration

Dopagaki user settingsにdocumentとは独立して保持。

例:

```json
{
  "dopagaki_audio_enabled": true,
  "dopagaki_audio_path": "C:/.../lets_go.webm",
  "dopagaki_audio_source_start": 47.8,
  "dopagaki_audio_drop": 51.45,
  "dopagaki_audio_volume": 0.75
}
```

値の単位:

```text
seconds
```

UIは後phaseで作ればよい。

初期実装はconfig constantでもよいが、converter codeへ埋め込まない。

---

# 35. Synchronization clock

audio同期とanimationは `time.monotonic()` 基準にする。

```text
ritual_started_at = monotonic()
drop_at = ritual_started_at + (source_drop - source_start)
```

Tk `after()` は表示更新をscheduleするだけ。

`after(16)` を正確な音楽clockとして扱わない。

遅延した場合:

```text
elapsed = monotonic() - ritual_started_at
```

から現在phaseを決める。

遅れたcountdown frameを順番に全部再生しない。

---

# 36. Audio / animation cancellation

以下で安全にcleanup。

- converter failure
- Editor destroy
- New/Openで既存Convert operationが終了扱いになる場合
- app exit
- explicit Dopagaki OFF
- 新しいF5 ritualへ置換される場合

cleanup対象:

- audio subprocess / player
- pending `after`
- particles
- effect overlay
- countdown stamp
- temporary intensity override

既存converter workerは、既存仕様に従って扱う。

---

# 37. D3 phaseを更新

旧Phase D3を次のように扱う。

## Phase D3 — F5 Convert Ritual

実装:

1. audio backend abstraction
2. user-local audio path
3. cue / drop settings
4. F5開始時prelude
5. countdown
6. converter result latch
7. success/failure choreography
8. audio unavailable fallback
9. cleanup / leak tests

このphaseではF8専用演出はまだ不要。

### D3 completion criteria

- F5 converter出力が通常版と同一
- F5押下直後にconverter開始
- audioはconverterを遅らせない
- drop前にsuccessならdropまでvisual resultをhold
- failure時にsuccess表示なし
- audioなしでもF5成功
- ritual中もEditor操作可能
- repeated F5でcallback / process leakなし
- Editor closeでaudio停止
- modified / Undo / selection semantics不変

---

# 38. D3向けCodex prompt

```text
repositoryの dopagaki.md を最初から最後まで読んでください。
今回は Phase D3 — F5 Convert Ritual のみ実装してください。

重要:
通常のSave & Convert処理・converter semantics・outputを変更しないでください。

F5押下時:
1. 従来通りactive editをcommit
2. 従来通りSave
3. 従来通りconverter workerを即開始
4. 同時にDopagaki Convert Ritualを開始

Ritual:
- local user-provided JAXSON GAMBLE - Let's Go audioを使用可能にする
- repositoryへ楽曲をcommitしない
- cue start / drop timestampはDopagaki設定として分離
- 初期仮値:
  source start ≈ 47.8s
  major drop ≈ 51.45s
- exact timestampはWindows nativeで後から調整可能にする
- countdown 3 → 2 → 1
- dropで LET'S GO!!
- converter成功済みの場合のみsuccess finale
- converterがまだ処理中ならCHARGING等へ移行し、successを偽装しない
- converter failureならcountdown/finale cancel + failure effect
- audio/backend unavailableならvisual-onlyでF5を正常継続

animation:
- time.monotonic()基準
- Tk after()はschedulerだけ
- non-modal
- focus/selectionを奪わない
- Editor destroy時cleanup
- idle時callbackなし

playback backendは現行environmentを調査して、
最小依存で安全な方法を選んでください。
TkinterがWebM/Opusをnative再生できると仮定しないこと。

public repoへcopyrighted audioを追加しないでください。

tests:
- output equivalence
- early converter success
- late converter success
- converter failure
- no-audio fallback
- ritual cancel
- repeated F5 lifecycle
- editor destroy cleanup
- modified/Undo/selection invariants

開発途中で何度もTkを起動しない。
headless中心。
最後に必要ならWSLg real Tkを1回。

Windows nativeでのaudio cueの耳確認はユーザーが後で行います。
```

---

# 39. F5の最終思想

F5は単なるボタンではなく:

```text
編集の一区切り
→ 発射準備
→ countdown
→ music build
→ converter truth check
→ LET'S GO
→ 爆発
```

にする。

ただし絶対条件:

```text
演出がconverterより偉くならない。
```

成功していないものを成功に見せない。
音楽が無くてもConvertは壊れない。
Dopagaki演出はTAS作業を加速させる側に置く。
