# WAV Takes to AAF Converter — Technical Spec

## 1. Overview

A macOS command-line script that takes a folder of multitrack WAV recordings (organized by "take") and produces a single AAF file that, when imported into Logic Pro, lays out all takes sequentially on a unified set of tracks with a configurable silence gap between takes.

This script does **not** parse Pro Tools `.ptx` files. The `.ptx` file is ignored. The WAV files and their filesystem timestamps are the sole source of truth for grouping and ordering takes.

### Goal

Replace the current manual workflow of grouping WAVs by Date Modified into "takes" and importing each take separately into Logic Pro. Output a single AAF that Logic imports in one step.

### Non-goals

- Preserving Pro Tools edits, fades, automation, or plugin parameters
- Parsing `.ptx` files
- Cross-platform support (macOS only)
- Batch processing multiple project folders in one invocation
- Any modification of source WAV files

---

## 2. Inputs and outputs

### Input

A path to a folder containing WAV files. Filename pattern:

```
<TrackName>_<TakeNumber>.wav
<TrackName>_<TakeNumber>-L.wav   (left channel of a stereo pair)
<TrackName>_<TakeNumber>-R.wav   (right channel of a stereo pair)
```

Examples from the real data:
- `Snare Top_11.wav` — track "Snare Top", take 11, mono
- `Overhead_11-L.wav` — track "Overhead", take 11, left of stereo pair
- `Overhead_11-R.wav` — track "Overhead", take 11, right of stereo pair
- `Kick Outside_07.wav` — track names may contain spaces

Track names and take numbers are extracted by regex. Take number is zero-padded but should be parsed as an integer (treat `_03` and `_3` as equivalent).

### Output

A single `.aaf` file written to a user-specified location (default: alongside the input folder). The AAF references the original WAV files by absolute path; it does **not** embed media. Source WAV files are never modified.

### Side outputs

- A human-readable preview (always printed to stdout) showing the detected takes, ordering, track layout, and final timeline positions.
- A log file (optional, `--log <path>`) capturing the same information plus warnings.

---

## 3. Constraints and environment

