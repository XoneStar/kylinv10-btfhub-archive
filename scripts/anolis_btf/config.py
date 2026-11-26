"""Static configuration for the Anolis OS BTF archive pipeline."""

from __future__ import annotations

BASE_URL = "https://mirrors.openanolis.cn"
HOST = "mirrors.openanolis.cn"

# Public layout: /anolis/{version}/{repo}/{arch}/debug/, with the yum metadata
# under debug/repodata/. Repositories of interest are "os" and "updates".
REPO_PATH_TEMPLATE = "/anolis/{version}/{repo}/{arch}/debug/"

# "all" discovers every numeric VERSION_ID published on the mirror. Anolis 7
# uses os/updates/Plus, 8 uses BaseOS/AppStream/..., and 23 uses os/updates/
# kernel-6, so repository names are discovered per version instead of being
# hard-coded here.
VERSIONS = ("all",)
ARCHES = ("x86_64", "aarch64")
REPOS = ("all",)

# Never repositories: ISO images, SRPM trees, update metadata and nightly
# snapshots have no stable debuginfo packages.
EXCLUDED_REPOS = frozenset({"isos", "source", "updateinfo", "Nightly"})

ARCHIVE_ROOT = "anolis"
ARCHIVE_SUFFIX = ".btf.tar.xz"
# Directory names in the archive, keyed by the upstream RPM architecture.
ARCHIVE_ARCH_ALIASES = {"aarch64": "arm64"}
MANIFEST_NAME = "manifest-anolis.json"

DEFAULT_MAX_NEW = 10
DEFAULT_CONCURRENCY = 3
MAX_CONCURRENCY = 8
MAX_INDEX_BYTES = 4 * 1024 * 1024
DEFAULT_TIME_BUDGET_MINUTES = 330
DEFAULT_DOWNLOAD_TIMEOUT = 300.0
DEFAULT_HTTP_TIMEOUT = 120.0
