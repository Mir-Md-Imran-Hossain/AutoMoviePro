"""Point-1 deep tests: job/stage state machine (virtual + edge angles)."""

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

from pipeline.custom_pipeline.job_state import (
    SCHEMA_VERSION,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    STATUS_SUCCEEDED,
    STAGES,
    compute_shippable,
    finish_active_stage,
    finish_stage,
    heartbeat,
    is_stale,
    load_job_state,
    new_job_state,
    normalize_job_state,
    prepare_resume,
    reaper_mark_stale,
    request_cancel,
    save_job_state,
    start_stage,
    summarize_stages,
)


def _pkg(tmp: Path | None = None) -> Path:
    root = Path(tmp) if tmp else Path(tempfile.mkdtemp())
    # open_package expects numbered folder name
    pkg = root / "001_(Test Topic)"
    for d in ("File", "Audio", "Image", "Video"):
        (pkg / d).mkdir(parents=True, exist_ok=True)
    return pkg


def test_new_state_has_all_stages_pending():
    pkg = _pkg()
    st = new_job_state(package_root=pkg, video_type="short", session_id="s1")
    assert st["schema_version"] == SCHEMA_VERSION
    assert st["status"] == STATUS_RUNNING
    assert st["shippable"] is False
    assert st["partial"] is False
    assert set(st["stages"].keys()) == set(STAGES)
    for name in STAGES:
        assert st["stages"][name]["status"] == STATUS_PENDING


def test_stage_lifecycle_and_active_stage():
    pkg = _pkg()
    st = new_job_state(package_root=pkg, video_type="short")
    start_stage(st, "topic")
    assert st["active_stage"] == "topic"
    assert st["stages"]["topic"]["status"] == STATUS_RUNNING
    assert st["stages"]["topic"]["started_at"]
    finish_stage(st, "topic", status=STATUS_SUCCEEDED, detail={"ok": True})
    assert st["active_stage"] is None
    assert st["stages"]["topic"]["status"] == STATUS_SUCCEEDED
    assert st["stages"]["topic"]["finished_at"]
    kinds = [e["kind"] for e in st["events"]]
    assert "stage.started" in kinds
    assert "stage.finished" in kinds


def test_invalid_stage_raises():
    st = new_job_state(package_root=Path("."), video_type="short")
    try:
        start_stage(st, "not_a_stage")
        assert False, "should raise"
    except ValueError:
        pass
    try:
        finish_stage(st, "bogus", status=STATUS_FAILED)
        assert False, "should raise"
    except ValueError:
        pass


def test_atomic_persist_and_bak_recovery():
    pkg = _pkg()
    st = new_job_state(package_root=pkg, video_type="long", session_id="persist")
    start_stage(st, "visual")
    save_job_state(pkg, st)
    path = pkg / "File" / "job_state.json"
    assert path.is_file()
    loaded = load_job_state(pkg)
    assert loaded is not None
    assert loaded["session_id"] == "persist"
    assert loaded["stages"]["visual"]["status"] == STATUS_RUNNING

    # Corrupt primary; bak should still load
    bak = path.with_suffix(path.suffix + ".bak")
    # Force another save to create bak from previous good file
    loaded["progress_message"] = "hb"
    save_job_state(pkg, loaded)
    assert bak.is_file() or path.is_file()
    path.write_text("{not-json", encoding="utf-8")
    recovered = load_job_state(pkg)
    assert recovered is not None
    assert recovered["session_id"] == "persist"


def test_schema_migrate_legacy_partial_dict():
    pkg = _pkg()
    legacy = {
        "job_id": "old-1",
        "package_root": str(pkg),
        "video_type": "short",
        "status": "running",
        "stages": {"topic": {"status": "succeeded"}},
        # missing budget / degraded / schema_version
    }
    (pkg / "File" / "job_state.json").write_text(
        json.dumps(legacy), encoding="utf-8"
    )
    loaded = load_job_state(pkg)
    assert loaded is not None
    assert loaded["schema_version"] == SCHEMA_VERSION
    assert "budget" in loaded
    assert loaded["stages"]["tts"]["status"] == STATUS_PENDING
    assert loaded["stages"]["topic"]["status"] == STATUS_SUCCEEDED
    assert loaded["job_id"] == "old-1"


def test_normalize_unknown_status_coerced():
    raw = {"status": "weird", "stages": {"media": {"status": "???"}}, "video_type": "short"}
    n = normalize_job_state(raw, package_root=Path("."))
    assert n["status"] == STATUS_RUNNING
    assert n["stages"]["media"]["status"] == STATUS_PENDING


def test_finish_active_stage_on_crash():
    st = new_job_state(package_root=Path("."), video_type="short")
    start_stage(st, "tts")
    name = finish_active_stage(st, status=STATUS_FAILED, error="boom")
    assert name == "tts"
    assert st["stages"]["tts"]["status"] == STATUS_FAILED
    assert "boom" in st["stages"]["tts"]["error"]
    assert st["active_stage"] is None


def test_prepare_resume_clears_zombie_running_stages():
    st = new_job_state(package_root=Path("."), video_type="short")
    start_stage(st, "media")
    st["status"] = STATUS_FAILED  # crashed
    prepare_resume(st)
    assert st["status"] == STATUS_RUNNING
    assert st["resume_count"] == 1
    assert st["cancel_requested"] is False
    assert st["stages"]["media"]["status"] == STATUS_FAILED
    assert st["stages"]["media"]["error"] == "interrupted_resume"
    prepare_resume(st)
    assert st["resume_count"] == 2


