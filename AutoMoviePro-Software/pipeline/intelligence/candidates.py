"""Topic candidate helpers (BUILD-04G-H)."""
from __future__ import annotations

import time
from typing import Any

from pipeline.intelligence.contracts import ContentFormat, TopicCandidate
from pipeline.intelligence.fingerprint import topic_identity_fingerprint
from pipeline.intelligence.normalization import canonical_topic_key


def make_topic_id(channel_id: int, fmt: ContentFormat, canonical: str) -> str:
    fp = topic_identity_fingerprint(job_id="discovery", channel_id=channel_id, fmt=fmt.value, canonical_topic=canonical)
    return f"t-{fp[:16]}"


def validate_candidate_dict(d: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate candidate identity fields before materialization."""
    issues: list[str] = []
    title = str(d.get("title") or "").strip()
    if not title:
        issues.append("missing_title")
    source = str(d.get("source") or "").strip()
    if not source:
        issues.append("missing_source")
    try:
        channel_id = int(d.get("channel_id") or 0)
    except (TypeError, ValueError):
        channel_id = 0
    if channel_id <= 0:
        issues.append("invalid_channel_id")
    fmt_raw = str(d.get("format") or "LONG").upper()
    if fmt_raw not in ("LONG", "SHORT"):
        issues.append("invalid_format")
    if source == "discovery":
        prov = (d.get("metadata") or {}).get("provenance") or {}
        if not prov.get("discovered_at"):
            issues.append("missing_discovered_at")
        if not prov.get("provider"):
            issues.append("missing_provider")
        if prov.get("external_api") is not False:
            issues.append("missing_external_api_flag")
    return len(issues) == 0, issues


def candidate_from_dict(d: dict[str, Any], *, strict: bool = False) -> TopicCandidate:
    ok, issues = validate_candidate_dict(d)
    if strict and not ok:
        raise ValueError(f"invalid_candidate:{','.join(issues)}")
    fmt = ContentFormat(d.get("format") or "LONG")
    title = str(d.get("title") or "")
    canonical = str(d.get("canonical_topic") or canonical_topic_key(title))
    channel_id = int(d.get("channel_id") or 0)
    tid = str(d.get("topic_id") or make_topic_id(channel_id, fmt, canonical))
    metadata = dict(d.get("metadata") or {})
    if d.get("source") == "discovery" and "provenance" not in metadata:
        metadata.setdefault("provenance", {
            "source": "discovery",
            "source_type": "local_generated",
            "provider": "local_discovery_v1",
            "external_api": False,
            "discovered_at": time.time(),
            "channel_id": channel_id,
            "format": fmt.value,
        })
    return TopicCandidate(
        title=title,
        canonical_topic=canonical,
        format=fmt,
        channel_id=channel_id,
        niche=str(d.get("niche") or ""),
        angle=str(d.get("angle") or ""),
        audience=str(d.get("audience") or ""),
        source=str(d.get("source") or "discovery"),
        topic_id=tid,
        language=str(d.get("language") or "en"),
        target_duration_sec=int(d.get("target_duration_sec") or 0),
        novelty_reason=str(d.get("novelty_reason") or ""),
        relevance_reason=str(d.get("relevance_reason") or ""),
        evidence_need=str(d.get("evidence_need") or ""),
        confidence=float(d.get("confidence") or 0.5),
        metadata=metadata,
    )
