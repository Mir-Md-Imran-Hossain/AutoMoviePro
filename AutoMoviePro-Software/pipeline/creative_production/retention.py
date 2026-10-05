"""Retention structure + title/thumbnail honesty. Extends retention_architecture."""
from __future__ import annotations

import re
from typing import Any, Optional

from pipeline.creative_production.script_quality import CLICKBAIT, classify_hook
from pipeline.retention_architecture import attach_retention_to_plan, retention_blueprint

_HOOKISH = re.compile(
    r"\b(why|how|what|most (?:people|viewers)|miss|secret|hidden|wait|"
    r"look|watch|stay|but|however|instead|actually|not what|changes?|"
    r"overlooked|detail|explainers|takeaway|evidence|reveal|payoff)\b|"
    r"\?",
    re.I,
)
_FLAT_OPEN = re.compile(
    r"^(the|a|an|this|in this|today we|let us|let's)\b",
    re.I,
)
_PAYOFFISH = re.compile(
    r"\b(because|so|that(?:'s| is) why|evidence|proves?|means?|reveals?|"
    r"shows?|result|answer|payoff|therefore|in short)\b",
    re.I,
)


def _narrations(plan: dict[str, Any]) -> list[str]:
    scenes = [s for s in (plan.get("scenes") or plan.get("beats") or []) if isinstance(s, dict)]
    out = []
    for s in scenes:
        t = str(s.get("narration") or s.get("text") or s.get("dialogue") or "").strip()
        if t:
            out.append(t)
    return out


