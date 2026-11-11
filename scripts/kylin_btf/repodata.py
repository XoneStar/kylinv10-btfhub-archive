"""Discover kernel-debuginfo packages from the Kylin update repositories."""

from __future__ import annotations

import gzip
import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import unquote, urljoin, urlparse

from . import config
from .http import HttpError, NotFound, read_bytes, read_text
from .models import Candidate, PackageInfo, is_kernel_debuginfo

LOGGER = logging.getLogger(__name__)


class DiscoveryError(RuntimeError):
    """The repository metadata could not be read or parsed."""


def debug_url(version: str, arch: str, repo: str) -> str:
    return config.BASE_URL + config.REPO_PATH_TEMPLATE.format(
        version=version, arch=arch, repo=repo
    )


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_repomd_primary(xml_data: bytes) -> str:
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        raise DiscoveryError(f"invalid repomd.xml: {exc}") from exc
    for data in root:
        if _localname(data.tag) != "data" or data.get("type") != "primary":
            continue
        for child in data:
            if _localname(child.tag) == "location" and child.get("href"):
                return child.get("href", "")
    raise DiscoveryError("repomd.xml has no primary metadata location")


def _load_primary_gz(xml_gz: bytes) -> bytes:
    try:
        with gzip.GzipFile(fileobj=BytesIO(xml_gz)) as handle:
            data = handle.read(config.MAX_REPODATA_BYTES + 1)
    except (OSError, EOFError) as exc:
        raise DiscoveryError(f"invalid primary metadata gzip: {exc}") from exc
    if len(data) > config.MAX_REPODATA_BYTES:
        raise DiscoveryError("primary metadata exceeds size limit")
    return data


def _parse_primary(xml_data: bytes) -> list[PackageInfo]:
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        raise DiscoveryError(f"invalid primary metadata: {exc}") from exc

    packages: list[PackageInfo] = []
    for node in root:
        if _localname(node.tag) != "package":
            continue
        checksum = None
        checksum_type = None
        location: str | None = None
        size: int | None = None
        build_time: int | None = None

        for child in node:
            name = _localname(child.tag)
            if name == "checksum":
                checksum = (child.text or "").strip() or None
                checksum_type = child.get("type")
            elif name == "location":
                location = child.get("href")
            elif name == "size":
                raw_size = child.get("package")
                if raw_size and raw_size.isdigit():
                    size = int(raw_size)
            elif name == "time":
                raw_time = child.get("build") or child.get("file")
                if raw_time and raw_time.isdigit():
                    build_time = int(raw_time)

        if not location:
            continue
        filename = unquote(location.rsplit("/", 1)[-1])
        if not is_kernel_debuginfo(filename):
            continue
        packages.append(
            PackageInfo(
                filename=filename,
                href=location,
                checksum_sha256=(
                    checksum
                    if checksum_type and checksum_type.lower() == "sha256"
                    else None
                ),
                size=size,
                build_time=build_time,
            )
        )
    return packages


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)
                break


def parse_html_listing(html_text: str) -> list[PackageInfo]:
    parser = _AnchorParser()
    parser.feed(html_text)
    parser.close()
    packages: list[PackageInfo] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        if not href or href.startswith(("..", "/", "?", "#")):
            continue
        filename = unquote(href.rsplit("/", 1)[-1])
        if filename in seen or not is_kernel_debuginfo(filename):
            continue
        seen.add(filename)
        packages.append(PackageInfo(filename=filename, href=href))
    return packages


def _candidates_from_packages(
    version: str, arch: str, repo: str, base_url: str, packages: Iterable[PackageInfo]
) -> list[Candidate]:
    expected_host = urlparse(config.BASE_URL).netloc
    result: list[Candidate] = []
    for package in packages:
        package_url = urljoin(base_url, package.href)
        parsed = urlparse(package_url)
        if parsed.scheme != "https" or parsed.netloc != expected_host:
            LOGGER.warning(
                "skipping package with unexpected URL %s/%s/%s: %s",
                version,
                arch,
                repo,
                package_url,
            )
            continue
        try:
            candidate = Candidate(
                version=version,
                arch=arch,
                repo=repo,
                filename=package.filename,
                url=package_url,
                checksum_sha256=package.checksum_sha256,
                size=package.size,
                build_time=package.build_time,
            )
            # Force validation of the filename/arch pair now.
            _ = candidate.kernel_version
        except ValueError as exc:
            LOGGER.warning("skipping %s/%s/%s: %s", version, arch, repo, exc)
            continue
        result.append(candidate)
    return result


def _from_repodata(base_url: str) -> list[PackageInfo] | None:
    repomd_url = urljoin(base_url, "repodata/repomd.xml")
    try:
        repomd = read_bytes(repomd_url, max_bytes=config.MAX_REPOMD_BYTES)
    except NotFound:
        return None
    primary_href = _find_repomd_primary(repomd)
    primary_url = urljoin(base_url, primary_href)
    try:
        primary_gz = read_bytes(primary_url, max_bytes=config.MAX_REPODATA_BYTES)
    except NotFound as exc:
        # repomd.xml exists but points at a missing primary file. Fall back to
        # the directory listing instead of treating the whole repo as absent.
        raise DiscoveryError(f"primary metadata is missing: {primary_url}") from exc
    return _parse_primary(_load_primary_gz(primary_gz))


def fetch_candidates(
    version: str, arch: str, repo: str, *, timeout: float = config.DEFAULT_HTTP_TIMEOUT
) -> list[Candidate]:
    """Return kernel-debuginfo packages, newest first.

    Prefers the repository's primary metadata (compact, includes sha256) and
    falls back to parsing the nginx directory listing.
    """
    base_url = debug_url(version, arch, repo)
    packages: list[PackageInfo] | None = None
    try:
        packages = _from_repodata(base_url)
    except NotFound:
        return []
    except (DiscoveryError, HttpError, OSError) as exc:
        LOGGER.warning(
            "repodata unavailable for %s/%s/%s (%s); using directory listing",
            version,
            arch,
            repo,
            exc,
        )

    if packages is None:
        try:
            html_text = read_text(
                base_url, max_bytes=config.MAX_LISTING_BYTES, timeout=timeout
            )
        except NotFound:
            return []
        packages = parse_html_listing(html_text)

    candidates = _candidates_from_packages(version, arch, repo, base_url, packages)
    candidates.sort(key=lambda item: item.sort_key(), reverse=True)
    LOGGER.info(
        "discovered %d kernel-debuginfo package(s) in %s/%s/%s",
        len(candidates),
        version,
        arch,
        repo,
    )
    return candidates
