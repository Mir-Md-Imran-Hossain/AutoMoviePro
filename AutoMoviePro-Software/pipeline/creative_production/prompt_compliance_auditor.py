"""Industrial Prompt Compliance Auditor.

Proves that topic/script LLM outputs actually honor the industrial prompt contracts
(retention, SEO/CTR, hook, information density) — not just that prompts were sent.

Layers:
  1) Deterministic contract scoring (authoritative, fail-closed)
  2) Optional LLM critic (purpose=critic) as corroborating judge
  3) One repair pass → re-audit
  4) Proof artifact: PROMPT_COMPLIANCE_AUDIT.json

Env:
  AMP_PROMPT_COMPLIANCE=0     → disable auditor (not recommended)
  AMP_PROMPT_COMPLIANCE_LLM=0 → skip LLM judge (deterministic only)
  AMP_PROMPT_COMPLIANCE_LLM=1 → force LLM judge attempt (default when keys exist)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

PROMPT_CONTRACT_VERSION = "industrial_prompt_contract_v1"
AUDITOR_VERSION = "prompt_compliance_auditor_v1"

CLAUSE_HOOK = "C01_opening_pattern_interrupt"
CLAUSE_RETENTION = "C02_mid_retention_rehooks"
CLAUSE_INFO = "C03_information_density"
CLAUSE_SEO = "C04_seo_ctr_package"
CLAUSE_TOPIC = "C05_topic_specificity"
CLAUSE_ENDING = "C06_ending_loop_close"
CLAUSE_NO_FLAT = "C07_no_encyclopedia_flatness"
CLAUSE_LLM_JUDGE = "C08_llm_industrial_judge"


class PromptComplianceError(RuntimeError):
    """Fail-closed: plan does not match industrial prompt engineering contracts."""

    def __init__(self, message: str, *, audit: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.audit = audit or {}


def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip() not in ("0", "false", "False", "no", "off")


def _plan_fingerprint(plan: Dict[str, Any]) -> str:
    scenes = plan.get("scenes") or plan.get("beats") or []
    payload = {
        "topic": plan.get("topic"),
        "title": plan.get("title"),
        "tags": plan.get("tags"),
        "narrations": [
            str(s.get("narration") or s.get("text") or s.get("dialogue") or "")
            for s in scenes
            if isinstance(s, dict)
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _narrations(plan: Dict[str, Any]) -> List[str]:
    rows = plan.get("scenes") or plan.get("beats") or []
    out: List[str] = []
    for s in rows:
        if not isinstance(s, dict):
            continue
        t = str(s.get("narration") or s.get("text") or s.get("dialogue") or "").strip()
        if t:
            out.append(t)
    return out


def _score_clause(pass_: bool, *, weight: float = 1.0, partial: float = 0.0) -> float:
    if pass_:
        return float(weight)
    return max(0.0, float(partial) * float(weight))


def score_deterministic_compliance(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Authoritative industrial contract scorecard."""
    from pipeline.creative_production.retention import (
        validate_retention_structure,
        validate_title_video_consistency,
    )
    from pipeline.creative_production.script_quality import (
        classify_hook,
        score_opening_attention,
        validate_script_plan_preflight,
    )

    plan = dict(plan or {})
    topic = str(plan.get("topic") or "").strip()
    title = str(plan.get("title") or "").strip()
    description = str(plan.get("description") or "").strip()
    tags = plan.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    narrations = _narrations(plan)
    violations: List[Dict[str, Any]] = []
    clauses: Dict[str, Dict[str, Any]] = {}

    # C01 Opening hook
    opening = narrations[0] if narrations else str(plan.get("hook") or "")
    hook = classify_hook(opening, topic=topic)
    attn = score_opening_attention(opening, topic=topic)
    hook_ok = hook.get("status") != "BLOCK" and attn.get("status") != "BLOCK"
    if not hook_ok:
        violations.append(
            {
                "clause": CLAUSE_HOOK,
                "severity": "critical",
                "evidence": opening[:180],
                "issues": list(hook.get("issues") or []) + list(attn.get("issues") or []),
            }
        )
    clauses[CLAUSE_HOOK] = {
        "pass": hook_ok,
        "score": _score_clause(hook_ok, weight=1.0, partial=0.25),
        "detail": {"hook": hook, "opening": attn},
    }

    # C02 Retention structure
    ret = validate_retention_structure(plan)
    ret_ok = ret.get("status") != "BLOCK"
    if not ret_ok:
        violations.append(
            {
                "clause": CLAUSE_RETENTION,
                "severity": "critical",
                "evidence": f"hook_signals={ret.get('hook_signals')} issues={ret.get('issues')}",
                "issues": list(ret.get("issues") or []),
            }
        )
    elif ret.get("warnings"):
        violations.append(
            {
                "clause": CLAUSE_RETENTION,
                "severity": "warning",
                "evidence": ",".join(ret.get("warnings") or [])[:200],
                "issues": list(ret.get("warnings") or []),
            }
        )
    clauses[CLAUSE_RETENTION] = {
        "pass": ret_ok,
        "score": _score_clause(ret_ok, weight=1.0, partial=0.35),
        "detail": {
            "hook_signals": ret.get("hook_signals"),
            "payoff_signals": ret.get("payoff_signals"),
            "warnings": ret.get("warnings") or [],
        },
    }

    # C03 Information density / preflight
    pre = validate_script_plan_preflight(plan, require_evidence=False)
    info_ok = not pre.get("blocked")
    if not info_ok:
        violations.append(
            {
                "clause": CLAUSE_INFO,
                "severity": "critical",
                "evidence": ",".join(pre.get("blocks") or pre.get("issues") or [])[:220],
                "issues": list(pre.get("blocks") or pre.get("issues") or []),
            }
        )
    clauses[CLAUSE_INFO] = {
        "pass": info_ok,
        "score": _score_clause(info_ok, weight=1.0, partial=0.2),
        "detail": {"blocked": pre.get("blocked"), "warnings": pre.get("warnings") or []},
    }

    # C04 SEO / CTR package
    tv = validate_title_video_consistency(title=title, topic=topic, narrations=narrations)
    seo_issues = list(tv.get("issues") or [])
    title_kw = set(re.findall(r"[a-z0-9]{4,}", title.lower()))
    topic_kw = set(re.findall(r"[a-z0-9]{4,}", topic.lower()))
    if title and topic_kw and title_kw and len(title_kw & topic_kw) == 0:
        seo_issues.append("title_topic_token_mismatch")
    if not title or len(title_kw) < 3:
        seo_issues.append("title_missing_or_thin")
    if not description or len(description.split()) < 12:
        seo_issues.append("description_too_thin_for_seo")
    if len([t for t in tags if str(t).strip()]) < 5:
        seo_issues.append("tags_below_industrial_minimum")
    # Soft: hashtags in description preferred
    if description and "#" not in description:
        seo_issues.append("description_missing_hashtags")
    critical_seo = {
        "clickbait_title",
        "title_not_grounded_in_video",
        "unsupported_title_claim",
        "title_missing_or_thin",
        "vague_non_seo_title",
    }
    seo_critical = [i for i in seo_issues if i in critical_seo]
    seo_ok = not seo_critical
    if seo_critical:
        violations.append(
            {
                "clause": CLAUSE_SEO,
                "severity": "critical",
                "evidence": title[:120],
                "issues": seo_critical,
            }
        )
    elif seo_issues:
        violations.append(
            {
                "clause": CLAUSE_SEO,
                "severity": "warning",
                "evidence": title[:120],
                "issues": seo_issues,
            }
        )
    seo_score = 1.0 if seo_ok and not seo_issues else (0.7 if seo_ok else 0.2)
    clauses[CLAUSE_SEO] = {
        "pass": seo_ok,
        "score": seo_score,
        "detail": {"issues": seo_issues, "tag_count": len(tags)},
    }

    # C05 Topic specificity
    topic_ok = bool(topic) and len(topic.split()) >= 3 and not re.fullmatch(
        r"(best|top|amazing)\s+\w+(\s+facts?)?", topic.strip(), re.I
    )
    if not topic_ok:
        violations.append(
            {
                "clause": CLAUSE_TOPIC,
                "severity": "critical",
                "evidence": topic[:160],
                "issues": ["topic_too_vague_or_missing"],
            }
        )
    clauses[CLAUSE_TOPIC] = {
        "pass": topic_ok,
        "score": _score_clause(topic_ok, weight=1.0, partial=0.2),
        "detail": {"topic": topic},
    }

    # C06 Ending close
    ending_ok = True
    if len(narrations) >= 3:
        last = narrations[-1].lower()
        ending_ok = bool(
            re.search(
                r"\b(so|because|means|takeaway|proves|remember|leaves|answer|watch for)\b",
                last,
            )
        )
        if not ending_ok:
            violations.append(
                {
                    "clause": CLAUSE_ENDING,
                    "severity": "warning",
                    "evidence": narrations[-1][:160],
                    "issues": ["ending_missing_loop_close_language"],
                }
            )
    clauses[CLAUSE_ENDING] = {
        "pass": ending_ok,
        "score": _score_clause(ending_ok, weight=0.8, partial=0.4),
        "detail": {},
    }

    # C07 Flat encyclopedia streak (from retention warnings/issues already)
    flat_issues = [
        i
        for i in (ret.get("issues") or []) + (ret.get("warnings") or [])
        if str(i).startswith("flat_description") or str(i).startswith("insufficient_rehook")
    ]
    flat_ok = not any(str(i).startswith("flat_description") for i in (ret.get("issues") or []))
    if not flat_ok:
        violations.append(
            {
                "clause": CLAUSE_NO_FLAT,
                "severity": "critical",
                "evidence": ",".join(flat_issues)[:200],
                "issues": flat_issues,
            }
        )
    clauses[CLAUSE_NO_FLAT] = {
        "pass": flat_ok,
        "score": _score_clause(flat_ok, weight=1.0, partial=0.3),
        "detail": {"flat_related": flat_issues},
    }

    scores = {k: float(v.get("score") or 0.0) for k, v in clauses.items()}
    weights = {
        CLAUSE_HOOK: 1.2,
        CLAUSE_RETENTION: 1.3,
        CLAUSE_INFO: 1.0,
        CLAUSE_SEO: 1.0,
        CLAUSE_TOPIC: 0.9,
        CLAUSE_ENDING: 0.7,
        CLAUSE_NO_FLAT: 1.1,
    }
    wsum = sum(weights.get(k, 1.0) for k in scores)
    overall = sum(scores[k] * weights.get(k, 1.0) for k in scores) / max(1e-9, wsum)
    critical = [v for v in violations if v.get("severity") == "critical"]
    if critical:
        verdict = "BLOCK"
    elif overall >= 0.82:
        verdict = "PASS"
    elif overall >= 0.62:
        verdict = "REPAIR_REQUIRED"
    else:
        verdict = "BLOCK"

    return {
        "verdict": verdict,
        "overall_score": round(overall, 4),
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "clauses": clauses,
        "violations": violations,
        "method": "DETERMINISTIC",
        "contract_version": PROMPT_CONTRACT_VERSION,
    }


