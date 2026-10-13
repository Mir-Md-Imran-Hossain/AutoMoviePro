# -*- coding: utf-8 -*-
"""
Omni Video Motion Studio (Industrial Clip Engine)
------------------------------------------------
Architecture:
1. Video Clip Fetching:
   - Primary: Google Veo (Veo-3.1 / Veo-2) via google.genai API
   - Secondary: Agnes Video API (apihub.agnes-ai.com)
   - Real-world Fallback: High-resolution Cinematic 4K/HD 9:16 vertical stock video clips
2. Dynamic Staggered Kinetic Typography Overlays:
   - Top Header Pill (Sliding from top)
   - Left Category Badge (Sliding from left)
   - Dynamic Narrative/Feature Card (Sliding from right)
   - Bottom Action CTA Box with Golden Button (Sliding from bottom)
3. Audio Mastery:
   - Studio Google TTS (Charon / Kore)
   - Sidechain ducked ambient background score
"""
import os
import sys
import time
import requests
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.sync_api import sync_playwright

FFMPEG_EXE = r"E:\All Project\AutoMovie_Pro_SAAS_Final_Update\AutoMoviePro-Software\ffmpeg-8.1.1-full_build\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
ENV_PATH = Path(r"E:\All Project\AutoMovie_Pro_SAAS_Final_Update\AutoMoviePro-Software\.env")


def get_env_map() -> Dict[str, str]:
    res = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                res[k.strip()] = v.strip()
    return res