def validate_retention_structure(plan: dict[str, Any]) -> dict[str, Any]:
    scenes = [s for s in (plan.get("scenes") or plan.get("beats") or []) if isinstance(s, dict)]
    issues: list[str] = []
    warnings: list[str] = []
    if not scenes:
        return {"status": "BLOCK", "issues": ["no_scenes_for_retention"], "method": "DETERMINISTIC"}
    attached = attach_retention_to_plan(dict(plan))
    role_rows = [
        s
        for s in (attached.get("scenes") or attached.get("beats") or [])
        if isinstance(s, dict)
    ]
    roles = [
        str((s.get("retention") or {}).get("role") or s.get("retention_role") or "")
        for s in role_rows
    ]
    if scenes and "pattern_interrupt" not in roles and "hook" not in roles:
        if not any(r.strip() for r in roles):
            issues.append("missing_retention_roles")

    narrations = _narrations(attached)
    bp = retention_blueprint(str(plan.get("video_type") or "short"))

    # Opening must be hookish
    if narrations:
        first = narrations[0]
        if _FLAT_OPEN.search(first) and not _HOOKISH.search(first):
            issues.append("opening_not_retention_hook")
        if not _HOOKISH.search(first):
            issues.append("opening_missing_curiosity_signal")

    # Topic continuity
    if len(narrations) >= 2:
        first_kw = set(re.findall(r"[a-z0-9]{4,}", narrations[0].lower()))
        rest = set(re.findall(r"[a-z0-9]{4,}", " ".join(narrations[1:]).lower()))
        if first_kw and rest and len(first_kw & rest) == 0:
            issues.append("topic_jump_no_shared_information")

    # Mid-script re-hooks: forbid long flat streaks
    flat_streak = 0
    max_flat = 0
    hook_signals = 0
    payoff_signals = 0
    question_marks = 0
    for i, text in enumerate(narrations):
        is_hook = bool(_HOOKISH.search(text))
        is_payoff = bool(_PAYOFFISH.search(text))
        if "?" in text:
            question_marks += 1
        if is_hook:
            hook_signals += 1
            flat_streak = 0
        else:
            flat_streak += 1
            max_flat = max(max_flat, flat_streak)
        if is_payoff:
            payoff_signals += 1
        # Mid beats should not be pure cold description
        if i >= 2 and i < len(narrations) - 1 and not is_hook and _FLAT_OPEN.search(text):
            warnings.append(f"mid_beat_flat_open:{i}")

    forbid = int(bp.get("forbid_flat_streak") or 2)
    if max_flat > forbid and len(narrations) >= 4:
        # After deterministic cadence repair, treat as warning (still visible)
        meta = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
        if meta.get("retention_cadence_enforced"):
            warnings.append(f"flat_description_streak:{max_flat}")
        else:
            issues.append(f"flat_description_streak:{max_flat}")

    # Need curiosity / question / re-hook density
    if len(narrations) >= 4 and hook_signals < max(2, len(narrations) // 3):
        issues.append("insufficient_rehook_density")
    if len(narrations) >= 5 and question_marks + hook_signals < 2:
        issues.append("no_mid_retention_questions_or_hooks")
    if len(narrations) >= 4 and payoff_signals < 1:
        warnings.append("weak_payoff_language")

    # Ending should feel like a close, not a new encyclopedia dump
    if bp.get("require_ending_close") and len(narrations) >= 3:
        last = narrations[-1]
        if _FLAT_OPEN.search(last) and not (_PAYOFFISH.search(last) or _HOOKISH.search(last)):
            warnings.append("ending_not_closing_loop")

    # Explicit open_loop / payoff_for metadata when provided
    opens = [str(s.get("open_loop") or "").strip() for s in scenes if str(s.get("open_loop") or "").strip()]
    closes = [str(s.get("payoff_for") or "").strip() for s in scenes if str(s.get("payoff_for") or "").strip()]
    min_opens = int(bp.get("min_open_loops") or 0)
    if opens and len(opens) < min_opens and len(scenes) >= 5:
        warnings.append(f"open_loops_below_target:{len(opens)}<{min_opens}")
    if opens and closes:
        ratio = len(closes) / max(1, len(opens))
        min_ratio = float(bp.get("min_loop_close_ratio") or 0.0)
        if ratio + 1e-9 < min_ratio:
            warnings.append(f"loop_close_ratio_low:{ratio:.2f}")

    status = "BLOCK" if issues else "PASS"
    return {
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "blueprint": bp,
        "roles": roles,
        "hook_signals": hook_signals,
        "payoff_signals": payoff_signals,
        "question_marks": question_marks,
        "method": "DETERMINISTIC",
    }


def validate_title_video_consistency(
    *,
    title: str,
    topic: str = "",
    narrations: Optional[list[str]] = None,
    thumbnail_claim: str = "",
) -> dict[str, Any]:
    issues: list[str] = []
    body = " ".join([topic or "", title or "", *(narrations or [])]).lower()
    tlow = (title or "").lower()
    if any(c in tlow for c in CLICKBAIT):
        issues.append("clickbait_title")
    # Vague non-SEO titles
    if re.fullmatch(r"(amazing|incredible|best|top)\s+(facts?|things?|tips?)", tlow or ""):
        issues.append("vague_non_seo_title")
    if len(re.findall(r"[a-z0-9]{4,}", tlow)) < 3:
        issues.append("title_too_thin_for_seo")
    hook = classify_hook(title, topic=topic)
    if hook.get("unsupported_claim"):
        issues.append("unsupported_title_claim")
    title_kw = set(re.findall(r"[a-z0-9]{4,}", tlow))
    body_kw = set(re.findall(r"[a-z0-9]{4,}", body))
    if title_kw and body_kw:
        if len(title_kw & body_kw) / max(1, len(title_kw)) < 0.15:
            issues.append("title_not_grounded_in_video")
    thumb = (thumbnail_claim or title or "").lower()
    if any(c in thumb for c in CLICKBAIT):
        issues.append("clickbait_thumbnail")
    thumb_kw = set(re.findall(r"[a-z0-9]{4,}", thumb))
    if thumb_kw and body_kw and len(thumb_kw & body_kw) / max(1, len(thumb_kw)) < 0.15:
        issues.append("thumbnail_promise_absent_from_video")
    status = "BLOCK" if issues else "PASS"
    return {"status": status, "issues": issues, "method": "DETERMINISTIC"}
