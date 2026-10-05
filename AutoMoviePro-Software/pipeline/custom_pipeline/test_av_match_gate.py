"""Tests for AV match gate + thrifty vision policy + Bangla cues."""

from __future__ import annotations

from pathlib import Path

from pipeline.custom_pipeline.av_match_gate import (
    dialogue_visual_alignment_score,
    ensure_prompt_av_ready,
    evaluate_generated_asset,
    extract_must_show,
    max_local_regen,
    merge_gate_with_vision,
    stock_forbidden_for_shot,
    strengthen_prompt_with_must_show,
)
from pipeline.custom_pipeline.av_vision_critic import (
    reset_vision_budget_for_tests,
    should_run_vision,
    vision_critic_mode,
)
from pipeline.custom_pipeline.media_prompts import narration_to_visual_cues
from pipeline.custom_pipeline.pipeline_learning import (
    LESSON_BRAND_UI_NO_STOCK,
    active_lessons,
    record_lesson,
    seed_known_lessons_from_live004,
)


def test_product_ui_must_show_chatgpt_settings():
    must = extract_must_show(
        "Open ChatGPT and click Custom Instructions then press Save.",
        visual_subject="product_ui",
        niche="AI Tech",
        topic="ChatGPT hack",
    )
    blob = " ".join(must).lower()
    assert "chatgpt" in blob
    assert "custom instructions" in blob or "save" in blob
    assert stock_forbidden_for_shot(
        visual_subject="product_ui",
        narration="Open ChatGPT Custom Instructions",
        niche="AI Tech",
    )


def test_bangla_narration_must_show():
    must = extract_must_show(
        "চ্যাটজিপিটিতে কাস্টম ইন্সট্রাকশন খুলে সেভ চাপুন",
        visual_subject="product_ui",
        niche="AI",
        topic="hack",
    )
    blob = " ".join(must).lower()
    assert "chatgpt" in blob or "custom" in blob or "save" in blob
    cues = narration_to_visual_cues(
        "কাস্টম ইন্সট্রাকশন সেভ করুন", prefer_ui=True, max_cues=6
    )
    assert "Custom" in cues or "Save" in cues or "ChatGPT" in cues


def test_av_gate_rejects_pexels_for_brand_ui():
    gate = evaluate_generated_asset(
        provider="pexels_stock",
        fallback=True,
        prompt="random laptop",
        stock_query="box first describe you student",
        narration="Click Custom Instructions in ChatGPT",
        visual_subject="product_ui",
        niche="ChatGPT",
        topic="hack",
    )
    assert gate["ok"] is False
    assert gate["action"] == "regenerate_ai"
    assert gate.get("needs_vision") is False  # hard forbid — no vision burn


def test_ensure_prompt_av_ready_zero_api():
    pre = ensure_prompt_av_ready(
        "a desk with a lamp",
        "Open ChatGPT Custom Instructions and click Save",
        visual_subject="product_ui",
        niche="AI",
        topic="t",
    )
    assert "MUST DEPICT EXACTLY" in pre["prompt"]
    assert "ChatGPT" in pre["prompt"]
    assert pre["must_show"]


def test_alignment_score_penalizes_mismatch():
    good = dialogue_visual_alignment_score(
        "Click Custom Instructions in ChatGPT",
        "ChatGPT Custom Instructions settings panel on laptop screen",
        must_show=["ChatGPT Custom Instructions settings panel"],
    )
    bad = dialogue_visual_alignment_score(
        "Click Custom Instructions in ChatGPT",
        "random beach sunset portrait",
        must_show=["ChatGPT Custom Instructions settings panel"],
    )
    assert good["score"] > bad["score"]


def test_strengthen_prompt_prepends_must():
    p = strengthen_prompt_with_must_show(
        "a desk",
        ["ChatGPT Custom Instructions settings panel", "NO human face"],
    )
    assert p.startswith("MUST DEPICT EXACTLY")
    assert "ChatGPT" in p


def test_vision_thrift_skips_when_heuristic_ok(monkeypatch):
    reset_vision_budget_for_tests()
    monkeypatch.setenv("AMP_AV_VISION_CRITIC", "auto")
    assert vision_critic_mode() == "auto"
    assert (
        should_run_vision(
            heuristic_ok=True,
            visual_subject="product_ui",
            provider="google",
            fallback=False,
            package_id="pkg",
            shot_key="S01",
        )
        is False
    )
    assert (
        should_run_vision(
            heuristic_ok=False,
            visual_subject="product_ui",
            provider="google",
            package_id="pkg",
            shot_key="S02",
        )
        is True
    )