def fetch_cinematic_motion_clip(query: str, out_path: Path, duration_s: int = 6) -> Optional[Path]:
    """
    Downloads authentic vertical 9:16 cinematic video clip.
    Tries Google Veo / Agnes, then high-res Pexels 1080x1920 video clips.
    """
    env = get_env_map()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Try Google Veo if API key quota allows
    google_keys = [v for k, v in env.items() if "GOOGLE" in k and v.startswith("AIza")]
    if google_keys:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=google_keys[0])
            op = client.models.generate_videos(
                model="veo-3.1-lite-generate-preview",
                prompt=f"{query}, cinematic high production vertical 9:16 portrait video",
                config=types.GenerateVideosConfig(aspect_ratio="9:16", duration_seconds=min(duration_s, 6), number_of_videos=1)
            )
            # Wait up to 30s
            t0 = time.time()
            while not op.done and time.time() - t0 < 30:
                time.sleep(5)
                op = client.operations.get(op)
            if op.done and getattr(op, "response", None):
                vids = getattr(op.response, "generated_videos", [])
                if vids and getattr(vids[0], "video", None):
                    client.files.download(file=vids[0].video, destination=str(out_path))
                    if out_path.exists() and out_path.stat().st_size > 10000:
                        return out_path
        except Exception:
            pass

    # 2. Try Agnes Video API
    agnes_keys = [v for k, v in env.items() if "AGNES" in k and "KEY" in k and v.strip()]
    if agnes_keys:
        try:
            base_url = env.get("AGNES_API_BASE_URL", "https://apihub.agnes-ai.com/v1")
            payload = {
                "model": "agnes-video-2.5-flash",
                "prompt": query,
                "mode": "std",
                "aspect_ratio": "9:16"
            }
            r = requests.post(f"{base_url}/videos", json=payload, headers={"Authorization": f"Bearer {agnes_keys[0]}"}, timeout=8)
            if r.status_code == 200:
                d = r.json()
                vurl = d.get("url") or (d.get("data") or {}).get("url")
                if vurl:
                    with requests.get(vurl, stream=True, timeout=30) as vr:
                        with open(out_path, "wb") as f:
                            for chunk in vr.iter_content(8192):
                                f.write(chunk)
                    if out_path.exists() and out_path.stat().st_size > 10000:
                        return out_path
        except Exception:
            pass

    # 3. High-Res Cinematic HD Stock Engine (Pexels Vertical Clip)
    pexels_key = env.get("PEXELS_API_KEY_1", "") or env.get("PEXELS_API_KEY", "")
    if pexels_key:
        try:
            # Semantic keyword enrichment for ultra-relevant tech, AI, creator & agency background visuals
            # Semantic keyword safety guard for 100% relevant tech, video editing & AI visuals
            q_lower = query.lower()
            if any(w in q_lower for w in ["video", "ভিডিও", "এডিটিং", "editing", "timeline"]):
                search_term = "video editing screen workspace portrait"
            elif any(w in q_lower for w in ["script", "রিসার্চ", "স্ক্রিপ্ট", "research", "topic"]):
                search_term = "typing computer screen modern tech portrait"
            elif any(w in q_lower for w in ["soundwave", "audio", "voice", "মাইক্রোফোন", "ভয়েস", "ডাবিং"]):
                search_term = "microphone sound recording studio portrait"
            elif any(w in q_lower for w in ["creator", "youtube", "reels", "ক্রিয়েটর", "ফেসবুক", "চ্যানেল"]):
                search_term = "content creator camera studio lights portrait"
            elif any(w in q_lower for w in ["business", "manager", "agency", "এজেন্সি", "মার্কেটিং", "সেলস"]):
                search_term = "business marketing office technology portrait"
            elif any(w in q_lower for w in ["income", "money", "dollar", "টাকা", "আয়", "প্যাসিভ"]):
                search_term = "financial chart analytics computer screen portrait"
            elif any(w in q_lower for w in ["mobile", "phone", "ক্যাপচা", "ফোন", "রিমোট"]):
                search_term = "smartphone app screen interaction portrait"
            elif any(w in q_lower for w in ["robot", "ai", "automation", "কম্পিউটার", "অটোপাইলট"]):
                search_term = "artificial intelligence futuristic glowing network portrait"
            else:
                search_term = "modern computer workspace technology portrait"

            r = requests.get(
                f"https://api.pexels.com/videos/search?query={search_term}&orientation=portrait&per_page=6",
                headers={"Authorization": pexels_key},
                timeout=12
            )
            if r.status_code == 200:
                vids = r.json().get("videos", [])
                if vids:
                    # Choose best vertical resolution (1080x1920 preferred)
                    best_file = None
                    for v_item in vids:
                        for f in v_item.get("video_files", []):
                            if f.get("width") == 1080 and f.get("height") == 1920:
                                best_file = f
                                break
                        if best_file:
                            break
                    if not best_file and vids:
                        files = vids[0].get("video_files", [])
                        if files:
                            best_file = files[0]

                    if best_file and best_file.get("link"):
                        with requests.get(best_file["link"], stream=True, timeout=30) as vr:
                            with open(out_path, "wb") as f:
                                for chunk in vr.iter_content(8192):
                                    f.write(chunk)
                        if out_path.exists() and out_path.stat().st_size > 10000:
                            return out_path
        except Exception:
            pass

    return None


