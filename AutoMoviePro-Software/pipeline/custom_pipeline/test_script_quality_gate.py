"""Unit tests for ScriptQualityGate, quality evaluation, and Shot 1 audio lead-in."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from pipeline.custom_pipeline.media_compose import _phrase_cues
from pipeline.custom_pipeline.script_quality_gate import (
    count_bengali_words,
    evaluate_hook_quality,
    evaluate_human_tone_and_flow,
    evaluate_information_density,
    evaluate_script_quality,
    evaluate_structure_and_outro,
)
from pipeline.custom_pipeline.topic_research import run_topic_research, save_topic_package


def test_bengali_word_count_accurate():
    text = "ডিম ভাঙছে, কাপড় ভাঁজ করছে—রোবট এখন প্রায় মানুষের মতো কাজ করছে! আসসালামু আলাইকুম।"
    count = count_bengali_words(text)
    assert count == 14
    assert count_bengali_words("") == 0
    assert count_bengali_words("   ") == 0


def test_package_006_weak_script_rejected():
    """Verify that yesterday's weak test video script (Package 006) is strictly rejected."""
    pkg_006_path = Path("Output/Short/006_(হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে!)/File/topic_script.json")
    if pkg_006_path.is_file():
        script_data = json.loads(pkg_006_path.read_text(encoding="utf-8"))
    else:
        # Fallback representation of Package 006
        script_data = {
            "seo_metadata": {
                "selected_topic": "হিউম্যানয়েড রোবট এখন মানুষের মতো কাজ করছে!",
                "target_duration_seconds": 70,
                "video_type": "Shorts",
            },
            "script_scenes": [
                {"shot_number": 1, "shot_duration_seconds": 6, "voiceover_script": "ডিম ভাঙছে, কাপড় ভাঁজ করছে—রোবট এখন প্রায় মানুষের মতো কাজ করছে! আসসালামু আলাইকুম।"},
                {"shot_number": 2, "shot_duration_seconds": 6, "voiceover_script": "আজকে আমরা দেখব কীভাবে নতুন প্রজন্মের হিউম্যানয়েড রোবট আমাদের দৈনন্দিন জীবনের রূপ বদলে দিচ্ছে।"},
                {"shot_number": 3, "shot_duration_seconds": 6, "voiceover_script": "একসময় ভাবা হতো রোবট শুধু কারখানায় ভারী লোহালক্কড় নাড়াচাড়া করার জিনিস।"},
                {"shot_number": 4, "shot_duration_seconds": 6, "voiceover_script": "কিন্তু কৃত্রিম বুদ্ধিমত্তা আর অ্যাডভান্সড সেন্সরের মেলবন্ধনে এরা এখন সূক্ষ্ম কাজও অনায়াসে শিখে নিচ্ছে।"},
                {"shot_number": 5, "shot_duration_seconds": 6, "voiceover_script": "ডিম ফাটানো বা কফি ঢালার মতো ডেলিকেট কাজ এরা মানুষের স্পর্শের অনুভূতি দিয়ে নিখুঁতভাবে করে।"},
                {"shot_number": 6, "shot_duration_seconds": 6, "voiceover_script": "শিল্প কারখানা থেকে শুরু করে বাসাবাড়ি—সব জায়গায় হয়তো এদের দেখা মিলবে খুব শিগগিরই।"},
                {"shot_number": 7, "shot_duration_seconds": 6, "voiceover_script": "তবে প্রশ্ন থেকে যায়, এরা কি মানুষের কাজের জায়গা দখল করে বেকারত্ব বাড়াবে?"},
                {"shot_number": 8, "shot_duration_seconds": 6, "voiceover_script": "নাকি কঠিন ও বিপজ্জনক কাজগুলো কাঁধে নিয়ে আমাদের জীবনকে করবে আরও সহজ আর নিরাপদ?"},
                {"shot_number": 9, "shot_duration_seconds": 6, "voiceover_script": "প্রযুক্তির এই বিপ্লব কোন পথে নিয়ে যাবে আমাদের? আপনার মতামত নিচে কমেন্ট করে জানান।"},
                {"shot_number": 10, "shot_duration_seconds": 6, "voiceover_script": "ভিডিওটি ভালো লাগলে লাইক ও সাবস্ক্রাইব করে বেল আইকনটি বাজিয়ে রাখুন। আল্লাহ হাফেজ।"},
            ],
        }

    report = evaluate_script_quality(script_data, video_type="short")
    assert report["ok"] is False, f"Package 006 script should be rejected! Report: {report}"
    assert report["score"] < 0.70
    assert len(report["issues"]) >= 2
    # Confirms weak hook / misplaced greeting was caught
    assert any("হুক" in issue or "সালাম" in issue for issue in report["issues"])
    # Confirms rewrite feedback generated
    assert len(report["rewrite_feedback"]) > 50


