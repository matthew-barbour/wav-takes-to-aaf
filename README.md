# wav-takes-to-aaf

A macOS command-line tool that scans a folder of multitrack WAV recordings (organized by "take"), groups them by filesystem mtime, and produces a single AAF file. When imported into Logic Pro, all takes are laid out sequentially on a unified set of tracks with a configurable silence gap between takes.

The script does **not** parse Pro Tools `.ptx` files. The WAV files and their filesystem timestamps are the sole source of truth for grouping and ordering takes. WAV files are referenced by absolute path — the AAF does not embed media, and source files are never modified.

See [docs/SPEC.md](docs/SPEC.md) for the full design spec.

## Requirements

- macOS
- Python 3.9 or newer
- Logic Pro with **"Enable Complete Features"** turned on under Logic Pro → Settings → Advanced. Without this, Logic's File → Import → AAF menu item does not appear.

## Install

```sh
git clone https://github.com/<your-account>/wav-takes-to-aaf.git
cd wav-takes-to-aaf
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

This installs the `wav-takes-to-aaf` console script into the venv. You can also invoke the package directly with `python -m wav_takes_to_aaf`.

## Filename convention

WAV files in the input folder must be named:

```
<TrackName>_<TakeNumber>.wav            mono track
<TrackName>_<TakeNumber>-L.wav          left  channel of a stereo pair
<TrackName>_<TakeNumber>-R.wav          right channel of a stereo pair
```

Track names may contain spaces. Take numbers may or may not be zero-padded (`_03` and `_3` are equivalent). Stereo pairs (`-L`/`-R`) are treated as **two separate mono tracks** in the output AAF.

Files that don't match are skipped with a warning, not fatal.

## Usage

```sh
# Preview only (default — does not write the AAF)
wav-takes-to-aaf /path/to/session

# Actually write the AAF
wav-takes-to-aaf /path/to/session --write

# Custom gap between takes (default 60s)
wav-takes-to-aaf /path/to/session --write --gap-seconds 30

# Custom output path
wav-takes-to-aaf /path/to/session --write -o /path/to/output.aaf

# Save the report to a log file as well
wav-takes-to-aaf /path/to/session --log /tmp/run.log
```

By default the script previews the planned timeline to stdout and exits. Re-run with `--write` to generate the AAF.

## Importing into Logic Pro

The simplest path: in Finder, right-click the generated `.aaf` and choose **Open With → Logic Pro**. Logic opens it directly and you can save the result as a new Logic project.

If that doesn't work (or the menu item is missing), use the in-app importer:
1. Confirm Logic → Settings → Advanced → **Enable Complete Features** is checked.
2. In Logic, File → Import → AAF…, select the generated `.aaf`.

Either way, Logic creates one track per unique track name and lays takes out sequentially with the configured silence gap between them.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (preview or write) |
| 1 | Usage / argument error |
| 2 | Input folder missing, not a directory, or empty of WAVs |
| 3 | Output AAF could not be written |
| 4 | Internal error |

## Development

```sh
pip install -e .
pip install pytest
pytest
```

## License

MIT — see [LICENSE](LICENSE).
