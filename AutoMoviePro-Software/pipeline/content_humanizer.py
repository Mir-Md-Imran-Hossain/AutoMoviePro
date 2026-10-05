"""
Human-voice content audit + rewrite.

Goal: titles, descriptions, tags, and narrations should read like a real creator —
not ChatGPT boilerplate — while keeping English-master + product locks intact.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Phrases that scream "AI wrote this" in YouTube/SEO copy
AI_TELL_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("delve", re.compile(r"\bdelve(?:s|d|ing)?\b", re.I)),
    ("landscape", re.compile(r"\bin today's (?:fast[- ]paced )?digital landscape\b", re.I)),
    ("moreover", re.compile(r"\bmoreover\b", re.I)),
    ("furthermore", re.compile(r"\bfurthermore\b", re.I)),
    ("in_conclusion", re.compile(r"\bin conclusion\b", re.I)),
    ("it_is_important", re.compile(r"\bit is important to note\b", re.I)),
    ("unlock_potential", re.compile(r"\bunlock(?:ing)? (?:your|the) potential\b", re.I)),
    ("game_changer", re.compile(r"\bgame[- ]changer\b", re.I)),
    ("revolutionize", re.compile(r"\brevolutionize\b", re.I)),
    ("seamless", re.compile(r"\bseamlessly\b", re.I)),
    ("dive_in", re.compile(r"\blet'?s dive (?:in|into)\b", re.I)),
    ("ever_wondered", re.compile(r"\bever wondered\b", re.I)),
    ("in_this_video", re.compile(r"\bin this (?:video|article) we will\b", re.I)),
    ("comprehensive_guide", re.compile(r"\bcomprehensive guide\b", re.I)),
    ("tapestry", re.compile(r"\btapestry\b", re.I)),
    ("beacon", re.compile(r"\bbeacon of\b", re.I)),
    ("nestled", re.compile(r"\bnestled\b", re.I)),
    ("embark", re.compile(r"\bembark(?:s|ed|ing)?\b", re.I)),
    ("cutting_edge_spam", re.compile(r"\bcutting[- ]edge (?:technology|solution)s?\b", re.I)),
    ("leverage", re.compile(r"\bleverage\b", re.I)),
    ("welcome_back", re.compile(r"\bwelcome back\b", re.I)),
    ("hello_everyone", re.compile(r"\bhello everyone\b", re.I)),
    ("hey_guys", re.compile(r"\bhey guys\b", re.I)),
    ("without_further_ado", re.compile(r"\bwithout further ado\b", re.I)),
    ("lets_get_started", re.compile(r"\blet'?s get started\b", re.I)),
    ("testament_to", re.compile(r"\ba testament to\b", re.I)),
    ("plethora", re.compile(r"\ba plethora of\b", re.I)),
    ("myriad", re.compile(r"\ba myriad of\b", re.I)),
    ("plays_vital_role", re.compile(r"\bplays? a vital role\b", re.I)),
    ("cornerstone", re.compile(r"\ba cornerstone of\b", re.I)),
    ("needless_to_say", re.compile(r"\bneedless to say\b", re.I)),
    ("at_the_end_of_day", re.compile(r"\bat the end of the day\b", re.I)),
    ("smash_subscribe", re.compile(r"\bsmash that (?:like|subscribe) button\b", re.I)),
]


def human_voice_contract() -> str:
    return (
        "HUMAN VOICE (mandatory): Write like a real YouTube creator speaking to a friend — "
        "specific, uneven, concrete. Ban AI tells: delve, furthermore, moreover, tapestry, "
        "digital landscape, unlock potential, game-changer, seamlessly, comprehensive guide, "
        "in conclusion, it is important to note. No symmetrical three-part slogans. "
        "Vary sentence length. Prefer plain verbs (shows, costs, breaks, lasts). "
        "Title: curiosity + exact product/topic, not generic hype. "
        "Description: 2–4 short paragraphs + real hashtags; not an essay. "
        "Narration: spoken documentary beats a human would actually say on camera."
    )


def find_ai_tells(text: str) -> List[str]:
    hits: List[str] = []
    raw = text or ""
    for code, pat in AI_TELL_PATTERNS:
        if pat.search(raw):
            hits.append(code)
    return hits


def _repeated_trigrams(text: str) -> int:
    words = re.findall(r"[A-Za-z0-9']+", (text or "").lower())
    if len(words) < 9:
        return 0
    grams = [" ".join(words[i : i + 3]) for i in range(len(words) - 2)]
    seen = {}
    for g in grams:
        seen[g] = seen.get(g, 0) + 1
    return sum(1 for c in seen.values() if c >= 2)


def score_human_text(text: str, *, field: str = "body") -> Dict[str, Any]:
    """
    Deterministic 0–100 human-likeness score (higher = more human).
    """
    t = (text or "").strip()
    if not t:
        return {"score": 0, "issues": ["empty"], "ai_tells": []}
    issues: List[str] = []
    score = 100
    tells = find_ai_tells(t)
    if tells:
        score -= min(40, 8 * len(tells))
        issues.append("ai_tells:" + ",".join(tells[:6]))
    reps = _repeated_trigrams(t)
    if reps:
        score -= min(20, 5 * reps)
        issues.append(f"repeated_phrases:{reps}")
    # Too-perfect parallel lists ("X, Y, and Z" spam)
    if len(re.findall(r"\b\w+, \w+, and \w+\b", t)) >= 2:
        score -= 10
        issues.append("parallel_list_spam")
    # Excess exclamation / emoji for title
    if field == "title":
        if t.count("!") > 1:
            score -= 8
            issues.append("title_exclaim")
        if len(t) > 90:
            score -= 6
            issues.append("title_too_long")
        if re.search(r"^(the ultimate|best|top \d+|complete guide)\b", t, re.I):
            score -= 12
            issues.append("generic_title_opener")
    if field == "description":
        if len(t) < 40:
            score -= 15
            issues.append("description_thin")
        # Wall of hashtags only
        hash_ratio = t.count("#") / max(1, len(t.split()))
        if hash_ratio > 0.35:
            score -= 10
            issues.append("hashtag_spam")
    if field == "narration":
        words = t.split()
        if len(words) > 28:
            score -= 8
            issues.append("narration_too_long_for_beat")
        if re.search(r"\bas an ai\b|\bi cannot\b|\bi'm unable\b", t, re.I):
            score -= 30
            issues.append("meta_ai_voice")
    score = max(0, min(100, score))
    return {"score": score, "issues": issues, "ai_tells": tells}


def audit_plan_human_voice(plan: Dict[str, Any]) -> Dict[str, Any]:
    fields: Dict[str, Dict[str, Any]] = {}
    fields["title"] = score_human_text(str(plan.get("title") or ""), field="title")
    fields["description"] = score_human_text(str(plan.get("description") or ""), field="description")
    fields["topic"] = score_human_text(str(plan.get("topic") or ""), field="title")
    scene_scores = []
    for i, sc in enumerate(plan.get("scenes") or []):
        if not isinstance(sc, dict):
            continue
        s = score_human_text(str(sc.get("narration") or ""), field="narration")
        s["scene_index"] = i
        scene_scores.append(s)
        if s["score"] < 70 or s["issues"]:
            fields[f"narration_{i}"] = s
    scores = [fields["title"]["score"], fields["description"]["score"]] + [
        s["score"] for s in scene_scores
    ]
    avg = sum(scores) / max(1, len(scores))
    all_issues = []
    for k, v in fields.items():
        for iss in v.get("issues") or []:
            all_issues.append(f"{k}:{iss}")
    passed = avg >= 72 and fields["title"]["score"] >= 65 and fields["description"]["score"] >= 60
    return {
        "ok": passed,
        "avg_score": round(avg, 1),
        "fields": fields,
        "scene_scores": scene_scores,
        "issues": all_issues[:40],
        "needs_rewrite": not passed,
    }


def _local_humanize_text(text: str, *, field: str) -> str:
    """Deterministic cleanup without LLM — strips common AI tells."""
    out = text or ""
    replacements = [
        (r"\bdelve(?:s|d|ing)? into\b", "look at"),
        (r"\bdelve(?:s|d|ing)?\b", "look"),
        (r"\bin today's (?:fast[- ]paced )?digital landscape\b", "right now"),
        (r"\bmoreover,?\b", "and"),
        (r"\bfurthermore,?\b", "also"),
        (r"\bin conclusion,?\b", "so"),
        (r"\bit is important to note that\b", ""),
        (r"\bunlock(?:ing)? (?:your|the) potential\b", "get more out of it"),
        (r"\bgame[- ]changer\b", "big upgrade"),
        (r"\bseamlessly\b", "smoothly"),
        (r"\blet'?s dive (?:in|into)\b", "here's"),
        (r"\bever wondered\b", "curious"),
        (r"\bin this (?:video|article) we will\b", "we cover"),
        (r"\bcomprehensive guide\b", "plain guide"),
        (r"\btapestry of\b", "mix of"),
        (r"\bbeacon of\b", "sign of"),
        (r"\bnestled\b", "sitting"),
        (r"\bembark(?:s|ed|ing)? on\b", "start"),
        (r"\bleverage\b", "use"),
        (r"\brevolutionize\b", "change"),
        (r"\bas an ai[, ]+\w+", ""),
        (r"\bwelcome back(?: to (?:the|our) channel)?\b", "look closely at"),
        (r"\bhello everyone\b", "look at this"),
        (r"\bhey guys\b", "look at this"),
        (r"\bwithout further ado,?\b", ""),
        (r"\blet'?s get started\b", "here is the evidence"),
        (r"\ba testament to\b", "proof of"),
        (r"\ba plethora of\b", "many"),
        (r"\ba myriad of\b", "countless"),
        (r"\bplays? a vital role\b", "matters"),
        (r"\ba cornerstone of\b", "the foundation of"),
        (r"\bneedless to say,?\b", ""),
        (r"\bat the end of the day,?\b", "ultimately"),
        (r"\bsmash that (?:like|subscribe) button\b", ""),
    ]
    for pat, rep in replacements:
        out = re.sub(pat, rep, out, flags=re.I)
    out = re.sub(r"\s{2,}", " ", out).strip()
    if field == "title":
        out = out.rstrip("!").strip()
        if len(out) > 95:
            out = out[:92].rsplit(" ", 1)[0] + "…"
    return out


def humanize_rewrite_instruction(*, field: str, text: str, topic: str = "") -> str:
    from pipeline.prompt_engineering import human_voice_contract as hvc

    return f"""Rewrite this YouTube {field} so it sounds 100% human-written (not ChatGPT).
