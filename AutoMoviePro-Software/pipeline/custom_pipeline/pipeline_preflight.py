"""Preflight health gate — fail closed before burning paid APIs.

Industrial launch rule: surface missing/misconfigured keys BEFORE topic/Grok spend.
Returns warnings (non-fatal) and blockers (fatal unless allow_degraded).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _mask(key: str) -> str:
    k = (key or "").strip()
    return f"…{k[-4:]}" if len(k) >= 4 else "…????"


def run_pipeline_preflight(
    *,
    languages: Optional[Sequence[str]] = None,
    include_bangla_tts: bool = True,
    skip_localize: bool = False,
    skip_visual: bool = False,
    skip_tts: bool = False,
    skip_media: bool = False,
    allow_degraded: bool = True,
) -> Dict[str, Any]:
    """Check dedicated + overflow pools before stage 1.

    Returns:
      ok: True if no blockers (or allow_degraded and only warnings)
      blockers: hard issues (no Grok, no image path, etc.)
      warnings: soft issues (few localize keys, duplicate slots, etc.)
      facts: counts for telemetry / UI
    """
    blockers: List[str] = []
    warnings: List[str] = []
    facts: Dict[str, Any] = {}

    langs = [str(x) for x in (languages or []) if x]
    expected_localize = list(langs)
    expected_tts = (["Bangla"] if include_bangla_tts else []) + list(langs)

    # ── Duplicate dedicated keys (.env / runtime) ─────────────
    try:
        from pipeline.dedicated_api_registry import find_duplicate_api_keys_from_env

        dups = find_duplicate_api_keys_from_env(unlocked=["bn", "ta", "ml", "en"])
        facts["duplicate_keys"] = len(dups or [])
        if dups:
            for d in dups[:8]:
                msg = d.get("message") if isinstance(d, dict) else str(d)
                warnings.append(f"Duplicate API key across slots: {msg}")
            logger.warning("Preflight: %s duplicate dedicated key conflict(s)", len(dups))
    except Exception as exc:
        warnings.append(f"Duplicate-key check skipped: {exc}")

    # ── Grok / OpenRouter ─────────────────────────────────────
    try:
        from pipeline.custom_pipeline.session_keys import (
            _is_openrouter_key,
            _partition_grok_pool,
            list_grok_keys,
            list_openrouter_keys,
        )

        raw = list_grok_keys()
        xai, or_from = _partition_grok_pool(raw)
        or_pool = list(or_from)
        for k in list_openrouter_keys():
            if k and k not in or_pool:
                or_pool.append(k)
        facts["grok_xai"] = len(xai)
        facts["grok_openrouter"] = len(or_pool)
        if not xai and not or_pool:
            blockers.append(
                "No Grok keys: add TOPIC_GROK_API_KEY_* (xAI or OpenRouter sk-or-…) "
                "or OPENROUTER_API_KEY_*."
            )
        elif not xai and or_pool:
            warnings.append(
                f"Topic Grok will use OpenRouter ({len(or_pool)} key(s)) — OK if intentional."
            )
        # Mis-typed: non-sk-or key that looks like OR model intent is rare; skip
        mixed = sum(1 for k in raw if _is_openrouter_key(k)) and sum(
            1 for k in raw if not _is_openrouter_key(k)
        )
        if mixed:
            warnings.append(
                "TOPIC/AGENT pool mixes xAI + OpenRouter keys — routing auto-splits (OK)."
            )
    except Exception as exc:
        blockers.append(f"Grok key check failed: {exc}")

    # ── Localization pool ─────────────────────────────────────
    if not skip_localize:
        try:
            from pipeline.custom_pipeline.session_keys import list_localization_keys

            loc_pool = list_localization_keys()
            facts["localize_pool"] = len(loc_pool)
            need = max(1, len(expected_localize) or 5)
            if len(loc_pool) < 1:
                blockers.append(
                    "No localization Google keys: add LOCALIZATION_GOOGLE_API_KEY_* "
                    "or GOOGLE_API_KEY_*."
                )
            elif len(loc_pool) < need:
                warnings.append(
                    f"Only {len(loc_pool)} localize key(s) for {need} language(s) — "
                    "keys will be reused across languages (slower / quota risk). "
                    "Add more LOCALIZATION_GOOGLE_API_KEY_* for unique pins."
                )
        except Exception as exc:
            blockers.append(f"Localize key check failed: {exc}")

    # ── Image path (Google / Workers / Pollinations free) ─────
    if not skip_media:
        try:
            from pipeline.custom_pipeline.session_keys import list_image_google_keys

            img = list_image_google_keys()
            facts["image_google"] = len(img)
            workers_ok = False
            try:
                from pipeline.dedicated_api_registry import list_workers_ai_credentials

                workers_ok = bool(list_workers_ai_credentials())
            except Exception:
                try:
                    from pipeline.dedicated_api_registry import (
                        list_workers_ai_keys,
                        workers_ai_account_id,
                    )

                    workers_ok = bool(list_workers_ai_keys()) and bool(workers_ai_account_id())
                except Exception:
                    workers_ok = False
            facts["workers_ai"] = bool(workers_ok)
            # Pollinations free URL always available as last resort
            if not img and not workers_ok:
                warnings.append(
                    "No IMAGE_GOOGLE or Workers AI credentials — image chain will use "
                    "Pollinations/Agnes free paths (quality may vary)."
                )
        except Exception as exc:
            warnings.append(f"Image key check soft-fail: {exc}")

    # ── TTS (bn/ta/ml Google dual; Edge covers en/hi/ur) ──────
    if not skip_tts and include_bangla_tts:
        try:
            from pipeline.custom_pipeline.tts_routing import resolve_dual_google_keys

            p, s = resolve_dual_google_keys("bn")
            facts["tts_bn_keys"] = int(bool(p)) + int(bool(s))
            if facts["tts_bn_keys"] < 1:
                warnings.append(
                    "No BN Google TTS keys — Bangla will use Edge-TTS fallback "
                    "(acceptable; Google voice preferred when keys healthy)."
                )
        except Exception as exc:
            warnings.append(f"TTS key check soft-fail: {exc}")

    if skip_visual:
        facts["skip_visual"] = True

    fatal = bool(blockers) and not allow_degraded
    ok = not blockers if not allow_degraded else (len([b for b in blockers if "No Grok" in b]) == 0)
    # Always hard-block missing Grok even when degraded allowed
    hard = [b for b in blockers if "No Grok" in b or "No localization Google keys" in b]
    if hard:
        ok = False

    report = {
        "ok": ok,
        "blockers": blockers,
        "hard_blockers": hard,
        "warnings": warnings,
        "facts": facts,
        "expected_localize": expected_localize,
        "expected_tts": expected_tts,
    }
    if hard:
        logger.error("Preflight BLOCKED: %s", "; ".join(hard))
    elif warnings:
        logger.warning("Preflight warnings (%s): %s", len(warnings), "; ".join(warnings[:5]))
    else:
        logger.info("Preflight OK facts=%s", facts)
    return report


def raise_if_preflight_blocked(report: Dict[str, Any]) -> None:
    hard = list(report.get("hard_blockers") or report.get("blockers") or [])
    if not report.get("ok") and hard:
        raise RuntimeError(
            "Pipeline preflight failed — fix API keys before create:\n- "
            + "\n- ".join(hard)
        )
