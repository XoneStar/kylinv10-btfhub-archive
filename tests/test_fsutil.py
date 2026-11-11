import json

import pytest
from kylin_btf.fsutil import (
    PathSafetyError,
    ensure_within,
    human_size,
    sha256_file,
    write_json_atomic,
)


def test_ensure_within_accepts_nested_path(tmp_path):
    result = ensure_within(tmp_path, "kylin/V10/file.btf.tar.xz")
    assert result == (tmp_path / "kylin/V10/file.btf.tar.xz").resolve()


@pytest.mark.parametrize("bad", ["../escape", "../../etc/passwd", "a/../../b"])
def test_ensure_within_rejects_traversal(tmp_path, bad):
    with pytest.raises(PathSafetyError):
        ensure_within(tmp_path, bad)


def test_write_json_atomic_creates_parents(tmp_path):
    path = tmp_path / "nested" / "manifest.json"
    write_json_atomic(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}


def test_sha256_file(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_human_size():
    assert human_size(0) == "0.0 B"
    assert human_size(1536) == "1.5 KiB"
