"""Research runtime with idempotency + live provider (BUILD-04G-H)."""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.idempotency.fingerprint import compute_fingerprint
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.states import IdempotencyState
from pipeline.intelligence.config import ResearchMode, get_research_mode
from pipeline.intelligence.contracts import INTELLIGENCE_CONTRACT_VERSION, ApiCostMetrics, ResearchRequest
from pipeline.intelligence.fingerprint import compute_research_fingerprint, detect_conflicts
from pipeline.intelligence.normalization import normalize_research_query
from pipeline.intelligence.research_provider import get_research_provider, research_unavailable_error

logger = logging.getLogger(__name__)

ResearchFn = Callable[[], dict[str, Any]]
_COST_LEDGER: list[dict[str, Any]] = []
_FP_LOCKS: dict[str, threading.Lock] = {}
_FP_REGISTRY = threading.Lock()


def _fingerprint_lock(fingerprint: str) -> threading.Lock:
    with _FP_REGISTRY:
        if fingerprint not in _FP_LOCKS:
            _FP_LOCKS[fingerprint] = threading.Lock()
        return _FP_LOCKS[fingerprint]


@dataclass
class ResearchResult:
    success: bool
    action: str = ""
    fingerprint: str = ""
    research: Optional[dict[str, Any]] = None
    fact_pack: Optional[dict[str, Any]] = None
    metrics: ApiCostMetrics = field(default_factory=ApiCostMetrics)
    state: IdempotencyState = IdempotencyState.NOT_STARTED
    provider_mode: str = ""


def get_cost_ledger() -> list[dict[str, Any]]:
    return list(_COST_LEDGER)


def reset_cost_ledger() -> None:
    _COST_LEDGER.clear()


def _record_cost(entry: dict[str, Any]) -> None:
    entry.setdefault("timestamp", time.time())
    _COST_LEDGER.append(entry)


def _stamp_research_metadata(
    out: dict[str, Any],
    req: ResearchRequest,
    mode: ResearchMode,
    *,
    fingerprint: str = "",
) -> dict[str, Any]:
    """Ensure persisted research records carry provenance fields (RV-006)."""
    research = out.setdefault("research", {})
    ts = time.time()
    research.setdefault("timestamp", ts)
    research.setdefault("queried_at", ts)
    research.setdefault("query", (req.query or req.canonical_topic or "").strip())
    if research.get("provider"):
        pass  # preserve provider identity from adapter (e.g. live_local, mock)
    else:
        research["provider"] = mode.value
    research.setdefault("topic_id", req.topic_id)
    research.setdefault("canonical_topic", req.canonical_topic)
    claims = (out.get("fact_pack") or {}).get("claims") or research.get("evidence") or []
    if claims:
        research["evidence"] = claims
        sources = sorted({str(c.get("source") or "") for c in claims if isinstance(c, dict) and c.get("source")})
        if sources:
            research["sources"] = sources
    if fingerprint:
        out["research_fingerprint"] = fingerprint
        research.setdefault("fingerprint", fingerprint)
    out["provider_mode"] = mode.value
    out["persisted_at"] = ts
    return out


def _validate_research_artifact(
    research_data: dict[str, Any] | None,
    fact_pack: dict[str, Any] | None,
) -> tuple[bool, str]:
    if research_data and research_data.get("gate_error"):
        return False, "provider_unavailable"
    if research_data and research_data.get("status") == "PROVIDER_UNAVAILABLE":
        return False, "provider_unavailable"
    if not fact_pack and not research_data:
        return False, "empty_research"
    claims = (fact_pack or {}).get("claims") or []
    if not claims:
        return False, "no_claims"
    for c in claims:
        if not isinstance(c, dict):
            return False, "invalid_claim"
        if not str(c.get("source") or "").strip():
            return False, "missing_source"
    return True, "ok"


def execute_research_request(
    work_dir: Path,
    req: ResearchRequest,
    *,
    job_id: str,
    provider_fn: Optional[ResearchFn] = None,
    use_mock: bool | None = None,
    mock_provider=None,
) -> ResearchResult:
    work_dir = Path(work_dir)
    job_id = job_id or work_dir.name
    req.query = normalize_research_query(req.query or req.canonical_topic)
    normalized_inputs = {
        "canonical_topic": req.canonical_topic.strip(),
        "query": req.query.strip(),
        "language": req.language,
        "region": req.region,
        "time_window": req.time_window,
        "prompt_version": req.prompt_version,
    }
    if use_mock is False:
        mode = ResearchMode.LIVE
    elif use_mock is True:
        mode = ResearchMode.MOCK
    else:
        mode = get_research_mode()
    fingerprint = compute_fingerprint(
        job_id=job_id,
        stage="research",
        entity_id=f"research-{req.topic_id}",
        contract_version=INTELLIGENCE_CONTRACT_VERSION,
        provider=req.provider or mode.value,
        model=req.model,
        inputs=normalized_inputs,
    )
    with _fingerprint_lock(fingerprint):
        return _execute_research_locked(
            work_dir, req, job_id=job_id, provider_fn=provider_fn,
            use_mock=use_mock, mock_provider=mock_provider, fingerprint=fingerprint,
            normalized_inputs=normalized_inputs, mode=mode,
        )


