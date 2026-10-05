"""Tests for duplicate topic/script detection and entity overlap guard."""

from pipeline.custom_pipeline.duplicate_guard import find_duplicate, similarity, token_overlap


def test_token_overlap_bengali_inflections():
    t1 = "BMW স্পার্টানবার্গে Figure 02 হিউম্যানয়েড রোবটের আসল ফ্যাক্টরি ট্রায়াল"
    t2 = "BMW স্পার্টানবার্গ কারখানায় Figure 02 হিউম্যানয়েড রোবটের পাইলট"
    overlap = token_overlap(t1, t2)
    assert overlap >= 0.70


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

    match = find_duplicate(new_payload, history, threshold=0.60)
    assert match is not None
    assert match["matched"] is True
    assert match["score"] >= 0.70


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

    match = find_duplicate(new_payload, history, threshold=0.60)
    assert match is None
