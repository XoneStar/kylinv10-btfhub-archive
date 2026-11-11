import pytest
from kylin_btf.manifest import Manifest
from kylin_btf.models import Candidate
from kylin_btf.selection import dedupe_by_target, select_pending


def candidate(version="V10SP3", arch="x86_64", repo="updates", release="52.70"):
    return Candidate(
        version=version,
        arch=arch,
        repo=repo,
        filename=f"kernel-debuginfo-4.19.90-{release}.v2207.ky10.{arch}.rpm",
        url=f"https://example.invalid/{release}.rpm",
    )


def test_selects_unseen_candidates(tmp_path):
    first = candidate(release="52.70")
    second = candidate(release="52.69")
    selection = select_pending(
        [first, second], Manifest.load(tmp_path / "m.json"), tmp_path, max_new=10
    )
    assert [c.filename for c in selection.pending] == [first.filename, second.filename]


def test_recorded_candidates_are_skipped(tmp_path):
    item = candidate()
    manifest = Manifest.load(tmp_path / "m.json").with_entry(item.source_key, {})
    selection = select_pending([item], manifest, tmp_path, max_new=10)
    assert selection.pending == ()
    assert selection.already_recorded == (item,)


def test_existing_archive_is_skipped_without_manifest(tmp_path):
    item = candidate()
    target = tmp_path / item.archive_relpath
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")
    selection = select_pending(
        [item], Manifest.load(tmp_path / "m.json"), tmp_path, max_new=10
    )
    assert selection.pending == ()
    assert selection.archived_on_disk == (item,)


def test_force_ignores_manifest_and_disk(tmp_path):
    item = candidate()
    target = tmp_path / item.archive_relpath
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")
    manifest = Manifest.load(tmp_path / "m.json").with_entry(item.source_key, {})
    selection = select_pending([item], manifest, tmp_path, max_new=10, force=True)
    assert selection.pending == (item,)


def test_max_new_is_respected(tmp_path):
    items = [candidate(release=f"52.{i}") for i in range(10)]
    selection = select_pending(
        items, Manifest.load(tmp_path / "m.json"), tmp_path, max_new=3
    )
    assert len(selection.pending) == 3


def test_same_archive_target_is_deduplicated(tmp_path):
    updates = candidate(repo="updates")
    base = candidate(repo="base")
    selection = select_pending(
        [updates, base], Manifest.load(tmp_path / "m.json"), tmp_path, max_new=10
    )
    assert selection.pending == (updates,)
    assert selection.duplicate_target == (base,)


def test_dedupe_by_target_keeps_first():
    updates = candidate(repo="updates")
    base = candidate(repo="base")
    assert dedupe_by_target([updates, base]) == [updates]


def test_negative_max_new_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        select_pending([], Manifest.load(tmp_path / "m.json"), tmp_path, max_new=-1)
