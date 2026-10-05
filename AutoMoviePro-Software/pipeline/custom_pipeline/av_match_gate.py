"""AV match gate — dialogue ↔ visual prompt ↔ generated/stock media (industrial).

Layers (cheap → expensive):
  1) Local MUST-SHOW extraction from narration + visual_subject
  2) Pre-flight prompt coverage (ZERO API) — rewrite until covered
  3) Brand-UI stock forbid (Pexels cannot show real ChatGPT chrome)
  4) Post-generate metadata gate → at most ONE local regen
  5) Optional thrifty vision critic (see av_vision_critic) — only when heuristics fail

Live failure (pkg 004): product_ui shots were STOCK_VIDEO from Pexels with queries like
\"box first describe you\" — zero ChatGPT Custom Instructions UI on screen while VO
described settings.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from pipeline.custom_pipeline.visual_subject_policy import (
    SUBJECT_BROLL,
    SUBJECT_HANDS_UI,
    SUBJECT_PRESENTER,
    SUBJECT_PRODUCT_UI,
    infer_visual_subject,
    is_non_presenter_topic,
    strip_face_language,
)

# Brand / product UI tokens that stock libraries almost never depict correctly
_BRAND_UI = re.compile(
    r"\b("
    r"chatgpt|gpt|openai|claude|gemini|copilot|midjourney|"
    r"custom instructions?|settings?|save button|sidebar|dashboard|"
    r"chat\s*box|prompt\s*box|web\s*ui|interface|"
    r"কাস্টম|ইন্সট্রাকশন|সেটিংস|চ্যাটজিপিটি"
    r")\b",
    re.I,
)

_UI_ACTIONS = re.compile(
    r"\b(click|open|tap|press|save|paste|copy|type|scroll|toggle|enable|profile|"
    r"ক্লিক|খুল|সেভ|পেস্ট|কপি|টগল|প্রোফাইল)\b",
    re.I,
)

# Unwanted human face in non-presenter shots (B-roll, documentary, robotics)
_FORBIDDEN_PRESENTER_FACE = re.compile(
    r"\b("
    r"male presenter|female presenter|bangladeshi male|bangladeshi female|"
    r"28-year-old|25-year-old|presenter in a compact|hoodie addressing camera|"
    r"looking straight at camera|looking directly at camera|selfie|portrait of a man|"
    r"portrait of a woman|talking head|handsome presenter|young man looking at camera|"
    r"stubble|beard|addressing the viewer|host talking"
    r")\b",
    re.I,
)

# Unrealistic text/UI instructions that image generators corrupt into gibberish smudges
_UNREALISTIC_TEXT_IN_PROMPT = re.compile(
    r"\b("
    r"mixed bengali-english|bengali-english text|readable headline|readable text on screen|"
    r"tech news article ui|news article ui|detailed article text|newspaper article|"
    r"dense charts and graphs|charts comparing|youtube video player ui|video player ui|"
    r"crisp play bar|volume icon|readable chrome|browser tabs|crisp ui chrome|"
    r"readable sans-serif text|article ui|news article"
    r")\b",
    re.I,
)

# Synonym groups: any member satisfies the group
_MUST_GROUPS: Dict[str, Sequence[str]] = {
    "chatgpt": ("chatgpt", "gpt", "openai chat", "chat gpt", "চ্যাটজিপিটি"),
    "custom_instructions": (
        "custom instructions",
        "custom instruction",
        "instructions panel",
        "instructions box",
        "instructions settings",
        "কাস্টম ইন্সট্রাকশন",
    ),
    "settings": ("settings", "setting", "preferences", "profile menu", "সেটিংস"),
    "save": ("save", "save button", "save changes", "সেভ"),
    "laptop_screen": ("laptop", "screen", "monitor", "display", "browser", "ল্যাপটপ", "স্ক্রিন"),
    "ui_chrome": ("ui", "interface", "panel", "sidebar", "button", "toggle", "box"),
}

# Bangla → English visual stems for AV lock (dialogue may be localized)
_BN_VISUAL_MAP: Tuple[Tuple[str, str], ...] = (
    # Software & UI
    (r"কাস্টম\s*ইন্সট্রাকশন|কাস্টম", "Custom Instructions"),
    (r"সেভ|সেভ\s*বাটন", "Save button"),
    (r"প্রোফাইল", "profile menu"),
    (r"টগল|চালু", "toggle switch"),
    (r"ল্যাপটপ|স্ক্রিন|মনিটর", "laptop screen"),
    (r"ক্লিক|চাপ|খুল", "clicking UI control"),
    (r"পেস্ট|কপি|বক্স", "text field / instructions box"),
    (r"চ্যাটজিপিটি|জিপিটি", "ChatGPT"),

    # Robotics, AI & Engineering (Fix for live pkg 006)
    (r"হিউম্যানয়েড\s*রোবট|হিউম্যানয়েড", "humanoid robot"),
    (r"রোবট|রোবটিক", "robot in action"),
    (r"ডিম\s*ভাঙা|ডিম", "robot delicately handling egg"),
    (r"কাপ[\u09dc\u09a1\u09bc]\s*ভাঁজ|কাপ[\u09dc\u09a1\u09bc]", "robot folding laundry clothes"),
    (r"কারখানা|ফ্যাক্টরি", "industrial factory assembly line"),
    (r"স্ক্রু|স্ক্রু\s*আটকানো", "tightening mechanical screws with robotic fingers"),
    (r"হাঁটা|হাঁটছে|পায়ে", "bipedal robot walking and balancing"),
    (r"আঙুল|হাতের\s*আঙুল|রোবোটিক\s*হাত", "dexterous robotic hand and fingers"),
    (r"যন্ত্র|যন্ত্রপাতি|অটোমেশন", "advanced automated machinery"),
    (r"গবেষণা|ল্যাব|ল্যাবরেটরি", "robotics research laboratory"),
    (r"সেন্সর|ক্যামেরা", "robotic vision sensors and optical cameras"),
    (r"কৃত্রিম\s*বুদ্ধিমত্তা|এআই", "advanced AI system and robotics"),
)

# Max local regenerations after gate fail (API thrift)
MAX_LOCAL_REGEN = 1


def max_local_regen() -> int:
    try:
        return max(0, min(2, int(os.environ.get("AMP_AV_MAX_REGEN") or str(MAX_LOCAL_REGEN))))
    except ValueError:
        return MAX_LOCAL_REGEN


def is_brand_software_narration(text: str = "", *, niche: str = "", topic: str = "") -> bool:
    blob = f"{text} {niche} {topic}"
    return bool(_BRAND_UI.search(blob))


def extract_must_show(
    narration: str,
    *,
    visual_subject: str = "",
    niche: str = "",
    topic: str = "",
) -> List[str]:
    """Concrete elements the frame MUST depict (English tokens for API prompts)."""
    narr = narration or ""
    subject = (visual_subject or "").strip().lower() or infer_visual_subject(
        narration=narr, niche=niche, topic=topic
    )
    must: List[str] = []
    low = narr.lower()

    # Bangla → English visual stems first (localized VO)
    for pat, eng in _BN_VISUAL_MAP:
        if re.search(pat, narr, re.I):
            must.append(eng)

    topic_non_presenter = is_non_presenter_topic(niche=niche, topic=topic) or bool(
        re.search(r"robot|humanoid|রোবট", f"{narr} {topic}", re.I)
    )

    if topic_non_presenter:
        if re.search(r"হিউম্যানয়েড|রোবট|robot|humanoid", f"{narr} {topic}", re.I):
            must.append("advanced humanoid robot in action")
        if re.search(r"ডিম|egg", narr, re.I):
            must.append("robot delicately handling or cracking an egg with precision fingers")
        if re.search(r"কাপ[\u09dc\u09a1\u09bc]|laundry|cloth", narr, re.I):
            must.append("humanoid robot folding laundry clothes smoothly")
        if re.search(r"কারখানা|ফ্যাক্টরি|factory|assembly", narr, re.I):
            must.append("humanoid robots working on industrial factory assembly line")
        if re.search(r"স্ক্রু|screw|tighten", narr, re.I):
            must.append("robotic mechanical fingers tightening a precision screw")
        if re.search(r"হাঁটা|walk|balancing", narr, re.I):
            must.append("bipedal robot walking smoothly and balancing on two legs")
        if re.search(r"আঙুল|হাত|fingers?|gripper", narr, re.I):
            must.append("close-up of advanced robotic hand and dexterous mechanical fingers")
        must.append("NO human presenter face / NO random portrait")

    if subject in (SUBJECT_PRODUCT_UI, SUBJECT_HANDS_UI) or is_brand_software_narration(
        narr, niche=niche, topic=topic
    ):
        if "custom instruction" in low or "কাস্টম" in narr:
            must.append("ChatGPT Custom Instructions settings panel")
        if re.search(r"\bsave\b|সেভ", narr, re.I):
            must.append("Save button on ChatGPT settings UI")
        if re.search(r"\btoggle|enable for new chats|টগল", narr, re.I):
            must.append("Enable for new chats toggle on ChatGPT UI")
        if re.search(r"\bprofile|প্রোফাইল", narr, re.I):
            must.append("ChatGPT profile menu open")
        if re.search(r"\bpaste|copy|কপি|পেস্ট|বক্স|box", narr, re.I):
            must.append("text box / instructions field on ChatGPT screen")
        if re.search(r"\blaptop|ল্যাপটপ|screen|স্ক্রিন|browser", narr, re.I):
            must.append("laptop screen showing ChatGPT web app")
        if not must:
            must.append("ChatGPT web UI settings or chat screen, readable panels")
        must.append("NO human face / NO random stock portrait")
        if subject == SUBJECT_HANDS_UI:
            must.append("adult hands only — face cropped out")

    # Generic AV nouns (EN)
    for word in ("phone", "camera", "keyboard", "monitor", "earbuds", "charger", "robot", "hand"):
        if re.search(rf"\b{word}\b", low):
            must.append(word)

    # Action verbs → visible motion cue (smooth dialogue↔visual)
    if _UI_ACTIONS.search(narr):
        if not any("click" in m.lower() or "hand" in m.lower() for m in must):
            must.append("visible UI interaction (cursor or finger on control)")

    # de-dupe preserve order
    seen: Set[str] = set()
    out: List[str] = []
    for m in must:
        k = m.lower()
        if k not in seen:
            seen.add(k)
            out.append(m)
    return out


def stock_forbidden_for_shot(
    *,
    visual_subject: str = "",
    narration: str = "",
    niche: str = "",
    topic: str = "",
) -> bool:
    """Pexels/Pixabay cannot render real ChatGPT chrome — forbid for brand UI shots."""
    subject = (visual_subject or "").strip().lower() or infer_visual_subject(
        narration=narration, niche=niche, topic=topic
    )
    if subject in (SUBJECT_PRODUCT_UI, SUBJECT_HANDS_UI):
        return True
    if is_brand_software_narration(narration, niche=niche, topic=topic) and _UI_ACTIONS.search(
        narration or ""
    ):
        return True
    return False


def _group_hit(text: str, synonyms: Sequence[str]) -> bool:
    low = (text or "").lower()
    return any(s in low for s in synonyms)


def prompt_covers_must_show(prompt: str, must_show: Sequence[str]) -> Dict[str, Any]:
    """Soft coverage: brand UI shots need chatgpt + (settings|instructions|ui) signal."""
    p = prompt or ""
    missing: List[str] = []
    for item in must_show:
        stems = re.findall(r"[A-Za-z\u0980-\u09FF]{3,}", item)
        if not stems:
            continue
        if item.upper().startswith("NO "):
            p_low = p.lower()
            neg_cues = (
                "no human face",
                "no face",
                "no presenter",
                "no human presenter face",
                "no portrait",
                "no random portrait",
            )
            if not any(neg in p_low for neg in neg_cues):
                missing.append(item)
            continue
        if not any(s.lower() in p.lower() for s in stems[:4]):
            missing.append(item)

    brand_ok = True
    if any("chatgpt" in m.lower() or "custom" in m.lower() for m in must_show):
        brand_ok = _group_hit(p, _MUST_GROUPS["chatgpt"]) and (
            _group_hit(p, _MUST_GROUPS["custom_instructions"])
            or _group_hit(p, _MUST_GROUPS["settings"])
            or _group_hit(p, _MUST_GROUPS["ui_chrome"])
        )
        if not brand_ok:
            missing.append("brand_ui_core(ChatGPT+settings/instructions)")

    score = 1.0 if not missing else max(0.0, 1.0 - 0.18 * len(missing))
    return {
        "ok": len(missing) == 0 and brand_ok,
        "score": round(score, 3),
        "missing": missing,
    }


def dialogue_visual_alignment_score(
    narration: str,
    prompt: str,
    *,
    must_show: Optional[Sequence[str]] = None,
    visual_subject: str = "",
    niche: str = "",
    topic: str = "",
) -> Dict[str, Any]:
    """0–1 score: how tightly the prompt tracks spoken meaning (local, no API)."""
    subject = (visual_subject or "").strip().lower() or infer_visual_subject(
        narration=narration, niche=niche, topic=topic
    )
    must = list(must_show) if must_show is not None else extract_must_show(
        narration, visual_subject=subject, niche=niche, topic=topic
    )
    cover = prompt_covers_must_show(prompt, must)
    prompt_low = (prompt or "").lower()

    # Hard rejection for unwanted human presenter faces in non-presenter shots
    is_non_presenter = (subject != SUBJECT_PRESENTER) or is_non_presenter_topic(niche=niche, topic=topic)
    audit_face_text = re.sub(
        r"(?i)\bno\s+(?:human\s+)?(?:presenter|face|portrait|selfie|talking\s*head)\b[^,.;/]*",
        " ",
        prompt_low,
    )
    if is_non_presenter and _FORBIDDEN_PRESENTER_FACE.search(audit_face_text):
        return {
            "score": 0.0,
            "ok": False,
            "lexical": 0.0,
            "coverage": {
                "ok": False,
                "score": 0.0,
                "missing": ["forbidden_presenter_face_in_non_presenter_shot"],
            },
            "must_show": must,
            "reasons": ["unwanted_presenter_face_in_non_presenter_shot"],
        }

    # Extract narration tokens: English tokens + mapped English stems from Bengali
    narr_tokens = set(re.findall(r"[A-Za-z]{4,}", (narration or "").lower()))
    stop = {
        "this", "that", "with", "from", "your", "have", "will", "just", "then",
        "when", "what", "they", "them", "here", "there", "about", "into",
    }
    narr_tokens -= stop

    # Also extract concepts from Bangla narration matching _BN_VISUAL_MAP
    for pat, eng in _BN_VISUAL_MAP:
        if re.search(pat, narration or "", re.I):
            for stem in re.findall(r"[A-Za-z]{4,}", eng.lower()):
                if stem not in stop:
                    narr_tokens.add(stem)

    hit = sum(1 for t in narr_tokens if t in prompt_low)
    lexical = (hit / max(1, len(narr_tokens))) if narr_tokens else 0.5

    # Check for unrealistic text instructions in image prompt
    text_penalty = 0.0
    if _UNREALISTIC_TEXT_IN_PROMPT.search(prompt_low):
        text_penalty = 0.25

    score = max(0.0, 0.65 * float(cover.get("score") or 0) + 0.35 * min(1.0, lexical) - text_penalty)
    ok = score >= 0.55 and bool(cover.get("ok")) and (text_penalty == 0.0)

    reasons: List[str] = []
    if not cover.get("ok"):
        reasons.append(f"missing_must_show:{cover.get('missing')}")
    if text_penalty > 0:
        reasons.append("unrealistic_text_in_prompt")

    return {
        "score": round(score, 3),
        "ok": ok,
        "lexical": round(lexical, 3),
        "coverage": cover,
        "must_show": must,
        "reasons": reasons,
    }


def stock_query_acceptable(query: str, must_show: Sequence[str]) -> Dict[str, Any]:
    q = query or ""
    if not _group_hit(
        q,
        (
            "chatgpt",
            "gpt",
            "laptop",
            "screen",
            "settings",
            "ui",
            "interface",
            "browser",
            "phone",
            "camera",
            "product",
        ),
    ):
        return {
            "ok": False,
            "score": 0.0,
            "missing": ["stock_query_lacks_ui_nouns"],
            "reason": "stock query has no UI/product nouns",
        }
    return prompt_covers_must_show(q, [m for m in must_show if not m.upper().startswith("NO ")])


def evaluate_generated_asset(
    *,
    provider: str = "",
    fallback: bool = False,
    prompt: str = "",
    stock_query: str = "",
    narration: str = "",
    visual_subject: str = "",
    niche: str = "",
    topic: str = "",
) -> Dict[str, Any]:
    """Decide whether to accept or regenerate/redownload (metadata / local only)."""
    must = extract_must_show(
        narration, visual_subject=visual_subject, niche=niche, topic=topic
    )
    subject = (visual_subject or "").strip().lower()
    prov = (provider or "").lower()
    is_stock = fallback or "stock" in prov or "pexels" in prov or "pixabay" in prov

    align = dialogue_visual_alignment_score(
        narration,
        prompt,
        must_show=must,
        visual_subject=subject,
        niche=niche,
        topic=topic,
    )
    result: Dict[str, Any] = {
        "ok": True,
        "must_show": must,
        "action": "accept",
        "reasons": [],
        "prompt_audit": align.get("coverage") or {},
        "alignment": align,
        "stock_audit": {},
        "needs_vision": False,
    }

    if stock_forbidden_for_shot(
        visual_subject=subject, narration=narration, niche=niche, topic=topic
    ):
        if is_stock:
            result["ok"] = False
            result["action"] = "regenerate_ai"
            result["reasons"].append(
                "brand_ui_stock_forbidden: Pexels/Pixabay cannot show real ChatGPT settings UI"
            )
            result["needs_vision"] = False  # already decisive — no need to burn vision API
            return result

    if prompt:
        pa = result["prompt_audit"]
        if "unwanted_presenter_face_in_non_presenter_shot" in align.get("reasons", []):
            result["ok"] = False
            result["action"] = "rewrite_prompt_and_regenerate"
            result["reasons"].append("unwanted_presenter_face_in_non_presenter_shot")
        elif "unrealistic_text_in_prompt" in align.get("reasons", []):
            result["ok"] = False
            result["action"] = "rewrite_prompt_and_regenerate"
            result["reasons"].append("unrealistic_text_in_prompt")
        elif pa and not pa.get("ok"):
            result["ok"] = False
            result["action"] = "rewrite_prompt_and_regenerate"
            result["reasons"].append(f"prompt_missing:{pa.get('missing')}")
        elif align.get("score", 1) < 0.45:
            result["ok"] = False
            result["action"] = "rewrite_prompt_and_regenerate"
            result["reasons"].append(f"weak_dialogue_visual_align:{align.get('score')}")

    if is_stock and stock_query:
        sa = stock_query_acceptable(stock_query, must)
        result["stock_audit"] = sa
        if not sa.get("ok"):
            result["ok"] = False
            result["action"] = "redownload_or_ai"
            result["reasons"].append(f"stock_query_weak:{sa.get('missing')}")

    # Suggest vision only when heuristic is soft-uncertain (not hard stock forbid)
    if result["ok"] and subject in (SUBJECT_PRODUCT_UI, SUBJECT_HANDS_UI) and is_stock:
        result["needs_vision"] = True
    elif not result["ok"] and result["action"] != "regenerate_ai":
        result["needs_vision"] = True

    return result


def strengthen_prompt_with_must_show(prompt: str, must_show: Sequence[str]) -> str:
    if not must_show:
        return prompt or ""
    block = "MUST DEPICT EXACTLY (dialogue AV lock): " + "; ".join(must_show)
    p = (prompt or "").strip()
    if "MUST DEPICT EXACTLY" in p:
        # Refresh must-show block if older/weaker
        if prompt_covers_must_show(p, must_show).get("ok"):
            return p
        p = re.sub(
            r"MUST DEPICT EXACTLY \(dialogue AV lock\):[^.]*\.\s*",
            "",
            p,
            count=1,
            flags=re.I,
        ).strip()
    return f"{block}. {p}".strip()


def ensure_prompt_av_ready(
    prompt: str,
    narration: str,
    *,
    visual_subject: str = "",
    niche: str = "",
    topic: str = "",
) -> Dict[str, Any]:
    """Pre-flight (0 API): strengthen until coverage OK or return best effort + audit."""
    subject = (visual_subject or "").strip().lower() or infer_visual_subject(
        narration=narration, niche=niche, topic=topic
    )
    must = extract_must_show(
        narration, visual_subject=subject, niche=niche, topic=topic
    )

    topic_is_doc = is_non_presenter_topic(niche=niche, topic=topic)
    cleaned = prompt or ""
    if subject != SUBJECT_PRESENTER or topic_is_doc:
        cleaned = strip_face_language(cleaned)

    if topic_is_doc:
        # Transform meta-screen prompts into direct live depiction
        cleaned = re.sub(
            r"(?i)\b(?:photoreal )?(?:extreme )?close-?up of (?:a |the )?(?:15-inch )?laptop(?:\s*screen)?(?:\s*on\s*the\s*dark\s*night\s*studio\s*desk)?[^,.]*,\s*(?:video\s*player\s*ui|tech\s*news\s*article\s*ui|article\s*ui)[^,.]*(?:playing|about)\s*",
            "Cinematic live depiction of ",
            cleaned,
        )
        cleaned = re.sub(
            r"(?i)\b(?:compact night tech studio|dark night studio desk|dual monitors with cyan glow|dual 27-inch monitors|dark matte desk|slim led strip on back wall)[^,.]*",
            " ",
            cleaned,
        )
        cleaned = _UNREALISTIC_TEXT_IN_PROMPT.sub(" ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;")

        # If prompt has lost its core topic entities (e.g. was just an empty studio / stripped presenter):
        core_tokens = ("robot", "humanoid", "machine", "factory", "assembly", "space", "science", "nature", "animal", "gear", "sensor", "optics")
        has_core = any(tok in cleaned.lower() for tok in core_tokens)
        if not has_core:
            from pipeline.custom_pipeline.media_prompts import narration_to_visual_cues
            cues = narration_to_visual_cues(narration, prefer_ui=False)
            if cues:
                cleaned = (
                    f"Cinematic photoreal depiction: {cues}. "
                    "Atmospheric cinematic lighting, 8k resolution, hyper-detailed scene, "
                    "shallow depth of field, no human presenter face, no portrait, no selfie"
                )
    else:
        cleaned = _UNREALISTIC_TEXT_IN_PROMPT.sub(" ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

    strengthened = strengthen_prompt_with_must_show(cleaned, must)
    # Second pass: inject alignment cue if still weak
    align = dialogue_visual_alignment_score(
        narration, strengthened, must_show=must, visual_subject=subject, niche=niche, topic=topic
    )
    if not align.get("ok"):
        beat = " ".join((narration or "").split())[:140]
        if beat and "SCENE INTENT" not in strengthened:
            strengthened = (
                f"SCENE INTENT (show this idea visually; DO NOT speak these words): {beat}. "
                + strengthened
            )
        strengthened = strengthen_prompt_with_must_show(strengthened, must)
        align = dialogue_visual_alignment_score(
            narration, strengthened, must_show=must, visual_subject=subject, niche=niche, topic=topic
        )
    return {
        "prompt": strengthened,
        "must_show": must,
        "alignment": align,
        "ok": bool(align.get("ok")),
    }


def brand_ui_stock_query(narration: str = "") -> str:
    """If stock is ever allowed as last resort — still UI-first keywords only."""
    bits = ["laptop computer screen", "web browser interface", "software settings panel closeup"]
    low = (narration or "").lower()
    if "custom instruction" in low or "কাস্টম" in (narration or ""):
        bits = ["software settings form on laptop screen", "scrolling preferences panel UI"]
    if "save" in low or "সেভ" in (narration or ""):
        bits.append("cursor clicking save button on screen")
    return " ".join(bits[:8])


def merge_gate_with_vision(
    gate: Dict[str, Any],
    vision: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Combine local gate + optional vision critic without overriding hard stock forbid."""
    out = dict(gate or {})
    out["vision"] = vision or {"skipped": True}
    if not vision or vision.get("skipped"):
        return out
    if vision.get("api_used") and vision.get("ok") is False:
        # Vision says mismatch — force regen only if we haven't already
        out["ok"] = False
        if out.get("action") == "accept":
            out["action"] = "rewrite_prompt_and_regenerate"
        out.setdefault("reasons", []).append(
            f"vision_mismatch:{vision.get('reason')}:{vision.get('missing')}"
        )
    elif vision.get("api_used") and vision.get("ok") and not out.get("ok"):
        # Soft: vision can rescue weak lexical score but NOT brand_ui_stock_forbidden
        reasons = " ".join(out.get("reasons") or [])
        if "brand_ui_stock_forbidden" not in reasons:
            out["ok"] = True
            out["action"] = "accept"
            out.setdefault("reasons", []).append("vision_rescue_accept")
    return out