Topic/product lock (keep exact names/numbers): {topic or "(keep product names)"}
{hvc()}

Original {field}:
\"\"\"{text}\"\"\"

Rules:
- Keep facts and product/SKU names exact.
- Remove AI tells and corporate filler.
- Output ONLY the rewritten {field}, no quotes or labels.
""".strip()


def humanize_plan(
    plan: Dict[str, Any],
    *,
    google_api_keys: Optional[Sequence[str]] = None,
    openrouter_keys: Optional[Sequence[str]] = None,
    work_dir: Optional[Path] = None,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """
    Cross-check + rewrite title/description/narrations for human voice.
    Returns {"plan": ..., "audit_before": ..., "audit_after": ..., "rewrites": [...]}
    """
    before = audit_plan_human_voice(plan)
    rewrites: List[Dict[str, Any]] = []
    out = dict(plan)
    topic = str(out.get("topic") or "")

    def _maybe_llm(field: str, text: str) -> str:
        cleaned = _local_humanize_text(text, field=field)
        if not use_llm:
            return cleaned
        try:
            from pipeline.llm_router import chat_text

            prompt = humanize_rewrite_instruction(field=field, text=cleaned, topic=topic)
            res = chat_text(
                prompt,
                purpose="script",
                google_api_keys=list(google_api_keys or []),
                openrouter_keys=list(openrouter_keys or []),
            )
            text_out = str((res or {}).get("text") or "").strip()
            text_out = re.sub(r'^["\']|["\']$', "", text_out)
            if len(text_out) >= 8:
                return _local_humanize_text(text_out, field=field)
        except Exception as exc:
            logger.debug("humanize LLM skip (%s): %s", field, exc)
        return cleaned

    # Always strip deterministic tells; LLM rewrite when audit fails or tells present
    for field in ("title", "description"):
        original = str(out.get(field) or "")
        sc = score_human_text(original, field=field)
        if sc["score"] < 78 or sc["ai_tells"] or sc["issues"]:
            new = _maybe_llm(field, original)
            if new and new != original:
                out[field] = new
                rewrites.append({"field": field, "before": original, "after": new, "score_before": sc["score"]})

    scenes = list(out.get("scenes") or [])
    new_scenes = []
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            new_scenes.append(sc)
            continue
        sc2 = dict(sc)
        narr = str(sc2.get("narration") or "")
        sc_score = score_human_text(narr, field="narration")
        if sc_score["score"] < 78 or sc_score["ai_tells"]:
            new_n = _maybe_llm("narration", narr)
            if new_n and new_n != narr:
                sc2["narration"] = new_n
                rewrites.append(
                    {
                        "field": f"narration_{i}",
                        "before": narr,
                        "after": new_n,
                        "score_before": sc_score["score"],
                    }
                )
        new_scenes.append(sc2)
    out["scenes"] = new_scenes

    # Second pass audit (cross-check)
    after = audit_plan_human_voice(out)
    # If still weak, force local cleanup again on title/desc
    if not after.get("ok"):
        out["title"] = _local_humanize_text(str(out.get("title") or ""), field="title")
        out["description"] = _local_humanize_text(str(out.get("description") or ""), field="description")
        after = audit_plan_human_voice(out)

    report = {
        "audit_before": before,
        "audit_after": after,
        "rewrites": rewrites,
        "passed": bool(after.get("ok")),
    }
    if work_dir:
        try:
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / "content_human_audit.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("human audit write skip: %s", exc)
    return {"plan": out, **report}
