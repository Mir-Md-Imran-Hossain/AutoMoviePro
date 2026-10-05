"""Industrial custom-pipeline unit tests (no live paid APIs)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pipeline.custom_pipeline.job_budget import BudgetExceeded, ensure_budget, record_spend
from pipeline.custom_pipeline.job_state import (
    STATUS_PARTIAL,
    STATUS_SUCCEEDED,
    compute_shippable,
    new_job_state,
    save_job_state,
    load_job_state,
)
from pipeline.custom_pipeline.media_call_guard import claim_create, prompt_fingerprint
from pipeline.custom_pipeline.media_compose import _phrase_cues
from pipeline.custom_pipeline.pipeline_control import (
    clear_cancel,
    is_cancelled,
    request_cancel,
)
from pipeline.custom_pipeline.visual_render import default_image_ffmpeg


def test_phrase_cues_split_multiple():
    cues = _phrase_cues("Hello world. Second phrase! Third one?", 9.0)
    assert len(cues) >= 2
    assert cues[0]["start"] == 0.0
    assert cues[-1]["end"] <= 9.0 + 0.01
    assert all(c["text"] for c in cues)


def test_ffmpeg_filter_portrait_not_1080p():
    filt = default_image_ffmpeg("9:16")
    assert "1080x1920" in filt
    assert "1920x1080" not in filt
    land = default_image_ffmpeg("16:9")
    assert "1920x1080" in land


def test_honest_shippable_requires_all_langs_and_shots():
    state = new_job_state(package_root=Path("/tmp/x"), video_type="short")
    # Incomplete → not shippable
    ship = compute_shippable(
        state,
        shared_success=2,
        shared_expected=3,
        finals_ok=["English"],
        expected_languages=["English", "Hindi"],
    )
    assert ship["shippable"] is False
    assert ship["partial"] is True
    # Complete → shippable
    ship2 = compute_shippable(
        state,
        shared_success=3,
        shared_expected=3,
        finals_ok=["English", "Hindi"],
        expected_languages=["English", "Hindi"],
    )
    assert ship2["shippable"] is True
    assert ship2["partial"] is False


def test_job_state_persist_roundtrip(tmp_path: Path | None = None):
    root = Path(tmp_path) if tmp_path else Path(tempfile.mkdtemp())
    # Minimal package layout
    file_dir = root / "File"
    file_dir.mkdir(parents=True)
    (root / "Audio").mkdir(exist_ok=True)
    (root / "Image").mkdir(exist_ok=True)
    (root / "Video").mkdir(exist_ok=True)
    state = new_job_state(package_root=root, video_type="short", session_id="t1")
    state["status"] = STATUS_PARTIAL
    save_job_state(root, state)
    loaded = load_job_state(root)
    assert loaded is not None
    assert loaded["session_id"] == "t1"
    assert loaded["status"] == STATUS_PARTIAL


def test_budget_cap_raises():
    state = new_job_state(package_root=Path("/tmp/b"), video_type="short")
    state["budget"]["cap_units"] = 5.0
    record_spend(state, kind="video", provider="test", units=3.0)
    ensure_budget(state, kind="image")  # still under
    record_spend(state, kind="video", provider="test", units=3.0)
    try:
        ensure_budget(state, kind="video")
        raised = False
    except BudgetExceeded:
        raised = True
    assert raised


def test_media_guard_claim_dedupe(tmp_path: Path | None = None):
    import os

    root = Path(tmp_path) if tmp_path else Path(tempfile.mkdtemp())
    guard = root / "guard.json"
    os.environ["AMP_MEDIA_GUARD_STATE"] = str(guard)
    # Reset module load flag
    import pipeline.custom_pipeline.media_call_guard as g

    g._loaded = False
    g._created.clear()
    g._circuit_open_until.clear()
    fp = prompt_fingerprint("same prompt", aspect="9:16", duration=5)
    assert claim_create("testprov", fp) is True
    assert claim_create("testprov", fp) is False
    # Reload from disk
    g._loaded = False
    g._created.clear()
    assert claim_create("testprov", fp) is False


def test_cancel_token():
    pkg = Path(tempfile.mkdtemp())
    clear_cancel(pkg)
    assert is_cancelled(pkg) is False
    request_cancel(pkg)
    assert is_cancelled(pkg) is True
    clear_cancel(pkg)


def test_soft_ok_forbidden_in_media_stage_semantics():
    """One language success must not imply ok=True when more expected."""
    from pipeline.custom_pipeline.media_stage import run_media_stage

    # Pure logic: shippable rule already in module — assert via compute
    state = {"expected_languages": ["English", "Hindi"], "expected_shots": 2}
    ship = compute_shippable(
        state,
        shared_success=2,
        shared_expected=2,
        finals_ok=["English"],
        expected_languages=["English", "Hindi"],
    )
    assert ship.get("shippable") is False
    assert STATUS_SUCCEEDED != STATUS_PARTIAL


if __name__ == "__main__":
    # Allow running without pytest
    test_phrase_cues_split_multiple()
    test_ffmpeg_filter_portrait_not_1080p()
    test_honest_shippable_requires_all_langs_and_shots()
    test_job_state_persist_roundtrip()
    test_budget_cap_raises()
    test_media_guard_claim_dedupe()
    test_cancel_token()
    test_soft_ok_forbidden_in_media_stage_semantics()
    print("all industrial tests passed")
