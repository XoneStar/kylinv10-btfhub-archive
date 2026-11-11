"""Value objects shared by discovery, selection and the pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from . import config

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+~-]*$")
_SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+~-]*$")


def is_kernel_debuginfo(filename: str) -> bool:
    """Return True for the kernel-debuginfo binary RPM only.

    kernel-tools-debuginfo, kernel-hash-init-debuginfo, kernel-debuginfo-common
    and source RPMs are deliberately excluded: they do not contain vmlinux.
    """
    if not filename or "/" in filename or "\\" in filename:
        return False
    if not filename.startswith(config.PACKAGE_PREFIX):
        return False
    if not filename.endswith(".rpm") or filename.endswith(".src.rpm"):
        return False
    if filename.startswith(f"{config.PACKAGE_PREFIX}common-"):
        return False
    return bool(_SAFE_COMPONENT.fullmatch(filename))


def kernel_version_from_filename(filename: str, arch: str) -> str:
    """Extract 4.19.90-52.70.v2207.ky10 from a package filename."""
    if not is_kernel_debuginfo(filename):
        raise ValueError(f"not a kernel-debuginfo RPM: {filename!r}")
    stem = filename[len(config.PACKAGE_PREFIX) : -len(".rpm")]
    suffix = f".{arch}"
    if not stem.endswith(suffix):
        raise ValueError(f"package {filename!r} does not match arch {arch!r}")
    version = stem[: -len(suffix)]
    if not version or not _SAFE_VERSION.fullmatch(version):
        raise ValueError(f"unsafe kernel version in {filename!r}")
    return version


def version_sort_key(text: str) -> tuple[tuple[int, int, str], ...]:
    """RPM-ish sort key so 52.70 sorts above 52.9 even without timestamps."""
    parts: list[tuple[int, int, str]] = []
    for token in re.findall(r"\d+|[A-Za-z]+", text):
        if token.isdigit():
            parts.append((0, int(token), ""))
        else:
            parts.append((1, 0, token.lower()))
    return tuple(parts)


@dataclass(frozen=True)
class Candidate:
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
                self.archive_arch,
                f"{self.kernel_version}{config.ARCHIVE_SUFFIX}",
            )
        )

    def sort_key(self) -> tuple[int, tuple[tuple[int, int, str], ...]]:
        return (self.build_time or 0, version_sort_key(self.kernel_version))


@dataclass(frozen=True)
class PackageInfo:
    """Parsed metadata for one package before it becomes a Candidate."""

    filename: str
    href: str
    checksum_sha256: str | None = None
    size: int | None = None
    build_time: int | None = None