def prompt_compliance_critic_instruction(*, plan: Dict[str, Any], contract_summary: str) -> str:
    narrations = _narrations(plan)
    beats = "\n".join(f"{i+1}. {n}" for i, n in enumerate(narrations[:14]))
    return f"""You are AutoMovie Pro INDUSTRIAL PROMPT COMPLIANCE JUDGE (not a cheerleader).
Your job: prove whether this script OUTPUT obeys the industrial prompt engineering contract.
Be harsh and evidence-based. If flat/encyclopedia, FAIL.

CONTRACT TO ENFORCE:
{contract_summary}

OUTPUT UNDER AUDIT:
topic: {plan.get('topic')}
title: {plan.get('title')}
description: {(plan.get('description') or '')[:400]}
tags: {plan.get('tags')}
spoken beats:
{beats}

Return STRICT JSON only:
{{
  "verdict": "PASS|BLOCK|REPAIR_REQUIRED",
  "overall_score": 0.0,
  "clause_results": [
    {{"clause_id": "C01_opening_pattern_interrupt", "pass": true, "evidence": "quote", "note": ""}}
  ],
  "must_fix": ["..."],
  "industrial_grade": true,
  "reason": "one sentence"
}}
Fail if: weak/missing hook, no mid re-hooks, vague SEO title, flat description chains, or ending without payoff.
""".strip()


