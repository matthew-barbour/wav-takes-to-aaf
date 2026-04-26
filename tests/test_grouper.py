from wav_takes_to_aaf.grouper import group_files
from wav_takes_to_aaf.scanner import scan_folder


def test_takes_ordered_by_earliest_mtime(tmp_path, wav_factory):
    wav_factory("Kick_05.wav", mtime=2_000_000_200)
    wav_factory("Kick_03.wav", mtime=2_000_000_100)
    wav_factory("Kick_04.wav", mtime=2_000_000_300)

    files, _ = scan_folder(tmp_path)
    session = group_files(files)
    take_order = [t.take_number for t in session.takes]
    assert take_order == [3, 5, 4]


def test_track_names_alphabetical_case_insensitive(tmp_path, wav_factory):
    wav_factory("Snare Top_01.wav", mtime=2_000_000_100)
    wav_factory("kick_01.wav", mtime=2_000_000_100)
    wav_factory("Bass_01.wav", mtime=2_000_000_100)

    files, _ = scan_folder(tmp_path)
    session = group_files(files)
    assert session.track_names == ["Bass", "kick", "Snare Top"]


def test_stereo_pair_kept_as_two_separate_tracks(tmp_path, wav_factory):
    wav_factory("Overhead_01-L.wav", mtime=2_000_000_100)
    wav_factory("Overhead_01-R.wav", mtime=2_000_000_100)

    files, _ = scan_folder(tmp_path)
    session = group_files(files)
    assert session.track_names == ["Overhead-L", "Overhead-R"]


def test_orphan_stereo_half_warns(tmp_path, wav_factory):
    wav_factory("Overhead_01-L.wav", mtime=2_000_000_100)

    files, _ = scan_folder(tmp_path)
    session = group_files(files)
    assert any("without matching '-R'" in w for w in session.warnings)


def test_near_tie_mtimes_warn_and_use_take_number(tmp_path, wav_factory):
    wav_factory("Kick_07.wav", mtime=2_000_000_101.5)
    wav_factory("Kick_06.wav", mtime=2_000_000_100.0)

    files, _ = scan_folder(tmp_path)
    session = group_files(files)
    assert [t.take_number for t in session.takes] == [6, 7]
    assert any("within 5s" in w for w in session.warnings)


def test_session_format_picks_majority_rate(tmp_path, wav_factory):
    wav_factory("A_01.wav", mtime=2_000_000_100, sample_rate=48000)
    wav_factory("B_01.wav", mtime=2_000_000_100, sample_rate=48000)
    wav_factory("C_01.wav", mtime=2_000_000_100, sample_rate=44100)

    files, _ = scan_folder(tmp_path)
    session = group_files(files)
    assert session.session_sample_rate == 48000
    assert any("Multiple sample rates" in w for w in session.warnings)


def test_within_take_duration_outlier_warns(tmp_path, wav_factory):
    wav_factory("A_01.wav", mtime=2_000_000_100, duration_seconds=5.0)
    wav_factory("B_01.wav", mtime=2_000_000_100, duration_seconds=2.0)

    files, _ = scan_folder(tmp_path)
    session = group_files(files)
    assert any("durations differ" in w for w in session.warnings)
