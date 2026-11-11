"""HTTP helpers built on the standard library only."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import config

LOGGER = logging.getLogger(__name__)

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
_PERMANENT_STATUS = {400, 401, 403, 404, 410}
_CHUNK = 1024 * 1024


class HttpError(RuntimeError):
    """Base class for HTTP failures."""


class NotFound(HttpError):
    """The requested URL does not exist (or is not public)."""


class DownloadError(HttpError):
    """A download failed permanently."""


class ChecksumMismatch(DownloadError):
    """Downloaded bytes do not match the repository checksum."""


@dataclass(frozen=True)
class DownloadResult:
    size: int
    sha256: str


def _headers() -> dict[str, str]:
    return {
        "User-Agent": config.USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    }


def _open(url: str, timeout: float, headers: dict[str, str] | None = None):
    request = Request(url, headers=headers or _headers())
    return urlopen(request, timeout=timeout)


def read_bytes(
    url: str, *, max_bytes: int, timeout: float = config.DEFAULT_HTTP_TIMEOUT
) -> bytes:
    """Fetch a small resource, refusing oversized responses."""
    try:
        with _open(url, timeout) as response:
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > max_bytes:
                raise HttpError(
                    f"response too large for {url}: {length} > {max_bytes} bytes"
                )
            data = response.read(max_bytes + 1)
    except HTTPError as exc:
        if exc.code in _PERMANENT_STATUS:
            raise NotFound(f"HTTP {exc.code} for {url}") from exc
        raise HttpError(f"HTTP {exc.code} for {url}") from exc
    except (URLError, TimeoutError) as exc:
        raise HttpError(f"network error for {url}: {exc}") from exc
    if len(data) > max_bytes:
        raise HttpError(f"response too large for {url}: > {max_bytes} bytes")
    return data


def read_text(
    url: str,
    *,
    max_bytes: int,
    timeout: float = config.DEFAULT_HTTP_TIMEOUT,
    encoding: str = "utf-8",
) -> str:
    return read_bytes(url, max_bytes=max_bytes, timeout=timeout).decode(
        encoding, errors="replace"
    )


def download_file(
    url: str,
    destination: Path,
    *,
    expected_sha256: str | None = None,
    timeout: float = config.DEFAULT_DOWNLOAD_TIMEOUT,
    retries: int = 3,
    max_bytes: int = config.MAX_RPM_BYTES,
) -> DownloadResult:
    """Download a large file with resume support and checksum verification.

    Partial data is kept in ``<destination>.part`` between attempts. A checksum
    mismatch discards the partial file and retries from byte zero.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    last_error: BaseException | None = None

    for attempt in range(1, retries + 1):
        offset = part.stat().st_size if part.exists() else 0
        headers = _headers()
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            with _open(url, timeout, headers) as response:
                status = getattr(response, "status", 200)
                if offset and status == 206:
                    mode = "ab"
                    digest = hashlib.sha256()
                    # Recompute incrementally while appending.
                    with open(part, "rb") as existing:
                        for chunk in iter(lambda: existing.read(_CHUNK), b""):
                            digest.update(chunk)
                else:
                    if offset and status == 200:
                        LOGGER.info("server ignored Range for %s; restarting", url)
                    offset = 0
                    mode = "wb"
                    digest = hashlib.sha256()

                length = response.headers.get("Content-Length")
                total = offset + int(length) if length is not None else None
                if total is not None and total > max_bytes:
                    raise DownloadError(
                        f"{url} is {total} bytes, above limit {max_bytes}"
                    )

                written = offset
                next_report = written + 128 * _CHUNK
                with open(part, mode) as handle:
                    while True:
                        chunk = response.read(_CHUNK)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > max_bytes:
                            raise DownloadError(
                                f"{url} exceeds limit {max_bytes} bytes"
                            )
                        digest.update(chunk)
                        handle.write(chunk)
                        if written >= next_report:
                            LOGGER.info(
                                "downloaded %s of %s",
                                _mb(written),
                                _mb(total) if total else "unknown",
                            )
                            next_report = written + 128 * _CHUNK
                    handle.flush()
                    os.fsync(handle.fileno())
        except HTTPError as exc:
            if exc.code in (404, 401, 403, 410):
                raise NotFound(f"HTTP {exc.code} for {url}") from exc
            if exc.code == 416:
                part.unlink(missing_ok=True)
            if exc.code not in _RETRYABLE_STATUS:
                raise HttpError(f"HTTP {exc.code} for {url}") from exc
            last_error = exc
        except DownloadError:
            part.unlink(missing_ok=True)
            raise
        except (URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        else:
            actual = digest.hexdigest()
            if expected_sha256 and actual.lower() != expected_sha256.lower():
                part.unlink(missing_ok=True)
                last_error = ChecksumMismatch(
                    f"checksum mismatch for {url}: {actual} != {expected_sha256}"
                )
            else:
                os.replace(part, destination)
                return DownloadResult(size=written, sha256=actual)

        if attempt < retries:
            delay = min(30.0, 2.0**attempt)
            LOGGER.warning(
                "download attempt %d/%d failed for %s (%s); retrying in %.0fs",
                attempt,
                retries,
                url,
                last_error,
                delay,
            )
            time.sleep(delay)

    raise DownloadError(f"failed to download {url}: {last_error}")


def _mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.0f} MiB"
