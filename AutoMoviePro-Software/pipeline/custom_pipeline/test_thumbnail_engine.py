"""Comprehensive Test Suite for Localized High-CTR Thumbnail Generation Engine."""

import json
import tempfile
from pathlib import Path
from unittest import mock
import pytest

from pipeline.custom_pipeline.thumbnail_engine import (
    build_thumbnail_prompt,
    _pick_localized_hook_text,
    render_thumbnail_with_branding,
    generate_localized_thumbnail_package,
)
from pipeline.metadata_thumbnail_engine import inspect_thumbnail_image


def test_build_thumbnail_prompt_long_and_short():
    """Prompt must incorporate niche aesthetics, composition, and safe zones."""
    # Long 16:9 prompt
    p_long = build_thumbnail_prompt(
        niche="Robotics & AI",
        topic="Figure 02 at BMW",
        title="Inside BMW's Robot Factory",
        premise="Humanoid robots assembling metal parts",
        language="en",
        video_type="long",
        channel_name="TechVision",
    )
    assert "Figure 02 at BMW" in p_long or "Inside BMW" in p_long
    assert "16:9" in p_long
    assert "bottom-right" in p_long  # YouTube duration badge safe zone
    assert "--no text" in p_long

    # Short 9:16 prompt
    p_short = build_thumbnail_prompt(
        niche="Robotics & AI",
        topic="Figure 02 at BMW",
        title="Inside BMW's Robot Factory",
        premise="Humanoid robots assembling metal parts",
        language="bn",
        video_type="short",
        channel_name="TechVision",
    )
    assert "9:16" in p_short
    assert "Vertical" in p_short


def test_pick_localized_hook_text_all_languages():
    """Hook text must be punchy (2-4 words) in the target language script."""
    # Bengali
    bn_hook = _pick_localized_hook_text("bn", ["BMW ফ্যাক্টরিতে রোবট কী করছে?"], "BMW রোবট")
    assert 2 <= len(bn_hook.split()) <= 5

    # English
    en_hook = _pick_localized_hook_text("en", ["Is Figure 02 replacing workers at BMW?"], "BMW Robots")
    assert 2 <= len(en_hook.split()) <= 5

    # Hindi
    hi_hook = _pick_localized_hook_text("hi", ["क्या रोबोट इंसानों की जगह लेंगे?"], "BMW Robots")
    assert 2 <= len(hi_hook.split()) <= 5


