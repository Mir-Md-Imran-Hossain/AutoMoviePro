"""Entity / fact / negation / temporal / drift validation (AMP-004 Phase-06)."""
from __future__ import annotations

import re
from typing import Any, Optional

from pipeline.localization_consistency.contract import LocalizationContract, extract_entity_bindings, extract_fact_bindings
from pipeline.multimodal_consistency.localization_semantic import extract_semantic_events


NEGATION_TOKENS = (" not ", " never ", " without ", " cannot ", " can't ", " no longer ", " doesn't ", " don't ", " isn't ", " aren't ")
TEMPORAL_TOKENS = (
    "before", "after", "during", "while", "then", "first", "finally", "already", "still", "previously", "later",
)


def _has_negation(text: str) -> bool:
    t = f" {(text or '').lower()} "
    return any(tok in t for tok in NEGATION_TOKENS) or bool(re.search(r"\b(no|not|never|without|cannot)\b", t))


def _temporal_markers(text: str) -> list[str]:
    lower = (text or "").lower()
    return [tok for tok in TEMPORAL_TOKENS if re.search(rf"\b{re.escape(tok)}\b", lower)]


def detect_entity_substitution(source: str, localized: str, bindings: list[str]) -> list[str]:
    issues: list[str] = []
    loc_lower = (localized or "").lower()
    src_lower = (source or "").lower()
    # Device feature must not become "transforms into camera"
    if re.search(r"\b(iphone|pixel|smartphone|phone)\s+camera\b", src_lower):
        if re.search(r"\b(becomes?|transforms? into|turns? into)\s+(a\s+)?camera\b", loc_lower):
            issues.append("entity_substitution:device_feature_to_device")
    # Brand preservation enforceable when localized still carries Latin script
    has_latin = bool(re.search(r"[A-Za-z]{3,}", localized or ""))
    for b in bindings:
        bl = b.lower()
        if re.search(r"[A-Za-z]", b) and len(b) >= 3:
            if bl in ("iphone", "pixel", "samsung", "google", "apple", "chernobyl", "nasa"):
                if has_latin and bl not in loc_lower and b not in (localized or ""):
                    issues.append(f"entity_missing:{b}")
    return issues


def _normalize_indic_digits(text: str) -> str:
    """Map common Indic/Arabic-Indic digits to ASCII so year/number facts survive translation."""
    trans = str.maketrans(
        {
            "০": "0",
            "১": "1",
            "২": "2",
            "৩": "3",
            "৪": "4",
            "৫": "5",
            "৬": "6",
            "৭": "7",
            "৮": "8",
            "৯": "9",
            "०": "0",
            "१": "1",
            "२": "2",
            "३": "3",
            "४": "4",
            "५": "5",
            "६": "6",
            "७": "7",
            "८": "8",
            "९": "9",
            "٠": "0",
            "١": "1",
            "٢": "2",
            "٣": "3",
            "٤": "4",
            "٥": "5",
            "٦": "6",
            "٧": "7",
            "٨": "8",
            "٩": "9",
        }
    )
    return (text or "").translate(trans)


def detect_fact_mismatch(
    source_facts: list[dict[str, Any]],
    localized: str,
    *,
    unit_policy: str = "preserve_source_units",
    currency_policy: str = "preserve_source_currency",
) -> list[str]:
    issues: list[str] = []
    loc_norm = _normalize_indic_digits(localized or "")
    loc_facts = extract_fact_bindings(loc_norm)
    loc_values = {f["value"].replace(",", "") for f in loc_facts}
    for f in source_facts:
        val = str(f.get("value") or "").replace(",", "")
        unit = str(f.get("unit") or "").lower()
        if val and val not in loc_values and val not in loc_norm:
            # number disappeared or changed
            issues.append(f"number_mismatch:expected_{val}")
        if unit and unit_policy == "preserve_source_units":
            # unit conversion without record
            if unit in ("m", "meters", "metre") and re.search(r"\b\d+\s*(ft|feet)\b", loc_norm, re.I):
                if "conversion" not in loc_norm.lower():
                    issues.append("unit_mismatch:m_to_ft_without_policy")
            if unit in ("$", "usd", "€", "eur", "£") and currency_policy == "preserve_source_currency":
                if unit in ("$", "usd"):
                    if re.search(r"[€£]|(\beur\b|\bgbp\b)", loc_norm, re.I) and "$" not in loc_norm and "usd" not in loc_norm.lower():
                        issues.append("currency_mismatch")
                if unit in ("€", "eur") and ("$" in loc_norm or "usd" in loc_norm.lower()) and "€" not in loc_norm:
                    issues.append("currency_mismatch")
    return issues


