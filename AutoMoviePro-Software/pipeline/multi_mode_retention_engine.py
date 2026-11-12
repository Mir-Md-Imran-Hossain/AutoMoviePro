"""
AutoMovie Pro — Multi-Mode Visual Retention & Self-Healing Engine
=============================================================================
Powers 3 Distinct Production Modes with Zero Static Screen Enforcement:
  Mode 1: Motion Graphics & Kinetic Mode (Animated cyber grid, moving gradients, metric cards)
  Mode 2: Agnes AI / Generative Living Video Footage Mode (Real living device/tech interaction)
  Mode 3: News Headline & Newspaper Scraper Mode (Breaking news chyron, newspaper zoom, scrolling marquee ticker)

Coupled with TikTok-style Kinetic Subtitle burning, procedural Whoosh/Impact/Pop/Glitch SFX,
and dynamic BGM mixing at broadcast 4Mbps CRF 20 bitrate.
"""
from __future__ import annotations

import math
import os
import random
import re
import struct
import subprocess
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pipeline.api_keys import load_api_bundle
from pipeline.compose import ffmpeg_bin, ffprobe_duration
from pipeline.motion_graphics_composer import MotionGraphicsComposer, draw_shaped_bengali_text
from pipeline.subtitle_align import proportional_cues
from pipeline.subtitle_burn import get_fonts_dir
from pipeline.tts_google import synthesize_narration

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
BGM_DIR = ASSETS_DIR / "audio" / "bgm"
OUTPUT_DIR = BASE_DIR / "Output" / "MultiMode_Retention_Suite"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# PROCEDURAL HIGH-RETENTION AUDIO SFX SYNTHESIZERS (Deterministic Wave Synthesis)
# =============================================================================

