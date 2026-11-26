"""Value objects for Anolis OS packages and archive paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from kylin_btf.models import kernel_version_from_filename, version_sort_key

from . import config


@dataclass(frozen=True)
class AnolisCandidate:
    version: str
    arch: str
    repo: str
    filename: str
    url: str
    checksum_sha256: str | None = None
    size: int | None = None
    build_time: int | None = None

    @property
    def source_key(self) -> str:
        return f"{self.version}/{self.arch}/{self.repo}/{self.filename}"

    @property
    def kernel_version(self) -> str:
        return kernel_version_from_filename(self.filename, self.arch)

    @property
    def archive_arch(self) -> str:
        return config.ARCHIVE_ARCH_ALIASES.get(self.arch, self.arch)

    @property
    def archive_relpath(self) -> str:
        return str(
            PurePosixPath(
                config.ARCHIVE_ROOT,
                self.version,
                self.archive_arch,
                f"{self.kernel_version}.{self.arch}{config.ARCHIVE_SUFFIX}",
            )
        )

    def sort_key(self) -> tuple[int, tuple[tuple[int, int, str], ...]]:
        return (self.build_time or 0, version_sort_key(self.kernel_version))


__all__ = ["AnolisCandidate"]
