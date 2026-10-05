#!/usr/bin/env python3
"""Prompt engineering contracts: director, critic, Agnes, image, TTS, translate."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.prompt_engineering import (  # noqa: E402
    AGNES_NEGATIVE,
    WORDS_PER_BEAT_MAX,
    agnes_generation_wrapper,
    critic_instruction,
    director_av_sync_rules,
    image_beat_prompt,
    on_screen_text_rule,
    precheck_instruction,
    product_lock_clause,
    revised_visual_prompt,
    sanitize_generation_prompt,
    script_bundle_instruction,
    sku_tokens,
    spoken_word_budget_rules,
    system_for_purpose,
    translate_instruction,
    trending_instruction,
    truncate_keep_lock,
)
from pipeline.prompt_hardening import harden_video_prompt  # noqa: E402
from pipeline.duration_budget import planned_scene_count  # noqa: E402


def test_spoken_budget_never_asks_long_monologues():
    rules = spoken_word_budget_rules(max_seconds=300, video_type="long")
    assert "35" not in rules and "55" not in rules
    assert str(WORDS_PER_BEAT_MAX) in rules
    assert str(planned_scene_count(300, "long")) in rules
    d = director_av_sync_rules(max_seconds=120, video_type="short")
    assert "35–55" not in d and "35-55" not in d
    assert "12" in d and "22" in d
    src = inspect.getsource(__import__("pipeline.niche_director", fromlist=["plan_niche_production"]))
    assert "35–55" not in src and "35-55" not in src


def test_sku_and_product_lock_survive_truncate():
    assert "9a" in sku_tokens("Pixel 9a")
    lock = product_lock_clause("Pixel 9a", ["unboxing"])
    assert "Pixel 9a" in lock and "9a" in lock and "9:16" in lock
    huge = ("cinematic atmospheric foggy forest still photo " * 80) + " filler"
    out = truncate_keep_lock(huge, limit=400, product_name="Pixel 9a", keywords=["unboxing"])
    assert len(out) <= 400
    assert "pixel 9a" in out.lower()
    assert "9a" in out.lower()


def test_display_beat_allows_device_ui():
    disp = on_screen_text_rule("display")
    assert "ON" in disp or "UI" in disp
    assert "blank" in disp.lower() or "black panel" in disp.lower()
    intro = on_screen_text_rule("intro")
    assert "burned" in intro.lower() or "captions" in intro.lower()
    hardened = harden_video_prompt(
        "hero of Pixel 9a",
        narration="The Pixel 9a display stays bright outdoors.",
        keywords=["Pixel 9a", "display"],
        product_name="Pixel 9a",
        element="display",
        niche="Gadget Reviews",
        duration_sec=8,
    )
    assert "UI chrome" not in hardened
    assert "Pixel 9a" in hardened
    assert "ON" in hardened or "UI" in hardened or "burned" in hardened.lower()


def test_revised_prompt_strips_api_junk_and_names_sku():
    dirty = sanitize_generation_prompt(
        "forest mist. Fix prior issues: critic_api_failed:429 avatar. RESOURCE_EXHAUSTED on thi."
    )
    assert "RESOURCE" not in dirty.upper()
    assert "critic_api" not in dirty.lower()
    rev = revised_visual_prompt(
        narration="Today we unbox the Pixel 9a.",
        keywords=["Pixel 9a", "unboxing"],
        exact_ai_video_prompt="cinematic forest",
        product_name="Pixel 9a",
        element="intro",
        issues=["precheck_no_keys", "wrong_subject"],
    )
    assert "precheck_no_keys" not in rev
    assert "Pixel 9a" in rev
    assert "9:16" in rev
    assert "Fix prior issues" not in rev


def test_agnes_wrapper_and_negative():
    p = agnes_generation_wrapper(
        "hero shot",
        product_name="Pixel 9a",
        keywords=["Pixel 9a"],
        narration_hint="The Pixel 9a unboxing starts now.",
        niche_mod="studio rim light",
    )
    assert "9:16" in p
    assert "Charon" in p or "male" in p.lower()
    assert "Pixel 9a" in p
    assert "Kore" in AGNES_NEGATIVE or "female" in AGNES_NEGATIVE


def test_image_beat_has_no_av_timing():
    p = image_beat_prompt(
        art_style="cinematic",
        profile_name="Pixel 9a",
        visual_description="teal phone",
        keywords=["Pixel 9a"],
        anchors=["Pixel", "unboxing"],
        beat_text="The Pixel 9a leaves the box.",
        beat_index=0,
        beat_count=2,
        seed=1,
    )
    low = p.lower()
    assert "setpts" not in low
    assert "finish every spoken" not in low
    assert "pixel 9a" in low
    assert "9:16" in p


def test_critic_and_precheck_name_visual_not_audio():
    pre = precheck_instruction(
        niche="gadget",
        element="intro",
        product_name="Pixel 9a",
        narration="The Pixel 9a unboxing.",
        keywords=["Pixel 9a"],
        exact_ai_video_prompt="cinematic forest",
        trained_txt="- test",
    )
    assert "audio pass" not in pre.lower() or "SKU" in pre
    assert "9:16" in pre
    assert "Pixel 9a" in pre
    cri = critic_instruction(
        niche="gadget",
        element="intro",
        product_name="Pixel 9a",
        narration="The Pixel 9a unboxing.",
        keywords=["Pixel 9a"],
        exact_ai_video_prompt="cinematic forest",
        trained_txt="- test",
        video_dur=8.0,
        audio_dur=8.0,
        pass_score=78,
    )
    assert "visual_anchors_missing" in cri
    assert "NEVER a visual pass" in cri or "not a visual pass" in cri.lower()
    assert "burned" in cri.lower()


def test_translate_keeps_sku_and_script_bundle_scene_count():
    t = translate_instruction(
        text="Today we review the Pixel 9a.",
        src_display="English",
        tgt_display="Bengali",
        domain_hint="documentary narration",
    )
    assert "Pixel" in t
    assert "9a" in t
    tr = trending_instruction(count=3, block_txt="- old phone", year=2026)
    assert "2026" in tr
    assert "2025-2026" not in tr
    sb = script_bundle_instruction(
        channel_name="Test",
        niche="Gadget",
        focus="Pixel 9a",
        research_notes="",
        video_type="short",
        max_sec=120,
        video_special="",
        generation_special="",
        title_desc_special="",
        example_script="",
    )
    n = planned_scene_count(120, "short")
    assert str(n) in sb
    assert "4-5" not in sb
    sys_s = system_for_purpose("script", json_mode=True)
    assert "helpful assistant" not in sys_s.lower()
    assert "JSON" in sys_s


def test_llm_router_not_generic_assistant():
    src = inspect.getsource(__import__("pipeline.llm_router", fromlist=["openai_compatible_chat"]))
    assert "You are a helpful assistant" not in src
    from pipeline.ai_providers import generate_script_bundle

    gsrc = inspect.getsource(generate_script_bundle)
    assert "4-5" not in gsrc
    assert "script_bundle_instruction" in gsrc


def main() -> int:
    test_spoken_budget_never_asks_long_monologues()
    test_sku_and_product_lock_survive_truncate()
    test_display_beat_allows_device_ui()
    test_revised_prompt_strips_api_junk_and_names_sku()
    test_agnes_wrapper_and_negative()
    test_image_beat_has_no_av_timing()
    test_critic_and_precheck_name_visual_not_audio()
    test_translate_keeps_sku_and_script_bundle_scene_count()
    test_llm_router_not_generic_assistant()
    print("OK prompt engineering contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
