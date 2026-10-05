"""Regenerate Output/_prompt_samples with full documentary prompts."""
from __future__ import annotations

from pathlib import Path

from pipeline.custom_pipeline.media_prompts import build_detailed_media_prompt
from pipeline.custom_pipeline.prompts import (
    SYSTEM_JSON_ONLY,
    SYSTEM_LOCALIZE_JSON,
    SYSTEM_VISUAL_RENDER_JSON,
    build_localization_prompt,
    build_topic_research_prompt,
    build_visual_render_prompt,
)
from pipeline.custom_pipeline.tts_client import build_locked_speak_prompt

out = Path("Output/_prompt_samples")
out.mkdir(parents=True, exist_ok=True)

parts: list[str] = [
    "# সম্পূর্ণ প্রম্পট (কোড থেকে জেনারেট — বিস্তারিত ফরম্যাট)\n",
    "সোর্স: `pipeline/custom_pipeline/prompts.py` + `media_prompts.py` + `tts_client.py`\n",
]

topic = build_topic_research_prompt(
    niche="[এখানে আপনার চ্যানেলের নিস লিখুন]",
    video_type="short",
    audience="[যেমন: তরুণ প্রজন্ম / সাধারণ দর্শক]",
)
(out / "01_topic_SYSTEM.txt").write_text(SYSTEM_JSON_ONLY, encoding="utf-8")
(out / "01_topic_USER.txt").write_text(topic, encoding="utf-8")
parts += [
    "\n---\n\n## SYSTEM — Topic\n\n```\n",
    SYSTEM_JSON_ONLY,
    "\n```\n\n## ১. Topic USER (পূর্ণ)\n\n```\n",
    topic,
    "\n```\n",
]

voice_json = """{
  "seo_metadata": {
    "selected_topic": "উদাহরণ টপিক",
    "suggested_titles": ["টাইটেল ১"],
    "seo_keywords": ["kw"],
    "video_type": "Shorts",
    "target_duration_seconds": 60
  },
  "voice_scenes": [
    {
      "shot_number": 1,
      "shot_duration_seconds": 6,
      "voiceover_script": "স্টুডেন্টরা শোনো — ChatGPT হ্যাকটা জানো?",
      "emotion_tag": "Engaging"
    }
  ]
}"""
loc = build_localization_prompt(
    target_language="English",
    audience_culture="Global English Reader",
    source_json=voice_json,
)
(out / "02_localize_SYSTEM.txt").write_text(SYSTEM_LOCALIZE_JSON, encoding="utf-8")
(out / "02_localize_USER.txt").write_text(loc, encoding="utf-8")
parts += [
    "\n---\n\n## SYSTEM — Localize\n\n```\n",
    SYSTEM_LOCALIZE_JSON,
    "\n```\n\n## ২. Localize USER (পূর্ণ)\n\n```\n",
    loc,
    "\n```\n",
]

script_json = """{
  "seo_metadata": {"selected_topic": "ChatGPT Hack", "video_type": "Shorts"},
  "script_scenes": [
    {
      "shot_number": 1,
      "shot_duration_seconds": 6,
      "visual_subject": "presenter",
      "voiceover_script": "স্টুডেন্টরা শোনো!",
      "visual_prompt": "Host in tech studio",
      "character_details": "Male 21 grey hoodie"
    },
    {
      "shot_number": 2,
      "shot_duration_seconds": 7,
      "visual_subject": "product_ui",
      "voiceover_script": "Custom Instructions-এ ক্লিক করো",
      "visual_prompt": "ChatGPT settings panel",
      "character_details": "none"
    }
  ]
}"""
vis = build_visual_render_prompt(
    source_json=script_json, aspect_ratio="9:16", art_style="Cinematic Hyper-realistic"
)
(out / "03_visual_SYSTEM.txt").write_text(SYSTEM_VISUAL_RENDER_JSON, encoding="utf-8")
(out / "03_visual_USER.txt").write_text(vis, encoding="utf-8")
parts += [
    "\n---\n\n## SYSTEM — Visual\n\n```\n",
    SYSTEM_VISUAL_RENDER_JSON,
    "\n```\n\n## ৩. Visual USER (পূর্ণ)\n\n```\n",
    vis,
    "\n```\n",
]

media_ui = build_detailed_media_prompt(
    {
        "shot_number": 3,
        "visual_subject": "product_ui",
        "visual_prompt": "Photoreal ChatGPT Custom Instructions panel, Save button, no face",
        "source_camera_angle": "Extreme close-up laptop screen",
        "source_lighting": "Cool ChatGPT screen glow",
        "source_character_details": "Young male grey hoodie",
        "niche": "AI Tech",
        "topic": "ChatGPT",
        "total_shots": 9,
        "shot_duration_seconds": 7,
        "motion_directives": {
            "camera_movement": "slow push into UI",
            "character_action": "cursor clicks",
        },
    },
    for_video=True,
    narration_text="Open ChatGPT and click Custom Instructions.",
)
(out / "04_media_PRODUCT_UI.txt").write_text(media_ui, encoding="utf-8")
parts += ["\n---\n\n## ৪. Media PRODUCT_UI VIDEO\n\n```\n", media_ui, "\n```\n"]

tts = build_locked_speak_prompt(
    "Open your laptop and click Custom Instructions.",
    language_code="en",
    emotion_tag="Clear & Instructive",
    continuous=False,
    target_duration_sec=7,
)
(out / "05_tts_SPEAK.txt").write_text(tts, encoding="utf-8")
parts += ["\n---\n\n## ৫. TTS Speak\n\n```\n", tts, "\n```\n"]

(out / "COMPLETE_PROMPTS_AS_YOU_WROTE.md").write_text("".join(parts), encoding="utf-8")
print(
    "OK",
    f"topic={len(topic)}",
    f"loc={len(loc)}",
    f"vis={len(vis)}",
    f"media={len(media_ui)}",
    f"tts={len(tts)}",
)
