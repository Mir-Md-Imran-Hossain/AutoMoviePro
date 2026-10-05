"""Cloudflare Workers AI TTS — MeloTTS + Deepgram Aura-1 (free-tier friendly).

Reuses the same Workers AI API token + Account ID pairs already configured for
image generation (WorkersAI_API_KEY_N / Account_ID_N), with optional per-language
overrides:

  TTS_CF_{LANG}_PRIMARY / TTS_CF_{LANG}_PRIMARY_ACCOUNT   → MeloTTS
  TTS_CF_{LANG}_SECONDARY / TTS_CF_{LANG}_SECONDARY_ACCOUNT → Aura-1

Language support (honest):
  MeloTTS (@cf/myshell-ai/melotts): EN, ES, FR, ZH, JP, KR only
  Aura-1 (@cf/deepgram/aura-1): English speakers only
  Indic (bn/hi/ta/ml/ur): Cloudflare TTS is skipped unless AMP_TTS_CF_FORCE=1
"""

from __future__ import annotations

import base64
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

logger = logging.getLogger(__name__)

MELOTTS_MODEL = "@cf/myshell-ai/melotts"
AURA_MODEL = "@cf/deepgram/aura-1"

# Official MeloTTS language codes on Cloudflare / MyShell
MELOTTS_LANGS = frozenset({"en", "es", "fr", "zh", "jp", "ja", "kr", "ko"})
AURA_LANGS = frozenset({"en"})

# Map pipeline ISO → MeloTTS `lang` query value
_MELO_LANG_MAP = {
    "en": "en",
    "es": "es",
    "fr": "fr",
    "zh": "zh",
    "ja": "jp",
    "jp": "jp",
    "ko": "kr",
    "kr": "kr",
}

# Aura-1 English speakers (female-leaning defaults first for narration)
_AURA_SPEAKER_BY_LANG = {
    "en": "asteria",
}


def melotts_supports(lang: str) -> bool:
    code = (lang or "en").strip().lower()[:2]
    if code == "ja":
        code = "jp"
    if code == "ko":
        code = "kr"
    return code in MELOTTS_LANGS or (lang or "").strip().lower() in MELOTTS_LANGS


