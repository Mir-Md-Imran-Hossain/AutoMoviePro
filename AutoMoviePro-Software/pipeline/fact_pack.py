"""FactPack v0 — claims with evidence; script must not invent outside pack."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def build_fact_pack(
    topic: str,
    *,
    notes: str = "",
    claims: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    if claims:
        for i, c in enumerate(claims):
            if not isinstance(c, dict):
                continue
            rows.append(
                {
                    "id": str(c.get("id") or f"F{i+1:02d}"),
                    "claim": str(c.get("claim") or "").strip(),
                    "evidence": str(c.get("evidence") or "UNVERIFIED"),
                    "source": str(c.get("source") or "notes"),
                    "confidence": float(c.get("confidence") or 0.5),
                    "freshness": str(c.get("freshness") or "UNVERIFIED"),
                }
            )
    # Seed from research notes sentences
    for i, sent in enumerate(re.split(r"(?<=[.!?])\s+", notes or "")):
        sent = sent.strip()
        if len(sent) < 20:
            continue
        if any(sent == r["claim"] for r in rows):
            continue
        rows.append(
            {
                "id": f"N{i+1:02d}",
                "claim": sent,
                "evidence": "research_notes",
                "source": "research_notes",
                "confidence": 0.4,
                "freshness": "UNVERIFIED",
            }
        )
        if len(rows) >= 12:
            break
    if not rows and topic:
        tl = topic.lower()
        if any(k in tl for k in ("crypto", "finance", "money", "invest", "bitcoin", "market", "trade")):
            claim_text = f"{topic} represents a dynamic subject of ongoing financial and technological development."
        elif any(k in tl for k in ("recipe", "cook", "food", "cake", "pancake", "kitchen", "bake")):
            claim_text = f"{topic} features distinctive preparation methods and time-tested culinary principles."
        elif any(k in tl for k in ("health", "fit", "diet", "sleep", "body", "muscle")):
            claim_text = f"{topic} impacts physiological wellness according to modern health and clinical research."
        elif any(k in tl for k in ("islam", "quran", "prophet", "mosque")):
            claim_text = f"{topic} reflects deep historical wisdom and enduring spiritual principles."
        elif any(k in tl for k in ("history", "ancient", "civilization", "ruins", "archaeolog")):
            claim_text = f"{topic} remains a compelling subject of historical and archaeological inquiry."
        elif any(k in tl for k in ("phone", "pixel", "laptop", "gadget", "apple", "camera")):
            claim_text = f"{topic} is characterized by modern hardware engineering and user experience benchmarks."
        else:
            claim_text = f"{topic} remains an important subject of study and contemporary analysis."
        rows.append(
            {
                "id": "T01",
                "claim": claim_text,
                "evidence": "evergreen",
                "source": "channel_evergreen",
                "confidence": 0.65,
                "freshness": "evergreen",
            }
        )
    return {
        "topic": topic,
        "version": "v0",
        "claims": rows,
        "unknowns": [],
    }


def claim_allowed(text: str, fact_pack: Dict[str, Any], *, min_overlap: float = 0.2) -> Dict[str, Any]:
    """Hallucination barrier: factual sentence should overlap a FactPack claim."""
    t = (text or "").strip()
    if not t:
        return {"allowed": False, "verdict": "FAIL", "reason": "empty"}
    # Soft allow questions / transitions
    if t.endswith("?") or t.lower().startswith(("tonight", "if this", "stay with")):
        return {"allowed": True, "verdict": "PASS", "reason": "non_claim_or_hook"}
    toks = set(re.findall(r"[a-z0-9\u0980-\u09FF]{3,}", t.lower()))
    best = 0.0
    best_id = ""
    for c in fact_pack.get("claims") or []:
        ct = set(re.findall(r"[a-z0-9\u0980-\u09FF]{3,}", str(c.get("claim") or "").lower()))
        if not ct:
            continue
        ov = len(toks & ct) / float(len(toks) or 1)
        if ov > best:
            best = ov
            best_id = str(c.get("id") or "")
    if best >= min_overlap:
        return {"allowed": True, "verdict": "PASS", "claim_id": best_id, "overlap": round(best, 3)}
    return {
        "allowed": False,
        "verdict": "UNKNOWN",
        "reason": "outside_fact_pack",
        "overlap": round(best, 3),
    }


def save_fact_pack(work_dir: Path, pack: Dict[str, Any]) -> Path:
    path = Path(work_dir) / "FACT_PACK.json"
    path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
