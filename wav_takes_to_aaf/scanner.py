"""Scan a folder for multitrack WAV files, parse filenames, read WAV headers."""
from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

FILENAME_RE = re.compile(r"^(?P<track>.+?)_(?P<take>\d+)(?:-(?P<channel>[LR]))?\.wav$", re.IGNORECASE)

WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_IEEE_FLOAT = 0x0003
WAVE_FORMAT_EXTENSIBLE = 0xFFFE


class WavParseError(Exception):
    pass


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
    """Return (sample_rate, bit_depth, channels, sample_count). Raises WavParseError.

    Parses RIFF/WAVE (and RF64) directly so it handles integer PCM (format 1),
    IEEE float (format 3), and WAVE_FORMAT_EXTENSIBLE (0xFFFE). The stdlib
    ``wave`` module only supports format 1, which is unusable for Pro Tools /
    Logic recordings that default to 32-bit float.
    """
    with open(path, "rb") as f:
        riff = f.read(4)
        if riff not in (b"RIFF", b"RF64"):
            raise WavParseError(f"not a RIFF/WAVE file (header: {riff!r})")
        f.read(4)  # file size, unused
        wave_id = f.read(4)
        if wave_id != b"WAVE":
            raise WavParseError(f"not a WAVE file (id: {wave_id!r})")

        fmt_data: Optional[bytes] = None
        data_size: Optional[int] = None
        ds64_data_size: Optional[int] = None

        while True:
            header = f.read(8)
            if len(header) < 8:
                break
            chunk_id = header[:4]
            chunk_size = struct.unpack("<I", header[4:])[0]

            if chunk_id == b"ds64":
                payload = f.read(chunk_size)
                if len(payload) < 16:
                    raise WavParseError("truncated ds64 chunk")
                _, ds64_data_size = struct.unpack_from("<QQ", payload, 0)
                if chunk_size % 2 == 1:
                    f.read(1)
            elif chunk_id == b"fmt ":
                fmt_data = f.read(chunk_size)
                if chunk_size % 2 == 1:
                    f.read(1)
            elif chunk_id == b"data":
                if chunk_size == 0xFFFFFFFF and ds64_data_size is not None:
                    data_size = ds64_data_size
                else:
                    data_size = chunk_size
                break
            else:
                skip = chunk_size + (chunk_size % 2)
                f.seek(skip, 1)

    if fmt_data is None:
        raise WavParseError("no 'fmt ' chunk found")
    if data_size is None:
        raise WavParseError("no 'data' chunk found")
    if len(fmt_data) < 16:
        raise WavParseError("truncated 'fmt ' chunk")

    format_code, channels, sample_rate, _byte_rate, block_align, bits_per_sample = struct.unpack_from(
        "<HHIIHH", fmt_data, 0
    )

    if format_code == WAVE_FORMAT_EXTENSIBLE:
        if len(fmt_data) < 40:
            raise WavParseError("truncated extensible 'fmt ' chunk")
        actual_format = struct.unpack_from("<H", fmt_data, 24)[0]
    else:
        actual_format = format_code

    if actual_format not in (WAVE_FORMAT_PCM, WAVE_FORMAT_IEEE_FLOAT):
        raise WavParseError(f"unsupported WAV format code: {actual_format}")
    if block_align == 0:
        raise WavParseError("invalid block_align of 0")

    sample_count = data_size // block_align
    return sample_rate, bits_per_sample, channels, sample_count


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
        except (WavParseError, OSError, struct.error) as exc:
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
