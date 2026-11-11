import gzip

import pytest
from kylin_btf.repodata import (
    DiscoveryError,
    _find_repomd_primary,
    _parse_primary,
    fetch_candidates,
    parse_html_listing,
)

PRIMARY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<metadata xmlns="http://linux.duke.edu/metadata/common"
          xmlns:rpm="http://linux.duke.edu/metadata/rpm">
  <package type="rpm">
    <name>kernel-debuginfo</name>
    <arch>x86_64</arch>
    <version epoch="0" ver="4.19.90" rel="52.70.v2207.ky10"/>
    <checksum type="sha256" pkgid="YES">abc123</checksum>
    <time file="1793689636" build="1793619511"/>
    <size package="484266932" installed="2341927212" archive="2344180288"/>
    <location href="kernel-debuginfo-4.19.90-52.70.v2207.ky10.x86_64.rpm"/>
  </package>
  <package type="rpm">
    <name>kernel-tools-debuginfo</name>
    <checksum type="sha256">def456</checksum>
    <location href="kernel-tools-debuginfo-4.19.90-52.70.v2207.ky10.x86_64.rpm"/>
  </package>
  <package type="rpm">
    <name>kernel-debuginfo-common-x86_64</name>
    <checksum type="sha256">ghi789</checksum>
    <location href="kernel-debuginfo-common-x86_64-4.19.90-52.70.v2207.ky10.x86_64.rpm"/>
  </package>
</metadata>
"""


def test_parse_primary_keeps_only_kernel_debuginfo():
    packages = _parse_primary(PRIMARY_XML.encode())
    assert len(packages) == 1
    package = packages[0]
    assert package.filename == ("kernel-debuginfo-4.19.90-52.70.v2207.ky10.x86_64.rpm")
    assert package.checksum_sha256 == "abc123"
    assert package.size == 484266932
    assert package.build_time == 1793619511


def test_find_repomd_primary():
    repomd = b"""<?xml version="1.0"?>
    <repomd xmlns="http://linux.duke.edu/metadata/repo">
      <data type="other"><location href="repodata/other.xml.gz"/></data>
      <data type="primary"><location href="repodata/abc-primary.xml.gz"/></data>
    </repomd>"""
    assert _find_repomd_primary(repomd) == "repodata/abc-primary.xml.gz"


def test_find_repomd_primary_missing():
    with pytest.raises(DiscoveryError):
        _find_repomd_primary(b"<repomd/>")


def test_parse_html_listing_uses_full_href_for_truncated_names():
    html = """
    <html><body><pre>
    <a href="../">../</a>
    <a href="kernel-debuginfo-4.19.90-52.70.v2207.ky10.x86_64.rpm">kernel-debuginfo-4.19.90-52.70.v2207.ky..&gt;</a>
    <a href="kernel-tools-debuginfo-4.19.90-52.70.v2207.ky10.x86_64.rpm">kernel-tools..&gt;</a>
    <a href="kernel-debuginfo-4.19.90-52.71.v2207.ky10.x86_64.rpm">kernel-debuginfo..&gt;</a>
    </pre></body></html>
    """
    packages = parse_html_listing(html)
    assert [p.filename for p in packages] == [
        "kernel-debuginfo-4.19.90-52.70.v2207.ky10.x86_64.rpm",
        "kernel-debuginfo-4.19.90-52.71.v2207.ky10.x86_64.rpm",
    ]
    assert packages[0].checksum_sha256 is None


def test_fetch_candidates_uses_repodata_and_sorts_newest_first(monkeypatch):
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
    candidates = fetch_candidates("V10SP3", "x86_64", "updates")
    assert len(candidates) == 1
    assert candidates[0].url == (
        "https://update.cs2c.com.cn/NS/V10/V10SP3/os/adv/lic/updates/"
        "x86_64/debug/kernel-debuginfo-4.19.90-52.70.v2207.ky10.x86_64.rpm"
    )
