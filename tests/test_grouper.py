from wav_takes_to_aaf.grouper import group_files
from wav_takes_to_aaf.scanner import scan_folder


def test_distant_mtimes_form_separate_takes(tmp_path, wav_factory):
    """Files separated by more than the cluster window become separate takes, in chronological order."""
    wav_factory("Kick_05.wav", mtime=2_000_000_200)
    wav_factory("Kick_03.wav", mtime=2_000_000_000)
    wav_factory("Kick_04.wav", mtime=2_000_000_400)

    files, _ = scan_folder(tmp_path)
    session = group_files(files, cluster_window_seconds=60.0)
    assert len(session.takes) == 3
    assert [t.take_number for t in session.takes] == [1, 2, 3]
    chronological_filenames = [t.files[0].path.name for t in session.takes]
    assert chronological_filenames == ["Kick_03.wav", "Kick_05.wav", "Kick_04.wav"]


def test_close_mtimes_cluster_into_one_take(tmp_path, wav_factory):
    """Files whose mtimes fall within the window form a single take, regardless of filename _NN."""
    wav_factory("Kick_05.wav", mtime=2_000_000_100)
    wav_factory("Snare_01.wav", mtime=2_000_000_120)
    wav_factory("BenGuitar_03.wav", mtime=2_000_000_150)

    files, _ = scan_folder(tmp_path)
    session = group_files(files, cluster_window_seconds=60.0)
    assert len(session.takes) == 1
    assert session.takes[0].file_count == 3


def test_window_boundary_splits_clusters(tmp_path, wav_factory):
    """Files exactly window+1 apart are in different clusters; files exactly at the window are together."""
    wav_factory("A_01.wav", mtime=1_000.0)
    wav_factory("B_01.wav", mtime=1_060.0)  # exactly 60s later → still clustered (<=)
    wav_factory("C_01.wav", mtime=1_121.0)  # 61s after B → new cluster

    files, _ = scan_folder(tmp_path)
    session = group_files(files, cluster_window_seconds=60.0)
    assert [t.file_count for t in session.takes] == [2, 1]


def test_cluster_window_can_be_overridden(tmp_path, wav_factory):
    """A wider window collapses what would be two takes into one."""
    wav_factory("A_01.wav", mtime=1_000.0)
    wav_factory("B_01.wav", mtime=1_200.0)  # 200s apart

    files, _ = scan_folder(tmp_path)

    narrow = group_files(files, cluster_window_seconds=60.0)
    wide = group_files(files, cluster_window_seconds=300.0)
    assert len(narrow.takes) == 2
    assert len(wide.takes) == 1


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


def test_duplicate_track_in_cluster_keeps_longest_and_warns(tmp_path, wav_factory):
    """If a track has 2+ files in a cluster, keep the longest and warn."""
    wav_factory("Kick_01.wav", mtime=2_000_000_100, duration_seconds=1.0)
    wav_factory("Kick_02.wav", mtime=2_000_000_120, duration_seconds=5.0)

    files, _ = scan_folder(tmp_path)
    session = group_files(files, cluster_window_seconds=60.0)
    assert len(session.takes) == 1
    assert session.takes[0].file_count == 1
    assert session.takes[0].files[0].path.name == "Kick_02.wav"
    assert any("Kick_01.wav" in w and "dropping" in w for w in session.warnings)
