"""Honest ok / partial / failed / shippable semantics for custom pipeline.

Industrial launch rules:
  - shippable_bn_only: primary market (Bangla) final + shared shots OK → user can publish BN
  - shippable_all_languages: every planned language has a final
  - shippable (default product gate): shippable_bn_only — create UX must not fail when
    optional localize langs drop, BUT missing_languages always lists the FULL plan
  - never hide multi-lang incompleteness (partial=True when not all langs)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def _norm_lang(name: str) -> str:
    n = (name or "").strip()
    low = n.lower()
    if low in ("bangla", "bengali", "bn"):
        return "Bangla"
    return n


def honest_completion(
    *,
    success_count: int,
    expected_count: int,
    extra_ok: bool = True,
) -> Dict[str, Any]:
    """Unit-count honesty (shots, langs, etc.)."""
    exp = max(0, int(expected_count))
    suc = max(0, int(success_count))
    complete = exp > 0 and suc >= exp and extra_ok
    partial = (not complete) and suc > 0
    failed = suc <= 0
    return {
        "ok": complete,
        "partial": partial,
        "failed": failed and not complete,
        "success_count": suc,
        "expected_count": exp,
        "missing_count": max(0, exp - suc),
    }


def honest_shippable(
    *,
    shared_success: int,
    shared_expected: int,
    finals_ok: Sequence[str],
    expected_languages: Sequence[str],
    shared_errors: Optional[Dict[str, Any]] = None,
    cancel_requested: bool = False,
    skip_compose: bool = False,
    primary_languages: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Full deliverable gate used by media_stage + runner.

    Product shippable = primary (default Bangla) ready.
    Complete multi-lang = shippable_all_languages.
    """
    langs_needed: List[str] = []
    seen_l: set[str] = set()
    for x in expected_languages:
        if not x:
            continue
        n = _norm_lang(x)
        if n not in seen_l:
            seen_l.add(n)
            langs_needed.append(n)
    finals_raw = [_norm_lang(x) for x in finals_ok if x]
    finals = list(dict.fromkeys(finals_raw))
    missing_langs = [l for l in langs_needed if l not in finals]

    primary_in = primary_languages
    if primary_in is None:
        if any(_norm_lang(x) == "Bangla" for x in langs_needed):
            primary = ["Bangla"]
        else:
            # No Bangla in plan → every planned lang is required to ship
            primary = list(langs_needed)
    else:
        primary = [_norm_lang(x) for x in primary_in if x]
    if not primary:
        primary = list(langs_needed) or ["Bangla"]
    missing_primary = [l for l in primary if l not in finals]

    shots = honest_completion(
        success_count=shared_success,
        expected_count=shared_expected,
        extra_ok=not bool(shared_errors),
    )
    if skip_compose:
        langs_complete = False
        primary_complete = False
    else:
        langs_complete = (not langs_needed) or (not missing_langs)
        primary_complete = (not primary) or (not missing_primary)

    shippable_all = bool(shots["ok"] and langs_complete and not cancel_requested)
    shippable_bn = bool(shots["ok"] and primary_complete and not cancel_requested)
    # Product gate: BN (primary) ready is enough to ship; incomplete langs → partial
    shippable = shippable_bn
    partial = (not shippable_all) and (
        shots["success_count"] > 0 or bool(finals)
    )
    return {
        "ok": shippable_all,  # strict: all planned langs
        "shippable": shippable,  # product: primary/BN ready
        "shippable_bn_only": shippable_bn,
        "shippable_all_languages": shippable_all,
        "partial": partial,
        "failed": (not shippable) and (not partial),
        "shared_success": shots["success_count"],
        "shared_expected": shots["expected_count"],
        "finals_ok": list(finals),
        "missing_languages": missing_langs,
        "missing_primary_languages": missing_primary,
        "planned_languages": langs_needed,
        "primary_languages": primary,
        "skip_compose": skip_compose,
    }


def finalize_language_results(
    results: Dict[str, Any],
    *,
    expected: Sequence[str],
    errors: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """For localize/TTS multi-lang aggregators."""
    errs = dict(errors or {})
    ok_langs: List[str] = []
    for name in expected:
        item = results.get(name) or {}
        if name in errs:
            continue
        if item.get("ok") and int(item.get("success_count") or 0) >= int(
            item.get("shot_count") or item.get("success_count") or 0
        ):
            sc = int(item.get("shot_count") or 0)
            su = int(item.get("success_count") or 0)
            if sc > 0 and su < sc:
                continue
            ok_langs.append(name)
        elif item.get("ok") and "shot_count" not in item:
            ok_langs.append(name)
    status = honest_completion(success_count=len(ok_langs), expected_count=len(list(expected)))
    return {
        **status,
        "ok_languages": ok_langs,
        "errors": errs,
    }
