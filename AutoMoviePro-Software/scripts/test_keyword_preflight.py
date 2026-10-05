"""Feature 4 tests: API-less keyword preflight before Agnes."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.prompt_hardening import (  # noqa: E402
    extract_model_tokens,
    preflight_keyword_prompt,
    required_visual_tokens,
)


def test_injects_missing_product_and_sku():
    pre = preflight_keyword_prompt(
        "cinematic desk shot, rim light, no text",
        keywords=["hero", "unboxing"],
        narration="Today we review the Pixel 9a in one tight look.",
        product_name="Pixel 9a",
    )
    assert "pixel" in pre["fixed_prompt"].lower()
    assert "9a" in pre["fixed_prompt"].lower()
    assert pre["injected"] is True
    assert pre["passed"] is True
    assert "9a" in extract_model_tokens("Pixel 9a")


def test_already_present_passes_without_inject():
    prompt = "Cinematic hero of Pixel 9a unboxing on dark desk, 9a chassis macro"
    pre = preflight_keyword_prompt(
        prompt,
        keywords=["Pixel 9a", "unboxing"],
        narration="Today we review the Pixel 9a.",
        product_name="Pixel 9a",
    )
    assert pre["passed"] is True
    assert pre["missing"] == []


def test_chernobyl_anchors():
    pre = preflight_keyword_prompt(
        "foggy night landscape",
        keywords=["reactor"],
        narration="The reactor exploded at 1:23 over Pripyat.",
        product_name="Chernobyl",
    )
    low = pre["fixed_prompt"].lower()
    assert "reactor" in low
    assert "chernobyl" in low
    req = required_visual_tokens(
        keywords=["reactor"], narration="The reactor exploded.", product_name="Chernobyl"
    )
    assert any("reactor" in r.lower() for r in req)


if __name__ == "__main__":
    test_injects_missing_product_and_sku()
    test_already_present_passes_without_inject()
    test_chernobyl_anchors()
    print("OK feature4 keyword preflight")
