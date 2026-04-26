"""Group parsed WAV files into takes and order them."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .scanner import ParsedFile

NEAR_TIE_SECONDS = 5.0
DURATION_TOLERANCE_SECONDS = 1.0


@dataclass(frozen=True)
class Take:
    take_number: int
    files: Tuple[ParsedFile, ...]

    @property
    def earliest_mtime(self) -> float:
        return min(f.mtime for f in self.files)

    @property
    def file_count(self) -> int:
        return len(self.files)


@dataclass
class GroupedSession:
    takes: List[Take]
    track_names: List[str]
    session_sample_rate: int
    session_bit_depth: int
    warnings: List[str] = field(default_factory=list)


def _alphabetical_key(name: str) -> str:
    return name.lower()


def _detect_session_format(files: List[ParsedFile]) -> Tuple[int, int, List[str]]:
    """Return (session_sample_rate, session_bit_depth, warnings)."""
    warnings: List[str] = []
    sample_rates = Counter(f.sample_rate for f in files)
    bit_depths = Counter(f.bit_depth for f in files)

    session_rate = sample_rates.most_common(1)[0][0]
    session_depth = bit_depths.most_common(1)[0][0]

    if len(sample_rates) > 1:
        outliers = sorted(
            (f.path.name for f in files if f.sample_rate != session_rate)
        )
        warnings.append(
            f"Multiple sample rates detected; using {session_rate} Hz. "
            f"Outliers: {', '.join(outliers)}"
        )
    if len(bit_depths) > 1:
        outliers = sorted(
            (f.path.name for f in files if f.bit_depth != session_depth)
        )
        warnings.append(
            f"Multiple bit depths detected; using {session_depth}-bit. "
            f"Outliers: {', '.join(outliers)}"
        )
    return session_rate, session_depth, warnings


def _detect_orphan_stereo_halves(files: List[ParsedFile]) -> List[str]:
    """Warn if any take has an -L without -R (or vice versa) for the same track."""
    warnings: List[str] = []
    by_take: Dict[int, Dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for f in files:
        if f.channel is not None:
            by_take[f.take_number][f.track_name].add(f.channel)
    for take_no, tracks in by_take.items():
        for track, channels in tracks.items():
            if channels == {"L"}:
                warnings.append(
                    f"Take {take_no} has '{track}-L' without matching '-R'; treating as mono"
                )
            elif channels == {"R"}:
                warnings.append(
                    f"Take {take_no} has '{track}-R' without matching '-L'; treating as mono"
                )
    return warnings


def _detect_within_take_duration_outliers(take: Take) -> List[str]:
    warnings: List[str] = []
    if not take.files:
        return warnings
    durations = [f.duration_seconds for f in take.files]
    longest = max(durations)
    shortest = min(durations)
    if longest - shortest > DURATION_TOLERANCE_SECONDS:
        warnings.append(
            f"Take {take.take_number}: file durations differ by "
            f"{longest - shortest:.2f}s (longest {longest:.2f}s, shortest {shortest:.2f}s); "
            "using longest"
        )
    return warnings


def group_files(files: List[ParsedFile]) -> GroupedSession:
    """Group ``files`` into takes ordered by earliest mtime."""
    warnings: List[str] = []

    if not files:
        return GroupedSession(takes=[], track_names=[], session_sample_rate=0, session_bit_depth=0)

    session_rate, session_depth, fmt_warnings = _detect_session_format(files)
    warnings.extend(fmt_warnings)
    warnings.extend(_detect_orphan_stereo_halves(files))

    by_take: Dict[int, List[ParsedFile]] = defaultdict(list)
    for f in files:
        by_take[f.take_number].append(f)

    takes: List[Take] = []
    for take_no, take_files in by_take.items():
        take = Take(take_number=take_no, files=tuple(take_files))
        warnings.extend(_detect_within_take_duration_outliers(take))
        takes.append(take)

    takes.sort(key=lambda t: (t.earliest_mtime, t.take_number))

    for prev, curr in zip(takes, takes[1:]):
        if abs(curr.earliest_mtime - prev.earliest_mtime) < NEAR_TIE_SECONDS:
            warnings.append(
                f"Takes {prev.take_number} and {curr.take_number} have mtimes within "
                f"{NEAR_TIE_SECONDS:.0f}s of each other; ordered by take number as tiebreaker"
            )

    track_names = sorted({f.display_track_name for f in files}, key=_alphabetical_key)

    return GroupedSession(
        takes=takes,
        track_names=track_names,
        session_sample_rate=session_rate,
        session_bit_depth=session_depth,
        warnings=warnings,
    )
