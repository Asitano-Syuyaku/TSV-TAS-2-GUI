# Dopagaki D3 — F5 Convert Ritual

Implemented on `dopagaki`, directly from
`a6522cfdf5c16f8957c9c367423eefa8893da8b0`. The full formal reference is
[dopagaki_v2.md](../dopagaki_v2.md); this checkout has no `dopagaki.md`.
The user's current D3 instructions and confirmed trimmed cue supersede the
older tentative 47.8s/51.45s cue in that specification. D0/D1/D2 remain the
foundation. No D4 FEVER or F8-specific finale is included.

D3.1 adds local WAV and standard Windows/WSL playback without changing this
timeline or result latch. See [DOPAGAKI_D3_AUDIO.md](DOPAGAKI_D3_AUDIO.md) for
the current backend priority and actual process verification; the measurements
below record the original D3 environment.

## Existing F5 behavior and result truth

The shared `EditorWindow.save_and_convert` is unchanged: active Table editing
is committed by the existing save path, the requesting file is saved, and
the existing converter worker starts with exactly the existing arguments.
Only after that request succeeds does the Dopagaki adapter start a ritual.
Rejected/busy/cancelled saves do not start a new ritual. F8 passes directly
to the original callback, without a D3 ritual.

The only shared conversion change is an inert presentation-observer method,
called on the Tk thread before existing success/error handling. Normal
entrypoints have no observer. `DopagakiApp` delivers one verified converter
result to a weak, generation-bound receiver, then drops the receiver. Worker
command building, parser, output checks, logs, dialogs and FTP are unchanged.
The original result dialog is still immediate; no new modal reward is added.

`ConvertRitual` keeps only a result boolean, never output/document snapshots:

- Early success: output/result is already complete; state is `SUCCESS_READY`
  and the visual reward waits for the drop.
- Drop before result: music stamp `LET'S GO!!`, small `CHARGING...` status,
  state `WAITING_FOR_CONVERTER`. No success wording or success burst.
- Late success: a fresh `CONVERTED` stamp/reward, including after audio ends.
- Failure: cancel phase callbacks, stop audio, remove ritual particles/stamps,
  then a short purple `CHECK OUTPUT` glitch and existing Problems/log accent.
  Existing converter error handling remains authoritative.
- New accepted F5, New/Open, explicit cancel, OFF, Editor unmapping or destroy:
  stop/clear the old ritual and invalidate its generation. The converter
  itself is not cancelled by presentation cleanup.

`CONVERTED` refers to that saved converter run. Later unsaved typing and its
modified/Undo state remain independent; there is no `CLEAN`/current-buffer claim.

## Audio policy and optional backend

No commercial media is tracked, copied into the repository, bundled or
rewritten. The confirmed user media is already trimmed:

```
Path.home() / ".local/share/tsv-tas-2-gui/dopagaki/lets_go_dopagaki.webm"
WebM / Opus / 48 kHz / stereo; approximately 97.427 seconds
original trim start: 29.913604 seconds
audio cue: trimmed 0.000 seconds
drop: trimmed 21.506 seconds (original 51.420)
```

`audio.py` provides `AudioBackend.play/stop/poll/close` and `FFplayBackend`.
ffplay is found on PATH or selected explicitly; no directory scan, download
or install occurs on F5. The subprocess uses an argv list and no shell:
`-nodisp -autoexit -loglevel error -nostats -volume 70 -i <local media>`.
Explicit Windows paths and WSL-local media for a Windows `.exe` are translated
using bounded `wslpath` calls. No personal absolute path is in product code.
stdin/stdout/stderr use DEVNULL, so no pipe-fill deadlock or GUI player window.

At most one owned player is allowed. Stop terminates/reaps it, escalating to
kill/reap after a 150ms termination timeout; a failed stop prevents replacement.
Natural/nonzero exit is polled at phase wakes and releases the process handle.
Missing media/player, translation/spawn exceptions and mid-playback errors
only select visual-only behavior. They never report a converter error.

`AudioSettings` stores `dopagaki_audio.json` beside the normal AppSettings
file. Normal AppSettings/TSV/Recovery/Undo formats are unchanged. Fields:

| Field | Default | Meaning |
| --- | --- | --- |
| `enabled` | true | Independent mute switch; OFF intensity also prohibits audio |
| `path` | empty | Use the home-relative candidate; selectable local override |
| `player` | empty | PATH ffplay; selectable explicit executable |
| `volume` | 70 | Integer 0–100 |
| `sync_offset_ms` | 0 | Positive = later visual phases; bounded ±2000ms |
| `tail_seconds` | 8.0 | Audio continues this long after drop; bounded 2–60s |

