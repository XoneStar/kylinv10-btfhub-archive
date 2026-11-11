"""Download and unpack kernel-debuginfo RPMs."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .config import MAX_RPM_BYTES
from .http import DownloadResult, download_file
from .models import Candidate
from .tools import require_tool

LOGGER = logging.getLogger(__name__)

_ELF_MAGIC = b"\x7fELF"


class RpmError(RuntimeError):
    """An RPM could not be unpacked or contains no usable vmlinux."""


def download_rpm(
    candidate: Candidate, destination: Path, *, timeout: float
) -> DownloadResult:
    return download_file(
        candidate.url,
        destination,
        expected_sha256=candidate.checksum_sha256,
        timeout=timeout,
        max_bytes=MAX_RPM_BYTES,
    )


def extract_vmlinux(rpm_path: Path, work_dir: Path, *, timeout: float = 1800) -> Path:
    """Extract only *vmlinux from the RPM's debuginfo payload."""
    rpm2cpio = require_tool("rpm2cpio")
    cpio = require_tool("cpio")
    extract_dir = work_dir / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info("extracting vmlinux from %s", rpm_path.name)
    producer = subprocess.Popen(
        [rpm2cpio, str(rpm_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert producer.stdout is not None
    consumer = subprocess.Popen(
        [cpio, "-idm", "--quiet", "--no-absolute-filenames", "*vmlinux"],
        stdin=producer.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(extract_dir),
    )
    producer.stdout.close()  # allow producer to see SIGPIPE when consumer exits

    try:
        _, consumer_err = consumer.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        producer.kill()
        consumer.kill()
        raise RpmError("cpio extraction timed out")
    producer_err = producer.stderr.read() if producer.stderr else b""
    producer.wait(timeout=60)

    if producer.returncode != 0:
        detail = producer_err.decode("utf-8", "replace").strip()[-2000:]
        raise RpmError(f"rpm2cpio failed ({producer.returncode}): {detail}")
    if consumer.returncode != 0:
        detail = consumer_err.decode("utf-8", "replace").strip()[-2000:]
        raise RpmError(f"cpio failed ({consumer.returncode}): {detail}")

    matches = [path for path in extract_dir.rglob("vmlinux") if path.is_file()]
    if not matches:
        raise RpmError("RPM payload contains no vmlinux")
    vmlinux = max(matches, key=lambda path: path.stat().st_size)
    _validate_elf(vmlinux)
    LOGGER.info("extracted vmlinux: %s", vmlinux)
    return vmlinux


def _validate_elf(path: Path) -> None:
    size = path.stat().st_size
    if size < 1024:
        raise RpmError(f"vmlinux is implausibly small: {path} ({size} bytes)")
    with open(path, "rb") as handle:
        magic = handle.read(4)
    if magic != _ELF_MAGIC:
        raise RpmError(f"extracted vmlinux is not an ELF file: {path}")
