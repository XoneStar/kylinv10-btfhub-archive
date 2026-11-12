import threading
import time

from kylin_btf import pipeline
from kylin_btf.manifest import Manifest
from kylin_btf.models import Candidate
from kylin_btf.report import RunReport


def candidate(release: str) -> Candidate:
    return Candidate(
        version="V10SP3",
        arch="x86_64",
        repo="updates",
        filename=f"kernel-debuginfo-4.19.90-{release}.v2207.ky10.x86_64.rpm",
        url=f"https://example.invalid/{release}.rpm",
    )


def test_pending_candidates_run_in_parallel(tmp_path, monkeypatch):
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_process(item, options, toolchain):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.1)
        with lock:
            active -= 1
        entry = {"btf": item.archive_relpath, "btf_size": 1}
        row = {
            "version": item.version,
            "arch": item.arch,
            "btf": item.archive_relpath,
            "btf_size": 1,
        }
        return item.source_key, entry, row

    monkeypatch.setattr(pipeline, "_process_candidate", fake_process)
    items = [candidate(release=f"52.{index}") for index in range(3)]
    options = pipeline.RunOptions(repo_root=tmp_path, concurrency=3)
    report = RunReport()

    manifest = pipeline._process_pending(
        items,
        options,
        Manifest.load(tmp_path / "kylin/V10/manifest.json"),
        None,
        report,
        deadline=time.monotonic() + 600,
    )

    assert peak == 3
    assert len(report.processed) == 3
    assert not report.failures
    assert all(manifest.contains(item.source_key) for item in items)


def test_expired_deadline_defers_everything(tmp_path, monkeypatch):
    def fail_process(item, options, toolchain):
        raise AssertionError("deferred candidates must not be processed")

    monkeypatch.setattr(pipeline, "_process_candidate", fail_process)
    options = pipeline.RunOptions(repo_root=tmp_path, concurrency=3)
    report = RunReport()

    pipeline._process_pending(
        [candidate("52.70")],
        options,
        Manifest.load(tmp_path / "kylin/V10/manifest.json"),
        None,
        report,
        deadline=0.0,
    )

    assert len(report.deferred) == 1
    assert not report.processed
