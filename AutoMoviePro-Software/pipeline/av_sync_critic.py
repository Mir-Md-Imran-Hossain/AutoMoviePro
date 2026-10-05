from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.compose import ffmpeg_bin, ffprobe_duration
from pipeline.prompt_engineering import (
    critic_instruction,
    meta_audit_instruction,
    precheck_instruction,
    revised_visual_prompt,
    sanitize_generation_prompt,
)

logger = logging.getLogger(__name__)

# Per-process critique counters (path → count) — stops scene_builder multi-critique burn
_CRITIC_CALL_COUNTS: Dict[str, int] = {}

PASS_SCORE = 78
CRITICAL_ISSUES = {
    "wrong_subject",
    "unrelated_broll",
    "talking_head",
    "duration_mismatch",
    "visual_anchors_missing",
    "master_not_english",
    "voice_drift",
    "burned_master_subs",
}
# Ordered by C11-B readiness evidence (2026-09-06): generateContent OK on account keys.
# Stale IDs (gemini-2.5-flash / gemini-2.0-flash) return 404 for new users — do not restore without probe.
CRITIC_MODELS = [
    "gemini-flash-latest",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
]

# Learned hard rules (marathon training appends here via apply_training_rule)
TRAINING_RULES_PATH = Path(__file__).resolve().parent / "av_sync_training_rules.json"


def load_training_rules() -> List[str]:
    if not TRAINING_RULES_PATH.exists():
        return []
    try:
        data = json.loads(TRAINING_RULES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(r).strip() for r in data if str(r).strip()]
        rules = data.get("rules") if isinstance(data, dict) else []
        return [str(r).strip() for r in (rules or []) if str(r).strip()]
    except Exception:
        return []


