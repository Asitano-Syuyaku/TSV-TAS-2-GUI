# Dopagaki D2 — Particles + Hype

Implemented on `dopagaki`, directly above D1 revision
`19b0ee981bdf4dd5ac5622d770a183da1e75d462`. The formal reference is
`dopagaki_v2.md`; this checkout has no `dopagaki.md`. D0/D1 remain the
foundation. The normal `main` branch is untouched.

## Architecture and isolation

`editor/dopagaki/hype.py` contains a small, clock-injectable Hype model.
`particles.py` owns one bounded particle list and four weak Canvas surfaces.
`juice.py` contains the small Palette meter and a finite `JuiceEffect` facade.
`CellEffects` connects these to the original, unchanged MotionController.

D1 has seven named effect slots; D2 uses its existing eighth slot, `juice`.
A repeated interaction replaces that facade, transferring the particle pool
without resetting individual birth times. The old facade detaches before its
finish method runs. CellEffects retains the pool/model, never completed
facades. Existing targets also retain their absolute start times through the
original finite batch transfer. There is still one controller/timer per grid,
with at most eight finite tracks and one pending animation callback.

Hooks live only in Dopagaki adapters. They observe the existing changed-cell
commit, Palette insertion, page switch and successful Go paths. Paste and row
duplicate use thin wrappers around their original methods and reward actual
changes only. Other row/column/delete operations are left to their unchanged
Table implementation. Frame values retain D1's changed-value-only pulse.

Converter/parser, document, Undo/Redo, selection, frame analysis, Stick
Preview resolution/history and shared window/grid/model code are unchanged.
Hype is runtime UI state, separate from persisted intensity. It is never
written to TSV, settings, Undo, Recovery, the document or converter output.
The normal entrypoint does not instantiate these modules or managers.

## Hype and intensity

```
H = clamp(H, 0.0, 1.0)
curve(H) = 0.08 + 0.92 * H ** 1.3
I = intensity_multiplier * curve(H)
H(now) = H(last_gain) * 2 ** (-(now - last_gain) / 5.0)
```

| Event | Gain |
| --- | ---: |
| Active cell move | 0.006, at most once per 120ms |
| Actual changed edit commit | 0.040 |
| Palette insertion | 0.060 |
| LS / RS Palette insertion | 0.070 |
| Basic / Advanced page switch | 0.015 |
| Successful frame jump | 0.070 |
| Changed paste / row duplicate | 0.080 |

Cell movement alone approaches a heat equilibrium below 0.4, even under
continuous arrow autorepeat; it cannot quickly fill the meter. No-op or
rejected commits and no-op paste do not receive their operation gain.

Decay has a five-second half-life, using `time.monotonic()` through the
existing clock injection. Interactions and active effect ticks sample decay.
Below 0.0005 it snaps to zero. There is no decay timer. The meter keeps its
last sample when idle; the next interaction reflects the elapsed cooling.
This deliberate sampled presentation preserves zero idle callbacks even
while the underlying Hype remains above zero.

| Intensity | Multiplier | Global particle cap | Presentation |
| --- | ---: | ---: | --- |
| OFF | 0.00 | 0 | No animations/gains; meter hidden; existing heat lazily cools |
| LOW | 0.28 | 30 | Small, muted bursts; no cell-navigation particles |
| MID | 0.62 | 90 | Clear local particles and accents |
| FULL | 1.00 | 180 | More particles, brighter colors and faster/wider bursts |

Changing intensity clears the active batch/particles/reward deadlines and
updates only presentation and the existing intensity setting. It does not
reset the runtime heat or change editing state. A hard ceiling of 260 also
exists; D2 never exceeds its lower per-intensity cap.

D1 timing is unchanged. Its baseline pulse remains visible at H=0; Hype
adds at most `0.16 * curve(H)` to its multiplier, clamped to 1.0, rather than
multiplying its visibility down by the Hype curve. Active-cell border
amplitude receives a small addition of `0.8 * curve(H)`. No text/font/Entry
size changes or layout animation occur.

## Particles and presentation

Particles use asset-free squares, circles, diamonds and short line sparks.
Each particle is a slotted record with origin/current coordinates, velocity,
birth time, lifetime, size, kind, color, gravity, weak surface and one Canvas
item ID. There are no PhotoImages, per-particle callbacks or retained trails.

| Event | LOW count | MID count | FULL count |
| --- | ---: | ---: | ---: |
| Changed commit | 1–2 | 3–5 | 6–10 |
| Palette insert | 1–3 | 4–7 | 8–14 |
| LS / RS | 1–3 | 4–7 | 8–12, plus the existing ring |
| Page switch | 0–1 | 1–3 | 2–5 |
| Successful frame jump | 1–2 | 3–5 | 6–9 |
| Changed paste / duplicate | 1–3 | 4–7 | 8–14 |
| Cell move, only H≥0.65 and admitted | 0 | 1 | 1; 2 at H≥0.85 |

