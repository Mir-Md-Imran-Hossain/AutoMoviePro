"""Topic reserve queues — persistent + atomic (BUILD-04G-H)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional, Sequence

from app.config import DATA_DIR
from pipeline.idempotency.fs_lock import exclusive_path_lock
from pipeline.intelligence.contracts import ContentFormat, DEFAULT_RESERVE_MIN, TopicLifecycleStatus

RESERVE_SCHEMA_VERSION = 1


def persistent_reserve_path(
    channel_id: int,
    fmt: ContentFormat,
    *,
    language: str = "en",
) -> Path:
    lang = (language or "en").strip().lower()[:16] or "en"
    return DATA_DIR / "intelligence" / "reserves" / f"ch{channel_id}" / lang / f"{fmt.value.lower()}_topic_reserve.json"


def reserve_path(
    work_dir: Path | None,
    fmt: ContentFormat,
    *,
    channel_id: int = 0,
    language: str = "en",
) -> Path:
    if channel_id:
        return persistent_reserve_path(channel_id, fmt, language=language)
    return Path(work_dir or DATA_DIR) / "intelligence" / f"{fmt.value.lower()}_topic_reserve.json"


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import time as _time
    for attempt in range(8):
        tmp = path.with_name(f"{path.stem}.{os.getpid()}.{_time.time_ns()}.tmp")
        try:
            data = json.dumps(payload, ensure_ascii=False, indent=2)
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
            return
        except OSError:
            _time.sleep(0.02 * (attempt + 1))
            try:
                if tmp.is_file():
                    tmp.unlink()
            except OSError:
                pass
    raise OSError(f"atomic write failed for {path}")


def _read_json(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        bak = path.with_suffix(path.suffix + ".corrupt")
        try:
            if path.is_file():
                os.replace(path, bak)
        except OSError:
            pass
        return []


def load_reserve(
    work_dir: Path | None,
    fmt: ContentFormat,
    *,
    channel_id: int = 0,
    language: str = "en",
) -> list[dict[str, Any]]:
    p = reserve_path(work_dir, fmt, channel_id=channel_id, language=language)
    with exclusive_path_lock(p):
        return _read_json(p)


def save_reserve(
    work_dir: Path | None,
    fmt: ContentFormat,
    entries: list[dict[str, Any]],
    *,
    channel_id: int = 0,
    language: str = "en",
) -> Path:
    p = reserve_path(work_dir, fmt, channel_id=channel_id, language=language)
    with exclusive_path_lock(p):
        _atomic_write_json(p, entries)
    return p


def reserve_topic_key(entry: dict[str, Any]) -> str:
    return str(entry.get("canonical_topic") or entry.get("title") or "").strip().lower()


def _entry_score(entry: dict[str, Any]) -> float:
    score = entry.get("score")
    if isinstance(score, dict):
        return float(score.get("total_score") or 0)
    try:
        return float(score or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_reserve_entry(
    cand: dict[str, Any],
    *,
    score: Any,
    channel_id: int,
    language: str,
    fmt: ContentFormat,
    reserved_at: float | None = None,
) -> dict[str, Any]:
    now = time.time()
    total = score.get("total_score") if isinstance(score, dict) else score
    meta = cand.get("metadata") or {}
    return {
        **cand,
        "topic_id": cand.get("topic_id"),
        "channel_id": channel_id,
        "format": fmt.value,
        "language": (language or "en").strip().lower()[:16] or "en",
        "score": total,
        "fingerprint": meta.get("discovery_fingerprint") or cand.get("fingerprint") or cand.get("topic_id"),
        "status": TopicLifecycleStatus.RESERVED.value,
        "reserved_at": reserved_at or now,
        "refreshed_at": now,
        "reserve_schema_version": RESERVE_SCHEMA_VERSION,
    }


def merge_reserve_entries(
    existing: Sequence[dict[str, Any]],
    incoming: Sequence[dict[str, Any]],
    *,
    max_entries: int,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for entry in existing:
        key = reserve_topic_key(entry)
        if not key:
            continue
        if entry.get("status") == TopicLifecycleStatus.CONSUMED.value:
            continue
        merged[key] = dict(entry)

    for entry in incoming:
        key = reserve_topic_key(entry)
        if not key:
            continue
        if key in merged:
            if _entry_score(entry) >= _entry_score(merged[key]):
                preserved = merged[key].get("reserved_at")
                merged[key] = {
                    **merged[key],
                    **entry,
                    "reserved_at": preserved or entry.get("reserved_at"),
                    "refreshed_at": time.time(),
                }
        else:
            merged[key] = dict(entry)

    ordered = sorted(
        merged.values(),
        key=lambda item: (-_entry_score(item), str(item.get("topic_id") or item.get("canonical_topic") or "")),
    )
    ordered = ordered[:max_entries]
    for index, entry in enumerate(ordered):
        entry["rank"] = index + 1
    return ordered


def reserve_refresh_fingerprint(
    ranked: Sequence[dict[str, Any]],
    *,
    channel_id: int,
    fmt: ContentFormat,
    language: str = "en",
) -> str:
    parts: list[str] = []
    for row in ranked:
        if not row.get("eligible"):
            continue
        score = row.get("score") or {}
        if isinstance(score, dict) and score.get("hard_blocked"):
            continue
        cand = row.get("candidate") or {}
        total = score.get("total_score") if isinstance(score, dict) else score
        parts.append(f"{cand.get('topic_id')}|{total}")
    parts.sort()
    blob = f"{channel_id}:{fmt.value}:{language}:" + ";".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def update_reserve(
    work_dir: Path | None,
    fmt: ContentFormat,
    ranked: Sequence[dict[str, Any]],
    *,
    channel_id: int = 0,
    language: str = "en",
    min_size: int = DEFAULT_RESERVE_MIN,
) -> dict[str, Any]:
    p = reserve_path(work_dir, fmt, channel_id=channel_id, language=language)
    max_entries = max(min_size, 10)
    eligible = [r for r in ranked if r.get("eligible") and not (r.get("score") or {}).get("hard_blocked")]
    incoming = [
        normalize_reserve_entry(
            r.get("candidate") or {},
            score=r.get("score") or {},
            channel_id=channel_id,
            language=language,
            fmt=fmt,
        )
        for r in eligible[:max_entries]
    ]
    refresh_fp = reserve_refresh_fingerprint(
        ranked,
        channel_id=channel_id,
        fmt=fmt,
        language=language,
    )
    with exclusive_path_lock(p):
        existing = _read_json(p)
        merged = merge_reserve_entries(existing, incoming, max_entries=max_entries)
        _atomic_write_json(p, merged)
    count = len(merged)
    status = "OK" if count >= min_size else "RESERVE_DEPLETED"
    return {
        "format": fmt.value,
        "count": count,
        "min_required": min_size,
        "needs_discovery": count < min_size,
        "status": status,
        "refresh_fingerprint": refresh_fp,
        "merged": len(incoming),
    }


def consume_top(
    work_dir: Path | None,
    fmt: ContentFormat,
    *,
    channel_id: int = 0,
    language: str = "en",
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    p = reserve_path(work_dir, fmt, channel_id=channel_id, language=language)
    with exclusive_path_lock(p):
        entries = _read_json(p)
        if not entries:
            return None, []
        top = entries.pop(0)
        top["status"] = TopicLifecycleStatus.CONSUMED.value
        for i, e in enumerate(entries):
            e["rank"] = i + 1
        _atomic_write_json(p, entries)
        return top, entries


def validate_reserve_integrity(entries: Sequence[dict[str, Any]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    seen: set[str] = set()
    for e in entries:
        key = reserve_topic_key(e)
        if not key:
            issues.append("missing_title")
        if e.get("status") in (
            TopicLifecycleStatus.BLOCKED.value,
            TopicLifecycleStatus.REJECTED.value,
            TopicLifecycleStatus.EXPIRED.value,
            TopicLifecycleStatus.CONSUMED.value,
        ):
            issues.append(f"invalid_status:{key}")
        score = e.get("score")
        if score is not None and not isinstance(score, (int, float)):
            if not (isinstance(score, dict) and "total_score" in score):
                issues.append(f"invalid_score:{key}")
        if key and key in seen:
            issues.append(f"duplicate_in_reserve:{key}")
        if key:
            seen.add(key)
    return len(issues) == 0, issues


def repair_reserve(
    work_dir: Path | None,
    fmt: ContentFormat,
    *,
    channel_id: int = 0,
    language: str = "en",
) -> dict[str, Any]:
    p = reserve_path(work_dir, fmt, channel_id=channel_id, language=language)
    with exclusive_path_lock(p):
        entries = _read_json(p)
        ok, issues = validate_reserve_integrity(entries)
        if ok:
            return {"repaired": False, "issues": [], "remaining": len(entries)}
        clean: list[dict[str, Any]] = []
        seen: set[str] = set()
        for e in entries:
            key = reserve_topic_key(e)
            if not key or key in seen:
                continue
            if e.get("status") in (
                TopicLifecycleStatus.BLOCKED.value,
                TopicLifecycleStatus.REJECTED.value,
                TopicLifecycleStatus.EXPIRED.value,
                TopicLifecycleStatus.CONSUMED.value,
            ):
                continue
            seen.add(key)
            clean.append(e)
        for i, e in enumerate(clean):
            e["rank"] = i + 1
        _atomic_write_json(p, clean)
        return {"repaired": True, "issues": issues, "remaining": len(clean)}


def purge_low_quality_reserve(
    work_dir: Path | None,
    fmt: ContentFormat,
    *,
    channel_id: int = 0,
    language: str = "en",
    niche: str = "",
) -> dict[str, Any]:
    """Remove placeholder / generic topics left from older discovery builds."""
    from pipeline.intelligence.topic_quality import validate_topic_quality

    p = reserve_path(work_dir, fmt, channel_id=channel_id, language=language)
    removed: list[str] = []
    with exclusive_path_lock(p):
        entries = _read_json(p)
        keep: list[dict[str, Any]] = []
        for e in entries:
            title = str(e.get("title") or e.get("canonical_topic") or "")
            q = validate_topic_quality(title, niche=niche)
            if not q.get("ok"):
                removed.append(title)
                continue
            keep.append(e)
        for i, e in enumerate(keep):
            e["rank"] = i + 1
        if removed:
            _atomic_write_json(p, keep)
        remaining = len(keep)
    return {"removed": len(removed), "remaining": remaining, "samples": removed[:5]}

