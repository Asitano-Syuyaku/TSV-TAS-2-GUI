# Dopagaki D3.1 — Native Audio Enablement / Verification

Implemented on `dopagaki` from `1c266665e2447821e896c848766e6eccf7ad6169`.
This updates only D3 audio selection/backends. D3's monotonic timeline,
converter result latch and visual effects are unchanged. No D4 or F8 finale.

## Local-only WAV preparation

Windows Desktop was obtained using
`[Environment]::GetFolderPath('Desktop')`, then converted using `wslpath`.
Existing `Desktop/yt-dlp/ffmpeg.exe` and `ffprobe.exe` were used. Nothing was
installed or downloaded. All commercial audio remains outside the repository:

```
~/.local/share/tsv-tas-2-gui/dopagaki/lets_go_dopagaki.webm
~/.local/share/tsv-tas-2-gui/dopagaki/lets_go_dopagaki_f5.wav
```

The confirmed WebM was converted once with the following FFmpeg arguments.
WSL paths were translated to Windows paths using `wslpath -w`; `-n` refused
overwriting an existing output. No source seek, cue change or WebM rewrite:

```
ffmpeg.exe -hide_banner -v error -n -i <source Windows path>
  -map 0:a:0 -vn -map_metadata -1 -af asetpts=PTS-STARTPTS -t 30.250
  -c:a pcm_s16le -ar 48000 -ac 2 -f wav <output Windows path>
```

Windows ffprobe and Linux `file` verified:

| Field | WAV |
| --- | --- |
| Container | RIFF/WAVE |
| Codec | `pcm_s16le` |
| Duration | 30.250000 seconds |
| Sample rate | 48,000 Hz |
| Channels | 2 / stereo |
| Size | 5,808,078 bytes (about 5.54 MiB) |
| SHA-256 | `a42b73169cb6ceaf3cdc4f55c5f47d931b644bfc17c6200b3b4b3e71383f336b` |

The source SHA-256 stayed
`cb5ebfae072077eeea703fdb07b105bc8606f6c76783055f45d6948eb4e6e9d0`.
Two short decoded PCM comparisons were sufficient; no new musical/cue analysis:

| Region | Stereo frames | Comparison at the same time position |
| --- | ---: | --- |
| 0.000–1.000s | 48,000 | All s16le samples identical, maximum difference 0 |
| 21.106–21.906s, around drop | 38,400 | All s16le samples identical, maximum difference 0 |

Both comparisons had zero sample offset. The WAV includes the confirmed
21.506s drop and 29.506s tail stop with 744ms of remaining source audio.
No media, `.gitignore` change or personal absolute path is tracked in product
code. WAV generation is a one-time local operation, never automatic on F5.

## Lightweight backend selection

`audio.py` keeps the existing `AudioBackend.play/stop/poll/close` interface and
`FFplayBackend`. `create_audio_backend(config)` returns an `AutoAudioBackend`
with at most two candidate objects and one active player:

| Environment | First for PCM WAV | Fallback |
| --- | --- | --- |
| Native Windows Python | `WinSoundBackend` | Explicit/PATH ffplay, then visual-only |
| WSL | `SoundPlayerBackend` via existing `powershell.exe` | Explicit/PATH ffplay, then visual-only |
| Other Linux/platform | ffplay | Visual-only |

The default local candidate is `lets_go_dopagaki_f5.wav` when it exists;
otherwise `lets_go_dopagaki.webm`. Existing explicit media/player overrides
and `dopagaki_audio.json` schema remain. A WebM override goes to ffplay;
neither standard Windows backend receives compressed media. Selecting ffplay
sets the fallback player rather than changing the native-WAV priority.

Construction does not open WAV or launch a player. Only F5 opens its small
WAV header to validate PCM and derive duration. Python never reads/retains
the PCM payload; filenames are passed to the Windows player. Native backends
use the Windows mixer volume; the existing `volume` setting applies to ffplay.
The independent enable/mute setting and OFF intensity stop all selected audio.

### Native Windows

`WinSoundBackend` imports the standard `winsound` module at playback time and
calls `PlaySound(filename, SND_FILENAME | SND_ASYNC | SND_NODEFAULT)`.
`PlaySound(None, 0)` stops playback. This avoids default system beeps and adds
no player process, Python thread or Tk callback. `poll()` is an estimate from
the WAV header duration and monotonic clock, not an audio-device query.

PlaySound is process-global. A weak owner ensures a new playback replaces
the old one while an older Editor's cleanup cannot stop a newer owner. If
the prior owner's stop fails, replacement/fallback is blocked. Native Windows
API behavior was tested with deterministic module stubs; native Windows Python
was not run in this WSL session.

