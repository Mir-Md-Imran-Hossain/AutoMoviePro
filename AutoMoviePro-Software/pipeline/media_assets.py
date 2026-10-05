from __future__ import annotations

import base64
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


def generate_logo_pollinations(
    prompt: str,
    out_path: Path,
    *,
    width: int = 1024,
    height: int = 1024,
    api_key: str = "",
) -> Path:
    """Generate logo image via image provider chain (logo-style prompt wrapper)."""
    safe_prompt = (
        f"minimal modern app logo, flat vector, clean, no text overload, "
        f"square icon, high contrast, {prompt}"
    )
    return _ai_still_via_chain(
        safe_prompt,
        out_path,
        width=width,
        height=height,
        api_key=api_key,
        google_api_keys=[],
    )


def generate_product_still(
    product_name: str,
    element: str,
    out_path: Path,
    *,
    visual_prompt: str = "",
    width: int = 1080,
    height: int = 1920,
    api_key: str = "",
    google_api_keys: Optional[List[str]] = None,
) -> Path:
    """
    Product frame that MUST depict the named gadget.
    Priority: real product photos (GSMArena / brand CDN) → AI still.
    """
    element = (element or "product").strip().lower()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) Real product photography (exact device — not generic stock / hallucinated AI)
    try:
        if _fetch_real_product_photo(product_name, out_path):
            return out_path
    except Exception as exc:
        logger.warning("real product photo failed: %s", str(exc)[:160])

    identity = _product_identity_cues(product_name)
    beat = _element_shot_direction(element, product_name)
    base = (visual_prompt or "").strip()
    prompt = (
        f"Photoreal commercial product photo of the real {product_name}. "
        f"CRITICAL: show the actual {product_name} industrial design — {identity}. "
        f"Shot: {beat}. "
        f"{base} "
        f"Single hero product filling most of the frame, sharp focus, studio rim light, "
        f"no other phone brands, no watermark, no UI text overlays, no logo badges."
    )

    return _ai_still_via_chain(
        prompt,
        out_path,
        width=width,
        height=height,
        api_key=api_key,
        google_api_keys=google_api_keys or [],
    )


def _ai_still_via_chain(
    prompt: str,
    out_path: Path,
    *,
    width: int,
    height: int,
    api_key: str = "",
    google_api_keys: Optional[List[str]] = None,
) -> Path:
    """Walk IMAGE_PROVIDER_PRIORITY / purpose_caps image chain for AI stills."""
    try:
        from pipeline.purpose_caps import image_provider_chain

        chain = image_provider_chain()
    except Exception:
        chain = ["pollinations", "freetheai", "goblin", "huggingface"]

    last_err: Optional[Exception] = None
    for provider in chain:
        try:
            if provider == "goblin":
                from pipeline.goblin_image import goblin_generate_image

                return goblin_generate_image(
                    prompt, out_path, width=min(width, 1024), height=min(height, 1024)
                )
            if provider == "pollinations":
                return _pollinations_image(
                    prompt, out_path, width=width, height=height, api_key=api_key
                )
            if provider == "freetheai":
                from pipeline.freetheai_image import freetheai_generate_image

                return freetheai_generate_image(
                    prompt,
                    out_path,
                    size=(
                        f"{min(width, 1024)}x{min(height, 1024)}"
                        if width and height
                        else "1024x1024"
                    ),
                )
            if provider == "google":
                from pipeline.google_api_gate import circuit_is_open
                import os

                if circuit_is_open():
                    continue
                g_keys = [k for k in (google_api_keys or []) if (k or "").strip()]
                env_k = os.environ.get("GEMINI_API_KEY", "").strip()
                if env_k and env_k not in g_keys:
                    g_keys.append(env_k)
                for key in g_keys[:2]:
                    if _google_product_image(
                        key, prompt, out_path, width=width, height=height
                    ):
                        return out_path
                continue
            if provider == "huggingface":
                # Optional: HF image endpoints vary; skip quietly if not wired
                logger.debug("huggingface image provider not wired — skip")
                continue
            if provider == "agnes":
                logger.debug("agnes image skipped in still chain (video primary)")
                continue
        except Exception as exc:
            last_err = exc
            logger.warning("image provider %s failed: %s", provider, str(exc)[:160])
            continue

    # Absolute last resort: Pollinations even if not in chain
    try:
        return _pollinations_image(
            prompt, out_path, width=width, height=height, api_key=api_key
        )
    except Exception as exc:
        last_err = exc
    raise RuntimeError(f"all image providers failed: {last_err}")


def _slug_product(name: str) -> str:
    s = (name or "").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s