def test_vision_off(monkeypatch):
    reset_vision_budget_for_tests()
    monkeypatch.setenv("AMP_AV_VISION_CRITIC", "off")
    assert (
        should_run_vision(
            heuristic_ok=False,
            visual_subject="product_ui",
            package_id="p",
            shot_key="s",
        )
        is False
    )


def test_merge_vision_cannot_rescue_stock_forbid():
    gate = evaluate_generated_asset(
        provider="pexels_stock",
        fallback=True,
        prompt="x",
        stock_query="y",
        narration="ChatGPT Custom Instructions",
        visual_subject="product_ui",
    )
    merged = merge_gate_with_vision(
        gate,
        {"ok": True, "api_used": True, "skipped": False, "reason": "looks fine"},
    )
    assert merged["ok"] is False  # stock forbid stays


def test_max_regen_capped(monkeypatch):
    monkeypatch.setenv("AMP_AV_MAX_REGEN", "9")
    assert max_local_regen() <= 2


def test_learning_inbox(tmp_path: Path, monkeypatch):
    out = tmp_path / "Output"
    out.mkdir()
    monkeypatch.chdir(tmp_path)
    seed_known_lessons_from_live004(out)
    lessons = active_lessons(out)
    kinds = {i["kind"] for i in lessons}
    assert LESSON_BRAND_UI_NO_STOCK in kinds
    inbox = list((out / "_admin_learning" / "inbox").glob("*.json"))
    assert len(inbox) >= 1
    seed_known_lessons_from_live004(out)
    record_lesson(
        kind="test_kind",
        title="t",
        detail="d",
        fix="f",
        output_root=out,
    )
    assert (out / "_admin_learning" / "lessons.json").is_file()


def test_bangla_robotics_must_show():
    must = extract_must_show(
        "হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে! ডিম ভাঙা থেকে কাপড় ভাঁজ পর্যন্ত।",
        visual_subject="broll",
        niche="Technology",
        topic="হিউম্যানয়েড রোবট",
    )
    blob = " ".join(must).lower()
    assert "humanoid robot" in blob or "robot" in blob
    assert "egg" in blob
    assert "cloth" in blob or "laundry" in blob
    assert "no human presenter face" in blob


def test_av_gate_rejects_presenter_face_in_robot_video():
    gate = evaluate_generated_asset(
        provider="pollinations",
        fallback=False,
        prompt="Ultra-detailed photoreal cinematic medium close-up of the same 28-year-old Bangladeshi male presenter in a compact night tech studio",
        narration="হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে!",
        visual_subject="broll",
        niche="Technology",
        topic="হিউম্যানয়েড রোবট",
    )
    assert gate["ok"] is False
    assert gate["action"] == "rewrite_prompt_and_regenerate"
    assert "unwanted_presenter_face_in_non_presenter_shot" in gate["reasons"]


def test_av_gate_rejects_unrealistic_news_text_prompt():
    gate = evaluate_generated_asset(
        provider="flux",
        fallback=False,
        prompt="tech news article UI in mixed Bengali-English about humanoid robot factory trials on laptop screen",
        narration="কারখানায় রোবট সফলভাবে পরীক্ষা সম্পন্ন করেছে।",
        visual_subject="broll",
        niche="Technology",
        topic="হিউম্যানয়েড রোবট",
    )
    assert gate["ok"] is False
    assert gate["action"] == "rewrite_prompt_and_regenerate"
    assert "unrealistic_text_in_prompt" in gate["reasons"]


def test_ensure_prompt_av_ready_cleans_presenter_face_and_text():
    pre = ensure_prompt_av_ready(
        prompt="cinematic medium close-up of 28-year-old male presenter looking at camera with tech news article UI in mixed Bengali-English",
        narration="হিউম্যানয়েড রোবট কারখানায় কাজ করছে এবং স্ক্রু টাইট করছে।",
        visual_subject="broll",
        niche="Technology",
        topic="হিউম্যানয়েড রোবট",
    )
    p = pre["prompt"].lower()
    assert "28-year-old" not in p
    assert "male presenter" not in p
    assert "mixed bengali-english" not in p
    assert "robot" in p
    assert pre["ok"] is True

