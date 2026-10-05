"""Per-channel topic history — drives discovery diversity & anti-repeat.

Sources merged (deduped, newest first):
  1) data/intelligence/topic_history/ch{N}.json  (selections / consumes)
  2) product_registry.reviewed_products
  3) channel DNA historical_topics (if present)
  4) optional TRS workflow current + history list
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.config import DATA_DIR

_STOP = {
    "about",
    "after",
    "before",
    "could",
    "every",
    "explained",
    "from",
    "guide",
    "how",
    "into",
    "that",
    "their",
    "there",
    "these",
    "this",
    "those",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
    "year",
}


def history_path(channel_id: int) -> Path:
    return DATA_DIR / "intelligence" / "topic_history" / f"ch{int(channel_id)}.json"


def _read(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [x for x in data["items"] if isinstance(x, dict)]
    return []


def _write(path: Path, items: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "topic_history_v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": items[:200],
    }
    tmp = path.with_suffix(f".{int(time.time()*1000)}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def significant_tokens(text: str) -> set[str]:
    toks = re.findall(r"[a-z0-9\u0980-\u09ff]{4,}", (text or "").lower())
    return {t for t in toks if t not in _STOP}


def topics_too_similar(a: str, b: str, *, token_overlap: int = 2, jaccard: float = 0.45) -> bool:
    """True when titles are near-duplicates (same story angle)."""
    aa = (a or "").strip().lower()
    bb = (b or "").strip().lower()
    if not aa or not bb:
        return False
    if aa == bb:
        return True
    if aa in bb or bb in aa:
        ta, tb = significant_tokens(aa), significant_tokens(bb)
        if len(ta & tb) >= max(2, token_overlap):
            return True
    try:
        from pipeline.product_registry import similarity_score

        if similarity_score(a, b) >= jaccard:
            return True
    except Exception:
        pass
    ta, tb = significant_tokens(aa), significant_tokens(bb)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    if inter >= token_overlap and inter / max(1, len(ta | tb)) >= 0.4:
        return True
    return False


def record_topic_use(
    channel_id: int,
    topic: str,
    *,
    source: str = "selected",
    video_type: str = "",
    niche: str = "",
) -> None:
    text = " ".join(str(topic or "").strip().split())
    if not text or not channel_id:
        return
    path = history_path(channel_id)
    items = _read(path)
    # de-dupe exact (keep newest at front)
    items = [x for x in items if str(x.get("topic") or "").strip().lower() != text.lower()]
    items.insert(
        0,
        {
            "topic": text,
            "source": source,
            "video_type": video_type,
            "niche": niche,
            "at": datetime.now(timezone.utc).isoformat(),
            "ts": time.time(),
        },
    )
    _write(path, items)


def load_channel_topic_history(
    channel_id: int,
    *,
    niche: str = "",
    channel: Optional[Dict[str, Any]] = None,
    limit: int = 80,
) -> List[str]:
    """Newest-first unique topic strings for anti-repeat / content-gap."""
    out: List[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        t = " ".join(str(name or "").strip().split())
        if not t:
            return
        key = t.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(t)

    if channel_id:
        for row in _read(history_path(channel_id)):
            _add(str(row.get("topic") or ""))

    try:
        from pipeline import product_registry as preg

        for row in preg.list_reviewed(channel_id=channel_id) or []:
            _add(str(row.get("product_name") or row.get("title") or ""))
    except Exception:
        pass

    if channel:
        dna_hist = channel.get("historical_topics") or []
        if isinstance(dna_hist, list):
            for t in dna_hist:
                _add(str(t))
        # TRS workflow current topic + history bag
        try:
            login = str(channel.get("owner_login_id") or channel.get("login_id") or "")
            if login:
                from app.customer_trs_workflow import load_workflow

                st = load_workflow(login, int(channel_id))
                cur = ((st.get("topic") or {}).get("topic_text") or "")
                _add(cur)
                for t in list(st.get("topic_history") or [])[:40]:
                    if isinstance(t, dict):
                        _add(str(t.get("topic_text") or t.get("topic") or ""))
                    else:
                        _add(str(t))
        except Exception:
            pass

    if niche:
        # niche-wide soft memory (same niche other channels) — secondary
        try:
            from pipeline import product_registry as preg

            for row in (preg.list_reviewed(niche=niche) or [])[:30]:
                _add(str(row.get("product_name") or ""))
        except Exception:
            pass

    return out[:limit]


def is_repeat_of_history(
    topic: str,
    historical: Sequence[str],
    *,
    recent_n: int = 12,
) -> bool:
    text = (topic or "").strip()
    if not text:
        return True
    for h in list(historical)[:recent_n]:
        if topics_too_similar(text, h):
            return True
    return False


def dominant_entities(historical: Sequence[str], *, recent_n: int = 5) -> set[str]:
    """Tokens that dominate the last few picks — discovery should prefer other entities."""
    counts: Dict[str, int] = {}
    for h in list(historical)[:recent_n]:
        for tok in significant_tokens(h):
            counts[tok] = counts.get(tok, 0) + 1
    return {t for t, n in counts.items() if n >= 2}