def _fetch_real_product_photo(product_name: str, out_path: Path) -> bool:
    """Download a real catalog photo of the named product if accessible, else gracefully return False."""
    slug = _slug_product(product_name)
    if not slug:
        return False

    urls: List[str] = []
    # If explicitly a known device slug in gadget niche
    pl = (product_name or "").lower()
    if any(k in pl for k in ("phone", "pixel", "galaxy", "iphone", "oneplus", "xiaomi")):
        urls.append(f"https://fdn2.gsmarena.com/vv/bigpic/{slug}.jpg")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    for url in urls:
        try:
            with httpx.Client(timeout=40.0, follow_redirects=True, headers=headers) as client:
                r = client.get(url)
                ctype = r.headers.get("content-type", "")
                if r.status_code >= 400 or "image" not in ctype or len(r.content) < 4000:
                    continue
                out_path.write_bytes(r.content)
                try:
                    from PIL import Image
                    import io

                    img = Image.open(io.BytesIO(r.content)).convert("RGB")
                    img.save(out_path.with_suffix(".png") if out_path.suffix.lower() == ".png" else out_path, quality=92)
                    if out_path.suffix.lower() == ".png":
                        img.save(out_path)
                except Exception:
                    pass
                if out_path.exists() and out_path.stat().st_size > 4000:
                    logger.info("Real product photo: %s", url[:90])
                    return True
        except Exception as exc:
            logger.debug("product url miss %s: %s", url[:60], exc)
    return False


def _product_identity_cues(product_name: str) -> str:
    p = (product_name or "").lower()
    if "oneplus" in p:
        return (
            "circular Hasselblad camera island on back, alert slider on side, "
            "premium glass back, OnePlus signature design language"
        )
    if "pixel" in p:
        return "horizontal camera bar on back, clean Google Pixel design, Matte finish"
    if "iphone" in p:
        return "Apple iPhone industrial design, Dynamic Island or notch as appropriate for model"
    if "galaxy" in p and "bud" not in p:
        return "Samsung Galaxy camera island, Contour Cut look, premium Samsung finish"
    if "nothing phone" in p or "nothing" in p:
        return "Nothing Phone Glyph LED light matrix on transparent back"
    if "bud" in p or "airpod" in p or "wf-" in p:
        return "exact wireless earbuds + charging case shape for this model"
    if "quest" in p:
        return "VR headset form factor with controllers vibe"
    if "gopro" in p or "osmo" in p:
        return "action camera body with lens module clearly visible"
    return f"exact retail design of {product_name}, recognizable silhouette and camera layout"


def _element_shot_direction(element: str, product_name: str) -> str:
    el = (element or "").lower()
    shots = {
        "intro": f"hero front 3/4 view of {product_name} on dark desk",
        "design": f"macro orbit details of {product_name} chassis, ports, buttons, finish",
        "display": f"{product_name} screen ON with colorful UI content, face-on",
        "camera": f"macro of {product_name} rear camera module only",
        "battery": f"{product_name} plugged into charger cable, charging glow",
        "sound": f"{product_name} earbuds / speakers close-up",
        "fit": f"earbuds of {product_name} in-ear fit close-up",
        "case": f"open charging case of {product_name}",
        "processor": f"{product_name} gaming performance metaphor with device in hand",
        "software": f"fingers using {product_name} on-screen UI",
        "price": f"retail box and {product_name} side by side",
        "pros_cons": f"{product_name} on review desk flat lay",
        "outro": f"final hero hold of {product_name}, soft spotlight",
    }
    return shots.get(el, f"close-up product photography of {product_name}")


def _pollinations_image(
    prompt: str,
    out_path: Path,
    *,
    width: int,
    height: int,
    api_key: str = "",
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Prefer free Pollinations URL first — keyed gen.pollinations often 401s on stale keys
    urls = [
        f"https://image.pollinations.ai/prompt/{quote(prompt)}"
        f"?width={width}&height={height}&nologo=true&model=flux",
    ]
    if api_key:
        urls.append(
            f"https://gen.pollinations.ai/image/{quote(prompt)}"
            f"?width={width}&height={height}&model=flux&key={api_key}",
        )

    last_err = None
    for url in urls:
        try:
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                r = client.get(url)
                r.raise_for_status()
                ctype = r.headers.get("content-type", "")
                if "image" not in ctype and len(r.content) < 2000:
                    raise RuntimeError(f"not an image: {ctype}")
                out_path.write_bytes(r.content)
                try:
                    from PIL import Image
                    import io

                    img = Image.open(io.BytesIO(r.content)).convert("RGB")
                    if out_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                        out_path = out_path.with_suffix(".png")
                    img.save(out_path)
                except Exception:
                    pass
                return out_path
        except Exception as exc:
            last_err = exc
            logger.warning("pollinations image failed: %s", exc)
    raise RuntimeError(f"product image generation failed: {last_err}")


def _google_product_image(
    api_key: str,
    prompt: str,
    out_path: Path,
    *,
    width: int,
    height: int,
) -> bool:
    """Best-effort Google Imagen 3 / 4 / Flash still via Google AI Studio / Google Pro."""
    try:
        from pipeline.google_media import generate_imagen_image

        res = generate_imagen_image(
            prompt,
            out_path,
            api_key,
            width=width,
            height=height,
        )
        if res and res.is_file() and res.stat().st_size > 2000:
            return True
    except Exception as exc:
        logger.debug("google_media generate_imagen_image attempt failed: %s", exc)

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return False

    models = [
        "gemini-2.5-flash-image",
        "gemini-3.1-flash-image-preview",
    ]
    client = genai.Client(api_key=api_key)
    for model in models:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )
            for cand in getattr(resp, "candidates", None) or []:
                for part in getattr(getattr(cand, "content", None), "parts", None) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline is not None and getattr(inline, "data", None):
                        data = inline.data
                        raw = base64.b64decode(data) if isinstance(data, str) else bytes(data)
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_bytes(raw)
                        return out_path.exists() and out_path.stat().st_size > 2000
        except Exception as exc:
            logger.debug("google image model %s: %s", model, exc)
    return False