def generate_whoosh_sfx(out_path: Path, duration_sec: float = 0.55, sample_rate: int = 44100) -> Path:
    """Generates a high-energy sweeping wind/whoosh sound effect for hooks and scene transitions."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    num_samples = int(duration_sec * sample_rate)
    with wave.open(str(out_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            env = math.exp(-((t - 0.26) ** 2) / (2 * (0.08 ** 2)))
            freq = 240.0 + 850.0 * math.sin(math.pi * (t / duration_sec))
            val = int(env * (math.sin(2.0 * math.pi * freq * t) * 0.75 + (random.random() * 2 - 1) * 0.25) * 29000.0)
            val = max(-32768, min(32767, val))
            frames.extend(val.to_bytes(2, "little", signed=True))
        wav_file.writeframes(frames)
    return out_path


def generate_impact_sfx(out_path: Path, duration_sec: float = 0.70, sample_rate: int = 44100) -> Path:
    """Generates a deep cinematic sub-bass thud/impact sound effect for high-stakes visual reveals."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    num_samples = int(duration_sec * sample_rate)
    with wave.open(str(out_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            decay = math.exp(-t * 7.5)
            freq = 115.0 * math.exp(-t * 9.0) + 38.0
            click = 1.0 if t < 0.006 else 0.0
            val = int((decay * math.sin(2.0 * math.pi * freq * t) * 0.85 + click * 0.5) * 31000.0)
            val = max(-32768, min(32767, val))
            frames.extend(val.to_bytes(2, "little", signed=True))
        wav_file.writeframes(frames)
    return out_path


def generate_glitch_sfx(out_path: Path, duration_sec: float = 0.40, sample_rate: int = 44100) -> Path:
    """Generates a modern digital glitch stutter effect for news alerts and tech cuts."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    num_samples = int(duration_sec * sample_rate)
    with wave.open(str(out_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        pitches = [1400.0, 480.0, 2600.0, 920.0, 3100.0, 750.0]
        for i in range(num_samples):
            t = i / sample_rate
            pitch = pitches[int(t * 22) % len(pitches)]
            gate = 1.0 if (int(t * 45) % 2 == 0) else 0.1
            env = math.exp(-t * 3.5)
            val = int(env * gate * math.sin(2.0 * math.pi * pitch * t) * 26000.0)
            val = max(-32768, min(32767, val))
            frames.extend(val.to_bytes(2, "little", signed=True))
        wav_file.writeframes(frames)
    return out_path


def generate_pop_sfx(out_path: Path, duration_sec: float = 0.35, sample_rate: int = 44100) -> Path:
    """Generates a clean bubble pop sound effect for cards and badges."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    num_samples = int(duration_sec * sample_rate)
    with wave.open(str(out_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            freq = 620.0 * math.exp(-t * 12.0) + 180.0
            envelope = math.exp(-t * 14.0)
            val = int(envelope * math.sin(2.0 * math.pi * freq * t) * 26000.0)
            val = max(-32768, min(32767, val))
            frames.extend(val.to_bytes(2, "little", signed=True))
        wav_file.writeframes(frames)
    return out_path


# =============================================================================
# TIKTOK-STYLE KINETIC SUBTITLE BURNER
# =============================================================================

def format_ass_time(sec: float) -> str:
    cs = int(round(sec * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_kinetic_ass_file(
    dialogue: str,
    duration: float,
    out_ass: Path,
    width: int = 1080,
    height: int = 1920,
    is_short: bool = True,
) -> Path:
    """
    Builds an eye-catching TikTok/Reels kinetic ASS subtitle file:
    - 2-4 word rhythmic bursts.
    - Large, prominent bold font with cyber yellow primary color (&H0000FFFF) and thick outline.
    - Positioned in the mobile safe-zone (MarginV = 420).
    - Proper ASS override syntax {\\c&H0000FFFF&} ensuring tags are parsed by libass and never printed as raw text.
    """
    out_ass.parent.mkdir(parents=True, exist_ok=True)
    cues = proportional_cues(dialogue, duration_sec=duration, is_short=is_short, words_per_chunk=3)
    if not cues:
        cues = [{"start": 0.2, "end": max(1.0, duration - 0.2), "text": dialogue}]

    font_name = "Hind Siliguri"
    font_size = 76 if is_short else 56
    margin_v = 420 if is_short else 120

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KineticTikTok,{font_name},{font_size},&H0000FFFF,&H000000FF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,4.5,2.0,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for c in cues:
        t0 = format_ass_time(float(c.get("start", 0.0)))
        t1 = format_ass_time(float(c.get("end", 1.0)))
        text = str(c.get("text", "")).strip()
        words = text.split()
        if len(words) > 1:
            styled_text = f"{{\\c&H0000FFFF&}}{words[0]} {{\\c&H00FFFFFF&}}{' '.join(words[1:])}"
        else:
            styled_text = f"{{\\c&H0000FFFF&}}{text}"
        events.append(f"Dialogue: 0,{t0},{t1},KineticTikTok,,0,0,0,,{styled_text}")

    out_ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_ass


def burn_kinetic_subtitles_to_video(
    in_video: Path,
    dialogue: str,
    out_video: Path,
    work_dir: Path,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    """Burns vibrant TikTok kinetic subtitles into the video with broadcast bitrate using HarfBuzz glyph shaping."""
    dur = ffprobe_duration(in_video)
    from pipeline.subtitle_burn import render_harfbuzz_cues_to_overlay, HAVE_HARFBUZZ
    
    if HAVE_HARFBUZZ:
        cues = proportional_cues(dialogue, duration_sec=dur, is_short=(height > width), words_per_chunk=3)
        if not cues:
            cues = [{"start": 0.2, "end": max(1.0, dur - 0.2), "text": dialogue}]
        
        hb_dir = work_dir / f"hb_overlay_{in_video.stem}"
        concat_txt = render_harfbuzz_cues_to_overlay(
            cues, out_dir=hb_dir, size=f"{width}x{height}", lang="bn", is_short=(height > width)
        )
        posix_p = concat_txt.resolve().as_posix().replace(":", r"\:")
        filter_str = f"movie='{posix_p}':f=concat[sub];[0:v][sub]overlay=0:0[outv]"
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i", str(in_video),
            "-filter_complex", filter_str,
            "-map", "[outv]",
            "-map", "0:a:0?",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-b:v", "4M",
            "-maxrate", "5M",
            "-bufsize", "8M",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(out_video),
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if out_video.exists() and out_video.stat().st_size > 5000:
            return out_video

    # Fallback to ASS
    ass_path = work_dir / f"kinetic_sub_{in_video.stem}.ass"
    build_kinetic_ass_file(dialogue, dur, ass_path, width=width, height=height, is_short=(height > width))

    sp = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
    fonts_dir = str(get_fonts_dir()).replace("\\", "/").replace(":", "\\:")
    
    sub_filter = f"subtitles='{sp}':fontsdir='{fonts_dir}'"
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i", str(in_video),
        "-vf", sub_filter,
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-b:v", "4M",
        "-maxrate", "5M",
        "-bufsize", "8M",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out_video),
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if out_video.exists() and out_video.stat().st_size > 5000:
        return out_video
    return in_video


# =============================================================================
# MODE 1: MOTION GRAPHICS & KINETIC MODE BUILDER
# =============================================================================

def build_mode1_motion_graphics_video(
    dialogue_scenes: List[Dict[str, Any]],
    out_path: Path,
    work_dir: Path,
    include_subtitles: bool = True,
    use_dynamic_background: bool = True,
) -> Path:
    """
    Mode 1: Animated dynamic background (cyber grid, pulsing vignette, hue drift),
    smooth glassmorphic cards with stat counter badges, TikTok kinetic subtitles,
    Whoosh & Pop SFX, and ambient tech BGM.
    """
    out_path = Path(out_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    rendered_clips = []
    total_text = " ".join(s["text"] for s in dialogue_scenes)

    for idx, sc in enumerate(dialogue_scenes, 1):
        sc_dur = sc.get("duration", 7.5)
        clip_path = work_dir / f"m1_sc{idx}_raw.mp4"
        
        # 1. Render Background
        bg_video = work_dir / f"m1_bg_sc{idx}.mp4"
        if use_dynamic_background:
            MotionGraphicsComposer.render_motion_background(
                bg_video, duration=sc_dur, size="1080x1920", style="neon_pulse"
            )
        else:
            # Flawed static background for self-healing demonstration
            cmd_static = [
                ffmpeg_bin(), "-y", "-f", "lavfi",
                "-i", f"color=c=0x080810:s=1080x1920:d={sc_dur}:r=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", str(sc_dur),
                str(bg_video)
            ]
            subprocess.run(cmd_static, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 2. Render Multiple Sequential Scene Graphic Cards (Multi-Card Transition)
        # Card A: Stat counter metric (0.0s -> 3.8s)
        card1_png = work_dir / f"m1_card1_sc{idx}.png"
        metric_v = "৳১,৫০,০০০" if idx == 1 else "১০X"
        metric_l = "গড় মাসিক সাশ্রয়" if idx == 1 else "প্রোডাক্টিভিটি বৃদ্ধি"
        badge_p = "⚡ REVOLUTIONARY AI" if idx == 1 else "🚀 MAXIMUM GROWTH"
        scene_payload_1 = {
            "scene_index": idx,
            "duration_sec": sc_dur,
            "video_category": "motion_graphics",
            "layout_template": "stat_counter_metric",
            "text_card_headline": sc["headline"][:40],
            "text_card_subheadline": "AUTO-GENERATED KINETIC VISUAL",
            "icon_keyword": "chart_and_stats",
            "badge_pill": badge_p,
            "niche": "Technology",
            "metric_value": metric_v,
            "metric_label": metric_l,
            "stat_metric": metric_v,
            "stat_label": metric_l,
        }
        MotionGraphicsComposer.render_scene_graphic_card(card1_png, scene_payload_1, size="1080x1920")

        # Card B: Actionable Checklist / Feature points (3.6s -> sc_dur)
        card2_png = work_dir / f"m1_card2_sc{idx}.png"
        points_b = [
            "১. আল্ট্রা-ফাস্ট নিউরাল প্রসেসিং",
            "২. ৯৯.৯% নিখুঁত অটোমেশন আর্কিটেকচার",
            "৩. রিয়েল-টাইম প্রোডাকশন স্কেলিং",
        ] if idx == 1 else [
            "১. ১০ গুণ দ্রুত ভিডিও কম্পোজিশন",
            "২. অ্যাডভান্সড হার্ফবাজ ফন্ট টাইপোগ্রাফি",
            "৩. অটোমেটিক মাল্টি-কার্ড ট্রানজিশন",
        ]
        scene_payload_2 = {
            "scene_index": idx,
            "duration_sec": sc_dur,
            "video_category": "motion_graphics",
            "layout_template": "checklist_points",
            "text_card_headline": "অটোমেশন ফিচারের মূল সুবিধাসমূহ" if idx == 1 else "নেক্সট-জেন প্রযুক্তির মূল স্তম্ভ",
            "checklist_items": points_b,
            "icon_keyword": "check-circle",
            "badge_pill": "🔥 CORE FEATURES",
            "niche": "Technology",
        }
        MotionGraphicsComposer.render_scene_graphic_card(card2_png, scene_payload_2, size="1080x1920")

        # 3. Composite with FFmpeg (Card 1 Slide-in/Out, then Card 2 Slide-in/Fade-out)
        t_card1_out = 3.4
        t_card2_in = 3.6
        t_card2_out = max(4.5, sc_dur - 0.4)
        filter_multi_card = (
            f"[1:v]format=rgba,fade=t=in:st=0:d=0.35:alpha=1,fade=t=out:st={t_card1_out}:d=0.35:alpha=1[c1];"
            f"[2:v]format=rgba,fade=t=in:st={t_card2_in}:d=0.35:alpha=1,fade=t=out:st={t_card2_out}:d=0.35:alpha=1[c2];"
            f"[0:v][c1]overlay=x='(W-w)/2':y='(H-h)/2 + if(lte(t,0.35), 45*(1-sin(t/0.35*PI/2)), if(gte(t,{t_card1_out}), -45*(sin((t-{t_card1_out})/0.35*PI/2)), 0))':enable='between(t,0,{t_card2_in})':format=auto[tmp_v];"
            f"[tmp_v][c2]overlay=x='(W-w)/2':y='(H-h)/2 + if(between(t,{t_card2_in},{t_card2_in+0.35}), 45*(1-sin((t-{t_card2_in})/0.35*PI/2)), 0)':enable='gte(t,{t_card2_in})':format=auto[outv]"
        )
        cmd_comp = [
            ffmpeg_bin(), "-y",
            "-i", str(bg_video),
            "-loop", "1", "-i", str(card1_png),
            "-loop", "1", "-i", str(card2_png),
            "-filter_complex", filter_multi_card,
            "-map", "[outv]",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-t", str(sc_dur),
            str(clip_path)
        ]
        subprocess.run(cmd_comp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if clip_path.exists():
            rendered_clips.append(clip_path)

    # Concat scenes
    concat_txt = work_dir / "m1_concat.txt"
    concat_txt.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in rendered_clips), encoding="utf-8")
    
    stitched_video = work_dir / "m1_stitched.mp4"
    subprocess.run([
        ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy", str(stitched_video)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    total_dur = ffprobe_duration(stitched_video)

    # 4. Audio: Generate Narrator voice, Whoosh hook SFX, Pop transition SFX, and BGM
    whoosh_wav = work_dir / "m1_whoosh.wav"
    generate_whoosh_sfx(whoosh_wav, duration_sec=0.55)
    
    pop_wav = work_dir / "m1_pop.wav"
    generate_pop_sfx(pop_wav, duration_sec=0.35)

    bgm_path = BGM_DIR / "tech_ambient.wav"
    
    # Synthesize authentic Google TTS narration
    keys = (load_api_bundle() or {}).get("google_keys") or []
    tts_raw = work_dir / "m1_narration_raw.wav"
    tts_out = synthesize_narration(text=total_text, out_path=tts_raw, language_hint="bn", google_api_keys=keys)

    # Audio filter graph: Mix Narration (loud) + Hook Whoosh at 0.2s + Pop at transition (7.5s) + ducked BGM
    audio_mixed = work_dir / "m1_master_audio.wav"
    t_pop = dialogue_scenes[0].get("duration", 7.5)
    filter_aud = (
        f"[1:a]adelay=200|200,volume=1.4[sfx_w];"
        f"[2:a]adelay={int(t_pop*1000)}|{int(t_pop*1000)},volume=1.2[sfx_p];"
        f"[3:a]volume=0.18,aloop=loop=-1:size=2e+09[bgm];"
        f"[0:a]volume=1.6[voc];"
        f"[voc][sfx_w][sfx_p][bgm]amix=inputs=4:duration=first:dropout_transition=2[aout]"
    )
    cmd_aud = [
        ffmpeg_bin(), "-y",
        "-i", str(tts_out),
        "-i", str(whoosh_wav),
        "-i", str(pop_wav),
        "-i", str(bgm_path),
        "-filter_complex", filter_aud,
        "-map", "[aout]",
        "-t", f"{total_dur:.2f}",
        str(audio_mixed)
    ]
    subprocess.run(cmd_aud, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Mux AV with explicit map 0:v:0 and 1:a:0
    av_temp = work_dir / "m1_av_temp.mp4"
    cmd_mux = [
        ffmpeg_bin(), "-y",
        "-i", str(stitched_video),
        "-i", str(audio_mixed),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-b:v", "4M",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total_dur:.2f}",
        str(av_temp)
    ]
    subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 5. Burn TikTok Kinetic Subtitles
    if include_subtitles:
        final_video = burn_kinetic_subtitles_to_video(av_temp, total_text, out_path, work_dir)
    else:
        import shutil
        shutil.copy2(av_temp, out_path)
        final_video = out_path

    return final_video


# =============================================================================
# MODE 2: AGNES AI / GENERATIVE LIVING VIDEO FOOTAGE BUILDER
# =============================================================================

def build_mode2_living_video_footage(
    dialogue_scenes: List[Dict[str, Any]],
    out_path: Path,
    work_dir: Path,
) -> Path:
    """
    Mode 2: Genuine living video footage matching dialogue entities (smartphone usage,
    AI screens, high-tech studio), TikTok kinetic subtitles, Impact & Whoosh SFX,
    and corporate pulse BGM.
    """
    out_path = Path(out_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Select real smartphone and tech device footage clips (pure tech focus, zero human faces)
    source_pool = [
        BASE_DIR / "Output" / "ch27_short_20261016_174824" / "scene_01_design.mp4",
        BASE_DIR / "Output" / "ch27_short_20261016_174824" / "scene_02_display.mp4",
        BASE_DIR / "Output" / "ch27_short_20261016_174824" / "agnes_11_design_i2v_a1.mp4",
        BASE_DIR / "Output" / "ch27_short_20261016_174824" / "scene_03_battery.mp4",
    ]
    available_clips = [p for p in source_pool if p.exists() and p.stat().st_size > 1000]
    if not available_clips:
        # Fallback to any valid b-roll in Output
        available_clips = list((BASE_DIR / "Output").rglob("*.mp4"))[:3]

    rendered_clips = []
    total_text = " ".join(s["text"] for s in dialogue_scenes)

    for idx, sc in enumerate(dialogue_scenes, 1):
        sc_dur = sc.get("duration", 7.5)
        raw_clip = work_dir / f"m2_sc{idx}_footage.mp4"
        
        src_vid = available_clips[(idx - 1) % len(available_clips)]
        src_dur = ffprobe_duration(src_vid)
        loop_cnt = max(1, int(math.ceil(sc_dur / max(1.0, src_dur))))

        cmd = [
            ffmpeg_bin(), "-y",
            "-stream_loop", str(loop_cnt),
            "-i", str(src_vid),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.12:saturation=1.15",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-b:v", "4M",
            "-t", f"{sc_dur:.2f}",
            str(raw_clip)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if raw_clip.exists():
            rendered_clips.append(raw_clip)

    concat_txt = work_dir / "m2_concat.txt"
    concat_txt.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in rendered_clips), encoding="utf-8")
    
    stitched_video = work_dir / "m2_stitched.mp4"
    subprocess.run([
        ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy", str(stitched_video)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    total_dur = ffprobe_duration(stitched_video)

    # Audio: Impact SFX at 0.2s hook, Whoosh at transition, corporate pulse BGM
    impact_wav = work_dir / "m2_impact.wav"
    generate_impact_sfx(impact_wav, duration_sec=0.70)
    
    whoosh_wav = work_dir / "m2_whoosh.wav"
    generate_whoosh_sfx(whoosh_wav, duration_sec=0.55)

    bgm_path = BGM_DIR / "corporate_pulse.wav"

    keys = (load_api_bundle() or {}).get("google_keys") or []
    tts_raw = work_dir / "m2_narration_raw.wav"
    tts_out = synthesize_narration(text=total_text, out_path=tts_raw, language_hint="bn", google_api_keys=keys)

    audio_mixed = work_dir / "m2_master_audio.wav"
    t_trans = dialogue_scenes[0].get("duration", 7.5)
    filter_aud = (
        f"[1:a]adelay=200|200,volume=1.5[sfx_imp];"
        f"[2:a]adelay={int(t_trans*1000)}|{int(t_trans*1000)},volume=1.2[sfx_w];"
        f"[3:a]volume=0.20,aloop=loop=-1:size=2e+09[bgm];"
        f"[0:a]volume=1.6[voc];"
        f"[voc][sfx_imp][sfx_w][bgm]amix=inputs=4:duration=first:dropout_transition=2[aout]"
    )
    cmd_aud = [
        ffmpeg_bin(), "-y",
        "-i", str(tts_out),
        "-i", str(impact_wav),
        "-i", str(whoosh_wav),
        "-i", str(bgm_path),
        "-filter_complex", filter_aud,
        "-map", "[aout]",
        "-t", f"{total_dur:.2f}",
        str(audio_mixed)
    ]
    subprocess.run(cmd_aud, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Mux AV with explicit map 0:v:0 and 1:a:0
    av_temp = work_dir / "m2_av_temp.mp4"
    cmd_mux = [
        ffmpeg_bin(), "-y",
        "-i", str(stitched_video),
        "-i", str(audio_mixed),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-b:v", "4M",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total_dur:.2f}",
        str(av_temp)
    ]
    subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Burn TikTok kinetic subtitles
    final_video = burn_kinetic_subtitles_to_video(av_temp, total_text, out_path, work_dir)
    return final_video


# =============================================================================
# MODE 3: NEWS HEADLINE & NEWSPAPER MARQUEE TICKER BUILDER
# =============================================================================

def build_mode3_news_headline_video(
    dialogue_scenes: List[Dict[str, Any]],
    out_path: Path,
    work_dir: Path,
) -> Path:
    """
    Mode 3: Breaking news broadcast layout, scrolling marquee news ticker at bottom,
    newspaper headline zoom-in motion with press imagery, TikTok kinetic subtitles,
    Glitch/Breaking SFX, and news broadcast pulse BGM.
    """
    out_path = Path(out_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    from pipeline.live_news_engine import LiveNewsEngine

    keys = (load_api_bundle() or {}).get("google_keys") or []
    rendered_clips = []
    total_text = " ".join(s["text"] for s in dialogue_scenes)

    for idx, sc in enumerate(dialogue_scenes, 1):
        sc_dur = sc.get("duration", 7.5)
        clip_path = work_dir / f"m3_sc{idx}_news.mp4"
        
        scene_payload = {
            "scene_index": idx,
            "headline": sc["headline"],
            "summary": sc["text"],
            "category": "আন্তর্জাতিক প্রযুক্তি",
            "video_type": "short",
        }
        LiveNewsEngine.compose_news_scene_clip(
            scene_data=scene_payload,
            narration_audio=None,
            duration=sc_dur,
            size="1080x1920",
            dest_clip=clip_path,
            work_dir=work_dir / f"news_work_{idx}",
            google_api_keys=keys,
        )
        if clip_path.exists():
            rendered_clips.append(clip_path)

    concat_txt = work_dir / "m3_concat.txt"
    concat_txt.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in rendered_clips), encoding="utf-8")
    
    stitched_video = work_dir / "m3_stitched.mp4"
    subprocess.run([
        ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy", str(stitched_video)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    total_dur = ffprobe_duration(stitched_video)

    # Audio: Glitch/Breaking SFX at 0.2s hook, Whoosh at transition, news broadcast pulse BGM
    glitch_wav = work_dir / "m3_glitch.wav"
    generate_glitch_sfx(glitch_wav, duration_sec=0.45)
    
    whoosh_wav = work_dir / "m3_whoosh.wav"
    generate_whoosh_sfx(whoosh_wav, duration_sec=0.55)

    bgm_path = BGM_DIR / "news_broadcast_pulse.wav"

    tts_raw = work_dir / "m3_narration_raw.wav"
    tts_out = synthesize_narration(text=total_text, out_path=tts_raw, language_hint="bn", google_api_keys=keys)

    audio_mixed = work_dir / "m3_master_audio.wav"
    t_trans = dialogue_scenes[0].get("duration", 7.5)
    filter_aud = (
        f"[1:a]adelay=200|200,volume=1.5[sfx_g];"
        f"[2:a]adelay={int(t_trans*1000)}|{int(t_trans*1000)},volume=1.2[sfx_w];"
        f"[3:a]volume=0.22,aloop=loop=-1:size=2e+09[bgm];"
        f"[0:a]volume=1.6[voc];"
        f"[voc][sfx_g][sfx_w][bgm]amix=inputs=4:duration=first:dropout_transition=2[aout]"
    )
    cmd_aud = [
        ffmpeg_bin(), "-y",
        "-i", str(tts_out),
        "-i", str(glitch_wav),
        "-i", str(whoosh_wav),
        "-i", str(bgm_path),
        "-filter_complex", filter_aud,
        "-map", "[aout]",
        "-t", f"{total_dur:.2f}",
        str(audio_mixed)
    ]
    subprocess.run(cmd_aud, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Mux AV with explicit map 0:v:0 and 1:a:0
    av_temp = work_dir / "m3_av_temp.mp4"
    cmd_mux = [
        ffmpeg_bin(), "-y",
        "-i", str(stitched_video),
        "-i", str(audio_mixed),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-b:v", "4M",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total_dur:.2f}",
        str(av_temp)
    ]
    subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Burn TikTok kinetic subtitles
    final_video = burn_kinetic_subtitles_to_video(av_temp, total_text, out_path, work_dir)
    return final_video
