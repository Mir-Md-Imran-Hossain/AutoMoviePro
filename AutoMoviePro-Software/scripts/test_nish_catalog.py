"""Smoke tests for Nish.Md catalog + niche agent wiring."""
from __future__ import annotations

from pipeline.niche_agent import apply_niche_to_channel, director_notes_from_channel
from pipeline.niche_director import niche_style_pack
from pipeline.nish_catalog import list_niches_for_api, load_niche_catalog, resolve_niche


def test_catalog_has_150():
    ns = load_niche_catalog(force_reload=True)
    assert len(ns) == 150
    assert ns[0]["name"]
    assert ns[0]["topic_generation_prompt"]
    assert ns[0]["video_prompt"]
    assert "{topic}" in ns[0]["video_prompt"] or "topic" in ns[0]["video_prompt"].lower()


def test_api_list_compact():
    items = list_niches_for_api()
    assert len(items) == 150
    assert "id" in items[0] and "name" in items[0]


def test_apply_niche_fills_channel():
    ch = apply_niche_to_channel({"niche_id": 1}, overwrite_empty_only=True)
    assert ch["niche"] == "Ancient Civilizations"
    assert ch["niche_id"] == 1
    assert ch["niche_style_family"] == "history"
    assert ch["video_special"]
    assert ch["niche_topic_prompt"]
    notes = director_notes_from_channel(ch)
    assert "NISH_ID=1" in notes
    assert "TOPIC_GENERATION_PROMPT" in notes


def test_style_packs_cover_families():
    for fam in (
        "history",
        "mystery",
        "science",
        "islamic",
        "gadget",
        "motivation",
        "health",
        "news",
        "finance",
        "nature",
        "true_crime",
    ):
        pack = niche_style_pack("x", fam)
        assert pack["grade"] and pack["faces"]


def test_resolve_by_name():
    p = resolve_niche("Epic Battles")
    assert p["id"] == 3
    assert p["style_family"] == "history"


if __name__ == "__main__":
    test_catalog_has_150()
    test_api_list_compact()
    test_apply_niche_fills_channel()
    test_style_packs_cover_families()
    test_resolve_by_name()
    print("OK nish catalog tests")
