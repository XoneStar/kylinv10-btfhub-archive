"""Small filesystem helpers with safety checks."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

PathLike = str | Path


class PathSafetyError(ValueError):
    """Raised when a remote-controlled path would escape its root."""


def ensure_within(root: PathLike, relative: PathLike) -> Path:
    """Resolve *relative* under *root* and refuse directory traversal."""
    root_path = Path(root).resolve()
    candidate = (root_path / relative).resolve()
    if candidate != root_path and root_path not in candidate.parents:
        raise PathSafetyError(f"path escapes archive root: {relative!r}")
    return candidate


def sha256_file(path: PathLike, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: PathLike, payload: Any) -> None:
    """Write JSON via a sibling temp file so readers never see half a file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{num_bytes} B"
