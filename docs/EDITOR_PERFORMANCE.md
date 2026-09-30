# Editor performance / memory measurements

## 対象と方法

変更前: `7c8b9e6e848c3ae0032586e6afe961b0cfbe4448`。Linux/WSLg、Python 3.12、Tk 8.6で計測しました。新しいruntime dependencyや常駐profilingは追加していません。

- GUI: `5\tls(90)\trs(180)\ta\n` を10,000行、converterで50,000 frameへ展開。
- CSV単独: `50000\tls(90)\trs(180)\ta\n` を既存converterの `-dm` で展開した44列のDebug CSV。
- Python allocation: `tracemalloc.start(1)` のcurrent / peak。Tcl/Tk native allocationやchild converterのRAMは含みません。
- RSS: Linux `/proc/self/status` の現在値。Python allocator、Tcl/Tk、tracemalloc自身の管理領域も含みます。
- 時間: CSVはtracingなしの3回中央値。GUI操作はtracingなしの30回中央値（Raw/Tableは5回）。起動・load・background完了はtracingありで別記しました。
- GUIは同じTk processを継続して測定し、変更後のmoduleをreload。変更後3回の測定で、大型cacheとwindowの回収を確認しました。

## 最も大きかった保持データ

Debug CSVの文字列と44-field row tuple、1P stickの8個のfloat、frameごとのrecordが主なallocationでした。変更前はInspectorを閉じてもEditorの参照が残り、全CSVと元document snapshotが保持されていました。

| CSV単独 / 50,000 rows | 変更前 | 変更後 |
| --- | ---: | ---: |
| Inspector全field: Python current | 56.505 MiB | 26.417 MiB |
| Inspector全field: Python peak | 56.950 MiB | 26.946 MiB |
| Inspector全field: RSS、tracingあり | 160.086 MiB | 62.801 MiB |
| Inspector全field: 読み込み中央値 | 154.505 ms | 243.345 ms |
| Preview: Python current | 26.473 MiB | 12.741 MiB |
| Preview: Python peak | 82.978 MiB | 12.777 MiB |
| Preview: RSS、tracingあり | 210.914 MiB | 48.645 MiB |
| Preview: 読み込み・projection中央値 | 493.814 ms | 379.914 ms |

RSS表はmodeごとに新しいPython processを使用しています。GUI全体のRSSやWindows working setの削減値ではありません。大量の同一controller stateが繰り返すfixtureなので、常に変化するmotion等では文字列・float共有の効果は小さくなります。

全CSVの文字列共有には約89 ms / 50,000 rowsの追加コストがあります。約30 MiBの保持allocation削減と引き換えに採用しました。全fieldや未知の追加columnは欠落させていません。

## GUI各段階

| 状態 | 変更前RSS | 変更前Python current | 変更後Python current |
| --- | ---: | ---: | ---: |
| A. Editor起動、Raw | 37.250 MiB | 0.946 MiB | 0.294 MiB |
| B. 空TSV、Table | 37.617 MiB | 0.952 MiB | 0.295 MiB |
| C. 10,000行load | 47.828 MiB | 4.016 MiB | 3.360 MiB |
| D. Basic Palette | 47.828 MiB | 4.017 MiB | 3.361 MiB |
| E. Advanced Palette | 47.828 MiB | 4.018 MiB | 3.363 MiB |
| F. background解析完了 | 246.984 MiB | 32.492 MiB | 17.575 MiB |
| G. Frame Inspector表示 | 304.281 MiB | 89.224 MiB | 44.190 MiB |
| H. Inspectorを閉じた後 | 304.539 MiB | 89.215 MiB | 17.579 MiB |

A～Eの差には初回importとwarm processの差が含まれるため、最適化によるstartup削減とは扱いません。同じ理由で、変更後GUI RSSの比較は行いません。変更後のprocessは変更前計測のallocator領域を保持し、約339～343 MiBでした。

解析による保持allocationの増分（F−A）は31.546→17.281 MiB。GUIでの解析・Inspector込みのPython peakは91.612→46.692 MiBです。

| GUI操作時間 | 変更前 | 変更後の3回の範囲 |
| --- | ---: | ---: |
| 起動、tracingあり | 134.831 ms | 141～152 ms |
| document load、tracingあり | 136.614 ms | 61～102 ms |
| load後の解析完了待ち、tracing・debounce込み | 4457.037 ms | 3384～3420 ms |
| Table redraw | 2.815 ms | 2.755～3.324 ms |
| single selection + redraw | 8.452 ms | 8.324～9.850 ms |
| range selection + redraw | 10.534 ms | 11.391～13.000 ms |
| vertical scroll | 9.698 ms | 10.143～11.764 ms |
| horizontal scroll | 8.528 ms | 6.484～6.946 ms |
| Basic→Advanced→Basic | 16.575 ms | 19.170～22.324 ms |
| Table→Raw→Table | 32.841 ms | 28.735～30.174 ms |

