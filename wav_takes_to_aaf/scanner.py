"""Scan a folder for multitrack WAV files, parse filenames, read WAV headers."""
from __future__ import annotations

import os
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

FILENAME_RE = re.compile(r"^(?P<track>.+?)_(?P<take>\d+)(?:-(?P<channel>[LR]))?\.wav$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedFile:
    path: Path
    track_name: str
    take_number: int
    channel: Optional[str]
    mtime: float
    sample_rate: int
    bit_depth: int
    channels: int
    sample_count: int

    @property
    def display_track_name(self) -> str:
        if self.channel is None:
            return self.track_name
        return f"{self.track_name}-{self.channel}"

    @property
    def duration_seconds(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.sample_count / self.sample_rate


def parse_filename(name: str) -> Optional[Tuple[str, int, Optional[str]]]:
    """Return (track_name, take_number, channel) or None if it doesn't match."""
    m = FILENAME_RE.match(name)
    if not m:
        return None
    track = m.group("track")
    take = int(m.group("take"))
    channel = m.group("channel")
    return track, take, channel


def _read_wav_header(path: Path) -> Tuple[int, int, int, int]:
    """Return (sample_rate, bit_depth, channels, sample_count). Raises on failure."""
    with wave.open(str(path), "rb") as w:
        sample_rate = w.getframerate()
        bit_depth = w.getsampwidth() * 8
        channels = w.getnchannels()
        sample_count = w.getnframes()
    return sample_rate, bit_depth, channels, sample_count


def scan_folder(folder: Path) -> Tuple[List[ParsedFile], List[str]]:
    """
    Non-recursively scan ``folder`` for ``*.wav`` files.

    Returns a list of successfully parsed files and a list of warning strings
    for skipped files. Never raises on per-file errors.
    """
    parsed: List[ParsedFile] = []
    warnings: List[str] = []

    for entry in sorted(os.scandir(folder), key=lambda e: e.name):
        if not entry.is_file():
            continue
        if not entry.name.lower().endswith(".wav"):
            continue

        result = parse_filename(entry.name)
        if result is None:
            warnings.append(f"Skipped {entry.name!r}: filename does not match expected pattern")
            continue
        track, take, channel = result

        try:
            sample_rate, bit_depth, channels, sample_count = _read_wav_header(Path(entry.path))
        except (wave.Error, EOFError, OSError) as exc:
            warnings.append(f"Skipped {entry.name!r}: could not read WAV header ({exc})")
            continue

        try:
            mtime = entry.stat().st_mtime
        except OSError as exc:
            warnings.append(f"Skipped {entry.name!r}: could not stat ({exc})")
            continue

        parsed.append(
            ParsedFile(
                path=Path(entry.path),
                track_name=track,
                take_number=take,
                channel=channel,
                mtime=mtime,
                sample_rate=sample_rate,
                bit_depth=bit_depth,
                channels=channels,
                sample_count=sample_count,
            )
        )

    return parsed, warnings