def render_scene_kinetic_overlays(
    badge_text: str,
    headline: str,
    subtext: str,
    cta_text: str = "অফার ৳৩,৯৯৯ (রেগুলার ৳১০,০০০)",
    temp_dir: Path = None,
    stat_label: str = "সফটওয়্যার অটোপাইলট",
    stat_val: str = "২৪/৭ ফুল অটোমেশন"
) -> Dict[str, Path]:
    """
    Renders 5 transparent graphic cards with Bengali typography for staggered animation.
    """
    temp_dir = Path(temp_dir or Path("./temp_cards"))
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 1. Top Header
    html_top = """<!DOCTYPE html><html><head><meta charset='utf-8'><link href='https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@700&display=swap' rel='stylesheet'><style>
    body { margin:0; padding:0; width:1080px; height:1920px; background:transparent; font-family:'Hind Siliguri', sans-serif; overflow:hidden; }
    .top-box { position:absolute; top:80px; left:60px; right:60px; height:100px; background:rgba(15,23,42,0.92); border:2px solid rgba(56,189,248,0.6); border-radius:50px; display:flex; align-items:center; justify-content:space-between; padding:0 40px; box-shadow:0 15px 35px rgba(0,0,0,0.6); }
    .logo-title { color:#fff; font-size:38px; font-weight:700; display:flex; align-items:center; gap:15px; }
    .status-pill { background:#059669; color:#fff; padding:8px 22px; border-radius:25px; font-size:24px; font-weight:700; }
    </style></head><body>
    <div class='top-box'><div class='logo-title'><span>🎬</span> AutoMovie Pro — Official AI Studio</div><div class='status-pill'>Active</div></div>
    </body></html>"""

    # 2. Left Badge
    html_left = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><link href='https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@700;800&display=swap' rel='stylesheet'><style>
    body {{ margin:0; padding:0; width:1080px; height:1920px; background:transparent; font-family:'Hind Siliguri', sans-serif; overflow:hidden; }}
    .badge {{ position:absolute; top:220px; left:60px; background:linear-gradient(135deg, #EA580C, #C2410C); border:2px solid #FDBA74; border-radius:30px; padding:18px 36px; color:#fff; font-size:42px; font-weight:800; display:flex; align-items:center; gap:16px; box-shadow:0 12px 30px rgba(234,88,12,0.5); }}
    </style></head><body>
    <div class='badge'><span>⚡</span> {badge_text}</div>
    </body></html>"""

    # 2b. Right Mini-Badge / Floating Stat Card (Fills mid-screen nicely without clutter)
    html_mid = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><link href='https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@600;700;800&display=swap' rel='stylesheet'><style>
    body {{ margin:0; padding:0; width:1080px; height:1920px; background:transparent; font-family:'Hind Siliguri', sans-serif; overflow:hidden; }}
    .stat-card {{ position:absolute; top:350px; right:60px; background:rgba(30,41,59,0.92); border:2px solid #38BDF8; border-radius:28px; padding:16px 30px; display:flex; align-items:center; gap:14px; box-shadow:0 15px 35px rgba(0,0,0,0.6); }}
    .stat-icon {{ font-size:36px; }}
    .stat-label {{ color:#94A3B8; font-size:22px; font-weight:600; }}
    .stat-val {{ color:#38BDF8; font-size:26px; font-weight:800; }}
    </style></head><body>
    <div class='stat-card'>
        <div class='stat-icon'>🚀</div>
        <div>
            <div class='stat-label'>{stat_label}</div>
            <div class='stat-val'>{stat_val}</div>
        </div>
    </div>
    </body></html>"""

    # 3. Dynamic Center Message Card
    html_center = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><link href='https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@600;700;800&display=swap' rel='stylesheet'><style>
    body {{ margin:0; padding:0; width:1080px; height:1920px; background:transparent; font-family:'Hind Siliguri', sans-serif; overflow:hidden; }}
    .message-card {{ position:absolute; bottom:280px; left:60px; right:60px; background:rgba(15,23,42,0.95); border:3px solid #6366F1; border-radius:40px; padding:35px 45px; box-shadow:0 20px 50px rgba(0,0,0,0.8); }}
    .headline {{ color:#FFFFFF; font-size:50px; font-weight:800; line-height:1.3; margin-bottom:15px; }}
    .subtext {{ color:#CBD5E1; font-size:34px; font-weight:600; line-height:1.4; }}
    </style></head><body>
    <div class='message-card'>
    <div class='headline'>{headline}</div>
    <div class='subtext'>{subtext}</div>
    </div>
    </body></html>"""

    # 4. Bottom CTA
    html_bottom = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><link href='https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@700;800&display=swap' rel='stylesheet'><style>
    body {{ margin:0; padding:0; width:1080px; height:1920px; background:transparent; font-family:'Hind Siliguri', sans-serif; overflow:hidden; }}
    .cta-box {{ position:absolute; bottom:90px; left:60px; right:60px; height:110px; background:linear-gradient(90deg, #1E1B4B, #0F172A); border:2px solid #F59E0B; border-radius:30px; display:flex; align-items:center; justify-content:space-between; padding:0 40px; box-shadow:0 15px 35px rgba(245,158,11,0.3); }}
    .cta-text {{ color:#FDE047; font-size:40px; font-weight:800; display:flex; align-items:center; gap:15px; }}
    .cta-btn {{ background:#F59E0B; color:#000; padding:12px 30px; border-radius:20px; font-size:32px; font-weight:800; }}
    </style></head><body>
    <div class='cta-box'><div class='cta-text'><span>💎</span> {cta_text}</div><div class='cta-btn'>অর্ডার করুন</div></div>
    </body></html>"""

    paths = {
        "top": temp_dir / "card_top.png",
        "left": temp_dir / "card_left.png",
        "mid": temp_dir / "card_mid.png",
        "center": temp_dir / "card_center.png",
        "bottom": temp_dir / "card_bottom.png"
    }

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1920})
        for k, content in [("top", html_top), ("left", html_left), ("mid", html_mid), ("center", html_center), ("bottom", html_bottom)]:
            page.set_content(content)
            page.screenshot(path=str(paths[k]), omit_background=True)
        browser.close()

    return paths


def compile_kinetic_scene_video(
    video_clip_path: Path,
    audio_voice_path: Path,
    cards: Dict[str, Path],
    duration: float,
    out_scene_mp4: Path
) -> Path:
    """
    Composites dynamic animated graphic cards over live motion clip.
    Staggered transitions:
    - Top pill drops down from top (t=0.2..0.8)
    - Left badge enters from left (t=0.7..1.3)
    - Right stat badge glides in from right (t=1.3..1.9)
    - Center message card glides in from right (t=1.8..2.4)
    - Bottom CTA slides up from bottom (t=2.6..3.2)
    Safety Guard: Continuous subtle background motion (0.0004 slow zoom) ensures zero frozen frame.
    """
    out_scene_mp4 = Path(out_scene_mp4)
    top_p = str(cards["top"]).replace("\\", "/")
    left_p = str(cards["left"]).replace("\\", "/")
    mid_p = str(cards["mid"]).replace("\\", "/")
    center_p = str(cards["center"]).replace("\\", "/")
    bottom_p = str(cards["bottom"]).replace("\\", "/")

    total_f = int(duration * 25)
    filter_graph = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        f"zoompan=z='min(zoom+0.0004,1.10)':d={total_f}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=25,"
        "drawbox=y=0:color=black@0.35:width=iw:height=ih:t=fill[bg];"
        f"[bg][1:v]overlay=0:'if(lt(t,0.8), -150 + 150*((t-0.2)/0.6), 0)':enable='gte(t,0.2)'[v1];"
        f"[v1][2:v]overlay='if(lt(t,1.3), -600 + 600*((t-0.7)/0.6), 0)':0:enable='gte(t,0.7)'[v2];"
        f"[v2][3:v]overlay='if(lt(t,1.9), 600 - 600*((t-1.3)/0.6), 0)':0:enable='gte(t,1.3)'[v3];"
        f"[v3][4:v]overlay='if(lt(t,2.4), 600 - 600*((t-1.8)/0.6), 0)':0:enable='gte(t,1.8)'[v4];"
        f"[v4][5:v]overlay=0:'if(lt(t,3.2), 200 - 200*((t-2.6)/0.6), 0)':enable='gte(t,2.6)'[v]"
    )

    cmd = [
        FFMPEG_EXE, "-y",
        "-stream_loop", "-1", "-i", str(video_clip_path),
        "-i", top_p,
        "-i", left_p,
        "-i", mid_p,
        "-i", center_p,
        "-i", bottom_p,
        "-i", str(audio_voice_path),
        "-filter_complex", filter_graph,
        "-map", "[v]",
        "-map", "6:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration),
        str(out_scene_mp4)
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return out_scene_mp4
