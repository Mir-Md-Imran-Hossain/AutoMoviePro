"""
Channel language entitlements: setup = English + 1, max 6 via paid unlocks.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from pipeline.lang_config import LANG_DISPLAY, LANG_FOLDERS, SOURCE_LANG, TARGET_LANG_CODES

MAX_LANGUAGES = 6
SETUP_LANGUAGE_COUNT = 2
DEFAULT_LANGUAGE_PRICE = "499"


def catalog() -> List[Dict[str, Any]]:
    return [
        {
            "code": code,
            "name": LANG_DISPLAY.get(code, code),
            "folder": LANG_FOLDERS.get(code, code),
            "is_english": code == SOURCE_LANG,
        }
        for code in TARGET_LANG_CODES
    ]


def secondary_options() -> List[Dict[str, Any]]:
    return [c for c in catalog() if not c["is_english"]]


def normalize_code(code: str) -> str:
    return (code or "").strip().lower()


def parse_languages(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        vals = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            vals = json.loads(raw)
        except Exception:
            vals = [x.strip() for x in raw.split(",") if x.strip()]
    else:
        return []
    out: List[str] = []
    seen = set()
    for v in vals:
        c = normalize_code(str(v))
        if c in TARGET_LANG_CODES and c not in seen:
            seen.add(c)
            out.append(c)
    if SOURCE_LANG not in seen and out:
        out.insert(0, SOURCE_LANG)
    elif SOURCE_LANG not in seen:
        out = [SOURCE_LANG]
    # keep English first
    rest = [c for c in out if c != SOURCE_LANG]
    return [SOURCE_LANG] + rest


def serialize_languages(codes: Sequence[str]) -> str:
    return json.dumps(parse_languages(list(codes)), ensure_ascii=False)


def setup_languages(secondary: str) -> List[str]:
    sec = normalize_code(secondary)
    if sec == SOURCE_LANG or sec not in TARGET_LANG_CODES:
        raise ValueError("secondary_lang_required")
    return [SOURCE_LANG, sec]


def channel_languages(channel: Optional[Dict[str, Any]]) -> List[str]:
    ch = channel or {}
    langs = parse_languages(ch.get("languages_json"))
    if len(langs) >= SETUP_LANGUAGE_COUNT:
        return langs
    # legacy channels without languages_json → English only until fixed at setup
    return langs or [SOURCE_LANG]


def can_request(code: str, unlocked: Sequence[str]) -> Dict[str, Any]:
    c = normalize_code(code)
    unlocked_n = parse_languages(list(unlocked))
    if c not in TARGET_LANG_CODES:
        return {"ok": False, "error": "invalid_language"}
    if c == SOURCE_LANG:
        return {"ok": False, "error": "english_included"}
    if c in unlocked_n:
        return {"ok": False, "error": "already_unlocked"}
    if len(unlocked_n) >= MAX_LANGUAGES:
        return {"ok": False, "error": "max_languages_reached"}
    return {"ok": True, "code": c, "name": LANG_DISPLAY.get(c, c)}


def unlock_language(unlocked: Sequence[str], code: str) -> List[str]:
    check = can_request(code, unlocked)
    if not check.get("ok"):
        raise ValueError(check.get("error") or "cannot_unlock")
    return parse_languages(list(unlocked) + [normalize_code(code)])