API reference: [Python winsound documentation](https://docs.python.org/3/library/winsound.html).

### WSL / Windows SoundPlayer

`SoundPlayerBackend` launches one Windows PowerShell subprocess without a shell:

```
powershell.exe -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden
  -EncodedCommand <UTF-16LE base64 fixed script>
```

The script takes the Windows filename as UTF-8 base64 data, assigns
`SoundLocation`, calls `Load()` then `PlaySync()`, and calls `Stop()`/`Dispose()`
on normal exit. User paths never become executable PowerShell fragments.
Explicit local WAV validation and `Load()` precede playback; invalid data does
not request the library's default beep. File loading/playback runs in the child.

The existing subprocess lifecycle is shared with ffplay: at most one owned
process, terminate/wait, kill/wait on timeout, natural/error exit reaping and
no-overlap guard on failed stop. stdin/stdout/stderr are DEVNULL; no pipes can
fill. A mid-play failure is noticed at an existing sparse phase wake and
continues the visual ritual, without a restart or converter error.

API reference: [Microsoft SoundPlayer.PlaySync documentation](https://learn.microsoft.com/en-us/dotnet/api/system.media.soundplayer.playsync?view=windowsdesktop-9.0).

## Timeline and calibration

No timestamps or scheduler logic changed:

| Phase | Source/ritual time (s) |
| --- | ---: |
| Start | 0.000 |
| 3 | 18.506 |
| 2 | 19.506 |
| 1 | 20.506 |
| Drop | 21.506 |
| Tail stop | 29.506 |

`sync_offset_ms` remains 0 by default. Player launch/load/device latency is
environment-dependent. No fixed correction was added. Process liveness and
visual deadlines do **not** certify audible start/drop alignment. Auditory
calibration remains pending the user's own listening.

Save/converter request still precedes player launch. Early success remains
latched for drop; late success remains separate from `LET'S GO!!`; failure
remains truthful. Backend selection changes neither documents, Undo, selection,
Hype, particle caps nor D3's sparse callback ownership.

## Representative real verification — 2026-10-01

The opt-in `tools/smoke_dopagaki_d31_tk.py` uses temporary editor documents and
settings. It performs short standalone/cancel/replace/close/OFF cases; its
`--production` flag runs one full timeline. `--skip-standalone` avoids repeating
an already verified standalone case. It never installs or generates media.

```
python3 tools/smoke_dopagaki_d31_tk.py --production --output /tmp/dopagaki-d31-tk.json
```

Eight SoundPlayer process launches occurred in total, including three short
diagnostic attempts while fixing the verification harness. There were two Tk
sessions and three Editor closes, and **only one production 29.506s run**.
The diagnostics handled locale-encoded PowerShell progress stderr, the expected
nonzero Get-Process status for an absent PID, and ordinary D1 commit feedback
remaining briefly after F5 cancellation. No production timeline/effect change
was needed. Previously verified standalone playback was not repeated in the
final successful Tk run.

Completed representative checks:

- Standalone WAV player survived several seconds, then terminated/reaped.
- JP F5 committed the active Entry and started the normal converter plus real
  SoundPlayer; a short development ritual cancelled its audio and phase job.
  The independent commit pulse finished naturally.
- A second accepted F5 reaped the first player before launching its replacement.
  The second player was stopped/reaped when the Editor closed.
- EN OFF still saved/converted with no audio/animation; native converter output
  matched the normal companion command byte-for-byte.
- EN FULL production run got converter success at 0.464s, latched until drop,
  then stopped audio near the configured tail. Document/selection/Hype stayed
  unchanged during the ritual.

Recorded Windows player PIDs in the final successful run were 30040 (cancel),
13048 (first F5), 6780 (replacement/close) and 28120 (production). Windows CIM
queries matched only the owned encoded SoundPlayer command, not other audio
or PowerShell sessions. After each stop, the WSL child had a reaped return code
(-15) and a Windows PID lookup confirmed absence. Maximum simultaneous player
count was one; no owned PowerShell process, zombie or audio callback remained.
Closed Editors/rituals/views/effect managers collected via weakref checks.

Production observations, not strict timing assertions:

| Observation | Actual elapsed |
| --- | ---: |
| Player launch call after ritual origin | 11.858ms |
| Countdown 3 / 2 / 1 callbacks | 18.507 / 19.507 / 20.507s |
| Drop callback | 21.507s |
| Tail callback | 29.508s |
| Player launch-to-stop observation | 29.497s |

Launch is not measured audible onset. No PCM buffers are retained in Python.
After tail, owned animation/phase callbacks and particle objects were zero.
No repeated long production waits or thousands of real input events were used.

## Tests and scope

```
env DISPLAY= WAYLAND_DISPLAY= python3 -m unittest discover -s tests -q
python3 -m compileall -q python_to_exe tests tools
git diff --check
```

433 tests: 340 pass headless, 93 existing GUI tests skip. All 407 D3 tests
remain; 26 deterministic audio tests were added. They cover platform priority,
WAV/WebM defaults and overrides, header-only loading, native async flags,
duration-derived poll, global weak owner, failed-stop guards, safe encoded
PowerShell paths, missing/invalid media/backend, spawn/translation/device
failure, replacement/close/reap, natural/mid-play exit, generation guards,
OFF, cancellation and visual-only fallback. Real 30s playback is opt-in and
is not part of unit tests. Existing converter fixtures/arguments and D3
early/late/failure truth, document/history/selection tests all remain passing.

No D4 FEVER, F8 finale, new visual system, commercial asset, audio dependency
or document reward state is included. User auditory calibration and packaged
native Windows/device verification remain separate follow-up work.
