"""Detailed media prompts — labeled, priority-ordered, never short stubs.

Priority order (kept first so API truncations never drop identity):
  1) Subject lock (product UI OR character — never force faces on tool demos)
  2) Camera angle
  3) Lighting
  4) Background / environment
  5) Spoken beat / scene intent (AV sync with narration)
  6) Visual description body
  7) Motion / duration / art style
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pipeline.custom_pipeline.visual_subject_policy import (
    SUBJECT_BROLL,
    SUBJECT_HANDS_UI,
    SUBJECT_PRESENTER,
    SUBJECT_PRODUCT_UI,
    character_allowed,
    hands_ui_subject_block,
    infer_visual_subject,
    negative_for_subject,
    product_ui_subject_block,
    strip_face_language,
)


NEGATIVE_IMAGE = (
    "blurry, low-res, watermark, logo overlay, burned-in text, burned-in subtitles, "
    "extra limbs, deformed hands, duplicate face, wrong wardrobe, color drift, "
    "stock-photo look, oversaturated neon mess"
)

NEGATIVE_VIDEO = (
    NEGATIVE_IMAGE + ", freeze-frame stutter, morphing face, wardrobe change mid-clip, "
    "camera jump-cut, text overlays"
)

_MJ_FLAG_RE = re.compile(
    r"(?:^|\s)--(?:ar|v|stylize|style|s|q|chaos|seed|no|tile|iw|cw|sw)\b[^\s]*",
    re.IGNORECASE,
)


def _clean(text: Any) -> str:
    t = " ".join(str(text or "").split()).strip().rstrip(",.;:")
    return t


def _strip_midjourney_flags(text: str) -> str:
    t = _MJ_FLAG_RE.sub(" ", text or "")
    return " ".join(t.split()).strip()


def _join_parts(parts: List[str]) -> str:
    out: List[str] = []
    seen = set()
    for p in parts:
        t = _clean(p)
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return ". ".join(out)


def _pick(scene: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = scene.get(k)
        if v is None:
            continue
        if isinstance(v, dict):
            # flatten short dicts
            bits = [f"{kk}: {_clean(vv)}" for kk, vv in v.items() if _clean(vv)]
            if bits:
                return "; ".join(bits)
            continue
        t = _clean(v)
        if t:
            return t
    return ""


def _extract_background(scene: Dict[str, Any], visual_prompt: str) -> str:
    """Prefer explicit background / macro_setting fields; else mine environment cues from visual_prompt."""
    explicit = _pick(
        scene,
        "macro_setting",
        "source_background",
        "background",
        "environment",
        "setting",
        "source_environment",
        "location",
    )
    if explicit:
        return explicit

    vp = visual_prompt or ""
    # Extract authentic scene environment phrases from visual prompt
    env_match = re.search(
        r"(?:setting|environment|location|background|inside|at|in a)\s*[:—\-]?\s*([^.,;]{10,80})",
        vp,
        flags=re.IGNORECASE,
    )
    if env_match:
        return _clean(env_match.group(1))

    return ""


def narration_to_visual_cues(
    narration: str,
    *,
    max_cues: int = 8,
    prefer_ui: bool = False,
) -> str:
    """Turn VO text into concrete MUST-SHOW props (not dialogue to lip-sync)."""
    text = _clean(narration)
    if not text:
        return ""
    # Bangla stems → English visual props (localized VO still drives English image APIs)
    bn_map = (
        (r"রোবট|হিউম্যানয়েড|অ্যান্ড্রয়েড", "humanoid robot"),
        (r"ডিম|রান্না|রান্নাবান্না", "cracking eggs, kitchen robot assistance"),
        (r"কাপড়|ভাঁজ", "folding laundry, household chore"),
        (r"কারখানা|ফ্যাক্টরি|ওয়ার্কশপ|ফ্লোর", "factory floor, industrial automation"),
        (r"হাঁটা|ভারসাম্য|ব্যালেন্স", "bipedal walking, dynamic balance"),
        (r"হাত|আঙুল", "robotic hand, articulated fingers"),
        (r"স্ক্রু|পার্টস|যন্ত্রাংশ|অ্যাসেম্বলি", "turning screws, mechanical assembly"),
        (r"বাক্স|তোলা|ভারী", "lifting boxes, warehouse logistics"),
        (r"চাকরি|কর্মক্ষেত্র|অফিস", "workplace automation, future labor"),
        (r"কাস্টম\s*ইন্সট্রাকশন|কাস্টম", "Custom Instructions"),
        (r"সেভ", "Save button"),
        (r"প্রোফাইল", "profile menu"),
        (r"টগল", "toggle"),
        (r"ল্যাপটপ|স্ক্রিন", "laptop screen"),
        (r"ক্লিক|চাপুন|খুলুন", "click UI"),
        (r"পেস্ট|কপি|বক্স", "text box"),
        (r"চ্যাটজিপিটি|জিপিটি", "ChatGPT"),
        (r"মহাকাশ|গ্রহ|নক্ষত্র|ব্ল্যাক হোল", "outer space, celestial cosmos"),
        (r"সমুদ্র|মহাসাগর|তলদেশ|গভীর", "deep ocean underwater, abyssal marine seafloor"),
        (r"অক্সিজেন|ডার্ক\s*অক্সিজেন", "dark oxygen chemical production, seafloor oxygen"),
        (r"শিলা|পাথর|নোডিউল|পলিমেটালিক", "polymetallic nodules underwater seafloor sediment"),
        (r"সাবমার্সিবল|জাহাজ|গবেষণা|ল্যাব", "ocean research submarine submersible, deep sea ROV probe"),
        (r"বিএমডব্লিউ|কারখানা|ফ্যাক্টরি", "automotive assembly factory, industrial robotics plant"),
        (r"রোবট|হিউম্যানয়েড|ফিগার", "humanoid robot automation, industrial robotic arm"),
    )
    bn_cues: List[str] = []
    for pat, eng in bn_map:
        if re.search(pat, text, re.I):
            bn_cues.append(eng)
    # Drop filler / address phrases that don't visualize
    drop = re.compile(
        r"\b(hey everyone|wow|so tell me|if you liked|share it|subscribe|comment|"
        r"look at this|first up|the second|the third|was this|really taken|"
        r"আসসালামু|বন্ধুরা|শেয়ার|সাবস্ক্রাইব|কমেন্ট)\b",
        re.I,
    )
    text = drop.sub(" ", text)
    # Prefer noun-ish tokens / key tech phrases — UI/product first when prefer_ui
    ui_phrases = re.findall(
        r"\b(?:ChatGPT|GPT|Custom Instructions?|Save|button|settings?|laptop|"
        r"screen|interface|UI|prompt|box|menu|sidebar|dashboard|browser|"
        r"paste|copy|type|click|panel|toggle)[a-zA-Z0-9_-]*\b",
        text,
        flags=re.I,
    )
    keep_phrases = re.findall(
        r"\b(?:robot|robotics|humanoid|optimus|figure|tesla|android|factory|automation|"
        r"assembly|mechanical|warehouse|sensor|motor|joint|metal|arm|AI|phone|camera|"
        r"night|photo|object|depth|cinematic|screen|fingerprint|swipe|studio|dark|"
        r"room|light|monitor|secret|trick|lens|flash|UI|button|city|window)[a-zA-Z0-9_-]*\b",
        text,
        flags=re.I,
    )
    # Drop "face"/"portrait" — they biased every stock search toward random people
    words = [w for w in text.replace(",", " ").split() if len(w) > 3]
    # Merge unique (UI cues first when product shot)
    seen = set()
    cues: List[str] = []
    ordered = (
        (bn_cues + ui_phrases + keep_phrases + words)
        if prefer_ui
        else (bn_cues + keep_phrases + ui_phrases + words)
    )
    for w in ordered:
        k = w.lower().strip(".,!?;:\"'")
        if k in seen or len(k) < 3:
            continue
        if prefer_ui and k in ("face", "portrait", "selfie", "man", "woman", "male", "female"):
            continue
        seen.add(k)
        cues.append(w.strip(".,!?;:\""))
        if len(cues) >= max_cues:
            break
    if not cues:
        return text[:160]
    return ", ".join(cues)


def resolve_scene_subject(
    scene: Dict[str, Any],
    *,
    narration_text: str = "",
) -> str:
    """Infer visual_subject for this scene (explicit field wins)."""
    spoken = _clean(
        narration_text
        or _pick(
            scene,
            "source_voiceover_script",
            "voiceover_script",
            "narration_beat",
            "subtitle_text",
            "spoken_beat",
        )
    )
    try:
        shot_n = int(scene.get("shot_number") or 0)
    except (TypeError, ValueError):
        shot_n = 0
    try:
        total = int(scene.get("total_shots") or scene.get("package_total_shots") or 0)
    except (TypeError, ValueError):
        total = 0
    return infer_visual_subject(
        narration=spoken,
        niche=str(scene.get("niche") or scene.get("package_niche") or ""),
        topic=str(scene.get("topic") or scene.get("selected_topic") or scene.get("package_topic") or ""),
        scene=scene,
        shot_number=shot_n,
        total_shots=total,
    )


def build_detailed_media_prompt(
    scene: Dict[str, Any],
    *,
    aspect_ratio: str = "9:16",
    art_style: str = "Cinematic Hyper-realistic",
    for_video: bool = False,
    narration_text: str = "",
) -> str:
    """Build a production prompt with subject lock + concrete visuals FIRST.

    VIDEO (Agnes/etc.): never paste dialogue as speech — models will speak English.
    IMAGE: put VISUAL DESCRIPTION early so Pollinations truncation keeps scene detail.
    Product/UI shots: NO character/face lock — ChatGPT settings/UI instead.
    """
    subject = resolve_scene_subject(scene, narration_text=narration_text)
    topic = str(scene.get("topic") or scene.get("selected_topic") or scene.get("package_topic") or "")
    niche = str(scene.get("niche") or scene.get("package_niche") or "")
    from pipeline.custom_pipeline.visual_subject_policy import is_non_presenter_topic
    topic_doc = is_non_presenter_topic(niche, topic)
    if topic_doc and subject in (SUBJECT_PRESENTER, "person", "character"):
        subject = SUBJECT_BROLL
    allow_char = character_allowed(subject) and not topic_doc

    raw_vp = _pick(scene, "visual_prompt", "image_prompt", "video_prompt")
    vp = _strip_midjourney_flags(raw_vp)
    if not allow_char:
        vp = strip_face_language(vp)
    cam = _pick(scene, "source_camera_angle", "camera_angle", "camera")
    light = _pick(scene, "source_lighting", "lighting", "light")
    char = _pick(scene, "source_character_details", "character_details", "character")
    if char and char.lower() in ("none", "n/a", "na", "no character", "-", "null"):
        char = ""
    if not allow_char:
        char = ""
    bg = _extract_background(scene, vp)
    emotion = _pick(scene, "source_emotion_tag", "emotion_tag", "emotion")
    spoken = _clean(
        narration_text
        or _pick(
            scene,
            "source_voiceover_script",
            "voiceover_script",
            "narration_beat",
            "subtitle_text",
            "spoken_beat",
        )
    )
    prefer_ui = subject in (SUBJECT_PRODUCT_UI, SUBJECT_HANDS_UI, SUBJECT_BROLL)
    visual_cues = narration_to_visual_cues(spoken, prefer_ui=prefer_ui)
    motion = scene.get("motion_directives") if isinstance(scene.get("motion_directives"), dict) else {}
    shot_n = scene.get("shot_number")
    dur = scene.get("shot_duration_seconds")

    parts: List[str] = []

    # 1. VISUAL DESCRIPTION FIRST (Diffusion models weight tokens 0-75 highest)
    if vp:
        parts.append(f"VISUAL DESCRIPTION (ultra-detailed): {vp}")
    else:
        if subject == SUBJECT_PRODUCT_UI:
            parts.append(
                f"VISUAL DESCRIPTION (ultra-detailed): {art_style} photoreal product UI screen, "
                f"crisp readable chrome, clean device framing, professional color grade, 8k, NO human face"
            )
        elif subject == SUBJECT_BROLL:
            parts.append(
                f"VISUAL DESCRIPTION (ultra-detailed): {art_style} cinematic shot directly depicting "
                f"the topic subject, rich atmospheric environment, realistic textures, photoreal, 8k, NO human face"
            )
        else:
            parts.append(
                f"VISUAL DESCRIPTION (ultra-detailed): {art_style} cinematic shot matching the "
                f"narration topic, detailed environment, professional color grade, photoreal, 8k"
            )

    # 2. MUST SHOW ON SCREEN (AV sync concrete props from spoken narration)
    if visual_cues:
        parts.append(
            f"MUST SHOW ON SCREEN (AV sync props from narration): {visual_cues}"
        )

    # 3. CAMERA & LIGHTING & BACKGROUND
    if cam:
        parts.append(f"CAMERA ANGLE: {cam}")
    if light:
        parts.append(f"LIGHTING: {light}")
    if bg:
        parts.append(f"BACKGROUND / ENVIRONMENT: {bg}")
    else:
        parts.append(
            "BACKGROUND / ENVIRONMENT: keep the same setting, lighting, and depth of field as described"
        )

    # 4. SUBJECT LOCK & POLICY (strictly enforce B-roll vs UI vs Presenter)
    if for_video:
        parts.append(
            "SILENT VIDEO ONLY: no speech, no dialogue, no voiceover, no lip-sync talk, "
            "no burned-in captions — ambient room tone only if any audio "
            "(critical: video models must NOT speak English over localized TTS)"
        )

    if subject == SUBJECT_PRODUCT_UI:
        parts.append(product_ui_subject_block(spoken))
    elif subject == SUBJECT_HANDS_UI:
        parts.append(hands_ui_subject_block())
        if char:
            parts.append(f"WARDROBE CUFF ONLY (no face): {char}")
    elif subject == SUBJECT_BROLL:
        parts.append(
            "SUBJECT LOCK (B-ROLL): environment / abstract tech mood — "
            "NO human face, NO portrait, NO talking head"
        )
    elif char:
        parts.append(f"CHARACTER LOCK (identical every frame): {char}")

    # 5. SCENE INTENT & NARRATION SYNC
    if spoken and not for_video:
        beat = spoken if len(spoken) <= 180 else spoken[:177].rsplit(" ", 1)[0] + "…"
        parts.append(f"SCENE INTENT (illustrate this idea — do not render text): {beat}")
    elif spoken and for_video:
        beat = spoken if len(spoken) <= 140 else spoken[:137].rsplit(" ", 1)[0] + "…"
        parts.append(
            f"SCENE INTENT (show this idea visually; DO NOT speak or mouth these words): {beat}"
        )

    if emotion and allow_char:
        parts.append(f"PERFORMANCE / EMOTION (face/body only, no speech): {emotion}")

    neg = negative_for_subject(subject, topic=topic)
    if neg:
        parts.append(f"NEGATIVE: {neg}")

    # --- FORMAT / MOTION ---
    if "9:16" in str(aspect_ratio):
        parts.append(f"FORMAT: aspect ratio {aspect_ratio}, vertical framing locked, 9:16 portrait")
    else:
        parts.append(f"FORMAT: aspect ratio {aspect_ratio}")

    if for_video:
        cam_m = _clean(motion.get("camera_movement"))
        act = _clean(motion.get("character_action"))
        if cam_m:
            parts.append(f"CAMERA MOVEMENT: {cam_m}")
        if act and allow_char:
            parts.append(f"CHARACTER ACTION: {act}")
        elif act and prefer_ui:
            parts.append(f"SCENE / SUBJECT ACTION: {act}")
        if dur:
            parts.append(f"DURATION: about {dur} seconds, smooth natural motion, 24fps")
        if allow_char:
            parts.append(
                "CONTINUITY: same identity every frame — no face morph, no outfit change, no set jump"
            )
        else:
            parts.append(
                "CONTINUITY: consistent environment, scene style, and lighting — no random people entering frame"
            )
        parts.append(
            "AUDIO POLICY: generate picture only; if the model emits audio it must be silence"
        )
    else:
        anim = _clean(motion.get("animation_type"))
        if anim:
            parts.append(f"STILL PREP FOR MOTION: {anim}")
        if subject == SUBJECT_PRODUCT_UI:
            parts.append(
                "OUTPUT: single photoreal frame, sharp focus on UI/screen/device panels, "
                "production-ready, crisp framing that matches MUST SHOW"
            )
        elif subject == SUBJECT_BROLL:
            parts.append(
                "OUTPUT: single photoreal cinematic frame, sharp focus on topic subject and action, "
                "production-ready, 8k detail, NO human face, matches MUST SHOW"
            )
        else:
            parts.append(
                "OUTPUT: single photoreal frame, sharp focus, production-ready, "
                "rich micro-detail on primary subject/props that match MUST SHOW"
            )

    if shot_n:
        parts.append(f"SHOT NUMBER: {shot_n}")
    parts.append(f"VISUAL SUBJECT: {subject}")
    if art_style:
        parts.append(f"ART STYLE: {art_style}")
    parts.append(
        "STRICT: no watermarks, no burned captions, no logos, no extra people, no on-screen text"
    )

    prompt = _join_parts(parts)
    if len(prompt.split()) < 45:
        if prefer_ui:
            prompt = (
                f"{prompt}. Expand with crisp product-UI composition, screen glow, "
                f"desk depth of field, controlled color grade, documentary YouTube look, "
                f"authentic interface chrome — zero human faces."
            )
        elif allow_char:
            prompt = (
                f"{prompt}. Expand with cinematic composition, depth of field, "
                f"environment continuity, fabric texture, skin detail, controlled color grade, "
                f"professional documentary visual, consistent wardrobe and face identity."
            )
        else:
            prompt = (
                f"{prompt}. Expand with cinematic composition, depth of field, "
                f"environment continuity, realistic textures, controlled color grade, "
                f"professional documentary visual, strictly NO human face, NO portrait, NO person in frame."
            )
    return prompt


def fit_prompt_for_provider(prompt: str, max_chars: int) -> str:
    """Truncate from the END only — priority block at the start always survives."""
    p = (prompt or "").strip()
    if max_chars <= 0 or len(p) <= max_chars:
        return p
    cut = p[: max_chars - 1].rsplit(" ", 1)[0].rstrip(".,;")
    return cut + "…"


def stock_search_query(scene: Dict[str, Any]) -> str:
    """Short stock query derived from scene (stock APIs need keywords, not Midjourney tags).
    
    Anchored with macro visual context to prevent brand misinterpretations (e.g. BMW -> factory robot,
    not sports cars; deep-sea nodule -> underwater seafloor, not mountain rock).
    """
    narr = _pick(scene, "source_voiceover_script", "voiceover_script")
    subject = resolve_scene_subject(scene, narration_text=narr)
    prefer_ui = subject in (SUBJECT_PRODUCT_UI, SUBJECT_HANDS_UI, SUBJECT_BROLL)
    
    thematic_domain = str(scene.get("thematic_domain") or "").strip()
    topic_val = str(scene.get("topic") or scene.get("package_topic") or "")
    niche_val = str(scene.get("niche") or scene.get("package_niche") or "")

    bits = []
    # 1. Macro Domain Anchor first
    if "robot" in f"{thematic_domain} {topic_val}".lower() or "factory" in f"{thematic_domain} {topic_val}".lower():
        bits.append("industrial factory robot assembly line automation")
    elif "deep sea" in f"{thematic_domain} {topic_val}".lower() or "ocean" in f"{thematic_domain} {topic_val}".lower() or "oxygen" in f"{thematic_domain} {topic_val}".lower():
        bits.append("deep sea ocean floor underwater 4000m exploration")
    elif "space" in f"{thematic_domain} {topic_val}".lower() or "astronomy" in f"{thematic_domain} {topic_val}".lower():
        bits.append("deep outer space cosmos nebula planets")

    # 2. Narration visual cues
    cues = narration_to_visual_cues(narr, max_cues=6, prefer_ui=prefer_ui)
    if cues:
        bits.append(cues)

    bits.append(_pick(scene, "source_camera_angle", "camera_angle"))

    if character_allowed(subject):
        bits.append(_pick(scene, "source_character_details", "character_details")[:80])
    else:
        from pipeline.custom_pipeline.visual_subject_policy import is_product_or_tool_niche
        if is_product_or_tool_niche(niche=niche_val, topic=topic_val):
            bits.extend(["software screen", "technology interface"])
        elif topic_val and not bits:
            clean_topic = re.sub(r"[^\w\s]", " ", topic_val)
            bits.append(" ".join(clean_topic.split()[:4]))

    bits.append(_extract_background(scene, _pick(scene, "visual_prompt"))[:80])
    if prefer_ui:
        bits.append(strip_face_language(_pick(scene, "visual_prompt"))[:100])
    else:
        bits.append(_pick(scene, "visual_prompt")[:100])

    text = " ".join(bits)
    text = _strip_midjourney_flags(text)

    # Strip forbidden tangents
    if "robot" in f"{thematic_domain} {topic_val}".lower():
        text = re.sub(r"(?i)\b(?:car|cars|automobile|motorcycle|motorbike|driving|highway|dealership|showroom)\b", " ", text)
    elif "deep sea" in f"{thematic_domain} {topic_val}".lower() or "ocean" in f"{thematic_domain} {topic_val}".lower():
        text = re.sub(r"(?i)\b(?:beach|mountain|dry|land|boulder|sky|sunny|swimmer|desert)\b", " ", text)

    if prefer_ui:
        text = strip_face_language(text)
        text = re.sub(
            r"(?i)\b(?:young|man|woman|male|female|portrait|face|hoodie|person|people)\b",
            " ",
            text,
        )

    words = [w for w in text.replace("--", " ").split() if len(w) > 2][:12]
    if words:
        return " ".join(words)
    if "deep sea" in f"{thematic_domain} {topic_val}".lower() or "ocean" in f"{thematic_domain} {topic_val}".lower():
        return "deep sea ocean floor underwater research"
    if "robot" in f"{thematic_domain} {topic_val}".lower():
        return "industrial robot factory automation"
    if prefer_ui:
        return "software screen settings interface computer"
    return "cinematic documentary background exploration"


def prompt_audit(scene: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    """Debug helper: confirm required layers are present in the final prompt."""
    p = prompt or ""
    pl = p.lower()
    subject = resolve_scene_subject(scene)
    return {
        "chars": len(p),
        "words": len(p.split()),
        "visual_subject": subject,
        "has_character": "character lock" in pl
        or (
            character_allowed(subject)
            and bool(_pick(scene, "source_character_details", "character_details"))
        ),
        "has_product_ui_lock": "product ui" in pl or "no human face" in pl,
        "has_camera": "camera angle" in pl
        or bool(_pick(scene, "source_camera_angle", "camera_angle")),
        "has_lighting": "lighting:" in pl
        or bool(_pick(scene, "source_lighting", "lighting")),
        "has_background": "background" in pl,
        "has_spoken_beat": "scene intent" in pl or "must show" in pl or "spoken beat" in pl,
        "has_visual_body": "visual description" in pl,
        "silent_video_policy": "silent video" in pl or "no speech" in pl,
        "has_must_show": "must show" in pl,
    }