def test_reaper_marks_stale_running_job():
    pkg = _pkg()
    st = new_job_state(package_root=pkg, video_type="short")
    start_stage(st, "localize")
    st["heartbeat_at"] = time.time() - 99999
    save_job_state(pkg, st)
    assert is_stale(st, max_silent_sec=60)
    out = reaper_mark_stale(pkg, max_silent_sec=60)
    assert out is not None
    assert out["status"] == STATUS_FAILED
    assert out["stages"]["localize"]["status"] == STATUS_FAILED
    assert out["stages"]["localize"]["error"] == "stale_heartbeat"


def test_reaper_skips_terminal_jobs():
    pkg = _pkg()
    st = new_job_state(package_root=pkg, video_type="short")
    st["status"] = STATUS_SUCCEEDED
    st["heartbeat_at"] = time.time() - 99999
    save_job_state(pkg, st)
    out = reaper_mark_stale(pkg, max_silent_sec=1)
    assert out["status"] == STATUS_SUCCEEDED


def test_cancel_persists():
    pkg = _pkg()
    st = new_job_state(package_root=pkg, video_type="short")
    save_job_state(pkg, st)
    request_cancel(pkg)
    loaded = load_job_state(pkg)
    assert loaded["cancel_requested"] is True
    assert loaded["status"] == STATUS_CANCELLED


def test_compute_shippable_matrix():
    st = new_job_state(package_root=Path("."), video_type="short")
    # empty → failed
    r = compute_shippable(
        st, shared_success=0, shared_expected=3, finals_ok=[], expected_languages=["English"]
    )
    assert r["shippable"] is False
    assert st["status"] == STATUS_FAILED
    # partial shots
    r = compute_shippable(
        st,
        shared_success=2,
        shared_expected=3,
        finals_ok=["English"],
        expected_languages=["English", "Hindi"],
    )
    assert r["shippable"] is False
    assert r["partial"] is True
    assert st["status"] == STATUS_PARTIAL
    assert st["partial"] is True
    # full
    r = compute_shippable(
        st,
        shared_success=3,
        shared_expected=3,
        finals_ok=["English", "Hindi"],
        expected_languages=["English", "Hindi"],
    )
    assert r["shippable"] is True
    assert st["status"] == STATUS_SUCCEEDED
    # cancel wins
    st["cancel_requested"] = True
    r = compute_shippable(
        st,
        shared_success=3,
        shared_expected=3,
        finals_ok=["English", "Hindi"],
        expected_languages=["English", "Hindi"],
    )
    assert r["shippable"] is False
    assert st["status"] == STATUS_CANCELLED


def test_heartbeat_updates_timestamp():
    pkg = _pkg()
    st = new_job_state(package_root=pkg, video_type="short")
    save_job_state(pkg, st)
    t0 = st["heartbeat_at"]
    time.sleep(0.05)
    heartbeat(pkg, st, "working")
    assert st["heartbeat_at"] >= t0
    assert st["progress_message"] == "working"
    loaded = load_job_state(pkg)
    assert loaded["progress_message"] == "working"


def test_concurrent_saves_do_not_corrupt():
    pkg = _pkg()
    st = new_job_state(package_root=pkg, video_type="short")
    save_job_state(pkg, st)
    errors: list = []

    def worker(i: int) -> None:
        try:
            local = load_job_state(pkg)
            assert local is not None
            start_stage(local, STAGES[i % len(STAGES)])
            finish_stage(local, STAGES[i % len(STAGES)], status=STATUS_SUCCEEDED)
            save_job_state(pkg, local)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    final = load_job_state(pkg)
    assert final is not None
    # Must still parse as valid JSON with all stages
    assert set(final["stages"].keys()) == set(STAGES)
    json.loads((pkg / "File" / "job_state.json").read_text(encoding="utf-8"))


def test_summarize_and_skip_status():
    st = new_job_state(package_root=Path("."), video_type="short")
    finish_stage(st, "topic", status=STATUS_SKIPPED, detail={"resumed": True})
    s = summarize_stages(st)
    assert s["topic"] == STATUS_SKIPPED
    assert s["media"] == STATUS_PENDING


def test_mutate_job_state_rmw():
    from pipeline.custom_pipeline.job_state import mutate_job_state

    pkg = _pkg()

    def bump(st):
        st["progress_pct"] = 42
        start_stage(st, "quality")

    out = mutate_job_state(pkg, bump)
    assert out["progress_pct"] == 42
    assert out["active_stage"] == "quality"
    loaded = load_job_state(pkg)
    assert loaded["progress_pct"] == 42


def test_live_package_roundtrip_if_exists():
    """Live angle: if an existing Short package exists, load/save must not break it."""
    root = Path(__file__).resolve().parents[2] / "Output" / "Short"
    if not root.is_dir():
        return
    pkgs = [p for p in root.iterdir() if p.is_dir() and (p / "File").is_dir()]
    if not pkgs:
        return
    pkg = pkgs[0]
    before = load_job_state(pkg)
    st = before or new_job_state(package_root=pkg, video_type="short", session_id="audit")
    # Don't overwrite production status aggressively — write to a shadow then restore
    shadow = dict(st)
    shadow["progress_message"] = "point1_audit_probe"
    # Save then reload then restore previous if we had one
    save_job_state(pkg, shadow)
    mid = load_job_state(pkg)
    assert mid is not None
    assert mid["progress_message"] == "point1_audit_probe"
    if before is not None:
        save_job_state(pkg, before)
    else:
        # leave normalized state — acceptable for packages without prior job_state
        pass


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failed.append((fn.__name__, exc))
            print(f"FAIL {fn.__name__}: {exc}")
    if failed:
        raise SystemExit(f"{len(failed)}/{len(tests)} failed")
    print(f"all {len(tests)} point-1 tests passed")
