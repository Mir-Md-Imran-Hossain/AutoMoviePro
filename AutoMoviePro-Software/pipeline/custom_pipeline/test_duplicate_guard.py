"""Tests for duplicate topic/script detection, cross-format history, and entity collision guard."""

import unicodedata
from pipeline.custom_pipeline.duplicate_guard import (
    DEFAULT_THRESHOLD,
    detect_entity_collision,
    extract_entities,
    find_duplicate,
    load_history,
    similarity,
    token_overlap,
)


def test_token_overlap_bengali_inflections():
    t1 = "BMW স্পার্টানবার্গে Figure 02 হিউম্যানয়েড রোবটের আসল ফ্যাক্টরি ট্রায়াল"
    t2 = "BMW স্পার্টানবার্গ কারখানায় Figure 02 হিউম্যানয়েড রোবটের পাইলট"
    overlap = token_overlap(t1, t2)
    assert overlap >= 0.65


def test_bengali_nfc_nukta_equivalence():
    """Bengali decomposed nukta (U+09AF+U+09BC) must equal precomposed (U+09DF) under NFC."""
    decomposed = "হিউম্যান\u09af\u09bcড"  # হিউম্যানয়েড
    precomposed = "হিউম্যান\u09dfড"       # হিউম্যানয়েড
    assert similarity(decomposed, precomposed) == 1.0
    assert token_overlap(decomposed, precomposed) == 1.0


def test_find_duplicate_catches_paraphrased_same_topic():
    history = [
        {
            "selected_topic": "BMW স্পার্টানবার্গে Figure 02 হিউম্যানয়েড রোবটের আসল ফ্যাক্টরি ট্রায়াল",
            "topic": "BMW স্পার্টানবার্গে Figure 02 হিউম্যানয়েড রোবটের আসল ফ্যাক্টরি ট্রায়াল BMW ফ্যাক্টরিতে Figure 02 আসলে কী করছে?",
            "script": "আসসালামু আলাইকুম! BMW-র ফ্যাক্টরিতে এখন মানুষের মতো রোবট শিট মেটাল জায়গায় বসাচ্ছে",
            "source": "007",
        }
    ]

    new_payload = {
        "seo_metadata": {
            "selected_topic": "BMW স্পার্টানবার্গ কারখানায় Figure 02 হিউম্যানয়েড রোবটের পাইলট",
            "suggested_titles": ["BMW কারখানায় Figure 02 একাই শিট মেটাল বসাচ্ছে!"],
        },
        "script_scenes": [
            {
                "voiceover_script": "আসসালামু আলাইকুম! BMW-এর স্পার্টানবার্গ কারখানায় Figure 02 রোবট শিট মেটাল তুলছে",
            }
        ],
    }

    match = find_duplicate(new_payload, history, threshold=0.45)
    assert match is not None
    assert match["matched"] is True
    assert match["score"] >= 0.70
    assert "bmw" in match["common_entities"] or "figure" in match["common_entities"]


def test_cross_format_collision_short_007_vs_long_003():
    """Short 007 and Long 003 are both about Figure 02 in BMW assembly — MUST collide."""
    short_007_record = {
        "selected_topic": "BMW স্পার্টানবার্গে Figure 02 হিউম্যানয়েড রোবটের আসল ফ্যাক্টরি ট্রায়াল",
        "topic": "BMW স্পার্টানবার্গে Figure 02 হিউম্যানয়েড রোবটের আসল ফ্যাক্টরি ট্রায়াল BMW ফ্যাক্টরিতে Figure 02 আসলে কী করছে",
        "script": "BMW ফ্যাক্টরিতে Figure 02 শিট মেটাল বসাচ্ছে",
        "source": "Short/007",
    }

    long_003_payload = {
        "seo_metadata": {
            "selected_topic": "২০২৫-এর হিউম্যানয়েড পাইলট: Figure 02, Optimus ও Digit কারখানায় কী সত্যি করছে",
            "suggested_titles": [
                "BMW-র লাইনে হিউম্যানয়েড: Figure 02 যা করছে, আর যা এখনো পারে না",
                "Tesla Optimus, Figure ও Digit: ঘণ্টায় খরচের আসল হিসাব",
            ],
        },
        "script_scenes": [
            {"voiceover_script": "হিউম্যানয়েড রোবট কারখানায় কাজ করছে"}
        ],
    }

    match = find_duplicate(long_003_payload, [short_007_record], threshold=0.45)
    assert match is not None
    assert match["matched"] is True
    assert match["score"] == 1.0
    assert match["entity_collision"] is True
    assert "bmw" in match["common_entities"]
    assert "figure" in match["common_entities"]