- **Platform**: macOS only. Tested on macOS Sequoia and Tahoe, Apple Silicon (M1).
- **Python**: 3.11 or newer (use whatever ships with a recent Homebrew Python or the user's preferred pyenv).
- **Source files are read-only**: the script must never modify, move, rename, or delete WAV files in the input folder.
- **Logic Pro AAF import requirement**: Logic must have "Enable Complete Features" turned on in Preferences > Advanced for AAF import to be available. The script's README should mention this.
- **Single project at a time**: no batch mode, no folder-of-folders processing.

---

## 4. Core logic

### 4.1 Take detection and grouping

1. Scan the input folder non-recursively for `*.wav` files.
2. For each WAV:
   - Parse filename with regex: `^(?P<track>.+?)_(?P<take>\d+)(?:-(?P<channel>[LR]))?\.wav$`
   - If the filename does not match, log a warning and skip the file. Do not abort.
   - Read the file's `mtime` (modification time) via `os.stat`.
   - Read the WAV header to extract sample rate, bit depth, channel count, and duration in samples. Use Python's stdlib `wave` module; if a file fails to parse, log a warning and skip it.
3. Group files by **take number** (the parsed integer from the filename). Each take is a set of WAV files sharing the same take number.
4. Within a take, identify stereo pairs by matching `-L` and `-R` suffixes on the same track name. A stereo pair is treated as **two separate mono tracks** in the AAF (per user requirement). Files without `-L`/`-R` suffix are mono tracks.

### 4.2 Take ordering

Takes are ordered by the **earliest mtime among the files in that take** (timestamp wins). The take number is used only as a label and grouping key, never for ordering.

If two takes have mtimes within 5 seconds of each other (unlikely but possible), order by take number as a tiebreaker and log a warning.

### 4.3 Track layout

- Determine the union of all track names across all takes.
- Sort track names **alphabetically** (case-insensitive, locale-independent — use Python's default string sort on lowercased names).
- Each unique track name becomes one Logic Pro track in the AAF output.
- For a given Logic track, all takes' WAV files for that track name are placed sequentially on the timeline.
- If a particular take is missing a particular track (e.g., take 3 has no `Keys` recording), that track's slot in that take is simply silent / empty. The track still exists in the AAF; it just has no clip in that take's time window.

### 4.4 Timeline positioning

Timeline starts at 00:00:00.

For each take, in chronological order:

1. Compute the take's duration as the **maximum sample count** across all files in that take. This handles the (real-world) case of files within a take having slightly different lengths.
2. Place every WAV file in that take at the take's start position on its corresponding Logic track. WAV files within a take are aligned to each other at sample 0 of the take.
3. After the take, advance the timeline cursor by `take_duration + gap_seconds`.

The gap value is configurable via CLI flag (`--gap-seconds`, default 60).

### 4.5 Sample rate and bit depth

- Read sample rate and bit depth from each WAV. Use the most common values across all files as the AAF's session rate and depth.
- If any file disagrees with the chosen session rate or bit depth, log a warning listing the dissenting files. Do not abort. (The AAF can still reference files of differing rates; Logic will handle conversion on import, though the user should be aware.)
- Expected default for this user's sessions: 48 kHz, 24-bit. Do not hardcode this — detect.

---

## 5. CLI interface

```
wav-takes-to-aaf <input_folder> [options]

Positional arguments:
  input_folder            Path to folder containing WAV files

Options:
  -o, --output PATH       Output AAF file path
                          (default: <input_folder>/<input_folder_name>.aaf)
  -g, --gap-seconds N     Silence gap between takes, in seconds (default: 60)
  --write                 Actually write the AAF file. Without this flag,
                          the script runs in preview mode only.
  --log PATH              Write detailed log to this file (in addition to stdout)
  -v, --verbose           Verbose output (per-file details)
  -h, --help              Show help and exit
```

### Default behavior: preview mode

By default, the script analyzes the folder and prints the planned timeline to stdout, but does **not** write the AAF. The user reviews the preview, then re-runs with `--write` to actually generate the file.

Rationale: weekly recurring use means take detection edge cases (missing files, weird filenames, mtime surprises) are the most likely source of bad output. A preview-by-default flow catches them in 2 seconds before writing a file Logic will then need to import.

### Preview output format

```
Input folder: /Users/matt/Music/SessionFolder
Found 168 WAV files, parsed 167 (1 skipped — see warnings)

Detected sample rate: 48000 Hz (all files agree)
Detected bit depth: 24 bit (all files agree)

Tracks (alphabetical, 14 total):
  Ben, Colby, Edrums, Keys, Kick Inside, Kick Outside,
  MaddMatt, Mex, Overhead-L, Overhead-R, Snare Bottom,
  Snare Top, Tom 1, Tom 2, Tom 3

Takes (ordered by earliest mtime, 12 total):
  Take  9  | mtime 2026-04-18 21:47:17 | duration 4m 23s | 14 files
  Take 10  | mtime 2026-04-18 21:53:02 | duration 5m 11s | 14 files
  Take 11  | mtime 2026-04-18 22:07:31 | duration 3m 58s | 14 files
  Take 12  | mtime 2026-04-18 22:19:44 | duration 6m 02s | 14 files
  ...

Timeline layout (gap: 60s between takes):
  00:00:00.000  Take  9   ends 00:04:23.000
  00:05:23.000  Take 10   ends 00:10:34.000
  00:11:34.000  Take 11   ends 00:15:32.000
  ...
  Total project length: 1h 12m 04s

Output AAF: /Users/matt/Music/SessionFolder/SessionFolder.aaf
(preview only — re-run with --write to generate)

Warnings:
  - Skipped 'random_note.wav': filename does not match expected pattern
```

### Exit codes

- 0: success (preview or write, no errors)
- 1: usage error / bad arguments
- 2: input folder not found, not a directory, or empty of WAVs
- 3: write failure (AAF could not be written)
- 4: internal error / unexpected exception

---

## 6. Dependencies

- **Python standard library only** for filesystem traversal, regex, WAV header parsing, argument parsing, logging.
- **`pyaaf2`** (`pip install pyaaf2`) — pure-Python AAF writer, MIT licensed, no native dependencies. Pin to `>=1.7.1`.
- A `requirements.txt` with just `pyaaf2>=1.7.1`.
- A `README.md` covering installation, the Logic "Enable Complete Features" requirement, and a usage example.

No virtualenv tooling is mandated, but the README should suggest one (`python3 -m venv .venv && source .venv/bin/activate`).

---

## 7. Error handling and edge cases

The script must handle these gracefully (log a warning and continue when possible; abort with a clear message when not):

| Case | Behavior |
|---|---|
| Filename does not match expected pattern | Skip file, log warning, continue |
| WAV file is corrupt or unreadable | Skip file, log warning, continue |
| Take has only an `-L` file with no matching `-R` (or vice versa) | Treat as mono, log warning |
| Files within a take have different sample rates | Use most common rate for AAF, log warning listing outliers |
| Files within a take have substantially different durations (>1 second) | Use longest, log warning |
| Two takes have nearly identical mtimes (<5s apart) | Order by take number, log warning |
| Input folder does not exist | Abort with clear error, exit code 2 |
| Input folder has zero WAV files | Abort with clear error, exit code 2 |
| Output path is not writable | Abort with clear error, exit code 3 |
| `pyaaf2` not installed | Abort with installation instructions, exit code 4 |

All warnings appear in the preview output and (if `--log` is given) the log file.

---

## 8. Testing plan

### 8.1 Unit-testable pieces

- Filename parser: feed it a list of valid and invalid filenames, assert correct extraction of track name, take number, and channel.
- Take grouper: feed it a list of parsed filenames + mtimes, assert correct grouping and ordering.
- Timeline computer: feed it grouped takes + gap, assert correct start positions and total duration.

These should have a `tests/` directory with `pytest` tests.

### 8.2 Integration / smoke test (critical)

Before the script is considered done, the developer must:

1. Generate a small synthetic test folder: 2 takes × 3 tracks (one mono, one stereo pair) of short WAV files (5 seconds each), with mtimes set to differ by a known amount.
2. Run the script with `--write` to produce an AAF.
3. Open Logic Pro, ensure "Enable Complete Features" is on, and import the AAF.
4. Verify in Logic that:
   - The expected number of tracks appears
   - Each take's regions are placed at the expected timeline positions
   - The gap between takes matches `--gap-seconds`
   - Audio plays back correctly (no broken file references, no silence where there should be sound)

This smoke test is **gating**: if Logic does not import the AAF cleanly, the format being produced needs to be adjusted before further work.

### 8.3 Real-data validation

After the smoke test passes, run the script against one of Matt's actual session folders in preview mode first, then with `--write`, and verify the result imports cleanly into Logic Pro and matches what the manual workflow would have produced.

---

## 9. Project structure

```
wav-takes-to-aaf/
├── README.md
├── requirements.txt
├── pyproject.toml          (optional, for `pip install -e .`)
├── wav_takes_to_aaf/
│   ├── __init__.py
│   ├── __main__.py         (entry point: `python -m wav_takes_to_aaf`)
│   ├── cli.py              (argparse, top-level orchestration)
│   ├── scanner.py          (folder scan, filename parsing, WAV header reading)
│   ├── grouper.py          (take grouping and ordering logic)
│   ├── timeline.py         (timeline position computation)
│   ├── aaf_writer.py       (pyaaf2 wrapper that emits the final AAF)
│   └── preview.py          (formats the preview text output)
└── tests/
    ├── test_scanner.py
    ├── test_grouper.py
    ├── test_timeline.py
    └── fixtures/           (small synthetic WAVs for integration tests)
```

A single-file implementation is also acceptable for an initial version — Claude Code may use its judgment. The module breakdown above is the recommended structure if the script grows beyond a few hundred lines.

---

## 10. Out of scope (explicit non-features)

These should **not** be implemented in v1:

- Reading the `.ptx` file
- Reading BWF timestamps (we know they're absent in this user's data)
- Recursive folder scanning
- Batch processing multiple project folders
- Configurable track ordering beyond alphabetical
- Stereo pair handling as single stereo Logic tracks (user wants two mono)
- GUI
- Watching the folder for changes
- Embedding WAV media in the AAF (referenced files only)
- Handling MIDI tracks, video tracks, automation, fades, or any other non-clip data

If any of these become useful later, they can be added in a v2.

---

## 11. Open questions for implementation time

Things the developer should confirm with Matt during or after the smoke test:

1. Does Logic correctly group the `Overhead-L` and `Overhead-R` tracks in a way that's easy to work with, or should the AAF name them differently (e.g., `Overhead L` / `Overhead R` with a space, or just `Overhead_L` / `Overhead_R` with underscores)?
2. Is the alphabetical track ordering actually convenient in Logic, or would a fixed default order (drums first, then bass, keys, etc.) be more useful even as a v1 default?
3. Is 60 seconds the right default gap, or would something different (30s, 90s, 120s) be better in practice? The flag is there either way; this is just about the default.

These are deliberately not blocking decisions — sensible defaults are in the spec, and the user can revise after using v1 a few times.
