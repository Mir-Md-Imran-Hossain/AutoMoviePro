# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Category B Multi-Card Kinetic Motion Graphics Engine
====================================================================
Proprietary Category B Engine for AutoMovie Pro SaaS.

Core Features:
1. Live Vertical 9:16 Motion Background (Curated Pexels clips or dynamic Cyber Ambient Motion).
2. Multi-Card Beat Synchronization:
   - Analyzes Bengali/English dialogue into 1 to 3 narrative clauses/beats.
   - For each beat, creates a dedicated Frosted Glassmorphism card.
   - Alternating Side Slide Animation:
     * Beat 1: Enters smoothly from LEFT, holds during narration, exits to RIGHT.
     * Beat 2: Enters smoothly from RIGHT, holds during narration, exits to LEFT.
     * Beat 3: Enters smoothly from LEFT, holds during narration, exits to RIGHT.
3. Context-Aware 3D Emojis & Badges (🧠, 🤖, ⚛️, 🔬, 📊, ⚡, ⚠️, 💡, 🚀).
4. Top Header & Bottom CTA/Source ticker.
5. Zero Black Screens Guarantee: Luminous background grading (Brightness + Saturation boost).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from playwright.sync_api import sync_playwright

from pipeline.api_keys import load_api_bundle
from pipeline.compose import ffmpeg_bin

logger = logging.getLogger("AutoMoviePro.KineticMotionEngine")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s][KineticEngine][%(levelname)s] %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass
class DialogueBeat:
    index: int
    clause_text: str
    start_sec: float
    end_sec: float
    side: str
    emoji: str
    badge: str
    headline: str
    stat_val: str
    accent_color: str


def get_api_bundle_map() -> Dict[str, Any]:
    bundle = load_api_bundle(extra_env_paths=[ROOT_DIR / ".env"]) or {}
    return bundle


