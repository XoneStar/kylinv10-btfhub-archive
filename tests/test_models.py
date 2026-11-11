from pathlib import PurePosixPath

import pytest
from kylin_btf.models import (
    Candidate,
    is_kernel_debuginfo,
    kernel_version_from_filename,
    version_sort_key,
)


@pytest.mark.parametrize(
    "filename,arch,expected",
    [
        (
            "kernel-debuginfo-4.19.90-52.70.v2207.ky10.x86_64.rpm",
            "x86_64",
            "4.19.90-52.70.v2207.ky10",
        ),
        (
            "kernel-debuginfo-4.19.90-52.70.v2207.ky10.aarch64.rpm",
            "aarch64",
            "4.19.90-52.70.v2207.ky10",
        ),
        (
            "kernel-debuginfo-4.19.90-52.70.v2207.a.ky10.loongarch64.rpm",
            "loongarch64",
            "4.19.90-52.70.v2207.a.ky10",
        ),
        (
            "kernel-debuginfo-4.19.90-vhulk2001.1.0.0026.ns7.15.x86_64.rpm",
            "x86_64",
            "4.19.90-vhulk2001.1.0.0026.ns7.15",
        ),
    ],
)
def test_kernel_version_from_filename(filename, arch, expected):
    assert kernel_version_from_filename(filename, arch) == expected


@pytest.mark.parametrize(
    "filename",
    [
        "kernel-tools-debuginfo-4.19.90-52.70.ky10.x86_64.rpm",
        "kernel-hash-init-debuginfo-1.0.5kord-se.ky10.x86_64.rpm",
        "kernel-debuginfo-common-x86_64-4.19.90-52.70.ky10.x86_64.rpm",
        "kernel-debuginfo-4.19.90-52.70.ky10.src.rpm",
        "../../kernel-debuginfo-4.19.90-52.70.ky10.x86_64.rpm",
        "kernel-debuginfo-4.19.90-52.70.ky10.x86_64.rpm.exe",
        "",
    ],
)
def test_non_kernel_debuginfo_is_rejected(filename):
    assert not is_kernel_debuginfo(filename)


def test_wrong_arch_is_rejected():
    with pytest.raises(ValueError):
        kernel_version_from_filename(
            "kernel-debuginfo-4.19.90-52.70.ky10.x86_64.rpm", "aarch64"
        )


def test_version_sort_orders_numerically():
    assert version_sort_key("4.19.90-52.70.v2207.ky10") > version_sort_key(
        "4.19.90-52.9.v2207.ky10"
    )


def test_candidate_archive_path_is_inside_archive_root():
    candidate = Candidate(
        version="V10SP3",
        arch="x86_64",
        repo="updates",
        filename="kernel-debuginfo-4.19.90-52.70.v2207.ky10.x86_64.rpm",
        url="https://example.invalid/pkg.rpm",
    )
    assert candidate.kernel_version == "4.19.90-52.70.v2207.ky10"
    assert candidate.archive_relpath == str(
        PurePosixPath("kylin/V10/x86_64/4.19.90-52.70.v2207.ky10.btf.tar.xz")
    )
    assert candidate.source_key == (
        "V10SP3/x86_64/updates/kernel-debuginfo-4.19.90-52.70.v2207.ky10.x86_64.rpm"
    )


def test_aarch64_packages_are_stored_under_arm64():
    candidate = Candidate(
        version="V10SP3",
        arch="aarch64",
        repo="updates",
        filename="kernel-debuginfo-4.19.90-52.70.v2207.ky10.aarch64.rpm",
        url="https://example.invalid/pkg.rpm",
    )
    assert candidate.archive_arch == "arm64"
    assert candidate.archive_relpath == str(
        PurePosixPath("kylin/V10/arm64/4.19.90-52.70.v2207.ky10.btf.tar.xz")
    )
