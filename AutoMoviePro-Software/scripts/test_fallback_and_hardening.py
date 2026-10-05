"""Unit tests for prompt hardening + fallback beat split (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.fallback_image_video import _split_beats, character_base_seed  # noqa: E402
from pipeline.prompt_hardening import harden_video_prompt  # noqa: E402
from pipeline.quota_backoff import cool_down_seconds, is_quota_error  # noqa: E402


def test_harden_includes_finish_rule():
    p = harden_video_prompt(
        "Chernobyl reactor night",
        narration="The control rods failed to drop in time.",
        keywords=["reactor", "control rods"],
        product_name="Chernobyl Disaster",
        element="reveal",
        duration_sec=8.0,
        prior_issues=["dialogue_cutoff"],
    )
    assert "Finish EVERY spoken word" in p
    assert "CRITICAL FIX" in p
    assert "reactor" in p.lower() or "control rods" in p.lower()


def test_split_beats_sum_duration():
    beats = _split_beats(
        "One. Two. Three. Four. Five. Six. Seven. Eight.",
        14.0,
    )
    assert len(beats) >= 2
    total = sum(d for _, d in beats)
    assert abs(total - 14.0) < 0.05


def test_quota_ladder():
    assert cool_down_seconds(1) == 30 * 60
    assert cool_down_seconds(2) == 60 * 60
    assert cool_down_seconds(4) == 3 * 60 * 60
    assert is_quota_error("429 RESOURCE_EXHAUSTED")
    assert not is_quota_error("file not found")


def test_seed_stable():
    a = character_base_seed("Pripyat", "empty ferris wheel fog")
    b = character_base_seed("Pripyat", "empty ferris wheel fog")
    assert a == b


if __name__ == "__main__":
    test_harden_includes_finish_rule()
    test_split_beats_sum_duration()
    test_quota_ladder()
    test_seed_stable()
    print("OK")