Tk描画・Palette・document処理は変更していません。上記のばらつきを改善・劣化の断定には使いません。startup高速化やtyping latency改善も主張しません。

## 採用した変更

1. **Inspector close時の参照解放**: 全CSV、Inspector参照、解析snapshotを解放。古いwindowのclose callbackが新しいwindowを消さないようidentityで確認。
2. **Previewの逐次CSV読み込み**: 同じheader・row検証を共有し、全44列cacheを作らず1P stick値だけを保持。2Pの壊れた非空rowも従来どおりerror。
3. **読み込み内だけの共有**: full CSVの繰り返す文字列と、Previewの繰り返す有限floatを共有。cacheには上限があり、読み込み終了後は破棄。global interningは使用しない。
4. **小recordのslots**: `StickState` / `StickFrame` / `LinePosition` のinstance dictionaryを省略。stick recordだけで約4.58 MiB減ることを独立計測し、採用。既存のPython 3.9互換性を狭めないよう、`dataclass(slots=True)`ではなく明示的な`__slots__`を使用。

converter scripts、command builder、snapshot / debounce / stale判定、Tk threading、UI appearance、Undo / Recovery / save処理は変更していません。

## 採用しなかった変更

- Canvas item pool: 30 redrawのprofileではcreateが主な処理でしたが、redraw中央値は約2.8 ms。今回の大きなcache削減を優先し、selection/header/Entry位置への変更リスクを増やしませんでした。
- Palette lazy生成: Basic / Advanced切替のallocation差は約0.002 MiB。両pageのwidgetや16個のPhotoImageを現状のまま維持。
- Stick Preview item pool: 更新はkeyで既に抑制され、各plotは12 item以下。変更に見合う効果を確認できませんでした。
- document / Raw / Table / Undoの統合: newline保持、Undo、Recovery、external guardのbaselineに必要な表現があるため、保存安全性へ影響する変更は行いませんでした。
- line mapの新しいindex: active rowは既にdict lookup。大量selectionやframe逆引きに新しいcacheを常時足す必要は確認できませんでした。

## 解放確認と回帰検証

同じTk sessionで変更後に50,000-frame Analyze / Inspector開閉を3回、Editor開閉・New・Palette往復を合計30回実行しました。各回のGC後にEditorWindow、FrameInspector、DebugFrames、StickFrame、StickState、LinePosition、PhotoImage、Fontは0件。Inspector close直後にもInspectorと全CSVのweak referenceが消えました。RSSが完全に戻らないことと、Python objectが生存し続けることは区別しています。

追加回帰テストは、streamingとfull CSVの値一致、1P/2P・frame欠落・duplicate・non-finite・日本語・Windows空record・未知column、壊れた2P rowの拒否、閉じたInspectorのcache解放、古いclose callbackからの保護を対象にしています。実Tk testではAnalyze / Inspector開閉とOpen / Newを反復します。

最終確認: `python3 -m unittest discover -s tests -q` はWSLgで**309件すべて成功、skipなし**。Python syntax checkと`git diff --check`も成功。既存Palette testの見出し検出を、以前から使われているnested Preview headingへ対応させました。runtimeのPalette layoutは変更していません。

変更前の50,000-frame fixtureと再生成したbinary（7,400,284 bytes）、Debug CSV（6,789,189 bytes）、source-line map（76 bytes）はbyte単位で一致しました。実TkのFrame Inspector全field表示、cached preview、Raw/Table、navigation、Undo、Recovery、backup、F5/F8、JP/ENも既存suiteで確認しています。Windows nativeとPyInstaller実行は未確認です。

## 再計測

既存converterでDebug CSVを生成した後、repository rootで各modeを別processとして実行します。benchmarkは入力CSVを変更せず、正常起動時には実行されません。

```sh
python3 -m tools.benchmark_debug_cache path/to/script-debug.csv --mode full
python3 -m tools.benchmark_debug_cache path/to/script-debug.csv --mode sticks
```

WindowsでもPython allocationと時間を測れます。Linux RSSを取得できない環境ではRSSは`null`です。native Windows / PyInstallerのmemory・latencyは未計測です。
