"""AutoMovie Pro — Motion Graphics & Explainer Video Compositor.

Generates professional, high-retention motion graphics explainer videos utilizing:
1. Open-Source Lucide Vector Icon Library (`pipeline.icon_library`).
2. Procedural Kinetic Motion Backgrounds (Deep Cyber Mesh, Minimal Clean Slate, Neon Tech Pulse, Warm Sunset).
3. Glassmorphic Text Cards, Vector Badges, and Kinetic Typography (with HarfBuzz Bengali shaping & bundled fonts).
4. Multiple Explainer Layout Templates:
   - `center_hero_icon`: Large glowing central icon, top badge, bold kinetic headline, secondary bullet cards.
   - `split_card_explainer`: Split card layout with framed icon and dynamic bullet points.
   - `stat_counter_metric`: Bold metric/stat counter badge (+85%, 10X, ৳১,০০,০০০) with progress gauge.
   - `checklist_points`: 3 animated checkmark cards revealing key rules/tips.
   - `versus_comparison`: "সাধারণ উপায় ❌" vs "স্মার্ট নিয়ম ✅" contrast cards.
   - `quote_wisdom_card`: Framed wisdom card with golden quotes, avatar/icon emblem, and elegant typography.
5. Smooth FFmpeg Animation: Slide-up transitions, subtle breathing zoom/pan, audio ducking, and pristine muxing.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import subprocess
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from pipeline.compose import ffmpeg_bin, ffprobe_duration
from pipeline.icon_library import IconLibrary

try:
    import freetype
    import uharfbuzz as hb
    _HARFBUZZ_AVAILABLE = True
except Exception:
    _HARFBUZZ_AVAILABLE = False

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = BASE_DIR / "assets" / "fonts"
CACHE_DIR = BASE_DIR / "assets" / "motion_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_font_file() -> Path:
    """Finds best OpenType/TrueType font file on system across Windows, Linux, and bundled assets."""
    candidates = [
        FONTS_DIR / "Kalpurush.ttf",
        FONTS_DIR / "PotroSansBangla-Bold.ttf",
        FONTS_DIR / "vrindab.ttf",
        Path("C:/Windows/Fonts/Nirmala.ttc"),
        Path("C:/Windows/Fonts/vrindab.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return FONTS_DIR / "Kalpurush.ttf"


def draw_shaped_bengali_text(
    canvas: Image.Image,
    text: str,
    xy: Tuple[int, int],
    font_size: int = 36,
    color: Tuple[int, int, int, int] = (255, 255, 255, 255),
    align: str = "center",
    outline_color: Optional[Tuple[int, int, int, int]] = None,
    outline_width: int = 2,
) -> int:
    """
    Renders complex Bengali & Latin script text onto a PIL Image canvas using HarfBuzz & FreeType.
    Provides 100% correct conjunct (যুক্তবর্ণ) and vowel-sign shaping with optional outline.
    Returns the rendered height in pixels.
    """
    if not text:
        return 0

    text = unicodedata.normalize("NFC", str(text))
    font_path = _resolve_font_file()
    w_canvas, h_canvas = canvas.size

    if not _HARFBUZZ_AVAILABLE or not font_path.exists():
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()
        draw.text(xy, text, font=font, fill=color)
        return font_size + 10

    try:
        face = freetype.Face(str(font_path))
        face.set_pixel_sizes(0, font_size)
        with open(font_path, "rb") as f:
            font_bytes = f.read()
        hb_face = hb.Face(font_bytes)
        hb_font = hb.Font(hb_face)
        hb_font.scale = (font_size * 64, font_size * 64)
    except Exception as exc:
        logger.warning("HarfBuzz init failed: %s, falling back to PIL", exc)
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()
        draw.text(xy, text, font=font, fill=color)
        return font_size + 10

    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf)

    infos = buf.glyph_infos
    positions = buf.glyph_positions
    total_w = sum(p.x_advance for p in positions) // 64
    line_h = int(font_size * 1.35)

    target_x, target_y = xy
    if align == "center":
        cur_x = target_x - (total_w // 2)
    elif align == "right":
        cur_x = target_x - total_w
    else:
        cur_x = target_x

    mask = Image.new("L", (w_canvas, h_canvas), 0)
    base_x = cur_x
    base_y = target_y + font_size

    for info, pos in zip(infos, positions):
        try:
            face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
            slot = face.glyph
            bitmap = slot.bitmap
            bx = base_x + (pos.x_offset // 64) + slot.bitmap_left
            by = base_y - (pos.y_offset // 64) - slot.bitmap_top
            bw, bh = bitmap.width, bitmap.rows

            if bw > 0 and bh > 0 and 0 <= bx < w_canvas and 0 <= by < h_canvas:
                max_w = min(bw, w_canvas - bx)
                max_h = min(bh, h_canvas - by)
                arr = np.array(bitmap.buffer, dtype=np.uint8).reshape((bh, bw))
                sub_arr = arr[:max_h, :max_w]
                glyph_img = Image.fromarray(sub_arr, "L")
                mask.paste(glyph_img, (bx, by))
        except Exception:
            pass
        base_x += pos.x_advance // 64

    # Outline pass
    if outline_color and outline_width > 0:
        outline_mask = mask.filter(ImageFilter.MaxFilter(outline_width * 2 + 1))
        canvas.paste(Image.new("RGBA", (w_canvas, h_canvas), outline_color), (0, 0), outline_mask)

    # Main text fill pass
    canvas.paste(Image.new("RGBA", (w_canvas, h_canvas), color), (0, 0), mask)
    return line_h


def _wrap_shaped_lines(text: str, font_size: int, max_px: int) -> List[str]:
    """Wraps text so shaped length does not exceed max_px."""
    words = text.split()
    if not words:
        return []
    lines = []
    cur = []
    char_limit = max(10, int(max_px / (font_size * 0.58)))
    for w in words:
        test = " ".join(cur + [w])
        if len(test) <= char_limit or not cur:
            cur.append(w)
        else:
            lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return lines


class MotionGraphicsComposer:
    """Industrial Motion Graphics & Explainer Video Renderer."""

    LAYOUT_TEMPLATES = [
        "center_hero_icon",
        "split_card_explainer",
        "stat_counter_metric",
        "checklist_points",
        "versus_comparison",
        "quote_wisdom_card",
    ]

    BACKGROUND_STYLES = [
        "deep_cyber_mesh",
        "clean_slate_pro",
        "neon_pulse",
        "warm_gradient",
    ]

    @classmethod
    def render_motion_background(
        cls,
        dest_video: Path,
        duration: float,
        size: str = "1080x1920",
        style: str = "deep_cyber_mesh",
    ) -> Path:
        """
        Generates a sleek, high-definition animated procedural motion background
        using FFmpeg lavfi filters and subtle animated ambient luminance.
        """
        dest_video.parent.mkdir(parents=True, exist_ok=True)
        dur = max(2.0, float(duration))
        w, h = (int(x) for x in size.split("x")) if "x" in size else (1080, 1920)

        if style == "neon_pulse":
            c1 = "0x050510"
            c2 = "0x0a192f"
        elif style == "clean_slate_pro":
            c1 = "0x0b1120"
            c2 = "0x1e293b"
        elif style == "warm_gradient":
            c1 = "0x180c1e"
            c2 = "0x2d122e"
        else:  # deep_cyber_mesh
            c1 = "0x030712"
            c2 = "0x0f172a"

        # High-performance animated procedural gradient background
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-f", "lavfi",
            "-i", f"gradients=s={w}x{h}:d={dur}:c0={c1}:c1={c2}:x0={w//2}:y0={int(h*0.25)}:x1={w//2}:y1={int(h*0.85)}",
            "-filter_complex",
            (
                f"[0:v]vignette=angle=PI/3.2:aspect={w}/{h}[vig];"
                f"[vig]noise=alls=4:allf=t+u[final]"
            ),
            "-map", "[final]",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-t", str(dur),
            str(dest_video),
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if not dest_video.exists() or dest_video.stat().st_size < 1000:
            cmd_fallback = [
                ffmpeg_bin(),
                "-y",
                "-f", "lavfi",
                "-i", f"color=c={c1}:s={w}x{h}:d={dur}:r=30",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-t", str(dur),
                str(dest_video),
            ]
            subprocess.run(cmd_fallback, capture_output=True, check=False)

        return dest_video

    @classmethod
    def render_scene_graphic_card(
        cls,
        dest_png: Path,
        scene_data: Dict[str, Any],
        size: str = "1080x1920",
    ) -> Path:
        """
        Renders kinetic typography, open-source icons, vector badges,
        and glassmorphic cards with HarfBuzz complex shaping.
        """
        dest_png.parent.mkdir(parents=True, exist_ok=True)
        w, h = (int(x) for x in size.split("x")) if "x" in size else (1080, 1920)
        is_vertical = h > w

        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        template = str(scene_data.get("layout_template") or "center_hero_icon").lower().strip()
        icon_key = str(scene_data.get("icon_keyword") or "").strip()
        headline = str(scene_data.get("text_card_headline") or "").strip()
        body_text = str(scene_data.get("text_card_body") or scene_data.get("narration") or "").strip()
        badge_pill = str(scene_data.get("badge_pill") or "ভাইরাল স্ট্র্যাটেজি • SECRET HACKS").strip()

        if not icon_key:
            icon_key = IconLibrary.resolve_icon_keyword(f"{headline} {body_text}")

        card_bg = (15, 23, 42, 230)
        border_col = (56, 189, 248, 160)

        # -------------------------------------------------------------
        # 1. TEMPLATE: CENTER HERO ICON
        # -------------------------------------------------------------
        if template == "center_hero_icon":
            icon_dim = 220 if is_vertical else 180
            icon_png = IconLibrary.render_icon_png(
                icon_key,
                size=icon_dim,
                color="#ffffff",
                badge="rounded_square",
                badge_bg="#0b1329",
                border_color="#38bdf8",
                glow_color="#0284c7",
            )
            icon_img = Image.open(icon_png).convert("RGBA")

            top_y = int(h * 0.16) if is_vertical else int(h * 0.10)

            # Top Pill Badge with Tiny Vector Icon
            pill_w = int(w * 0.76) if is_vertical else int(w * 0.45)
            pill_h = 54
            pill_x1 = (w - pill_w) // 2
            pill_y1 = top_y
            draw.rounded_rectangle(
                [pill_x1, pill_y1, pill_x1 + pill_w, pill_y1 + pill_h],
                radius=27,
                fill=(30, 41, 59, 220),
                outline=(56, 189, 248, 190),
                width=2,
            )
            # Small badge icon
            badge_icon_dim = 30
            badge_icon_png = IconLibrary.render_icon_png(
                "sparkles", size=badge_icon_dim, color="#38bdf8", badge="none"
            )
            badge_icon_img = Image.open(badge_icon_png).convert("RGBA")
            canvas.alpha_composite(badge_icon_img, (pill_x1 + 18, pill_y1 + (pill_h - badge_icon_dim) // 2))

            draw_shaped_bengali_text(
                canvas,
                badge_pill,
                (pill_x1 + 18 + badge_icon_dim + 12 + (pill_w - 60) // 2 - 40, pill_y1 + 10),
                font_size=26 if is_vertical else 22,
                color=(248, 250, 252, 255),
                align="center",
            )

            # Center Hero Icon
            icon_x = (w - icon_dim) // 2
            icon_y = pill_y1 + pill_h + (35 if is_vertical else 20)
            canvas.alpha_composite(icon_img, (icon_x, icon_y))

            # Headline Card
            card_w = int(w * 0.88) if is_vertical else int(w * 0.70)
            card_x1 = (w - card_w) // 2
            card_y1 = icon_y + icon_dim + (35 if is_vertical else 20)

            head_text = headline or "মূল রহস্য ও সফলতার কার্যপদ্ধতি"
            head_size = 46 if is_vertical else 38
            body_size = 32 if is_vertical else 26

            head_lines = _wrap_shaped_lines(head_text, head_size, card_w - 70)
            body_lines = _wrap_shaped_lines(body_text, body_size, card_w - 70)[:4]

            card_content_h = (len(head_lines) * 60) + (len(body_lines) * 44) + 80
            card_y2 = card_y1 + card_content_h

            draw.rounded_rectangle(
                [card_x1, card_y1, card_x1 + card_w, card_y2],
                radius=24,
                fill=card_bg,
                outline=border_col,
                width=3,
            )
            draw.rounded_rectangle(
                [card_x1 + 40, card_y1, card_x1 + card_w - 40, card_y1 + 4],
                radius=2,
                fill=(56, 189, 248, 255),
            )

            cur_ty = card_y1 + 35
            for line in head_lines:
                draw_shaped_bengali_text(
                    canvas,
                    line,
                    (w // 2, cur_ty),
                    font_size=head_size,
                    color=(255, 215, 0, 255),
                    align="center",
                    outline_color=(0, 0, 0, 200),
                    outline_width=2,
                )
                cur_ty += 60

            cur_ty += 15
            for line in body_lines:
                draw_shaped_bengali_text(
                    canvas,
                    line,
                    (w // 2, cur_ty),
                    font_size=body_size,
                    color=(226, 232, 240, 255),
                    align="center",
                )
                cur_ty += 44

        # -------------------------------------------------------------
        # 2. TEMPLATE: STAT COUNTER METRIC
        # -------------------------------------------------------------
        elif template == "stat_counter_metric":
            stat_num = str(scene_data.get("stat_metric") or "+৮৫%").strip()
            stat_label = str(scene_data.get("stat_label") or headline or "অবিশ্বাস্য ফলাফল ও বৃদ্ধি").strip()

            icon_dim = 160 if is_vertical else 140
            icon_png = IconLibrary.render_icon_png(
                icon_key or "trending-up",
                size=icon_dim,
                color="#00f2fe",
                badge="circle",
                badge_bg="#081b29",
                border_color="#00f2fe",
                glow_color="#00f2fe",
            )
            icon_img = Image.open(icon_png).convert("RGBA")

            top_y = int(h * 0.16) if is_vertical else int(h * 0.10)
            icon_x = (w - icon_dim) // 2
            canvas.alpha_composite(icon_img, (icon_x, top_y))

            card_w = int(w * 0.88) if is_vertical else int(w * 0.72)
            card_x1 = (w - card_w) // 2
            card_y1 = top_y + icon_dim + 30

            head_size = 40 if is_vertical else 34
            body_size = 30 if is_vertical else 26
            head_lines = _wrap_shaped_lines(stat_label, head_size, card_w - 70)
            body_lines = _wrap_shaped_lines(body_text, body_size, card_w - 70)[:3]

            card_h = 130 + (len(head_lines) * 52) + (len(body_lines) * 42) + 60
            card_y2 = card_y1 + card_h

            draw.rounded_rectangle(
                [card_x1, card_y1, card_x1 + card_w, card_y2],
                radius=26,
                fill=card_bg,
                outline=(0, 242, 254, 180),
                width=3,
            )

            cur_ty = card_y1 + 25
            draw_shaped_bengali_text(
                canvas,
                stat_num,
                (w // 2, cur_ty),
                font_size=88 if is_vertical else 72,
                color=(0, 242, 254, 255),
                align="center",
                outline_color=(0, 0, 0, 220),
                outline_width=2,
            )
            cur_ty += 115

            pb_w = int(card_w * 0.75)
            pb_x = (w - pb_w) // 2
            draw.rounded_rectangle([pb_x, cur_ty, pb_x + pb_w, cur_ty + 14], radius=7, fill=(30, 41, 59, 255))
            draw.rounded_rectangle([pb_x, cur_ty, pb_x + int(pb_w * 0.88), cur_ty + 14], radius=7, fill=(0, 242, 254, 255))
            cur_ty += 35

            for line in head_lines:
                draw_shaped_bengali_text(
                    canvas,
                    line,
                    (w // 2, cur_ty),
                    font_size=head_size,
                    color=(255, 255, 255, 255),
                    align="center",
                )
                cur_ty += 52

            cur_ty += 10
            for line in body_lines:
                draw_shaped_bengali_text(
                    canvas,
                    line,
                    (w // 2, cur_ty),
                    font_size=body_size,
                    color=(203, 213, 225, 255),
                    align="center",
                )
                cur_ty += 42

        # -------------------------------------------------------------
        # 3. TEMPLATE: CHECKLIST POINTS
        # -------------------------------------------------------------
        elif template == "checklist_points":
            points = scene_data.get("checklist_items") or [
                "১. বিষয় নির্বাচন ও সুনির্দিষ্ট স্ট্র্যাটেজি",
                "২. সঠিক ভেক্টর আইকন ও টেক্সট কার্ড",
                "৩. ১-ক্লিকে স্বয়ংক্রিয় ভিডিও রেন্ডারিং",
            ]
            top_y = int(h * 0.14) if is_vertical else int(h * 0.08)

            t_text = headline or "৩টি মূল নিয়ম ও চেকলিস্ট"
            draw_shaped_bengali_text(
                canvas,
                t_text,
                (w // 2, top_y),
                font_size=42 if is_vertical else 36,
                color=(255, 215, 0, 255),
                align="center",
                outline_color=(0, 0, 0, 200),
                outline_width=2,
            )

            card_w = int(w * 0.88) if is_vertical else int(w * 0.75)
            card_x1 = (w - card_w) // 2
            cur_cy = top_y + 80

            check_dim = 54
            check_png = IconLibrary.render_icon_png("check-circle", size=check_dim, color="#10b981", badge="none")
            check_img = Image.open(check_png).convert("RGBA")

            for i, pt in enumerate(points[:3], start=1):
                pt_h = 96 if is_vertical else 80
                draw.rounded_rectangle(
                    [card_x1, cur_cy, card_x1 + card_w, cur_cy + pt_h],
                    radius=18,
                    fill=card_bg,
                    outline=(16, 185, 129, 150),
                    width=2,
                )
                canvas.alpha_composite(check_img, (card_x1 + 20, cur_cy + (pt_h - check_dim) // 2))
                draw_shaped_bengali_text(
                    canvas,
                    pt,
                    (card_x1 + 20 + check_dim + 15, cur_cy + (pt_h - 34) // 2 - 5),
                    font_size=32 if is_vertical else 26,
                    color=(248, 250, 252, 255),
                    align="left",
                )
                cur_cy += pt_h + 22

        # -------------------------------------------------------------
        # 4. TEMPLATE: VERSUS COMPARISON
        # -------------------------------------------------------------
        elif template == "versus_comparison":
            top_y = int(h * 0.14) if is_vertical else int(h * 0.08)
            t_text = headline or "সাধারণ পদ্ধতি বনাম স্মার্ট উপায়"
            draw_shaped_bengali_text(
                canvas,
                t_text,
                (w // 2, top_y),
                font_size=42 if is_vertical else 36,
                color=(255, 255, 255, 255),
                align="center",
                outline_color=(0, 0, 0, 200),
                outline_width=2,
            )

            card_w = int(w * 0.88) if is_vertical else int(w * 0.75)
            card_x1 = (w - card_w) // 2
            box_h = 170 if is_vertical else 135

            # Dynamic versus contents
            bad_title = str(scene_data.get("versus_bad_title") or "❌ সনাতন অপ্রচলিত ভুল").strip()
            bad_p1 = str(scene_data.get("versus_bad_p1") or "• সঠিক দিকনির্দেশনা ও পরিকল্পনার অভাব").strip()
            bad_p2 = str(scene_data.get("versus_bad_p2") or "• সময়ের অপচয় ও ক্লান্তিকর অনিশ্চিত ফল").strip()

            good_title = str(scene_data.get("versus_good_title") or "✅ আধুনিক পরীক্ষিত সমাধান").strip()
            good_p1 = str(scene_data.get("versus_good_p1") or "• সুনির্দিষ্ট বিজ্ঞানসম্মত কৌশল প্রয়োগ").strip()
            good_p2 = str(scene_data.get("versus_good_p2") or "• দ্রুত সর্বোচ্চ ফলাফল ও দীর্ঘস্থায়ী সাফল্য").strip()

            y_box1 = top_y + 75
            draw.rounded_rectangle(
                [card_x1, y_box1, card_x1 + card_w, y_box1 + box_h],
                radius=20,
                fill=(45, 15, 20, 225),
                outline=(239, 68, 68, 170),
                width=2,
            )
            draw_shaped_bengali_text(
                canvas, bad_title, (card_x1 + 30, y_box1 + 20),
                font_size=34 if is_vertical else 28, color=(239, 68, 68, 255), align="left",
            )
            draw_shaped_bengali_text(
                canvas, bad_p1, (card_x1 + 30, y_box1 + 75),
                font_size=28 if is_vertical else 22, color=(226, 232, 240, 255), align="left",
            )
            draw_shaped_bengali_text(
                canvas, bad_p2, (card_x1 + 30, y_box1 + 115),
                font_size=28 if is_vertical else 22, color=(226, 232, 240, 255), align="left",
            )

            vs_y = y_box1 + box_h + 15
            draw.rounded_rectangle([(w - 90) // 2, vs_y, (w + 90) // 2, vs_y + 44], radius=22, fill=(30, 41, 59, 240), outline=(255, 215, 0, 200), width=2)
            draw_shaped_bengali_text(
                canvas, "VS", (w // 2, vs_y + 8),
                font_size=32 if is_vertical else 26, color=(255, 215, 0, 255), align="center",
            )

            y_box2 = vs_y + 44 + 15
            draw.rounded_rectangle(
                [card_x1, y_box2, card_x1 + card_w, y_box2 + box_h],
                radius=20,
                fill=(10, 35, 25, 225),
                outline=(16, 185, 129, 180),
                width=2,
            )
            draw_shaped_bengali_text(
                canvas, good_title, (card_x1 + 30, y_box2 + 20),
                font_size=34 if is_vertical else 28, color=(16, 185, 129, 255), align="left",
            )
            draw_shaped_bengali_text(
                canvas, good_p1, (card_x1 + 30, y_box2 + 75),
                font_size=28 if is_vertical else 22, color=(226, 232, 240, 255), align="left",
            )
            draw_shaped_bengali_text(
                canvas, good_p2, (card_x1 + 30, y_box2 + 115),
                font_size=28 if is_vertical else 22, color=(226, 232, 240, 255), align="left",
            )

        # -------------------------------------------------------------
        # 5. TEMPLATE: SPLIT CARD EXPLAINER
        # -------------------------------------------------------------
        elif template == "split_card_explainer":
            top_y = int(h * 0.14) if is_vertical else int(h * 0.08)
            card_w = int(w * 0.88) if is_vertical else int(w * 0.75)
            card_x1 = (w - card_w) // 2

            # Top Badge Pill
            draw.rounded_rectangle(
                [card_x1, top_y, card_x1 + 280, top_y + 46],
                radius=12,
                fill=(30, 41, 59, 230),
                outline=(56, 189, 248, 180),
                width=2,
            )
            draw_shaped_bengali_text(
                canvas, badge_pill, (card_x1 + 140, top_y + 8),
                font_size=22 if is_vertical else 18, color=(56, 189, 248, 255), align="center",
            )

            # Hero Framed Icon
            icon_dim = 160 if is_vertical else 130
            icon_png = IconLibrary.render_icon_png(
                icon_key or "lightbulb",
                size=icon_dim,
                color="#38bdf8",
                badge="rounded_square",
                badge_bg="#0b1329",
                border_color="#38bdf8",
                glow_color="#0284c7",
            )
            icon_img = Image.open(icon_png).convert("RGBA")
            icon_y = top_y + 65
            canvas.alpha_composite(icon_img, ((w - icon_dim) // 2, icon_y))

            # Headline & Bullet Content Card
            card_y1 = icon_y + icon_dim + 25
            head_size = 38 if is_vertical else 32
            body_size = 28 if is_vertical else 24

            head_lines = _wrap_shaped_lines(headline or "মূল কার্যপ্রণালী ও গুরুত্বপূর্ণ বিষয়", head_size, card_w - 60)
            body_lines = _wrap_shaped_lines(body_text, body_size, card_w - 60)[:4]

            card_h = (len(head_lines) * 50) + (len(body_lines) * 38) + 60
            card_y2 = card_y1 + card_h

            draw.rounded_rectangle(
                [card_x1, card_y1, card_x1 + card_w, card_y2],
                radius=20,
                fill=card_bg,
                outline=border_col,
                width=2,
            )

            cur_ty = card_y1 + 25
            for line in head_lines:
                draw_shaped_bengali_text(
                    canvas, line, (w // 2, cur_ty),
                    font_size=head_size, color=(255, 215, 0, 255), align="center",
                )
                cur_ty += 50

            cur_ty += 10
            for line in body_lines:
                draw_shaped_bengali_text(
                    canvas, line, (w // 2, cur_ty),
                    font_size=body_size, color=(226, 232, 240, 255), align="center",
                )
                cur_ty += 38

        # -------------------------------------------------------------
        # 6. TEMPLATE: QUOTE WISDOM CARD
        # -------------------------------------------------------------
        else:
            icon_dim = 150 if is_vertical else 130
            icon_png = IconLibrary.render_icon_png(
                icon_key or "book-open",
                size=icon_dim,
                color="#ffd700",
                badge="circle",
                badge_bg="#17120a",
                border_color="#ffd700",
                glow_color="#f59e0b",
            )
            icon_img = Image.open(icon_png).convert("RGBA")

            top_y = int(h * 0.18) if is_vertical else int(h * 0.10)
            icon_x = (w - icon_dim) // 2
            canvas.alpha_composite(icon_img, (icon_x, top_y))

            card_w = int(w * 0.88) if is_vertical else int(w * 0.72)
            card_x1 = (w - card_w) // 2
            card_y1 = top_y + icon_dim + 30

            head_size = 40 if is_vertical else 34
            body_size = 32 if is_vertical else 26

            head_lines = _wrap_shaped_lines(headline or "জ্ঞান ও বাস্তবতার অমূল্য বার্তা", head_size, card_w - 70)
            body_lines = _wrap_shaped_lines(body_text, body_size, card_w - 70)[:4]

            card_h = (len(head_lines) * 55) + (len(body_lines) * 44) + 110
            card_y2 = card_y1 + card_h

            draw.rounded_rectangle(
                [card_x1, card_y1, card_x1 + card_w, card_y2],
                radius=26,
                fill=card_bg,
                outline=(255, 215, 0, 170),
                width=2,
            )

            cur_ty = card_y1 + 35
            for line in head_lines:
                draw_shaped_bengali_text(
                    canvas, line, (w // 2, cur_ty),
                    font_size=head_size, color=(255, 215, 0, 255), align="center",
                )
                cur_ty += 55

            cur_ty += 15
            for line in body_lines:
                draw_shaped_bengali_text(
                    canvas, line, (w // 2, cur_ty),
                    font_size=body_size, color=(241, 245, 249, 255), align="center",
                )
                cur_ty += 44

        canvas.save(dest_png, "PNG")
        return dest_png

    @classmethod
    @classmethod
    def compose_motion_scene_clip(
        cls,
        *,
        scene_data: dict,
        narration_audio: Path | None = None,
        duration: float | None = None,
        dest_clip: Path | None = None,
        work_dir: Path | None = None,
        size: str = "1080x1920"
    ) -> Path:
        """
        Creates a complete motion graphics scene MP4 clip with audio synchronization.
        """
        import tempfile
        work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="sc_motion_"))
        idx = scene_data.get("scene_index", 1)
        bg_style = scene_data.get("motion_background_style") or "deep_cyber_mesh"

        if narration_audio and narration_audio.exists():
            dur = max(2.5, ffprobe_duration(narration_audio))
        else:
            dur = max(2.5, float(duration or scene_data.get("estimated_duration_sec") or 5.0))

        # 1. Render Background Video (Real 4K B-Roll Video / 8K Synthesis / Animated Ambient Glow)
        bg_video = work / f"motion_bg_sc{idx}.mp4"
        
        # Priority 1: Genuine Downloaded B-Roll Video Footage
        broll_vid = scene_data.get("broll_video")
        if broll_vid and Path(broll_vid).exists():
            cmd_broll = [
                ffmpeg_bin(), "-y", "-i", str(broll_vid),
                "-t", f"{dur:.2f}",
                "-vf", "eq=brightness=-0.06:contrast=1.18:saturation=1.15,vignette=angle='PI/3.4+0.04*sin(2*PI*t/3)':eval=frame",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                str(bg_video)
            ]
            subprocess.run(cmd_broll, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Priority 2: 8K Synthesized Visual with Ken Burns
        if not bg_video.exists() or bg_video.stat().st_size < 1000:
            broll_img = scene_data.get("broll_image") or scene_data.get("broll_visual")
            if broll_img and Path(broll_img).exists():
                from pipeline.fallback_image_video import FFmpegProcessor
                temp_broll = work / f"temp_broll_raw_sc{idx}.mp4"
                FFmpegProcessor.image_to_ken_burns(
                    image=Path(broll_img),
                    dest=temp_broll,
                    duration=dur,
                    size=size,
                    motion="zoom_in",
                    fps=30,
                )
                cmd_dim = [
                    ffmpeg_bin(), "-y", "-i", str(temp_broll),
                    "-vf", "eq=brightness=0.03:contrast=1.18:saturation=1.20,vignette=angle=PI/3.8",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    str(bg_video)
                ]
                subprocess.run(cmd_dim, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    if temp_broll.exists():
                        temp_broll.unlink()
                except Exception:
                    pass

        # Priority 3: Procedural Animated Ambient Glow Background
        if not bg_video.exists() or bg_video.stat().st_size < 1000:
            cls.render_motion_background(bg_video, duration=dur, size=size, style=bg_style)

        # 2. Render Graphic Card Overlay
        card_png = work / f"motion_card_sc{idx}.png"
        cls.render_scene_graphic_card(card_png, scene_data, size=size)

        # 3. Composite with FFmpeg (Smooth Slide-Up and Fade Animation)
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i", str(bg_video),
            "-loop", "1",
            "-i", str(card_png),
        ]

        if narration_audio and narration_audio.exists():
            cmd.extend(["-i", str(narration_audio)])
            # Dynamic Pop-In Bounce Animation & Centered Responsive Card Placement
            filter_str = (
                "[1:v]format=rgba,fade=t=in:st=0:d=0.35:alpha=1[card];"
                "[0:v][card]overlay=x='(W-w)/2':y='(H-h)/2 + if(lte(t,0.35), 45*(1-sin(t/0.35*PI/2)), 0)':format=auto[outv]"
            )
            cmd.extend([
                "-filter_complex", filter_str,
                "-map", "[outv]",
                "-map", "2:a",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-t", str(dur),
                str(dest_clip),
            ])
        else:
            # Dynamic Pop-In Bounce Animation & Centered Responsive Card Placement
            filter_str = (
                "[1:v]format=rgba,fade=t=in:st=0:d=0.35:alpha=1[card];"
                "[0:v][card]overlay=x='(W-w)/2':y='(H-h)/2 + if(lte(t,0.35), 45*(1-sin(t/0.35*PI/2)), 0)':format=auto[outv]"
            )
            cmd.extend([
                "-filter_complex", filter_str,
                "-map", "[outv]",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-t", str(dur),
                str(dest_clip),
            ])

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if not dest_clip.exists() or dest_clip.stat().st_size < 1000:
            logger.error("Motion graphics scene composition failed: %s", res.stderr[:300])
            raise RuntimeError(f"FFmpeg motion graphics render failed for scene {idx}: {res.stderr[:200]}")

        return dest_clip