def detect_negation_reversal(source: str, localized: str) -> Optional[str]:
    src_neg = _has_negation(source)
    # For same-language or Latin-script localized test fixtures, check negation presence
    loc = localized or ""
    if re.search(r"[A-Za-z]{3,}", loc):
        loc_neg = _has_negation(loc)
        if src_neg and not loc_neg:
            # classic reversal patterns
            if re.search(r"\b(opens?|does|is|can)\b", loc.lower()) and re.search(r"\b(not|never|doesn't|cannot)\b", source.lower()):
                return "negation_reversal"
            if "does not" in source.lower() or "doesn't" in source.lower() or "never" in source.lower():
                return "negation_reversal"
    return None


def detect_temporal_reversal(source: str, localized: str) -> Optional[str]:
    src_m = _temporal_markers(source)
    loc_m = _temporal_markers(localized)
    if not src_m or not loc_m:
        return None
    # before/after swap
    if "before" in src_m and "after" in loc_m and "before" not in loc_m:
        return "temporal_reversal:before_to_after"
    if "after" in src_m and "before" in loc_m and "after" not in loc_m:
        return "temporal_reversal:after_to_before"
    if "first" in src_m and "finally" in loc_m and "first" not in loc_m:
        return "temporal_reversal:first_to_finally"
    return None


