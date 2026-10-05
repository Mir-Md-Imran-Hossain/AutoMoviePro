"""Unit tests for Part 4: Visual Misalignment, Face Overuse & Unrealistic Meta-Screens Fix."""

import pytest
from pathlib import Path
from pipeline.custom_pipeline.visual_subject_policy import (
    SUBJECT_BROLL,
    SUBJECT_PRESENTER,
    is_non_presenter_topic,
    infer_visual_subject,
    strip_face_language,
)
from pipeline.custom_pipeline.visual_render import normalize_render_payload
from pipeline.custom_pipeline.media_generate import _ensure_character_reference
from pipeline.custom_pipeline.av_match_gate import (
    ensure_prompt_av_ready,
    dialogue_visual_alignment_score,
)
from pipeline.custom_pipeline.media_prompts import build_detailed_media_prompt


def test_is_non_presenter_topic_bangla_and_english():
    assert is_non_presenter_topic(topic="হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে!")
    assert is_non_presenter_topic(topic="Humanoid Robots Working in Factories 2026")
    assert is_non_presenter_topic(niche="Science & Technology", topic="মহাকাশের রহস্য")
    assert is_non_presenter_topic(topic="Wild animals of Amazon rainforest")
    assert not is_non_presenter_topic(topic="My Daily Vlog in Dhaka")


def test_infer_visual_subject_forces_broll_on_robot_topic():
    # Even if Grok explicitly set visual_subject: presenter, topic-driven must override to broll
    subj = infer_visual_subject(
        topic="হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে!",
        scene={"visual_subject": "presenter", "source_character_details": "28-year-old male"},
        narration="ডিম ভাঙছে, কাপড় ভাঁজ করছে—রোবট এখন প্রায় মানুষের মতো কাজ করছে!",
    )
    assert subj == SUBJECT_BROLL


def test_normalize_render_payload_clears_presenter_on_robot_topic():
    source = {
        "topic": "হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে!",
        "niche": "Tech & Robotics",
        "script_scenes": [
            {
                "shot_number": 1,
                "shot_duration_seconds": 7,
                "voiceover_script": "ডিম ভাঙছে, কাপড় ভাঁজ করছে—রোবট এখন প্রায় মানুষের মতো কাজ করছে!",
                "visual_subject": "presenter",
                "character_details": "Male, 28 years old, short black hair",
            }
        ]
    }
    raw_payload = {
        "production_metadata": {},
        "render_scenes": [
            {
                "shot_number": 1,
                "render_type": "IMAGE",
                "visual_subject": "presenter",
                "visual_prompt": "Cinematic 28-year-old Bangladeshi male presenter speaking to camera",
            }
        ]
    }
    norm = normalize_render_payload(raw_payload, source, aspect_ratio="9:16")
    sc1 = norm["render_scenes"][0]
    assert sc1["visual_subject"] == SUBJECT_BROLL
    assert sc1["source_character_details"] == "none"
    assert sc1["topic"] == "হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে!"


def test_ensure_character_reference_skips_on_robot_topic(tmp_path):
    class FakePaths:
        image = tmp_path / "Image"
    FakePaths.image.mkdir(parents=True)
    pkg = tmp_path / "006_(হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে!)"
    pkg.mkdir()

    scenes = [
        {
            "shot_number": 1,
            "visual_subject": "presenter",
            "source_character_details": "28-year-old male presenter",
            "topic": "হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে!",
        }
    ]
    ref = _ensure_character_reference(pkg, FakePaths, scenes, aspect="9:16", art="Cinematic")
    assert ref is None


def test_ensure_prompt_av_ready_transforms_stripped_presenter_prompt():
    raw_presenter_prompt = (
        "Cinematic hyper-realistic medium close-up, 28-year-old Bangladeshi male presenter, "
        "short black hair, light stubble, plain dark navy t-shirt, intrigued half-smile addressing camera, "
        "compact night tech studio, dual 27-inch monitors with faint cyan UI glow behind, dark matte desk"
    )
    narration = "ডিম ভাঙছে, কাপড় ভাঁজ করছে—রোবট এখন প্রায় মানুষের মতো কাজ করছে! আসসালামু আলাইকুম।"
    topic = "হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে!"

    res = ensure_prompt_av_ready(
        raw_presenter_prompt,
        narration,
        topic=topic,
    )
    p = res["prompt"].lower()
    # Must NOT have presenter face words
    assert "28-year-old" not in p
    assert "male presenter" not in p
    assert "stubble" not in p
    # Must have concrete robot action from narration
    assert "robot" in p
    assert res["ok"] is True


def test_ensure_prompt_av_ready_transforms_unrealistic_laptop_screens():
    raw_screen_prompt = (
        "Photoreal extreme close-up of a 15-inch laptop screen filling a vertical 9:16 frame in a dark night tech studio, "
        "video player UI playing Tesla Optimus humanoid robot walking and balancing footage, crisp play bar, volume icon, "
        "readable chrome, cool white-blue screen glow on black bezel"
    )
    narration = "ল্যাপটপে সাম্প্রতিক ক্লিপগুলো দেখলে বোঝা যায়—হাঁটা, ভারসাম্য, বাক্স তোলা—সবই শিখছে।"
    topic = "হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে!"

    res = ensure_prompt_av_ready(
        raw_screen_prompt,
        narration,
        topic=topic,
    )
    p = res["prompt"].lower()
    assert "video player ui" not in p
    assert "readable chrome" not in p
    assert "robot" in p
    assert res["ok"] is True