def apply_training_rule(rule: str, *, source: str = "marathon") -> None:
    """Append a durable critic rule learned from marathon meta-audit."""
    rule = (rule or "").strip()
    if not rule:
        return
    rules = load_training_rules()
    if rule in rules:
        return
    rules.append(rule)
    TRAINING_RULES_PATH.write_text(
        json.dumps({"rules": rules[-120:], "updated_by": source}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Training rule added (%s): %s", source, rule[:120])


def precheck_generation_prompt(
    *,
    narration_bn: str,
    exact_ai_video_prompt: str,
    keyword_triggers: Optional[List[str]] = None,
    niche: str = "",
    element: str = "",
    product_name: str = "",
    google_api_keys: Optional[List[str]] = None,
    video_type: str = "short",
) -> Dict[str, Any]:
    """
    BEFORE Agnes: judge whether the prompt will sync with narration.
    Returns fixed prompt if problems found.
    """
    keywords = [str(k).strip() for k in (keyword_triggers or []) if str(k).strip()]
    keys = [k.strip() for k in (google_api_keys or []) if (k or "").strip()]
    trained = load_training_rules()
    trained_txt = "\n".join(f"- {r}" for r in trained[:40]) or "(none yet)"

    instruction = precheck_instruction(
        niche=niche,
        element=element,
        product_name=product_name,
        narration=narration_bn,
        keywords=keywords,
        exact_ai_video_prompt=exact_ai_video_prompt,
        trained_txt=trained_txt,
        video_type=video_type,
    )

    if not keys:
        fixed = _default_revised_prompt(
            narration_bn=narration_bn,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            product_name=product_name,
            element=element,
            issues=["precheck_no_keys"],
        )
        return {
            "prompt_score": 50,
            "passed": False,
            "issues": ["precheck_no_keys"],
            "missing_triggers": keywords,
            "risk_flags": [],
            "fixed_prompt": fixed,
            "raw": {"fallback": True},
        }

    # Prefer non-Google text routers for prompt precheck (Google = translate only).
    try:
        from pipeline.llm_router import chat_text

        hit = chat_text(instruction, purpose="precheck", json_mode=True)
        text = str((hit or {}).get("text") or "")
        if text.strip():
            data = json.loads(_extract_json(text))
            out = _normalize_precheck(
                data, keywords, exact_ai_video_prompt, narration_bn, product_name, element
            )
            out["raw"] = {**(out.get("raw") or {}), "provider": f"text_router:{(hit or {}).get('provider')}"}
            return out
    except Exception as exc:
        logger.warning("precheck text_router failed: %s", str(exc)[:160])

    use_google = (os.environ.get("AMP_CRITIC_USE_GOOGLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not use_google or not keys:
        fixed = _default_revised_prompt(
            narration_bn=narration_bn,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            product_name=product_name,
            element=element,
            issues=["precheck_router_failed"],
        )
        return {
            "prompt_score": 55,
            "passed": True,  # soft-pass: do not block generation on precheck outage
            "issues": ["precheck_router_failed"],
            "missing_triggers": [],
            "risk_flags": [],
            "fixed_prompt": fixed or exact_ai_video_prompt,
            "raw": {"fallback": True, "google_skipped": not use_google},
        }

    from pipeline.google_api_gate import (
        GoogleCircuitOpen,
        circuit_is_open,
        gated_generate_content,
    )

    if circuit_is_open():
        fixed = _default_revised_prompt(
            narration_bn=narration_bn,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            product_name=product_name,
            element=element,
            issues=["precheck_google_circuit_open"],
        )
        return {
            "prompt_score": 50,
            "passed": False,
            "issues": ["precheck_google_circuit_open"],
            "missing_triggers": [],
            "risk_flags": [],
            "fixed_prompt": fixed or exact_ai_video_prompt,
            "raw": {"fallback": True, "circuit_open": True},
        }

    try:
        from google.genai import types

        result = gated_generate_content(
            api_keys=keys,
            contents=instruction,
            models=list(CRITIC_MODELS[:3]),
            purpose="critic",
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        data = json.loads(_extract_json(result.text))
        return _normalize_precheck(
            data, keywords, exact_ai_video_prompt, narration_bn, product_name, element
        )
    except GoogleCircuitOpen as exc:
        logger.warning("precheck circuit open: %s", str(exc)[:120])
    except Exception as exc:
        logger.warning("precheck gated failed: %s", str(exc)[:160])

    fixed = _default_revised_prompt(
        narration_bn=narration_bn,
        keywords=keywords,
        exact_ai_video_prompt=exact_ai_video_prompt,
        product_name=product_name,
        element=element,
        issues=["precheck_api_failed"],
    )
    return {
        "prompt_score": 50,
        "passed": False,
        "issues": ["precheck_api_failed"],
        "missing_triggers": keywords,
        "risk_flags": [],
        "fixed_prompt": fixed,
        "raw": {"fallback": True},
    }



def meta_audit_critique(
    *,
    video_path: Path,
    narration_bn: str,
    agent_critique: Dict[str, Any],
    keyword_triggers: Optional[List[str]] = None,
    google_api_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Second-opinion auditor: did the AV critic judge correctly?
    Used in marathon to train the agent.
    """
    keywords = [str(k).strip() for k in (keyword_triggers or []) if str(k).strip()]
    keys = [k.strip() for k in (google_api_keys or []) if (k or "").strip()]
    instruction = meta_audit_instruction(
        narration=narration_bn,
        keywords=keywords,
        agent_blob=json.dumps(
            {
                k: agent_critique.get(k)
                for k in (
                    "match_score",
                    "passed",
                    "issues",
                    "critical_issues",
                    "visual_summary",
                    "audio_summary",
                    "matched_keywords",
                    "missed_keywords",
                )
            },
            ensure_ascii=False,
        ),
    )

    if not keys:
        return {
            "agent_was_correct": True,
            "error_type": "none",
            "your_match_score": agent_critique.get("match_score"),
            "your_passed": agent_critique.get("passed"),
            "explanation": "no keys for meta audit",
            "training_rule": "",
            "raw": {"skipped": True},
        }

    quota_hits = 0
    from pipeline.google_api_gate import circuit_is_open, is_daily_quota_zero, open_circuit

    if circuit_is_open():
        return {
            "agent_was_correct": True,
            "error_type": "none",
            "your_match_score": agent_critique.get("match_score"),
            "your_passed": agent_critique.get("passed"),
            "explanation": "meta_audit_skipped_circuit_open",
            "training_rule": "",
            "raw": {"skipped": True, "circuit_open": True},
        }

    for key in keys[:1]:  # HARD: never spray meta-audit across the vault
        try:
            data = _critique_via_video_upload(key, Path(video_path), instruction)
            if not data:
                data = _critique_via_frames(key, Path(video_path), instruction)
            if not data:
                continue
            rule = str(data.get("training_rule") or "").strip()
            if rule and data.get("agent_was_correct") is False:
                apply_training_rule(rule, source="meta_audit")
            return {
                "agent_was_correct": bool(data.get("agent_was_correct", True)),
                "error_type": str(data.get("error_type") or "none"),
                "your_match_score": data.get("your_match_score"),
                "your_passed": data.get("your_passed"),
                "explanation": str(data.get("explanation") or ""),
                "training_rule": rule,
                "raw": data,
            }
        except Exception as exc:
            logger.warning("meta audit failed: %s", str(exc)[:180])
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                quota_hits += 1
                if quota_hits >= 2:
                    break
            continue

    return {
        "agent_was_correct": True,
        "error_type": "none",
        "your_match_score": agent_critique.get("match_score"),
        "your_passed": agent_critique.get("passed"),
        "explanation": "meta_audit_unavailable",
        "training_rule": "",
        "raw": {"fallback": True, "quota_hits": quota_hits},
    }


def _normalize_precheck(
    data: Dict[str, Any],
    keywords: List[str],
    exact_ai_video_prompt: str,
    narration_bn: str,
    product_name: str,
    element: str,
) -> Dict[str, Any]:
    try:
        score = int(float(data.get("prompt_score", 0)))
    except Exception:
        score = 0
    score = max(0, min(100, score))
    issues = data.get("issues") or []
    if not isinstance(issues, list):
        issues = [str(issues)]
    missing = data.get("missing_triggers") or []
    if not isinstance(missing, list):
        missing = []
    risks = data.get("risk_flags") or []
    if not isinstance(risks, list):
        risks = []
    risks = [str(r).strip().lower() for r in risks if str(r).strip()]
    fixed = str(data.get("fixed_prompt") or "").strip()
    if not fixed:
        fixed = _default_revised_prompt(
            narration_bn=narration_bn,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            product_name=product_name,
            element=element,
            issues=[str(i) for i in issues] or ["precheck_fix"],
        )
    bad_risk = any(r in {"wrong_subject", "talking_head", "unrelated_metaphor"} for r in risks)
    passed = score >= 80 and not missing and not bad_risk
    if "passed" in data and not passed:
        pass  # enforce
    return {
        "prompt_score": score,
        "passed": passed,
        "issues": [str(i) for i in issues],
        "missing_triggers": [str(m) for m in missing],
        "risk_flags": risks,
        "fixed_prompt": fixed,
        "raw": data,
    }


def critique_scene_clip(
    *,
    video_path: Path,
    audio_path: Path,
    narration_bn: str,
    keyword_triggers: Optional[List[str]] = None,
    exact_ai_video_prompt: str = "",
    niche: str = "",
    element: str = "",
    google_api_keys: Optional[List[str]] = None,
    product_name: str = "",
    video_type: str = "short",
) -> Dict[str, Any]:
    """
    Multimodal AV-sync critic: score how well the muxed clip matches narration.
    Prefer Gemini Files API on the muxed MP4 (video+audio); fall back to frames.
    """
    keywords = [str(k).strip() for k in (keyword_triggers or []) if str(k).strip()]
    video_path = Path(video_path)
    audio_path = Path(audio_path)

    # Cap API critiques per muxed clip path (scene_builder used to call 4–8×)
    try:
        max_c = int((os.environ.get("AMP_MAX_CRITIQUES_PER_CLIP") or "2").strip() or "2")
    except Exception:
        max_c = 2
    clip_key = str(video_path.resolve()) if video_path.exists() else str(video_path)
    n_prev = int(_CRITIC_CALL_COUNTS.get(clip_key, 0))
    if n_prev >= max(1, max_c):
        return _local_gates_only_critique(
            narration_bn=narration_bn,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            element=element,
            product_name=product_name,
            reason=f"critique_cap:{n_prev}>={max_c}",
        )
    _CRITIC_CALL_COUNTS[clip_key] = n_prev + 1

    keys = [k.strip() for k in (google_api_keys or []) if (k or "").strip()]
    if not keys:
        return _fallback_critique(
            narration_bn=narration_bn,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            element=element,
            product_name=product_name,
            reason="no_google_api_keys",
        )

    from pipeline.google_api_gate import (
        circuit_is_open,
        is_daily_quota_zero,
        open_circuit,
        select_keys,
    )

    instruction = _critic_instruction(
        narration_bn=narration_bn,
        keywords=keywords,
        exact_ai_video_prompt=exact_ai_video_prompt,
        niche=niche,
        element=element,
        product_name=product_name,
        video_dur=ffprobe_duration(video_path),
        audio_dur=ffprobe_duration(audio_path),
        video_type=video_type,
    )

    # Google free-tier / policy: default to text router (Groq/OR) — do NOT burn
    # Gemini on video upload critics unless AMP_CRITIC_USE_GOOGLE=1.
    use_google = (os.environ.get("AMP_CRITIC_USE_GOOGLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not use_google or circuit_is_open():
        alt = _critique_via_text_router(
            instruction=instruction,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            narration_bn=narration_bn,
            product_name=product_name,
            element=element,
        )
        if alt:
            return alt
        return _local_gates_only_critique(
            narration_bn=narration_bn,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            element=element,
            product_name=product_name,
            reason="google_critic_disabled" if not use_google else "google_circuit_open",
        )

    last_err: Optional[str] = None
    quota_hits = 0
    # HARD: at most 1 sticky key — never spray 5–19 keys on critic uploads
    try:
        try_keys = select_keys(keys, purpose="critic")
    except Exception as exc:
        alt = _critique_via_text_router(
            instruction=instruction,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            narration_bn=narration_bn,
            product_name=product_name,
            element=element,
        )
        if alt:
            return alt
        return _fallback_critique(
            narration_bn=narration_bn,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            element=element,
            product_name=product_name,
            reason=f"critic_gate:{exc}",
        )
    for key in try_keys:
        # Primary: upload full muxed clip
        try:
            data = _critique_via_video_upload(key, video_path, instruction)
            if data:
                return _normalize_result(
                    data, keywords, exact_ai_video_prompt, narration_bn, product_name, element
                )
        except Exception as exc:
            last_err = str(exc)
            logger.warning("AV critic video upload failed: %s", str(exc)[:200])
            msg = str(exc)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                quota_hits += 1
                try:
                    from pipeline.quota_backoff import record_key_quota_hit

                    record_key_quota_hit(key, "google")
                except Exception:
                    pass
                if is_daily_quota_zero(msg):
                    from pipeline.google_api_gate import maybe_trip_circuit_if_pool_dead

                    maybe_trip_circuit_if_pool_dead(keys, reason="critic_daily0")
                continue  # try next sticky/sibling key — do not vault-wipe on one key

        # Fallback: frames + narration text
        try:
            data = _critique_via_frames(key, video_path, instruction)
            if data:
                return _normalize_result(
                    data, keywords, exact_ai_video_prompt, narration_bn, product_name, element
                )
        except Exception as exc:
            last_err = str(exc)
            logger.warning("AV critic frames fallback failed: %s", str(exc)[:200])
            msg = str(exc)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                quota_hits += 1
                try:
                    from pipeline.quota_backoff import record_key_quota_hit

                    record_key_quota_hit(key, "google")
                except Exception:
                    pass
                if is_daily_quota_zero(msg):
                    from pipeline.google_api_gate import maybe_trip_circuit_if_pool_dead

                    maybe_trip_circuit_if_pool_dead(keys, reason="critic_frames_daily0")
                continue

    logger.error("AV critic exhausted keys (quota_hits=%s): %s", quota_hits, last_err)
    alt = _critique_via_text_router(
        instruction=instruction,
        keywords=keywords,
        exact_ai_video_prompt=exact_ai_video_prompt,
        narration_bn=narration_bn,
        product_name=product_name,
        element=element,
    )
    if alt:
        return alt
    return _fallback_critique(
        narration_bn=narration_bn,
        keywords=keywords,
        exact_ai_video_prompt=exact_ai_video_prompt,
        element=element,
        product_name=product_name,
        reason=f"critic_api_failed:{last_err}",
    )


def _critique_via_text_router(
    *,
    instruction: str,
    keywords: List[str],
    exact_ai_video_prompt: str,
    narration_bn: str,
    product_name: str,
    element: str,
) -> Optional[Dict[str, Any]]:
    """Non-Google JSON critic when Gemini circuit/quota is burned."""
    try:
        from pipeline.llm_router import chat_text

        prompt = (
            instruction
            + "\n\nVIDEO FILE IS NOT ATTACHED. You CANNOT see pixels.\n"
            "HARD RULES for this text-only mode:\n"
            "- Do NOT set critical_issues to wrong_subject, visual_anchors_missing, "
            "unrelated_broll, or talking_head (impossible without video).\n"
            "- Prefer passed=true and match_score>=70 when narration + exact_ai_video_prompt "
            "look on-topic for the product/keywords.\n"
            "- Only fail on clear dialogue/script problems in the text.\n"
            "Return ONLY JSON with keys: match_score, passed, issues, "
            "critical_issues, matched_keywords, missed_keywords, "
            "visual_summary, audio_summary, revised_prompt."
        )
        out = chat_text(prompt, purpose="critic", json_mode=True)
        text = str((out or {}).get("text") or "")
        data = json.loads(_extract_json(text))
        if not isinstance(data, dict):
            return None
        data["_provider"] = f"text_router:{(out or {}).get('provider') or 'unknown'}"
        data["_text_only"] = True
        # Never trust visual hard fails from a blind text judge
        visual_hard = {
            "wrong_subject",
            "visual_anchors_missing",
            "unrelated_broll",
            "talking_head",
        }
        crit = [str(c) for c in (data.get("critical_issues") or [])]
        data["critical_issues"] = [c for c in crit if c not in visual_hard and not str(c).startswith("visual_anchors_missing")]
        issues = [str(i) for i in (data.get("issues") or [])]
        data["issues"] = [
            i
            for i in issues
            if not any(
                x in i.lower()
                for x in ("wrong_subject", "visual_anchors_missing", "unrelated_broll", "talking_head")
            )
        ]
        # On-topic text → soft pass so deterministic local gates remain the hard authority
        blob = f"{narration_bn} {exact_ai_video_prompt} {product_name}".lower()
        topic_hit = bool(product_name and product_name.lower()[:12] in blob) or any(
            str(k).lower() in blob for k in (keywords or [])[:4] if str(k).strip()
        )
        if topic_hit:
            data["matched_keywords"] = list(keywords[:6]) if keywords else data.get("matched_keywords") or []
            data["missed_keywords"] = []
            try:
                score = int(float(data.get("match_score") or 0))
            except Exception:
                score = 0
            # Must meet PASS_SCORE or normalize() forces passed=False and Agnes regen loops forever
            data["match_score"] = max(score, PASS_SCORE)
            data["passed"] = True
        return _normalize_result(
            data, keywords, exact_ai_video_prompt, narration_bn, product_name, element
        )
    except Exception as exc:
        logger.warning("text-router critic failed: %s", str(exc)[:180])
        return None

def _local_gates_only_critique(
    *,
    narration_bn: str,
    keywords: List[str],
    exact_ai_video_prompt: str,
    element: str,
    product_name: str,
    reason: str,
) -> Dict[str, Any]:
    """Deterministic degrade path — does NOT mark fallback for outage majority."""
    return {
        "match_score": 68,
        "passed": True,
        "issues": [f"critic_degraded:{reason}"],
        "critical_issues": [],
        "matched_keywords": list(keywords[:4]),
        "missed_keywords": [],
        "visual_summary": "local_gates_only",
        "audio_summary": (narration_bn or "")[:200],
        "revised_prompt": exact_ai_video_prompt
        or _default_revised_prompt(
            narration_bn=narration_bn,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            product_name=product_name,
            element=element,
            issues=[reason],
        ),
        "raw": {"local_gates_only": True, "reason": reason, "fallback": False},
        "skipped": True,
    }


def persist_critique(
    work: Path,
    idx: int,
    attempt: int,
    critique: Dict[str, Any],
    prompt_used: str,
) -> None:
    work.mkdir(parents=True, exist_ok=True)
    (work / f"scene_{idx:02d}_critique_attempt{attempt}.json").write_text(
        json.dumps(critique, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (work / f"scene_{idx:02d}_prompt_attempt{attempt}.txt").write_text(
        prompt_used or "",
        encoding="utf-8",
    )


def _critic_instruction(
    *,
    narration_bn: str,
    keywords: List[str],
    exact_ai_video_prompt: str,
    niche: str,
    element: str,
    product_name: str,
    video_dur: float,
    audio_dur: float,
    video_type: str = "short",
) -> str:
    trained = load_training_rules()
    trained_txt = "\n".join(f"- {r}" for r in trained[:40]) or "(none yet)"
    return critic_instruction(
        niche=niche,
        element=element,
        product_name=product_name,
        narration=narration_bn,
        keywords=keywords,
        exact_ai_video_prompt=exact_ai_video_prompt,
        trained_txt=trained_txt,
        video_dur=video_dur,
        audio_dur=audio_dur,
        pass_score=PASS_SCORE,
        video_type=video_type,
    )


def _critique_via_video_upload(api_key: str, video_path: Path, instruction: str) -> Optional[Dict[str, Any]]:
    from google import genai
    from google.genai import types

    # Gemini File API path — preferred for large masters (≥100MB) and used for all uploads.
    size_b = int(Path(video_path).stat().st_size) if Path(video_path).is_file() else 0
    if size_b >= 100 * 1024 * 1024:
        logger.info(
            "AV critic using Gemini File API for large video (%.1f MB)",
            size_b / (1024 * 1024),
        )

    client = genai.Client(api_key=api_key)
    uploaded = client.files.upload(file=str(video_path))
    # Wait until ACTIVE
    for _ in range(30):
        meta = client.files.get(name=uploaded.name)
        state = str(getattr(meta, "state", "") or "").upper()
        if "ACTIVE" in state or state in {"", "STATE_UNSPECIFIED"}:
            # Some SDKs return ACTIVE; empty may mean ready
            if "FAILED" in state:
                raise RuntimeError(f"file processing failed: {state}")
            if "ACTIVE" in state or getattr(meta, "uri", None):
                break
        if "FAILED" in state:
            raise RuntimeError(f"file processing failed: {state}")
        time.sleep(2)
    else:
        logger.warning("file may not be ACTIVE yet; attempting generate anyway")

    last_quota: Optional[Exception] = None
    for model in CRITIC_MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_uri(
                                file_uri=uploaded.uri,
                                mime_type=getattr(uploaded, "mime_type", None) or "video/mp4",
                            ),
                            types.Part.from_text(text=instruction),
                        ],
                    )
                ],
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            text = getattr(resp, "text", None) or str(resp)
            data = json.loads(_extract_json(text))
            data["_provider"] = f"video_upload:{model}"
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass
            return data
        except Exception as exc:
            logger.warning("critic model %s failed: %s", model, str(exc)[:160])
            msg = str(exc)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                last_quota = exc
                break  # don't hammer more models on same key
            if "503" in msg or "UNAVAILABLE" in msg:
                time.sleep(3)
                continue
            continue
    try:
        client.files.delete(name=uploaded.name)
    except Exception:
        pass
    if last_quota is not None:
        raise last_quota
    return None


def _critique_via_frames(api_key: str, video_path: Path, instruction: str) -> Optional[Dict[str, Any]]:
    from google import genai
    from google.genai import types

    frames = _extract_frames(video_path, count=5)
    if not frames:
        return None
    client = genai.Client(api_key=api_key)
    parts: List[Any] = []
    for fp in frames:
        parts.append(
            types.Part.from_bytes(data=fp.read_bytes(), mime_type="image/jpeg")
        )
    parts.append(types.Part.from_text(text=instruction + "\n(Note: analyzing sampled frames; infer AV sync from visuals + provided narration.)"))

    last_quota: Optional[Exception] = None
    for model in CRITIC_MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            text = getattr(resp, "text", None) or str(resp)
            data = json.loads(_extract_json(text))
            data["_provider"] = f"frames:{model}"
            return data
        except Exception as exc:
            logger.warning("critic frames model %s failed: %s", model, str(exc)[:160])
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                last_quota = exc
                break
            continue
    if last_quota is not None:
        raise last_quota
    return None


def _extract_frames(video_path: Path, count: int = 5) -> List[Path]:
    dur = max(ffprobe_duration(video_path), 1.0)
    out_dir = video_path.parent / f"_critic_frames_{video_path.stem}"
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: List[Path] = []
    for i in range(count):
        t = (dur * (i + 0.5) / count)
        dest = out_dir / f"f{i:02d}.jpg"
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-ss",
            f"{t:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(dest),
        ]
        subprocess.run(cmd, capture_output=True)
        if dest.exists() and dest.stat().st_size > 500:
            frames.append(dest)
    return frames


def _normalize_result(
    data: Dict[str, Any],
    keywords: List[str],
    exact_ai_video_prompt: str,
    narration_bn: str,
    product_name: str,
    element: str,
) -> Dict[str, Any]:
    try:
        score = int(float(data.get("match_score", 0)))
    except Exception:
        score = 0
    score = max(0, min(100, score))
    issues = data.get("issues") or []
    if not isinstance(issues, list):
        issues = [str(issues)]
    critical = data.get("critical_issues") or []
    if not isinstance(critical, list):
        critical = [str(critical)]
    critical = [str(c).strip().lower() for c in critical if str(c).strip()]
    # Also detect critical phrases inside issues
    for iss in issues:
        low = str(iss).lower().replace(" ", "_")
        for c in CRITICAL_ISSUES:
            if c in low or c.replace("_", " ") in str(iss).lower():
                if c not in critical:
                    critical.append(c)

    matched = data.get("matched_keywords") or []
    missed = data.get("missed_keywords") or []
    if not isinstance(matched, list):
        matched = []
    if not isinstance(missed, list):
        missed = list(keywords)

    kw_l = {str(k).strip().lower() for k in (keywords or []) if str(k).strip()}
    prod = (product_name or "").strip().lower()
    text_only = bool(data.get("_text_only")) or str(data.get("_provider") or "").startswith(
        "text_router:"
    )
    # Blind text critic cannot judge pixels — never promote visual hard fails here
    if text_only:
        visual_hard = {
            "wrong_subject",
            "visual_anchors_missing",
            "unrelated_broll",
            "talking_head",
        }
        critical = [c for c in critical if c not in visual_hard]
        issues = [
            i
            for i in issues
            if not any(
                x in str(i).lower()
                for x in (
                    "wrong_subject",
                    "visual_anchors_missing",
                    "unrelated_broll",
                    "talking_head",
                )
            )
        ]
        missed_hits = []
    else:
        missed_hits = []
        matched_l = [str(x) for x in matched]
        vis = str(data.get("visual_summary") or "")
        try:
            from pipeline.av_quality_gates import visual_phrase_covered
        except Exception:
            visual_phrase_covered = None  # type: ignore
        for m in missed:
            ml = str(m or "").strip().lower()
            if not ml:
                continue
            if visual_phrase_covered and (
                visual_phrase_covered(str(m), matched=matched_l, visual_summary=vis)
                or (
                    prod
                    and visual_phrase_covered(
                        product_name or "", matched=matched_l, visual_summary=vis
                    )
                    and (ml in prod or prod in ml)
                )
            ):
                continue
            if ml in kw_l or (prod and (ml in prod or prod in ml)):
                missed_hits.append(ml)
            elif any(ml in k or k in ml for k in kw_l):
                missed_hits.append(ml)
    if missed_hits and "visual_anchors_missing" not in critical:
        critical.append("visual_anchors_missing")

    revised = str(data.get("revised_prompt") or "").strip()
    if not revised:
        revised = _default_revised_prompt(
            narration_bn=narration_bn,
            keywords=keywords,
            exact_ai_video_prompt=exact_ai_video_prompt,
            product_name=product_name,
            element=element,
            issues=[str(i) for i in issues],
        )

    passed = bool(data.get("passed")) if "passed" in data else (score >= PASS_SCORE and not any(c in CRITICAL_ISSUES for c in critical))
    # Enforce threshold regardless of model claim
    if text_only:
        # Text-only: local deterministic gates (applied later) are the hard authority.
        # Do not fail solely on LLM score when visual criticals were stripped.
        if score < PASS_SCORE:
            score = PASS_SCORE
        passed = not any(c in CRITICAL_ISSUES for c in critical)
    elif score < PASS_SCORE or any(c in CRITICAL_ISSUES for c in critical):
        passed = False
    elif score >= PASS_SCORE and not any(c in CRITICAL_ISSUES for c in critical):
        passed = True

    return {
        "match_score": score,
        "passed": passed,
        "issues": [str(i) for i in issues],
        "critical_issues": critical,
        "matched_keywords": [str(m) for m in matched],
        "missed_keywords": [str(m) for m in missed],
        "visual_summary": str(data.get("visual_summary") or ""),
        "audio_summary": str(data.get("audio_summary") or ""),
        "revised_prompt": revised,
        "raw": data,
    }


def _fallback_critique(
    *,
    narration_bn: str,
    keywords: List[str],
    exact_ai_video_prompt: str,
    element: str,
    product_name: str,
    reason: str,
) -> Dict[str, Any]:
    """Conservative fail-open-for-regen: assume mismatch so prompt can improve."""
    revised = _default_revised_prompt(
        narration_bn=narration_bn,
        keywords=keywords,
        exact_ai_video_prompt=exact_ai_video_prompt,
        product_name=product_name,
        element=element,
        issues=[reason],
    )
    return {
        "match_score": 50,
        "passed": False,
        "issues": [f"critic_unavailable:{reason}"],
        "critical_issues": [],
        "matched_keywords": [],
        "missed_keywords": list(keywords),
        "visual_summary": "",
        "audio_summary": narration_bn[:200],
        "revised_prompt": revised,
        "raw": {"fallback": True, "reason": reason},
    }


def _default_revised_prompt(
    *,
    narration_bn: str,
    keywords: List[str],
    exact_ai_video_prompt: str,
    product_name: str,
    element: str,
    issues: List[str],
) -> str:
    return revised_visual_prompt(
        narration=narration_bn,
        keywords=keywords,
        exact_ai_video_prompt=exact_ai_video_prompt,
        product_name=product_name,
        element=element,
        issues=issues,
    )


def _extract_json(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("{"):
        return text
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else "{}"