def test_rich_script_passes_gate():
    """Verify that a high-density, engaging, properly structured script passes the gate."""
    rich_script = {
        "seo_metadata": {
            "selected_topic": "হিউম্যানয়েড রোবট: ভবিষ্যৎ বনাম বাস্তবতা",
            "target_duration_seconds": 65,
            "video_type": "Shorts",
        },
        "script_scenes": [
            {
                "shot_number": 1,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "আসসালামু আলাইকুম! আপনি কি জানেন, মাত্র ৩ সেকেন্ডে টেসলার অপটিমাস রোবট মানুষের মতো চা বানিয়ে জামাকাপড় ভাঁজ করতে পারে?",
            },
            {
                "shot_number": 2,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "একসময় ভাবা হতো রোবট শুধু গাড়ির কারখানায় ভারী কাজ করবে, কিন্তু ২০২৬ সালের এই নতুন প্রযুক্তি বিশ্বকে পুরোপুরি স্তব্ধ করে দিয়েছে।",
            },
            {
                "shot_number": 3,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "বোস্টন ডায়নামিক্স এবং টেসলা তাদের রোবটে এমন ট্যাকটাইল সেন্সর যুক্ত করেছে, যা দিয়ে ১ মিলিমিটার সূক্ষ্ম কাঁচের গ্লাসও ভাঙবে না।",
            },
            {
                "shot_number": 4,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "বর্তমানে বিশ্বজুড়ে ১০০ বিলিয়ন ডলারের এই রোবোটিক্স বাজারে চীন এবং আমেরিকা এখন একে অপরকে টেক্কা দিতে মরিয়া।",
            },
            {
                "shot_number": 5,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "তবে সবচেয়ে রোমাঞ্চকর বিষয় হলো, এই রোবটগুলো এখন মানুষের সাহায্য ছাড়াই নিজস্ব এআই ব্রেন দিয়ে নতুন কাজ শিখে নিচ্ছে।",
            },
            {
                "shot_number": 6,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "বিশেষজ্ঞদের গবেষণা বলছে, ২০৩০ সালের মধ্যে প্রায় ৬০ শতাংশ ফ্যাক্টরি ও ঘরের কাজ মানুষের বদলে এই রোবটরাই সামলাবে।",
            },
            {
                "shot_number": 7,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "একটু ভেবে দেখুন, যেখানে আগে ১০ জন কর্মীর সারা দিন লাগত, সেখানে একটি রোবট মাত্র ২ ঘণ্টায় নির্ভুলভাবে সব কাজ শেষ করছে।",
            },
            {
                "shot_number": 8,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "এখন মূল প্রশ্ন হলো—রোবটের এই যুগান্তকারী বিপ্লব কি মানুষের চাকরির সুযোগ কেড়ে নেবে, নাকি আমাদের জীবনকে আরও স্বাধীন ও সহজ করবে?",
            },
            {
                "shot_number": 9,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "আপনার মূল্যবান মতামত অবশ্যই নিচে কমেন্টে জানান—আপনি কি আপনার বাসায় এমন রোবট সহকারী রাখবেন?",
            },
            {
                "shot_number": 10,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "এমন আরও চোখ জুড়ানো টেকনোলজি আপডেটের জন্য ভিডিওটি লাইক করে এখনি সাবস্ক্রাইব করুন। আল্লাহ হাফেজ।",
            },
        ],
    }

    report = evaluate_script_quality(rich_script, video_type="short")
    assert report["ok"] is True, f"Rich script must pass! Issues: {report.get('issues')}"
    assert report["score"] >= 0.85
    assert len(report["issues"]) == 0
    assert report["breakdown"]["hook_score"] >= 0.80
    assert report["breakdown"]["density_score"] >= 0.80
    assert report["breakdown"]["human_tone_score"] >= 0.80
    assert report["breakdown"]["structure_score"] >= 0.85