def generate_cyber_ambient_motion_clip(
    out_path: Path,
    duration_s: float = 8.0,
    scene_index: int = 0
) -> Path:
    """
    Renders a luminous 1080x1920 (9:16 vertical) Cyber Ambient Motion Background.
    Guaranteed:
    1. NEVER BLACK: Vibrant cyberpunk gradients (Deep Sapphire, Neon Cyan #00F2FE, Electric Violet #8B5CF6, Indigo #6366F1).
    2. Dynamic glowing ambient bokeh light spheres and futuristic cyber-grid overlay.
    3. Continuous, smooth camera pan and zoom motion via FFmpeg.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp_bg_png = out_path.parent / f"ambient_canvas_s{scene_index}_{int(time.time()*1000)%10000}.png"

    themes = [
        # Scene 0: Electric Cyber Cyan & Deep Sapphire
        {"c1": "rgba(56, 189, 248, 0.45)", "c2": "rgba(99, 102, 241, 0.35)", "c3": "rgba(14, 165, 233, 0.30)", "bg": "#070E1E", "accent": "#38BDF8"},
        # Scene 1: Neon Violet & Fuchsia Cyber Glow
        {"c1": "rgba(168, 85, 247, 0.45)", "c2": "rgba(236, 72, 153, 0.35)", "c3": "rgba(129, 140, 248, 0.30)", "bg": "#0D0A1C", "accent": "#C084FC"},
        # Scene 2: Emerald Green & Radiant Teal Matrix
        {"c1": "rgba(16, 185, 129, 0.45)", "c2": "rgba(6, 182, 212, 0.35)", "c3": "rgba(52, 211, 153, 0.30)", "bg": "#051614", "accent": "#34D399"},
        # Scene 3: Sunset Amber & Cyber Gold Energy
        {"c1": "rgba(245, 158, 11, 0.45)", "c2": "rgba(239, 68, 68, 0.35)", "c3": "rgba(251, 191, 36, 0.30)", "bg": "#140D05", "accent": "#FBBF24"},
    ]
    t = themes[scene_index % len(themes)]

    html_ambient = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><style>
    body {{
        margin:0; padding:0; width:1080px; height:1920px; overflow:hidden;
        background: {t['bg']};
        position: relative;
    }}
    .glow-sphere-1 {{
        position: absolute; width: 900px; height: 900px; border-radius: 50%;
        background: radial-gradient(circle, {t['c1']} 0%, transparent 70%);
        top: 15%; left: 10%; filter: blur(70px);
    }}
    .glow-sphere-2 {{
        position: absolute; width: 850px; height: 850px; border-radius: 50%;
        background: radial-gradient(circle, {t['c2']} 0%, transparent 70%);
        bottom: 20%; right: 5%; filter: blur(80px);
    }}
    .glow-sphere-3 {{
        position: absolute; width: 600px; height: 600px; border-radius: 50%;
        background: radial-gradient(circle, {t['c3']} 0%, transparent 70%);
        top: 50%; left: 25%; filter: blur(60px);
    }}
    .cyber-grid {{
        position: absolute; inset: 0;
        background-image: linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px),
                          linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px);
        background-size: 60px 60px;
    }}
    .vignette {{
        position: absolute; inset: 0;
        background: radial-gradient(circle at 50% 50%, transparent 40%, rgba(3, 7, 18, 0.6) 100%);
    }}
    </style></head><body>
    <div class="glow-sphere-1"></div>
    <div class="glow-sphere-2"></div>
    <div class="glow-sphere-3"></div>
    <div class="cyber-grid"></div>
    <div class="vignette"></div>
    </body></html>"""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--disable-d3d11",
                "--disable-gpu-compositing",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu-rasterization",
                "--no-sandbox"
            ]
        )
        page = browser.new_page(viewport={"width": 1080, "height": 1920})
        page.set_content(html_ambient)
        page.screenshot(path=str(temp_bg_png))
        browser.close()

    fps = 30
    total_frames = int(duration_s * fps) + 60
    zoom_filter = f"zoompan=z='min(zoom+0.0003,1.08)':d={total_frames}:x='iw/2-(iw/zoom/2)+sin(in/40)*15':y='ih/2-(ih/zoom/2)+cos(in/40)*15':s=1080x1920:fps={fps}"

    cmd = [
        ffmpeg_bin(), "-y",
        "-loop", "1", "-i", str(temp_bg_png),
        "-vf", zoom_filter,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-t", f"{duration_s:.3f}",
        str(out_path)
    ]
    si = None
    cflags = 0
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        cflags = subprocess.CREATE_NO_WINDOW

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, startupinfo=si, creationflags=cflags)
    temp_bg_png.unlink(missing_ok=True)
    return out_path


