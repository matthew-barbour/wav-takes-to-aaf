"""Integration smoke test: 2-take x 3-track fixture, round-trip the AAF."""
from __future__ import annotations

from pathlib import Path

import aaf2
import pytest

from wav_takes_to_aaf.aaf_writer import write_aaf
from wav_takes_to_aaf.cli import main as cli_main
from wav_takes_to_aaf.grouper import group_files
from wav_takes_to_aaf.scanner import scan_folder
from wav_takes_to_aaf.timeline import build_timeline


@pytest.fixture
def two_takes_three_tracks(tmp_path, wav_factory):
    """
    Layout (mtimes spaced beyond the default 60s cluster window):
      Take 1 (mtime t0):        Kick, Overhead-L, Overhead-R, Mex
      Take 2 (mtime t0 + 600):  Kick, Overhead-L, Overhead-R       (Mex missing — silent gap)
    """
    folder = tmp_path / "session"
    folder.mkdir()
    t0 = 2_000_000_000

    for name in ["Kick_01.wav", "Overhead_01-L.wav", "Overhead_01-R.wav", "Mex_01.wav"]:
        wav_factory(name, mtime=t0, duration_seconds=1.0, folder=folder)
    for name in ["Kick_02.wav", "Overhead_02-L.wav", "Overhead_02-R.wav"]:
        wav_factory(name, mtime=t0 + 600, duration_seconds=1.0, folder=folder)

    return folder


def test_round_trip_structure(tmp_path, two_takes_three_tracks):
    folder = two_takes_three_tracks
    files, _ = scan_folder(folder)
    session = group_files(files)
    plan = build_timeline(session, gap_seconds=2.0)

    out = tmp_path / "out.aaf"
    write_aaf(out, session, plan)

    assert out.exists() and out.stat().st_size > 0

    expected_take_samples = 48000  # 1 second @ 48000
    expected_gap_samples = 96000  # 2 seconds @ 48000

    with aaf2.open(str(out), "r") as f:
        comps = list(f.content.compositionmobs())
        masters = list(f.content.mastermobs())
        sources = list(f.content.sourcemobs())

        assert len(comps) == 1
        # 7 master mobs / source mobs — one per WAV file
        assert len(masters) == 7
        assert len(sources) == 7

        comp = comps[0]
        slots = list(comp.slots)
        slot_names = sorted(s.name for s in slots)
        assert slot_names == ["Kick", "Mex", "Overhead-L", "Overhead-R"]

        for slot in slots:
            seq = slot.segment
            assert seq.media_kind == "Sound"
            comps_in_seq = list(seq.components)

            if slot.name == "Mex":
                # take 1 = SourceClip, gap = Filler, take 2 = Filler (no Mex_02)
                kinds = [type(c).__name__ for c in comps_in_seq]
                assert kinds == ["SourceClip", "Filler", "Filler"]
                assert comps_in_seq[0].length == expected_take_samples
                assert comps_in_seq[1].length == expected_gap_samples
                assert comps_in_seq[2].length == expected_take_samples
            else:
                kinds = [type(c).__name__ for c in comps_in_seq]
                assert kinds == ["SourceClip", "Filler", "SourceClip"]
                assert comps_in_seq[0].length == expected_take_samples
                assert comps_in_seq[1].length == expected_gap_samples
                assert comps_in_seq[2].length == expected_take_samples


def test_cli_preview_only_does_not_write(tmp_path, two_takes_three_tracks, capsys):
    out = tmp_path / "preview.aaf"
    rc = cli_main(["--gap-seconds", "2", "-o", str(out), str(two_takes_three_tracks)])
    assert rc == 0
    assert not out.exists()
    captured = capsys.readouterr()
    assert "preview only" in captured.out
    assert "Total project length" in captured.out


def test_cli_write_creates_file(tmp_path, two_takes_three_tracks):
    out = tmp_path / "written.aaf"
    rc = cli_main(["--write", "--gap-seconds", "2", "-o", str(out), str(two_takes_three_tracks)])
    assert rc == 0
    assert out.exists()
    assert out.stat().st_size > 0


def test_cli_missing_input_returns_2(tmp_path, capsys):
    rc = cli_main([str(tmp_path / "does_not_exist")])
    assert rc == 2


def test_cli_empty_folder_returns_2(tmp_path, capsys):
    rc = cli_main([str(tmp_path)])
    assert rc == 2
