"""Pure selection logic: which discovered packages still need work."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest
from .models import Candidate


@dataclass(frozen=True)
class Selection:
    pending: tuple[Candidate, ...]
    already_recorded: tuple[Candidate, ...]
    archived_on_disk: tuple[Candidate, ...]
    duplicate_target: tuple[Candidate, ...]


def select_pending(
    candidates: Iterable[Candidate],
    manifest: Manifest,
    repo_root: Path,
    *,
    max_new: int,
    force: bool = False,
) -> Selection:
    """Choose candidates to process, newest first, never repeating a target.

    A remote package is considered handled when its source key is in the
    manifest or its compressed BTF already exists in the working tree.
    """
    if max_new < 0:
        raise ValueError("max_new must be >= 0")

    pending: list[Candidate] = []
    recorded: list[Candidate] = []
    on_disk: list[Candidate] = []
    duplicates: list[Candidate] = []
    seen_targets: set[str] = set()

    for candidate in candidates:
        if not force and manifest.contains(candidate.source_key):
            recorded.append(candidate)
            continue
        target = candidate.archive_relpath
        if target in seen_targets:
            duplicates.append(candidate)
            continue
        seen_targets.add(target)
        if not force and (repo_root / target).exists():
            on_disk.append(candidate)
            continue
        if len(pending) < max_new:
            pending.append(candidate)

    return Selection(
        pending=tuple(pending),
        already_recorded=tuple(recorded),
        archived_on_disk=tuple(on_disk),
        duplicate_target=tuple(duplicates),
    )


def dedupe_by_target(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Keep the first (preferred repository order) candidate per target."""
    seen: set[str] = set()
    result: list[Candidate] = []
    for candidate in candidates:
        if candidate.archive_relpath in seen:
            continue
        seen.add(candidate.archive_relpath)
        result.append(candidate)
    return result
