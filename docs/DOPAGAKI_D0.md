# Dopagaki D0 — Branch + foundation

Formal contract: [dopagaki_v2.md](../dopagaki_v2.md), read in full, including
the later F5/D3 additions. This implementation is limited to Phase D0.
The branch starts at main/origin/main
`e35c3e49f912191fce2d8afed7a9a26ff7838fe0`.

## Run

```bash
python3 -m python_to_exe.main_dopagaki_jp
python3 -m python_to_exe.main_dopagaki_en
```

Direct script execution also works. The Converter's Edit action opens the
Dopagaki Editor. Existing `main_jp.py` / `main_en.py` still use the normal UI.

Use the Editor's **Dopagaki: Motion intensity / 演出の強さ** menu to choose
OFF, LOW, MID, or FULL. Default: MID. User settings store
`dopagaki_intensity` separately from scripts and Recovery snapshots.
Multipliers are 0.00 / 0.28 / 0.62 / 1.00. OFF retains the static theme and
creates no pulse items or animation timers. Changing level cancels the current
pulse; the next cell move uses the new level.

## Architecture

```text
main_dopagaki_jp.py / main_dopagaki_en.py
  DopagakiApp (inherits TASConverterApp)
    shared editor factory and conversion/validation/analysis callbacks
      DopagakiEditorWindow (inherits EditorWindow)
        DopagakiTableGrid (inherits TableGrid)
          CellEffects -> MotionController -> ActiveCellPulse
```

Dopagaki modules live in `python_to_exe/editor/dopagaki/`:

- `theme.py`: local dark navy chrome, cyan accents, bright neutral table/input
  surfaces. Existing fonts, geometry, syntax colors, style builders, and Stick
  Preview data remain shared. No global Tk or named-font mutation.
- `motion.py`: one finite effect and at most one pending `after(16)` callback.
  Progress uses `time.monotonic()`, with an injectable clock for headless tests.
  A delayed tick jumps to its current elapsed position or completion. No idle
  ticks, catch-up frames, animation history, Hype timers, or background threads.
- `effects.py`: one 180ms cyan cell-outline pulse. A transparent-fill Canvas
  rectangle has its own `dopagaki_effect` tag. Animation only updates that item;
  it does not redraw the table or create overlay widgets. LOW/MID/FULL change
  brightness and outline width. Rapid cell moves replace the previous pulse.
- `ui.py`: thin inheritance adapters, intensity menu, read-only observation of
  the normal grid draw result, scroll/header clipping, Unmap cancellation, and
  destruction cleanup. No selection or document operations originate here.

The common UI exposes theme/grid/editor class injection points. Converter and
parser implementations, document state, Undo/Redo, rectangular selection,
frame analysis, Debug CSV, and line-map semantics are reused without changes.
Tkinter and the Python standard library are the only runtime dependencies.

## Lifecycle and memory

Finite effects release their Canvas item and references on completion,
replacement, OFF/level changes, unmapping, and destruction. The controller's
scheduler and timer closure use weak references; generations invalidate late
callbacks without affecting replacement jobs. Editor destruction also closes
effects before destroying children, with Destroy handlers covering direct Tk
destruction. Finished effects are not retained by the effect manager.

The final real-Tk check also exposed an inherited Entry `StringVar` write-trace
retention after typing: widget destruction alone does not remove the variable's
Tcl command. The normal grid now records that trace's ID. The Dopagaki grid
removes it and releases the variable on destruction. This does not change
live editing, modified flags, history, or selection. The normal UI's existing
destruction behavior is otherwise unchanged.

## Verification (2026-10-01)

```bash
env DISPLAY= WAYLAND_DISPLAY= python3 -m unittest discover -s tests -q
python3 -m compileall -q python_to_exe tests tools
git diff --check -- python_to_exe tests tools docs/DOPAGAKI_D0.md
```

The headless suite has 331 tests: 238 pass, 93 GUI tests skip. D0 adds 22
headless tests for completion, idle, delayed ticks, replacement, stale callbacks,
OFF, level amplitude, destruction, collectability, local themes, settings,
document/history/selection isolation, scrolling, and resizing. Stress checks
cover 1000 cell moves and 30 Editor/grid cleanup cycles. A real Tcl interpreter
(without a Tk window) verifies removal of the Entry trace's actual Tcl command
and collection of the captured grid/Editor. The trace regression failed before
cleanup and passes afterward.

One WSLg Tk session was run using `tools/smoke_dopagaki_tk.py`. JP/EN,
coexisting normal theme, pulse completion, intensity menu/persistence, actual
Entry editing, Undo/Redo, rectangular selection, Palette/pages, Stick Preview,
scrolling, Raw/Table, Validate, and Save & Convert all passed. Mixed source
newlines remained byte-identical. After 100 real cell moves, registered grid
command count returned to baseline. Closing during a pulse removed both its
pending `after` event and its Tcl command; a stale tick did nothing.

That session's final weakref assertion failed due to the Entry trace described
above. The fix was validated with headless real-Tcl regression testing;
the GUI session was not repeated, respecting the one-session limit. Full
post-fix graphical weakref confirmation and Windows-native DPI/IME/PyInstaller
checks have not been run.

## D0 boundary

No particles, Hype accumulation/decay, combo, FEVER, audio, F5 ritual, giant
finale, or mascot. No automatic conversion, text mutation, focus changes, or
selection/scroll movement from effects. D1 and later require a separate task.