The Dopagaki F5 audio menu offers enable/mute, media/player selection, sync
offset and non-modal ritual cancellation. File/offset changes cancel the
current ritual and apply to the next run. Mute stops audio while visual
presentation continues. Settings writes are atomic; unavailable storage
retains the in-memory configuration. The 8s tail is an initial configurable
choice, not a claim of auditory tuning in this environment.

## Monotonic timeline

`ritual.py` uses `time.monotonic()` and absolute deadlines. T=0 is the audio
launch request, or the same visual start if audio is unavailable. External
player startup latency can be calibrated with the offset; it never enters
converter logic.

| T (s), default offset 0 | Event |
| ---: | --- |
| 0.000 | Immediate pulse, thin cyan edge, small burst |
| 6.000 | Pink build, Palette/Frame accent |
| 9.000 | Small occasional sparks |
| 12.000 | Gold tension edge/tape, Preview rings |
| 15.000 / 17.000 | Small occasional sparks |
| 18.506 | Cyan 3 |
| 19.506 | Larger cyan/pink 2 |
| 20.506 | Largest yellow/white 1, effect-only shake/rings |
| 21.506 | `LET'S GO!!`; success reward only if converter succeeded |
| 29.506 | Stop any still-playing audio; pending converter status can remain |

There is at most one phase `after` callback, aimed at the next absolute
event. A delayed wake skips missed phases/countdowns rather than replaying
them. Static build/waiting does not run an animation clock. The injected
`RitualTimeline` supports a short development timeline without changing any
production cue or adding a document setting.

The tail callback is omitted when no player is active at the drop. Drop/finale
edges and stamps finish with their finite animation, independently of audio
or remaining phase callbacks; even a much later success returns to ordinary
editing. A small pending status may remain until the converter result.

## D2 integration, intensity and rendering

`ritual_view.py` owns dedicated `dopagaki_ritual_static`/`dopagaki_ritual_stamp`
Canvas tags on the existing grid. There are no tag input bindings, focus
calls, widget moves or selection mutations. Grid hit-testing remains coordinate
based and the raised editing Entry stays above Canvas items. Scroll/resize
redraws relocate edges/stamps to the current viewport. In Raw mode a small
18px Canvas occupies only the unused right end of the existing status bar;
the Raw Text is never overlaid or modified. No Table layout height is added.

D3 reuses D2's particle list/surfaces, cap and analytic motion. A small optional
particle `owner` field allows cancelling only ritual particles, preserving
ordinary editing feedback. Ritual progress supplies temporary heat to particle
brightness/velocity/density through `0.08 + 0.92 * progress ** 1.3`; it does not
write to runtime Hype. D1 durations and OFF/LOW/MID/FULL multipliers stay intact.
Ritual-created micro pulses have at most four weak ownership records. Cancel
removes them only while they are still the current effect in that slot, so
subsequent ordinary editing feedback survives. Destroyed Tcl Canvas/banner
commands are tolerated during cleanup.

`JuiceEffect` accepts a weak ritual-view extension. Its finite deadline includes
the short stamp/edge pulse, so D3 still uses D2's eighth slot, the original
MotionController and at most one animation callback. Handoffs retain particle
births and detach old facades before replacing a stamp. Static decorations
have no MotionController lifetime/timer. No second particle engine exists.

| Parameter | LOW | MID | FULL |
| --- | ---: | ---: | ---: |
| Particle cap, across all surfaces | 30 | 90 | 180 |
| Startup grid burst | 2 | 4 | 8 |
| Drop grid burst | 5 | 16 | 34 |
| Success grid burst | 10 | 48 | 96 |
| Success extras per Preview | 1 | 6 | 12 |
| Stamp duration (ms) | 350 | 550 | 700 |
| Base countdown font (pt) | 24 | 46 | 70 |
| Effect-only shake maximum (px) | 0 | 1 | 3 |

3/2/1 use 0.8/0.9/1.0 of the base font and 0.6/0.8/1.0 border-pulse strength.
Only the stamp font bounces (0.90→1.08); normal fonts/layout never animate.
Long words fit the grid viewport using Tk's measured peak text width, cached
per stamp/viewport and recomputed on resize. Failures last 280ms; border pulses last
180ms LOW / 320ms MID-FULL. Canvas text/font/color updates are cached, and
static warning stripes repaint only when their visual signature changes.
The global hard ceiling remains 260, with D3 always using the lower user cap.
At an early FULL success, drop+success requests 154 particles before unrelated
editing particles; cap enforcement still limits the combined total to 180.

