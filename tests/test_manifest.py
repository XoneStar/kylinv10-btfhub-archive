import json

import pytest
from kylin_btf.manifest import Manifest, ManifestError


def test_missing_manifest_is_empty(tmp_path):
    manifest = Manifest.load(tmp_path / "missing.json")
    assert manifest.entries == {}
    assert not manifest.contains("V10SP3/x86_64/updates/pkg.rpm")


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = Manifest.load(path).with_entry(
        "V10SP3/x86_64/updates/pkg.rpm", {"btf": "kylin/V10/pkg.btf.tar.xz"}
    )
    manifest.save()

    reloaded = Manifest.load(path)
    assert reloaded.entries == manifest.entries
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    assert list(payload["entries"]) == ["V10SP3/x86_64/updates/pkg.rpm"]


def test_with_entry_is_immutable(tmp_path):
    original = Manifest.load(tmp_path / "manifest.json")
    updated = original.with_entry("a/b/c/d.rpm", {"btf": "x"})
    assert original.entries == {}
    assert updated.entries["a/b/c/d.rpm"]["btf"] == "x"


def test_entries_are_sorted_on_save(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = Manifest.load(path).with_entry("z", {"n": 1}).with_entry("a", {"n": 2})
    manifest.save()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert list(payload["entries"]) == ["a", "z"]


def test_invalid_schema_is_rejected(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema": 999, "entries": {}}), encoding="utf-8")
    with pytest.raises(ManifestError):
        Manifest.load(path)


def test_corrupt_json_is_rejected(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ManifestError):
        Manifest.load(path)