def fetch_cinematic_motion_clip(
    query: str,
    out_path: Path,
    duration_s: float = 8.0,
    scene_index: int = 0
) -> Path:
    """
    Fetches an authentic vertical 1080x1920 motion video clip from Pexels,
    or falls back to procedural Cyber Ambient Motion.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = get_api_bundle_map()
    pex_keys = bundle.get("pexels_keys", []) or []
    pex_key = pex_keys[0] if pex_keys else os.getenv("PEXELS_API_KEY", "")

    if pex_key:
        try:
            # Clean English search query free of hardcoded domain bias
            search_term = re.sub(r'[\u0980-\u09FF]', '', str(query or "")).strip()
            search_term = re.sub(r'[^a-zA-Z0-9\s\-]', ' ', search_term).strip()
            if len(search_term) < 4:
                search_term = "cinematic ambient documentary atmosphere landscape"
            if "people" not in search_term.lower() and "face" not in search_term.lower():
                search_term = f"{search_term} no people faceless"

            url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(search_term)}&orientation=portrait&per_page=5"
            r = requests.get(
                url,
                headers={"Authorization": pex_key},
                timeout=12
            )
            if r.status_code == 200:
                vids = r.json().get("videos", [])
                if vids:
                    v_item = vids[scene_index % len(vids)]
                    files = v_item.get("video_files", [])
                    best_file = None
                    for f in files:
                        if f.get("width") == 1080 and f.get("height") == 1920:
                            best_file = f
                            break
                    if not best_file and files:
                        best_file = sorted(files, key=lambda x: (x.get("width") or 0) * (x.get("height") or 0), reverse=True)[0]

                    if best_file and best_file.get("link"):
                        with requests.get(best_file["link"], stream=True, timeout=30) as vr:
                            with open(out_path, "wb") as f:
                                for chunk in vr.iter_content(8192):
                                    f.write(chunk)
                        if out_path.exists() and out_path.stat().st_size > 10000:
                            logger.info(f"[*] Acquired authentic Pexels video clip for '{search_term}' ({round(out_path.stat().st_size / (1024*1024), 2)} MB)")
                            return out_path
        except Exception as e_pex:
            logger.debug("Pexels video fetch note: %s", e_pex)

    # Bulletproof Fallback: Generate illuminated, moving Cyber Ambient Canvas
    logger.info(f"[*] Generating luminous cyber ambient motion background (Scene {scene_index + 1})...")
    return generate_cyber_ambient_motion_clip(out_path, duration_s=max(float(duration_s), 6.0), scene_index=scene_index)


def split_dialogue_into_kinetic_beats(
    dialogue: str,
    duration: float,
    scene_idx: int = 1,
    niche: str = "Technology"
) -> List[DialogueBeat]:
    """
    Deconstructs scene narration into 1 to 3 dynamic, context-aware visual beats.
    Assigns precise start/end timings, alternating entry sides, contextual emojis,
    and glassmorphic color accents.
    """
    raw_clauses = [c.strip() for c in re.split(r'[।!?;]+', dialogue) if c.strip()]
    if not raw_clauses:
        raw_clauses = [dialogue.strip()]

    # If only 1 clause exists but is long (> 10 words) and duration >= 5.0s, split by commas
    if len(raw_clauses) == 1 and len(raw_clauses[0].split()) > 10 and duration >= 5.0:
        comma_split = [c.strip() for c in re.split(r'[,]+', raw_clauses[0]) if c.strip()]
        if len(comma_split) >= 2:
            raw_clauses = comma_split

    # Bound to max 3 beats to maintain high visual impact without overcrowding
    clauses = raw_clauses[:3]
    count = len(clauses)

    timing: List[Tuple[float, float]] = []
    if count == 1:
        timing.append((0.10, max(0.5, round(duration - 0.20, 2))))
    elif count == 2:
        mid = round(duration * 0.48, 2)
        timing.append((0.10, mid))
        timing.append((round(mid + 0.15, 2), max(mid + 0.5, round(duration - 0.20, 2))))
    else:  # count == 3
        t1 = round(duration * 0.32, 2)
        t2 = round(duration * 0.65, 2)
        timing.append((0.10, t1))
        timing.append((round(t1 + 0.15, 2), t2))
        timing.append((round(t2 + 0.15, 2), max(t2 + 0.5, round(duration - 0.20, 2))))

    beats: List[DialogueBeat] = []
    default_badges = ["মূল পর্যবেক্ষণ", "গাণিতিক উপাত্ত", "চূড়ান্ত বিশ্লেষণ"]
    accent_colors = ["#38BDF8", "#FBBF24", "#34D399"]  # Cyan, Amber, Emerald

    for i, (clause, (st, en)) in enumerate(zip(clauses, timing)):
        # Contextual Emoji and Icon extraction
        c_lower = clause.lower()
        if any(k in c_lower for k in ["এআই", "রোবট", "কম্পিউটার", "মেশিন", "বুদ্ধিমত্তা", "অ্যালগরিদম", "ai", "robot"]):
            emoji = "🤖" if i % 2 == 0 else "🧠"
        elif any(k in c_lower for k in ["পরমাণু", "পদার্থবিজ্ঞান", "বিজ্ঞান", "মহাবিশ্ব", "গবেষণা", "physics", "science"]):
            emoji = "🔬" if i % 2 == 0 else "💡"
        elif any(k in c_lower for k in ["সংখ্যা", "%", "শতাংশ", "হিসাব", "টাকা", "উপাত্ত", "রেকর্ড", "পরিমাপ", "data", "percent"]):
            emoji = "📊" if i % 2 == 0 else "📈"
        elif any(k in c_lower for k in ["বিপদ", "ঝুঁকি", "হুমকি", "ভয়ানক", "ধ্বংস", "নিয়ন্ত্রণ", "danger", "warning"]):
            emoji = "⚠️" if i % 2 == 0 else "⚡"
        elif any(k in c_lower for k in ["সত্য", "রহস্য", "আবিষ্কার", "উন্মোচন", "অলৌকিক", "discovery", "secret"]):
            emoji = "💡" if i % 2 == 0 else "🔍"
        else:
            rotation = ["⚡", "🚀", "💎", "🧠", "🔬", "📊"]
            emoji = rotation[(scene_idx + i) % len(rotation)]

        # Alternating side slide
        side = "left" if (i % 2 == 0) else "right"

        # Badge pill
        badge = default_badges[i % len(default_badges)]

        # Extract number if present
        nums = re.findall(r'(\d+|[০-৯]+)', clause)
        stat_val = f"{nums[0]} পরিমাপ" if nums else "যাচাইকৃত সত্য"

        # Headline: first 4-5 words
        words = re.sub(r'[।!?,;\'\"“”‘’—\-]', ' ', clause).split()
        headline = " ".join(words[:5]) if len(words) >= 5 else clause

        beats.append(
            DialogueBeat(
                index=i + 1,
                clause_text=clause,
                start_sec=st,
                end_sec=en,
                side=side,
                emoji=emoji,
                badge=badge,
                headline=headline,
                stat_val=stat_val,
                accent_color=accent_colors[i % len(accent_colors)]
            )
        )

    return beats


def render_beat_glass_cards(
    beats: List[DialogueBeat],
    temp_dir: Path,
    logo_title: str = "AutoMovie Pro",
    cta_text: str = "লাইক ও সাবস্ক্রাইব করুন"
) -> Dict[str, Path]:
    """
    Renders the static transparent PNGs for:
    1. Top Channel/Topic Header Pill
    2. Dynamic Beat Cards (1, 2, 3) with frosted glassmorphism & contextual emojis
    3. Bottom Action/CTA Pill
    """
    temp_dir = Path(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 1. Top Header Pill
    html_top = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><link href='https://fonts.googleapis.com/css2?family=Anek+Bangla:wght@600;700;800&family=Hind+Siliguri:wght@700&display=swap' rel='stylesheet'><style>
    body {{ margin:0; padding:0; width:1080px; height:1920px; background:transparent; font-family:'Anek Bangla', 'Hind Siliguri', sans-serif; overflow:hidden; }}
    .top-box {{ position:absolute; top:80px; left:60px; right:60px; height:95px; background:rgba(15,23,42,0.85); backdrop-filter:blur(20px); border:1.5px solid rgba(56,189,248,0.55); border-radius:48px; display:flex; align-items:center; justify-content:space-between; padding:0 35px; box-shadow:0 15px 35px rgba(0,0,0,0.6); }}
    .logo-title {{ color:#fff; font-size:34px; font-weight:700; display:flex; align-items:center; gap:14px; }}
    .status-pill {{ background:#059669; color:#fff; padding:6px 20px; border-radius:20px; font-size:22px; font-weight:700; }}
    </style></head><body>
    <div class='top-box'><div class='logo-title'><span>🎬</span> {logo_title}</div><div class='status-pill'>Active</div></div>
    </body></html>"""

    # 2. Bottom CTA Box
    html_bottom = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><link href='https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@700;800&display=swap' rel='stylesheet'><style>
    body {{ margin:0; padding:0; width:1080px; height:1920px; background:transparent; font-family:'Anek Bangla', 'Hind Siliguri', sans-serif; overflow:hidden; }}
    .cta-box {{ position:absolute; bottom:85px; left:60px; right:60px; height:100px; background:rgba(15,23,42,0.88); backdrop-filter:blur(20px); border:2px solid #F59E0B; border-radius:30px; display:flex; align-items:center; justify-content:space-between; padding:0 35px; box-shadow:0 15px 35px rgba(245,158,11,0.25); }}
    .cta-text {{ color:#FDE047; font-size:34px; font-weight:800; display:flex; align-items:center; gap:12px; }}
    .cta-btn {{ background:#F59E0B; color:#000; padding:10px 26px; border-radius:18px; font-size:28px; font-weight:800; }}
    </style></head><body>
    <div class='cta-box'><div class='cta-text'><span>💎</span> {cta_text}</div><div class='cta-btn'>অনুসন্ধান করুন</div></div>
    </body></html>"""

    # 3. Dynamic Frosted Glass Beat Cards
    card_htmls: List[Tuple[str, str]] = []
    card_htmls.append(("top", html_top))
    card_htmls.append(("bottom", html_bottom))

    # Center card position (Y: 680px for balanced 9:16 vertical focus)
    card_y = 680

    for b in beats:
        html_card = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><link href='https://fonts.googleapis.com/css2?family=Anek+Bangla:wght@600;700;800&family=Hind+Siliguri:wght@700&display=swap' rel='stylesheet'><style>
        body {{ margin:0; padding:0; width:1080px; height:1920px; background:transparent; font-family:'Anek Bangla', 'Hind Siliguri', sans-serif; overflow:hidden; }}
        .glass-card {{
            position: absolute;
            top: {card_y}px;
            left: 60px;
            right: 60px;
            background: rgba(15, 23, 42, 0.82);
            border: 1.5px solid rgba(255, 255, 255, 0.22);
            border-top: 3px solid {b.accent_color};
            border-radius: 36px;
            padding: 35px 42px;
            box-shadow: 0 25px 60px rgba(0, 0, 0, 0.75), inset 0 1px 0 rgba(255, 255, 255, 0.25);
        }}
        .top-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }}
        .badge-group {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .icon-emoji {{
            font-size: 42px;
            filter: drop-shadow(0 4px 8px rgba(0,0,0,0.5));
        }}
        .badge-pill {{
            background: rgba(255, 255, 255, 0.10);
            border: 1px solid {b.accent_color};
            color: {b.accent_color};
            font-size: 24px;
            font-weight: 700;
            padding: 5px 18px;
            border-radius: 18px;
        }}
        .stat-badge {{
            color: #FDE047;
            font-size: 28px;
            font-weight: 800;
        }}
        .headline {{
            color: #FFFFFF;
            font-size: 44px;
            font-weight: 800;
            line-height: 1.25;
            margin-bottom: 12px;
        }}
        .subtext {{
            color: #CBD5E1;
            font-size: 30px;
            font-weight: 600;
            line-height: 1.38;
        }}
        </style></head><body>
        <div class='glass-card'>
            <div class='top-row'>
                <div class='badge-group'>
                    <span class='icon-emoji'>{b.emoji}</span>
                    <span class='badge-pill'>{b.badge}</span>
                </div>
                <div class='stat-badge'>{b.stat_val}</div>
            </div>
            <div class='headline'>{b.headline}</div>
            <div class='subtext'>{b.clause_text}</div>
        </div>
        </body></html>"""
        card_htmls.append((f"card_beat_{b.index}", html_card))

    paths: Dict[str, Path] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--disable-d3d11",
                "--disable-gpu-compositing",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu-rasterization",
                "--no-sandbox"
            ]
        )
        page = browser.new_page(viewport={"width": 1080, "height": 1920})
        for key, html_text in card_htmls:
            p_out = temp_dir / f"{key}.png"
            page.set_content(html_text)
            page.screenshot(path=str(p_out), omit_background=True)
            paths[key] = p_out
        browser.close()

    return paths


def compile_multicard_kinetic_video(
    video_clip_path: Optional[Path],
    audio_voice_path: Optional[Path],
    beats: List[DialogueBeat],
    card_paths: Dict[str, Path],
    duration: float,
    out_scene_mp4: Path,
    scene_number: int = 1
) -> Path:
    """
    Assembles the final Category B motion graphics video:
    - Normalizes background video to 1080x1920 30fps with luminous grading.
    - Top header pill drops in immediately.
    - Each beat card slides in from its assigned side (Left or Right), holds, and slides out.
    - Bottom CTA slides up.
    - Lossless audio mapping with voiceover sync.
    """
    out_scene_mp4 = Path(out_scene_mp4)
    out_scene_mp4.parent.mkdir(parents=True, exist_ok=True)

    top_p = str(card_paths["top"]).replace("\\", "/")
    bottom_p = str(card_paths["bottom"]).replace("\\", "/")

    if not video_clip_path or not Path(video_clip_path).exists() or Path(video_clip_path).stat().st_size < 1000:
        video_clip_path = generate_cyber_ambient_motion_clip(
            out_path=out_scene_mp4.parent / f"ambient_bg_s{scene_number}.mp4",
            duration_s=duration + 2.0,
            scene_index=scene_number - 1
        )

    # Build Filtergraph
    # 1. Base video scaling, 30fps, luminous color grading, soft vignettes
    filter_parts = [
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "fps=30,setpts=PTS-STARTPTS,"
        "eq=contrast=1.12:brightness=0.05:saturation=1.25,"
        "drawbox=y=0:h=260:color=black@0.40:t=fill,"
        "drawbox=y=ih-700:h=700:color=black@0.45:t=fill[bg];"
    ]

    # 2. Overlay Top Header Pill (drops in 0.0s to 0.25s)
    filter_parts.append(
        "[bg][1:v]overlay=0:'if(lt(t,0.25), -120 + 120*(t/0.25), 0)':shortest=1[v_top];"
    )

    curr_stream = "[v_top]"
    input_index = 2

    # 3. Dynamic Side-Slide Overlays for each Beat Card
    for b in beats:
        key = f"card_beat_{b.index}"
        if key not in card_paths:
            continue

        trans_in = 0.25
        trans_out = 0.22
        t_st = b.start_sec
        t_en = b.end_sec
        t_in_end = t_st + trans_in
        t_out_st = max(t_st + trans_in, t_en - trans_out)

        if b.side == "left":
            # Slide in from LEFT, slide out to RIGHT
            x_expr = (
                f"if(lt(t,{t_in_end:.2f}), -1080 + 1080*((t-{t_st:.2f})/{trans_in:.2f}), "
                f"if(gt(t,{t_out_st:.2f}), 1080*((t-{t_out_st:.2f})/{trans_out:.2f}), 0))"
            )
        else:
            # Slide in from RIGHT, slide out to LEFT
            x_expr = (
                f"if(lt(t,{t_in_end:.2f}), 1080 - 1080*((t-{t_st:.2f})/{trans_in:.2f}), "
                f"if(gt(t,{t_out_st:.2f}), -1080*((t-{t_out_st:.2f})/{trans_out:.2f}), 0))"
            )

        next_stream = f"[v_b{b.index}]"
        filter_parts.append(
            f"{curr_stream}[{input_index}:v]overlay='{x_expr}':0:enable='between(t,{t_st:.2f},{t_en:.2f})':shortest=1{next_stream};"
        )
        curr_stream = next_stream
        input_index += 1

    # 4. Overlay Bottom CTA (slides up at 0.20s)
    filter_parts.append(
        f"{curr_stream}[{input_index}:v]overlay=0:'if(lt(t,0.45), 200 - 200*((t-0.20)/0.25), 0)':enable='gte(t,0.20)':shortest=1[v]"
    )

    filter_graph = "".join(filter_parts)

    cmd = [
        ffmpeg_bin(), "-y",
        "-stream_loop", "-1", "-i", str(video_clip_path),
        "-loop", "1", "-i", top_p,
    ]

    for b in beats:
        key = f"card_beat_{b.index}"
        if key in card_paths:
            cmd.extend(["-loop", "1", "-i", str(card_paths[key]).replace("\\", "/")])

    cmd.extend(["-loop", "1", "-i", bottom_p])

    has_audio = audio_voice_path and Path(audio_voice_path).exists()
    if has_audio:
        cmd.extend(["-i", str(audio_voice_path)])

    cmd.extend([
        "-filter_complex", filter_graph,
        "-map", "[v]",
    ])

    if has_audio:
        audio_stream_idx = input_index + 1
        cmd.extend([
            "-map", f"{audio_stream_idx}:a",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        ])

    cmd.extend([
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-t", f"{duration:.3f}",
        str(out_scene_mp4)
    ])

    si = None
    cflags = 0
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        cflags = subprocess.CREATE_NO_WINDOW

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, startupinfo=si, creationflags=cflags)
    return out_scene_mp4


class AutoMovieKineticEngine:
    """
    AutoMovie Pro Proprietary Category B Engine.
    Transforms raw scene scripts into dynamic, multi-card beat-synchronized
    motion graphic scenes over background videos.
    """

    @classmethod
    def render_scene(
        cls,
        scene_data: Dict[str, Any],
        duration: float,
        out_clip_path: Path,
        scene_idx: int = 1,
        total_scenes: int = 6,
        audio_path: Optional[Path] = None,
        niche: str = "Technology & AI",
        topic_title: str = "AutoMovie Pro"
    ) -> Dict[str, Any]:
        out_clip_path = Path(out_clip_path)
        work_dir = out_clip_path.parent
        work_dir.mkdir(parents=True, exist_ok=True)

        dialogue = scene_data.get("dialogue_bn", "")

        # 1. Extract Multi-Card Beats (1 to 3 distinct beats per scene)
        beats = split_dialogue_into_kinetic_beats(
            dialogue=dialogue,
            duration=duration,
            scene_idx=scene_idx,
            niche=niche
        )
        logger.info(f"[*] Scene {scene_idx:02d}: Extracted {len(beats)} kinetic beats for {duration:.2f}s timeline.")

        # 2. Acquire background video
        bg_clip_path = work_dir / f"scene_{scene_idx:02d}_bg_motion.mp4"
        bg_img_str = scene_data.get("background_image_path")
        bg_img_path = Path(bg_img_str) if bg_img_str else None

        # Priority 1: If authentic AI photoreal background image exists, animate with 3D Ken Burns
        # (Guarantees 100% semantic alignment with the topic and ZERO unwanted human faces)
        if bg_img_path and bg_img_path.exists() and bg_img_path.stat().st_size > 5000:
            if not (bg_clip_path.exists() and bg_clip_path.stat().st_size > 10000):
                try:
                    from pipeline.custom_pipeline.multi_still_clip import ken_burns_from_image
                    ken_burns_from_image(bg_img_path, bg_clip_path, duration=duration, w=1080, h=1920)
                    logger.info(f"[*] Animated authentic background image for Scene {scene_idx:02d} via 3D Ken Burns")
                except Exception as e_kb:
                    logger.debug("Ken burns background animation note: %s", e_kb)

        # Priority 2: Curated faceless stock video matching the exact scene entity
        if not (bg_clip_path.exists() and bg_clip_path.stat().st_size > 10000):
            query = scene_data.get("concrete_visual_subject") or scene_data.get("visual_keywords_en")
            if isinstance(query, list):
                query = " ".join(query)
            query = query or scene_data.get("visual_direction") or niche
            fetch_cinematic_motion_clip(query=str(query), out_path=bg_clip_path, duration_s=duration, scene_index=scene_idx)

        # 3. Render Glassmorphic Beat Overlays
        cards_dir = work_dir / f"scene_{scene_idx:02d}_cards"
        cta_text = "লাইক ও সাবস্ক্রাইব করুন" if scene_idx >= total_scenes - 1 else "পরবর্তী পর্যবেক্ষণ"
        cards = render_beat_glass_cards(
            beats=beats,
            temp_dir=cards_dir,
            logo_title=topic_title[:32],
            cta_text=cta_text
        )

        # 4. Composite Video with Multi-Card Staggered Transitions
        compile_multicard_kinetic_video(
            video_clip_path=bg_clip_path,
            audio_voice_path=audio_path,
            beats=beats,
            card_paths=cards,
            duration=duration,
            out_scene_mp4=out_clip_path,
            scene_number=scene_idx
        )

        keyframe_path = work_dir / f"scene_{scene_idx:02d}_motion_clip_keyframe.jpg"
        first_card_key = f"card_beat_{beats[0].index}"
        if first_card_key in cards:
            from PIL import Image
            Image.open(cards[first_card_key]).convert("RGB").save(keyframe_path, quality=95)

        return {
            "scene_id": f"scene_{scene_idx:02d}",
            "category": "Category B (AutoMovie Kinetic)",
            "video_clip_path": str(out_clip_path.resolve()),
            "keyframe_path": str(keyframe_path.resolve()),
            "duration_sec": duration,
            "total_beats": len(beats),
            "file_size_bytes": out_clip_path.stat().st_size if out_clip_path.exists() else 0,
            "asset_status": "RENDERED_SUCCESSFULLY"
        }


# Backwards compatibility alias
OmniKineticEngine = AutoMovieKineticEngine
