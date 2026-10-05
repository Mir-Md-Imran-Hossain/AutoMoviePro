"""
Social Call-To-Action (CTA) Overlay and Audio SFX Generator.

Generates localized on-screen animated CTA badges (Like, Comment, Share, Subscribe)
locked inside platform-safe margins (avoiding TikTok / Reels / Shorts right icons & bottom bar)
paired with synchronized Pop / Whoosh SFX audio pulses.
"""
from __future__ import annotations

import logging
import math
import subprocess
import wave
from pathlib import Path
from typing import Optional, Tuple

from pipeline.compose import ffmpeg_bin, ffprobe_duration

logger = logging.getLogger(__name__)

# Localized CTA badge text
CTA_MESSAGES = {
    "bn": "লাইক ও সাবস্ক্রাইব করুন",
    "en": "Like & Subscribe",
    "hi": "लाइक और सब्सक्राइब करें",
    "ta": "லைக் & சப்ஸ்கிரைப் செய்யவும்",
    "ml": "ലൈക്കും സബ്സ്ക്രൈബും ചെയ്യുക",
    "ar": "إعجاب واشتراك",
    "es": "Dale Like y Suscríbete",
}


def get_cta_text(lang: str = "en") -> str:
    code = (lang or "en").lower()[:2]
    return CTA_MESSAGES.get(code, "Like & Subscribe")


def generate_pop_sfx(out_path: Path, duration_sec: float = 0.35, sample_rate: int = 44100) -> Path:
    """Generate a clean, pleasant pop/bubble audio pulse using pure Python wave module."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    num_samples = int(duration_sec * sample_rate)
    with wave.open(str(out_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            # Frequency pitch drop from 600Hz down to 220Hz creates an organic pop
            freq = 600.0 * math.exp(-t * 12.0) + 180.0
            # Rapid exponential decay envelope
            envelope = math.exp(-t * 14.0)
            val = int(envelope * math.sin(2.0 * math.pi * freq * t) * 26000.0)
            val = max(-32768, min(32767, val))
            frames.extend(val.to_bytes(2, byteorder="little", signed=True))
        wav_file.writeframes(frames)
    return out_path


def render_cta_badge_image(
    out_path: Path,
    *,
    text: str,
    lang: str = "en",
    width: int = 680,
    height: int = 140,
) -> Path:
    """Render a modern glassmorphic pill badge with icons and localized CTA text."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont

        # Create RGBA canvas
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw rounded rectangle background (vibrant red/crimson gradient or sleek dark with gold border)
        pad = 8
        draw.rounded_rectangle(
            [(pad, pad), (width - pad, height - pad)],
            radius=40,
            fill=(20, 20, 26, 230),
            outline=(255, 68, 88, 255),
            width=3,
        )

        # Load font
        font_size = 32
        font = None
        font_names = ["Nirmala.ttf", "Kalpurush.ttf", "Arial.ttf", "segoeui.ttf"]
        for fn in font_names:
            try:
                font = ImageFont.truetype(fn, font_size)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        # Bell / Heart icon symbol and text
        full_text = f"🔔  {text}  ❤️"
        bbox = draw.textbbox((0, 0), full_text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (width - tw) // 2
        ty = (height - th) // 2 - 2

        # Draw subtle text drop shadow
        draw.text((tx + 2, ty + 2), full_text, fill=(0, 0, 0, 200), font=font)
        # Draw crisp white text
        draw.text((tx, ty), full_text, fill=(255, 255, 255, 255), font=font)

        img.save(out_path, format="PNG")
        return out_path
    except Exception as exc:
        logger.warning("render_cta_badge_image fallback: %s", exc)
        return out_path


def apply_social_cta_overlay(
    video_path: Path,
    out_path: Path,
    *,
    lang: str = "en",
    is_short: bool = True,
    cta_duration: float = 4.0,
) -> Path:
    """
    Overlay animated social CTA badge and pop SFX in the final seconds of the video.
    Strictly placed inside platform safe margins (avoiding TikTok/Reels/Shorts UI).
    """
    total_dur = ffprobe_duration(video_path)
    if total_dur < cta_duration + 1.0:
        return video_path

    start_time = max(0.0, total_dur - cta_duration)
    cta_text = get_cta_text(lang)

    badge_png = out_path.parent / "_tmp_cta_badge.png"
    render_cta_badge_image(badge_png, text=cta_text, lang=lang, width=640, height=130)

    pop_wav = out_path.parent / "_tmp_cta_pop.wav"
    generate_pop_sfx(pop_wav, duration_sec=0.35)

    if not badge_png.exists() or badge_png.stat().st_size < 500:
        return video_path

    # Vertical safe margin: centered X, positioned safely above bottom UI bar (y = H - 380 on 1080x1920)
    # avoids like/comment/share icons on right and soundbar on bottom
    ffmpeg = ffmpeg_bin()
    if is_short:
        overlay_x = "(W-w)/2"
        overlay_y = "H-h-360"
    else:
        overlay_x = "(W-w)/2"
        overlay_y = "H-h-120"

    # Filter complex: overlay badge with subtle fade-in, mix pop sfx with audio
    filter_complex = (
        f"[1:v]format=rgba,fade=t=in:st={start_time:.2f}:d=0.3:alpha=1[cta];"
        f"[0:v][cta]overlay={overlay_x}:{overlay_y}:enable='between(t,{start_time:.2f},{total_dur:.2f})'[v];"
        f"[2:a]adelay={int(start_time * 1000)}|{int(start_time * 1000)}[sfx];"
        f"[0:a][sfx]amix=inputs=2:duration=first:dropout_transition=2[a]"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-i", str(video_path),
        "-i", str(badge_png),
        "-i", str(pop_wav),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", "192k",
        str(out_path),
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 5000:
            logger.info("Social CTA badge and SFX overlay applied successfully: %s", out_path.name)
            return out_path
    except Exception as exc:
        logger.warning("apply_social_cta_overlay error: %s", exc)

    return video_path