Counts interpolate within these ranges with `curve(H)`. Speed is
`(35 + 90 * I) * random(0.75, 1.20)` px/s. Lifetime is 220ms through a
random upper bound of `400 + 120 * I` ms. Initial size ranges from 1px
through `1.8 + 1.7 * I` px, then shrinks/fades. Light grid colors are darker
for readability; dark meter/plot surfaces use neon accents. Birth color has
a visible baseline plus an I-scaled accent; fade uses twelve color steps.
When at cap, new particles are reduced/dropped after expired ones are deleted.

Origins follow the operation: committed/moved/jumped cell corner, the input
destination beside the raised editing Entry, the corresponding LS/RS unit
circle rim, or the pager's projected position on the meter strip. Palette
buttons retain their D1 pulse and controller icons. Entry remains above all
Canvas items; Palette particles appear just outside its edge so caret and
pending text remain visible.

Canvas items have only the dedicated `dopagaki_particle` tag, separate from
normal grid and `dopagaki_effect` / `dopagaki_ring` tags. They add no bindings
and no focusable widgets. Normal grid redraw raises only the particle tag
after its inherited draw; hit-testing remains the original coordinate logic.
Grid particles clip out the header/gutter. A changed scroll/resize viewport
cancels particles on that surface. Stick Preview's inherited delete-all draw
invalidates/recreates presentation IDs while preserving birth times and all
resolved current/previous-three-frame values.

The meter occupies a 14px strip plus 2px padding below the Palette heading,
without reducing Table height. Heat moves its thin bar from cyan to pink to
gold, with muted LOW and clear FULL levels. Milestones at 0.25/0.50/0.75/0.90
give a local `HYPE UP` label for 320ms. Each latch rearms only after cooling
below its threshold minus 0.08. H≥0.65 meaningful actions briefly accent the
Palette border for 180ms; H≥0.80 or a ≥0.75 milestone uses 280ms. This is a
small finite accent; there is no FEVER mode or giant stamp.

## Timing and lifecycle

The unchanged MotionController uses monotonic elapsed time and Tk `after`.
Particle positions are analytic (`origin + velocity * age`, plus gravity),
so delayed callbacks skip missed frames and immediately expire old records.
Coalesced interactions avoid re-sending old particle positions within 12ms;
new items appear immediately. Meter paint sends only changed pixel/color/
label values, and particle color calculation runs only on a new fade step.

Completion, replacement, OFF, intensity changes, Unmap and destroy remove
particle IDs and restore styles. Destroy closes the controller first, clears
the pool/surfaces/RNG/model, then releases target/clock references. Tk targets
are weak; the D0 weak scheduler, generation guard and Entry variable-trace
cleanup remain unchanged. No active finite effect/particle means callback 0.

## Performance and memory measurements

Measured with WSLg on 2026-10-01, using temporary files. D1 baseline at
`19b0ee9` observed cell reaction median 7.47ms JP / 7.53ms EN, maxima 28.10ms
/ 32.13ms. Its controller tick median was 0.294ms, p95 0.753ms. D2 operation
latencies are recorded by `tools/smoke_dopagaki_d2_tk.py`: JP median 8.85ms
(max 43.97ms), EN/FULL representative median 8.75ms (max 17.67ms). The
median increase over D1 was about 1.3ms. Palette median was 15.40ms JP and
11.04ms EN (max 66.63ms / 15.70ms). These runs had different repetition
counts, so the measurements are indicative rather than a controlled benchmark.

`tools/profile_dopagaki_d2.py` uses the existing injected clock for deterministic
heat/age/cooling while creating actual Tk Canvas items and timers. It consumes
each scheduled timer before driving its tick and separately flushes real
Canvas drawing with `update_idletasks()`. Tick and paint are measured apart;
these are local machine observations, not strict performance assertions.

| Scenario | Particles | Tick median / p95 ms | Tick + paint median / p95 ms |
| --- | ---: | ---: | ---: |
| LOW H=0, small burst | 3 | 0.213 / 0.353 | 0.401 / 0.502 |
| MID H=0.5, small burst | 7 | 0.321 / 0.554 | 0.498 / 0.822 |
| FULL H=1, small burst | 14 | 0.496 / 0.863 | 0.802 / 1.147 |
| LOW H=1, cap | 30 | 0.622 / 1.007 | 0.875 / 1.429 |
| MID H=1, cap | 90 | 1.024 / 2.321 | 1.441 / 3.979 |
| FULL H=1, cap | 180 | 1.337 / 2.197 | 1.666 / 2.956 |