def test_render_thumbnail_with_branding_outputs_valid_jpeg():
    """Rendered thumbnail must have valid JPEG magic bytes, dimensions, and pass QA."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        base_img = tmp / "base.png"
        out_jpg = tmp / "thumb.jpg"
        out_png = tmp / "thumb.png"
        logo_img = tmp / "logo.png"

        # Create dummy logo
        from PIL import Image
        im = Image.new("RGBA", (100, 100), (255, 0, 0, 200))
        im.save(logo_img)

        # Render 16:9 Long thumbnail
        render_thumbnail_with_branding(
            base_image_path=base_img,
            out_jpg=out_jpg,
            out_png=out_png,
            hook_text="অবিশ্বাস্য আবিষ্কার!",
            language="bn",
            video_type="long",
            logo_path=logo_img,
            channel_name="AutoMovie Pro",
        )

        assert out_jpg.is_file()
        assert out_png.is_file()

        # Strict inspection using inspect_thumbnail_image
        res = inspect_thumbnail_image(out_jpg)
        assert res["valid"] is True
        assert res["width"] == 1280
        assert res["height"] == 720
        assert res["aspect_ratio"] == "16:9"
        assert res["format"].upper() in ("JPEG", "JPG")
        assert res["file_size_bytes"] < 2 * 1024 * 1024  # Under YouTube 2MB limit


def test_generate_localized_thumbnail_package_end_to_end():
    """End-to-end package generation creates thumbnails and metadata for all active languages."""
    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "Short" / "001_(AI Revolution)"
        file_dir = pkg / "File"
        file_dir.mkdir(parents=True, exist_ok=True)

        # Master topic script
        master_script = {
            "niche": "AI Tech",
            "channel_name": "NextGen AI",
            "video_type": "Shorts",
            "seo_metadata": {
                "selected_topic": "হিউম্যানয়েড রোবট বিপ্লব",
                "suggested_titles": ["রোবট কি মানুষের কাজ দখল করবে?"],
                "seo_keywords": ["AI", "Robot", "Tech"],
            },
            "scenes": [
                {"voiceover_script": "আজকে আমরা দেখব কীভাবে রোবট মানুষের কাজ পরিবর্তন করছে।"}
            ],
        }
        (file_dir / "topic_script.json").write_text(json.dumps(master_script, ensure_ascii=False), encoding="utf-8")

        # Localized English voice file
        en_voice = {
            "target_language": "English",
            "seo_metadata": {
                "selected_topic": "Humanoid Robot Revolution 2026",
                "suggested_titles": ["Will Robots Replace Human Labor?"],
                "seo_keywords": ["Humanoid", "Robots", "AI"],
            },
            "voice_scenes": [
                {"voiceover_script": "Today we explore how humanoid robots are changing manufacturing."}
            ],
        }
        (file_dir / "localized_voice_EN.json").write_text(json.dumps(en_voice), encoding="utf-8")

        def _fake_gen(prompt, out_path, **kwargs):
            p = Path(out_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            from PIL import Image
            im = Image.new("RGB", (1080, 1920), color=(20, 25, 45))
            im.save(p, format="PNG")
            return {"ok": True, "path": p}

        with mock.patch("pipeline.custom_pipeline.thumbnail_engine.generate_image_with_fallback", side_effect=_fake_gen):
            # Run thumbnail package generation
            summary = generate_localized_thumbnail_package(
                pkg,
                languages=["Bangla", "English"],
                channel_name="NextGen AI",
                force=True,
            )

        assert summary["package_root"] == str(pkg)
        assert "Bangla" in summary["results"]
        assert "English" in summary["results"]

        # Verify physical files on disk
        thumb_dir = pkg / "Thumbnail"
        assert thumb_dir.is_dir()
        
        # Root localized files
        bn_jpg = list(thumb_dir.glob("Thumbnail_*_BN_*.jpg"))
        en_jpg = list(thumb_dir.glob("Thumbnail_*_EN_*.jpg"))
        assert len(bn_jpg) == 1
        assert len(en_jpg) == 1

        # Per-language subfolders for upload tools
        assert (thumb_dir / "BN" / "thumbnail.jpg").is_file()
        assert (thumb_dir / "EN" / "thumbnail.jpg").is_file()

        # Metadata JSON files
        bn_meta = list(file_dir.glob("Metadata_*_BN_*.json"))
        en_meta = list(file_dir.glob("Metadata_*_EN_*.json"))
        assert len(bn_meta) == 1
        assert len(en_meta) == 1

        # Check metadata JSON contents
        meta_content = json.loads(bn_meta[0].read_text(encoding="utf-8"))
        assert meta_content["channel_name"] == "NextGen AI"
        assert "seo_title" in meta_content
        assert "seo_description" in meta_content
        assert "platform_upload_guide" in meta_content
        assert meta_content["thumbnail"]["passed_qa"] is True

        # Check manifest file
        manifest_file = file_dir / "thumbnail_generation_manifest.json"
        assert manifest_file.is_file()


def test_audit_thumbnail_clickability_and_quality():
    """Quality audit must verify dimensions, dynamic range, legibility, and clickability score."""
    from pipeline.custom_pipeline.thumbnail_engine import audit_thumbnail_clickability_and_quality
    with tempfile.TemporaryDirectory() as td:
        img_path = Path(td) / "test_thumb.jpg"
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (1280, 720), color=(15, 23, 42))
        draw = ImageDraw.Draw(im)
        # Add high contrast features
        for x in range(0, 1280, 40):
            draw.line([(x, 0), (x, 720)], fill=(x % 255, (x * 2) % 255, 255), width=2)
        im.save(img_path, format="JPEG", quality=92)

        res = audit_thumbnail_clickability_and_quality(img_path, expected_aspect="16:9", hook_text="মানুষের কাজ শেষ?")
        assert res["valid"] is True
        assert res["width"] == 1280
        assert res["height"] == 720
        assert res["clickability_score"] >= 80
        assert res["legibility_passed"] is True
        assert res["verdict"] == "PASSED"


def test_bengali_complex_conjuncts_rendering():
    """Complex Indic ligatures (যুক্তাক্ষর) like 'মানুষের কাজ শেষ?' must render cleanly without errors."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        base_img = tmp / "base.png"
        out_jpg = tmp / "thumb_bn.jpg"
        out_png = tmp / "thumb_bn.png"

        from PIL import Image
        im = Image.new("RGB", (1280, 720), color=(20, 20, 35))
        im.save(base_img, format="PNG")

        render_thumbnail_with_branding(
            base_image_path=base_img,
            out_jpg=out_jpg,
            out_png=out_png,
            hook_text="মানুষের কাজ শেষ?",
            sub_hook_text="বিপ্লবী রোবট!",
            language="bn",
            video_type="long",
        )

        assert out_jpg.is_file()
        assert out_jpg.stat().st_size > 1000
        assert out_png.is_file()
        assert out_png.stat().st_size > 1000
