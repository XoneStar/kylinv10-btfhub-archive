"""Subprocess helpers for the external RPM/BTF toolchain."""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Sequence

LOGGER = logging.getLogger(__name__)


class ToolError(RuntimeError):
    """An external tool is missing or failed."""


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ToolError(f"required tool not found in PATH: {name}")
    return path


def first_available(names: Sequence[str]) -> str:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    raise ToolError(f"none of these tools found in PATH: {', '.join(names)}")


def run(
    command: Sequence[str],
    *,
    timeout: float,
    cwd: str | None = None,
    check: bool = True,
    description: str | None = None,
) -> subprocess.CompletedProcess[str]:
    label = description or command[0]
    LOGGER.debug("running %s: %s", label, " ".join(command))
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"{label} timed out after {timeout:.0f}s") from exc
    except OSError as exc:
        raise ToolError(f"{label} could not start: {exc}") from exc

    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip()
        tail = stderr[-2000:] if stderr else "(no stderr)"
        raise ToolError(f"{label} exited with status {result.returncode}: {tail}")
    return result


def tool_version(name: str) -> str:
    """Best-effort version string for manifest provenance."""
    try:
        result = run([name, "--version"], timeout=20, check=False)
    except ToolError:
        return "unknown"
    output = (result.stdout or result.stderr or "").strip().splitlines()
    return output[0].strip() if output else "unknown"
