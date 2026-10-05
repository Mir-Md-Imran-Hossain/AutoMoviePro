"""Idempotent script/director bridge — BUILD-04C."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.idempotency.script_request import (
    DEFAULT_SCRIPT_MODEL,
    DEFAULT_SCRIPT_PROVIDER,
    ScriptRequestSpec,
    director_prompt_identity,
    load_fact_pack_identity,
    topic_identity_from_parts,
)
from pipeline.idempotency.script_runtime import ScriptGenerationResult, execute_script_request
from pipeline.idempotency.states import IdempotencyState

logger = logging.getLogger(__name__)


def build_script_spec(
    *,
    job_id: str,
    niche: str,
    niche_id: int,
    video_type: str,
    topic: str,
    max_seconds: int,
    research_notes: str = "",
    blocked_products: Optional[List[str]] = None,
    channel_specials: Optional[Dict[str, str]] = None,
    fact_pack_id: str = "",
    fact_pack_hash: str = "",
    provider: str = DEFAULT_SCRIPT_PROVIDER,
    model: str = DEFAULT_SCRIPT_MODEL,
    language: str = "en",
    revision_id: str = "",
) -> ScriptRequestSpec:
    from pipeline.idempotency.fingerprint import hash_text

    prompt_version, prompt_template_hash = director_prompt_identity()
    tid = topic_identity_from_parts(topic=topic, niche=niche, niche_id=niche_id)
    return ScriptRequestSpec(
        job_id=job_id,
        topic=topic,
        topic_identity=tid,
        niche=niche,
        niche_id=int(niche_id or 0),
        video_type=video_type,
        max_seconds=int(max_seconds),
        language=language,
        provider=provider,
        model=model,
        research_notes_hash=hash_text(research_notes)[:32],
        fact_pack_id=fact_pack_id,
        fact_pack_hash=fact_pack_hash,
        prompt_version=prompt_version,
        prompt_template_hash=prompt_template_hash,
        blocked_products=list(blocked_products or []),
        channel_specials=dict(channel_specials or {}),
        revision_id=revision_id,
    )


def idempotent_plan_niche_production(
    work_dir: Path,
    *,
    job_id: str,
    niche: str,
    channel_name: str,
    video_type: str,
    topic: str = "",
    research_notes: str = "",
    google_api_keys: Optional[List[str]] = None,
    openrouter_api: str = "",
    openrouter_keys: Optional[List[str]] = None,
    max_seconds: int = 120,
    blocked_products: Optional[List[str]] = None,
    channel_specials: Optional[Dict[str, str]] = None,
    niche_id: Optional[int] = None,
    niche_pack: Optional[Dict[str, Any]] = None,
    revision_id: str = "",
    provider_fn=None,
    use_mock: bool = False,
    mock_provider=None,
    plan_filename: str = "director_plan.json",
) -> Dict[str, Any]:
    """
    Canonical wrapper around plan_niche_production.
    Preserves existing generator as execution engine.
    """
    work_dir = Path(work_dir)
    job_id = job_id or work_dir.name
    out_path = work_dir / plan_filename
    fp_id, fp_hash = load_fact_pack_identity(work_dir)
    spec = build_script_spec(
        job_id=job_id,
        niche=niche,
        niche_id=int(niche_id or 0),
        video_type=video_type,
        topic=topic,
        max_seconds=max_seconds,
        research_notes=research_notes,
        blocked_products=blocked_products,
        channel_specials=channel_specials,
        fact_pack_id=fp_id,
        fact_pack_hash=fp_hash,
        revision_id=revision_id,
    )

    if out_path.is_file() and not revision_id:
        try:
            import json

            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if existing.get("scenes"):
                r = execute_script_request(
                    work_dir,
                    spec,
                    out_path,
                    skip_generation=True,
                    skip_reference=str(out_path),
                )
                if r.success and r.plan:
                    return r.plan
        except Exception:
            pass

    if provider_fn is None and not use_mock:

        def _real():
            from pipeline.niche_director import plan_niche_production

            return plan_niche_production(
                niche=niche,
                niche_id=niche_id,
                channel_name=channel_name,
                video_type=video_type,
                topic=topic,
                research_notes=research_notes,
                google_api_keys=google_api_keys,
                openrouter_api=openrouter_api,
                openrouter_keys=openrouter_keys,
                max_seconds=max_seconds,
                blocked_products=blocked_products,
                channel_specials=channel_specials,
                niche_pack=niche_pack,
            )

        provider_fn = _real

    result = execute_script_request(
        work_dir,
        spec,
        out_path,
        provider_fn=provider_fn,
        use_mock=use_mock,
        mock_provider=mock_provider,
    )

    if result.success and result.plan:
        plan = dict(result.plan)
        # Full industrial compliance proof with artifact + optional LLM judge
        try:
            from pipeline.creative_production.prompt_compliance_auditor import (
                PromptComplianceError,
                audit_script_prompt_compliance,
            )

            audit = audit_script_prompt_compliance(
                plan,
                work_dir=work_dir,
                job_id=job_id,
                enable_llm_critic=None,  # honor AMP_PROMPT_COMPLIANCE_LLM
                repair=True,
                fail_closed=True,
                google_api_keys=google_api_keys,
                openrouter_keys=openrouter_keys,
            )
            plan = audit.get("plan") or plan
            plan["prompt_compliance"] = {
                "verdict": audit.get("verdict"),
                "overall_score": audit.get("overall_score"),
                "industrial_grade": audit.get("industrial_grade"),
                "artifact_path": audit.get("artifact_path"),
                "llm_critic_verdict": (audit.get("llm_critic") or {}).get("verdict"),
                "repairs_applied": audit.get("repairs_applied") or [],
            }
            try:
                import json

                out_path.write_text(
                    json.dumps(plan, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
            except Exception:
                pass
            return plan
        except PromptComplianceError as exc:
            logger.error("prompt compliance blocked job=%s: %s", job_id, exc)
            raise RuntimeError(str(exc)) from exc
        except Exception as exc:
            logger.warning("prompt compliance audit soft-fail in bridge: %s", exc)
            return plan

    if result.state == IdempotencyState.UNKNOWN:
        raise RuntimeError("Script generation UNKNOWN — reconciliation required before retry")

    raise RuntimeError(
        f"script generation failed action={result.action} state={result.state}"
    )


def idempotent_script_generation(
    work_dir: Path,
    spec: ScriptRequestSpec,
    out_path: Path,
    *,
    provider_fn=None,
    use_mock: bool = False,
    mock_provider=None,
) -> ScriptGenerationResult:
    """Lower-level entry for tests and future multi-path integration."""
    return execute_script_request(
        work_dir,
        spec,
        out_path,
        provider_fn=provider_fn,
        use_mock=use_mock,
        mock_provider=mock_provider,
    )
