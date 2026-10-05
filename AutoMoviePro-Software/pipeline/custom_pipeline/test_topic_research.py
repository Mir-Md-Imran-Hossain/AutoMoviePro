"""Lightweight tests for custom topic-research helpers (no live Grok call)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.custom_pipeline.prompts import build_topic_research_prompt
from pipeline.custom_pipeline.topic_research import (
    normalize_payload,
    normalize_video_type,
    parse_grok_json,
    pick_primary_title,
    save_topic_package,
)


def test_duration_prompt_short_vs_long():
    short_p = build_topic_research_prompt(
        niche="AI Tech", video_type="short", audience="তরুণ প্রজন্ম"
    )
    long_p = build_topic_research_prompt(
        niche="AI Tech", video_type="long", audience="তরুণ প্রজন্ম"
    )
    assert "Short (40-120 Seconds)" in short_p
    assert "Long (240-300 Seconds)" in long_p
    assert "AI Tech" in short_p


def test_parse_and_pick_title():
    raw = json.dumps(
        {
            "seo_metadata": {
                "selected_topic": "Quantum Tips",
                "suggested_titles": ["Title A", "Title B"],
                "seo_keywords": ["a", "b"],
                "video_type": "Shorts",
                "target_duration_seconds": 999,
            },
            "script_scenes": [{"shot_number": 1, "shot_duration_seconds": 6}],
        }
    )
    data = parse_grok_json(raw)
    assert pick_primary_title(data) == "Title A"
    norm = normalize_payload(data, video_type="short")
    assert 40 <= int(norm["seo_metadata"]["target_duration_seconds"]) <= 120
    assert normalize_video_type("SHORTS") == "short"


def test_merge_locked_visuals_keeps_source_shots():
    from pipeline.custom_pipeline.localization import build_voice_only_payload

    source = {
        "seo_metadata": {
            "selected_topic": "মূল টপিক",
            "suggested_titles": ["বাংলা টাইটেল"],
            "seo_keywords": ["ক"],
            "video_type": "Shorts",
            "target_duration_seconds": 60,
        },
        "script_scenes": [
            {
                "shot_number": 1,
                "shot_duration_seconds": 7,
                "camera_angle": "Wide Shot",
                "lighting": "Neon",
                "character_details": "Male hoodie",
                "visual_prompt": "KEEP THIS VISUAL",
                "voiceover_script": "বাংলা ভয়েস",
                "emotion_tag": "Mysterious",
                "sfx": "Whoosh",
                "bgm_style": "Ambient",
            }
        ],
    }
    localized = {
        "seo_metadata": {
            "selected_topic": "Localized Topic",
            "suggested_titles": ["Eng Title"],
            "seo_keywords": ["kw"],
            "video_type": "CHANGED",
            "target_duration_seconds": 999,
        },
        "voice_scenes": [
            {
                "shot_number": 1,
                "voiceover_script": "English voiceover here",
                "emotion_tag": "Culturally Warm",
                "subtitle_text": "English subtitle",
            }
        ],
    }
    merged = build_voice_only_payload(localized, source, target_language="English")
    assert merged["visuals_shared"] is True
    shot = merged["voice_scenes"][0]
    assert "visual_prompt" not in shot
    assert "camera_angle" not in shot
    assert "character_details" not in shot
    assert "lighting" not in shot
    assert shot["voiceover_script"] == "English voiceover here"
    assert shot["emotion_tag"] == "Culturally Warm"
    assert shot["subtitle_text"] == "English subtitle"
    assert shot["shot_duration_seconds"] == 7
    assert merged["seo_metadata"]["video_type"] == "Shorts"
    assert merged["seo_metadata"]["suggested_titles"] == ["Eng Title"]



def test_save_to_output_folder(tmp_path: Path):
    payload = {
        "seo_metadata": {
            "selected_topic": "Moon Facts",
            "suggested_titles": ["Amazing Moon Secrets"],
            "seo_keywords": ["moon", "space"],
            "video_type": "Shorts",
            "target_duration_seconds": 60,
        },
        "script_scenes": [
            {
                "shot_number": 1,
                "shot_duration_seconds": 6,
                "voiceover_script": "Hello",
            }
        ],
    }
    saved = save_topic_package(payload, video_type="short", output_root=tmp_path)
    assert saved["ok"]
    out = Path(saved["json_path"])
    assert out.is_file()
    assert "Short" in saved["package_root"]
    assert "Amazing_Moon_Secrets" in saved["folder_name"] or "Amazing" in saved["folder_name"]
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["seo_metadata"]["selected_topic"] == "Moon Facts"
