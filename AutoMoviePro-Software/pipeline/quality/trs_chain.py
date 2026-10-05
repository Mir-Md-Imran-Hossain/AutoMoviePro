"""Persist Topic → Research → FactPack → Script chain artifacts (Critical-12 Q1)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


def persist_trs_chain_artifacts(
    work_dir: Path,
    *,
    topic: str = "",
    research: Optional[dict[str, Any]] = None,
    fact_pack: Optional[dict[str, Any]] = None,
    script_plan: Optional[dict[str, Any]] = None,
    job_id: str = "",
) -> dict[str, Any]:
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    job = job_id or work_dir.name
    written: list[str] = []

    topic_doc = {
        "job_id": job,
        "status": "PRESENT" if str(topic or "").strip() else "MISSING",
        "topic_text": topic,
        "authority": "pipeline.intelligence.topic_quality / TRS",
    }
    (work_dir / "TOPIC.json").write_text(json.dumps(topic_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    written.append("TOPIC.json")

    research_doc = dict(research or {})
    research_doc.setdefault("job_id", job)
    research_doc.setdefault("status", "PRESENT" if research else "ABSENT")
    (work_dir / "RESEARCH.json").write_text(json.dumps(research_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    written.append("RESEARCH.json")

    fp_doc = dict(fact_pack or {})
    fp_doc.setdefault("job_id", job)
    fp_doc.setdefault("status", "PRESENT" if fact_pack else "ABSENT")
    (work_dir / "FACTPACK.json").write_text(json.dumps(fp_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    written.append("FACTPACK.json")

    script_doc = dict(script_plan or {})
    script_doc.setdefault("job_id", job)
    script_doc.setdefault("status", "PRESENT" if script_plan else "ABSENT")
    script_doc.setdefault("topic", topic)
    (work_dir / "SCRIPT.json").write_text(json.dumps(script_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    written.append("SCRIPT.json")

    chain = {
        "job_id": job,
        "order": ["TOPIC", "RESEARCH", "FACTPACK", "SCRIPT"],
        "files": written,
        "linked": True,
        "authority": "pipeline.quality.trs_chain",
    }
    (work_dir / "TRS_CHAIN.json").write_text(json.dumps(chain, ensure_ascii=False, indent=2), encoding="utf-8")
    return chain