def _execute_research_locked(
    work_dir: Path,
    req: ResearchRequest,
    *,
    job_id: str,
    provider_fn: Optional[ResearchFn],
    use_mock: bool | None,
    mock_provider,
    fingerprint: str,
    normalized_inputs: dict[str, Any],
    mode: ResearchMode,
) -> ResearchResult:
    executor = IdempotentExecutor(work_dir)
    inv = {"n": 0}
    metrics = ApiCostMetrics(provider=req.provider or mode.value)

    def _execute() -> dict[str, Any]:
        inv["n"] += 1
        metrics.cache_misses += 1
        metrics.request_count += 1
        if provider_fn:
            out = provider_fn()
        else:
            if mode == ResearchMode.MOCK:
                mp = mock_provider
                if mp is None:
                    from pipeline.intelligence.mock_research_provider import get_mock_research_provider
                    mp = get_mock_research_provider()
                out = mp.research(req)
            else:
                try:
                    provider = get_research_provider(mode=ResearchMode.LIVE)
                    out = provider.research(req)
                except Exception as exc:
                    return research_unavailable_error(req, str(exc))
        out = _stamp_research_metadata(out, req, mode, fingerprint=fingerprint)
        _record_cost({
            "provider": mode.value,
            "model": req.model,
            "operation": "research",
            "fingerprint": fingerprint,
            "cache_hit": False,
            "retry_count": 0,
            "result_status": "executed",
        })
        return out

    def _validate(out: dict[str, Any]) -> tuple[bool, str]:
        if out.get("gate_error"):
            return False, "provider_unavailable"
        ok, reason = _validate_research_artifact(out.get("research"), out.get("fact_pack"))
        if not ok:
            return False, reason
        claims = (out.get("fact_pack") or {}).get("claims") or []
        conflicts = detect_conflicts(claims)
        if conflicts:
            out.setdefault("research", {})["conflicts"] = conflicts
        return True, "ok"

    def _persist(out: dict[str, Any]) -> str:
        stamped = _stamp_research_metadata(dict(out), req, mode, fingerprint=fingerprint)
        out_path = work_dir / "research" / f"{req.topic_id}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        import os as _os
        import time as _time
        tmp = out_path.with_name(f"{out_path.stem}.{_time.time_ns()}.tmp")
        tmp.write_text(json.dumps(stamped, ensure_ascii=False, indent=2), encoding="utf-8")
        _os.replace(tmp, out_path)
        return str(out_path)

    result = executor.execute(
        job_id=job_id,
        stage="research",
        entity_id=f"research-{req.topic_id}",
        inputs=normalized_inputs,
        provider=req.provider or mode.value,
        model=req.model,
        execute_fn=_execute,
        validate_fn=_validate,
        persist_fn=_persist,
    )

    if result.action == "reuse":
        metrics.cache_hits += 1
        metrics.avoided_calls += 1
        _record_cost({
            "provider": mode.value,
            "model": req.model,
            "operation": "research",
            "fingerprint": fingerprint,
            "cache_hit": True,
            "result_status": "reuse",
        })

    research_data = None
    fact_pack = None
    if result.result_reference and Path(result.result_reference).is_file():
        data = json.loads(Path(result.result_reference).read_text(encoding="utf-8"))
        research_data = data.get("research")
        fact_pack = data.get("fact_pack")

    artifact_ok, _artifact_reason = _validate_research_artifact(research_data, fact_pack)
    success = (
        result.action in ("execute", "reuse")
        and artifact_ok
        and not (research_data or {}).get("status") == "PROVIDER_UNAVAILABLE"
    )
    return ResearchResult(
        success=success,
        action=result.action,
        fingerprint=result.fingerprint,
        research=research_data,
        fact_pack=fact_pack,
        metrics=metrics,
        state=result.state,
        provider_mode=mode.value,
    )


def provider_execution_count() -> int:
    return sum(1 for e in _COST_LEDGER if not e.get("cache_hit"))
