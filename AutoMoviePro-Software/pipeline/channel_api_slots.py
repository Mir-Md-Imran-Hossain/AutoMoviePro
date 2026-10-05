"""
Per-channel provider API slots: max 5 each, min 2 required for app active.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# (form/db key prefix, label, required for app active)
# Legacy provider buckets — dedicated per-task slots (dedicated_api_registry)
# are authoritative for readiness. These stay for backward-compatible channel JSON.
PROVIDER_DEFS: Tuple[Tuple[str, str, bool], ...] = (
    ("google", "Google AI Studio", False),  # superseded by localize/image/tts slots
    ("groq", "Groq", False),
    ("openrouter", "OpenRouter", False),  # can satisfy Grok transport
    ("pollinations", "Pollinations", False),  # free URL OK
    ("pexels", "Pexels", False),
    ("agnes", "Agnes", False),  # free URL OK
    ("huggingface", "Hugging Face", False),
    ("cerebras", "Cerebras", False),
    ("freetheai", "FreeTheAI", False),
    ("workers_ai", "Cloudflare Workers AI", False),
)

MAX_SLOTS = 5
MIN_REQUIRED = 2
# Stock / free-URL providers: one key is enough (Pollinations also has a no-key URL).
MIN_BY_PROVIDER = {
    "google": 2,
    "groq": 2,
    "openrouter": 2,
    "agnes": 2,
    "pollinations": 1,
    "pexels": 1,
}


def min_for_provider(pid: str, *, required: bool) -> int:
    if not required:
        return 0
    return int(MIN_BY_PROVIDER.get(pid, MIN_REQUIRED))


def empty_slot_map() -> Dict[str, List[str]]:
    return {pid: [] for pid, _, _ in PROVIDER_DEFS}


def _dedupe_keep(keys: Sequence[str], *, limit: int = MAX_SLOTS) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in keys:
        v = (raw or "").strip()
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
        if len(out) >= limit:
            break
    return out


def parse_api_keys_json(raw: Any) -> Dict[str, List[str]]:
    data = empty_slot_map()
    obj: Any = raw
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
        except Exception:
            return data
    if not isinstance(obj, dict):
        return data
    for pid, _, _ in PROVIDER_DEFS:
        vals = obj.get(pid) or obj.get(f"{pid}_keys") or []
        if isinstance(vals, str):
            vals = [vals]
        if isinstance(vals, list):
            data[pid] = _dedupe_keep([str(x) for x in vals])
    return data


def legacy_keys_from_channel(channel: Mapping[str, Any]) -> Dict[str, List[str]]:
    """Map old single/dual fields into slot lists."""
    data = empty_slot_map()
    g = []
    for f in ("google_api_1", "google_api_2"):
        v = (channel.get(f) or "").strip()
        if v:
            g.append(v)
    for extra in channel.get("google_api_extra") or []:
        if (extra or "").strip():
            g.append(str(extra).strip())
    data["google"] = _dedupe_keep(g)
    for pid, field in (
        ("agnes", "agnes_api"),
        ("pexels", "pexels_api"),
        ("pollinations", "pollinations_api"),
        ("openrouter", "openrouter_api"),
        ("huggingface", "huggingface_api"),
        ("groq", "groq_api"),
        ("cerebras", "cerebras_api"),
        ("freetheai", "freetheai_api"),
    ):
        v = (channel.get(field) or "").strip()
        if v:
            data[pid] = _dedupe_keep([v])
    return data


def channel_provider_keys(channel: Optional[Mapping[str, Any]]) -> Dict[str, List[str]]:
    ch = channel or {}
    merged = empty_slot_map()
    # Prefer explicit JSON blob
    from_json = parse_api_keys_json(ch.get("api_keys_json"))
    legacy = legacy_keys_from_channel(ch)
    for pid, _, _ in PROVIDER_DEFS:
        merged[pid] = _dedupe_keep(list(from_json.get(pid) or []) + list(legacy.get(pid) or []))
    # Also accept numbered form fields already flattened onto channel
    for pid, _, _ in PROVIDER_DEFS:
        numbered = []
        for i in range(1, MAX_SLOTS + 1):
            v = (ch.get(f"{pid}_api_{i}") or "").strip()
            if v:
                numbered.append(v)
        if numbered:
            merged[pid] = _dedupe_keep(list(merged[pid]) + numbered)
    return merged


def collect_from_form(form: Mapping[str, Any]) -> Dict[str, List[str]]:
    data = empty_slot_map()
    for pid, _, _ in PROVIDER_DEFS:
        vals = []
        for i in range(1, MAX_SLOTS + 1):
            key = f"{pid}_api_{i}"
            raw = form.get(key)
            if raw is None:
                continue
            if hasattr(raw, "strip"):
                v = str(raw).strip()
            else:
                v = str(raw).strip()
            if v:
                vals.append(v)
        data[pid] = _dedupe_keep(vals)
    return data


def serialize_api_keys_json(slots: Mapping[str, Sequence[str]]) -> str:
    clean = {pid: _dedupe_keep(slots.get(pid) or []) for pid, _, _ in PROVIDER_DEFS}
    return json.dumps(clean, ensure_ascii=False)


def sync_legacy_fields(slots: Mapping[str, Sequence[str]]) -> Dict[str, str]:
    """Keep old columns in sync for older code paths."""
    g = list(slots.get("google") or [])
    a = list(slots.get("agnes") or [])
    p = list(slots.get("pexels") or [])
    po = list(slots.get("pollinations") or [])
    return {
        "google_api_1": g[0] if len(g) > 0 else "",
        "google_api_2": g[1] if len(g) > 1 else "",
        "agnes_api": a[0] if a else "",
        "pexels_api": p[0] if p else "",
        "pollinations_api": po[0] if po else "",
    }


def merge_keep_existing(
    incoming: Mapping[str, Sequence[str]],
    existing: Mapping[str, Sequence[str]],
) -> Dict[str, List[str]]:
    """Empty incoming slots keep existing keys (form leave-blank = don't wipe)."""
    out = empty_slot_map()
    for pid, _, _ in PROVIDER_DEFS:
        inc = _dedupe_keep(incoming.get(pid) or [])
        if inc:
            out[pid] = inc
        else:
            out[pid] = _dedupe_keep(existing.get(pid) or [])
    return out


def evaluate_readiness(
    *,
    channel: Optional[Mapping[str, Any]] = None,
    bundle: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    App is active when dedicated per-task API slots meet their minimums
    (language-gated TTS included). Legacy provider buckets are informational only.
    """
    from pipeline.api_keys import load_api_bundle

    ch = dict(channel or {})
    slots = channel_provider_keys(ch)
    b = dict(bundle) if bundle is not None else dict(load_api_bundle(channel=ch))

    # Authoritative: dedicated task slots
    dedicated: Dict[str, Any] = {}
    try:
        from pipeline.dedicated_api_registry import evaluate_dedicated_readiness
        from pipeline.lang_entitlement import channel_languages

        unlocked = channel_languages(ch)
        dedicated = evaluate_dedicated_readiness(channel=ch, unlocked=unlocked)
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("dedicated readiness failed: %s", exc)
        dedicated = {
            "active": False,
            "missing": ["dedicated_api_registry_error"],
            "warnings": [],
            "details": {},
            "counts": {},
        }

    counts: Dict[str, int] = dict(dedicated.get("counts") or {})
    missing: List[str] = list(dedicated.get("missing") or [])
    details: Dict[str, Dict[str, Any]] = dict(dedicated.get("details") or {})
    warnings: List[str] = list(dedicated.get("warnings") or [])

    bundle_map = {
        "google": list(b.get("google_keys") or []),
        "groq": list(b.get("groq_keys") or []),
        "openrouter": list(b.get("openrouter_keys") or []),
        "pollinations": list(b.get("pollinations_keys") or ([b["pollinations_key"]] if b.get("pollinations_key") else [])),
        "pexels": list(b.get("pexels_keys") or ([b["pexels_key"]] if b.get("pexels_key") else [])),
        "agnes": list(b.get("agnes_keys") or []),
        "huggingface": list(b.get("huggingface_keys") or []),
        "cerebras": list(b.get("cerebras_keys") or []),
        "freetheai": list(b.get("freetheai_keys") or []),
        "workers_ai": list(b.get("workers_ai_keys") or []),
    }

    # Legacy provider info (never blocks when dedicated is OK)
    for pid, label, required in PROVIDER_DEFS:
        combined = _dedupe_keep(list(slots.get(pid) or []) + list(bundle_map.get(pid) or []), limit=40)
        n = len(combined)
        need = min_for_provider(pid, required=required)
        counts[f"legacy_{pid}"] = n
        if pid not in details:
            details[f"legacy_{pid}"] = {
                "label": label,
                "count": n,
                "required": False,
                "min": need,
                "max": MAX_SLOTS,
                "ok": True,
            }

    active = bool(dedicated.get("active")) and len(missing) == 0
    tts_ready = False
    tts_snap: Dict[str, Any] = {}
    try:
        from pipeline.tts_credential_diagnostics import readiness_snapshot

        tts_snap = readiness_snapshot()
        tts_ready = bool(tts_snap.get("google_tts_ready"))
    except Exception:
        tts_snap = {"google_tts_ready": False, "reason": "snapshot_error"}
    return {
        "active": active,
        "inactive": not active,
        "missing": missing,
        "warnings": warnings,
        "counts": counts,
        "details": details,
        "dedicated": dedicated,
        "min_required": MIN_REQUIRED,
        "max_slots": MAX_SLOTS,
        "google_tts_ready": tts_ready,
        "google_tts_readiness": tts_snap,
        "message_key": "app_active" if active else "app_inactive_apis",
        "message": (
            "Application active"
            if active
            else "Application inactive — add the missing API keys: " + ", ".join(missing)
        ),
    }


def mask_slots(slots: Mapping[str, Sequence[str]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for pid, _, _ in PROVIDER_DEFS:
        masked = []
        for k in slots.get(pid) or []:
            s = str(k)
            masked.append((s[:4] + "…") if len(s) > 4 else "••••")
        out[pid] = masked
    return out