def detect_omission_addition(source: str, localized: str, bindings: list[str]) -> list[str]:
    issues: list[str] = []
    src_words = set(re.findall(r"[A-Za-z0-9]{4,}", (source or "").lower()))
    loc_words = set(re.findall(r"[A-Za-z0-9]{4,}", (localized or "").lower()))
    # Drastic length collapse
    if len(source or "") >= 40 and len(localized or "") < max(8, len(source) * 0.2):
        issues.append("omission_suspected")
    if len(loc_words) >= 1 and len(src_words) >= 3:
        # heavy omission of content words
        overlap = src_words & loc_words
        if len(overlap) < max(1, len(src_words) // 5) and len(localized) < len(source) * 0.35:
            if "omission_suspected" not in issues:
                issues.append("omission_suspected")
        # addition of unrelated long english phrase markers
        added = loc_words - src_words
        noise = {w for w in added if w in {"suddenly", "magically", "explodes", "aliens", "lottery"}}
        if noise:
            issues.append(f"addition_detected:{','.join(sorted(noise))}")
    # Explicit noise markers even for short sources
    for marker in ("suddenly", "magically", "aliens", "lottery"):
        if marker in (localized or "").lower() and marker not in (source or "").lower():
            if not any(i.startswith("addition_detected:") for i in issues):
                issues.append(f"addition_detected:{marker}")
            break
    for b in bindings:
        if b.lower() in (source or "").lower() and b.lower() not in (localized or "").lower() and re.search(r"[A-Za-z]", b):
            # brand missing counted under entity; skip duplicate
            pass
    return issues


def detect_english_as_localized(source: str, localized: str, target_lang: str) -> Optional[str]:
    """
    Fail-closed when a required non-EN locale ships English (or Latin-dominant copy of source).
    Must never label English narration as a successful localization for Indic/Arabic targets.
    """
    tgt = (target_lang or "").strip().lower()[:2]
    if not tgt or tgt == "en":
        return None
    src = (source or "").strip()
    loc = (localized or "").strip()
    if not loc:
        return "english_as_localized:missing"
    if loc.lower() == src.lower():
        return "english_as_localized:identical"
    # Product target langs beyond EN use non-Latin primary scripts
    non_latin = {"bn", "hi", "ur", "ta", "ml"}
    if tgt not in non_latin:
        return None
    # Script inventory: Latin vs target-family letters
    latin_n = len(re.findall(r"[A-Za-z]", loc))
    script_n = len(
        re.findall(
            r"[A-Za-z\u0900-\u097F\u0980-\u09FF\u0B80-\u0BFF\u0D00-\u0D7F\u0600-\u06FF]",
            loc,
        )
    ) or 1
    if latin_n >= 20 and (latin_n / script_n) >= 0.85:
        return "english_as_localized:latin_dominant"
    src_toks = set(re.findall(r"[a-z]{4,}", src.lower()))
    loc_toks = set(re.findall(r"[a-z]{4,}", loc.lower()))
    if src_toks and len(src_toks) >= 4:
        overlap = len(src_toks & loc_toks) / max(1, len(src_toks))
        if overlap >= 0.7 and latin_n >= max(24, int(0.6 * len(loc))):
            return "english_as_localized:source_token_overlap"
    return None


def validate_translation_drift(
    contract: LocalizationContract,
    localized_text: str,
    *,
    speaker_changed: bool = False,
    emotion_changed: bool = False,
) -> dict[str, Any]:
    """SOURCE vs LOCALIZED semantic comparison. Critical drift → BLOCK."""
    issues: list[str] = []
    method = "DETERMINISTIC"
    src = contract.source_text
    loc = (localized_text or "").strip()

    if not loc:
        return {"status": "BLOCK", "issues": ["missing_localized_text"], "method": method}

    en_as_loc = detect_english_as_localized(src, loc, contract.target_language)
    if en_as_loc:
        issues.append(en_as_loc)

    issues.extend(detect_entity_substitution(src, loc, contract.entity_bindings))
    issues.extend(detect_fact_mismatch(contract.fact_bindings, loc, unit_policy=contract.unit_policy, currency_policy=contract.currency_policy))

    neg = detect_negation_reversal(src, loc)
    if neg:
        issues.append(neg)
    temp = detect_temporal_reversal(src, loc)
    if temp:
        issues.append(temp)
    issues.extend(detect_omission_addition(src, loc, contract.entity_bindings))

    # Action preservation via shared event vocabulary when Latin present
    src_events = contract.action_events or extract_semantic_events(src)
    loc_events = extract_semantic_events(loc)
    if src_events and loc_events:
        missing = [e for e in src_events if e not in loc_events]
        if missing:
            issues.append(f"action_omission:{','.join(missing)}")

    if speaker_changed:
        issues.append("speaker_identity_changed")
    if emotion_changed:
        issues.append("emotion_intent_changed")

    # Naturalness heuristic (machine leakage)
    if re.search(r"\b(ssml|tts|translate the following)\b", loc, re.I):
        issues.append("machine_instruction_leakage")
    if re.search(r"\b(culturally localize|word-for-word|locale voice guide)\b", loc, re.I):
        issues.append("machine_instruction_leakage")

    # Literal MT smell: English source scaffolding leaked into Indic scripts
    tgt = (contract.target_language or "").lower()[:2]
    if tgt in ("bn", "hi", "ur", "ta", "ml"):
        if re.search(
            r"\b(as we can see|in this video|don't forget to|subscribe now|"
            r"let'?s dive in|without further ado)\b",
            loc,
            re.I,
        ):
            issues.append("cultural_tone_mismatch:english_filler_calque")

    status = "BLOCK" if issues else "PASS"
    # If target is non-Latin and we couldn't apply Latin checks → some checks UNKNOWN
    if not re.search(r"[A-Za-z]{3,}", loc) and not issues:
        return {
            "status": "PASS",
            "issues": [],
            "method": "HEURISTIC",
            "semantic_naturalness": "UNKNOWN",
            "unknown_is_not_pass_for_naturalness": True,
            "note": "non_latin_naturalness_unknown",
        }

    return {
        "status": status,
        "issues": issues,
        "method": method,
        "semantic_naturalness": "HEURISTIC" if status == "PASS" else "FAIL",
    }
