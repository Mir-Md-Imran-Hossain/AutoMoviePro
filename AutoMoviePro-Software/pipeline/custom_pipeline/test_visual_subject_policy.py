"""Unit tests — product/UI-first visual subject policy (no gratuitous faces)."""

from __future__ import annotations

from pipeline.custom_pipeline.media_prompts import (
    build_detailed_media_prompt,
    prompt_audit,
    stock_search_query,
)
from pipeline.custom_pipeline.prompts import (
    build_topic_research_prompt,
    build_visual_render_prompt,
)
from pipeline.custom_pipeline.visual_subject_policy import (
    SUBJECT_HANDS_UI,
    SUBJECT_PRESENTER,
    SUBJECT_PRODUCT_UI,
    infer_visual_subject,
)


def test_infer_chatgpt_demo_is_product_ui():
    subj = infer_visual_subject(
        narration="Open your laptop. Go into ChatGPT and click Custom Instructions.",
        niche="AI Tech",
        topic="ChatGPT Hidden Hack 2026",
        shot_number=3,
        total_shots=9,
    )
    assert subj == SUBJECT_PRODUCT_UI


def test_infer_paste_save_is_ui_not_face():
    assert (
        infer_visual_subject(
            narration="Copy-paste your three best assignments into that box.",
            niche="ChatGPT",
            topic="writing style clone",
        )
        == SUBJECT_PRODUCT_UI
    )
    assert (
        infer_visual_subject(
            narration="Press the Save button. Ask any question.",
            niche="AI Tech",
            topic="ChatGPT",
        )
        == SUBJECT_PRODUCT_UI
    )


def test_infer_salam_hook_can_be_presenter():
    subj = infer_visual_subject(
        narration="Assalamu Alaikum. Today I will show you this productivity hack.",
        niche="AI Tech",
        topic="ChatGPT",
        shot_number=2,
        total_shots=9,
    )
    assert subj == SUBJECT_PRESENTER


def test_explicit_visual_subject_wins():
    assert (
        infer_visual_subject(
            narration="Click Save now",
            scene={"visual_subject": "presenter"},
        )
        == SUBJECT_PRESENTER
    )
    assert (
        infer_visual_subject(
            narration="Hey everyone listen",
            scene={"visual_subject": "product_ui"},
        )
        == SUBJECT_PRODUCT_UI
    )


def test_media_prompt_ui_shot_has_no_character_lock():
    scene = {
        "shot_number": 3,
        "visual_subject": "product_ui",
        "visual_prompt": "Young man in hoodie looking at camera with laptop",
        "source_character_details": "21yo Bangladeshi male grey hoodie",
        "source_camera_angle": "OTS laptop",
        "source_lighting": "screen glow",
        "source_voiceover_script": "Open ChatGPT and click Custom Instructions.",
        "niche": "AI Tech",
        "topic": "ChatGPT Hidden Hack",
        "total_shots": 9,
    }
    prompt = build_detailed_media_prompt(
        scene, for_video=True, narration_text=scene["source_voiceover_script"]
    )
    low = prompt.lower()
    assert "character lock" not in low
    assert "no human face" in low or "product ui" in low
    assert "custom instructions" in low or "chatgpt" in low
    audit = prompt_audit(scene, prompt)
    assert audit["visual_subject"] == SUBJECT_PRODUCT_UI
    assert audit["has_product_ui_lock"] is True


def test_media_prompt_presenter_keeps_character_lock():
    scene = {
        "shot_number": 1,
        "visual_subject": "presenter",
        "visual_prompt": "Host in tech studio addressing camera",
        "source_character_details": "25yo male black hoodie",
        "source_voiceover_script": "Hey everyone, welcome to today's tip.",
    }
    prompt = build_detailed_media_prompt(
        scene, for_video=False, narration_text=scene["source_voiceover_script"]
    )
    assert "CHARACTER LOCK" in prompt
    assert "25yo male black hoodie" in prompt


def test_stock_query_ui_avoids_young_man():
    scene = {
        "shot_number": 4,
        "visual_subject": "product_ui",
        "source_voiceover_script": "Paste into Custom Instructions then hit Save.",
        "source_character_details": "young man grey hoodie",
        "visual_prompt": "young man typing on laptop",
        "niche": "ChatGPT",
        "topic": "ChatGPT hack",
    }
    q = stock_search_query(scene).lower()
    assert "young" not in q
    assert "man" not in q.split()  # allow 'manual' etc but not bare man from character
    assert "chatgpt" in q or "screen" in q or "settings" in q or "laptop" in q
    assert "cinematic tech studio young man" not in q


def test_topic_prompt_documents_visual_subject_policy():
    p = build_topic_research_prompt(niche="AI Tech", video_type="short", audience="students")
    assert "visual_subject" in p
    assert "product_ui" in p
    assert "presenter" in p
    assert "ফেস ওভারইউজ" in p or "মুখ" in p


def test_visual_render_prompt_ui_first():
    p = build_visual_render_prompt(source_json='{"script_scenes":[]}', aspect_ratio="9:16")
    assert "product_ui" in p
    assert "NO human face" in p or "মুখ" in p


def test_hands_ui_inference():
    subj = infer_visual_subject(
        narration="Type on the keyboard and paste the text into the ChatGPT box.",
        niche="AI Tech",
        topic="ChatGPT",
    )
    assert subj in (SUBJECT_HANDS_UI, SUBJECT_PRODUCT_UI)