def run_llm_compliance_judge(
    plan: Dict[str, Any],
    *,
    google_api_keys: Optional[Sequence[str]] = None,
    openrouter_keys: Optional[Sequence[str]] = None,
    huggingface_keys: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Secondary LLM judge (purpose=critic). Never overrides deterministic BLOCK alone to PASS."""
    from pipeline.prompt_engineering import (
        industrial_retention_rules,
        industrial_seo_rules,
        industrial_topic_selection_rules,
        system_for_purpose,
    )

    contract_summary = "\n\n".join(
        [
            industrial_retention_rules(
                max_seconds=int(plan.get("max_seconds") or 60),
                video_type=str(plan.get("video_type") or "short"),
            ),
            industrial_seo_rules(video_type=str(plan.get("video_type") or "short")),
            industrial_topic_selection_rules(),
        ]
    )
    instruction = prompt_compliance_critic_instruction(plan=plan, contract_summary=contract_summary)
    try:
        from pipeline.llm_router import chat_text, extract_json_object

        hit = chat_text(
            instruction,
            purpose="critic",
            system=system_for_purpose("critic", json_mode=True)
            + " You are auditing SCRIPT prompt-compliance for retention and SEO. JSON only.",
            google_api_keys=list(google_api_keys or []),
            openrouter_keys=list(openrouter_keys or []),
            huggingface_keys=list(huggingface_keys or []),
            json_mode=True,
        )
        data = json.loads(extract_json_object(hit.get("text") or ""))
        data["provider"] = hit.get("provider")
        data["method"] = "LLM_CRITIC"
        data["clause"] = CLAUSE_LLM_JUDGE
        return data
    except Exception as exc:
        return {
            "verdict": "UNKNOWN",
            "overall_score": None,
            "method": "LLM_CRITIC",
            "clause": CLAUSE_LLM_JUDGE,
            "error": str(exc)[:240],
            "industrial_grade": False,
        }


def repair_plan_for_compliance(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic industrial repairs before re-audit."""
    from pipeline.creative_production.script_quality import (
        enforce_dialogue_window_on_plan,
        enforce_opening_hook_on_plan,
        enforce_retention_cadence_on_plan,
    )
    from pipeline.retention_architecture import attach_retention_to_plan

    out = dict(plan or {})
    out = enforce_opening_hook_on_plan(out)
    out = enforce_retention_cadence_on_plan(out)
    out = enforce_dialogue_window_on_plan(out)
    out = attach_retention_to_plan(out)
    topic = str(out.get("topic") or "").strip()
    title = str(out.get("title") or "").strip()
    title_kw = set(re.findall(r"[a-z0-9]{4,}", title.lower()))
    if (not title or len(title_kw) < 3) and topic:
        out["title"] = f"{topic} — what most explainers miss"
    desc = str(out.get("description") or "").strip()
    if (not desc or len(desc.split()) < 12) and topic:
        out["description"] = (
            f"Learn why {topic} matters, the evidence most viewers miss, and the payoff that keeps you watching. "
            f"#{''.join(w.capitalize() for w in topic.split()[:3]) or 'Documentary'} #YouTubeSEO #Evidence"
        )
    tags = out.get("tags") if isinstance(out.get("tags"), list) else []
    if len(tags) < 5 and topic:
        base = [w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", topic)][:6]
        out["tags"] = list(
            dict.fromkeys(base + ["documentary", "explained", "evidence", "2026", "retention"])
        )[:12]
    return out


def persist_compliance_audit(work_dir: Optional[Path], audit: Dict[str, Any]) -> Optional[Path]:
    if work_dir is None:
        return None
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    path = work / "PROMPT_COMPLIANCE_AUDIT.json"
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    # Also keep a latest stamp under _meta if curated later
    return path


def audit_script_prompt_compliance(
    plan: Dict[str, Any],
    *,
    work_dir: Optional[Path] = None,
    job_id: str = "",
    enable_llm_critic: Optional[bool] = None,
    repair: bool = True,
    fail_closed: bool = True,
    google_api_keys: Optional[Sequence[str]] = None,
    openrouter_keys: Optional[Sequence[str]] = None,
    huggingface_keys: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Full industrial compliance audit with optional repair + proof artifact.

    Returns audit dict. When fail_closed and final verdict is BLOCK, raises PromptComplianceError.
    """
    if not _env_flag("AMP_PROMPT_COMPLIANCE", "1"):
        return {
            "verdict": "SKIPPED",
            "reason": "AMP_PROMPT_COMPLIANCE=0",
            "plan": plan,
            "auditor_version": AUDITOR_VERSION,
        }

    working = dict(plan or {})
    repairs_applied: List[str] = []
    det = score_deterministic_compliance(working)

    if det.get("verdict") in ("REPAIR_REQUIRED", "BLOCK") and repair:
        working = repair_plan_for_compliance(working)
        repairs_applied.append("deterministic_industrial_repair_v1")
        det_after = score_deterministic_compliance(working)
        det_after["pre_repair"] = {
            "verdict": det.get("verdict"),
            "overall_score": det.get("overall_score"),
            "violations": det.get("violations"),
        }
        det = det_after

    llm: Dict[str, Any] = {"verdict": "SKIPPED", "method": "LLM_CRITIC"}
    use_llm = enable_llm_critic
    if use_llm is None:
        # Default: attempt LLM judge unless explicitly disabled
        use_llm = _env_flag("AMP_PROMPT_COMPLIANCE_LLM", "1")
    if use_llm:
        llm = run_llm_compliance_judge(
            working,
            google_api_keys=google_api_keys,
            openrouter_keys=openrouter_keys,
            huggingface_keys=huggingface_keys,
        )

    # Merge verdict: deterministic is AUTHORITATIVE for ship/block.
    # LLM is corroboration — may trigger one repair pass, but cannot alone BLOCK
    # a plan that already passes deterministic industrial clauses (false BLOCK from
    # flaky/rate-limited critics was killing live marathon).
    final_verdict = str(det.get("verdict") or "BLOCK")
    llm_verdict = str(llm.get("verdict") or "UNKNOWN").upper()
    if final_verdict == "PASS" and llm_verdict in ("BLOCK", "REPAIR_REQUIRED"):
        if repair:
            working = repair_plan_for_compliance(working)
            repairs_applied.append("post_llm_deterministic_repair")
            det = score_deterministic_compliance(working)
            final_verdict = str(det.get("verdict") or "PASS")
        if final_verdict == "PASS":
            # Keep PASS; LLM disagreement recorded on audit for operators
            llm["escalation_ignored"] = True
            llm["escalation_note"] = (
                "deterministic_pass_authoritative; llm_block_does_not_fail_closed"
            )

    industrial_ok = final_verdict == "PASS"
    audit: Dict[str, Any] = {
        "auditor_version": AUDITOR_VERSION,
        "contract_version": PROMPT_CONTRACT_VERSION,
        "job_id": job_id or (Path(work_dir).name if work_dir else ""),
        "organized_at": datetime.now(timezone.utc).isoformat(),
        "plan_fingerprint": _plan_fingerprint(working),
        "verdict": final_verdict,
        "industrial_grade": industrial_ok,
        "overall_score": det.get("overall_score"),
        "deterministic": det,
        "llm_critic": llm,
        "repairs_applied": repairs_applied,
        "decision_reason": (
            "Output matches industrial prompt contracts (retention + SEO + hook)."
            if industrial_ok
            else "Output failed industrial prompt-compliance proof — quality would degrade if shipped."
        ),
        "proof": {
            "what_we_checked": [
                "opening pattern interrupt / curiosity gap",
                "mid-script re-hooks and information density",
                "SEO/CTR title-description-tags honesty",
                "topic specificity",
                "ending loop close",
                "optional LLM industrial judge",
            ],
            "authoritative_layer": "deterministic",
            "corroboration_layer": "llm_critic" if llm.get("verdict") not in (None, "SKIPPED") else "none",
        },
    }
    path = persist_compliance_audit(work_dir, audit)
    if path:
        audit["artifact_path"] = str(path)
        # Persist repaired plan beside audit when repaired
        if repairs_applied and work_dir is not None:
            try:
                rp = Path(work_dir) / "PROMPT_COMPLIANCE_REPAIR.json"
                rp.write_text(
                    json.dumps(
                        {"repairs_applied": repairs_applied, "plan": working},
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                    encoding="utf-8",
                )
                audit["repair_artifact_path"] = str(rp)
            except Exception:
                pass

    audit["plan"] = working

    if fail_closed and final_verdict == "BLOCK":
        raise PromptComplianceError(
            "prompt_compliance_blocked:"
            + ",".join(
                str(v.get("clause"))
                for v in (det.get("violations") or [])
                if v.get("severity") == "critical"
            )
            or "industrial_contract_fail",
            audit=audit,
        )
    return audit