def test_chatgpt_custom_instructions_collision():
    """Short 003 vs Short 004/005 about ChatGPT Custom Instructions must collide."""
    history = [
        {
            "selected_topic": "ChatGPT Custom Instructions Writing Style Clone Hack Students Miss in 2026",
            "topic": "ChatGPT Custom Instructions Writing Style Clone Hack Students Miss in 2026",
            "script": "ChatGPT Custom Instructions দিয়ে স্টুডেন্ট ও ফ্রিল্যান্সারদের কাজ দ্রুত করো",
            "source": "Short/003",
        }
    ]

    new_payload = {
        "seo_metadata": {
            "selected_topic": "ChatGPT Custom Instructions একবার সেট, সারাজীবন সময় বাঁচো",
            "suggested_titles": ["ChatGPT Custom Instructions সেট করো—আর কখনো একই প্রম্পট লিখতে হবে না"],
        },
        "script_scenes": [
            {"voiceover_script": "চ্যাটজিপিটি কাস্টম ইন্সট্রাকশন সেট করার নিয়ম"}
        ],
    }

    match = find_duplicate(new_payload, history, threshold=0.45)
    assert match is not None
    assert match["matched"] is True
    assert match["score"] >= 0.70
    assert "chatgpt" in match["common_entities"]


def test_find_duplicate_allows_genuinely_different_topic():
    history = [
        {
            "selected_topic": "BMW স্পার্টানবার্গে Figure 02 হিউম্যানয়েড রোবটের আসল ফ্যাক্টরি ট্রায়াল",
            "topic": "BMW স্পার্টানবার্গে Figure 02 হিউম্যানয়েড রোবটের আসল ফ্যাক্টরি ট্রায়াল",
            "script": "BMW-র ফ্যাক্টরিতে এখন মানুষের মতো রোবট",
            "source": "007",
        }
    ]

    new_payload = {
        "seo_metadata": {
            "selected_topic": "Boston Dynamics নতুন অল-ইলেকট্রিক Atlas রোবটের অবিশ্বাস্য ক্ষমতা",
            "suggested_titles": ["নতুন Atlas রোবট কীভাবে মানুষের চেয়েও বেশি ঘুরতে পারে?"],
        },
        "script_scenes": [
            {
                "voiceover_script": "বোস্টন ডাইনামিকসের নতুন অল-ইলেকট্রিক অ্যাটলাস রোবট এখন পুরো ৩৬০ ডিগ্রি ঘুরতে পারে!",
            }
        ],
    }

    match = find_duplicate(new_payload, history, threshold=0.45)
    assert match is None


def test_find_duplicate_allows_unrelated_science_topics():
    history = [
        {
            "selected_topic": "ইভেন্ট হরাইজনের ওপারে: ব্ল্যাক হোলের ভিতরে আসলে কী ঘটে",
            "topic": "ইভেন্ট হরাইজনের ওপারে: ব্ল্যাক হোলের ভিতরে আসলে কী ঘটে ব্ল্যাক হোলে পড়লে কী হবে",
            "script": "মহাবিশ্বের সবচেয়ে রহস্যময় বস্তু হলো ব্ল্যাক হোল",
            "source": "Long/001",
        }
    ]

    mayan_payload = {
        "seo_metadata": {
            "selected_topic": "কৃত্রিম বুদ্ধিমত্তার সাহায্যে প্রাচীন মায়ান সভ্যতার গোপন শহর আবিষ্কার",
            "suggested_titles": ["মায়ান সভ্যতার গোপন পিরামিড কীভাবে স্যাটেলাইট ও AI খুঁজে পেল?"],
        },
        "script_scenes": [
            {"voiceover_script": "মায়ান সভ্যতার প্রাচীন শহর গভীর জঙ্গলে লুকিয়ে ছিল হাজার বছর ধরে।"}
        ],
    }

    match = find_duplicate(mayan_payload, history, threshold=0.45)
    assert match is None


def test_load_history_includes_both_short_and_long():
    """Verify load_history loads outputs across both Short and Long by default."""
    records = load_history(include_all_formats=True)
    assert len(records) > 0
    # Must have both Short and Long sources
    sources = [str(r.get("source", "")).lower() for r in records]
    has_short = any("short" in s for s in sources)
    has_long = any("long" in s for s in sources)
    assert has_short and has_long
