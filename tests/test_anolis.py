import gzip

from anolis_btf import pipeline
from anolis_btf.models import AnolisCandidate
from anolis_btf.repodata import (
    debug_url,
    discover_repos,
    discover_versions,
    fetch_candidates,
)

PRIMARY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<metadata xmlns="http://linux.duke.edu/metadata/common">
  <package type="rpm">
    <name>kernel-debuginfo</name>
    <arch>aarch64</arch>
    <checksum type="sha256" pkgid="YES">abc123</checksum>
    <time file="1793689636" build="1793619511"/>
    <size package="1000" installed="2000" archive="3000"/>
    <location href="Packages/kernel-debuginfo-4.18.0-193.28.1.an7.aarch64.rpm"/>
  </package>
  <package type="rpm">
    <name>kernel-debuginfo-common-aarch64</name>
    <checksum type="sha256">def456</checksum>
    <location href="Packages/kernel-debuginfo-common-aarch64-4.18.0-193.28.1.an7.aarch64.rpm"/>
  </package>
</metadata>
"""


def test_debug_url_points_at_debug_packages():
    assert debug_url("7.9", "x86_64", "updates") == (
        "https://mirrors.openanolis.cn/anolis/7.9/updates/x86_64/debug/"
    )


def test_discover_versions_keeps_numeric_directories_sorted(monkeypatch):
    html = """
    <a href="../">../</a>
    <a href="23.5/">23.5/</a>
    <a href="8/">8/</a>
    <a href="epao/">epao/</a>
    <a href="7.9/">7.9/</a>
    <a href="8.2/">8.2/</a>
    <a href="23/">23/</a>
    """
    monkeypatch.setattr("anolis_btf.repodata.read_text", lambda *a, **k: html)
    assert discover_versions() == ["7.9", "8", "8.2", "23", "23.5"]


def test_discover_repos_filters_non_repositories(monkeypatch):
    html = """
    <a href="../">../</a>
    <a href="BaseOS/">BaseOS/</a>
    <a href="AppStream/">AppStream/</a>
    <a href="isos/">isos/</a>
    <a href="source/">source/</a>
    <a href="updateinfo/">updateinfo/</a>
    <a href="Nightly/">Nightly/</a>
    """
    monkeypatch.setattr("anolis_btf.repodata.read_text", lambda *a, **k: html)
    assert discover_repos("8.9") == ["BaseOS", "AppStream"]


def test_resolve_versions_and_repos(monkeypatch):
    monkeypatch.setattr(pipeline, "discover_versions", lambda: ["8.9", "23.5"])
    monkeypatch.setattr(pipeline, "discover_repos", lambda version: [f"{version}-repo"])
    assert pipeline._resolve_versions(["all"]) == ["8.9", "23.5"]
    assert pipeline._resolve_versions(["7.9", "7.9"]) == ["7.9"]
    assert pipeline._resolve_repos("8.9", ["all"]) == ["8.9-repo"]
    assert pipeline._resolve_repos("8.9", ["BaseOS", "source"]) == ["BaseOS"]


def test_candidate_archive_path_keeps_native_arch_in_filename():
    candidate = AnolisCandidate(
        version="7.9",
        arch="aarch64",
        repo="updates",
        filename="kernel-debuginfo-4.18.0-193.28.1.an7.aarch64.rpm",
        url="https://mirrors.openanolis.cn/anolis/7.9/updates/aarch64/debug/Packages/x.rpm",
    )
    assert candidate.kernel_version == "4.18.0-193.28.1.an7"
    assert candidate.archive_relpath == (
        "anolis/7.9/arm64/4.18.0-193.28.1.an7.aarch64.btf.tar.xz"
    )
    assert candidate.source_key == (
        "7.9/aarch64/updates/kernel-debuginfo-4.18.0-193.28.1.an7.aarch64.rpm"
    )


def test_fetch_candidates_uses_repodata_and_skips_common(monkeypatch):
    repomd = b"""<repomd xmlns="http://linux.duke.edu/metadata/repo">
      <data type="primary"><location href="repodata/abc-primary.xml.gz"/></data>
    </repomd>"""
    primary = gzip.compress(PRIMARY_XML.encode())

    def fake_read_bytes(url, *, max_bytes, timeout=None):
        if url.endswith("repomd.xml"):
            return repomd
        assert url.endswith("abc-primary.xml.gz")
        return primary

    monkeypatch.setattr("kylin_btf.repodata.read_bytes", fake_read_bytes)
    candidates = fetch_candidates("7.9", "aarch64", "updates")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.arch == "aarch64"
    assert candidate.checksum_sha256 == "abc123"
    assert candidate.url == (
        "https://mirrors.openanolis.cn/anolis/7.9/updates/aarch64/debug/"
        "Packages/kernel-debuginfo-4.18.0-193.28.1.an7.aarch64.rpm"
    )
