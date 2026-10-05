"""Deterministic script / hook quality — prevention before generation.

Does NOT replace BUILD-04F evaluate_script_quality. This layer blocks
obvious structural failures before expensive providers.
"""
from __future__ import annotations

import re
from typing import Any, Optional

GENERIC_HOOKS = (
    "today we will discuss",
    "today we're going to discuss",
    "in this video",
    "in today's video",
    "hey guys",
    "hello everyone",
    "welcome back",
    "without further ado",
    "let's get started",
    "good morning",
    "what's up everybody",
    "welcome to this video",
    "welcome to our channel",
    "welcome to the channel",
    "welcome to today's",
    "have you ever wondered",
    "are you curious about",
    "in this episode",
    "in today's episode",
    "today we take a look at",
    "let us examine",
    "before we begin",
    "before we start",
    "according to the dictionary",
    "by definition",
    "webster's dictionary defines",
)

CLICKBAIT = (
    "you won't believe",
    "you wont believe",
    "doctors hate",
    "shocking truth",
    "this one trick",
    "gone wrong",
    "secret they don't want",
    "miracle cure",
)

FILLER = (
    "as we all know",
    "it goes without saying",
    "needless to say",
    "at the end of the day",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def classify_hook(text: str, *, topic: str = "") -> dict[str, Any]:
    raw = text or ""
    low = _norm(raw)
    generic = any(g in low for g in GENERIC_HOOKS)
    clickbait = any(c in low for c in CLICKBAIT)
    topic_kw = set(re.findall(r"[a-z0-9]{4,}", (topic or "").lower()))
    hook_kw = set(re.findall(r"[a-z0-9]{4,}", low))
    overlap = len(topic_kw & hook_kw) / max(1, len(topic_kw)) if topic_kw else 1.0
    topic_aligned = overlap >= 0.1 or not topic_kw
    sensational = bool(re.search(r"\b(always|never|guaranteed|100%|miracle)\b", low))
    unsupported = clickbait or (sensational and not topic_aligned)
    issues: list[str] = []
    if generic:
        issues.append("weak_generic_hook")
    if clickbait:
        issues.append("clickbait_hook")
    if unsupported:
        issues.append("unsupported_hook_claim")
    if topic_kw and overlap < 0.1:
        issues.append("hook_topic_mismatch")
    # Topic mismatch is production-blocking (PART-5B): hook must be topic-specific.
    status = (
        "BLOCK"
        if (generic or clickbait or unsupported or (topic_kw and overlap < 0.1))
        else ("WARN" if issues else "PASS")
    )
    return {
        "status": status,
        "generic": generic,
        "clickbait": clickbait,
        "unsupported_claim": unsupported,
        "topic_aligned": topic_aligned,
        "overlap": round(overlap, 4),
        "issues": issues,
        "method": "DETERMINISTIC",
    }


def score_opening_attention(text: str, *, topic: str = "") -> dict[str, Any]:
    """Deterministic first-beat attention gate (not a viewer KPI claim).

    Blocks openings that cannot hold niche documentary attention: too short/long,
    generic, mid-doc cold open, or topic-detached. Does not claim guaranteed engagement.
    """
    raw = (text or "").strip()
    low = _norm(raw)
    issues: list[str] = []
    words = low.split()
    if len(words) < 6:
        issues.append("opening_too_short")
    if len(words) > 55:
        issues.append("opening_too_long_for_hook")
    if any(g in low for g in GENERIC_HOOKS):
        issues.append("opening_generic_filler")
    specifics = len(re.findall(r"\d|[A-Z][a-z]{3,}", raw))
    has_curiosity = bool(
        re.search(
            r"[?]|\b(why|how|what if|what most|secret|hidden|never|before|most people|"
            r"watch|look closer|pay attention|changes everything|you think|nobody)\b",
            low,
        )
    )
    mid_doc = bool(
        re.match(r"^(the|a|an)\s+", low)
        and re.search(
            r"\b(floats|sits|orbits|reveals|shows|is unveiling|appears|stands|rotates|"
            r"protects|holding|facing|pierces|unveiling)\b",
            low,
        )
        and not has_curiosity
    )
    if mid_doc:
        issues.append("opening_mid_documentary_cold_open")
    if specifics < 1 and not has_curiosity and len(words) >= 6:
        issues.append("opening_low_specificity_or_curiosity")
    if not has_curiosity and len(words) >= 8:
        issues.append("opening_no_curiosity_hook")
    topic_kw = set(re.findall(r"[a-z0-9]{4,}", (topic or "").lower()))
    hook_kw = set(re.findall(r"[a-z0-9]{4,}", low))
    overlap = len(topic_kw & hook_kw) / max(1, len(topic_kw)) if topic_kw else 1.0
    if topic_kw and overlap < 0.1:
        issues.append("opening_topic_detached")
    # Score 0–1 for telemetry; BLOCK when structural failures present
    score = 1.0
    if issues:
        score = max(0.0, 1.0 - 0.18 * len(issues))
    if overlap >= 0.2:
        score = min(1.0, score + 0.1)
    if has_curiosity:
        score = min(1.0, score + 0.08)
    blocking = {
        "opening_too_short",
        "opening_generic_filler",
        "opening_topic_detached",
        "opening_low_specificity_or_curiosity",
        "opening_mid_documentary_cold_open",
        "opening_no_curiosity_hook",
    }
    hard = [i for i in issues if i in blocking or i == "opening_too_long_for_hook"]
    status = "BLOCK" if hard else ("WARN" if issues else "PASS")
    return {
        "status": status,
        "score": round(score, 3),
        "overlap": round(overlap, 4),
        "issues": issues,
        "claims_guaranteed_engagement": False,
        "method": "DETERMINISTIC",
    }


def looks_like_cold_open(text: str) -> bool:
    """True when narration starts mid-description with no retention hook."""
    r = score_opening_attention(text)
    return any(
        i in (r.get("issues") or [])
        for i in (
            "opening_mid_documentary_cold_open",
            "opening_no_curiosity_hook",
            "opening_generic_filler",
            "opening_too_short",
        )
    )


def rewrite_cold_open_hook(text: str, *, topic: str = "") -> str:
    """Deterministic industrial cold-open → curiosity-gap hook (no LLM)."""
    subject = (topic or "").strip()
    if not subject:
        m = re.search(
            r"\b((?:The\s+)?[A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,5})\b",
            text or "",
        )
        subject = (m.group(1) if m else "this mission").strip()
    # Prefer a concrete noun phrase under ~8 words
    sub_words = subject.split()
    if len(sub_words) > 8:
        subject = " ".join(sub_words[:8])
    detail = re.sub(r"\s+", " ", (text or "").strip())
    # Keep one concrete clause from the original for continuity
    clause = ""
    for part in re.split(r"[.!?]+\s*", detail):
        p = part.strip()
        if len(p.split()) >= 5:
            clause = p[:110].rstrip(",;:")
            break
    if clause and subject.lower() not in clause.lower():
        return (
            f"Most viewers miss this about {subject} — {clause[0].lower() + clause[1:] if clause[:1].isupper() else clause}. "
            f"Stay for the evidence."
        )
    if clause:
        return (
            f"Why does {subject} matter right now? {clause}. "
            f"Watch the payoff."
        )
    return (
        f"What {subject} just exposed changes how we map the evidence — "
        f"look closer in the next few seconds."
    )


def enforce_opening_hook_on_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Force scene-0 / hook beat into a retention-grade cold open when weak."""
    plan = dict(plan or {})
    topic = str(plan.get("topic") or plan.get("title") or "").strip()
    key = "beats" if plan.get("beats") else "scenes"
    rows = list(plan.get(key) or [])
    if not rows:
        return plan
    row0 = rows[0] if isinstance(rows[0], dict) else None
    if not row0:
        return plan
    field = "narration" if "narration" in row0 or not row0.get("text") else "text"
    if not row0.get(field) and row0.get("dialogue"):
        field = "dialogue"
    text = str(row0.get(field) or row0.get("narration") or row0.get("text") or "").strip()
    if not text:
        return plan
    opening = score_opening_attention(text, topic=topic)
    if opening.get("status") != "BLOCK" and not looks_like_cold_open(text):
        plan["hook"] = text
        return plan
    rewritten = rewrite_cold_open_hook(text, topic=topic)
    row0[field] = rewritten
    row0["narration"] = rewritten
    row0["retention_role"] = "pattern_interrupt"
    row0["open_loop"] = row0.get("open_loop") or f"What makes {topic or 'this'} different?"
    row0["element"] = row0.get("element") or "intro"
    rows[0] = row0
    plan[key] = rows
    plan["hook"] = rewritten
    meta = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
    meta = dict(meta or {})
    meta["opening_hook_enforced"] = True
    meta["opening_hook_prior"] = text[:200]
    meta["opening_hook_issues"] = opening.get("issues") or []
    plan["metadata"] = meta
    return plan


_MID_REHOOK_PREFIXES = (
    "But here's the detail most explainers skip — ",
    "Why does that matter right now? ",
    "Watch what this changes next — ",
    "What most viewers overlook next is this: ",
)


def _needs_mid_rehook(text: str) -> bool:
    low = (text or "").strip()
    if not low:
        return False
    if "?" in low:
        return False
    if re.search(
        r"\b(why|how|what|most (?:people|viewers)|miss|but|however|actually|instead|watch|stay|"
        r"overlooked|detail|explainers|takeaway|reveal)\b",
        low,
        re.I,
    ):
        return False
    # Any mid beat without curiosity language needs a re-hook
    if re.match(r"^(the|a|an|this|also|then|next|in|it|there)\b", low, re.I):
        return True
    return len(low.split()) >= 5


def enforce_retention_cadence_on_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Inject mid-script re-hooks and ending loop-close language when beats are flat."""
    plan = dict(plan or {})
    topic = str(plan.get("topic") or plan.get("title") or "").strip()
    key = "beats" if plan.get("beats") else "scenes"
    rows = list(plan.get(key) or [])
    if len(rows) < 3:
        return plan
    repairs: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        field = "narration" if "narration" in row or not row.get("text") else "text"
        if not row.get(field) and row.get("dialogue"):
            field = "dialogue"
        text = str(row.get(field) or row.get("narration") or row.get("text") or "").strip()
        if not text:
            continue
        # Skip first (handled by opening hook) 
        if i == 0:
            row.setdefault("retention_role", "pattern_interrupt")
            rows[i] = row
            continue
        # Mid beats: force re-hook language on flat descriptive chains
        if 0 < i < len(rows) - 1 and _needs_mid_rehook(text):
            prefix = _MID_REHOOK_PREFIXES[i % len(_MID_REHOOK_PREFIXES)]
            # Avoid double-prefixing
            if not text.lower().startswith(prefix.lower()[:12]):
                body = text[0].lower() + text[1:] if text[:1].isupper() else text
                rewritten = f"{prefix}{body}"
                # Keep spoken length sane
                words = rewritten.split()
                if len(words) > 42:
                    rewritten = " ".join(words[:40]).rstrip(",;") + "."
                row[field] = rewritten
                row["narration"] = rewritten
                row["retention_role"] = row.get("retention_role") or (
                    "question" if i % 2 else "evidence"
                )
                row["open_loop"] = row.get("open_loop") or (
                    f"What happens after this {topic.split()[0] if topic else 'reveal'}?"
                )
                repairs.append({"index": i, "action": "mid_rehook", "prior": text[:120]})
        # Ending: ensure close language
        if i == len(rows) - 1:
            low = text.lower()
            if not re.search(r"\b(so|because|means|leaves|proves|answer|watch for|remember)\b", low):
                closer = (
                    f" So the takeaway on {topic or 'this'}: "
                    if topic
                    else " So the takeaway: "
                )
                if closer.strip().lower() not in low:
                    rewritten = text.rstrip(".!? ") + "." + closer + "hold that detail."
                    words = rewritten.split()
                    if len(words) > 44:
                        rewritten = " ".join(words[:42]).rstrip(",;") + "."
                    row[field] = rewritten
                    row["narration"] = rewritten
                    repairs.append({"index": i, "action": "ending_close", "prior": text[:120]})
            row["retention_role"] = row.get("retention_role") or "ending"
            row["payoff_for"] = row.get("payoff_for") or "main_open_loop"
        rows[i] = row
    plan[key] = rows
    if repairs:
        meta = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
        meta = dict(meta or {})
        meta["retention_cadence_enforced"] = True
        meta["retention_cadence_repairs"] = repairs
        plan["metadata"] = meta
    if rows and isinstance(rows[0], dict):
        plan["hook"] = str(
            rows[0].get("narration") or rows[0].get("text") or plan.get("hook") or ""
        ).strip()
    return plan


_AI_PATTERN_PHRASES = (
    "in today's rapidly evolving",
    "it is important to note that",
    "in conclusion, it is clear",
    "delve into the",
    "tapestry of",
    "landscape of",
    "multifaceted",
    "as an ai",
)


def evaluate_script_naturalness(narrations: list[str]) -> dict[str, Any]:
    """Hard style gate using robot_detector + AI-pattern phrases.

    Honesty: does not prove human authorship; blocks clearly robotic scripts.
    """
    issues: list[str] = []
    try:
        from pipeline.robot_detector import robot_score

        robot = robot_score(narrations)
    except Exception as exc:
        return {
            "status": "UNKNOWN",
            "ok": False,
            "issues": [f"naturalness_probe_failed:{exc}"],
            "claims_human_written": False,
            "method": "UNKNOWN",
        }
    if not robot.get("passed", True):
        issues.extend([f"robot:{x}" for x in (robot.get("issues") or ["robot_fail"])])
    blob = _norm(" ".join(narrations or []))
    for p in _AI_PATTERN_PHRASES:
        if p in blob:
            issues.append(f"ai_pattern:{p}")
    status = "BLOCK" if issues else "PASS"
    return {
        "status": status,
        "ok": not issues,
        "issues": issues,
        "robot": robot,
        "claims_human_written": False,
        "method": "DETERMINISTIC_HEURISTIC",
    }


def detect_information_repetition(narrations: list[str]) -> dict[str, Any]:
    issues: list[str] = []
    norms = [re.sub(r"\s+", " ", (n or "").strip().lower()) for n in narrations]
    for i in range(1, len(norms)):
        a, b = norms[i - 1], norms[i]
        if a and b and a == b:
            issues.append(f"repetition_scene_{i}")
        elif a and b and len(a) > 50 and a[:72] == b[:72]:
            issues.append(f"repetition_scene_{i}")
    starts = [tuple((n or "").lower().split()[:5]) for n in narrations if (n or "").strip()]
    if len(starts) >= 4 and len(set(starts)) == 1:
        issues.append("robotic_sentence_starts")
    return {"status": "BLOCK" if issues else "PASS", "issues": issues, "method": "DETERMINISTIC"}


def detect_filler_and_length(narrations: list[str]) -> dict[str, Any]:
    issues: list[str] = []
    for i, n in enumerate(narrations):
        low = _norm(n)
        if any(f in low for f in FILLER):
            issues.append(f"filler_scene_{i}")
        words = low.split()
        if len(words) > 80:
            issues.append(f"excessive_sentence_length_scene_{i}")
    return {"status": "WARN" if issues else "PASS", "issues": issues, "method": "HEURISTIC"}


_EXPAND_CLAUSES = (
    "that mission planners can verify against flight telemetry",
    "using calibrated instruments amid real thermal stress",
    "so future crews can trust the mapped deposits",
    "without inventing unsupported claims beyond the evidence",
    "while keeping the causal chain clear for viewers",
    "tied to the same subject introduced one beat earlier",
)


def _estimate_spoken(text: str) -> float:
    try:
        from pipeline.dialogue_sync import estimate_spoken_seconds

        return float(estimate_spoken_seconds(text) or 0.0)
    except Exception:
        return len((text or "").split()) / 2.5


def enforce_dialogue_window_on_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Deterministic 7–9s spoken-window + light continuity repair on ScriptPlan/beats.

    Expands thin beats and injects a bridge noun from the previous beat when
    adjacent dialogues share no content keywords. Does not call providers.
    """
    from pipeline.quality.thresholds import DEFAULT_MAX_DIALOGUE_SEC, DEFAULT_MIN_DIALOGUE_SEC
    from pipeline.prompt_engineering import WORDS_PER_BEAT_MAX, WORDS_PER_BEAT_MIN
    import os

    plan = enforce_opening_hook_on_plan(plan)
    plan = enforce_retention_cadence_on_plan(plan)
    plan = dict(plan or {})
    topic = str(plan.get("topic") or "").strip()
    topic_kw = [w for w in re.findall(r"[A-Za-z0-9]{4,}", topic) if w.lower() not in ("that", "with", "from", "this")]
    min_d = float(os.environ.get("AMP_MIN_DIALOGUE_SEC", DEFAULT_MIN_DIALOGUE_SEC))
    max_d = float(os.environ.get("AMP_MAX_DIALOGUE_SEC", DEFAULT_MAX_DIALOGUE_SEC))
    key = "beats" if plan.get("beats") else "scenes"
    rows = list(plan.get(key) or [])
    repairs: list[dict[str, Any]] = []
    prev_text = ""
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        field = "narration" if "narration" in row or not row.get("text") else "text"
        if not row.get(field) and row.get("dialogue"):
            field = "dialogue"
        text = str(row.get(field) or row.get("narration") or row.get("text") or row.get("dialogue") or "").strip()
        if not text:
            continue
        # Continuity bridge
        if prev_text:
            prev_kw = set(re.findall(r"[a-z0-9]{4,}", prev_text.lower()))
            cur_kw = set(re.findall(r"[a-z0-9]{4,}", text.lower()))
            if prev_kw and cur_kw and len(prev_kw & cur_kw) == 0 and len(cur_kw) >= 3:
                stop = {
                    "building",
                    "permanently",
                    "using",
                    "that",
                    "this",
                    "from",
                    "with",
                    "into",
                    "just",
                    "very",
                    "more",
                    "than",
                    "about",
                    "will",
                    "have",
                    "been",
                    "were",
                    "their",
                    "these",
                    "those",
                    "mission",
                    "planners",
                    "verify",
                    "against",
                    "flight",
                }
                bridge_candidates = [w for w in sorted(prev_kw, key=len, reverse=True) if w not in stop and len(w) >= 5]
                bridge = bridge_candidates[0] if bridge_candidates else ""
                if bridge:
                    # Avoid "Building on …" — location extractors misread "building"
                    text = f"From that {bridge}, {text[0].lower() + text[1:] if text[:1].isupper() and len(text) > 1 else text}"
                    repairs.append({"i": i, "action": "bridge", "bridge": bridge})
        # Expand toward ≥7s / ≥WORDS_PER_BEAT_MIN
        est = _estimate_spoken(text)
        words = text.split()
        clause_i = 0
        while (est < min_d - 0.35 or len(words) < WORDS_PER_BEAT_MIN) and clause_i < len(_EXPAND_CLAUSES):
            clause = _EXPAND_CLAUSES[(i + clause_i) % len(_EXPAND_CLAUSES)]
            if topic_kw:
                anchor = topic_kw[i % len(topic_kw)]
                addition = f" — {clause}, focused on {anchor}"
            else:
                addition = f" — {clause}"
            candidate = (text.rstrip(". ") + addition + ".").strip()
            if len(candidate.split()) > WORDS_PER_BEAT_MAX + 4:
                break
            text = candidate
            words = text.split()
            est = _estimate_spoken(text)
            repairs.append({"i": i, "action": "expand", "est_sec": round(est, 2)})
            clause_i += 1
        # Soft trim if wildly long (keep first WORDS_PER_BEAT_MAX+2 words)
        if len(words) > WORDS_PER_BEAT_MAX + 6 or est > max_d + 1.5:
            text = " ".join(words[: WORDS_PER_BEAT_MAX + 2]).rstrip(",;:") + "."
            est = _estimate_spoken(text)
            repairs.append({"i": i, "action": "trim", "est_sec": round(est, 2)})
        row[field] = text
        if "narration" not in row:
            row["narration"] = text
        row["estimated_duration_sec"] = round(max(min_d, min(max_d, est or min_d)), 2)
        rows[i] = row
        prev_text = text
    plan[key] = rows
    if plan.get("hook") and rows:
        first = str(rows[0].get("narration") or rows[0].get("text") or "")
        if first:
            plan["hook"] = first
    plan.setdefault("metadata", {})
    if isinstance(plan["metadata"], dict):
        plan["metadata"]["dialogue_window_repairs"] = repairs
        plan["metadata"]["dialogue_window_enforced"] = True
    return plan


def validate_script_structure(
    plan: dict[str, Any],
    *,
    scenes: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    rows = list(scenes if scenes is not None else (plan.get("scenes") or []))
    narrations = [
        str(r.get("narration") or r.get("dialogue") or "") for r in rows if isinstance(r, dict)
    ]
    topic = str(plan.get("topic") or plan.get("title") or "")
    issues: list[str] = []
    if not rows:
        issues.append("no_scenes")
    if not topic.strip():
        issues.append("missing_topic")
    opening_text = narrations[0] if narrations else ""
    hook = classify_hook(opening_text, topic=topic)
    issues.extend(hook.get("issues") or [])
    opening = score_opening_attention(opening_text, topic=topic)
    issues.extend(opening.get("issues") or [])
    natural = evaluate_script_naturalness(narrations)
    if natural.get("status") == "BLOCK":
        issues.extend(natural.get("issues") or [])
    rep = detect_information_repetition(narrations)
    issues.extend(rep.get("issues") or [])
    fill = detect_filler_and_length(narrations)
    issues.extend(fill.get("issues") or [])
    # Abrupt empty middle
    if any(len((n or "").strip()) < 8 for n in narrations):
        issues.append("empty_or_too_short_scene")
    blocking = [
        i
        for i in issues
        if i.startswith("weak_generic")
        or i.startswith("clickbait")
        or i.startswith("unsupported")
        or i.startswith("hook_topic")
        or i.startswith("opening_")
        or i.startswith("robot:")
        or i.startswith("ai_pattern:")
        or i in ("no_scenes", "missing_topic", "empty_or_too_short_scene")
        or i.startswith("repetition_")
    ]
    status = "BLOCK" if blocking else ("WARN" if issues else "PASS")
    return {
        "status": status,
        "issues": issues,
        "hook": hook,
        "opening": opening,
        "naturalness": natural,
        "repetition": rep,
        "filler": fill,
        "method": "DETERMINISTIC",
        "scene_count": len(rows),
    }


def validate_script_plan_preflight(
    plan: dict[str, Any] | None,
    *,
    require_evidence: bool = True,
) -> dict[str, Any]:
    """C05-TRS structural preflight — deterministic BLOCK / HEURISTIC WARNING / UNKNOWN.

    Does NOT claim human-written, engagement, or perfect storytelling.
    """
    plan = dict(plan or {})
    blocks: list[str] = []
    warnings: list[str] = []
    unknowns: list[str] = []

    topic = str(plan.get("topic") or "").strip()
    if not topic:
        blocks.append("missing_topic")

    beats = list(plan.get("beats") or [])
    scenes = list(plan.get("scenes") or [])
    rows = beats if beats else scenes
    if not rows:
        blocks.append("empty_narrative")

    narrations = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        text = str(row.get("narration") or row.get("text") or row.get("dialogue") or "").strip()
        narrations.append(text)
        if not text:
            blocks.append(f"empty_narrative_beat:{i}")
        speaker = str(row.get("speaker") or "").strip()
        if beats and not speaker:
            blocks.append(f"missing_speaker:{i}")
        # Emotion / action heuristics
        emo = str(row.get("emotion") or row.get("emotional_intent") or "").strip()
        if text and ("!" in text or "?" in text) and not emo:
            warnings.append(f"missing_emotional_intent:{i}")
        action = str(row.get("action_intent") or row.get("action") or "").strip()
        if any(v in text.lower() for v in ("opened", "stood", "sat", "entered", "holding")) and not action:
            warnings.append(f"missing_action_intent:{i}")
        loc = str(row.get("location_ref") or row.get("location") or "").strip()
        if any(v in text.lower() for v in ("office", "hospital", "street", "kitchen")) and not loc:
            warnings.append(f"unresolved_location:{i}")
        dur = row.get("estimated_duration_sec")
        if dur is not None:
            try:
                if float(dur) < 0:
                    blocks.append(f"malformed_duration:{i}")
            except Exception:
                blocks.append(f"malformed_duration:{i}")

    # Live marathon criteria: each spoken beat ≈ 7–9 seconds (env-overridable)
    try:
        import os

        from pipeline.dialogue_sync import estimate_spoken_seconds
        from pipeline.quality.thresholds import DEFAULT_MAX_DIALOGUE_SEC, DEFAULT_MIN_DIALOGUE_SEC

        min_d = float(os.environ.get("AMP_MIN_DIALOGUE_SEC", DEFAULT_MIN_DIALOGUE_SEC))
        max_d = float(os.environ.get("AMP_MAX_DIALOGUE_SEC", DEFAULT_MAX_DIALOGUE_SEC))
        for i, text in enumerate(narrations):
            if not text:
                continue
            try:
                est = float(estimate_spoken_seconds(text) or 0.0)
            except Exception:
                est = len(text.split()) / 2.5
            # Soft band matches creative gate: only hard-block clear overruns
            if est > max_d + 2.0:
                blocks.append(f"dialogue_too_long:{i}:{est:.1f}s")
            elif est > max_d + 0.75:
                warnings.append(f"dialogue_soft_long:{i}:{est:.1f}s")
            elif 0 < est < min_d - 1.0:
                warnings.append(f"dialogue_too_short:{i}:{est:.1f}s")
            # Adjacent continuity (lexical bridge)
            if i > 0 and narrations[i - 1]:
                prev_kw = set(re.findall(r"[a-z0-9]{4,}", narrations[i - 1].lower()))
                cur_kw = set(re.findall(r"[a-z0-9]{4,}", text.lower()))
                if prev_kw and cur_kw and len(prev_kw & cur_kw) == 0 and len(cur_kw) >= 4:
                    warnings.append(f"dialogue_bridge_weak:{i}")
    except Exception:
        unknowns.append("dialogue_duration_preflight_unavailable")

    # Hook + opening attention (PART-5B)
    hook_text = str(plan.get("hook") or (narrations[0] if narrations else "")).strip()
    if not hook_text:
        blocks.append("missing_hook")
    else:
        hook = classify_hook(hook_text, topic=topic)
        if hook.get("status") == "BLOCK":
            blocks.extend(hook.get("issues") or ["weak_hook"])
        elif hook.get("issues"):
            warnings.extend(hook.get("issues") or [])
        opening = score_opening_attention(hook_text, topic=topic)
        if opening.get("status") == "BLOCK":
            blocks.extend(opening.get("issues") or ["weak_opening"])
        elif opening.get("issues"):
            warnings.extend(opening.get("issues") or [])

    # Mid-script industrial retention cadence
    try:
        from pipeline.creative_production.retention import validate_retention_structure

        ret = validate_retention_structure(plan)
        if ret.get("status") == "BLOCK":
            blocks.extend(ret.get("issues") or ["retention_structure_fail"])
        for w in ret.get("warnings") or []:
            warnings.append(str(w))
    except Exception:
        unknowns.append("retention_structure_preflight_unavailable")

    # Naturalness hard gate (does not claim human-written)
    natural = evaluate_script_naturalness(narrations)
    if natural.get("status") == "BLOCK":
        blocks.extend(natural.get("issues") or ["naturalness_fail"])
    elif natural.get("status") == "UNKNOWN":
        unknowns.extend(natural.get("issues") or ["naturalness_unknown"])

    # Claims ↔ evidence
    claims = list(plan.get("claims") or [])
    evidence_refs = set(str(x) for x in (plan.get("evidence_refs") or []))
    for c in claims:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or c.get("claim_id") or "")
        refs = c.get("evidence_refs") or c.get("evidence") or []
        if require_evidence and c.get("mandatory") and not refs and cid not in evidence_refs:
            blocks.append(f"unsupported_mandatory_claim:{cid or 'unknown'}")
        if c.get("contradiction"):
            blocks.append(f"contradictory_claim:{cid or 'unknown'}")

    # Chronology heuristic
    temporal_marks = []
    for i, n in enumerate(narrations):
        low = n.lower()
        if "yesterday" in low:
            temporal_marks.append((i, 0))
        if "today" in low:
            temporal_marks.append((i, 1))
        if "tomorrow" in low:
            temporal_marks.append((i, 2))
    if len(temporal_marks) >= 2:
        vals = [t for _, t in temporal_marks]
        if vals != sorted(vals):
            blocks.append("impossible_chronology")

    # Repetition
    rep = detect_information_repetition(narrations)
    if rep.get("status") == "BLOCK":
        blocks.extend(rep.get("issues") or [])
    fill = detect_filler_and_length(narrations)
    if fill.get("issues"):
        warnings.extend(fill.get("issues") or [])
        # stylistic → HEURISTIC
        unknowns.append("stylistic_naturalness_unknown")

    # Provider-specific visual prompts must not be treated as canonical ownership
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if row.get("exact_ai_video_prompt") and not row.get("visual_implication"):
            warnings.append(f"legacy_visual_prompt_present:{i}")

    status = "BLOCKED" if blocks else ("WARNING" if warnings else "PASS")
    return {
        "status": status,
        "ok": not blocks,
        "blocked": bool(blocks),
        "blocks": blocks,
        "warnings": warnings,
        "unknowns": unknowns,
        "confidence": "HEURISTIC" if warnings or unknowns else "DETERMINISTIC",
        "claims_human_written": False,
        "claims_guaranteed_engagement": False,
        "method": "DETERMINISTIC_PREFLIGHT",
        "note": "stylistic judgments are HEURISTIC; naturalness not proven",
    }
