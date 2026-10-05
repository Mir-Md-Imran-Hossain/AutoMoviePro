"""
Load ALL API keys from workspace .env files + channel DB fields.
Never logs secret values — only counts / last-4 for diagnostics.

Canonical secret-loading paths: app.config.software_env_paths (H2).
Canonical redaction helpers live here (mask_key / redact_*) — extend, do not fork.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SOFTWARE_ROOT = Path(__file__).resolve().parents[1]

try:
    from app.config import software_env_paths

    DEFAULT_ENV_PATHS = tuple(software_env_paths())
except Exception:
    DEFAULT_ENV_PATHS = (_SOFTWARE_ROOT / ".env",)

# Token-like patterns for text redaction (shared authority)
_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_\-/.])([A-Za-z0-9_\-]{24,}|"
    r"sk-[A-Za-z0-9_\-]{16,}|"
    r"AIza[0-9A-Za-z_\-]{20,}|"
    r"gsk_[A-Za-z0-9]{20,}|"
    r"hf_[A-Za-z0-9]{20,}|"
    r"Bearer\s+[A-Za-z0-9\-._~+/]+=*)"
    r"(?![A-Za-z0-9_\-])",
    re.IGNORECASE,
)
_SENSITIVE_KEY_PARTS = ("api_key", "apikey", "token", "password", "secret", "authorization", "bearer", "credential")


def parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path or not Path(path).exists():
        return out
    try:
        text = Path(path).read_text(encoding="utf-8-sig", errors="ignore")
    except Exception as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        if key and val:
            out[key] = val
    return out


def merge_env_maps(*maps: Dict[str, str]) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for m in maps:
        for k, v in (m or {}).items():
            if k and v and k not in merged:
                merged[k] = v
    return merged


def _collect_numbered(env: Dict[str, str], prefixes: List[str], *, max_n: int = 40) -> List[str]:
    found: List[str] = []
    seen = set()

    def _add(val: str) -> None:
        v = (val or "").strip()
        if not v or v in seen:
            return
        seen.add(v)
        found.append(v)

    for prefix in prefixes:
        bare = (env.get(prefix) or "").strip()
        if bare:
            _add(bare)
        for i in range(1, max_n + 1):
            for name in (f"{prefix}_{i}", f"{prefix}{i}"):
                _add(env.get(name) or "")
    return found


def load_api_bundle(
    *,
    channel: Optional[Dict] = None,
    extra_env_paths: Optional[List[Path]] = None,
) -> Dict[str, object]:
    try:
        from app.config import software_env_paths

        paths = list(software_env_paths(extra_env_paths))
    except Exception:
        paths = list(DEFAULT_ENV_PATHS)
        if extra_env_paths:
            paths.extend(extra_env_paths)

    maps: List[Dict[str, str]] = []
    loaded_paths: List[str] = []
    for p in paths:
        m = parse_env_file(Path(p))
        if m:
            maps.append(m)
            loaded_paths.append(str(Path(p)))

    import os

    maps.append({k: v for k, v in os.environ.items() if v})
    env = merge_env_maps(*maps)

    google = _collect_numbered(
        env, ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_API_KEY"], max_n=40
    )
    agnes = _collect_numbered(env, ["AGNES_API_KEY", "AGNES_API"], max_n=20)
    openrouter = _collect_numbered(env, ["OPENROUTER_API_KEY"], max_n=10)
    huggingface = _collect_numbered(
        env, ["HUGGINGFACE_API_KEY", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"], max_n=20
    )
    groq = _collect_numbered(env, ["GROQ_API_KEY"], max_n=20)
    cerebras = _collect_numbered(env, ["CEREBRAS_API_KEY"], max_n=20)
    xai = _collect_numbered(env, ["XAI_API_KEY", "GROK_API_KEY"], max_n=20)
    freetheai = _collect_numbered(env, ["FREETHEAI_API_KEY"], max_n=10)
    freetheai_base = (
        (env.get("FREETHEAI_API_BASE_URL") or "").strip()
        or "https://api.freetheai.xyz/v1"
    )

    ch = channel or {}
    try:
        from pipeline.channel_api_slots import channel_provider_keys

        slots = channel_provider_keys(ch)
    except Exception:
        slots = {}

    for v in slots.get("google") or []:
        if v and v not in google:
            google.insert(0, v)
    for field in ("google_api_1", "google_api_2"):
        v = (ch.get(field) or "").strip()
        if v and v not in google:
            google.insert(0, v)
    for extra in ch.get("google_api_extra") or []:
        v = (extra or "").strip()
        if v and v not in google:
            google.append(v)

    for v in slots.get("agnes") or []:
        if v and v not in agnes:
            agnes.insert(0, v)
    ch_agnes = (ch.get("agnes_api") or "").strip()
    if ch_agnes and ch_agnes not in agnes:
        agnes.insert(0, ch_agnes)

    for v in slots.get("openrouter") or []:
        if v and v not in openrouter:
            openrouter.insert(0, v)
    for v in slots.get("huggingface") or []:
        if v and v not in huggingface:
            huggingface.insert(0, v)
    for v in slots.get("groq") or []:
        if v and v not in groq:
            groq.insert(0, v)
    for v in slots.get("cerebras") or []:
        if v and v not in cerebras:
            cerebras.insert(0, v)
    for v in slots.get("xai") or slots.get("grok") or []:
        if v and v not in xai:
            xai.insert(0, v)
    for v in slots.get("freetheai") or []:
        if v and v not in freetheai:
            freetheai.insert(0, v)

    ch_hf = (ch.get("huggingface_api") or ch.get("hf_api") or "").strip()
    if ch_hf and ch_hf not in huggingface:
        huggingface.insert(0, ch_hf)

    pollinations_list = _collect_numbered(env, ["POLLINATIONS_API_KEY"], max_n=10)
    for v in slots.get("pollinations") or []:
        if v and v not in pollinations_list:
            pollinations_list.insert(0, v)
    ch_po = (ch.get("pollinations_api") or "").strip()
    if ch_po and ch_po not in pollinations_list:
        pollinations_list.insert(0, ch_po)
    pollinations = pollinations_list[0] if pollinations_list else ""

    pexels_list = _collect_numbered(env, ["PEXELS_API_KEY"], max_n=10)
    for v in slots.get("pexels") or []:
        if v and v not in pexels_list:
            pexels_list.insert(0, v)
    ch_px = (ch.get("pexels_api") or "").strip()
    if ch_px and ch_px not in pexels_list:
        pexels_list.insert(0, ch_px)
    pexels = pexels_list[0] if pexels_list else ""

    # Cap channel-facing slots at 5 in returned lists for UI consistency (env may add more)
    def _cap5(xs: List[str]) -> List[str]:
        return list(xs)[:5] if len(xs) > 5 else list(xs)

    counts = {
        "google": len(google),
        "agnes": len(agnes),
        "openrouter": len(openrouter),
        "huggingface": len(huggingface),
        "groq": len(groq),
        "cerebras": len(cerebras),
        "xai": len(xai),
        "freetheai": len(freetheai),
        "pollinations": len(pollinations_list),
        "pexels": len(pexels_list),
        "env_files": len(loaded_paths),
    }
    logger.info(
        "API bundle: google=%s agnes=%s groq=%s cerebras=%s xai=%s or=%s hf=%s fta=%s po=%s px=%s files=%s",
        counts["google"],
        counts["agnes"],
        counts["groq"],
        counts["cerebras"],
        counts["xai"],
        counts["openrouter"],
        counts["huggingface"],
        counts["freetheai"],
        counts["pollinations"],
        counts["pexels"],
        counts["env_files"],
    )
    return {
        "google_keys": google,
        "agnes_keys": agnes,
        "openrouter_keys": openrouter,
        "huggingface_keys": huggingface,
        "groq_keys": groq,
        "cerebras_keys": cerebras,
        "xai_keys": xai,
        "freetheai_keys": freetheai,
        "freetheai_base_url": freetheai_base,
        "pollinations_key": pollinations,
        "pollinations_keys": pollinations_list,
        "pexels_key": pexels,
        "pexels_keys": pexels_list,
        "env_files_loaded": loaded_paths,
        "counts": counts,
        "channel_slots": {k: _cap5(v) for k, v in (slots or {}).items()},
    }


def slots_from_bundle(bundle: Optional[Dict[str, object]] = None) -> Dict[str, List[str]]:
    """First 5 keys per provider from env+channel bundle — for UI/channel slots."""
    from pipeline.channel_api_slots import PROVIDER_DEFS, _dedupe_keep

    b = dict(bundle or load_api_bundle())
    mapped = {
        "google": list(b.get("google_keys") or []),
        "groq": list(b.get("groq_keys") or []),
        "openrouter": list(b.get("openrouter_keys") or []),
        "pollinations": list(b.get("pollinations_keys") or []),
        "pexels": list(b.get("pexels_keys") or []),
        "agnes": list(b.get("agnes_keys") or []),
        "huggingface": list(b.get("huggingface_keys") or []),
        "cerebras": list(b.get("cerebras_keys") or []),
        "freetheai": list(b.get("freetheai_keys") or []),
    }
    return {pid: _dedupe_keep(mapped.get(pid) or []) for pid, _, _ in PROVIDER_DEFS}


def seed_channel_from_env(channel_id: Optional[int] = None) -> Dict[str, object]:
    """Copy master .env keys into the channel so Settings/Live Lab show them."""
    from app import db as store
    from pipeline.channel_api_slots import (
        channel_provider_keys,
        evaluate_readiness,
        merge_keep_existing,
        serialize_api_keys_json,
        sync_legacy_fields,
    )

    rows = store.list_channels()
    if not rows:
        return {"ok": False, "error": "channel_missing", "seeded": {}}
    ch = dict(rows[0] if channel_id is None else (store.get_channel(int(channel_id)) or rows[0]))
    incoming = slots_from_bundle(load_api_bundle(channel={}))
    existing = channel_provider_keys(ch)
    # Env fills empty providers; keep any extra keys already on the channel.
    merged = merge_keep_existing(incoming, existing)
    for pid, keys in existing.items():
        extra = [k for k in keys if k not in (merged.get(pid) or [])]
        if extra:
            merged[pid] = list(merged.get(pid) or []) + extra
    legacy = sync_legacy_fields(merged)
    ch["api_keys_json"] = serialize_api_keys_json(merged)
    ch["google_api_1"] = legacy["google_api_1"] or ch.get("google_api_1")
    ch["google_api_2"] = legacy["google_api_2"] or ch.get("google_api_2")
    ch["agnes_api"] = legacy["agnes_api"] or ch.get("agnes_api")
    ch["pexels_api"] = legacy["pexels_api"] or ch.get("pexels_api")
    ch["pollinations_api"] = legacy["pollinations_api"] or ch.get("pollinations_api")
    cid = store.upsert_channel(ch, int(ch["id"]))
    ready = evaluate_readiness(channel=store.get_channel(cid) or ch)
    counts = {pid: len(merged.get(pid) or []) for pid in merged}
    logger.info("Seeded channel API slots: %s active=%s", counts, ready.get("active"))
    return {"ok": True, "channel_id": cid, "counts": counts, "active": bool(ready.get("active"))}


def mask_key(key: str) -> str:
    k = (key or "").strip()
    if len(k) < 8:
        return "****"
    return f"…{k[-4:]}"


def redact_sensitive_text(text: str) -> str:
    """Redact token-like / Bearer values from free text (logs, exceptions, chat)."""
    return _TOKEN_RE.sub("[REDACTED]", text or "")


def redact_mapping(data: Dict[str, Any] | None) -> Dict[str, Any]:
    """Redact values whose keys look secret-bearing; recurse one level of dicts."""
    out: Dict[str, Any] = {}
    for k, v in (data or {}).items():
        ks = str(k).lower()
        if any(p in ks for p in _SENSITIVE_KEY_PARTS):
            out[k] = "[REDACTED]"
        elif isinstance(v, dict):
            out[k] = redact_mapping(v)
        elif isinstance(v, str):
            out[k] = redact_sensitive_text(v)
        else:
            out[k] = v
    return out