def generate_intro_video(
    prompt: str,
    out_path: Path,
    *,
    agnes_keys: Optional[List[str]] = None,
    pollinations_key: str = "",
    duration_sec: float = 4.0,
    size: str = "1920x1080",
    ffmpeg_bin: str = "ffmpeg",
) -> Dict[str, Any]:
    """
    Intro video: try Agnes video API, fallback to Pollinations still → ffmpeg motion.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    agnes_keys = agnes_keys or []

    # Agnes keys — try free endpoint first (faster), then paid poll briefly
    for key in agnes_keys[:1]:
        key = (key or "").strip()
        if not key:
            continue
        try:
            path = _agnes_free_or_paid(key, prompt, out_path, max_poll=12)
            if path and path.exists() and path.stat().st_size > 5000:
                return {"path": str(path), "provider": "agnes"}
        except Exception as exc:
            logger.warning("agnes intro failed: %s", exc)

    # Pollinations slideshow fallback
    frames_dir = out_path.parent / "intro_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames: List[Path] = []
    for i in range(3):
        frame = frames_dir / f"frame_{i}.png"
        try:
            generate_logo_pollinations(
                f"{prompt}, cinematic intro frame {i+1}, dramatic lighting, gadget theme",
                frame,
                width=1280,
                height=720,
                api_key=pollinations_key,
            )
            frames.append(frame)
        except Exception as exc:
            logger.warning("intro frame %s failed: %s", i, exc)

    if not frames:
        # last resort solid color via ffmpeg
        _run(
            [
                ffmpeg_bin,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x0b1215:s={size}:d={duration_sec}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(out_path),
            ]
        )
        return {"path": str(out_path), "provider": "ffmpeg_fallback"}

    # Ken Burns-ish from images
    # Create short clips then concat
    clips = []
    per = max(1.0, duration_sec / max(1, len(frames)))
    for i, fr in enumerate(frames):
        clip = out_path.parent / f"intro_clip_{i}.mp4"
        _run(
            [
                ffmpeg_bin,
                "-y",
                "-loop",
                "1",
                "-i",
                str(fr),
                "-t",
                str(per),
                "-vf",
                f"scale={size.replace('x', ':')}:force_original_aspect_ratio=increase,crop={size.replace('x', ':')},zoompan=z='min(zoom+0.0015,1.08)':d=125:s={size}:fps=25",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ]
        )
        if clip.exists():
            clips.append(clip)
        else:
            _run(
                [
                    ffmpeg_bin,
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    str(fr),
                    "-t",
                    str(per),
                    "-vf",
                    f"scale={size.replace('x', ':')}",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(clip),
                ]
            )
            if clip.exists():
                clips.append(clip)

    if len(clips) == 1:
        clips[0].replace(out_path)
        return {"path": str(out_path), "provider": "pollinations"}

    lst = out_path.parent / "intro_concat.txt"
    lst.write_text("\n".join(f"file '{c.as_posix()}'" for c in clips), encoding="utf-8")
    _run(
        [
            ffmpeg_bin,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out_path),
        ]
    )
    return {"path": str(out_path), "provider": "pollinations"}


def generate_agnes_dialogue_clip(
    *,
    api_key: str = "",
    api_keys: Optional[List[str]] = None,
    product_name: str,
    element: str,
    visual_prompt: str,
    out_path: Path,
    narration_hint: str = "",
    size: str = "1080x1920",
    duration_hint: float = 5.0,
    image_url: str = "",
    max_poll: int = 36,
    override_prompt: str = "",
    niche: str = "",
    keyword_triggers: Optional[List[str]] = None,
    use_catalog_image: bool = True,
) -> Optional[Path]:
    """
    Generate a real moving video clip for ONE dialogue beat via Agnes Video V2.0.
    Rotates across api_keys on rate-limit / queue-full / auth failures.
    """
    keys: List[str] = []
    for k in api_keys or []:
        kk = (k or "").strip()
        if kk and kk not in keys:
            keys.append(kk)
    single = (api_key or "").strip()
    if single and single not in keys:
        keys.insert(0, single)
    if not keys:
        # Auto-resolve from environment and configured channels
        try:
            from pipeline.custom_pipeline.session_keys import _collect_numbered, _env_map
            env_keys = _collect_numbered(_env_map(), ["AGNES_API_KEY", "AGNES_API"], max_n=20)
            for ek in env_keys:
                if ek and ek not in keys:
                    keys.append(ek)
        except Exception:
            pass
        if not keys:
            for env_name in ("AGNES_API_KEY", "AGNES_API"):
                val = (os.environ.get(env_name) or "").strip()
                if val and val not in keys:
                    keys.append(val)
        if not keys:
            try:
                from app import db as store
                for ch in store.list_channels():
                    k = (ch.get("agnes_api") or "").strip()
                    if k and k not in keys:
                        keys.append(k)
            except Exception:
                pass
    if not keys:
        logger.warning("generate_agnes_dialogue_clip: No Agnes API keys available in params, env, or DB")
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)

    w, h = (int(x) for x in size.split("x"))
    # Agnes defaults ~1152x768; keep aspect, clamp to supported-ish sizes
    if h > w:  # portrait short
        width, height = 768, 1152
    else:
        width, height = 1152, 768

    fps = 24
    # Agnes reliable AV max ~10s; num_frames must be 8n+1 and <= 441
    from pipeline.dialogue_sync import (
        AGNES_MAX_SECONDS,
        AGNES_MIN_SECONDS,
        AGNES_TARGET_SECONDS,
    )

    capped = max(AGNES_MIN_SECONDS, min(float(duration_hint or AGNES_TARGET_SECONDS), AGNES_MAX_SECONDS))
    raw_frames = int(capped * fps)
    n = max(0, (raw_frames - 1) // 8)
    num_frames = min(441, 8 * n + 1)
    if num_frames < 49:
        num_frames = 49  # ~2s
    logger.info(
        "Agnes duration_hint=%.2fs → capped=%.2fs num_frames=%s (~%.2fs) keys=%s",
        float(duration_hint or 0),
        capped,
        num_frames,
        num_frames / fps,
        len(keys),
    )

    niche_mod = _niche_cinematic_modifiers(niche)
    keywords = [str(k).strip() for k in (keyword_triggers or []) if str(k).strip()]

    if (override_prompt or "").strip():
        from pipeline.prompt_engineering import agnes_generation_wrapper

        prompt = agnes_generation_wrapper(
            override_prompt.strip(),
            product_name=product_name,
            keywords=keywords,
            narration_hint=narration_hint,
            niche_mod=niche_mod,
        )
    else:
        from pipeline.prompt_engineering import agnes_generation_wrapper

        identity = _product_identity_cues(product_name)
        beat = _element_shot_direction(element, product_name)
        core = (
            f"Cinematic documentary B-roll of {product_name}. "
            f"Show {product_name} clearly ({identity}). Camera/motion: {beat}. "
            f"{visual_prompt}."
        )
        prompt = agnes_generation_wrapper(
            core,
            product_name=product_name,
            keywords=keywords,
            narration_hint=narration_hint,
            niche_mod=niche_mod,
        )

    from pipeline.prompt_engineering import AGNES_NEGATIVE

    negative = AGNES_NEGATIVE

    # Prefer image-to-video from real catalog URL (gadget niches)
    # BUT: action keywords need free motion — catalog stills often freeze into static hero
    action_kw = {str(k).lower() for k in (keyword_triggers or [])}
    needs_action = bool(
        action_kw
        & {
            "unboxing",
            "scroll",
            "scrolling",
            "charging",
            "open",
            "opening",
            "plug",
            "orbit",
            "reveal",
        }
    )
    if use_catalog_image and not image_url and not needs_action:
        image_url = _catalog_image_url(product_name)
    if needs_action and not image_url:
        # Force text-to-video so Agnes can animate the action
        image_url = ""
        logger.info("Agnes: action keywords %s → text-to-video (no catalog still)", sorted(action_kw & {
            "unboxing", "scroll", "scrolling", "charging", "open", "opening", "plug", "orbit", "reveal"
        }))
    if not use_catalog_image:
        image_url = image_url or ""

    for i, key in enumerate(keys[:2]):  # hard cap: never rotate through a long key list per scene
        if _agnes_budget_exhausted():
            logger.warning("Agnes scene budget exhausted before key %s — image fallback", i + 1)
            break
        path = _agnes_video(
            key,
            prompt,
            out_path,
            max_poll=max_poll,
            width=width,
            height=height,
            num_frames=num_frames,
            frame_rate=fps,
            image_url=image_url,
            negative_prompt=negative,
        )
        if path and path.exists() and path.stat().st_size > 8000:
            if i > 0:
                logger.info("Agnes succeeded with fallback key …%s (%s/%s)", key[-4:], i + 1, len(keys))
            # Keep Agnes native audio+video together for AV sync
            return path
        logger.warning(
            "Agnes key …%s failed (%s/%s) — trying next key",
            key[-4:],
            i + 1,
            len(keys),
        )
        time.sleep(3)
    return None


def _strip_to_video_only(path: Path) -> Path:
    """Remove Agnes audio track so only our TTS is ever heard."""
    import subprocess

    from pipeline.compose import ffmpeg_bin

    tmp = path.with_name(path.stem + "_silent" + path.suffix)
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-an",
        "-c:v",
        "copy",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 2000:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        tmp.replace(path)
        logger.info("Stripped Agnes audio → video-only: %s", path.name)
        return path
    # If strip fails, keep original but mux must still map TTS-only
    logger.warning("Could not strip Agnes audio from %s — mux must force TTS map", path.name)
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass
    return path


def _niche_cinematic_modifiers(niche: str) -> str:
    n = (niche or "").lower()
    if any(x in n for x in ("islam", "deen", "quran", "muslim")):
        return (
            "Warm soft golden ambient light, serene spiritual atmosphere, "
            "faceless metaphors only, no idols, respectful Islamic aesthetic."
        )
    if any(x in n for x in ("science", "physics", "chem", "space")):
        return (
            "Teal/cyan cinematic grade, macro lab metaphors, shallow DOF, "
            "high contrast scientific mystery mood."
        )
    if any(x in n for x in ("histor", "war", "civilization")):
        return (
            "Desaturated cinematic film look, textured period atmosphere, "
            "dramatic side light, documentary B-roll energy."
        )
    if any(x in n for x in ("myster", "horror", "unexplain", "secret")):
        return (
            "Dark teal green grade, eerie macro metaphors, locked objects, "
            "fire/chemical energy, cinematic mystery tension."
        )
    if any(x in n for x in ("gadget", "tech", "phone", "review")):
        return (
            "Premium product photography lighting, rim light, clean studio desk, "
            "sharp macro of the exact device."
        )
    return "Cinematic color grade, shallow depth of field, intentional camera motion."


def _catalog_image_url(product_name: str) -> str:
    """Public HTTPS catalog image suitable for image-to-video when in gadget niche."""
    pl = (product_name or "").lower()
    if not any(k in pl for k in ("phone", "pixel", "galaxy", "iphone", "oneplus", "nothing phone")):
        return ""
    if "oneplus 13" in pl:
        return "https://oasis.opstatics.com/content/dam/oasis/page/2024/global/phones/13/specs/13-blue.png"
    if "pixel 9a" in pl:
        return "https://fdn2.gsmarena.com/vv/bigpic/google-pixel-9a.jpg"
    if "nothing phone" in pl and "3" in pl:
        return "https://fdn2.gsmarena.com/vv/bigpic/nothing-phone-3.jpg"
    slug = _slug_product(product_name)
    if slug:
        return f"https://fdn2.gsmarena.com/vv/bigpic/{slug}.jpg"
    return ""


def _agnes_free_or_paid(api_key: str, prompt: str, out_path: Path, max_poll: int = 12) -> Optional[Path]:
    """Legacy helper used by intro generation."""
    return _agnes_video(api_key, prompt, out_path, max_poll=max_poll)


_LAST_AGNES_CREATE_TS = 0.0
# Per-scene create budget — prevents nested create×key×split×retry storms
_AGNES_SCENE_CREATES = 0
_AGNES_SCENE_BUDGET = 2


def reset_agnes_scene_budget(max_creates: int = 2) -> None:
    """Call at the start of each scene build (build_dialogue_clip)."""
    global _AGNES_SCENE_CREATES, _AGNES_SCENE_BUDGET
    _AGNES_SCENE_CREATES = 0
    _AGNES_SCENE_BUDGET = max(1, int(max_creates))


def _agnes_budget_exhausted() -> bool:
    return _AGNES_SCENE_CREATES >= _AGNES_SCENE_BUDGET


def _agnes_rate_limit_wait(min_gap_s: float = 55.0) -> None:
    """Space creates for all-day Agnes quota (default ~55–70s from system profile)."""
    global _LAST_AGNES_CREATE_TS
    try:
        from pipeline.system_profile import agnes_create_gap_sec

        min_gap_s = float(agnes_create_gap_sec())
    except Exception:
        min_gap_s = max(55.0, float(min_gap_s))
    try:
        from pipeline.agnes_cooldown import wait_create_gap

        wait_create_gap(min_gap_s, last_create_ts=_LAST_AGNES_CREATE_TS)
        return
    except Exception:
        pass
    if _LAST_AGNES_CREATE_TS <= 0:
        return
    gap = min_gap_s - (time.time() - _LAST_AGNES_CREATE_TS)
    if gap > 0:
        logger.info("Agnes rate-limit pacing: waiting %.1fs", gap)
        try:
            from pipeline.live_activity import log as live_log

            live_log("media", f"Agnes pacing {gap:.0f}s", api="agnes", action="rate_limit")
        except Exception:
            pass
        time.sleep(gap)


def _agnes_video(
    api_key: str,
    prompt: str,
    out_path: Path,
    max_poll: int = 36,
    *,
    width: int = 1152,
    height: int = 768,
    num_frames: int = 121,
    frame_rate: int = 24,
    image_url: str = "",
    negative_prompt: str = "",
) -> Optional[Path]:
    """
    Agnes Video V2.0 async API:
      POST https://apihub.agnes-ai.com/v1/videos
      GET  https://apihub.agnes-ai.com/agnesapi?video_id=...
    """
    global _LAST_AGNES_CREATE_TS
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": "agnes-video-v2.0",
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_frames": num_frames,
        "frame_rate": frame_rate,
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    if image_url:
        payload["image"] = image_url

    # Single create endpoint only — never fan-out to alternate URLs (API misuse)
    create_url = "https://apihub.agnes-ai.com/v1/videos"

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        global _AGNES_SCENE_CREATES
        try:
            from pipeline.agnes_cooldown import (
                is_in_cooldown,
                looks_like_rate_limit,
                arm_cooldown,
                wait_out_cooldown_or_abort,
                clear_cooldown,
            )

            if is_in_cooldown():
                try:
                    from pipeline.live_activity import is_cancel_requested

                    cancel = is_cancel_requested
                except Exception:
                    cancel = None
                ok_wait = wait_out_cooldown_or_abort(cancel_check=cancel)
                if not ok_wait:
                    return None
        except Exception:
            looks_like_rate_limit = lambda _e: False  # type: ignore
            arm_cooldown = None  # type: ignore
            clear_cooldown = None  # type: ignore

        if _agnes_budget_exhausted():
            logger.warning(
                "Agnes scene budget exhausted (%s/%s) — skip create",
                _AGNES_SCENE_CREATES,
                _AGNES_SCENE_BUDGET,
            )
            return None

        video_id = None
        task_id = None
        last_err = ""
        # ONE create only — never retry-create after timeout (wastes paid jobs)
        _agnes_rate_limit_wait(55.0)
        try:
            _LAST_AGNES_CREATE_TS = time.time()
            _AGNES_SCENE_CREATES += 1
            try:
                from pipeline.live_activity import log as live_log

                live_log(
                    "media",
                    f"Agnes create (scene budget {_AGNES_SCENE_CREATES}/{_AGNES_SCENE_BUDGET})",
                    api="agnes",
                    action="create",
                )
            except Exception:
                pass
            r = client.post(create_url, headers=headers, json=payload)
            if r.status_code in (429, 503, 502):
                last_err = f"{create_url} -> {r.status_code} {r.text[:220]}"
                logger.warning("agnes create rate-limited: %s", last_err)
                if arm_cooldown:
                    arm_cooldown(reason=last_err[:160])
                return None
            if r.status_code >= 400:
                last_err = f"{create_url} -> {r.status_code} {r.text[:220]}"
                logger.warning("agnes create failed: %s", last_err)
                # One image-less retry only if image rejected (same budget slot already used)
                if "image" in (r.text or "").lower() and payload.get("image"):
                    payload.pop("image", None)
                    if not _agnes_budget_exhausted():
                        _AGNES_SCENE_CREATES += 1
                        r = client.post(create_url, headers=headers, json=payload)
                        if r.status_code >= 400:
                            return None
                    else:
                        return None
                else:
                    return None
            data = r.json()
            # Prefer opaque video_id for agnesapi; keep task_id for /v1/videos/{task_id}
            video_id = (
                data.get("video_id")
                or (data.get("data") or {}).get("video_id")
            )
            task_id = (
                data.get("task_id")
                or data.get("id")
                or (data.get("data") or {}).get("task_id")
                or (data.get("data") or {}).get("id")
            )
            if not video_id and task_id and str(task_id).startswith("video_"):
                video_id = task_id
            if video_id or task_id:
                logger.info(
                    "Agnes task created video_id=%s task_id=%s",
                    video_id,
                    task_id,
                )
                if clear_cooldown:
                    try:
                        clear_cooldown()
                    except Exception:
                        pass
            else:
                last_err = f"no video_id/task_id in {data}"
        except Exception as exc:
            last_err = str(exc)
            logger.warning("agnes create exception: %s", exc)
            return None

        if not video_id and not task_id:
            logger.error("Agnes create failed completely: %s", last_err)
            return None

        video_url = None
        # Agnes inference alone often ~60s; allow up to ~4 min (never abandon early)
        poll_cap = max(24, min(int(max_poll or 36), 48))
        for i in range(poll_cap):
            time.sleep(5 if i < 12 else 6)
            # ONLY poll working endpoints:
            #  - agnesapi?video_id=...  (works with encoded video_id)
            #  - /v1/videos/{task_id}   (task_* id — NOT the video_ id)
            poll_urls: List[str] = []
            if video_id:
                poll_urls.append(
                    f"https://apihub.agnes-ai.com/agnesapi?video_id={video_id}"
                )
            if task_id and str(task_id).startswith("task_"):
                poll_urls.append(f"https://apihub.agnes-ai.com/v1/videos/{task_id}")
            if not poll_urls and task_id:
                poll_urls.append(f"https://apihub.agnes-ai.com/v1/videos/{task_id}")

            pdata = None
            for poll_url in poll_urls:
                try:
                    pr = client.get(poll_url, headers=headers)
                    if pr.status_code >= 400:
                        continue
                    pdata = pr.json()
                    break  # one successful poll body per tick — no duplicate fan-out
                except Exception:
                    continue
            if not isinstance(pdata, dict):
                logger.info("Agnes polling %s/%s (no body) ...", i + 1, poll_cap)
                continue

            status = str(
                pdata.get("status")
                or pdata.get("internal_status")
                or (pdata.get("data") or {}).get("status")
                or ""
            ).lower()
            progress = pdata.get("progress") or pdata.get("internal_progress") or 0
            video_url = (
                pdata.get("url")
                or pdata.get("video_url")
                or (pdata.get("data") or {}).get("url")
                or (pdata.get("data") or {}).get("video_url")
                or (pdata.get("output") or {}).get("url")
            )
            if video_url:
                break
            if status in {"failed", "error"} or pdata.get("error"):
                logger.error("Agnes task failed: %s", pdata.get("error") or pdata)
                return None
            if i % 3 == 0:
                logger.info(
                    "Agnes polling %s/%s status=%s progress=%s",
                    i + 1,
                    poll_cap,
                    status or "?",
                    progress,
                )

        if not video_url:
            logger.error(
                "Agnes poll timeout video_id=%s task_id=%s (waited ~%ss)",
                video_id,
                task_id,
                poll_cap * 5,
            )
            return None
        media = client.get(video_url)
        media.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(media.content)
        if out_path.stat().st_size < 8000:
            logger.error("Agnes downloaded file too small")
            return None
        logger.info("Agnes clip saved: %s (%s bytes)", out_path.name, out_path.stat().st_size)
        return out_path


def render_high_aesthetic_thumbnail(
    title: str,
    subject: str,
    out_path: Path,
    *,
    niche: str = "",
    logo_path: Optional[Path] = None,
) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    out_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = 1280, 720
    n = (niche or subject or "").lower()

    # Determine theme colors based on niche
    if any(k in n for k in ("islam", "deen", "quran")):
        c1, c2, accent = (8, 28, 20), (18, 56, 42), (255, 215, 0)
        badge = "ISLAMIC REFLECTIONS"
    elif any(k in n for k in ("financ", "money", "invest", "crypto", "wealth")):
        c1, c2, accent = (8, 16, 32), (18, 36, 68), (0, 212, 255)
        badge = "FINANCIAL BLUEPRINT"
    elif any(k in n for k in ("health", "fitness", "sleep", "diet")):
        c1, c2, accent = (10, 26, 18), (20, 52, 36), (82, 183, 136)
        badge = "HEALTH & VITALITY"
    elif any(k in n for k in ("space", "science", "physics", "astronomy")):
        c1, c2, accent = (10, 6, 26), (26, 14, 56), (181, 23, 158)
        badge = "SCIENCE DOCUMENTARY"
    elif any(k in n for k in ("motivat", "habit", "mindset", "discipline")):
        c1, c2, accent = (24, 14, 8), (54, 28, 14), (247, 127, 0)
        badge = "MASTER THE MINDSET"
    elif any(k in n for k in ("myster", "crime", "unexplain", "secret")):
        c1, c2, accent = (18, 10, 12), (40, 16, 20), (230, 57, 70)
        badge = "COLD CASE INVESTIGATION"
    elif any(k in n for k in ("gadget", "tech", "phone", "review")):
        c1, c2, accent = (12, 16, 26), (24, 34, 54), (255, 183, 3)
        badge = "HARDWARE EVALUATION"
    else:
        c1, c2, accent = (14, 20, 28), (28, 38, 54), (46, 196, 182)
        badge = "SPECIAL DOCUMENTARY"

    # 1. Base gradient
    base = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(base)
    for y in range(h):
        ratio = y / float(h)
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b, 255))

    # 2. Ambient radial glow on top-right quadrant
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    gx, gy = int(w * 0.78), int(h * 0.35)
    for rad in range(380, 0, -15):
        alpha = int((1.0 - rad / 380.0) * 45)
        glow_draw.ellipse(
            [gx - rad, gy - rad, gx + rad, gy + rad],
            fill=(accent[0], accent[1], accent[2], alpha),
        )
    base = Image.alpha_composite(base, glow)
    draw = ImageDraw.Draw(base)

    # 3. Framing corners / cinematic brackets
    bw, blen = 4, 60
    # Top-left bracket
    draw.line([(40, 40), (40 + blen, 40)], fill=accent, width=bw)
    draw.line([(40, 40), (40, 40 + blen)], fill=accent, width=bw)
    # Top-right bracket
    draw.line([(w - 40, 40), (w - 40 - blen, 40)], fill=accent, width=bw)
    draw.line([(w - 40, 40), (w - 40, 40 + blen)], fill=accent, width=bw)
    # Bottom-left bracket
    draw.line([(40, h - 40), (40 + blen, h - 40)], fill=accent, width=bw)
    draw.line([(40, h - 40), (40, h - 40 - blen)], fill=accent, width=bw)
    # Bottom-right bracket
    draw.line([(w - 40, h - 40), (w - 40 - blen, h - 40)], fill=accent, width=bw)
    draw.line([(w - 40, h - 40), (w - 40, h - 40 - blen)], fill=accent, width=bw)

    # 4. Resolve font
    font_title = None
    font_badge = None
    font_sub = None
    font_candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/tahomabd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for fc in font_candidates:
        if Path(fc).is_file():
            try:
                font_title = ImageFont.truetype(fc, 56)
                font_badge = ImageFont.truetype(fc, 24)
                font_sub = ImageFont.truetype(fc, 32)
                break
            except Exception:
                continue
    if not font_title:
        font_title = ImageFont.load_default()
        font_badge = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # 5. Draw Badge Pill
    bx, by = 80, 85
    b_text = f"  {badge}  "
    draw.rounded_rectangle([bx, by, bx + 360, by + 42], radius=8, fill=(accent[0], accent[1], accent[2], 40), outline=accent, width=2)
    draw.text((bx + 18, by + 8), b_text, fill=accent, font=font_badge)

    # 6. Word wrap Title cleanly (max 3 lines)
    words = title.replace(":", " —").split()
    lines = []
    curr = []
    for word in words:
        curr.append(word)
        if len(" ".join(curr)) > 30:
            lines.append(" ".join(curr[:-1]))
            curr = [word]
    if curr:
        lines.append(" ".join(curr))
    lines = lines[:3]

    ty = 170
    for line in lines:
        # Drop shadow
        draw.text((83, ty + 3), line, fill=(0, 0, 0, 220), font=font_title)
        draw.text((80, ty), line, fill=(255, 255, 255), font=font_title)
        ty += 70

    # 7. Highlight entity / subject bar
    if subject and subject.lower() not in title.lower():
        sub_text = f"FOCUS: {subject.upper()[:45]}"
        draw.text((82, ty + 25), sub_text, fill=(0, 0, 0, 200), font=font_sub)
        draw.text((80, ty + 23), sub_text, fill=accent, font=font_sub)

    # 8. Logo placement in bottom-right corner
    if logo_path and Path(logo_path).is_file():
        try:
            logo = Image.open(logo_path).convert("RGBA").resize((130, 130))
            base.paste(logo, (w - 190, h - 190), logo)
        except Exception:
            pass

    final_rgb = base.convert("RGB")
    final_rgb.save(out_path, quality=92)
    return out_path


def generate_thumbnail(
    title: str,
    gadget: str,
    out_path: Path,
    *,
    pollinations_key: str = "",
    logo_path: Optional[Path] = None,
    google_api_keys: Optional[List[str]] = None,
    niche: str = "",
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = (
        f"YouTube thumbnail hero product photo of {gadget}, bold cinematic lighting, "
        f"the exact {gadget} clearly visible and large in frame, high contrast, no watermark"
    )
    generated = False
    try:
        generate_product_still(
            gadget,
            "intro",
            out_path,
            visual_prompt=prompt,
            width=1280,
            height=720,
            api_key=pollinations_key,
            google_api_keys=google_api_keys or [],
        )
        if out_path.exists() and out_path.stat().st_size > 5000:
            generated = True
            if logo_path and logo_path.exists():
                try:
                    from PIL import Image

                    base = Image.open(out_path).convert("RGBA")
                    logo = Image.open(logo_path).convert("RGBA").resize((140, 140))
                    base.paste(logo, (base.width - 160, base.height - 160), logo)
                    base.convert("RGB").save(out_path)
                except Exception:
                    pass
    except Exception:
        generated = False

    if not generated or not out_path.exists() or out_path.stat().st_size < 5000:
        render_high_aesthetic_thumbnail(
            title=title,
            subject=gadget,
            out_path=out_path,
            niche=niche,
            logo_path=logo_path,
        )

    return out_path


def _run(cmd: List[str]) -> None:
    import subprocess

    subprocess.run(cmd, check=False, capture_output=True)
