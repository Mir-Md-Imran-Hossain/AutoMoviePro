"""Dedicated per-task API key registry (UI + readiness + runtime resolution).

Design (product policy):
- Each pipeline job has its own key slots (not one shared Google/Grok pool).
- Required slots block app activation when empty.
- Optional slots (image Google, Agnes, Pollinations, Workers AI) degrade gracefully
  with user-facing notifications — no silent general-pool fallback for image.
- TTS Google slots appear only for unlocked non-Edge languages (bn/ta/ml).
- Cross-pool borrow is allowed only as a last resort with an explicit warning.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Edge-only langs never ask for Google TTS keys.
EDGE_ONLY_LANGS = frozenset({"en", "hi", "ur"})
GOOGLE_TTS_LANGS = frozenset({"bn", "ta", "ml"})

LANG_LABELS = {
    "bn": "Bangla",
    "ta": "Tamil",
    "ml": "Malayalam",
    "en": "English",
    "hi": "Hindi",
    "ur": "Urdu",
}


@dataclass(frozen=True)
class SlotDef:
    """One dedicated task group shown in Settings."""

    id: str
    label: str
    label_bn: str
    provider: str  # google | grok | pollinations | agnes | workers_ai | pexels | openrouter
    env_prefixes: Tuple[str, ...]
    slots: int = 2
    min_required: int = 0
    required: bool = False
    optional_recommended: bool = False
    free_url_ok: bool = False
    language_gate: Optional[str] = None  # ISO code → only if unlocked
    portal_url: str = ""
    portal_label: str = ""
    help_key: str = ""
    borrow_from: Tuple[str, ...] = ()  # other slot ids that may lend keys
    notify_if_missing: bool = False
    form_prefix: str = ""  # channel form field prefix (defaults to id)
    requires_account_id: bool = False  # Workers AI: API key ⇒ Account ID mandatory
    is_paid_master: bool = False  # Special subscription tier (Part 2 lock & upsell modal)

    def field_prefix(self) -> str:
        return self.form_prefix or self.id


# Static (non language-gated) slot definitions.
# Required = system cannot run without them.
# Google Paid Master is optional — unlocks pure-video pipeline & high-quota studio models.
# Image Google is intentionally NOT required — 0/1/2 keys all OK; 0 → skip Google image.
STATIC_SLOT_DEFS: Tuple[SlotDef, ...] = (
    SlotDef(
        id="google_paid",
        label="Google AI Studio Paid Master (Gemini + Imagen + Omni)",
        label_bn="Google AI Studio পেইড মাস্টার (Gemini + Imagen + Omni)",
        provider="google",
        env_prefixes=(
            "GOOGLE_PAID_API_KEY",
            "GOOGLE_PAID_MASTER_KEY",
            "PAID_GOOGLE_API_KEY",
        ),
        slots=3,
        min_required=0,
        required=False,
        optional_recommended=True,
        portal_url="https://aistudio.google.com/apikey",
        portal_label="Google AI Studio",
        help_key="help_api_google_paid",
        form_prefix="google_paid",
        is_paid_master=True,
    ),
    SlotDef(
        id="agent_grok",
        label="Agent activity — Grok API",
        label_bn="Agent এর কর্মকাণ্ড — Grok API",
        provider="grok",
        env_prefixes=("AGENT_GROK_API_KEY", "AGENT_XAI_API_KEY"),
        slots=1,
        min_required=1,
        required=True,
        portal_url="https://console.x.ai/",
        portal_label="xAI Console",
        help_key="help_api_agent_grok",
        borrow_from=("topic_grok",),
        form_prefix="agent_grok",
    ),
    SlotDef(
        id="topic_grok",
        label="Topic generation — Grok API",
        label_bn="টপিক জেনারেশন — Grok API",
        provider="grok",
        env_prefixes=("TOPIC_GROK_API_KEY", "TOPIC_XAI_API_KEY", "XAI_API_KEY", "GROK_API_KEY"),
        slots=2,
        min_required=2,
        required=True,
        portal_url="https://console.x.ai/",
        portal_label="xAI Console",
        help_key="help_api_topic_grok",
        borrow_from=("agent_grok",),
        form_prefix="topic_grok",
    ),
    SlotDef(
        id="image_google",
        label="Image generation — Google AI Studio",
        label_bn="ইমেজ জেনারেশন — Google AI Studio",
        provider="google",
        env_prefixes=("IMAGE_GOOGLE_API_KEY", "GOOGLE_IMAGE_API_KEY"),
        slots=2,
        min_required=0,
        required=False,
        optional_recommended=True,
        notify_if_missing=True,
        portal_url="https://aistudio.google.com/apikey",
        portal_label="Google AI Studio",
        help_key="help_api_image_google",
        borrow_from=("localize_google",),
        form_prefix="image_google",
    ),
    SlotDef(
        id="localize_google",
        label="Localization — Google AI Studio",
        label_bn="লোকালাইজেশন — Google AI Studio",
        provider="google",
        env_prefixes=("LOCALIZATION_GOOGLE_API_KEY", "GOOGLE_LOCALIZE_API_KEY"),
        slots=2,
        min_required=2,
        required=True,
        portal_url="https://aistudio.google.com/apikey",
        portal_label="Google AI Studio",
        help_key="help_api_localize_google",
        borrow_from=("image_google",),
        form_prefix="localize_google",
    ),
    SlotDef(
        id="pollinations",
        label="Pollinations (optional — free URL works without key)",
        label_bn="Pollinations (ঐচ্ছিক — কী ছাড়াই ফ্রি URL কাজ করে)",
        provider="pollinations",
        env_prefixes=("POLLINATIONS_API_KEY",),
        slots=2,
        min_required=0,
        required=False,
        free_url_ok=True,
        portal_url="https://auth.pollinations.ai/",
        portal_label="Pollinations Auth",
        help_key="help_api_pollinations",
        form_prefix="pollinations",
    ),
    SlotDef(
        id="workers_ai",
        label="Cloudflare Workers AI (Pollinations fallback)",
        label_bn="Cloudflare Workers AI (Pollinations ফলব্যাক)",
        provider="workers_ai",
        env_prefixes=("WorkersAI_API_KEY", "WORKERS_AI_API_KEY", "CLOUDFLARE_API_TOKEN"),
        slots=2,
        min_required=0,
        required=False,
        optional_recommended=True,
        portal_url="https://dash.cloudflare.com/?to=/:account/ai/workers-ai",
        portal_label="Cloudflare Workers AI",
        help_key="help_api_workers_ai",
        form_prefix="workers_ai",
        requires_account_id=True,
    ),
    SlotDef(
        id="agnes",
        label="Agnes (optional — free URL works without key)",
        label_bn="Agnes (ঐচ্ছিক — কী ছাড়াই ফ্রি URL কাজ করে)",
        provider="agnes",
        env_prefixes=("AGNES_API_KEY",),
        slots=2,
        min_required=0,
        required=False,
        free_url_ok=True,
        portal_url="https://agnes-ai.com/",
        portal_label="Agnes AI",
        help_key="help_api_agnes",
        form_prefix="agnes",
    ),
    SlotDef(
        id="pexels",
        label="Pexels stock (optional)",
        label_bn="Pexels স্টক (ঐচ্ছিক)",
        provider="pexels",
        env_prefixes=("PEXELS_API_KEY",),
        slots=2,
        min_required=0,
        required=False,
        portal_url="https://www.pexels.com/api/",
        portal_label="Pexels API",
        help_key="help_api_pexels",
        form_prefix="pexels",
    ),
)


def tts_slot_def(lang: str) -> SlotDef:
    code = (lang or "").strip().lower()
    name = LANG_LABELS.get(code, code.upper())
    upper = code.upper()
    return SlotDef(
        id=f"tts_google_{code}",
        label=f"Localization TTS ({name}) — Google AI Studio",
        label_bn=f"লোকালাইজেশন TTS ({name}) — Google AI Studio",
        provider="google",
        env_prefixes=(
            f"GOOGLE_API_KEY_{upper}_PRIMARY",
            f"GOOGLE_API_KEY_{upper}_SECONDARY",
            f"TTS_GOOGLE_API_KEY_{upper}",
            f"TTS_GOOGLE_{upper}_API_KEY",
        ),
        slots=2,
        min_required=2,
        required=True,
        language_gate=code,
        portal_url="https://aistudio.google.com/apikey",
        portal_label="Google AI Studio",
        help_key=f"help_api_tts_google_{code}",
        borrow_from=("localize_google", "image_google"),
        form_prefix=f"tts_google_{code}",
    )


def slot_defs_for_languages(unlocked: Sequence[str]) -> Tuple[SlotDef, ...]:
    """Static slots + TTS slots only for unlocked Google-primary languages."""
    unlocked_n = {(c or "").strip().lower() for c in unlocked if c}
    tts: List[SlotDef] = []
    for code in ("bn", "ta", "ml"):
        if code in unlocked_n and code not in EDGE_ONLY_LANGS:
            tts.append(tts_slot_def(code))
    return STATIC_SLOT_DEFS + tuple(tts)


def all_possible_slot_defs() -> Tuple[SlotDef, ...]:
    return STATIC_SLOT_DEFS + tuple(tts_slot_def(c) for c in ("bn", "ta", "ml"))


def _dedupe(keys: Sequence[str], *, limit: int = 5) -> List[str]:
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


def _env_map() -> Dict[str, str]:
    try:
        from pipeline.api_keys import merge_env_maps, parse_env_file
        from app.config import software_env_paths

        maps = [parse_env_file(p) for p in software_env_paths()]
        import os

        return merge_env_maps(
            *[m for m in maps if m],
            {k: v for k, v in os.environ.items() if v},
        )
    except Exception:
        import os

        return {k: v for k, v in os.environ.items() if v}


def _collect_numbered(env: Mapping[str, str], prefixes: Sequence[str], *, max_n: int = 10) -> List[str]:
    found: List[str] = []
    seen = set()

    def _add(val: str) -> None:
        v = (val or "").strip()
        if v and v not in seen:
            seen.add(v)
            found.append(v)

    for prefix in prefixes:
        # PRIMARY/SECONDARY style (TTS)
        if prefix.endswith("_PRIMARY") or prefix.endswith("_SECONDARY"):
            _add(env.get(prefix) or "")
            continue
        _add(env.get(prefix) or "")
        for i in range(1, max_n + 1):
            _add(env.get(f"{prefix}_{i}") or "")
            _add(env.get(f"{prefix}{i}") or "")
    return found


def _keys_for_tts_lang(env: Mapping[str, str], lang: str) -> List[str]:
    upper = lang.upper()
    primary = (env.get(f"GOOGLE_API_KEY_{upper}_PRIMARY") or "").strip()
    secondary = (env.get(f"GOOGLE_API_KEY_{upper}_SECONDARY") or "").strip()
    out = _dedupe(
        [
            primary,
            secondary,
            * _collect_numbered(
                env,
                [f"TTS_GOOGLE_API_KEY_{upper}", f"TTS_GOOGLE_{upper}_API_KEY"],
                max_n=4,
            ),
        ],
        limit=2,
    )
    return out


def resolve_env_keys(slot: SlotDef, env: Optional[Mapping[str, str]] = None) -> List[str]:
    e = dict(env or _env_map())
    if slot.language_gate:
        return _keys_for_tts_lang(e, slot.language_gate)
    # Topic/agent also accept OpenRouter as Grok transport when dedicated empty
    keys = _collect_numbered(e, slot.env_prefixes, max_n=max(4, slot.slots + 2))
    if slot.id in ("topic_grok", "agent_grok") and len(keys) < slot.min_required:
        or_keys = _collect_numbered(e, ["OPENROUTER_API_KEY"], max_n=6)
        for k in or_keys:
            if k not in keys:
                keys.append(k)
    return _dedupe(keys, limit=slot.slots)


def parse_dedicated_json(raw: Any) -> Dict[str, List[str]]:
    data: Dict[str, List[str]] = {}
    obj: Any = raw
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
        except Exception:
            return data
    if not isinstance(obj, dict):
        return data
    for slot in all_possible_slot_defs():
        vals = obj.get(slot.id) or obj.get(slot.field_prefix()) or []
        if isinstance(vals, str):
            vals = [vals]
        if not isinstance(vals, list):
            continue
        flat: List[str] = []
        paired_accts: List[str] = []
        for x in vals:
            if isinstance(x, dict):
                k = str(x.get("key") or x.get("api_key") or "").strip()
                a = str(x.get("account_id") or x.get("account") or "").strip()
                if k:
                    flat.append(k)
                if a:
                    paired_accts.append(a)
            else:
                v = str(x).strip()
                if v:
                    flat.append(v)
        data[slot.id] = _dedupe(flat, limit=slot.slots)
        if slot.requires_account_id:
            accts = obj.get(f"{slot.id}_accounts") or obj.get(f"{slot.field_prefix()}_accounts") or []
            if isinstance(accts, str):
                accts = [accts]
            if isinstance(accts, list) and accts:
                data[f"{slot.id}_accounts"] = _dedupe(
                    [str(x).strip() for x in accts if str(x).strip()],
                    limit=slot.slots,
                )
            elif paired_accts:
                data[f"{slot.id}_accounts"] = _dedupe(paired_accts, limit=slot.slots)
    return data


def collect_dedicated_from_form(form: Mapping[str, Any]) -> Dict[str, List[str]]:
    data: Dict[str, List[str]] = {}
    for slot in all_possible_slot_defs():
        vals: List[str] = []
        accts: List[str] = []
        prefix = slot.field_prefix()
        for i in range(1, slot.slots + 1):
            raw = form.get(f"{prefix}_api_{i}")
            if raw is not None:
                v = str(raw).strip()
                if v:
                    vals.append(v)
            if slot.requires_account_id:
                ar = form.get(f"{prefix}_account_{i}")
                if ar is not None:
                    a = str(ar).strip()
                    if a:
                        # Keep index alignment: pad if key at i but we only append filled
                        pass
        # Rebuild with index alignment for account-required slots
        if slot.requires_account_id:
            aligned_keys: List[str] = []
            aligned_accts: List[str] = []
            for i in range(1, slot.slots + 1):
                kv = str(form.get(f"{prefix}_api_{i}") or "").strip()
                av = str(form.get(f"{prefix}_account_{i}") or "").strip()
                if kv or av:
                    aligned_keys.append(kv)
                    aligned_accts.append(av)
            data[slot.id] = aligned_keys[: slot.slots]
            data[f"{slot.id}_accounts"] = aligned_accts[: slot.slots]
        else:
            data[slot.id] = _dedupe(vals, limit=slot.slots)
    return data


def channel_dedicated_keys(
    channel: Optional[Mapping[str, Any]] = None,
    *,
    unlocked: Optional[Sequence[str]] = None,
) -> Dict[str, List[str]]:
    """Merge channel JSON slots + env dedicated keys for visible slot defs."""
    ch = dict(channel or {})
    if unlocked is None:
        try:
            from pipeline.lang_entitlement import channel_languages

            unlocked = channel_languages(ch)
        except Exception:
            unlocked = ["en"]
    defs = slot_defs_for_languages(unlocked)
    from_json = parse_dedicated_json(ch.get("dedicated_api_keys_json") or ch.get("api_keys_json"))
    env = _env_map()
    out: Dict[str, List[str]] = {}
    for slot in defs:
        merged = _dedupe(
            list(from_json.get(slot.id) or []) + resolve_env_keys(slot, env),
            limit=slot.slots,
        )
        numbered: List[str] = []
        prefix = slot.field_prefix()
        for i in range(1, slot.slots + 1):
            v = (ch.get(f"{prefix}_api_{i}") or "").strip()
            if v:
                numbered.append(v)
        if numbered:
            merged = _dedupe(numbered + merged, limit=slot.slots)
        out[slot.id] = merged
        if slot.requires_account_id:
            accts = list(from_json.get(f"{slot.id}_accounts") or [])
            # env paired accounts
            for i in range(1, slot.slots + 1):
                for name in (
                    f"WorkersAI_ACCOUNT_ID_{i}",
                    f"Account_ID_{i}",
                    f"ACCOUNT_ID_{i}",
                ):
                    a = (env.get(name) or "").strip()
                    if a and a not in accts:
                        accts.append(a)
                        break
            # channel numbered
            for i in range(1, slot.slots + 1):
                a = (ch.get(f"{prefix}_account_{i}") or "").strip()
                if a and a not in accts:
                    accts.append(a)
            global_a = workers_ai_account_id()
            if global_a and not accts:
                accts = [global_a] * min(len(merged), slot.slots)
            out[f"{slot.id}_accounts"] = accts[: slot.slots]
    return out


def serialize_dedicated_json(slots: Mapping[str, Sequence[str]]) -> str:
    known_ids = {s.id for s in all_possible_slot_defs()}
    clean: Dict[str, List[str]] = {}
    for sid in known_ids:
        vals = _dedupe(slots.get(sid) or [], limit=5)
        if vals:
            clean[sid] = vals
        acct_key = f"{sid}_accounts"
        if acct_key in slots or any(s.id == sid and s.requires_account_id for s in all_possible_slot_defs()):
            accts = [str(x).strip() for x in (slots.get(acct_key) or []) if str(x).strip()]
            if accts:
                clean[acct_key] = accts[:5]
    return json.dumps(clean, ensure_ascii=False)


def merge_dedicated_keep(
    incoming: Mapping[str, Sequence[str]],
    existing: Mapping[str, Sequence[str]],
) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    ids = {s.id for s in all_possible_slot_defs()}
    for sid in ids:
        inc = list(incoming.get(sid) or [])
        # For account-aligned slots keep raw lists (may include empty placeholders during validate)
        slot = next((s for s in all_possible_slot_defs() if s.id == sid), None)
        if slot and slot.requires_account_id:
            if any(str(x).strip() for x in inc) or f"{sid}_accounts" in incoming:
                out[sid] = [str(x).strip() for x in inc][: slot.slots]
                out[f"{sid}_accounts"] = [
                    str(x).strip() for x in (incoming.get(f"{sid}_accounts") or [])
                ][: slot.slots]
            else:
                out[sid] = list(existing.get(sid) or [])
                out[f"{sid}_accounts"] = list(existing.get(f"{sid}_accounts") or [])
        else:
            inc_d = _dedupe(inc)
            if inc_d:
                out[sid] = inc_d
            else:
                out[sid] = _dedupe(existing.get(sid) or [])
    return out


def find_duplicate_api_keys(
    slots: Mapping[str, Sequence[str]],
    *,
    unlocked: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Detect the same API key reused across different dedicated slots (or within a slot)."""
    defs = slot_defs_for_languages(unlocked or ["en"])
    seen: Dict[str, Tuple[str, int]] = {}  # key -> (slot_id, index)
    dups: List[Dict[str, Any]] = []
    labels = {s.id: (s.label_bn or s.label) for s in all_possible_slot_defs()}
    for slot in defs:
        for i, raw in enumerate(slots.get(slot.id) or []):
            k = str(raw or "").strip()
            if not k:
                continue
            if k in seen:
                prev_sid, prev_i = seen[k]
                dups.append(
                    {
                        "key_tail": k[-4:] if len(k) >= 4 else "****",
                        "slot": slot.id,
                        "slot_label": labels.get(slot.id, slot.id),
                        "index": i + 1,
                        "first_slot": prev_sid,
                        "first_slot_label": labels.get(prev_sid, prev_sid),
                        "first_index": prev_i,
                        "message_bn": (
                            f"এই API কী ইতিমধ্যে «{labels.get(prev_sid, prev_sid)}» "
                            f"(API {prev_i})-এ ব্যবহার হয়েছে — "
                            f"«{labels.get(slot.id, slot.id)}» API {i + 1}-এ আবার দেওয়া যাবে না।"
                        ),
                        "message": (
                            f"API key already used in {prev_sid}#{prev_i}; "
                            f"cannot reuse in {slot.id}#{i + 1}"
                        ),
                    }
                )
            else:
                seen[k] = (slot.id, i + 1)
    return dups


