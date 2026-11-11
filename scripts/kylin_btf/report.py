"""Run reports for logs, GitHub step summaries and artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .fsutil import human_size


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass
class RunReport:
    started_at: str = field(default_factory=utc_now)
    finished_at: str = ""
    discovered: int = 0
    pending: int = 0
    dry_run: bool = False
    processed: list[dict[str, Any]] = field(default_factory=list)
    deferred: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)

    def finish(self) -> None:
        self.finished_at = utc_now()

    def to_payload(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "discovered": self.discovered,
            "pending": self.pending,
            "dry_run": self.dry_run,
            "processed": self.processed,
            "deferred": self.deferred,
            "skipped": self.skipped,
            "failures": self.failures,
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(self.to_payload(), handle, indent=2, ensure_ascii=False)
            handle.write("\n")

    def to_markdown(self) -> str:
        lines = [
            "## Kylin V10 BTF archive update",
            "",
            f"- Started: `{self.started_at}`",
            f"- Finished: `{self.finished_at or 'running'}`",
            f"- Discovered: {self.discovered} package(s)",
            f"- Selected: {self.pending} package(s)"
            + (" (dry run)" if self.dry_run else ""),
            f"- {'Would generate' if self.dry_run else 'Generated'}: {len(self.processed)}",
            f"- Deferred: {len(self.deferred)}",
            f"- Skipped: {len(self.skipped)}",
            f"- Failed: {len(self.failures)}",
            "",
        ]
        if self.processed:
            heading = "### Would generate" if self.dry_run else "### Generated"
            lines.extend(
                [
                    heading,
                    "",
                    "| Version | Arch | Kernel | Size | Method |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for item in self.processed:
                size_bytes = int(item.get("btf_size") or item.get("package_size") or 0)
                lines.append(
                    "| {version} | {arch} | `{kernel}` | {size} | {method} |".format(
                        version=item.get("version", ""),
                        arch=item.get("arch", ""),
                        kernel=item.get("kernel_version", ""),
                        size=human_size(size_bytes) if size_bytes else "-",
                        method=item.get("method", ""),
                    )
                )
            lines.append("")
        if self.failures:
            lines.extend(
                [
                    "### Failures",
                    "",
                    "| Version | Arch | Package | Error |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for item in self.failures:
                lines.append(
                    "| {version} | {arch} | `{package}` | {error} |".format(
                        version=item.get("version", ""),
                        arch=item.get("arch", ""),
                        package=item.get("filename", ""),
                        error=str(item.get("error", "")).replace("|", "\\|")[:500],
                    )
                )
            lines.append("")
        if self.deferred:
            lines.extend(
                [
                    f"Deferred {len(self.deferred)} package(s) to the next run (time budget reached).",
                    "",
                ]
            )
        lines.extend(
            [
                "Artifacts: `kylin/V10/manifest.json` and `kylin/V10/<arch>/*.btf.tar.xz`.",
                "",
            ]
        )
        return "\n".join(lines)