def test_evaluate_hook_placement_rules():
    # Misplaced salam at end of hook
    bad_hook = evaluate_hook_quality("ডিম ভাঙছে রোবট। আসসালামু আলাইকুম।")
    assert bad_hook["score"] < 0.60
    assert any("সালাম" in iss for iss in bad_hook["issues"])

    # Weak generic hook
    weak_hook = evaluate_hook_quality("আজকে আমরা কথা বলব রোবট নিয়ে।")
    assert weak_hook["score"] < 0.50
    assert any("গতানুগতিক" in iss for iss in weak_hook["issues"])

    # High quality punchy hook
    good_hook = evaluate_hook_quality(
        "আসসালামু আলাইকুম! আপনি কি জানেন, মাত্র ৩ সেকেন্ডে টেসলার নতুন রোবট কীভাবে মানুষের চোখ কপালে তুলে দিল?"
    )
    assert good_hook["score"] >= 0.85
    assert len(good_hook["issues"]) == 0


def test_information_density_catches_thin_shots():
    # Script with only 5 words per shot
    thin_shots = [
        {"shot_number": i, "shot_duration_seconds": 6, "voiceover_script": "রোবট কাজ করছে ভালো।"}
        for i in range(1, 11)
    ]
    report = evaluate_information_density(thin_shots, "short")
    assert report["score"] < 0.50
    assert report["total_words"] < 60
    assert len(report["thin_shots"]) == 10
    assert any("শব্দ সংখ্যা অত্যন্ত কম" in iss for iss in report["issues"])


def test_phrase_cues_with_lead_in():
    text = "আসসালামু আলাইকুম! রোবট বিপ্লব শুরু হয়েছে।"
    # Without lead-in
    cues_0 = _phrase_cues(text, 6.0, lead_in=0.0)
    assert len(cues_0) >= 1
    assert cues_0[0]["start"] == 0.0

    # With 250ms lead-in
    cues_lead = _phrase_cues(text, 6.0, lead_in=0.25)
    assert len(cues_lead) >= 1
    assert cues_lead[0]["start"] == 0.25
    assert cues_lead[-1]["end"] <= 6.25


