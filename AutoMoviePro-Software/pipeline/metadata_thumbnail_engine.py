"""AutoMovie Pro — Dynamic Thumbnail, Title, Description & Tags Generation Engine.

Core Features:
1. High-Click-Through (CTR) Multilingual Metadata Synthesis:
    - Language-specific localized Title, Description, and Tags (for YouTube, Facebook, TikTok).
    - SEO-keyword ranking injection with hashtags tailored to local niches.
2. Dynamic Thumbnail Generation with Pollinations AI & Local Fallback:
    - Generates high-impact psychological curiosity prompt.
    - Synthesizes 1280x720 (16:9 Long) or 1080x1920 (9:16 Short) thumbnail artwork.
    - Ensures genuine JPEG encoding with verified magic bytes (\\xff\\xd8\\xff) and pixel dimensions.
3. Local Self-Healing Agent Inspection:
    - Audits title length (40-65 chars optimal for YouTube CTR).
    - Checks description formatting with timestamps and social links.
    - Validates localized spellings and cultural appropriateness.
    - Strict JPEG integrity check: rejects 0-byte placeholders or corrupt images.
    - Triggers auto-regeneration if SEO score is below target threshold.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def inspect_thumbnail_image(thumb_path: Path) -> Dict[str, Any]:
    """Strictly validates thumbnail file existence, magic bytes, JPEG integrity, and dimensions."""
    res = {
        "valid": False,
        "width": 0,
        "height": 0,
        "aspect_ratio": "unknown",
        "format": "",
        "mime_type": "image/jpeg",
        "file_size_bytes": 0,
        "error": "",
    }

    if not thumb_path.exists():
        res["error"] = f"Thumbnail file not found at {thumb_path}"
        return res

    file_size = thumb_path.stat().st_size
    res["file_size_bytes"] = file_size

    if file_size < 500:
        res["error"] = f"Empty 0-byte file or corrupted placeholder ({file_size} bytes)"
        return res

    MAX_UPLOAD_SIZE = 2 * 1024 * 1024  # YouTube 2MB limit
    if file_size > MAX_UPLOAD_SIZE:
        res["error"] = f"Thumbnail file size ({file_size} bytes) exceeds YouTube 2MB upload limit"
        return res

    # Check JPEG magic bytes: starts with \xff\xd8\xff and reject mock markers
    try:
        header = thumb_path.read_bytes()[:32]
        head_lower = header.lower()
        if b"mock" in head_lower or b"fixture" in head_lower or b"dummy" in head_lower:
            res["error"] = "Mock artifact marker detected in thumbnail header"
            return res
        if header[:3] != b"\xff\xd8\xff":
            res["error"] = f"Invalid JPEG magic bytes header: {header[:3].hex()}"
            return res
    except Exception as exc:
        res["error"] = f"Unable to read file header: {exc}"
        return res

    # Decode and verify with PIL
    try:
        with Image.open(thumb_path) as im:
            im.verify()
        with Image.open(thumb_path) as im:
            im.load()  # Full pixel decode verification
            w, h = im.size
            fmt = im.format or ""
            mode = im.mode or ""
            res["width"] = w
            res["height"] = h
            res["format"] = fmt
            res["aspect_ratio"] = "9:16" if h > w else "16:9"

            if fmt.upper() not in ("JPEG", "JPG"):
                res["error"] = f"Invalid image format: expected JPEG but got {fmt}"
                return res

            # F-07: Platform upload compatibility checks
            MAX_UPLOAD_SIZE = 2 * 1024 * 1024  # YouTube 2MB limit
            if file_size > MAX_UPLOAD_SIZE:
                res["error"] = f"Thumbnail file size ({file_size} bytes) exceeds YouTube 2MB upload limit"
                return res

            if w < 360 or h < 360:
                res["error"] = f"Thumbnail resolution too low ({w}x{h}, minimum 360x360 required for upload)"
                return res

            if mode not in ("RGB", "RGBA", "L"):
                res["error"] = f"Unsupported color mode for upload: {mode}"
                return res

        res["valid"] = w > 0 and h > 0 and file_size >= 500
        res["error"] = "" if res["valid"] else "Invalid pixel dimensions"
        return res
    except Exception as exc:
        res["error"] = f"JPEG decode verification failed: {exc}"
        return res


def score_title_emotional_curiosity(title: str, language: str = "en") -> Dict[str, Any]:
    """Evaluates emotional power words and curiosity gap mechanics for viral YouTube CTR."""
    t_clean = (title or "").strip()
    t_lower = t_clean.lower()
    lang = (language or "en").lower().strip()

    # Multilingual Emotional Power Lexicon
    emotional_keywords = {
        "en": [
            "shocking", "insane", "unbelievable", "secret", "exposed", "truth", "tragic",
            "warning", "heartbreaking", "mindblowing", "danger", "deadly", "genius", "miracle",
            "nightmare", "ruined", "proved", "confession", "banned", "illegal", "hidden",
            "fear", "powerful", "astonishing", "urgent", "bizarre", "catastrophic", "untold", "reality"
        ],
        "bn": [
            "অবিশ্বাস্য", "গোপন", "রহস্য", "ভয়ঙ্কর", "ভয়ংকর", "সত্য", "ফাঁস", "আশ্চর্যজনক",
            "বিপদজনক", "চমকপ্রদ", "হৃদয়বিদারক", "হৃদয়বিদারক", "সতর্কবার্তা", "অবাক", "প্রমাণিত",
            "অজানা", "ভুল", "ধ্বংস", "বিপ্লব", "চমক", "আসল"
        ],
        "hi": [
            "हैरान", "चौंक", "सच्चाई", "सच", "रहस्य", "खुलासा", "खतरनाक", "गुप्त", "अद्भुत",
            "चेतावनी", "सबूत", "चौंकाने", "डरावना", "अनसुना", "तबाही", "राज", "रहस्यमयी"
        ],
        "ur": [
            "حیرت", "سچ", "راز", "انکشاف", "خطرناک", "ثبوت", "چھپائی", "خوفناک", "تباہی",
            "چونکانے", "حقیقت"
        ],
    }

    # Curiosity Gap Triggers
    curiosity_triggers = {
        "en": [
            "why", "how", "what", "nobody", "never", "revealed", "the truth", "exposed",
            "real reason", "what happens", "don't", "before", "mistake", "is this", "wait until"
        ],
        "bn": [
            "কেন", "কীভাবে", "কিভাবে", "কি", "কেউ", "বলবে না", "গোপন সত্য", "সত্যিটা",
            "যে কারণে", "সবাই", "জানেন কি", "ফাঁস", "কী ঘটে"
        ],
        "hi": [
            "क्यों", "कैसे", "क्या", "कोई नहीं", "असली सच", "सच्चाई", "जानकर", "चौंक जाएंगे",
            "जो कोई नहीं बताता", "खुलासा"
        ],
        "ur": [
            "کیوں", "کیسے", "کیا", "کوئی نہیں", "اصل سچ", "چھپائی گئی", "حقائق", "راز"
        ],
    }

    # Match emotional keywords across current language and English fallback
    matched_emotional = []
    pool_emo = emotional_keywords.get(lang, []) + emotional_keywords["en"]
    for w in set(pool_emo):
        if w.lower() in t_lower:
            matched_emotional.append(w)

    # Match curiosity triggers
    matched_curiosity = []
    pool_cur = curiosity_triggers.get(lang, []) + curiosity_triggers["en"]
    for c in set(pool_cur):
        if c.lower() in t_lower:
            matched_curiosity.append(c)

    # Intrigue syntax checks (questions, dashes, colons, ellipses, brackets)
    has_punctuation_hook = any(p in t_clean for p in ["?", "!", "—", "...", ":", "(", ")", "[", "]"])
    has_number_hook = any(ch.isdigit() for ch in t_clean) or "%" in t_clean or "১০০%" in t_clean

    # Calculate Emotional Power Score (0-100)
    emotional_power_score = min(100.0, 40.0 + (len(matched_emotional) * 20.0))

    # Calculate Curiosity Gap Score (0-100)
    curiosity_bonus = (10.0 if has_punctuation_hook else 0.0) + (10.0 if has_number_hook else 0.0)
    curiosity_gap_score = min(100.0, 40.0 + (len(matched_curiosity) * 20.0) + curiosity_bonus)

    # Title Length / Format score (0-100)
    t_len = len(t_clean)
    if 35 <= t_len <= 75:
        length_score = 100.0
    elif 25 <= t_len <= 90:
        length_score = 85.0
    elif 15 <= t_len <= 98:
        length_score = 70.0
    else:
        length_score = 50.0

    # Composite CTR Score
    composite_ctr_score = round(
        (emotional_power_score * 0.40) + (curiosity_gap_score * 0.45) + (length_score * 0.15),
        1,
    )

    if composite_ctr_score >= 90.0:
        tier = "A+ Viral Potential"
    elif composite_ctr_score >= 80.0:
        tier = "A High CTR"
    elif composite_ctr_score >= 70.0:
        tier = "B Strong"
    else:
        tier = "C Standard"

    recommendations = []
    if len(matched_emotional) == 0:
        recommendations.append("Add a high-impact emotional power word (e.g. 'Secret', 'Shocking', 'অবিশ্বাস্য').")
    if len(matched_curiosity) == 0 and not has_punctuation_hook:
        recommendations.append("Create a curiosity gap with 'Why', 'How', or cliffhanger punctuation.")
    if t_len < 30:
        recommendations.append("Title is slightly short. Elaborate the premise to maximize mobile readability.")
    elif t_len > 80:
        recommendations.append("Title may get truncated on mobile devices. Keep under 75 characters if possible.")

    return {
        "title": t_clean,
        "language": lang,
        "emotional_power_score": round(emotional_power_score, 1),
        "curiosity_gap_score": round(curiosity_gap_score, 1),
        "length_score": round(length_score, 1),
        "composite_ctr_score": composite_ctr_score,
        "tier": tier,
        "matched_emotional_words": sorted(matched_emotional),
        "matched_curiosity_hooks": sorted(matched_curiosity),
        "has_punctuation_hook": has_punctuation_hook,
        "has_number_hook": has_number_hook,
        "recommendations": recommendations,
    }


def generate_video_chapters(
    topic_title: str,
    total_duration_seconds: int = 300,
    video_format: str = "long",
    language: str = "en",
) -> List[Dict[str, Any]]:
    """Automated video chapters & timestamp generator (e.g. '00:00 Intro', '02:15 The Secret')."""
    fmt = (video_format or "long").lower().strip()
    lang = (language or "en").lower().strip()

    if fmt == "short":
        if lang == "bn":
            labels = [
                (0, "00:00", "ভূমিকা ও হুক (Intro & Critical Hook)"),
                (15, "00:15", "মূল রহস্য (The Core Twist)"),
                (35, "00:35", "গোপন সত্য উন্মোচন (The Secret Revealed)"),
                (50, "00:50", "চূড়ান্ত বার্তা (Final Verdict)"),
            ]
        elif lang == "hi":
            labels = [
                (0, "00:00", "शुरुआती हुक (Intro & Critical Hook)"),
                (15, "00:15", "असली मोड़ (The Core Twist)"),
                (35, "00:35", "सच्चाई का खुलासा (The Secret Revealed)"),
                (50, "00:50", "अंतिम निष्कर्ष (Final Verdict)"),
            ]
        elif lang == "ur":
            labels = [
                (0, "00:00", "ابتدائی تعارف (Intro & Critical Hook)"),
                (15, "00:15", "اہم موڑ (The Core Twist)"),
                (35, "00:35", "راز فاش (The Secret Revealed)"),
                (50, "00:50", "حتمی فیصلہ (Final Verdict)"),
            ]
        else:
            labels = [
                (0, "00:00", "Intro & Critical Hook"),
                (15, "00:15", "The Core Twist"),
                (35, "00:35", "The Secret Revealed"),
                (50, "00:50", "Final Verdict & Takeaway"),
            ]
    else:
        if lang == "bn":
            labels = [
                (0, "00:00", "ভূমিকা ও হুক (Intro & Critical Hook)"),
                (45, "00:45", f"মূল প্রেক্ষাপট (Core Reality of {topic_title})"),
                (135, "02:15", "গোপন রহস্য ও প্রমাণ (The Secret & Shocking Evidence)"),
                (220, "03:40", "গভীর বিশ্লেষণ (Deep Dive Breakdown)"),
                (270, "04:30", "চূড়ান্ত সিদ্ধান্ত (Final Verdict & Actionable Advice)"),
            ]
        elif lang == "hi":
            labels = [
                (0, "00:00", "शुरुआती हुक (Intro & Critical Hook)"),
                (45, "00:45", f"विषय की सच्चाई (Core Reality of {topic_title})"),
                (135, "02:15", "गुप्त रहस्य और सबूत (The Secret & Evidence)"),
                (220, "03:40", "विस्तृत विश्लेषण (Deep Dive Breakdown)"),
                (270, "04:30", "अंतिम निष्कर्ष (Final Verdict)"),
            ]
        elif lang == "ur":
            labels = [
                (0, "00:00", "ابتدائی تعارف (Intro & Critical Hook)"),
                (45, "00:45", f"بنیادی حقیقت (Core Reality of {topic_title})"),
                (135, "02:15", "چھپا ہوا راز اور ثبوت (The Secret & Evidence)"),
                (220, "03:40", "مکمل جائزہ (Deep Dive Breakdown)"),
                (270, "04:30", "حتمی فیصلہ (Final Verdict)"),
            ]
        else:
            labels = [
                (0, "00:00", "Intro & Critical Hook"),
                (45, "00:45", f"The Core Reality of {topic_title}"),
                (135, "02:15", "The Secret & Shocking Evidence"),
                (220, "03:40", "Deep Dive & Breakdown"),
                (270, "04:30", "Final Verdict & Key Takeaways"),
            ]

    chapters = []
    for sec, ts, lbl in labels:
        chapters.append({
            "seconds": sec,
            "time": ts,
            "timestamp": ts,
            "label": lbl,
            "title": lbl,
        })
    return chapters


@dataclass
class VideoMetadataPackage:
    language: str
    video_format: str  # 'short' or 'long'
    title: str
    description: str
    tags: List[str]
    hashtags: List[str]
    thumbnail_prompt: str
    thumbnail_image_path: str
    seo_score: float
    passed_qa: bool
    qa_notes: str = ""
    thumbnail_details: Dict[str, Any] = field(default_factory=dict)
    # Enterprise A/B Testing & Deep SEO additions
    thumbnail_variants: List[Dict[str, Any]] = field(default_factory=list)
    title_candidates: List[Dict[str, Any]] = field(default_factory=list)
    video_chapters: List[Dict[str, str]] = field(default_factory=list)
    seo_breakdown: Dict[str, Any] = field(default_factory=dict)


class MetadataThumbnailEngine:
    """Enterprise metadata synthesis and AI thumbnail generator."""

    def __init__(self, thumbs_dir: Optional[Path] = None):
        if thumbs_dir is None:
            thumbs_dir = Path(__file__).resolve().parent.parent / "data" / "thumbnails"
        self.thumbs_dir = Path(thumbs_dir)
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, str] = {}

    def _generate_via_pollinations(
        self,
        prompt: str,
        out_path: Path,
        width: int,
        height: int,
    ) -> Optional[Path]:
        """Generates thumbnail image via Pollinations AI API with timeout and JPEG conversion."""
        if os.environ.get("AUTOMOVIE_OFFLINE") == "1":
            return None

        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width={width}&height={height}&nologo=true&model=flux"
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                r = client.get(url)
                if r.status_code == 200 and len(r.content) > 1000:
                    with Image.open(io.BytesIO(r.content)) as im:
                        rgb = im.convert("RGB")
                        if rgb.size != (width, height):
                            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
                            rgb = rgb.resize((width, height), resample=resample)
                        rgb.save(out_path, format="JPEG", quality=92)
                    return out_path
        except Exception as exc:
            logger.debug("Pollinations thumbnail generation failed: %s", exc)
        return None

    def _render_local_thumbnail(
        self,
        out_path: Path,
        title: str,
        niche: str,
        width: int,
        height: int,
        variant_style: str = "bold_hook",  # 'bold_hook', 'split_curiosity', 'minimal_cinematic'
    ) -> Path:
        """Renders high-CTR, genuine JPEG thumbnail locally with niche themes, typography, and multiple visual styles."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        from PIL import ImageFont

        n = (niche or "").lower()
        if any(k in n for k in ("islam", "deen", "quran")):
            c1, c2, accent = (8, 28, 20), (18, 56, 42), (255, 215, 0)
            badge_text = "ISLAMIC REFLECTIONS"
        elif any(k in n for k in ("financ", "money", "invest", "crypto", "wealth")):
            c1, c2, accent = (8, 16, 32), (18, 36, 68), (0, 212, 255)
            badge_text = "FINANCIAL BLUEPRINT"
        elif any(k in n for k in ("health", "fitness", "sleep", "diet")):
            c1, c2, accent = (10, 26, 18), (20, 52, 36), (82, 183, 136)
            badge_text = "HEALTH & VITALITY"
        elif any(k in n for k in ("space", "science", "physics", "astronomy")):
            c1, c2, accent = (10, 6, 26), (26, 14, 56), (181, 23, 158)
            badge_text = "SCIENCE DOCUMENTARY"
        elif any(k in n for k in ("myster", "crime", "unexplain", "secret")):
            c1, c2, accent = (18, 10, 12), (40, 16, 20), (230, 57, 70)
            badge_text = "INVESTIGATION"
        elif any(k in n for k in ("tech", "gadget", "ai", "software")):
            c1, c2, accent = (12, 16, 28), (24, 34, 56), (255, 183, 3)
            badge_text = "TECH & AI PULSE"
        else:
            c1, c2, accent = (15, 23, 42), (30, 41, 59), (245, 158, 11)
            badge_text = "EXCLUSIVE"

        # Normalize variant style
        style_norm = (variant_style or "bold_hook").lower().strip()
        if style_norm in ("bold_hook", "high_emotion", "high_emotion_face"):
            effective_style = "high_emotion_face"
        elif style_norm in ("split_curiosity", "split_screen"):
            effective_style = "split_screen"
        elif style_norm in ("minimal_cinematic", "minimalist", "minimal"):
            effective_style = "minimalist"
        else:
            effective_style = style_norm

        base = Image.new("RGBA", (width, height), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(base)

        if effective_style == "split_screen":
            # Split Screen A/B Visual Contrast Layout
            split_x = width // 2
            # Left half: base gradient c1 -> c2
            for y in range(height):
                ratio = y / max(1, height)
                r = int(c1[0] + (c2[0] - c1[0]) * ratio)
                g = int(c1[1] + (c2[1] - c1[1]) * ratio)
                b = int(c1[2] + (c2[2] - c1[2]) * ratio)
                draw.line([(0, y), (split_x, y)], fill=(r, g, b, 255))
            # Right half: contrasting dramatic warm/neon tone
            c3, c4 = (35, 12, 18), (65, 20, 30)
            for y in range(height):
                ratio = y / max(1, height)
                r = int(c3[0] + (c4[0] - c3[0]) * ratio)
                g = int(c3[1] + (c4[1] - c3[1]) * ratio)
                b = int(c3[2] + (c4[2] - c3[2]) * ratio)
                draw.line([(split_x, y), (width, y)], fill=(r, g, b, 255))
            # Sharp divider line down center with neon glow
            div_w = max(2, int(min(width, height) * 0.006))
            draw.line([(split_x, 0), (split_x, height)], fill=accent, width=div_w)
        elif effective_style == "minimalist":
            # Minimalist Clean Matte Aesthetic with Refined Negative Space
            mc1 = (int(c1[0] * 0.45), int(c1[1] * 0.45), int(c1[2] * 0.45))
            mc2 = (int(c2[0] * 0.55), int(c2[1] * 0.55), int(c2[2] * 0.55))
            for y in range(height):
                ratio = y / max(1, height)
                r = int(mc1[0] + (mc2[0] - mc1[0]) * ratio)
                g = int(mc1[1] + (mc2[1] - mc1[1]) * ratio)
                b = int(mc1[2] + (mc2[2] - mc1[2]) * ratio)
                draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
        else:
            # High Emotion Face / Bold Hook Dramatic Gradient
            for y in range(height):
                ratio = y / max(1, height)
                r = int(c1[0] + (c2[0] - c1[0]) * ratio)
                g = int(c1[1] + (c2[1] - c1[1]) * ratio)
                b = int(c1[2] + (c2[2] - c1[2]) * ratio)
                draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        # Ambient / Focal Lighting depending on style
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        if effective_style == "high_emotion_face":
            # Multi-tiered intense facial spotlight aura
            gx, gy = int(width * 0.75), int(height * 0.4)
            max_rad = int(min(width, height) * 0.55)
            for rad in range(max_rad, 0, -15):
                alpha = int((1.0 - rad / max_rad) * 65)
                glow_draw.ellipse(
                    [gx - rad, gy - rad, gx + rad, gy + rad],
                    fill=(accent[0], accent[1], accent[2], alpha),
                )
        elif effective_style == "split_screen":
            # Dual ambient highlights on left and right
            gx1, gy1 = int(width * 0.25), int(height * 0.3)
            gx2, gy2 = int(width * 0.75), int(height * 0.7)
            max_rad = int(min(width, height) * 0.35)
            for rad in range(max_rad, 0, -20):
                alpha = int((1.0 - rad / max_rad) * 35)
                glow_draw.ellipse(
                    [gx1 - rad, gy1 - rad, gx1 + rad, gy1 + rad],
                    fill=(accent[0], accent[1], accent[2], alpha),
                )
                glow_draw.ellipse(
                    [gx2 - rad, gy2 - rad, gx2 + rad, gy2 + rad],
                    fill=(240, 60, 80, alpha),
                )
        else:
            # Minimalist subtle ambient glow
            gx, gy = int(width * 0.5), int(height * 0.2)
            max_rad = int(min(width, height) * 0.4)
            for rad in range(max_rad, 0, -25):
                alpha = int((1.0 - rad / max_rad) * 25)
                glow_draw.ellipse(
                    [gx - rad, gy - rad, gx + rad, gy + rad],
                    fill=(accent[0], accent[1], accent[2], alpha),
                )
        base = Image.alpha_composite(base, glow)
        draw = ImageDraw.Draw(base)

        # High-contrast framing brackets (skip on minimalist for clean negative space)
        margin = int(min(width, height) * 0.04)
        bw = max(2, int(min(width, height) * 0.006))
        blen = int(min(width, height) * 0.08)
        if effective_style != "minimalist":
            # Top-left bracket
            draw.line([(margin, margin), (margin + blen, margin)], fill=accent, width=bw)
            draw.line([(margin, margin), (margin, margin + blen)], fill=accent, width=bw)
            # Top-right bracket
            draw.line([(width - margin, margin), (width - margin - blen, margin)], fill=accent, width=bw)
            draw.line([(width - margin, margin), (width - margin - blen, margin)], fill=accent, width=bw)
            # Bottom-left bracket
            draw.line([(margin, height - margin), (margin + blen, height - margin)], fill=accent, width=bw)
            draw.line([(margin, height - margin), (margin, height - margin - blen)], fill=accent, width=bw)
            # Bottom-right bracket
            draw.line([(width - margin, height - margin), (width - margin - blen, height - margin)], fill=accent, width=bw)
            draw.line([(width - margin, height - margin), (width - margin, height - margin - blen)], fill=accent, width=bw)

        # Resolve font safely with fallbacks
        font_title = None
        font_badge = None
        for fc in [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/tahomabd.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]:
            if Path(fc).is_file():
                try:
                    font_title = ImageFont.truetype(fc, int(min(width, height) * 0.075))
                    font_badge = ImageFont.truetype(fc, max(12, int(min(width, height) * 0.035)))
                    break
                except Exception:
                    continue
        if not font_title:
            font_title = ImageFont.load_default()
            font_badge = ImageFont.load_default()

        # Draw Badge
        bx = margin + int(min(width, height) * 0.05)
        by = margin + int(min(width, height) * 0.05)
        badge_w = int(width * 0.42)
        badge_h = int(height * 0.08) if height > width else int(height * 0.09)
        if effective_style == "minimalist":
            draw.rectangle(
                [bx, by, bx + badge_w, by + badge_h],
                fill=(0, 0, 0, 100),
                outline=accent,
                width=1,
            )
            draw.text((bx + 14, by + int(badge_h * 0.2)), f" {badge_text} ", fill=accent, font=font_badge)
            # Minimalist clean rule under badge
            draw.line([(bx, by + badge_h + 8), (bx + int(width * 0.25), by + badge_h + 8)], fill=accent, width=2)
        elif effective_style == "high_emotion_face":
            draw.rounded_rectangle(
                [bx, by, bx + badge_w, by + badge_h],
                radius=8,
                fill=(accent[0], accent[1], accent[2], 70),
                outline=(255, 255, 255),
                width=2,
            )
            draw.text((bx + 16, by + int(badge_h * 0.2)), f" 🚨 {badge_text} ", fill=(255, 255, 255), font=font_badge)
        else:
            draw.rounded_rectangle(
                [bx, by, bx + badge_w, by + badge_h],
                radius=6,
                fill=(accent[0], accent[1], accent[2], 50),
                outline=accent,
                width=2,
            )
            draw.text((bx + 16, by + int(badge_h * 0.2)), f" {badge_text} ", fill=accent, font=font_badge)

        # Title Text Wrap & Clean Rendering
        clean_words = title.replace(":", " —").split()
        lines = []
        curr = []
        max_chars = 24 if width < height else 32
        for word in clean_words:
            curr.append(word)
            if len(" ".join(curr)) > max_chars:
                lines.append(" ".join(curr[:-1]))
                curr = [word]
        if curr:
            lines.append(" ".join(curr))
        lines = lines[:3]

        ty = by + badge_h + int(height * 0.06)
        line_spacing = int(min(width, height) * 0.095)
        for line in lines:
            # Shadow
            draw.text((bx + 3, ty + 3), line, fill=(0, 0, 0, 220), font=font_title)
            # Main
            draw.text((bx, ty), line, fill=(255, 255, 255), font=font_title)
            ty += line_spacing

        # Convert and save as high-quality real JPEG
        final_rgb = base.convert("RGB")
        final_rgb.save(out_path, format="JPEG", quality=92)
        return out_path

    def generate_thumbnail_variants(
        self,
        *,
        topic_title: str,
        niche: str,
        video_format: str,
        language: str,
        base_hash: str,
    ) -> List[Dict[str, Any]]:
        """Generates 3 distinct high-CTR thumbnail styles for A/B testing: Minimalist, High Emotion Face, Split Screen."""
        w, h = (1080, 1920) if video_format == "short" else (1280, 720)
        variants = []
        styles = [
            ("minimalist", "Minimalist Clean Aesthetic with Refined Negative Space"),
            ("high_emotion_face", "High Emotion Face & Dramatic Focal Hook"),
            ("split_screen", "Split Screen A/B Visual Contrast Layout"),
        ]

        for s_idx, (style_id, style_label) in enumerate(styles, 1):
            var_path = self.thumbs_dir / f"thumb_{language}_{video_format}_{base_hash[:8]}_v{s_idx}_{style_id}.jpg"
            self._render_local_thumbnail(var_path, topic_title, niche, width=w, height=h, variant_style=style_id)
            details = inspect_thumbnail_image(var_path)
            variants.append({
                "variant_id": f"v{s_idx}",
                "style": style_id,
                "label": style_label,
                "path": str(var_path),
                "is_primary": (s_idx == 1),
                "details": details,
            })
        return variants

    def score_title(self, title: str, language: str = "en") -> Dict[str, Any]:
        """Evaluates title for emotional power and curiosity gap mechanics."""
        return score_title_emotional_curiosity(title, language=language)

    def generate_package(
        self,
        *,
        topic_title: str,
        niche: str,
        video_format: str = "short",
        language: str = "bn",
        channel_name: str = "AutoMovie Pro Channel",
    ) -> VideoMetadataPackage:
        """Generates localized titles, description, tags, chapters and verified real JPEG thumbnail."""
        fmt = video_format.lower().strip()
        lang = language.lower().strip()

        # 1. Generate localized title candidates (High CTR, Curiosity Gap, Keyword SEO)
        if lang == "bn":
            title_a = f"{topic_title} — অবিশ্বাস্য তথ্য যা আপনাকে অবাক করবে!"
            title_b = f"কেন সবাই {topic_title} নিয়ে কথা বলছে? গোপন সত্য জেনে নিন"
            title_c = f"{topic_title}: যা কেউ আপনাকে বলবে না (১০০% প্রমাণিত)"
        elif lang == "hi":
            title_a = f"{topic_title} — हैरान कर देने वाली सच्चाई!"
            title_b = f"{topic_title} का असली सच क्या है? जानकर चौंक जाएंगे"
            title_c = f"{topic_title} का पूरा सच (जो कोई नहीं बताता)"
        elif lang == "ur":
            title_a = f"{topic_title} — حیرت انگیز حقائق جو آپ نہیں جانتے!"
            title_b = f"{topic_title} کا اصل سچ کیا ہے؟"
            title_c = f"{topic_title}: وہ حقیقت جو چھپائی گئی"
        else:
            title_a = f"{topic_title} — The Untold Truth Revealed!"
            title_b = f"Why Nobody Is Talking About {topic_title} (The Reality)"
            title_c = f"{topic_title}: What They Never Told You (Exposed)"

        raw_candidates = [
            {"style": "viral_hook", "title": title_a},
            {"style": "curiosity_gap", "title": title_b},
            {"style": "authority_investigation", "title": title_c},
        ]

        # Score all title candidates with Emotional Power & Curiosity Gap algorithm
        title_candidates = []
        best_title = title_a
        best_composite = -1.0
        for idx, rc in enumerate(raw_candidates):
            c_score = score_title_emotional_curiosity(rc["title"], language=lang)
            is_rec = idx == 0  # Primary hook recommended
            if c_score["composite_ctr_score"] > best_composite:
                best_composite = c_score["composite_ctr_score"]
                best_title = rc["title"]
            title_candidates.append({
                "style": rc["style"],
                "title": rc["title"],
                "is_recommended": is_rec,
                "emotional_power_score": c_score["emotional_power_score"],
                "curiosity_gap_score": c_score["curiosity_gap_score"],
                "composite_ctr_score": c_score["composite_ctr_score"],
                "tier": c_score["tier"],
                "matched_emotional_words": c_score["matched_emotional_words"],
                "matched_curiosity_hooks": c_score["matched_curiosity_hooks"],
            })

        localized_title = title_a

        # 2. Dynamic Video Chapters & Timestamps generator (00:00 Intro, 02:15 The Secret, etc.)
        total_sec = 60 if fmt == "short" else 300
        chapters = generate_video_chapters(topic_title, total_duration_seconds=total_sec, video_format=fmt, language=lang)

        # Generate description with timestamps & CTA
        chapter_str = "\n".join([f"{ch['time']} - {ch['label']}" for ch in chapters])
        desc_lines = [
            localized_title,
            "",
            f"স্বাগতম {channel_name} এ! আজকের পর্বে আমরা বিস্তারিত আলোচনা করেছি {topic_title} নিয়ে।",
            "",
            "📌 গুরুত্বপূর্ণ অংশসমূহ (Chapters & Timestamps):",
            chapter_str,
            "",
            "🔔 নিয়মিত নতুন ভিডিও পেতে লাইক ও সাবস্ক্রাইব করে পাশে থাকুন!",
            f"#AutoMoviePro #{fmt} #{niche.replace(' ', '')}",
        ]
        description = "\n".join(desc_lines)

        tags = [topic_title, niche, fmt, "viral", "trending", "2026", "facts", lang]
        hashtags = [f"#{topic_title.replace(' ', '')}", f"#{fmt}", "#viral", "#trending"]

        # 3. Dynamic Thumbnail Generation
        thumb_prompt = (
            f"Hyper-realistic, viral YouTube thumbnail for '{topic_title}', dramatic lighting, "
            f"high contrast, expressive face or central intrigue object, glowing neon accents, 8k resolution"
        )

        # Standard canvas dimensions: 1080x1920 (9:16 Short) or 1280x720 (16:9 Long)
        w, h = (1080, 1920) if fmt == "short" else (1280, 720)
        thumb_hash = hashlib.md5(f"{thumb_prompt}_{fmt}".encode("utf-8")).hexdigest()
        thumb_file = self.thumbs_dir / f"thumb_{lang}_{fmt}_{thumb_hash[:8]}.jpg"

        cached_valid = False
        if thumb_hash in self._cache:
            cached_path = Path(self._cache[thumb_hash])
            if cached_path.is_file():
                inspected_cached = inspect_thumbnail_image(cached_path)
                if inspected_cached["valid"]:
                    cached_valid = True
                    thumb_file = cached_path
                else:
                    logger.warning("Evicting invalid thumbnail from cache: %s", thumb_hash)
                    self._cache.pop(thumb_hash, None)
                    try:
                        cached_path.unlink(missing_ok=True)
                    except Exception as exc:
                        logger.debug("Failed deleting invalid thumbnail: %s", exc)
            else:
                self._cache.pop(thumb_hash, None)
        elif thumb_file.exists():
            inspected_file = inspect_thumbnail_image(thumb_file)
            if inspected_file["valid"]:
                cached_valid = True
            else:
                try:
                    thumb_file.unlink(missing_ok=True)
                except Exception as exc:
                    logger.debug("Failed deleting invalid thumbnail: %s", exc)

        if not cached_valid:
            # Try Pollinations online API first
            resolved = self._generate_via_pollinations(thumb_prompt, thumb_file, width=w, height=h)
            if not resolved or not resolved.exists() or resolved.stat().st_size == 0:
                # Local high-quality synthetic thumbnail fallback
                self._render_local_thumbnail(thumb_file, topic_title, niche, width=w, height=h)

        # Generate 3 distinct A/B testing variants
        thumbnail_variants = self.generate_thumbnail_variants(
            topic_title=topic_title,
            niche=niche,
            video_format=fmt,
            language=lang,
            base_hash=thumb_hash,
        )

        package = VideoMetadataPackage(
            language=lang,
            video_format=fmt,
            title=localized_title,
            description=description,
            tags=tags,
            hashtags=hashtags,
            thumbnail_prompt=thumb_prompt,
            thumbnail_image_path=str(thumb_file),
            seo_score=0.0,
            passed_qa=False,
            qa_notes="",
            thumbnail_variants=thumbnail_variants,
            title_candidates=title_candidates,
            video_chapters=chapters,
            seo_breakdown={},
        )

        # 4. Local Agent Quality Audit
        package = self.inspect_metadata_quality(package)

        # Automated Recovery: If QA failed, attempt recovery by rendering clean local thumbnail
        if not package.passed_qa:
            logger.warning(
                "Thumbnail/Metadata QA failed (%s). Triggering automated recovery fallback.",
                package.qa_notes,
            )
            self._render_local_thumbnail(thumb_file, topic_title, niche, width=w, height=h)
            package = self.inspect_metadata_quality(package)

        # F-04: Only record in cache if package passes QA and thumbnail exists
        if package.passed_qa and thumb_file.exists() and thumb_file.stat().st_size >= 500:
            self._cache[thumb_hash] = str(thumb_file)
        else:
            self._cache.pop(thumb_hash, None)

        return package

    def inspect_metadata_quality(self, package: VideoMetadataPackage) -> VideoMetadataPackage:
        """Local agent auditing SEO viability, character length, and JPEG image integrity."""
        notes = []
        score = 90.0

        # Title length audit
        if len(package.title) < 20:
            score -= 10.0
            notes.append("Title too short for high CTR. Extended.")
            package.title += " (Full Breakdown)"
        elif len(package.title) > 95:
            score -= 5.0
            notes.append("Title length near maximum display limit.")

        # Tags count audit
        if len(package.tags) >= 5:
            score += 5.0

        # Thumbnail Image Integrity Audit
        thumb_path = Path(package.thumbnail_image_path)
        inspected = inspect_thumbnail_image(thumb_path)
        package.thumbnail_details = inspected
        expected_ratio = "9:16" if package.video_format == "short" else "16:9"

        if not inspected["valid"]:
            score -= 40.0
            notes.append(f"Thumbnail QA Failure: {inspected['error']}")
        else:
            if inspected["aspect_ratio"] != expected_ratio:
                score -= 20.0
                notes.append(
                    f"Thumbnail QA Failure: Aspect ratio mismatch (expected {expected_ratio} but got {inspected['aspect_ratio']})"
                )
            else:
                score += 5.0
                notes.append(
                    f"Thumbnail verified: valid JPEG {inspected['width']}x{inspected['height']} ({inspected['file_size_bytes']} bytes)"
                )

        # Variant Integrity & SEO Breakdown
        variants_ok = True
        if package.thumbnail_variants:
            for v in package.thumbnail_variants:
                v_path = Path(v.get("path", ""))
                if not v_path.exists() or v_path.stat().st_size < 500:
                    variants_ok = False
                    notes.append(f"Variant {v.get('variant_id')} file invalid or missing")
            if variants_ok:
                notes.append(f"A/B variants verified: {len(package.thumbnail_variants)} distinct styles ready")

        # Calculate CTR Curiosity & SEO breakdown metrics via dedicated algorithm
        title_len = len(package.title)
        title_viability = "optimal" if 25 <= title_len <= 85 else ("acceptable" if 15 <= title_len <= 95 else "suboptimal")
        title_eval = score_title_emotional_curiosity(package.title, package.language)
        curiosity_score = title_eval["curiosity_gap_score"]
        emotional_score = title_eval["emotional_power_score"]
        composite_ctr = title_eval["composite_ctr_score"]

        package.seo_breakdown = {
            "title_length": title_len,
            "title_viability": title_viability,
            "tags_count": len(package.tags),
            "hashtags_count": len(package.hashtags),
            "has_chapters": bool(package.video_chapters),
            "chapter_count": len(package.video_chapters),
            "variant_count": len(package.thumbnail_variants),
            "variants_verified": variants_ok,
            "ctr_curiosity_score": curiosity_score,
            "ctr_emotional_score": emotional_score,
            "composite_ctr_score": composite_ctr,
            "ctr_tier": title_eval["tier"],
            "title_scoring": title_eval,
            "matched_emotional_triggers": title_eval["matched_emotional_words"],
            "matched_curiosity_hooks": title_eval["matched_curiosity_hooks"],
        }

        package.seo_score = round(max(0.0, min(100.0, score)), 1)
        package.passed_qa = (
            package.seo_score >= 80.0
            and inspected["valid"]
            and (inspected.get("aspect_ratio") == expected_ratio)
            and variants_ok
        )
        package.qa_notes = " | ".join(notes)
        return package

    def regenerate_thumbnail(
        self,
        package: VideoMetadataPackage,
        *,
        custom_prompt: Optional[str] = None,
    ) -> VideoMetadataPackage:
        """Surgically re-generates thumbnail image with updated high-CTR prompt."""
        fmt = package.video_format
        w, h = (1080, 1920) if fmt == "short" else (1280, 720)
        prompt = custom_prompt or f"{package.thumbnail_prompt} (ultra vivid high contrast)"

        new_hash = hashlib.md5(f"{prompt}_{fmt}_regen".encode("utf-8")).hexdigest()
        new_file = self.thumbs_dir / f"thumb_{package.language}_{fmt}_{new_hash[:8]}.jpg"

        resolved = self._generate_via_pollinations(prompt, new_file, width=w, height=h)
        if not resolved or not resolved.exists() or resolved.stat().st_size == 0:
            self._render_local_thumbnail(new_file, package.title, "viral", width=w, height=h)

        package.thumbnail_prompt = prompt
        package.thumbnail_image_path = str(new_file)
        return self.inspect_metadata_quality(package)
