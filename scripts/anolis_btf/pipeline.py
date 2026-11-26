"""End-to-end Anolis OS archive update, one manifest per VERSION_ID."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Sequence

from kylin_btf.btf import Toolchain, detect_toolchain
from kylin_btf.http import HttpError
from kylin_btf.manifest import Manifest
from kylin_btf.pipeline import RunOptions, process_pending
from kylin_btf.repodata import DiscoveryError
from kylin_btf.report import RunReport
from kylin_btf.selection import select_pending

from . import config
from .models import AnolisCandidate
from .repodata import (
    discover_repos,
    discover_versions,
    fetch_candidates,
)

LOGGER = logging.getLogger(__name__)

_ARTIFACTS = (
    "`anolis/<version>/manifest-anolis.json` and "
    "`anolis/<version>/<arch>/*.btf.tar.xz`."
)


def run(options: RunOptions) -> RunReport:
    repo_root = options.repo_root.resolve()
    report = RunReport(dry_run=options.dry_run, artifacts=_ARTIFACTS)
    deadline = time.monotonic() + options.time_budget_minutes * 60.0
    remaining = options.max_new
    toolchain: Toolchain | None = None

    try:
        versions = _resolve_versions(options.versions)
    except (DiscoveryError, HttpError, OSError) as exc:
        LOGGER.error("cannot list Anolis versions: %s", exc)
        report.failures.append(
            {
                "version": "(index)",
                "arch": "",
                "repo": "",
                "filename": "(version index)",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        report.finish()
        return report

    for version in versions:
        try:
            repos = _resolve_repos(version, options.repos)
        except (DiscoveryError, HttpError, OSError) as exc:
            LOGGER.error("cannot list repositories for %s: %s", version, exc)
            report.failures.append(
                {
                    "version": version,
                    "arch": "",
                    "repo": "(index)",
                    "filename": "(repository index)",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        manifest_path = repo_root / config.ARCHIVE_ROOT / version / config.MANIFEST_NAME
        manifest = Manifest.load(manifest_path)
        candidates, failures = _discover(version, repos, options)
        report.discovered += len(candidates)
        report.failures.extend(failures)

        selection = select_pending(
            candidates,
            manifest,
            repo_root,
            max_new=remaining,
            force=options.force,
        )
        report.pending += len(selection.pending)
        report.skipped.extend(
            _skip_rows(selection.already_recorded, "already in manifest")
        )
        report.skipped.extend(
            _skip_rows(selection.archived_on_disk, "already archived")
        )
        report.skipped.extend(
            _skip_rows(selection.duplicate_target, "duplicate archive path")
        )
        remaining -= len(selection.pending)

        if options.dry_run:
            for candidate in selection.pending:
                report.processed.append(_candidate_row(candidate))
            continue
        if not selection.pending:
            continue
        if toolchain is None:
            toolchain = detect_toolchain()
            LOGGER.info(
                "toolchain: pahole=%s objcopy=%s",
                toolchain.pahole_version,
                toolchain.objcopy,
            )
        manifest = process_pending(
            selection.pending, options, manifest, toolchain, report, deadline
        )

    report.finish()
    return report


def _resolve_versions(values: Sequence[str]) -> list[str]:
    if any(value.lower() == "all" for value in values):
        return discover_versions()
    return list(dict.fromkeys(values))


def _resolve_repos(version: str, values: Sequence[str]) -> list[str]:
    if any(value.lower() == "all" for value in values):
        return discover_repos(version)
    return [
        value for value in dict.fromkeys(values) if value not in config.EXCLUDED_REPOS
    ]


def _discover(
    version: str, repos: Sequence[str], options: RunOptions
) -> tuple[list[AnolisCandidate], list[dict[str, str]]]:
    candidates: list[AnolisCandidate] = []
    failures: list[dict[str, str]] = []
    for arch in options.arches:
        for repo in repos:
            try:
                candidates.extend(
                    fetch_candidates(
                        version,
                        arch,
                        repo,
                        timeout=config.DEFAULT_HTTP_TIMEOUT,
                    )
                )
            except (DiscoveryError, HttpError, OSError) as exc:
                LOGGER.error(
                    "discovery failed for %s/%s/%s: %s", version, arch, repo, exc
                )
                failures.append(
                    {
                        "version": version,
                        "arch": arch,
                        "repo": repo,
                        "filename": "(repository metadata)",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    return candidates, failures


def _candidate_row(candidate: AnolisCandidate) -> dict[str, object]:
    return {
        "version": candidate.version,
        "arch": candidate.arch,
        "repo": candidate.repo,
        "filename": candidate.filename,
        "kernel_version": candidate.kernel_version,
        "btf": candidate.archive_relpath,
        "package_size": candidate.size,
    }


def _skip_rows(
    candidates: Iterable[AnolisCandidate], reason: str
) -> list[dict[str, object]]:
    return [{**_candidate_row(candidate), "reason": reason} for candidate in candidates]


__all__ = ["run"]