def test_run_topic_research_quality_gate_retry(tmp_path: Path):
    """Test that run_topic_research retries when script quality gate fails, and saves manifest."""
    weak_payload = {
        "seo_metadata": {
            "selected_topic": "রোবটের গল্প",
            "suggested_titles": ["রোবট নিয়ে কিছু কথা"],
            "seo_keywords": ["robot"],
            "video_type": "Shorts",
            "target_duration_seconds": 60,
        },
        "script_scenes": [
            {"shot_number": 1, "shot_duration_seconds": 6, "voiceover_script": "আজকে আমরা রোবট দেখব।"},
            {"shot_number": 2, "shot_duration_seconds": 6, "voiceover_script": "রোবট কাজ করে।"},
        ],
    }

    rich_payload = {
        "seo_metadata": {
            "selected_topic": "২০২৬ সালে রোবট প্রযুক্তির অবিশ্বাস্য অগ্রগতি",
            "suggested_titles": ["হিউম্যানয়েড রোবট: ভবিষ্যৎ বনাম বাস্তবতা"],
            "seo_keywords": ["রোবট", "টেসলা অপটিমাস", "বোস্টন ডায়নামিক্স"],
            "video_type": "Shorts",
            "target_duration_seconds": 65,
        },
        "script_scenes": [
            {
                "shot_number": 1,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "আসসালামু আলাইকুম! আপনি কি জানেন, মাত্র ৩ সেকেন্ডে টেসলার অপটিমাস রোবট মানুষের মতো চা বানিয়ে জামাকাপড় ভাঁজ করতে পারে?",
            },
            {
                "shot_number": 2,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "একসময় ভাবা হতো রোবট শুধু কারখানায় ভারী কাজ করবে, কিন্তু ২০২৬ সালের এই নতুন প্রযুক্তি বিশ্বকে পুরোপুরি স্তব্ধ করে দিয়েছে।",
            },
            {
                "shot_number": 3,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "বোস্টন ডায়নামিক্স এবং টেসলা তাদের রোবটে এমন ট্যাকটাইল সেন্সর যুক্ত করেছে, যা দিয়ে ১ মিলিমিটার সূক্ষ্ম কাঁচের গ্লাসও ভাঙবে না।",
            },
            {
                "shot_number": 4,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "বর্তমানে বিশ্বজুড়ে ১০০ বিলিয়ন ডলারের এই রোবোটিক্স বাজারে চীন এবং আমেরিকা এখন একে অপরকে টেক্কা দিতে মরিয়া।",
            },
            {
                "shot_number": 5,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "তবে সবচেয়ে রোমাঞ্চকর বিষয় হলো, এই রোবটগুলো এখন মানুষের সাহায্য ছাড়াই নিজস্ব এআই ব্রেন দিয়ে নতুন কাজ শিখে নিচ্ছে।",
            },
            {
                "shot_number": 6,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "বিশেষজ্ঞদের গবেষণা বলছে, ২০৩০ সালের মধ্যে প্রায় ৬০ শতাংশ ফ্যাক্টরি ও ঘরের কাজ মানুষের বদলে এই রোবটরাই সামলাবে।",
            },
            {
                "shot_number": 7,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "একটু ভেবে দেখুন, যেখানে আগে ১০ জন কর্মীর সারা দিন লাগত, সেখানে একটি রোবট মাত্র ২ ঘণ্টায় নির্ভুলভাবে সব কাজ শেষ করছে।",
            },
            {
                "shot_number": 8,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "এখন মূল প্রশ্ন হলো—রোবটের এই যুগান্তকারী বিপ্লব কি মানুষের চাকরির সুযোগ কেড়ে নেবে, নাকি আমাদের জীবনকে আরও স্বাধীন ও সহজ করবে?",
            },
            {
                "shot_number": 9,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "আপনার মূল্যবান মতামত অবশ্যই নিচে কমেন্টে জানান—আপনি কি আপনার বাসায় এমন রোবট সহকারী রাখবেন?",
            },
            {
                "shot_number": 10,
                "shot_duration_seconds": 6.5,
                "voiceover_script": "এমন আরও চোখ জুড়ানো টেকনোলজি আপডেটের জন্য ভিডিওটি লাইক করে এখনি সাবস্ক্রাইব করুন। আল্লাহ হাফেজ।",
            },
        ],
    }

    mock_responses = [json.dumps(weak_payload), json.dumps(rich_payload)]

    with patch("pipeline.custom_pipeline.topic_research.grok_chat", side_effect=mock_responses):
        res = run_topic_research(
            niche="Robotics",
            video_type="short",
            output_root=tmp_path,
            max_dedupe_retries=2,
        )

    assert res["ok"] is True
    # Attempt 1 failed quality, Attempt 2 succeeded
    attempts = res["dedupe"]["attempts"]
    assert len(attempts) == 2
    assert attempts[0]["quality_ok"] is False
    assert attempts[1]["quality_ok"] is True
    assert res["dedupe"]["accepted_quality"] is True

    # Manifest saved
    pkg_dir = Path(res["save"]["package_root"])
    manifest_path = pkg_dir / "File" / "script_quality_manifest.json"
    assert manifest_path.is_file()
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["ok"] is True
    assert manifest_data["score"] >= 0.85
