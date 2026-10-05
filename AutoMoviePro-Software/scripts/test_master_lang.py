"""Feature 1 tests: English-master lock (no network required)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.av_sync_critic import _critic_instruction, precheck_generation_prompt  # noqa: E402
from pipeline.master_lang import (  # noqa: E402
    DIRECTOR_MASTER_LANGUAGE_RULES,
    assert_plan_english,
    lock_english_master_plan,
    looks_like_english_master,
    master_lang_issues,
    rewrite_master_language_instructions,
)
from pipeline.niche_agent import FAMILY_CHANNEL_DEFAULTS  # noqa: E402
from pipeline.niche_director import DIRECTOR_SYSTEM, _fallback_plan, _primary_feature_line  # noqa: E402
from pipeline.ai_providers import _fallback_bundle  # noqa: E402


def _has_bengali(text: str) -> bool:
    return any("\u0980" <= ch <= "\u09FF" for ch in (text or ""))


def test_detector_english_vs_bangla():
    assert looks_like_english_master("Today we review the Pixel 9a in one tight look.")
    assert not looks_like_english_master("আজকের রিভিউতে আছে Pixel 9a — এক নজরে জেনে নিন।")
    issues = master_lang_issues("আজকের রিভিউতে আছে Pixel 9a", field="narration")
    assert any("bn" in i for i in issues)


def test_director_system_is_english_master():
    assert "natural English" in DIRECTOR_SYSTEM
    assert "Bangla/Hindi" in DIRECTOR_SYSTEM or "Do NOT write Bangla" in DIRECTOR_SYSTEM
    assert "Spoken language: natural Bangla" not in DIRECTOR_SYSTEM
    assert "English picture+audio MASTER" in DIRECTOR_MASTER_LANGUAGE_RULES


def test_fallback_plan_has_no_bengali():
    for vt in ("short", "long"):
        plan = _fallback_plan("Gadget Reviews", "Pixel 9a", vt, 120 if vt == "short" else 300, "Test Channel")
        locked = lock_english_master_plan(plan)
        assert locked.get("master_lang") == "en"
        assert not _has_bengali(locked.get("title") or "")
        for scene in locked["scenes"]:
            narr = scene["narration"]
            assert looks_like_english_master(narr), narr
            assert not _has_bengali(narr), narr
        left = [i for i in assert_plan_english(locked) if "title" not in i]
        assert not left, left


def test_lock_repairs_old_bangla_plan_without_api():
    dirty = {
        "topic": "Chernobyl",
        "title": "চেরনোবিল দুর্ঘটনা",
        "description": "",
        "scenes": [
            {"element": "hook", "narration": "এপ্রিলের ২৬ তারিখ, ১৯৮৬। ইউক্রেনের একটি ছোট শহর প্রিপিয়াত।"}
        ],
    }
    locked = lock_english_master_plan(dirty)
    assert looks_like_english_master(locked["scenes"][0]["narration"])
    assert not _has_bengali(locked["scenes"][0]["narration"])
    assert locked["master_lang_repairs"]


def test_channel_specials_rewritten():
    out = rewrite_master_language_instructions("Documentary Bangla narration; one concrete beat.")
    assert "Bangla narration" not in out
    assert "English" in out


def test_niche_agent_defaults_not_bangla_master():
    for fam, vals in FAMILY_CHANNEL_DEFAULTS.items():
        vs = vals.get("video_special") or ""
        assert "Bangla narration" not in vs, fam
        # localization mention is OK; instructing Bangla as spoken master is not
        if "Bangla" in vs:
            assert "localization" in vs.lower() or "later" in vs.lower(), fam


def test_primary_feature_line_english():
    line = _primary_feature_line("Sony WF-1000XM5")
    assert looks_like_english_master(line)
    assert not _has_bengali(line)


def test_script_bundle_fallback_english():
    bundle = _fallback_bundle("Pixel 9a", "short", 120)
    assert looks_like_english_master(bundle["title"])
    for s in bundle["scenes"]:
        assert looks_like_english_master(s["narration"])
        assert not _has_bengali(s["narration"])


def test_critic_prompt_says_english_master():
    instr = _critic_instruction(
        narration_bn="The reactor exploded at 1:23.",
        keywords=["reactor"],
        exact_ai_video_prompt="cinematic reactor night",
        niche="history",
        element="reveal",
        product_name="Chernobyl",
        video_dur=8.0,
        audio_dur=8.0,
    )
    assert "Spoken English master narration" in instr
    assert "Spoken Bangla narration" not in instr
    pre = precheck_generation_prompt(
        narration_bn="The reactor exploded at 1:23.",
        exact_ai_video_prompt="cinematic reactor",
        keyword_triggers=["reactor"],
        niche="history",
        element="reveal",
        product_name="Chernobyl",
        google_api_keys=[],
    )
    # no keys → heuristic precheck, prompt text is in instruction only when keys exist
    assert isinstance(pre, dict)


if __name__ == "__main__":
    test_detector_english_vs_bangla()
    test_director_system_is_english_master()
    test_fallback_plan_has_no_bengali()
    test_lock_repairs_old_bangla_plan_without_api()
    test_channel_specials_rewritten()
    test_niche_agent_defaults_not_bangla_master()
    test_primary_feature_line_english()
    test_script_bundle_fallback_english()
    test_critic_prompt_says_english_master()
    print("OK feature1 english master")
