# Dopagaki D1 — Micro Juice

Implemented only Phase D1 on `dopagaki`, starting at
`f742c8674a75d97a1bfc980d1e89edb3a1778c82`.
The formal reference remains [dopagaki_v2.md](../dopagaki_v2.md), read in full.
[D0](DOPAGAKI_D0.md)'s theme, JP/EN entrypoints, settings, MotionController,
weak references, generation guards and destruction cleanup remain in place.

## Feedback and timing

Durations in milliseconds:

| Target | LOW | MID | FULL | Presentation |
| --- | ---: | ---: | ---: | --- |
| Active cell | 150 | 180 | 200 | D0's immediate cyan accent, smooth crest and fade |
| Accepted changed cell commit | 150 | 180 | 210 | Stronger violet/pink border on the committed cell |
| Palette candidate | 120 | 160 | 190 | Button surface and border color pulse |
| LS / RS input | 140 | 180 | 210 | Corresponding unit-circle ring pulse |
| Frame Position | 120 | 170 | 200 | Only changed values briefly turn toward gold |
| Basic / Advanced page | 120 | 160 | 190 | Pager text briefly turns toward gold |

OFF cancels all current effects and starts none. D0's amplitude multipliers
remain LOW 0.28, MID 0.62, FULL 1.00. LOW is short and subtle; FULL has brighter
button accents and a clearly visible pink ring. Cell/commit stroke amplitudes
are 2/3 pixels above their 2-pixel base. Stick rings add at most 3 pixels of
radius and use a 1–4 pixel stroke. Fonts, widget sizes, images and text do not
animate. The D0 cell curve is retained; button/text/ring fades use
`(1 - progress) ** 1.5`.

Tab, Enter, their Shift variants, clicks and Palette-assisted commits use the
existing `_apply_editor_value` path. Feedback compares the actual accepted
model cell before/after that call. Rejected or unchanged contents emit no
strong pulse; unchanged commits also do not restart an already running one.
X11/WSLg reports Shift+Tab as `ISO_Left_Tab`; the Dopagaki Entry aliases it to
the existing Shift+Tab binding script, without registering another callback
or creating another history transaction.

Every Palette category uses the same button primitive, including Cappy,
Accel, Gyro, Notation and STAS Commands. The original Tcl insertion callback
runs before feedback, preserving text, caret, placeholder selection and
controller icons. LS/RS candidates also pulse their corresponding preview.
Preview redraws recreate only the ring overlay after the unchanged shared
plot draw. Resolved coordinates and the current/previous three-frame samples
remain authoritative; no interpolation or synthetic frames are introduced.

## Integration

```text
existing JP/EN Dopagaki entrypoints
  DopagakiEditorWindow / DopagakiTableGrid
    CellEffects: bounded named targets
      EffectBatch (finite D0 effect protocol)
        ActiveCellPulse / WidgetPulse / ValuePulses / RingPulse
      unchanged MotionController: monotonic clock + one Tk after(16)
```

- `theme.py` owns local colors and intensity timings. Normal theme tokens and
  named fonts are unchanged.
- `micro.py` contains the small finite primitives and batch protocol adapter.
- `effects.py` adds named slots to D0's observer and controller. Repeated cell,
  commit, button, page or stick effects replace their slot immediately.
- `widgets.py` supplies read-only Frame/Stick presentation adapters. Frame
  values are split from the shared editor's exact localized status string;
  frame numbers are not recomputed. Only changed value labels animate.
- `ui.py` supplies thin hooks into shared editing, insertion and page switching.
  Scroll/resize draws relocate cell/commit borders to the normal clipped boxes.
- The only shared `window.py` change is an optional Stick Preview class factory;
  its default still constructs the original normal preview. Animation logic
  stays in `editor/dopagaki/`. No runtime dependency was added.

Parser/converter, document, Undo/Redo, selection, Table model, frame analysis
and previous-3f implementations are unchanged from D0. Dedicated row/column,
delete and range-paste flashes are deferred because they would need additional
grid mutation hooks. Ordinary cell movement feedback still applies wherever
the normal grid moves the active cell.

## Lifecycle and memory

All targets share the original MotionController and at most one pending
animation callback. Actual D1 slots number seven; the adapter enforces a hard
limit of eight. Tracks retain absolute start times when a batch is replaced,
so unrelated actions cannot extend an old animation indefinitely. Removing
the longest track shortens the batch deadline. No history of effects is kept.

Completion/replacement/OFF/intensity changes/Unmap/destroy delete overlay
items, restore exact widget styles and release references. Widget and canvas
targets are weak references. Closed managers release their clock and canvas;
the D0 controller retains its weak scheduler/tick closures and generation
checks. D0's Entry variable-trace cleanup is also retained and now confirmed
with real-Tk post-fix Editor collection. Idle animation callbacks are zero.

## Verification (2026-10-01)

```bash
env DISPLAY= WAYLAND_DISPLAY= python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -q  # Opt-in WSLg real Tk
python3 tools/smoke_dopagaki_d1_tk.py     # Opt-in JP/EN interaction stress
python3 -m compileall -q python_to_exe tests tools
git diff --check
```

The suite has **344 tests**: all 344 pass with real Tk; headless passes 251
and skips 93 GUI tests. The previous 331 tests, including converter output
fixtures, remain. Thirteen new headless tests cover changed/no-op/rejected
commits, unchanged Palette text/placeholders/icons, unchanged resolved stick
values/history, exact Frame strings and changed values only, page state and
pending Entry isolation, OFF, amplitude/timing, absolute lifetimes, rapid
replacement, bounded targets, deadline shortening, destroy/stale callbacks,
effect weakref collection and the X11 Shift+Tab alias.

Seven WSLg smoke/probe sessions, including diagnostic runs, were used for D0
post-fix verification, key tuning and LOW/FULL visual inspection. The full GUI
suite ran separately. Final complete D1 checks **per language, JP and EN**:

| Operation | Repetitions |
| --- | ---: |
| Real arrow-key cell navigation | 1000 |
| Changed cell commits | 300 |
| Palette insertion | 300 |
| Basic / Advanced switches | 100 |
| LS / RS candidate input | 300 |

F2→edit→commit, Tab/Enter/Shift variants, click commit, Undo/Redo, controller
icons, placeholders, row-header and rectangular selections, scrolling,
Raw/Table, OFF/LOW/MID/FULL and 1000×650 / 1400×800 / 1200×700 resizing were
also checked. Existing Entry identity, position, focus handling and grid
hit-testing remain intact. The baseline smoke separately verified coexisting
normal theme, Validate and Save & Convert.

The final instrumented run observed cell reaction median **7.51ms JP /
7.81ms EN**, maximum **46.02ms JP / 27.73ms EN**. It checks the actual Tcl
timer list (animation cap one), bounded targets, stable button/grid Tcl command
counts, collection of every observed completed effect, zero idle animation
callbacks and Editor/grid/manager weakref collection after closing mid-effect.
Temporary source files remained byte-identical.

Actual LOW/FULL screenshots were inspected for button/ring strength, commit
border, resolved current/previous stick points, gold Frame values, unchanged
Total, readable text and stable layout. Japanese glyph boxes are the known
WSLg font limitation; Japanese insertion/labels/settings logic passed.

No D2 work, particles/confetti, Hype/combo, FEVER, audio/F5 ritual, giant
stamps/finale, screen shake or mascot is included.