The complete matrix covers H=0/0.5/1 with bursts and cap for every enabled
intensity, plus idle and OFF. Across the matrix maximum tick+paint was 4.791ms.
Grid item count started at 368 and reached 398/458/548 at LOW/MID/FULL caps;
all registered Canvas surfaces totaled 411/471/561. Each expired cohort's
weakrefs collected and object count returned to 27,435 after each measured
case. Idle/off animation callbacks and particles were zero.

Before the testing-policy update, the lifecycle profile completed 100 Hype 0→1→decay cycles, 100 FULL cap
cycles, 100 intensity switches, 30 normal Editor open/closes and 30
mid-particle destroys (alternating JP/EN). Document, Undo availability and
selection were unchanged. Live-Editor snapshots: Python objects 27,433→27,431,
particles 0→0, Tcl commands 859→859, images 20→20; RSS 42,904→44,488 KiB.
After warmup, 60 close cycles: objects 23,354→23,354, commands 199→199,
images 4→4, RSS 44,488→44,488 KiB. Editors, grids, CellEffects, Hype,
ParticleSystem and meters all collected. Separate tracemalloc stress used
323,855 bytes peak and retained 7,279 bytes after GC, including profile state.
The initial RSS increase was bounded allocator/backend warmup; no growing
particle/effect/widget/image/Tcl-command population was observed.

## Verification and visual tuning

```bash
env DISPLAY= WAYLAND_DISPLAY= python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -q  # Opt-in real Tk
python3 tools/smoke_dopagaki_d2_tk.py --output /tmp/dopagaki-d2-interactions.json
python3 tools/profile_dopagaki_d2.py --output /tmp/dopagaki-d2-profile.json
python3 -m compileall -q python_to_exe tests tools
git diff --check
```

The suite contains 369 tests, retaining all previous 344. Headless passes
276 and skips the existing 93 GUI tests. The real-Tk full suite passed all
367 tests before the last two deterministic tests were added; those last two
also pass headless, and the 93 GUI tests are unchanged. The 25 additions cover
gains/clamp/curve/decay/autorepeat/hysteresis, OFF/intensity, capped spawning,
expiry/frame skipping, scroll/resize/unmap isolation, redraw preservation,
finite transfer/idle, stale callbacks, weakref collection and presentation
isolation from document, selection, Palette text/placeholders/icons, Stick
Preview values/history and exact Frame strings, plus 100 heat→cap→expiry
cycles and 100 intensity switches with stale generation callbacks entirely
headless. Existing converter fixtures
remain unchanged. GUI stress checks real Undo/Redo and pending Entry state.

After the user's testing-policy update, the drivers were reduced to
representative operations: cell 100, commit/Palette/LS-RS 40 each, page 20;
the profile uses three heat/cap samples, eight intensity switches and three
normal plus three mid-particle Editor closes. They contain no input pacing
sleep. Long repetition belongs in deterministic unit tests. The earlier
large real-Tk results above are historical evidence, not instructions to
repeat them. No further large GUI stress was run after the policy update.

JP/EN LOW/MID/FULL snapshots were inspected at low/medium/high heat, for
Palette input and both stick rims. Visual tuning kept sparks outside the
Entry, added redraw tag raising, cached redundant paints and preserved the
D1 timing/typography/layout. Japanese glyph boxes remain the known WSLg
font limitation. Approximately fourteen real-Tk process launches were used,
including baseline, two profiles, visual probes, diagnostic/partial workflow
runs, three minimal connection checks, the GUI suite and the final EN
representative run. Before the policy update, three long workflow attempts
were interrupted by Xwayland exit code 134. Its stderr reported
`request could not be marshaled: can't send file descriptor`; the cause was
not established. WSLg restarted. JP completed its earlier workflow and EN
completed the final representative workflow; profile, visual inspection
and the existing GUI suite also passed. This environment limitation remains
recorded instead of claiming that every long GUI stress attempt succeeded.
Finite-effect start assertions run before possibly delayed GUI updates;
cleanup checks run after expiry, without strict wall-clock assertions.

The workflow checks F2/edit, Tab/Enter/Shift variants, click commit,
Undo/Redo, controller icons and placeholder ranges, LS/RS, page persistence
with a pending Entry, exact Frame Position values, row-header/rectangular
selection, scroll, Raw/Table, all intensity levels, and 1000×650 / 1400×800 /
1200×700 resize. Source files remain byte-identical. Every observed completed
effect and closed Editor/grid/manager collects; animation timers peak at one
and idle at zero. Final EN observed the FULL cap of 180 without leaving items.

## Deferred work

D3 and later phases are not implemented: no Validate/Convert hype surge,
FEVER, F5 ritual/music/audio/countdown, Convert/Send finale, F8-specific effect,
full-screen shake, mascot, modal rewards or permanent large HUD. No new UI
framework or dependency is introduced.
