"""BTF extraction, encoding, validation and compression."""

from __future__ import annotations

import logging
import lzma
import os
import re
import struct
import tarfile
from dataclasses import dataclass
from pathlib import Path

from . import config
from .tools import first_available, require_tool, run, tool_version

LOGGER = logging.getLogger(__name__)

BTF_MAGIC = 0xEB9F
_BTF_HEADER = struct.Struct("<HBBIIIII")
_MIN_BTF_SIZE = _BTF_HEADER.size
_MEMBER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+~-]*\.btf$")


class BtfError(RuntimeError):
    """BTF could not be produced or failed validation."""


@dataclass(frozen=True)
class Toolchain:
    objcopy: str
    pahole: str
    pahole_version: str


def detect_toolchain() -> Toolchain:
    objcopy = first_available(
        ("llvm-objcopy", "llvm-objcopy-18", "llvm-objcopy-17", "objcopy")
    )
    pahole = require_tool("pahole")
    return Toolchain(
        objcopy=objcopy,
        pahole=pahole,
        pahole_version=tool_version(pahole),
    )


def dump_btf(objcopy: str, vmlinux: Path, destination: Path) -> bool:
    """Dump an existing .BTF section; return False when there is none."""
    destination.unlink(missing_ok=True)
    result = run(
        [objcopy, "--dump-section", f".BTF={destination}", str(vmlinux)],
        timeout=1800,
        check=False,
        description="objcopy --dump-section .BTF",
    )
    if result.returncode != 0 or not destination.exists():
        destination.unlink(missing_ok=True)
        return False
    if destination.stat().st_size < _MIN_BTF_SIZE:
        destination.unlink(missing_ok=True)
        return False
    return True


def encode_btf(toolchain: Toolchain, vmlinux: Path, destination: Path) -> str:
    """Generate BTF from DWARF, preferring a detached output file."""
    destination.unlink(missing_ok=True)
    detached = run(
        [toolchain.pahole, f"--btf_encode_detached={destination}", str(vmlinux)],
        timeout=3600,
        check=False,
        description="pahole --btf_encode_detached",
    )
    if detached.returncode == 0 and destination.exists():
        return "pahole-detached"

    if detached.returncode != 0:
        LOGGER.info(
            "detached BTF encoding unavailable/failed (status %d); "
            "falling back to in-place pahole -J",
            detached.returncode,
        )
    destination.unlink(missing_ok=True)

    inplace = run(
        [toolchain.pahole, "-J", str(vmlinux)],
        timeout=3600,
        check=False,
        description="pahole -J",
    )
    if inplace.returncode != 0:
        LOGGER.warning("pahole -J failed; retrying with --btf_encode_force")
        inplace = run(
            [toolchain.pahole, "--btf_encode_force", "-J", str(vmlinux)],
            timeout=3600,
            check=False,
            description="pahole --btf_encode_force -J",
        )
    if inplace.returncode != 0:
        detail = (inplace.stderr or "").strip()[-2000:]
        raise BtfError(f"pahole -J failed ({inplace.returncode}): {detail}")
    if not dump_btf(toolchain.objcopy, vmlinux, destination):
        raise BtfError("pahole -J produced no .BTF section")
    return "pahole-inplace"


def produce_btf(toolchain: Toolchain, vmlinux: Path, destination: Path) -> str:
    """Ensure *destination* holds validated BTF; return the method used."""
    method = None
    if dump_btf(toolchain.objcopy, vmlinux, destination):
        try:
            validate_btf(destination)
        except BtfError as exc:
            LOGGER.warning("embedded .BTF is invalid (%s); re-encoding", exc)
            destination.unlink(missing_ok=True)
        else:
            method = "embedded"
    if method is None:
        method = encode_btf(toolchain, vmlinux, destination)
        validate_btf(destination)
    LOGGER.info("BTF ready via %s (%d bytes)", method, destination.stat().st_size)
    return method


def validate_btf(path: Path) -> None:
    size = path.stat().st_size
    with open(path, "rb") as handle:
        header = handle.read(_MIN_BTF_SIZE)
    _validate_header(header, size, str(path))


def _validate_header(header: bytes, size: int, label: str) -> None:
    if size < _MIN_BTF_SIZE or len(header) < _MIN_BTF_SIZE:
        raise BtfError(f"BTF file is too small: {label} ({size} bytes)")
    magic, version, _flags, hdr_len, type_off, type_len, str_off, str_len = (
        _BTF_HEADER.unpack(header)
    )
    if magic != BTF_MAGIC:
        raise BtfError(f"bad BTF magic 0x{magic:04x} in {label}")
    if version != 1:
        raise BtfError(f"unsupported BTF version {version} in {label}")
    if hdr_len < _MIN_BTF_SIZE or hdr_len > size:
        raise BtfError(f"bad BTF header length {hdr_len} in {label}")
    if type_off + type_len > size or str_off + str_len > size:
        raise BtfError(f"BTF section offsets exceed file size in {label}")


def pack_btf(source: Path, destination: Path, member_name: str) -> None:
    """Pack *source* as *member_name* inside a deterministic ``.btf.tar.xz``."""
    if not _MEMBER_NAME.fullmatch(member_name):
        raise BtfError(f"unsafe BTF member name: {member_name!r}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    temp.unlink(missing_ok=True)
    info = tarfile.TarInfo(member_name)
    info.size = source.stat().st_size
    info.mode = 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    try:
        with (
            open(source, "rb") as handle,
            tarfile.open(temp, "w:xz", preset=9) as archive,
        ):
            archive.addfile(info, handle)
        _verify_archive(temp, member_name)
        size = temp.stat().st_size
        if size > config.MAX_ARCHIVE_BYTES:
            raise BtfError(
                f"compressed BTF is {size} bytes, above GitHub's per-file limit"
            )
        os.replace(temp, destination)
    except (tarfile.TarError, lzma.LZMAError) as exc:
        raise BtfError(f"cannot pack {source}: {exc}") from exc
    finally:
        temp.unlink(missing_ok=True)


def _verify_archive(path: Path, member_name: str) -> None:
    with tarfile.open(path, "r:xz") as archive:
        members = archive.getmembers()
        if len(members) != 1 or members[0].name != member_name:
            raise BtfError(f"unexpected archive members in {path}")
        extracted = archive.extractfile(members[0])
        if extracted is None:
            raise BtfError(f"cannot read {member_name} from {path}")
        header = extracted.read(_MIN_BTF_SIZE)
    _validate_header(header, members[0].size, f"{path}:{member_name}")
