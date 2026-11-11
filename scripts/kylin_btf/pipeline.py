"""End-to-end orchestration for one archive update run."""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from . import config
from .btf import Toolchain, detect_toolchain, pack_btf, produce_btf
from .fsutil import ensure_within, human_size, sha256_file
from .http import HttpError
from .manifest import Manifest
from .models import Candidate
from .repodata import DiscoveryError, fetch_candidates
from .report import RunReport, utc_now
from .rpm import download_rpm, extract_vmlinux
from .selection import select_pending

LOGGER = logging.getLogger(__name__)

_MIN_FREE_DISK = 5 * 1024 * 1024 * 1024
_RESERVED_SECONDS = 120


class PipelineError(RuntimeError):
    """A candidate cannot be processed in this environment."""


@dataclass(frozen=True)
class RunOptions:
    repo_root: Path
    versions: Sequence[str] = config.VERSIONS
    arches: Sequence[str] = config.ARCHES
    repos: Sequence[str] = config.REPOS
    max_new: int = config.DEFAULT_MAX_NEW
    dry_run: bool = False
    force: bool = False
    work_dir: Path | None = None
    time_budget_minutes: float = config.DEFAULT_TIME_BUDGET_MINUTES
    download_timeout: float = config.DEFAULT_DOWNLOAD_TIMEOUT
    keep_temp: bool = False