## Verification and performance (2026-10-01)

```
env DISPLAY= WAYLAND_DISPLAY= python3 -m unittest discover -s tests -q
python3 tools/smoke_dopagaki_d3_tk.py --output /tmp/dopagaki-d3-tk.json
python3 tools/smoke_dopagaki_d3_tk.py --realtime  # one full timeline, opt-in
python3 -m compileall -q python_to_exe tests tools
git diff --check
```

The suite has 407 tests: 314 pass headless, 93 existing GUI tests skip. All
previous 369 remain. The 38 new deterministic tests cover exact cue/countdown,
early/late success, failure before/after drop, pending truth, sparse/delayed
scheduling, cancellation/generation guards, 100 headless replacements, OFF,
missing media/backend/spawn/mid-playback failure, offset isolation, shell-free
Windows path handling, terminate/kill/reap and no-overlap guards, capped
particles, facade replacement, weakref collection, document/history/selection
isolation, exact Frame values, unchanged resolved/current/previous-three-frame
Preview values and existing converter arguments/result behavior. They also
cover absent-player tail omission, late-finale expiry, measured stamp resize,
destroyed Tcl commands and preserving user feedback during ritual cleanup. Existing
converter fixtures are unchanged. Real Tk compares an actual F5 output with
the normal companion command's output byte-for-byte in both JP/EN.

Four successful WSLg Tk sessions were used: representative JP/EN workflow,
visual/cache tuning plus ONE full 21.506s timeline, a short final
countdown/failure tuning check, and a targeted long-stamp/resize correction.
A separate import diagnostic failed before creating Tk and was fixed.
In total ten Editors were closed, including
mid-effect closes; no thousands of real inputs or repeated 21s waits. The
workflow uses 30 rapid arrows per language, one Tab edit and LS placeholder,
page roundtrip, Undo/Redo, rectangular selection, Raw/Table, scroll/resize,
LOW/MID/FULL/OFF, early/late/failure, cancel and second accepted F5. Pending
Entry identity/text/selection/geometry and focus are checked during countdown.
Screenshots confirm LOW/FULL contrast, readable caret, Preview rings, JP/EN
layout, stepped number sizes, short two-line success and purple failure.
The final check caught a clipped FULL `CHECK OUTPUT`; measured-width fitting
then passed at both 1200px and the 800px minimum window width.
JP glyph boxes remain the known WSLg font limitation.

Representative measurements (tick includes `update_idletasks`/paint):

| Observation | D2 recorded | D3 representative |
| --- | ---: | ---: |
| Cell reaction median | 8.75ms EN / 8.85ms JP | 9.57ms combined |
| Major ritual tick+paint median / p95 | — | 5.15 / 9.56ms |
| Phase callback median | — | 2.76ms |
| Idle animation/ritual callbacks after settle | 0 | 0 |

These are indicative local observations, not a controlled benchmark or strict
timing assertions. Major text rendering is heavier than D2 micro feedback,
but is bounded to at most 700ms; the 21s build is sparse/static. After the
first five close checks, Tcl commands stayed 199→199 and images 4→4; RSS was
45,868→46,132 KiB with bounded allocator retention. In the second warm sample,
objects/commands/images/RSS were unchanged at 24,171 / 199 / 4 / 46,308 KiB.
All observed Editors, rituals, views, effects, Hype/particle managers collected.
After settle/cancel/destroy, particles/items and both owned callback types
were zero. There were no player processes because ffplay is unavailable.

Existing Windows Desktop/yt-dlp contains FFmpeg/ffprobe but no ffplay, and
ffplay is absent from both PATHs. The user confirmed it was probably never
downloaded. No package was installed. Successful real audio playback and
auditory start/drop calibration are **not verified**; offset remains 0ms.
Missing-player fallback was verified with real Tk, and backend behavior with
deterministic subprocess stubs. One short Windows PowerShell process probe
also verified WSL `terminate()` stops the owned Windows process itself.

## Deferred work

D4 FEVER, F8/Send finale, mascot, new game/reward state, audio assets,
packaging and native Windows/DPI/audio calibration are not included. No
conversion is triggered by animations, no document reward state is saved,
and no new UI framework/dependency is introduced.
