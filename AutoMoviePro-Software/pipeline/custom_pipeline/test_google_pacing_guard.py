"""Unit tests for Google Pro Pacing Guard and Intelligent Quota Manager."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

from pipeline.custom_pipeline.google_pacing_guard import (
    DEFAULT_PACING_RANGES,
    analyze_quota_error,
    compute_random_gap,
    get_pacing_range,
    handle_quota_exhaustion,
    is_package_video_completed,
    post_generation_cooldown,
    wait_pacing_gap,
)
from pipeline.custom_pipeline.pipeline_control import PipelineCancelled, request_cancel


def test_pacing_ranges_defaults_and_randomness():
    """Verify that video, audio, image, and general have proper randomized intervals."""
    for mod in ("video", "audio", "image", "general"):
        min_sec, max_sec = get_pacing_range(mod)
        assert min_sec > 0
        assert max_sec > min_sec
        # Video and audio have longer delays than general
        if mod in ("video", "audio"):
            assert min_sec >= 30.0

        # Verify randomness produces values within range
        gaps = [compute_random_gap(mod) for _ in range(20)]
        assert all(min_sec <= g <= max_sec for g in gaps)
        # Check there is variance (not a fixed single constant)
        assert len(set(gaps)) > 1


def test_pacing_env_overrides():
    """Verify environment variables can customize min/max pacing per modality."""
    with mock.patch.dict(os.environ, {"AMP_GAP_VIDEO_MIN": "12.0", "AMP_GAP_VIDEO_MAX": "15.0"}):
        min_sec, max_sec = get_pacing_range("video")
        assert min_sec == 12.0
        assert max_sec == 15.0
        g = compute_random_gap("video")
        assert 12.0 <= g <= 15.0


def test_wait_pacing_gap_respects_elapsed():
    """Test that wait_pacing_gap sleeps only the necessary difference."""
    with mock.patch.dict(os.environ, {"AMP_GAP_GENERAL_MIN": "0.1", "AMP_GAP_GENERAL_MAX": "0.2"}):
        # First call establishes baseline
        w1 = wait_pacing_gap(modality="general", provider="test_prov_a")
        # Immediate second call must wait
        w2 = wait_pacing_gap(modality="general", provider="test_prov_a")
        assert w2 > 0.05


def test_post_generation_cooldown_interruptible():
    """Verify post_generation_cooldown is immediately interrupted by cancel signal."""
    tmp = Path(tempfile.mkdtemp())
    pkg = tmp / "001_(Test)"
    pkg.mkdir()

    with mock.patch.dict(os.environ, {"AMP_GAP_IMAGE_MIN": "10.0", "AMP_GAP_IMAGE_MAX": "20.0"}):
        request_cancel(pkg)
        with pytest.raises(PipelineCancelled):
            post_generation_cooldown(modality="image", provider="test_google", package_root=str(pkg))


def test_analyze_quota_error_header():
    """Test parsing explicit retry-after header."""
    res = analyze_quota_error(
        "Too Many Requests",
        response_headers={"retry-after": "45"},
    )
    assert res.is_quota is True
    assert 45.0 <= res.cooldown_seconds <= 55.0
    assert res.can_auto_wait is True
    assert res.window_type == "explicit_retry_after"


def test_analyze_quota_error_text_varieties():
    """Test parsing various Google / Gemini error text patterns."""
    # 1. Text retry after seconds
    r1 = analyze_quota_error("429 Resource has been exhausted (e.g. check quota). retry after 25s")
    assert r1.is_quota is True
    assert 25.0 <= r1.cooldown_seconds <= 40.0
    assert r1.can_auto_wait is True

    # 2. Text retry after minutes
    r2 = analyze_quota_error("Please retry after 5m")
    assert r2.is_quota is True
    assert 300.0 <= r2.cooldown_seconds <= 320.0
    assert r2.can_auto_wait is True

    # 3. 10-minute window
    r3 = analyze_quota_error("Quota exceeded for quota metric ... per 10 minutes")
    assert r3.is_quota is True
    assert 600.0 <= r3.cooldown_seconds <= 640.0
    assert r3.can_auto_wait is True
    assert r3.window_type == "short_window"

    # 4. Daily limit (limit: 0, per day)
    r4 = analyze_quota_error("429 RESOURCE_EXHAUSTED. limit: 0, generate_content_free_tier per day")
    assert r4.is_quota is True
    assert r4.cooldown_seconds >= 3600.0 * 5.0
    assert r4.can_auto_wait is False  # Cannot auto wait 6h+
    assert r4.window_type == "daily"


def test_handle_quota_exhaustion_decision_logic():
    """Test decision logic between short auto-wait vs. complete-by-any-means fallback."""
    tmp = Path(tempfile.mkdtemp())
    pkg = tmp / "002_(Incomplete Video)"
    pkg.mkdir()

    # Case 1: Short burst RPM error -> RETRY after auto-sleep
    with mock.patch("pipeline.custom_pipeline.pipeline_control.interruptible_sleep") as mock_sleep:
        action, analysis = handle_quota_exhaustion(
            error_or_text="429 Too Many Requests per 60 seconds",
            package_root=pkg,
        )
        assert action == "RETRY"
        assert analysis.can_auto_wait is True
        mock_sleep.assert_called_once()

    # Case 2: Daily limit with incomplete video -> FALLBACK_BY_ANY_MEANS
    action, analysis = handle_quota_exhaustion(
        error_or_text="429 RESOURCE_EXHAUSTED limit: 0 per day",
        package_root=pkg,
    )
    assert action == "FALLBACK_BY_ANY_MEANS"
    assert analysis.window_type == "daily"

    # Case 3: Daily limit with completed video -> PAUSE_UNTIL_RESET
    vid_dir = pkg / "Video"
    vid_dir.mkdir()
    final_vid = vid_dir / "final_BN.mp4"
    final_vid.write_bytes(b"x" * 60000)  # > 50KB valid video size
    assert is_package_video_completed(pkg) is True

    action, analysis = handle_quota_exhaustion(
        error_or_text="429 RESOURCE_EXHAUSTED limit: 0 per day",
        package_root=pkg,
    )
    assert action == "PAUSE_UNTIL_RESET"
