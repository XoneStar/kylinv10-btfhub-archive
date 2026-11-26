"""Command line interface for the Anolis OS BTF archive updater."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from kylin_btf.manifest import ManifestError
from kylin_btf.pipeline import PipelineError, RunOptions
from kylin_btf.tools import ToolError

from . import config
from .pipeline import run

LOGGER = logging.getLogger("anolis_btf")
_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Discover Anolis OS kernel-debuginfo RPMs and archive BTF files.")
    )
    parser.add_argument("--repo-root", default=".", help="repository root (default: .)")
    parser.add_argument(
        "--versions",
        type=_csv,
        default=list(config.VERSIONS),
        help=("comma separated VERSION_IDs, or all to auto-discover (default: all)"),
    )
    parser.add_argument(
        "--arches",
        type=_csv,
        default=list(config.ARCHES),
        help="comma separated architectures (default: x86_64,aarch64)",
    )
    parser.add_argument(
        "--repos",
        type=_csv,
        default=list(config.REPOS),
        help=(
            "comma separated repository names, or all to discover per version "
            "(default: all)"
        ),
    )
    parser.add_argument(
        "--max-new",
        type=int,
        default=config.DEFAULT_MAX_NEW,
        help=f"maximum packages to process per run (default: {config.DEFAULT_MAX_NEW})",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=config.DEFAULT_CONCURRENCY,
        help=(
            "packages processed in parallel, 1-"
            f"{config.MAX_CONCURRENCY} (default: {config.DEFAULT_CONCURRENCY})"
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="discover only")
    parser.add_argument(
        "--force", action="store_true", help="regenerate even if already archived"
    )
    parser.add_argument(
        "--work-dir", type=Path, help="directory for temporary RPM data"
    )
    parser.add_argument(
        "--keep-temp", action="store_true", help="keep downloaded RPM/vmlinux data"
    )
    parser.add_argument(
        "--time-budget-minutes",
        type=float,
        default=config.DEFAULT_TIME_BUDGET_MINUTES,
        help="stop starting new packages after this many minutes",
    )
    parser.add_argument(
        "--download-timeout",
        type=float,
        default=config.DEFAULT_DOWNLOAD_TIMEOUT,
        help="per-download socket timeout in seconds",
    )
    parser.add_argument("--report-json", type=Path, help="write a JSON run report")
    parser.add_argument("--report-md", type=Path, help="write a Markdown run report")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser


def _validate_choices(
    values: Iterable[str], allowed: Iterable[str], label: str
) -> None:
    allowed_set = set(allowed)
    unknown = [value for value in values if value not in allowed_set]
    if unknown:
        raise SystemExit(f"unsupported {label}: {', '.join(unknown)}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if not args.versions:
        raise SystemExit("--versions must not be empty")
    if not any(value.lower() == "all" for value in args.versions):
        bad_versions = [
            value for value in args.versions if not _VERSION_RE.fullmatch(value)
        ]
        if bad_versions:
            raise SystemExit(f"invalid VERSION_ID: {', '.join(bad_versions)}")
    _validate_choices(args.arches, config.ARCHES, "arch(es)")
    if not any(value.lower() == "all" for value in args.repos):
        bad_repos = [
            value
            for value in args.repos
            if not _REPO_RE.fullmatch(value) or value in config.EXCLUDED_REPOS
        ]
        if bad_repos:
            raise SystemExit(f"invalid repository name: {', '.join(bad_repos)}")
    if args.max_new < 0:
        raise SystemExit("--max-new must be >= 0")
    if not 1 <= args.concurrency <= config.MAX_CONCURRENCY:
        raise SystemExit(
            f"--concurrency must be between 1 and {config.MAX_CONCURRENCY}"
        )
    if args.time_budget_minutes <= 0:
        raise SystemExit("--time-budget-minutes must be > 0")

    options = RunOptions(
        repo_root=Path(args.repo_root),
        versions=tuple(args.versions),
        arches=tuple(args.arches),
        repos=tuple(args.repos),
        max_new=args.max_new,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
        force=args.force,
        work_dir=args.work_dir,
        time_budget_minutes=args.time_budget_minutes,
        download_timeout=args.download_timeout,
        keep_temp=args.keep_temp,
    )

    try:
        report = run(options)
    except (ManifestError, ToolError, PipelineError) as exc:
        LOGGER.error("%s", exc)
        return 1

    if args.report_json:
        report.write_json(args.report_json)
    if args.report_md:
        args.report_md.parent.mkdir(parents=True, exist_ok=True)
        args.report_md.write_text(report.to_markdown(), encoding="utf-8")
    LOGGER.info(
        "done: discovered=%d selected=%d generated=%d deferred=%d skipped=%d failed=%d",
        report.discovered,
        report.pending,
        len(report.processed),
        len(report.deferred),
        len(report.skipped),
        len(report.failures),
    )
    return 2 if report.failures else 0


__all__ = ["build_parser", "main"]
