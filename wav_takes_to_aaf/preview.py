"""Format the human-readable preview output."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from textwrap import wrap
from typing import List, Optional

from .grouper import GroupedSession
from .timeline import TimelinePlan


def _format_hms(seconds: float) -> str:
    seconds = max(0.0, seconds)
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _format_short_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    total = int(round(seconds))
    m, s = divmod(total, 60)
    return f"{m}m {s:02d}s"


def _format_mtime(mtime: float) -> str:
    return dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")


def _wrap_track_list(track_names: List[str], indent: str = "  ", width: int = 70) -> str:
    joined = ", ".join(track_names)
    lines = wrap(joined, width=width, initial_indent=indent, subsequent_indent=indent)
    return "\n".join(lines) if lines else indent


def format_preview(
    input_folder: Path,
    total_files_seen: int,
    parsed_count: int,
    skipped_count: int,
    session: GroupedSession,
    plan: TimelinePlan,
    output_path: Path,
    write_mode: bool,
    warnings: List[str],
) -> str:
    lines: List[str] = []
    lines.append(f"Input folder: {input_folder}")
    if skipped_count:
        lines.append(
            f"Found {total_files_seen} WAV files, parsed {parsed_count} "
            f"({skipped_count} skipped — see warnings)"
        )
    else:
        lines.append(f"Found {total_files_seen} WAV files, parsed {parsed_count}")
    lines.append("")

    if parsed_count == 0:
        lines.append("No parseable WAV files found.")
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines)

    rate_note = "all files agree" if not _has_warning_about(warnings, "sample rates") else "see warnings"
    depth_note = "all files agree" if not _has_warning_about(warnings, "bit depths") else "see warnings"
    lines.append(f"Detected sample rate: {session.session_sample_rate} Hz ({rate_note})")
    lines.append(f"Detected bit depth: {session.session_bit_depth} bit ({depth_note})")
    lines.append("")

    lines.append(f"Tracks (alphabetical, {len(session.track_names)} total):")
    lines.append(_wrap_track_list(session.track_names))
    lines.append("")

    lines.append(f"Takes (ordered by earliest mtime, {len(session.takes)} total):")
    for take in session.takes:
        duration = sum(1 for _ in take.files)  # noqa: F841 — just to compute file count below
        lines.append(
            f"  Take {take.take_number:>2}  | "
            f"mtime {_format_mtime(take.earliest_mtime)} | "
            f"duration {_format_short_duration(_max_take_duration_seconds(take, session.session_sample_rate))} | "
            f"{take.file_count} files"
        )
    lines.append("")

    lines.append(f"Timeline layout (gap: {plan.gap_seconds:.0f}s between takes):")
    for placement in plan.placements:
        start_s = placement.start_sample / plan.sample_rate if plan.sample_rate else 0.0
        end_s = placement.end_sample / plan.sample_rate if plan.sample_rate else 0.0
        lines.append(
            f"  {_format_hms(start_s)}  Take {placement.take.take_number:>2}   "
            f"ends {_format_hms(end_s)}"
        )
    lines.append(f"  Total project length: {_format_hms(plan.total_seconds)}")
    lines.append("")

    lines.append(f"Output AAF: {output_path}")
    if not write_mode:
        lines.append("(preview only — re-run with --write to generate)")

    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"  - {w}")

    return "\n".join(lines)


def _has_warning_about(warnings: List[str], substring: str) -> bool:
    return any(substring in w for w in warnings)


def _max_take_duration_seconds(take, session_sample_rate: int) -> float:
    if not take.files or session_sample_rate <= 0:
        return 0.0
    durations = []
    for f in take.files:
        if f.sample_rate <= 0:
            continue
        durations.append(f.sample_count / f.sample_rate)
    return max(durations) if durations else 0.0
