"""Command-line entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .grouper import DEFAULT_CLUSTER_WINDOW_SECONDS, group_files
from .preview import format_preview
from .scanner import scan_folder
from .timeline import build_timeline

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_INPUT = 2
EXIT_WRITE = 3
EXIT_INTERNAL = 4


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wav-takes-to-aaf",
        description=(
            "Group a folder of multitrack WAV takes into a single AAF that imports "
            "into Logic Pro as a sequence of takes laid out on unified tracks."
        ),
    )
    p.add_argument("input_folder", type=Path, help="Path to folder containing WAV files")
    p.add_argument("-o", "--output", type=Path, default=None, help="Output AAF path")
    p.add_argument(
        "-g",
        "--gap-seconds",
        type=float,
        default=60.0,
        help="Silence gap between takes, in seconds (default: 60)",
    )
    p.add_argument(
        "--cluster-window-seconds",
        type=float,
        default=DEFAULT_CLUSTER_WINDOW_SECONDS,
        help=(
            "Files whose mtimes fall within this window are grouped into the same take "
            "(default: 60). Pro Tools writes each track's mtime when recording stops, "
            "so files from the same record-pass cluster tightly. Increase if your DAW "
            "stops tracks asynchronously; decrease if takes happen back-to-back."
        ),
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Actually write the AAF. Without this, the script previews only.",
    )
    p.add_argument("--log", type=Path, default=None, help="Write detailed log to this file")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    return p


def _default_output(input_folder: Path) -> Path:
    return input_folder / f"{input_folder.name}.aaf"


def _emit(report: str, log_path: Optional[Path]) -> None:
    print(report)
    if log_path is not None:
        log_path.write_text(report + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    input_folder: Path = args.input_folder
    if not input_folder.exists():
        print(f"Error: input folder does not exist: {input_folder}", file=sys.stderr)
        return EXIT_INPUT
    if not input_folder.is_dir():
        print(f"Error: input path is not a directory: {input_folder}", file=sys.stderr)
        return EXIT_INPUT

    if args.gap_seconds < 0:
        print("Error: --gap-seconds must be >= 0", file=sys.stderr)
        return EXIT_USAGE
    if args.cluster_window_seconds < 0:
        print("Error: --cluster-window-seconds must be >= 0", file=sys.stderr)
        return EXIT_USAGE

    output_path: Path = args.output or _default_output(input_folder)

    try:
        parsed_files, scan_warnings = scan_folder(input_folder)
    except OSError as exc:
        print(f"Error: failed to scan folder: {exc}", file=sys.stderr)
        return EXIT_INPUT

    total_seen = len(parsed_files) + len(scan_warnings)
    if not parsed_files:
        warnings: List[str] = list(scan_warnings)
        from .grouper import GroupedSession
        from .timeline import TimelinePlan

        empty_session = GroupedSession(takes=[], track_names=[], session_sample_rate=0, session_bit_depth=0, cluster_window_seconds=args.cluster_window_seconds, warnings=warnings)
        empty_plan = TimelinePlan(placements=[], sample_rate=0, gap_samples=0, total_samples=0)
        report = format_preview(
            input_folder=input_folder,
            total_files_seen=total_seen,
            parsed_count=0,
            skipped_count=len(scan_warnings),
            session=empty_session,
            plan=empty_plan,
            output_path=output_path,
            write_mode=args.write,
            warnings=warnings,
        )
        _emit(report, args.log)
        print(f"\nError: no parseable WAV files in {input_folder}", file=sys.stderr)
        return EXIT_INPUT

    session = group_files(parsed_files, cluster_window_seconds=args.cluster_window_seconds)
    all_warnings = list(scan_warnings) + list(session.warnings)
    plan = build_timeline(session, gap_seconds=args.gap_seconds)

    report = format_preview(
        input_folder=input_folder,
        total_files_seen=total_seen,
        parsed_count=len(parsed_files),
        skipped_count=len(scan_warnings),
        session=session,
        plan=plan,
        output_path=output_path,
        write_mode=args.write,
        warnings=all_warnings,
    )
    _emit(report, args.log)

    if not args.write:
        return EXIT_OK

    try:
        from .aaf_writer import write_aaf
    except ImportError as exc:
        print(
            f"Error: pyaaf2 is required to write AAFs. Install with `pip install pyaaf2`. ({exc})",
            file=sys.stderr,
        )
        return EXIT_INTERNAL

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_aaf(out_path=output_path, session=session, plan=plan, composition_name=input_folder.name)
    except OSError as exc:
        print(f"Error: could not write AAF: {exc}", file=sys.stderr)
        return EXIT_WRITE
    except Exception as exc:  # noqa: BLE001
        print(f"Error: unexpected failure while writing AAF: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return EXIT_INTERNAL

    print(f"\nWrote AAF: {output_path}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
