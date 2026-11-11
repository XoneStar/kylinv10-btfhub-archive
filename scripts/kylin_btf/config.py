"""Static configuration for the Kylin V10 BTF archive pipeline."""

from __future__ import annotations

BASE_URL = "https://update.cs2c.com.cn"

# Public layout observed on update.cs2c.com.cn (verified 2026-11-11).
# design.md mentions /NS/V10/{version}/updates/{arch}/debug/, which returns
# 404; the package repositories actually live under os/adv/lic/.
REPO_PATH_TEMPLATE = "/NS/V10/{version}/os/adv/lic/{repo}/{arch}/debug/"

VERSIONS = (
    "V10.0",
    "V10.1",
    "V10SP1",
    "V10SP1.1",
    "V10SP2",
    "V10SP3",
    "V10SP3.1",
)

ARCHES = ("x86_64", "aarch64", "loongarch64")

# "updates" carries post-release errata; "base" carries the GA kernel and is
# the only source for some versions (for example V10.0 and V10SP3.1).
REPOS = ("updates", "base")

ARCHIVE_ROOT = "kylin/V10"
ARCHIVE_SUFFIX = ".btf.tar.xz"
# Upstream RPM arch names differ from the archive's directory names.
ARCHIVE_ARCH_ALIASES = {"aarch64": "arm64"}
MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = 1

PACKAGE_PREFIX = "kernel-debuginfo-"
USER_AGENT = "kylin-v10-btf-archive/1.0"

# Safety limits for data received from the update server.
MAX_REPOMD_BYTES = 2 * 1024 * 1024
MAX_REPODATA_BYTES = 64 * 1024 * 1024
MAX_LISTING_BYTES = 128 * 1024 * 1024
MAX_RPM_BYTES = 3 * 1024 * 1024 * 1024

# GitHub rejects files larger than 100 MiB.
MAX_ARCHIVE_BYTES = 95 * 1024 * 1024

DEFAULT_MAX_NEW = 10
DEFAULT_TIME_BUDGET_MINUTES = 330
DEFAULT_DOWNLOAD_TIMEOUT = 300.0
DEFAULT_HTTP_TIMEOUT = 120.0
