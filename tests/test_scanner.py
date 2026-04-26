from pathlib import Path

import pytest

from wav_takes_to_aaf.scanner import parse_filename, scan_folder


class TestParseFilename:
    @pytest.mark.parametrize(
        "filename,expected_track,expected_take,expected_channel",
        [
            ("Snare Top_11.wav", "Snare Top", 11, None),
            ("Overhead_11-L.wav", "Overhead", 11, "L"),
            ("Overhead_11-R.wav", "Overhead", 11, "R"),
            ("Kick Outside_07.wav", "Kick Outside", 7, None),
            ("Tom 1_03.wav", "Tom 1", 3, None),
            ("Bass_3.wav", "Bass", 3, None),
            ("Track_With_Underscores_12.wav", "Track_With_Underscores", 12, None),
        ],
    )
    def test_valid(self, filename, expected_track, expected_take, expected_channel):
        track, take, channel = parse_filename(filename)
        assert track == expected_track
        assert take == expected_take
        assert channel == expected_channel

    @pytest.mark.parametrize(
        "filename",
        [
            "random_note.wav",
            "no_extension",
            "Track.wav",
            "Track_abc.wav",
            "Track_12-X.wav",
            ".wav",
        ],
    )
    def test_invalid(self, filename):
        assert parse_filename(filename) is None

    def test_zero_padded_and_unpadded_equivalent(self):
        a = parse_filename("Kick_03.wav")
        b = parse_filename("Kick_3.wav")
        assert a is not None and b is not None
        assert a[1] == b[1] == 3


class TestScanFolder:
    def test_empty_folder(self, tmp_path):
        files, warnings = scan_folder(tmp_path)
        assert files == []
        assert warnings == []

    def test_skips_non_wav(self, tmp_path, wav_factory):
        wav_factory("Kick_01.wav")
        (tmp_path / "notes.txt").write_text("hi")
        files, warnings = scan_folder(tmp_path)
        assert len(files) == 1
        assert warnings == []

    def test_warns_on_bad_filename(self, tmp_path, wav_factory):
        wav_factory("Kick_01.wav")
        wav_factory("random_note.wav")
        files, warnings = scan_folder(tmp_path)
        assert len(files) == 1
        assert len(warnings) == 1
        assert "random_note.wav" in warnings[0]

    def test_warns_on_corrupt_wav(self, tmp_path):
        (tmp_path / "Kick_01.wav").write_bytes(b"not a real wav")
        files, warnings = scan_folder(tmp_path)
        assert len(files) == 0
        assert len(warnings) == 1
        assert "Kick_01.wav" in warnings[0]

    def test_extracts_header_fields(self, tmp_path, wav_factory):
        wav_factory("Kick_01.wav", sample_rate=48000, bit_depth=24, duration_seconds=2.0)
        files, _ = scan_folder(tmp_path)
        assert len(files) == 1
        f = files[0]
        assert f.sample_rate == 48000
        assert f.bit_depth == 24
        assert f.channels == 1
        assert f.sample_count == 96000

    def test_display_track_name_with_channel(self, tmp_path, wav_factory):
        wav_factory("Overhead_11-L.wav")
        wav_factory("Overhead_11-R.wav")
        wav_factory("Kick_11.wav")
        files, _ = scan_folder(tmp_path)
        names = sorted(f.display_track_name for f in files)
        assert names == ["Kick", "Overhead-L", "Overhead-R"]

    def test_reads_32bit_float_wav(self, tmp_path):
        from tests.conftest import write_silent_float_wav

        path = tmp_path / "Kick_01.wav"
        write_silent_float_wav(path, sample_rate=48000, duration_seconds=2.0)
        files, warnings = scan_folder(tmp_path)
        assert warnings == []
        assert len(files) == 1
        f = files[0]
        assert f.sample_rate == 48000
        assert f.bit_depth == 32
        assert f.channels == 1
        assert f.sample_count == 96000
