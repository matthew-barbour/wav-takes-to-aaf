"""Shared fixtures: synthetic WAV builder with controlled mtime."""
from __future__ import annotations

import os
import wave
from pathlib import Path

import pytest


def write_silent_wav(
    path: Path,
    *,
    sample_rate: int = 48000,
    bit_depth: int = 24,
    channels: int = 1,
    duration_seconds: float = 1.0,
) -> int:
    """Write a silent WAV at ``path``. Returns the sample count."""
    sample_width = bit_depth // 8
    n_samples = int(sample_rate * duration_seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00" * sample_width * channels * n_samples)
    return n_samples


def set_mtime(path: Path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


@pytest.fixture
def wav_factory(tmp_path):
    def _factory(
        name: str,
        *,
        mtime: float | None = None,
        sample_rate: int = 48000,
        bit_depth: int = 24,
        channels: int = 1,
        duration_seconds: float = 1.0,
        folder: Path | None = None,
    ) -> Path:
        target_folder = folder or tmp_path
        target_folder.mkdir(parents=True, exist_ok=True)
        path = target_folder / name
        write_silent_wav(
            path,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            channels=channels,
            duration_seconds=duration_seconds,
        )
        if mtime is not None:
            set_mtime(path, mtime)
        return path

    return _factory