def aura_supports(lang: str) -> bool:
    code = (lang or "en").strip().lower()[:2]
    force = (os.environ.get("AMP_TTS_CF_FORCE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    return code in AURA_LANGS or force


def _force_cf() -> bool:
    return (os.environ.get("AMP_TTS_CF_FORCE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def list_tts_cf_credentials(lang: str = "") -> List[Tuple[str, str, str]]:
    """Return [(api_key, account_id, role)] role=primary|secondary|shared.

    Prefer per-lang TTS_CF_* then fall back to Workers AI image credentials.
    """
    code = (lang or "").strip().upper()
    env: Dict[str, str] = {}
    try:
        from pipeline.dedicated_api_registry import _env_map

        env = dict(_env_map())
    except Exception:
        env = {k: str(v) for k, v in os.environ.items() if v}

    out: List[Tuple[str, str, str]] = []
    seen = set()

    def _add(key: str, acct: str, role: str) -> None:
        k = (key or "").strip()
        a = (acct or "").strip()
        if not k or not a:
            return
        sig = (k, a)
        if sig in seen:
            return
        seen.add(sig)
        out.append((k, a, role))

    if code:
        _add(
            env.get(f"TTS_CF_{code}_PRIMARY") or env.get(f"TTS_WORKERS_AI_{code}_PRIMARY") or "",
            env.get(f"TTS_CF_{code}_PRIMARY_ACCOUNT")
            or env.get(f"TTS_CF_{code}_ACCOUNT_PRIMARY")
            or env.get(f"TTS_WORKERS_AI_{code}_PRIMARY_ACCOUNT")
            or "",
            "primary",
        )
        _add(
            env.get(f"TTS_CF_{code}_SECONDARY")
            or env.get(f"TTS_WORKERS_AI_{code}_SECONDARY")
            or "",
            env.get(f"TTS_CF_{code}_SECONDARY_ACCOUNT")
            or env.get(f"TTS_CF_{code}_ACCOUNT_SECONDARY")
            or env.get(f"TTS_WORKERS_AI_{code}_SECONDARY_ACCOUNT")
            or "",
            "secondary",
        )

    # Global CF TTS pair (optional)
    _add(
        env.get("TTS_CF_API_KEY_1") or env.get("TTS_WORKERS_AI_API_KEY_1") or "",
        env.get("TTS_CF_ACCOUNT_ID_1")
        or env.get("TTS_CF_ACCOUNT_ID")
        or env.get("WorkersAI_ACCOUNT_ID")
        or "",
        "primary",
    )
    _add(
        env.get("TTS_CF_API_KEY_2") or env.get("TTS_WORKERS_AI_API_KEY_2") or "",
        env.get("TTS_CF_ACCOUNT_ID_2")
        or env.get("Account_ID_2")
        or env.get("WorkersAI_ACCOUNT_ID_2")
        or "",
        "secondary",
    )

    # Reuse image Workers AI credentials (product: same free CF APIs)
    try:
        from pipeline.dedicated_api_registry import list_workers_ai_credentials

        for i, (k, a) in enumerate(list_workers_ai_credentials()):
            _add(k, a, "primary" if i == 0 else "secondary")
    except Exception:
        pass

    return out


def _extract_audio_bytes(resp: httpx.Response) -> Optional[bytes]:
    ctype = (resp.headers.get("content-type") or "").lower()
    raw = resp.content or b""
    if not raw:
        return None
    # Direct audio
    if (
        "audio" in ctype
        or "mpeg" in ctype
        or "octet-stream" in ctype
        or raw[:3] == b"ID3"
        or raw[:2] == b"\xff\xfb"
        or raw[:4] == b"RIFF"
        or raw[:4] == b"fLaC"
        or raw[:4] == b"OggS"
    ):
        return raw
    # JSON wrappers: {result: {audio: base64}} or {audio: "..."}
    try:
        data = resp.json()
    except Exception:
        # Some CF responses are raw binary with wrong content-type
        if len(raw) > 500:
            return raw
        return None
    if not isinstance(data, dict):
        return None
    result = data.get("result") if isinstance(data.get("result"), dict) else data
    for key in ("audio", "audio_base64", "data"):
        val = result.get(key) if isinstance(result, dict) else None
        if isinstance(val, str) and len(val) > 64:
            try:
                return base64.b64decode(val)
            except Exception:
                continue
        if isinstance(val, list) and val and isinstance(val[0], (int, float)):
            # rare: raw byte array
            try:
                return bytes(int(x) & 0xFF for x in val)
            except Exception:
                continue
    # Nested success envelope
    if isinstance(data.get("result"), str) and len(data["result"]) > 64:
        try:
            return base64.b64decode(data["result"])
        except Exception:
            pass
    return None


def _post_workers_ai(
    *,
    account_id: str,
    api_key: str,
    model: str,
    payload: Dict[str, Any],
    timeout: float = 120.0,
) -> Tuple[Optional[bytes], str]:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    try:
        r = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except Exception as exc:
        return None, f"http_error:{exc}"
    if r.status_code >= 400:
        return None, f"{r.status_code}:{r.text[:180]}"
    audio = _extract_audio_bytes(r)
    if not audio or len(audio) < 200:
        return None, f"no_audio:{r.status_code}:{(r.headers.get('content-type') or '')[:40]}"
    return audio, "ok"


def _ensure_m4a_or_mp3(raw: bytes, out_path: Path) -> Path:
    """Write CF audio (usually mp3) to out_path (.m4a preferred via ffmpeg copy/re-encode)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".mp3")
    tmp.write_bytes(raw)
    if out_path.suffix.lower() == ".mp3":
        if tmp.resolve() != out_path.resolve():
            out_path.write_bytes(raw)
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
        return out_path
    # Try ffmpeg → m4a
    try:
        import subprocess

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(tmp),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(out_path.with_suffix(".m4a")),
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=60)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return out_path.with_suffix(".m4a")
    except Exception:
        # Keep mp3 if transcode fails
        final = out_path.with_suffix(".mp3")
        if final.resolve() != tmp.resolve():
            final.write_bytes(raw)
        return final


def synthesize_melotts(
    text: str,
    out_path: Path,
    *,
    language: str = "en",
    api_key: str = "",
    account_id: str = "",
    timeout: float = 120.0,
) -> Path:
    """Synthesize via Cloudflare MeloTTS. Raises RuntimeError on failure."""
    code = (language or "en").strip().lower()
    if not melotts_supports(code) and not _force_cf():
        raise RuntimeError(f"melotts_unsupported_lang:{code}")
    melo_lang = _MELO_LANG_MAP.get(code, _MELO_LANG_MAP.get(code[:2], "en"))
    creds = []
    if api_key and account_id:
        creds = [(api_key, account_id, "explicit")]
    else:
        creds = list_tts_cf_credentials(code)
    if not creds:
        raise RuntimeError("melotts_no_credentials")

    prompt = (text or "").strip()
    if not prompt:
        raise RuntimeError("melotts_empty_text")
    # MeloTTS works better with modest length chunks
    if len(prompt) > 1200:
        prompt = prompt[:1200]

    last = ""
    for key, acct, role in creds[:4]:
        audio, status = _post_workers_ai(
            account_id=acct,
            api_key=key,
            model=(os.environ.get("WorkersAI_MELOTTS_MODEL") or MELOTTS_MODEL).strip(),
            payload={"prompt": prompt, "lang": melo_lang},
            timeout=timeout,
        )
        if audio:
            path = _ensure_m4a_or_mp3(audio, Path(out_path))
            logger.info(
                "TTS OK engine=MELOTTS lang=%s role=%s key…%s → %s (%s bytes)",
                code,
                role,
                key[-4:],
                path.name,
                path.stat().st_size,
            )
            return path
        last = status
        logger.warning("MeloTTS fail role=%s key…%s: %s", role, key[-4:], status[:120])
    raise RuntimeError(f"melotts_failed:{last}")


def synthesize_aura(
    text: str,
    out_path: Path,
    *,
    language: str = "en",
    speaker: str = "",
    api_key: str = "",
    account_id: str = "",
    timeout: float = 120.0,
) -> Path:
    """Synthesize via Cloudflare Deepgram Aura-1. Raises RuntimeError on failure."""
    code = (language or "en").strip().lower()[:2]
    if not aura_supports(code):
        raise RuntimeError(f"aura_unsupported_lang:{code}")
    creds = []
    if api_key and account_id:
        creds = [(api_key, account_id, "explicit")]
    else:
        # Prefer secondary slot for Aura (primary reserved for MeloTTS)
        all_c = list_tts_cf_credentials(code)
        secs = [c for c in all_c if c[2] == "secondary"]
        creds = secs + [c for c in all_c if c[2] != "secondary"]
    if not creds:
        raise RuntimeError("aura_no_credentials")

    prompt = (text or "").strip()
    if not prompt:
        raise RuntimeError("aura_empty_text")
    if len(prompt) > 2000:
        prompt = prompt[:2000]
    spk = (speaker or _AURA_SPEAKER_BY_LANG.get(code) or "asteria").strip()
    model = (os.environ.get("WorkersAI_AURA_MODEL") or AURA_MODEL).strip()

    last = ""
    for key, acct, role in creds[:4]:
        # Prefer mp3 for easy ffmpeg path
        for payload in (
            {"text": prompt, "speaker": spk, "encoding": "mp3"},
            {"text": prompt, "speaker": spk},
            {"text": prompt},
        ):
            audio, status = _post_workers_ai(
                account_id=acct,
                api_key=key,
                model=model,
                payload=payload,
                timeout=timeout,
            )
            if audio:
                path = _ensure_m4a_or_mp3(audio, Path(out_path))
                logger.info(
                    "TTS OK engine=AURA lang=%s speaker=%s role=%s key…%s → %s (%s bytes)",
                    code,
                    spk,
                    role,
                    key[-4:],
                    path.name,
                    path.stat().st_size,
                )
                return path
            last = status
        logger.warning("Aura fail role=%s key…%s: %s", role, key[-4:], last[:120])
    raise RuntimeError(f"aura_failed:{last}")


def provider_capabilities() -> Dict[str, Any]:
    return {
        "melotts": {
            "model": MELOTTS_MODEL,
            "languages": sorted(MELOTTS_LANGS),
            "note": "EN/ES/FR/ZH/JP/KR only — not Indic scripts",
        },
        "aura": {
            "model": AURA_MODEL,
            "languages": ["en"],
            "speakers": [
                "angus",
                "asteria",
                "arcas",
                "orion",
                "orpheus",
                "athena",
                "luna",
                "zeus",
                "perseus",
                "helios",
                "hera",
                "stella",
            ],
            "note": "English-only Deepgram Aura-1",
        },
    }