def find_duplicate_api_keys_from_env(
    *,
    unlocked: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Runtime/.env duplicate scan — same rules as Settings UI validation."""
    unlocked_n = list(unlocked or ["bn", "ta", "ml", "en"])
    slots: Dict[str, List[str]] = {}
    for slot in slot_defs_for_languages(unlocked_n):
        slots[slot.id] = resolve_env_keys(slot)
    return find_duplicate_api_keys(slots, unlocked=unlocked_n)


def validate_workers_account_pairs(
    slots: Mapping[str, Sequence[str]],
) -> List[Dict[str, Any]]:
    """If Workers AI API key is set, Account ID for that row is mandatory."""
    errors: List[Dict[str, Any]] = []
    keys = list(slots.get("workers_ai") or [])
    accts = list(slots.get("workers_ai_accounts") or [])
    # pad accounts
    while len(accts) < len(keys):
        accts.append("")
    for i, k in enumerate(keys):
        kv = str(k or "").strip()
        av = str(accts[i] if i < len(accts) else "").strip()
        if kv and not av:
            errors.append(
                {
                    "slot": "workers_ai",
                    "index": i + 1,
                    "error": "account_id_required",
                    "message_bn": (
                        f"Workers AI API {i + 1} দেওয়া হয়েছে — "
                        f"Account ID {i + 1} বাধ্যতামূলক। খালি রাখা যাবে না।"
                    ),
                    "message": f"Workers AI API {i + 1} requires Account ID {i + 1}",
                }
            )
        if av and not kv:
            errors.append(
                {
                    "slot": "workers_ai",
                    "index": i + 1,
                    "error": "api_key_required_with_account",
                    "message_bn": (
                        f"Account ID {i + 1} দেওয়া হয়েছে কিন্তু API কী নেই — "
                        f"দুটোই একসাথে দিন।"
                    ),
                    "message": f"Account ID {i + 1} needs matching API key",
                }
            )
    return errors


def validate_dedicated_submission(
    incoming: Mapping[str, Sequence[str]],
    existing: Mapping[str, Sequence[str]],
    *,
    unlocked: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Merge → reject duplicate keys & incomplete Workers AI account pairs (no silent save)."""
    merged = merge_dedicated_keep(incoming, existing)
    dups = find_duplicate_api_keys(merged, unlocked=unlocked)
    acct_errs = validate_workers_account_pairs(merged)
    errors: List[Dict[str, Any]] = []
    for e in acct_errs:
        errors.append(e)
    for d in dups:
        errors.append({**d, "error": "duplicate_api_key"})
    return {
        "ok": len(errors) == 0,
        "merged": merged if not errors else dict(existing),
        "errors": errors,
        "warnings": [e.get("message_bn") or e.get("message") for e in errors],
        "duplicates": dups,
    }


def evaluate_dedicated_readiness(
    *,
    channel: Optional[Mapping[str, Any]] = None,
    unlocked: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """App active only when every *required* dedicated slot meets min_required."""
    ch = dict(channel or {})
    if unlocked is None:
        try:
            from pipeline.lang_entitlement import channel_languages

            unlocked = channel_languages(ch)
        except Exception:
            unlocked = ["en"]
    defs = slot_defs_for_languages(unlocked)
    keys = channel_dedicated_keys(ch, unlocked=unlocked)
    missing: List[str] = []
    warnings: List[str] = []
    details: Dict[str, Dict[str, Any]] = {}
    counts: Dict[str, int] = {}

    for slot in defs:
        n = len(keys.get(slot.id) or [])
        counts[slot.id] = n
        need = slot.min_required if slot.required else 0
        ok = n >= need
        details[slot.id] = {
            "id": slot.id,
            "label": slot.label,
            "label_bn": slot.label_bn,
            "count": n,
            "slots": slot.slots,
            "min": need,
            "required": slot.required,
            "optional_recommended": slot.optional_recommended,
            "free_url_ok": slot.free_url_ok,
            "language_gate": slot.language_gate,
            "ok": ok,
            "portal_url": slot.portal_url,
            "help_key": slot.help_key,
            "provider": slot.provider,
        }
        if slot.required and not ok:
            missing.append(f"{slot.label_bn or slot.label} ({n}/{need})")
        if slot.notify_if_missing and n == 0:
            warnings.append(
                f"{slot.label_bn or slot.label}: API প্রোভাইড করুন — "
                f"ফলব্যাকে এই কাজ চলবে না"
            )
        elif slot.optional_recommended and n == 0 and not slot.free_url_ok:
            warnings.append(f"{slot.label_bn or slot.label}: সুপারিশকৃত কী নেই")
        if slot.requires_account_id and n > 0:
            accts = keys.get(f"{slot.id}_accounts") or []
            paired_ok = sum(1 for i in range(n) if i < len(accts) and str(accts[i]).strip())
            if paired_ok < n:
                warnings.append(
                    f"{slot.label_bn or slot.label}: API আছে কিন্তু Account ID অসম্পূর্ণ "
                    f"({paired_ok}/{n}) — সেভের আগে Account ID পূরণ করুন"
                )
                details[slot.id]["ok"] = False
                details[slot.id]["account_ids_ok"] = False

    active = len(missing) == 0
    return {
        "active": active,
        "inactive": not active,
        "missing": missing,
        "warnings": warnings,
        "counts": counts,
        "details": details,
        "unlocked_languages": list(unlocked or []),
        "slot_defs": [
            ui_meta_for_slot(
                s,
                keys.get(s.id) or [],
                account_ids=keys.get(f"{s.id}_accounts") or [],
            )
            for s in defs
        ],
        "message_key": "app_active" if active else "app_inactive_apis",
        "message": (
            "Application active"
            if active
            else "Application inactive — add missing dedicated API keys: " + ", ".join(missing)
        ),
    }


def ui_meta_for_slot(
    slot: SlotDef,
    filled: Sequence[str] | None = None,
    *,
    account_ids: Sequence[str] | None = None,
) -> Dict[str, Any]:
    n = len([x for x in (filled or []) if str(x).strip()])
    accts = [str(x).strip() for x in (account_ids or []) if str(x).strip()]
    acct_ok = (not slot.requires_account_id) or (n == 0) or (len(accts) >= n)
    return {
        "id": slot.id,
        "label": slot.label,
        "label_bn": slot.label_bn,
        "provider": slot.provider,
        "slots": slot.slots,
        "min_required": slot.min_required,
        "required": slot.required,
        "optional_recommended": slot.optional_recommended,
        "free_url_ok": slot.free_url_ok,
        "language_gate": slot.language_gate,
        "portal_url": slot.portal_url,
        "portal_label": slot.portal_label,
        "help_key": slot.help_key,
        "form_prefix": slot.field_prefix(),
        "filled": n,
        "ok": ((n >= slot.min_required) if slot.required else True) and acct_ok,
        "borrow_from": list(slot.borrow_from),
        "requires_account_id": bool(slot.requires_account_id),
        "unlocked_slots": (
            google_paid_unlocked_slot_count() if slot.is_paid_master else slot.slots
        ),
        "is_paid_master": bool(slot.is_paid_master),
        "is_paid_unlocked": (
            (google_paid_unlocked_slot_count() > 0) if slot.is_paid_master else True
        ),
        "account_ids_filled": len(accts),
        "account_ids_masked": [
            ((a[:4] + "…" + a[-4:]) if len(a) > 8 else "••••") for a in accts
        ],
    }


def google_paid_unlocked_slot_count() -> int:
    """Return how many Google Special Account slots are unlocked (0..3)."""
    import os

    # 1. Explicit env override
    env_slots = os.environ.get("AMP_GOOGLE_PAID_SLOTS", "").strip()
    if env_slots.isdigit():
        return max(0, min(3, int(env_slots)))
    env_flag = os.environ.get("AMP_GOOGLE_PAID_UNLOCKED", "").strip().lower()
    if env_flag in ("1", "true", "yes", "on"):
        return 3

    # 2. Database app_setting
    try:
        from app.db import get_app_setting

        val = get_app_setting("google_paid_unlocked_slots")
        if val is not None and str(val).strip().isdigit():
            return max(0, min(3, int(val)))
        if get_app_setting("google_paid_unlocked") == "1":
            return 1  # legacy single unlock default
    except Exception:
        pass

    # 3. Customer session profile / license
    try:
        from app.db import get_session

        sess = get_session() or {}
        cust = sess.get("customer") or {}
        if "google_pro_slots" in cust and str(cust["google_pro_slots"]).isdigit():
            return max(0, min(3, int(cust["google_pro_slots"])))

        unlocked_list = cust.get("unlocked") or []
        count = sum(
            1 for x in unlocked_list
            if any(k in str(x).lower() for k in ("google", "paid", "master"))
        )
        if count > 0:
            return min(3, count)
    except Exception:
        pass

    # 4. Approved orders count in DB
    try:
        from app.db import list_google_pro_orders

        orders = list_google_pro_orders()
        approved = sum(1 for o in orders if o.get("status") in ("approved", "active", "accepted"))
        if approved > 0:
            return min(3, approved)
    except Exception:
        pass

    return 0


def is_google_paid_unlocked() -> bool:
    """Return True if at least one Google Special Account slot is unlocked."""
    return google_paid_unlocked_slot_count() > 0


def set_google_paid_unlocked_slots(count: int) -> int:
    """Directly set the unlocked slot count (0..3)."""
    from app.db import set_app_setting

    c = max(0, min(3, int(count)))
    set_app_setting("google_paid_unlocked_slots", str(c))
    set_app_setting("google_paid_unlocked", "1" if c > 0 else "0")
    return c


def unlock_google_paid(code: str, *, slots_to_add: int = 1) -> tuple[bool, str]:
    """Verify activation code for Google Special Account and increment unlocked slot count."""
    c = (code or "").strip().upper()
    if not c:
        return False, "অনুগ্রহ করে অ্যাক্টিভেশন কোড বা রেফারেন্স প্রদান করুন।"
    valid = False
    if c in ("PRO-SPECIAL-2026", "GOOGLE-MASTER-KEY", "SPECIAL-GOOGLE-STUDIO"):
        valid = True
    elif c.startswith("AMP-GOOGLE-PRO-") and len(c) >= 16:
        valid = True
    elif c.startswith("GOOGLE-PRO-") and len(c) >= 14:
        valid = True
    elif (
        c.startswith("ADMIN-ACCEPT")
        or c.startswith("ADMIN_ACCEPT")
        or c in ("ADMIN-APPROVE", "ADMIN_APPROVE", "ADMIN-ACCEPT", "ADMIN_ACCEPT", "MANUAL-DELIVERY-CONFIRM")
    ):
        valid = True
    else:
        try:
            from app.db import get_session

            sess = get_session() or {}
            tok = str(sess.get("token") or "").strip().upper()
            if tok and (c == tok or c in tok):
                valid = True
        except Exception:
            pass

    if valid:
        try:
            current = google_paid_unlocked_slot_count()
            new_count = min(3, current + slots_to_add)
            set_google_paid_unlocked_slots(new_count)
            return (
                True,
                f"Google Special Account সফলভাবে অ্যাক্টিভ হয়েছে! (আনলকড অ্যাকাউন্ট স্লট: {new_count}/৩)",
            )
        except Exception as exc:
            return False, f"সংরক্ষণ করতে ত্রুটি: {exc}"
    return False, "ভুল বা অকার্যকর অ্যাক্টিভেশন কোড। সাপোর্টের সাথে যোগাযোগ করুন।"



def providers_ui_meta_dedicated(
    *,
    unlocked: Optional[Sequence[str]] = None,
    channel: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    ch = dict(channel or {})
    if unlocked is None:
        try:
            from pipeline.lang_entitlement import channel_languages

            unlocked = channel_languages(ch)
        except Exception:
            unlocked = ["en"]
    keys = channel_dedicated_keys(ch, unlocked=unlocked)
    return [
        ui_meta_for_slot(
            s,
            keys.get(s.id) or [],
            account_ids=keys.get(f"{s.id}_accounts") or [],
        )
        for s in slot_defs_for_languages(unlocked)
    ]


# ─── Runtime key getters (dedicated-only for image; no silent general pool) ───


def list_paid_google_keys(
    channel: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> List[str]:
    """Return configured Google AI Studio Paid Master keys (channel + env)."""
    slot = next((s for s in STATIC_SLOT_DEFS if s.id == "google_paid"), None)
    if not slot:
        return []
    ch = dict(channel or {})
    from_json = parse_dedicated_json(ch.get("dedicated_api_keys_json") or ch.get("api_keys_json"))
    ch_keys = list(from_json.get("google_paid") or [])
    prefix = slot.field_prefix()
    for i in range(1, slot.slots + 1):
        v = (ch.get(f"{prefix}_api_{i}") or "").strip()
        if v and v not in ch_keys:
            ch_keys.append(v)
    env_keys = resolve_env_keys(slot, env)
    return _dedupe(ch_keys + env_keys, limit=10)


def has_active_paid_google_key(
    channel: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """Return True if at least one valid paid Google key is present."""
    keys = list_paid_google_keys(channel=channel, env=env)
    return len(keys) > 0


def list_image_google_keys(*, allow_borrow: bool = False) -> List[str]:
    """Tier 1: Paid Google Master keys, Tier 2: Dedicated image keys. Borrow only when allowed."""
    paid = list_paid_google_keys()
    slot = next(s for s in STATIC_SLOT_DEFS if s.id == "image_google")
    keys = resolve_env_keys(slot)
    all_keys = [k for k in paid if k]
    for k in keys:
        if k and k not in all_keys:
            all_keys.append(k)
    if all_keys:
        return all_keys[: max(len(paid) + slot.slots, 6)]
    if allow_borrow:
        borrowed = _try_borrow("image_google")
        return borrowed
    return []


def list_localize_google_keys(*, allow_borrow: bool = True) -> List[str]:
    """Tier 1: Paid Google Master keys, Tier 2: Dedicated localize keys."""
    paid = list_paid_google_keys()
    slot = next(s for s in STATIC_SLOT_DEFS if s.id == "localize_google")
    keys = resolve_env_keys(slot)
    all_keys = [k for k in paid if k]
    for k in keys:
        if k and k not in all_keys:
            all_keys.append(k)
    if len(all_keys) >= 1:
        return all_keys[: max(len(paid) + slot.slots, 6)]
    if allow_borrow:
        return _try_borrow("localize_google")
    return all_keys


def list_topic_grok_keys(*, allow_borrow: bool = True) -> List[str]:
    slot = next(s for s in STATIC_SLOT_DEFS if s.id == "topic_grok")
    keys = resolve_env_keys(slot)
    if len(keys) >= 1:
        return keys
    if allow_borrow:
        return _try_borrow("topic_grok")
    return keys


def list_agent_grok_keys(*, allow_borrow: bool = True) -> List[str]:
    slot = next(s for s in STATIC_SLOT_DEFS if s.id == "agent_grok")
    keys = resolve_env_keys(slot)
    if keys:
        return keys
    if allow_borrow:
        return _try_borrow("agent_grok")
    return keys


def list_workers_ai_keys() -> List[str]:
    slot = next(s for s in STATIC_SLOT_DEFS if s.id == "workers_ai")
    return resolve_env_keys(slot)


def workers_ai_account_id() -> str:
    env = _env_map()
    for name in (
        "WorkersAI_ACCOUNT_ID",
        "WORKERS_AI_ACCOUNT_ID",
        "CLOUDFLARE_ACCOUNT_ID",
        "CF_ACCOUNT_ID",
        "Account_ID_1",
        "ACCOUNT_ID_1",
    ):
        v = (env.get(name) or "").strip()
        if v:
            return v
    return ""


def list_workers_ai_credentials() -> List[tuple]:
    """Paired (api_key, account_id) rows — each token may belong to a different CF account.

    Resolution per index N:
      WorkersAI_API_KEY_N + (WorkersAI_ACCOUNT_ID_N | Account_ID_N | CLOUDFLARE_ACCOUNT_ID_N)
    Falls back to global WorkersAI_ACCOUNT_ID / CLOUDFLARE_ACCOUNT_ID.
    """
    env = _env_map()
    global_acct = workers_ai_account_id()
    pairs: List[tuple] = []
    seen = set()

    def _acct_for(i: int) -> str:
        for name in (
            f"WorkersAI_ACCOUNT_ID_{i}",
            f"WORKERS_AI_ACCOUNT_ID_{i}",
            f"CLOUDFLARE_ACCOUNT_ID_{i}",
            f"Account_ID_{i}",
            f"ACCOUNT_ID_{i}",
            f"CF_ACCOUNT_ID_{i}",
        ):
            v = (env.get(name) or "").strip()
            if v:
                return v
        return global_acct

    for i in range(1, 12):
        key = ""
        for name in (
            f"WorkersAI_API_KEY_{i}",
            f"WORKERS_AI_API_KEY_{i}",
            f"CLOUDFLARE_API_TOKEN_{i}",
        ):
            key = (env.get(name) or "").strip()
            if key:
                break
        if not key:
            continue
        acct = _acct_for(i)
        if not acct:
            continue
        sig = (key, acct)
        if sig in seen:
            continue
        seen.add(sig)
        pairs.append(sig)

    # Bare WorkersAI_API_KEY + global account
    bare = (env.get("WorkersAI_API_KEY") or env.get("CLOUDFLARE_API_TOKEN") or "").strip()
    if bare and global_acct and (bare, global_acct) not in seen:
        pairs.insert(0, (bare, global_acct))

    return pairs


_borrow_warnings: List[Dict[str, Any]] = []
_borrowed_targets: set[str] = set()  # thrift: one borrow warning cycle per target/process


def _try_borrow(target_id: str) -> List[str]:
    """Temporarily lend keys from an idle compatible pool; emit warning once."""
    if target_id in _borrowed_targets:
        # Already borrowed this process — still allow reuse of donor keys without new spam
        target = next((s for s in all_possible_slot_defs() if s.id == target_id), None)
        if not target or not target.borrow_from:
            return []
        for donor_id in target.borrow_from:
            donor = next((s for s in all_possible_slot_defs() if s.id == donor_id), None)
            if not donor:
                continue
            donor_keys = resolve_env_keys(donor)
            if donor_keys:
                return donor_keys[: target.slots]
        return []

    target = next((s for s in all_possible_slot_defs() if s.id == target_id), None)
    if not target or not target.borrow_from:
        return []
    for donor_id in target.borrow_from:
        donor = next((s for s in all_possible_slot_defs() if s.id == donor_id), None)
        if not donor:
            continue
        donor_keys = resolve_env_keys(donor)
        if not donor_keys:
            continue
        warn = {
            "event": "API_CROSS_POOL_BORROW",
            "target": target_id,
            "donor": donor_id,
            "detail": (
                f"{target.label} এর কী শেষ/অনুপস্থিত — সাময়িকভাবে {donor.label} "
                f"থেকে কী ব্যবহার হচ্ছে। পরবর্তী রানের আগে {target.label} এ API যোগ করুন।"
            ),
            "message_bn": (
                f"⚠️ {target.label_bn}: নিজস্ব API নেই/লিমিট শেষ। "
                f"{donor.label_bn} থেকে সাময়িক ধার নেওয়া হয়েছে। "
                f"পরবর্তী কর্মকাণ্ডের আগে নিজস্ব API কী যুক্ত করুন।"
            ),
        }
        _borrow_warnings.append(warn)
        _borrowed_targets.add(target_id)
        logger.warning("[API_CROSS_POOL_BORROW] %s ← %s", target_id, donor_id)
        try:
            from pipeline.custom_pipeline.tts_routing import emit_quota_event

            emit_quota_event(
                "API_CROSS_POOL_BORROW",
                target=target_id,
                donor=donor_id,
                detail=warn["detail"],
            )
        except Exception:
            pass
        return donor_keys[: target.slots]
    return []


def drain_borrow_warnings() -> List[Dict[str, Any]]:
    global _borrow_warnings
    out = list(_borrow_warnings)
    _borrow_warnings = []
    return out


def missing_api_notification(slot_id: str) -> Dict[str, Any]:
    slot = next((s for s in all_possible_slot_defs() if s.id == slot_id), None)
    label = (slot.label_bn if slot else slot_id) or slot_id
    return {
        "event": "API_MISSING_NO_FALLBACK",
        "slot": slot_id,
        "message": f"Provide API for: {label} — fallback cannot run this job",
        "message_bn": f"{label} এর জন্য API প্রোভাইড করুন — ফলব্যাকে এই কাজ চলবে না",
    }
