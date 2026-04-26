"""Compute timeline positions for each take."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .grouper import GroupedSession, Take


@dataclass(frozen=True)
class TakePlacement:
    take: Take
    start_sample: int
    duration_samples: int

    @property
    def end_sample(self) -> int:
        return self.start_sample + self.duration_samples


@dataclass(frozen=True)
class TimelinePlan:
    placements: List[TakePlacement]
    sample_rate: int
    gap_samples: int
    total_samples: int

    @property
    def gap_seconds(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.gap_samples / self.sample_rate

    @property
    def total_seconds(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.total_samples / self.sample_rate


def _take_duration_samples(take: Take, session_sample_rate: int) -> int:
    """Per spec 4.4: take duration = max sample count across files in the take.

    Files at a different rate from the session are converted to session-rate
    samples for the duration calculation only; the AAF still references the
    file at its native rate.
    """
    if not take.files:
        return 0
    samples_at_session_rate = []
    for f in take.files:
        if f.sample_rate == session_sample_rate or f.sample_rate <= 0:
            samples_at_session_rate.append(f.sample_count)
        else:
            scaled = int(round(f.sample_count * session_sample_rate / f.sample_rate))
            samples_at_session_rate.append(scaled)
    return max(samples_at_session_rate)


def build_timeline(session: GroupedSession, gap_seconds: float) -> TimelinePlan:
    """Lay each take out sequentially with ``gap_seconds`` of silence between."""
    sample_rate = session.session_sample_rate
    gap_samples = int(round(gap_seconds * sample_rate)) if sample_rate > 0 else 0

    placements: List[TakePlacement] = []
    cursor = 0
    for i, take in enumerate(session.takes):
        duration = _take_duration_samples(take, sample_rate)
        placements.append(
            TakePlacement(take=take, start_sample=cursor, duration_samples=duration)
        )
        cursor += duration
        if i != len(session.takes) - 1:
            cursor += gap_samples

    return TimelinePlan(
        placements=placements,
        sample_rate=sample_rate,
        gap_samples=gap_samples,
        total_samples=cursor,
    )