def run(options: RunOptions) -> RunReport:
    repo_root = options.repo_root.resolve()
    manifest_path = repo_root / config.ARCHIVE_ROOT / config.MANIFEST_NAME
    manifest = Manifest.load(manifest_path)
    report = RunReport(dry_run=options.dry_run)

    candidates, discovery_failures = _discover(options)
    report.discovered = len(candidates)
    report.failures.extend(discovery_failures)

    selection = select_pending(
        candidates,
        manifest,
        repo_root,
        max_new=options.max_new,
        force=options.force,
    )
    report.pending = len(selection.pending)
    report.skipped.extend(_skip_rows(selection.already_recorded, "already in manifest"))
    report.skipped.extend(_skip_rows(selection.archived_on_disk, "already archived"))
    report.skipped.extend(
        _skip_rows(selection.duplicate_target, "duplicate archive path")
    )

    if options.dry_run:
        for candidate in selection.pending:
            report.processed.append(_candidate_row(candidate))
        report.finish()
        return report

    if not selection.pending:
        LOGGER.info("no new kernel-debuginfo packages found")
        report.finish()
        return report

    toolchain = detect_toolchain()
    LOGGER.info(
        "toolchain: pahole=%s objcopy=%s", toolchain.pahole_version, toolchain.objcopy
    )

    deadline = time.monotonic() + options.time_budget_minutes * 60.0
    pending = list(selection.pending)
    for index, candidate in enumerate(pending):
        remaining = deadline - time.monotonic()
        if remaining < _RESERVED_SECONDS:
            report.deferred.extend(_candidate_row(item) for item in pending[index:])
            LOGGER.warning(
                "time budget reached; deferring %d package(s)",
                len(pending) - index,
            )
            break
        try:
            updated_manifest, row = _process_candidate(
                candidate, options, manifest, toolchain
            )
        except Exception as exc:
            LOGGER.exception(
                "failed to process %s/%s/%s",
                candidate.version,
                candidate.arch,
                candidate.filename,
            )
            report.failures.append(
                {
                    **_candidate_row(candidate),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        # Persist the manifest immediately so a later crash cannot lose the
        # record of BTF files that are already written to the work tree.
        try:
            updated_manifest.save()
        except OSError as exc:
            raise PipelineError(f"cannot save manifest: {exc}") from exc
        manifest = updated_manifest
        report.processed.append(row)
        LOGGER.info(
            "archived %s (%s)",
            row["btf"],
            human_size(int(row["btf_size"])),
        )

    report.finish()
    return report


def _discover(
    options: RunOptions,
) -> tuple[list[Candidate], list[dict[str, str]]]:
    candidates: list[Candidate] = []
    failures: list[dict[str, str]] = []
    for version in options.versions:
        for arch in options.arches:
            for repo in options.repos:
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


def _process_candidate(
    candidate: Candidate,
    options: RunOptions,
    manifest: Manifest,
    toolchain: Toolchain,
) -> tuple[Manifest, dict[str, object]]:
    work_root = _prepare_work_root(options)
    _check_free_disk(work_root, candidate)
    work = Path(
        tempfile.mkdtemp(
            prefix=f"{candidate.version}-{candidate.arch}-", dir=str(work_root)
        )
    )
    try:
        rpm_path = work / "package.rpm"
        LOGGER.info(
            "downloading %s (%s)",
            candidate.filename,
            human_size(candidate.size) if candidate.size else "size unknown",
        )
        download = download_rpm(candidate, rpm_path, timeout=options.download_timeout)
        vmlinux = extract_vmlinux(rpm_path, work)
        raw_btf = work / "kernel.btf"
        method = produce_btf(toolchain, vmlinux, raw_btf)
        raw_size = raw_btf.stat().st_size
        raw_hash = sha256_file(raw_btf)

        target = ensure_within(options.repo_root.resolve(), candidate.archive_relpath)
        pack_btf(raw_btf, target, f"{candidate.kernel_version}.btf")

        entry = {
            "version": candidate.version,
            "arch": candidate.arch,
            "repo": candidate.repo,
            "package": candidate.filename,
            "package_url": candidate.url,
            "package_size": download.size,
            "package_sha256": download.sha256,
            "source_checksum": candidate.checksum_sha256,
            "kernel_version": candidate.kernel_version,
            "btf": candidate.archive_relpath,
            "btf_container": "tar",
            "btf_compression": "xz",
            "btf_member": f"{candidate.kernel_version}.btf",
            "btf_size": target.stat().st_size,
            "btf_sha256": sha256_file(target),
            "btf_uncompressed_size": raw_size,
            "btf_uncompressed_sha256": raw_hash,
            "btf_method": method,
            "pahole": toolchain.pahole_version,
            "generated_at": utc_now(),
        }
        row = {
            "version": candidate.version,
            "arch": candidate.arch,
            "repo": candidate.repo,
            "filename": candidate.filename,
            "kernel_version": candidate.kernel_version,
            "btf": candidate.archive_relpath,
            "btf_size": entry["btf_size"],
            "method": method,
        }
        return manifest.with_entry(candidate.source_key, entry), row
    finally:
        if options.keep_temp:
            LOGGER.info("keeping work directory %s", work)
        else:
            shutil.rmtree(work, ignore_errors=True)


def _prepare_work_root(options: RunOptions) -> Path:
    if options.work_dir is None:
        return Path(tempfile.gettempdir())
    options.work_dir.mkdir(parents=True, exist_ok=True)
    return options.work_dir


def _check_free_disk(work_root: Path, candidate: Candidate) -> None:
    free = shutil.disk_usage(work_root).free
    needed = max(_MIN_FREE_DISK, (candidate.size or 0) * 2)
    if free < needed:
        raise PipelineError(
            f"insufficient disk space in {work_root}: "
            f"{human_size(free)} free, need at least {human_size(needed)}"
        )


def _candidate_row(candidate: Candidate) -> dict[str, object]:
    return {
        "version": candidate.version,
        "arch": candidate.arch,
        "repo": candidate.repo,
        "filename": candidate.filename,
        "kernel_version": candidate.kernel_version,
        "btf": candidate.archive_relpath,
        "package_size": candidate.size,
    }


def _skip_rows(candidates: Iterable[Candidate], reason: str) -> list[dict[str, object]]:
    return [{**_candidate_row(candidate), "reason": reason} for candidate in candidates]
