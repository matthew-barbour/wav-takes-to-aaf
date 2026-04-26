"""Write an AAF file from a grouped session and timeline plan."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional

import aaf2
import aaf2.ama

from .grouper import GroupedSession
from .scanner import ParsedFile
from .timeline import TimelinePlan


def _index_files_by_track_and_take(session: GroupedSession) -> Dict[str, Dict[int, ParsedFile]]:
    index: Dict[str, Dict[int, ParsedFile]] = {name: {} for name in session.track_names}
    for take in session.takes:
        for f in take.files:
            index[f.display_track_name][take.take_number] = f
    return index


def _create_master_mob_for_file(f, parsed: ParsedFile):
    """Create SourceMob + WAVEDescriptor + MasterMob referencing ``parsed.path``."""
    abs_path = str(parsed.path.resolve())

    source_mob = f.create.SourceMob()
    source_mob.name = parsed.path.stem
    f.content.mobs.append(source_mob)

    descriptor = f.create.WAVEDescriptor()
    descriptor["SampleRate"].value = parsed.sample_rate
    descriptor["Summary"].value = aaf2.ama.get_wave_fmt(abs_path)
    descriptor["Length"].value = parsed.sample_count
    descriptor["ContainerFormat"].value = f.dictionary.lookup_containerdef("AAF")
    descriptor["Locator"].append(aaf2.ama.create_network_locator(f, abs_path))
    source_mob.descriptor = descriptor

    source_slot = source_mob.create_sound_slot(edit_rate=parsed.sample_rate)
    source_slot.segment.length = parsed.sample_count

    master_mob = f.create.MasterMob()
    master_mob.name = parsed.path.stem
    f.content.mobs.append(master_mob)
    master_slot = master_mob.create_sound_slot(edit_rate=parsed.sample_rate)
    master_clip = source_mob.create_source_clip(slot_id=source_slot.slot_id, media_kind="Sound")
    master_clip.length = parsed.sample_count
    master_slot.segment.components.append(master_clip)

    return master_mob, master_slot


def write_aaf(
    out_path: Path,
    session: GroupedSession,
    plan: TimelinePlan,
    composition_name: str = "WAV Takes",
) -> None:
    """
    Render ``session`` and ``plan`` to an AAF at ``out_path``.

    The AAF references each WAV by absolute file:// URL — no media is embedded.
    """
    edit_rate = session.session_sample_rate
    if edit_rate <= 0:
        raise ValueError("session_sample_rate must be positive")

    files_by_track_and_take = _index_files_by_track_and_take(session)

    with aaf2.open(str(out_path), "w") as f:
        master_mobs: Dict[Path, tuple] = {}

        for track_name in session.track_names:
            for take_no, parsed in files_by_track_and_take[track_name].items():
                if parsed.path not in master_mobs:
                    master_mobs[parsed.path] = _create_master_mob_for_file(f, parsed)

        comp = f.create.CompositionMob()
        comp.name = composition_name
        f.content.mobs.append(comp)

        for track_name in session.track_names:
            slot = comp.create_sound_slot(edit_rate=edit_rate)
            slot.name = track_name
            sequence = f.create.Sequence(media_kind="Sound")
            slot.segment = sequence

            track_files = files_by_track_and_take[track_name]
            running_length = 0

            for i, placement in enumerate(plan.placements):
                take_no = placement.take.take_number
                parsed = track_files.get(take_no)
                if parsed is None:
                    filler = f.create.Filler("Sound", placement.duration_samples)
                    sequence.components.append(filler)
                else:
                    master_mob, master_slot = master_mobs[parsed.path]
                    clip = master_mob.create_source_clip(
                        slot_id=master_slot.slot_id, media_kind="Sound"
                    )
                    clip.length = placement.duration_samples
                    sequence.components.append(clip)
                running_length += placement.duration_samples

                if i != len(plan.placements) - 1 and plan.gap_samples > 0:
                    sequence.components.append(
                        f.create.Filler("Sound", plan.gap_samples)
                    )
                    running_length += plan.gap_samples

            sequence.length = running_length
            slot.segment.length = running_length
