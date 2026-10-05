"""Production helpers: apply montage brain + prefer retrieved stock before Agnes."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.montage_brain.discipline import (
    MONTAGE_BRAIN_VERSION,
    montage_compose_checklist,
    montage_stage_manifest,
)
from pipeline.montage_brain.slot_planner import enrich_plan_with_montage_slots, slot_search_queries_for_scene

logger = logging.getLogger(__name__)


def apply_montage_brain_to_plan(
    plan: Dict[str, Any] | None,
    *,
    video_type: str = "short",
) -> Dict[str, Any]:
    """Enrich plan with stage manifest + concrete slots + compose checklist."""
    plan = enrich_plan_with_montage_slots(dict(plan or {}))
    plan["montage_manifest"] = montage_stage_manifest(video_type=video_type or str(plan.get("video_type") or "short"))
    checklist = montage_compose_checklist(plan)
    plan["montage_checklist"] = checklist
    meta = dict(plan.get("metadata") or {})
    meta["montage_brain"] = {
        "version": MONTAGE_BRAIN_VERSION,
        "checklist_ok": checklist.get("ok"),
        "openmontage_agpl_imported": False,
    }
    plan["metadata"] = meta
    return plan


def prefer_retrieved_stock_for_scene(
    *,
    work: Path,
    idx: int,
    scene: Dict[str, Any],
    topic: str = "",
    pexels_api: str = "",
    size: str = "1080x1920",
    customer_id: str = "",
    channel_id: str = "",
) -> Optional[Path]:
    """
    Try AMP retrieval (Pexels/local) using montage slot queries BEFORE Agnes.
    Returns a downloaded video path if a usable stock clip is found; else None.
    Never imports OpenMontage AGPL.
    """
    work = Path(work)
    queries = slot_search_queries_for_scene(scene, topic=topic)
    if not queries:
        return None

    # Fast path: direct Pexels using slot queries (retrieval-first documentary style)
    if pexels_api:
        try:
            from pipeline.ai_providers import fetch_pexels_videos, download_file

            orient = (
                "portrait"
                if "x" in size and int(size.split("x")[1]) > int(size.split("x")[0])
                else "landscape"
            )
            for qi, q in enumerate(queries[:3]):
                urls = fetch_pexels_videos(pexels_api, q, per_page=3, orientation=orient)
                for ui, url in enumerate(urls or []):
                    try:
                        dest = work / f"montage_stock_{idx:02d}_q{qi}_{ui}.mp4"
                        raw = download_file(url, dest)
                        if raw and Path(raw).exists() and Path(raw).stat().st_size > 20000:
                            marker = work / f"scene_{idx:02d}_MONTAGE_STOCK.txt"
                            marker.write_text(
                                f"query={q}\nurl={url}\nbrain={MONTAGE_BRAIN_VERSION}\n",
                                encoding="utf-8",
                            )
                            logger.info(
                                "Scene %s: montage brain stock hit query=%r",
                                idx,
                                q[:80],
                            )
                            return Path(raw)
                    except Exception as exc:
                        logger.debug("montage stock download miss: %s", exc)
        except Exception as exc:
            logger.debug("montage pexels path soft-fail: %s", exc)

    # Structured retrieval evidence (optional; does not block)
    try:
        from pipeline.retrieval.bridge import attach_retrieval_evidence

        beat = {
            "narration": scene.get("narration"),
            "visual_mode": scene.get("visual_mode") or "VIDEO",
            "keyword_triggers": scene.get("keyword_triggers") or [],
            "montage_slot": scene.get("montage_slot") or {},
            "search_queries": queries,
            "subject": topic,
            "action": scene.get("element") or "",
        }
        ev = attach_retrieval_evidence(
            beat,
            index_root=str(work / "retrieval_index"),
            pexels_api_key=pexels_api or "",
            customer_id=customer_id,
            channel_id=channel_id,
            allow_hash_embedder=True,
        )
        (work / f"scene_{idx:02d}_RETRIEVAL_EVIDENCE.json").write_text(
            __import__("json").dumps(ev, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.debug("retrieval evidence soft-fail: %s", exc)

    return None
