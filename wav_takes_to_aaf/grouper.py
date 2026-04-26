"""Group parsed WAV files into takes by clustering on filesystem mtime.

Pro Tools updates a WAV file's mtime when recording stops, not when it starts,
and numbers files per-track rather than per-session. So files that share a
filename ``_NN`` suffix are not necessarily the same take. The reliable signal
is mtime: every track that was rolling when you hit Stop gets the same mtime.
We cluster files whose mtimes fall within a configurable window — each cluster
is one take.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .scanner import ParsedFile

DEFAULT_CLUSTER_WINDOW_SECONDS = 60.0
DURATION_TOLERANCE_SECONDS = 1.0


@dataclass(frozen=True)
class Take:
    """A take = one cluster of files. ``take_number`` is the 1-based chronological index."""

    take_number: int
    files: Tuple[ParsedFile, ...]

    @property
    def earliest_mtime(self) -> float:
        return min(f.mtime for f in self.files)

    @property
    def latest_mtime(self) -> float:
        return max(f.mtime for f in self.files)

    @property
    def file_count(self) -> int:
        return len(self.files)


@dataclass
class GroupedSession:
    takes: List[Take]
    track_names: List[str]
    session_sample_rate: int
    session_bit_depth: int
    cluster_window_seconds: float = DEFAULT_CLUSTER_WINDOW_SECONDS
    warnings: List[str] = field(default_factory=list)


def _alphabetical_key(name: str) -> str:
    return name.lower()


def _detect_session_format(files: List[ParsedFile]) -> Tuple[int, int, List[str]]:
    warnings: List[str] = []
    sample_rates = Counter(f.sample_rate for f in files)
    bit_depths = Counter(f.bit_depth for f in files)
    session_rate = sample_rates.most_common(1)[0][0]
    session_depth = bit_depths.most_common(1)[0][0]

    if len(sample_rates) > 1:
        outliers = sorted(f.path.name for f in files if f.sample_rate != session_rate)
        warnings.append(
            f"Multiple sample rates detected; using {session_rate} Hz. "
            f"Outliers: {', '.join(outliers)}"
        )
    if len(bit_depths) > 1:
        outliers = sorted(f.path.name for f in files if f.bit_depth != session_depth)
        warnings.append(
            f"Multiple bit depths detected; using {session_depth}-bit. "
            f"Outliers: {', '.join(outliers)}"
        )
    return session_rate, session_depth, warnings


def _cluster_by_mtime(
    files: List[ParsedFile], window_seconds: float
) -> List[List[ParsedFile]]:
    """Cluster files whose consecutive mtimes (sorted asc) are within ``window_seconds``."""
    if not files:
        return []
    sorted_files = sorted(files, key=lambda f: f.mtime)
    clusters: List[List[ParsedFile]] = [[sorted_files[0]]]
    for f in sorted_files[1:]:
        if f.mtime - clusters[-1][-1].mtime <= window_seconds:
            clusters[-1].append(f)
        else:
            clusters.append([f])
    return clusters


def _resolve_track_duplicates(
    take_no: int, files: List[ParsedFile]
) -> Tuple[List[ParsedFile], List[str]]:
    """If a track has >1 file in the cluster, keep the longest and warn about the rest."""
    warnings: List[str] = []
    by_track: Dict[str, List[ParsedFile]] = defaultdict(list)
    for f in files:
        by_track[f.display_track_name].append(f)

    deduped: List[ParsedFile] = []
    for track_name, track_files in by_track.items():
        if len(track_files) == 1:
            deduped.append(track_files[0])
            continue
        longest = max(track_files, key=lambda f: f.sample_count)
        dropped = sorted(f.path.name for f in track_files if f is not longest)
        warnings.append(
            f"Take {take_no}: track {track_name!r} has {len(track_files)} files "
            f"in this cluster; using {longest.path.name!r}, dropping {', '.join(dropped)}"
        )
        deduped.append(longest)
    return deduped, warnings


def _detect_orphan_stereo_halves(take_no: int, files: List[ParsedFile]) -> List[str]:
    warnings: List[str] = []
    by_track: Dict[str, set] = defaultdict(set)
    for f in files:
        if f.channel is not None:
            by_track[f.track_name].add(f.channel)
    for track, channels in by_track.items():
        if channels == {"L"}:
            warnings.append(
                f"Take {take_no} has {track!r}-L without matching '-R'; treating as mono"
            )
        elif channels == {"R"}:
            warnings.append(
                f"Take {take_no} has {track!r}-R without matching '-L'; treating as mono"
            )
    return warnings


def _detect_within_take_duration_outliers(
    take_no: int, files: List[ParsedFile]
) -> List[str]:
    if not files:
        return []
    durations = [f.duration_seconds for f in files]
    longest = max(durations)
    shortest = min(durations)
    if longest - shortest <= DURATION_TOLERANCE_SECONDS:
        return []
    return [
        f"Take {take_no}: file durations differ by "
        f"{longest - shortest:.2f}s (longest {longest:.2f}s, shortest {shortest:.2f}s); "
        "using longest"
    ]


def group_files(
    files: List[ParsedFile],
    cluster_window_seconds: float = DEFAULT_CLUSTER_WINDOW_SECONDS,
) -> GroupedSession:
    """Cluster ``files`` into takes by mtime windowing."""
    warnings: List[str] = []

    if not files:
        return GroupedSession(
            takes=[],
            track_names=[],
            session_sample_rate=0,
            session_bit_depth=0,
            cluster_window_seconds=cluster_window_seconds,
        )

    session_rate, session_depth, fmt_warnings = _detect_session_format(files)
    warnings.extend(fmt_warnings)

    clusters = _cluster_by_mtime(files, cluster_window_seconds)

    takes: List[Take] = []
    for i, cluster in enumerate(clusters, start=1):
        deduped, dup_warnings = _resolve_track_duplicates(i, cluster)
        warnings.extend(dup_warnings)
        warnings.extend(_detect_orphan_stereo_halves(i, deduped))
        warnings.extend(_detect_within_take_duration_outliers(i, deduped))
        takes.append(Take(take_number=i, files=tuple(deduped)))

    track_names = sorted({f.display_track_name for f in files}, key=_alphabetical_key)

    return GroupedSession(
        takes=takes,
        track_names=track_names,
        session_sample_rate=session_rate,
        session_bit_depth=session_depth,
        cluster_window_seconds=cluster_window_seconds,
        warnings=warnings,
    )
