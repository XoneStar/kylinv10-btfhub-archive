import struct
import tarfile

import pytest
from kylin_btf.btf import BtfError, pack_btf, validate_btf


def write_btf(path, *, magic=0xEB9F, version=1, hdr_len=24, sizes=(24, 0, 24, 0)):
    payload = struct.pack("<HBBIIIII", magic, version, 0, hdr_len, *sizes)
    payload += b"\x00" * 32
    path.write_bytes(payload)


def test_valid_btf_header(tmp_path):
    path = tmp_path / "kernel.btf"
    write_btf(path)
    validate_btf(path)


def test_bad_magic_is_rejected(tmp_path):
    path = tmp_path / "kernel.btf"
    write_btf(path, magic=0x1234)
    with pytest.raises(BtfError):
        validate_btf(path)


def test_bad_version_is_rejected(tmp_path):
    path = tmp_path / "kernel.btf"
    write_btf(path, version=2)
    with pytest.raises(BtfError):
        validate_btf(path)


def test_offsets_beyond_file_are_rejected(tmp_path):
    path = tmp_path / "kernel.btf"
    write_btf(path, sizes=(24, 1000, 24, 0))
    with pytest.raises(BtfError):
        validate_btf(path)


def test_tiny_file_is_rejected(tmp_path):
    path = tmp_path / "kernel.btf"
    path.write_bytes(b"\x9f\xeb")
    with pytest.raises(BtfError):
        validate_btf(path)


def test_pack_btf_round_trip(tmp_path):
    source = tmp_path / "kernel.btf"
    write_btf(source)
    destination = tmp_path / "out" / "4.19.90.btf.tar.xz"
    pack_btf(source, destination, "4.19.90.btf")
    with tarfile.open(destination, "r:xz") as archive:
        names = archive.getnames()
        extracted = archive.extractfile("4.19.90.btf")
        assert extracted is not None
        assert extracted.read() == source.read_bytes()
    assert names == ["4.19.90.btf"]


def test_pack_btf_rejects_unsafe_member(tmp_path):
    source = tmp_path / "kernel.btf"
    write_btf(source)
    with pytest.raises(BtfError):
        pack_btf(source, tmp_path / "out.btf.tar.xz", "../kernel.btf")
