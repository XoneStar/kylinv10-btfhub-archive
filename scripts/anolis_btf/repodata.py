"""Discover Anolis kernel-debuginfo packages from the official OpenAnolis mirror."""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from urllib.parse import unquote

from kylin_btf.http import read_text
from kylin_btf.repodata import fetch_candidates as _fetch_candidates

from . import config
from .models import AnolisCandidate

LOGGER = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


class _DirectoryParser(HTMLParser):
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


def _directories(url: str, *, timeout: float) -> list[str]:
    html_text = read_text(url, max_bytes=config.MAX_INDEX_BYTES, timeout=timeout)
    parser = _DirectoryParser()
    parser.feed(html_text)
    parser.close()
    names: list[str] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        if not href or href.startswith(("..", "/", "?", "#")):
            continue
        name = unquote(href.rstrip("/").rsplit("/", 1)[-1])
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def discover_versions(*, timeout: float = config.DEFAULT_HTTP_TIMEOUT) -> list[str]:
    """Return every numeric VERSION_ID directory, oldest first."""
    versions = [
        name
        for name in _directories(config.BASE_URL + "/anolis/", timeout=timeout)
        if _VERSION_RE.fullmatch(name)
    ]
    versions.sort(key=_version_key)
    LOGGER.info(
        "discovered %d Anolis version(s): %s", len(versions), ",".join(versions)
    )
    return versions


def discover_repos(
    version: str, *, timeout: float = config.DEFAULT_HTTP_TIMEOUT
) -> list[str]:
    """Return repository directories for one VERSION_ID."""
    repos = [
        name
        for name in _directories(
            f"{config.BASE_URL}/anolis/{version}/", timeout=timeout
        )
        if _REPO_RE.fullmatch(name) and name not in config.EXCLUDED_REPOS
    ]
    LOGGER.info(
        "using %d repository/repositories for %s: %s",
        len(repos),
        version,
        ",".join(repos),
    )
    return repos


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def debug_url(version: str, arch: str, repo: str) -> str:
    return config.BASE_URL + config.REPO_PATH_TEMPLATE.format(
        version=version, arch=arch, repo=repo
    )


def fetch_candidates(
    version: str,
    arch: str,
    repo: str,
    *,
    timeout: float = config.DEFAULT_HTTP_TIMEOUT,
) -> list[AnolisCandidate]:
    return _fetch_candidates(
        version,
        arch,
        repo,
        timeout=timeout,
        base_url=debug_url(version, arch, repo),
        candidate_factory=AnolisCandidate,
        allowed_host=config.HOST,
    )


__all__ = [
    "debug_url",
    "discover_repos",
    "discover_versions",
    "fetch_candidates",
]
