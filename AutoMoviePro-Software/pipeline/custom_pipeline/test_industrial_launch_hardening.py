"""Industrial hardening tests: plan-time STOCK forbid, preflight, honest BN ship."""

from __future__ import annotations

from pipeline.custom_pipeline.honest_status import honest_shippable
from pipeline.custom_pipeline.visual_render import normalize_render_payload


def test_plan_time_stock_rewrites_product_ui():
    source = {
        "script_scenes": [
            {
                "shot_number": 1,
                "shot_duration_seconds": 6,
                "visual_subject": "product_ui",
                "voiceover_script": "ChatGPT Custom Instructions খুলে Save চাপো",
                "visual_prompt": "ChatGPT settings",
            }
        ]
    }
    payload = {
        "production_metadata": {"aspect_ratio": "9:16"},
        "render_scenes": [
            {
                "shot_number": 1,
                "render_type": "STOCK_VIDEO",
                "visual_subject": "product_ui",
                "visual_prompt": "ChatGPT Custom Instructions panel",
            }
        ],
    }
    out = normalize_render_payload(payload, source, aspect_ratio="9:16")
    assert out["render_scenes"][0]["render_type"] == "IMAGE"


def test_honest_ship_bn_only_when_optional_langs_missing():
    ship = honest_shippable(
        shared_success=8,
        shared_expected=8,
        finals_ok=["Bangla", "English"],
        expected_languages=["Bangla", "English", "Hindi", "Tamil", "Malayalam", "Urdu"],
    )
    assert ship["shippable"] is True
    assert ship["shippable_bn_only"] is True
    assert ship["shippable_all_languages"] is False
    assert "Tamil" in ship["missing_languages"]
    assert ship["partial"] is True


def test_honest_ship_no_bn_plan_requires_all():
    ship = honest_shippable(
        shared_success=2,
        shared_expected=2,
        finals_ok=["English"],
        expected_languages=["English", "Hindi"],
    )
    assert ship["shippable"] is False
    assert "Hindi" in ship["missing_languages"]


def test_preflight_runs_without_crash():
    from pipeline.custom_pipeline.pipeline_preflight import run_pipeline_preflight

    report = run_pipeline_preflight(
        languages=["English", "Hindi"],
        include_bangla_tts=True,
        skip_media=True,
        skip_tts=True,
        skip_localize=False,
    )
    assert "facts" in report
    assert "warnings" in report
    assert "blockers" in report


if __name__ == "__main__":
    test_plan_time_stock_rewrites_product_ui()
    test_honest_ship_bn_only_when_optional_langs_missing()
    test_honest_ship_no_bn_plan_requires_all()
    test_preflight_runs_without_crash()
    print("ok")
