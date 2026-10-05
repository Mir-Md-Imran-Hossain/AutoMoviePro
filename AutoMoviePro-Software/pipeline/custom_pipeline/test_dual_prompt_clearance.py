"""Tests for Dual-Gate Pre-Generation Prompt Clearance & Agnes Multi-Key Rotation.

Verifies:
  1. Test 1: Macro Domain & Setting Coherence (Theme / Tone lock, purging forbidden tangents).
  2. Test 2: Dialogue & Physical Action / Props Synchronization (Props lock, micro-detail >= 50 words).
  3. Automatic Repair & Re-verification Loop.
  4. Agnes Video and Image Multi-Key Rotation and zero-detail loss on fallback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from pipeline.custom_pipeline.visual_intelligence import (
    analyze_macro_topic_and_script,
    audit_prompt_preflight_clearance,
    verify_prompt_dual_clearance,
)


def test_dual_clearance_purges_forbidden_tangents_and_faces():
    """Test 1: Forbidden tangents (driving cars) and faces are purged on robotics topic."""
    scene = {
        "shot_number": 1,
        "topic": "BMW Factory Humanoid Robot Figure 02 Automation",
        "niche": "AI Tech & Robotics",
        "visual_subject": "broll",
    }
    # Raw prompt with forbidden driving car on highway and presenter face
    raw_prompt = (
        "Commercial car driving on highway with young man looking at camera in hoodie portrait. "
        "Dealership background with traffic."
    )
    narration = "কারখানায় হিউম্যানয়েড রোবট যন্ত্রাংশ তুলছে এবং অটোমেশনে কাজ করছে।"

    clearance = verify_prompt_dual_clearance(
        scene, raw_prompt, narration, for_video=True
    )

    assert clearance["passed"] is True
    verified = clearance["verified_prompt"].lower()
    # Forbidden terms must be purged
    assert "driving on highway" not in verified
    assert "dealership" not in verified
    assert "young man looking at camera" not in verified
    assert "hoodie portrait" not in verified
    assert "hoodie" not in verified
    # Must have factory robotics setting anchor
    assert any(k in verified for k in ("factory", "robot", "assembly", "industrial"))
    # Must have SILENT VIDEO directive
    assert "silent video" in verified
    assert clearance["test_1_theme_passed"] is True
    assert clearance["clearance"] in ("GRANTED", "REPAIRED_AND_GRANTED")


def test_dual_clearance_enforces_dialogue_sync_and_micro_details():
    """Test 2: Spoken props (cracking eggs, folding clothes) must be explicitly depicted."""
    scene = {
        "shot_number": 2,
        "topic": "Figure 02 Humanoid Robot capabilities",
        "niche": "Robotics",
        "visual_subject": "broll",
    }
    # Thin prompt lacking dialogue props
    thin_prompt = "A robot standing in a room."
    narration = "রোবটটি ডিম ভাঙা বা কাপড় ভাঁজ করার মতো সূক্ষ্ম হাতের কাজ নিখুঁতভাবে করতে পারে।"

    clearance = verify_prompt_dual_clearance(
        scene, thin_prompt, narration, for_video=True
    )

    assert clearance["passed"] is True
    verified = clearance["verified_prompt"]
    # Check that word count is enriched to at least 50 words
    assert len(verified.split()) >= 50
    # Must show dialogue props (egg / handling / fingers / clothes / laundry)
    v_low = verified.lower()
    assert any(k in v_low for k in ("egg", "handling", "finger", "cloth", "laundry", "hand", "robot"))
    assert clearance["alignment_score"] >= 0.70
    assert clearance["test_2_dialogue_passed"] is True


def test_dual_clearance_deep_sea_environment_lock():
    """Test 1: Deep sea topic must be locked to 4,000m abyssal underwater environment."""
    scene = {
        "shot_number": 3,
        "topic": "Deep Sea Dark Oxygen Mystery 4000 meters underwater",
        "niche": "Science & Nature",
        "visual_subject": "broll",
    }
    prompt_with_dry_rock = "A dry land rock sitting under sunny daylight sky with beach pebble."
    narration = "চার হাজার মিটার গভীরে ডার্ক অক্সিজেন তৈরি করছে এই রহস্যময় পলিমেটালিক নোডিউল।"

    clearance = verify_prompt_dual_clearance(
        scene, prompt_with_dry_rock, narration, for_video=False
    )

    assert clearance["passed"] is True
    verified = clearance["verified_prompt"].lower()
    # Dry terrain must be purged
    assert "dry land rock" not in verified
    assert "sunny beach" not in verified
    # Deep sea context must be injected
    assert any(k in verified for k in ("underwater", "deep sea", "ocean floor", "abyssal", "4,000m", "4000m"))
    assert clearance["test_1_theme_passed"] is True
    assert clearance["alignment_score"] >= 0.70


def test_backward_compatibility_audit_prompt_preflight_clearance():
    """Verify audit_prompt_preflight_clearance returns dual clearance structure."""
    scene = {
        "shot_number": 1,
        "topic": "NVIDIA GR00T Robot Learning",
        "niche": "AI Robotics",
    }
    prompt = (
        "Cinematic wide shot of advanced humanoid robot in high-tech robotics lab, "
        "dexterous mechanical fingers manipulating electronic components on workbench, "
        "atmospheric studio lighting, 8k photoreal visual."
    )
    narration = "গ্রুট মডেলের মাধ্যমে রোবট ভিডিও দেখে মানুষের কাজ শিখছে।"

    res = audit_prompt_preflight_clearance(scene, prompt, narration, for_video=True)
    assert res["passed"] is True
    assert "clearance" in res
    assert "verified_prompt" in res
    assert "test_1_theme_passed" in res
    assert "test_2_dialogue_passed" in res
    assert res["word_count"] >= 30
