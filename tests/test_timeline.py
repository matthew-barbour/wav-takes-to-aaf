from wav_takes_to_aaf.grouper import group_files
from wav_takes_to_aaf.scanner import scan_folder
from wav_takes_to_aaf.timeline import build_timeline


def test_single_take_at_zero(tmp_path, wav_factory):
    wav_factory("Kick_01.wav", mtime=2_000_000_100, duration_seconds=2.0)
    files, _ = scan_folder(tmp_path)
    session = group_files(files)
    plan = build_timeline(session, gap_seconds=60.0)
    assert len(plan.placements) == 1
    p = plan.placements[0]
    assert p.start_sample == 0
    assert p.duration_samples == 96000
    assert plan.total_samples == 96000


def test_two_takes_with_gap(tmp_path, wav_factory):
    wav_factory("Kick_01.wav", mtime=2_000_000_100, duration_seconds=2.0)
    wav_factory("Kick_02.wav", mtime=2_000_000_200, duration_seconds=3.0)
    files, _ = scan_folder(tmp_path)
    session = group_files(files)
    plan = build_timeline(session, gap_seconds=10.0)

    assert plan.placements[0].start_sample == 0
    assert plan.placements[0].duration_samples == 96000
    assert plan.placements[1].start_sample == 96000 + 480000
    assert plan.placements[1].duration_samples == 144000
    assert plan.total_samples == 96000 + 480000 + 144000


def test_take_duration_is_max_within_take(tmp_path, wav_factory):
    wav_factory("A_01.wav", mtime=2_000_000_100, duration_seconds=2.0)
    wav_factory("B_01.wav", mtime=2_000_000_100, duration_seconds=3.0)
    files, _ = scan_folder(tmp_path)
    session = group_files(files)
    plan = build_timeline(session, gap_seconds=0.0)
    assert plan.placements[0].duration_samples == 144000


def test_no_gap_after_last_take(tmp_path, wav_factory):
    wav_factory("Kick_01.wav", mtime=2_000_000_100, duration_seconds=1.0)
    wav_factory("Kick_02.wav", mtime=2_000_000_200, duration_seconds=1.0)
    files, _ = scan_folder(tmp_path)
    session = group_files(files)
    plan = build_timeline(session, gap_seconds=5.0)
    assert plan.total_samples == 48000 + 240000 + 48000
