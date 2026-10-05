"""Per-language YouTube/Facebook destination bindings."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional


def parse_lang_destinations(raw: Any) -> Dict[str, Dict[str, str]]:
    if isinstance(raw, dict):
        obj = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
        except Exception:
            return {}
    else:
        return {}
    if not isinstance(obj, dict):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for code, slot in obj.items():
        if not isinstance(slot, dict):
            continue
        out[str(code).lower()] = {
            "youtube_name": str(slot.get("youtube_name") or "").strip(),
            "facebook_name": str(slot.get("facebook_name") or "").strip(),
            "tiktok_name": str(slot.get("tiktok_name") or "").strip(),
            "youtube_session": str(slot.get("youtube_session") or "").strip(),
            "facebook_session": str(slot.get("facebook_session") or "").strip(),
            "tiktok_session": str(slot.get("tiktok_session") or "").strip(),
        }
    return out


def serialize_lang_destinations(data: Mapping[str, Mapping[str, Any]]) -> str:
    clean = {}
    for code, slot in (data or {}).items():
        clean[str(code).lower()] = {
            "youtube_name": str((slot or {}).get("youtube_name") or "").strip(),
            "facebook_name": str((slot or {}).get("facebook_name") or "").strip(),
            "tiktok_name": str((slot or {}).get("tiktok_name") or "").strip(),
            "youtube_session": str((slot or {}).get("youtube_session") or "").strip(),
            "facebook_session": str((slot or {}).get("facebook_session") or "").strip(),
            "tiktok_session": str((slot or {}).get("tiktok_session") or "").strip(),
        }
    return json.dumps(clean, ensure_ascii=False)


def resolve_destination(channel: Mapping[str, Any], lang_code: str = "en") -> Dict[str, Any]:
    """
    Overlay language-specific YT/FB/TikTok names + sessions onto channel copy for upload.
    Falls back to channel-level youtube_name / facebook_name / tiktok_name / sessions.
    """
    ch = dict(channel or {})
    code = (lang_code or "en").lower().strip() or "en"
    dest = parse_lang_destinations(ch.get("lang_destinations_json"))
    slot = dest.get(code) or {}
    if slot.get("youtube_name"):
        ch["youtube_name"] = slot["youtube_name"]
    if slot.get("facebook_name"):
        ch["facebook_name"] = slot["facebook_name"]
    if slot.get("tiktok_name"):
        ch["tiktok_name"] = slot["tiktok_name"]
    if slot.get("youtube_session"):
        ch["youtube_session"] = slot["youtube_session"]
    if slot.get("facebook_session"):
        ch["facebook_session"] = slot["facebook_session"]
    if slot.get("tiktok_session"):
        ch["tiktok_session"] = slot["tiktok_session"]
    ch["_upload_lang"] = code
    return ch


def merge_destination_form(
    existing_raw: Any,
    languages: List[str],
    form_get,
) -> Dict[str, Dict[str, str]]:
    """Read lang_yt_{code} / lang_fb_{code} / lang_tt_{code} from form; keep sessions from existing."""
    existing = parse_lang_destinations(existing_raw)
    out: Dict[str, Dict[str, str]] = {}
    for code in languages:
        c = (code or "").lower().strip()
        if not c:
            continue
        prev = existing.get(c) or {}
        yt = str(form_get(f"lang_yt_{c}") or form_get(f"lang_youtube_{c}") or "").strip()
        fb = str(form_get(f"lang_fb_{c}") or form_get(f"lang_facebook_{c}") or "").strip()
        tt = str(form_get(f"lang_tt_{c}") or form_get(f"lang_tiktok_{c}") or "").strip()
        out[c] = {
            "youtube_name": yt or prev.get("youtube_name") or "",
            "facebook_name": fb or prev.get("facebook_name") or "",
            "tiktok_name": tt or prev.get("tiktok_name") or "",
            "youtube_session": prev.get("youtube_session") or "",
            "facebook_session": prev.get("facebook_session") or "",
            "tiktok_session": prev.get("tiktok_session") or "",
        }
    # Preserve languages not in list
    for c, slot in existing.items():
        if c not in out:
            out[c] = slot
    return out

