"""Point-2 deep tests: progress + cancel end-to-end."""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path

from pipeline.custom_pipeline.job_state import (
    STATUS_CANCELLED,
    load_job_state,
    new_job_state,
    save_job_state,
    start_stage,
)
from pipeline.custom_pipeline.media_gap import set_media_gap_package, wait_media_gap
from pipeline.custom_pipeline.pipeline_control import (
    PipelineCancelled,
    check_cancelled,
    clear_cancel,
    emit_progress,
    interruptible_sleep,
    is_cancelled,
    register_progress,
    request_cancel,
    wall_clock_exceeded,
)


def _pkg() -> Path:
    root = Path(tempfile.mkdtemp())
    pkg = root / "001_(Cancel Test)"
    for d in ("File", "Audio", "Image", "Video"):
        (pkg / d).mkdir(parents=True, exist_ok=True)
    return pkg


def test_ram_cancel_flag():
    pkg = _pkg()
    clear_cancel(pkg)
    assert is_cancelled(pkg) is False
    request_cancel(pkg)
    assert is_cancelled(pkg) is True
    clear_cancel(pkg)
    assert is_cancelled(pkg) is False


def test_disk_cancel_visible_without_ram_flag():
    """Simulate CLI cancel: only job_state.json written, RAM empty."""
    pkg = _pkg()
    clear_cancel(pkg)
    st = new_job_state(package_root=pkg, video_type="short")
    save_job_state(pkg, st)
    # Write cancel via job_state API only (bypass pipeline_control RAM)
    from pipeline.custom_pipeline.job_state import request_cancel as js_cancel

    # Ensure RAM clear
    clear_cancel(pkg)
    # Direct disk cancel without setting RAM first — js_cancel alone
    # First clear disk cancel from previous clear_cancel
    st2 = load_job_state(pkg)
    assert st2 is not None
    # Use js path: pipeline request_cancel sets both; we test is_cancelled disk poll
    # by manually setting cancel on disk after clearing RAM
    from pipeline.custom_pipeline.job_state import mutate_job_state

    def mark(s):
        s["cancel_requested"] = True
        s["status"] = STATUS_CANCELLED

    # Clear RAM only
    from pipeline.custom_pipeline import pipeline_control as pc

    with pc._lock:
        pc._cancel_flags.pop(pc._key(pkg), None)

    mutate_job_state(pkg, mark)
    assert is_cancelled(pkg) is True


def test_check_cancelled_raises():
    pkg = _pkg()
    clear_cancel(pkg)
    request_cancel(pkg)
    try:
        check_cancelled(pkg)
        assert False, "expected PipelineCancelled"
    except PipelineCancelled:
        pass
    clear_cancel(pkg)


def test_interruptible_sleep_aborts_quickly():
    pkg = _pkg()
    clear_cancel(pkg)
    st = new_job_state(package_root=pkg, video_type="short")
    save_job_state(pkg, st)

    def cancel_soon():
        time.sleep(0.15)
        request_cancel(pkg)

    t = threading.Thread(target=cancel_soon)
    t.start()
    t0 = time.monotonic()
    try:
        interruptible_sleep(5.0, package_root=pkg, state=st, slice_sec=0.1)
        assert False, "should have cancelled"
    except PipelineCancelled:
        elapsed = time.monotonic() - t0
        assert elapsed < 2.0, f"cancel too slow: {elapsed}"
    t.join()
    clear_cancel(pkg)


def test_media_gap_propagates_cancel():
    pkg = _pkg()
    clear_cancel(pkg)
    os.environ["AMP_MEDIA_CALL_GAP_SEC"] = "3"
    # Force last call recent so wait > 0
    import pipeline.custom_pipeline.media_gap as mg

    mg._last_mono = time.monotonic()
    set_media_gap_package(str(pkg), None)

    def cancel_soon():
        time.sleep(0.1)
        request_cancel(pkg)

    t = threading.Thread(target=cancel_soon)
    t.start()
    t0 = time.monotonic()
    try:
        wait_media_gap(reason="test")
        assert False, "should cancel during gap"
    except PipelineCancelled:
        assert time.monotonic() - t0 < 2.5
    t.join()
    clear_cancel(pkg)
    os.environ["AMP_MEDIA_CALL_GAP_SEC"] = "0"


def test_emit_progress_does_not_clobber_stages():
    pkg = _pkg()
    st = new_job_state(package_root=pkg, video_type="short")
    start_stage(st, "media")
    save_job_state(pkg, st)
    # In-memory advance that isn't saved yet
    st["stages"]["media"]["detail"] = {"shots": 3}
    emit_progress(pkg, 55, "composing", state=st)
    assert st["stages"]["media"]["status"] == "running"
    assert st["stages"]["media"]["detail"]["shots"] == 3
    loaded = load_job_state(pkg)
    assert loaded["progress_pct"] == 55
    assert loaded["stages"]["media"]["detail"]["shots"] == 3


def test_progress_callback_invoked():
    pkg = _pkg()
    seen = []

    def cb(pct, msg):
        seen.append((pct, msg))

    register_progress(pkg, cb)
    st = new_job_state(package_root=pkg, video_type="short")
    save_job_state(pkg, st)
    emit_progress(pkg, 10, "topic", state=st)
    register_progress(pkg, None)
    assert seen and seen[0][0] == 10 and seen[0][1] == "topic"


def test_clear_cancel_clears_disk_flag():
    pkg = _pkg()
    st = new_job_state(package_root=pkg, video_type="short")
    save_job_state(pkg, st)
    request_cancel(pkg)
    assert load_job_state(pkg)["cancel_requested"] is True
    clear_cancel(pkg)
    assert is_cancelled(pkg) is False
    loaded = load_job_state(pkg)
    assert loaded["cancel_requested"] is False


def test_wall_clock():
    assert wall_clock_exceeded(time.time() - 10, 5) is True
    assert wall_clock_exceeded(time.time(), 100) is False
    assert wall_clock_exceeded(time.time() - 10, 0) is False


def test_cli_cancel_status_roundtrip():
    """Live-ish: status + cancel CLI helpers against a package."""
    from pipeline.custom_pipeline.__main__ import _cmd_cancel, _cmd_status
    import argparse

    pkg = _pkg()
    st = new_job_state(package_root=pkg, video_type="short")
    save_job_state(pkg, st)
    assert _cmd_status(argparse.Namespace(package_root=str(pkg))) == 0
    assert _cmd_cancel(argparse.Namespace(package_root=str(pkg))) == 0
    assert is_cancelled(pkg) is True
    clear_cancel(pkg)


if __name__ == "__main__":
    os.environ.setdefault("AMP_MEDIA_CALL_GAP_SEC", "0")
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
    print(f"all {len(tests)} point-2 tests passed")
