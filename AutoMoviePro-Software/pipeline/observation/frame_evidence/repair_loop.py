"""Controlled FAIL → BUILD-04F → BUILD-03 targeted VISUAL_ASSET → re-observe.

Orchestrates existing authorities only — does not implement a repair engine.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from pipeline.observation.common import STATUS_FAIL, STATUS_UNKNOWN
from pipeline.observation.frame_evidence.observe import observe_frame
from pipeline.observation.frame_evidence.repair_hook import repair_handoff_from_frame_evidence
from pipeline.observation.frame_sampling import sample_frames
from pipeline.retrieval.common import content_hash_file, strip_secrets


def execute_targeted_visual_asset_repair_loop(
    *,
    work_dir: Path | str,
    beat_id: str,
    scene_id: str,
    old_asset_path: Path | str,
    fail_bridge_or_temporal: Mapping[str, Any],
    repair_prompt: str,
    customer_id: str = "",
    channel_id: str = "",
    google_api_keys: Optional[Sequence[str]] = None,
    pollinations_key: str = "",
    max_repair_attempts: int = 1,
    duration_sec: float = 3.0,
    size: str = "1080x1920",
    provider_fn: Optional[Callable[[], Path]] = None,
) -> dict[str, Any]:
    """
    1) BUILD-04F VISUAL_ASSET handoff
    2) Existing BUILD-03 idempotent image/clip generation (targeted)
    3) LIVE re-observation of new asset

    If generation cannot run safely → execution NOT_CERTIFIED (handoff still recorded).
    """
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    old_path = Path(old_asset_path)
    old_hash = content_hash_file(old_path) if old_path.is_file() else ""

    handoff = repair_handoff_from_frame_evidence(
        beat_id=beat_id,
        scene_id=scene_id,
        frame_bridge_or_temporal=fail_bridge_or_temporal,
        old_fingerprint=old_hash[:24],
    )
    if not handoff.get("repair_triggered"):
        return strip_secrets(
            {
                "execution": "NOT_ATTEMPTED",
                "reason": "handoff_did_not_trigger",
                "handoff": handoff,
                "whole_video_regeneration": False,
            }
        )
    if handoff.get("repair_scope") != "VISUAL_ASSET":
        return strip_secrets(
            {
                "execution": "REJECTED",
                "reason": "non_visual_asset_scope",
                "handoff": handoff,
                "whole_video_regeneration": False,
            }
        )
    if int(max_repair_attempts) != 1:
        max_repair_attempts = 1  # bounded — no infinite loop

    out_path = work / f"repair_{scene_id}_{beat_id}_a1.mp4"
    lineage = {
        "old_asset_path": str(old_path),
        "old_content_hash": old_hash,
        "beat_id": beat_id,
        "scene_id": scene_id,
        "customer_id": customer_id,
        "channel_id": channel_id,
        "repair_prompt": (repair_prompt or "")[:400],
    }

    # Prefer caller provider_fn; else existing fallback_image_video via BUILD-03
    try:
        from pipeline.generation_payload import idempotent_image_clip_via_build03
        from pipeline.idempotency.visual_request import VisualRequestSpec
    except Exception as exc:
        return strip_secrets(
            {
                "execution": "NOT_CERTIFIED",
                "reason": f"build03_import_failed:{exc}",
                "handoff": handoff,
                "lineage": lineage,
                "whole_video_regeneration": False,
                "second_repair_engine": False,
            }
        )

    def _default_provider() -> Path:
        from pipeline.fallback_image_video import build_image_video_fallback

        build_image_video_fallback(
            work=work,
            out_path=out_path,
            narration=repair_prompt[:200],
            duration=float(duration_sec),
            size=size,
            audio_path=None,
            base_prompt=repair_prompt,
            keywords=[],
            product_name=beat_id,
            element="repair",
            niche="phase6e",
            pollinations_key=pollinations_key,
            google_api_keys=list(google_api_keys or []),
        )
        return out_path

    pfn = provider_fn or _default_provider
    payload = {
        "job_id": f"phase6e-{beat_id}",
        "customer_id": customer_id,
        "channel_id": channel_id,
        "provider_name": "fallback_image_video",
        "beat_id": beat_id,
        "scene_id": 6 if not str(scene_id).isdigit() else int(scene_id),
        "dialogue_id": f"dlg-{beat_id}",
        "canonical_prompt": repair_prompt,
        "provider_prompt": repair_prompt,
        "visual_mode": "IMAGE",
        "actual_mode": "IMAGE",
        "generation_mode": "IMAGE_GENERATION",
        "semantic_repair": True,
        "adapter": "phase6e_targeted_visual_asset",
    }

    gen: dict[str, Any]
    try:
        # Unique out path + payload fingerprint via BUILD-03
        gen = idempotent_image_clip_via_build03(
            work_dir=work,
            payload=payload,
            out_path=out_path,
            provider_fn=pfn,
            size=size,
            duration_sec=duration_sec,
        )
    except Exception as exc:
        return strip_secrets(
            {
                "execution": "NOT_CERTIFIED",
                "reason": f"generation_failed:{exc}"[:240],
                "handoff": handoff,
                "lineage": lineage,
                "whole_video_regeneration": False,
                "second_repair_engine": False,
                "build03_authority": "pipeline.idempotency.visual_runtime.execute_visual_request",
            }
        )

    new_path = Path(gen.get("path") or out_path)
    if not gen.get("ok") or not new_path.is_file() or new_path.stat().st_size < 1000:
        return strip_secrets(
            {
                "execution": "NOT_CERTIFIED",
                "reason": "repair_asset_missing_or_blocked",
                "generation": {k: gen.get(k) for k in ("ok", "blocked", "blocks", "action", "fingerprint")},
                "handoff": handoff,
                "lineage": lineage,
                "whole_video_regeneration": False,
                "unrelated_assets_regenerated": False,
                "second_repair_engine": False,
            }
        )

    new_hash = content_hash_file(new_path)
    lineage.update(
        {
            "new_asset_path": str(new_path),
            "new_content_hash": new_hash,
            "fingerprint": gen.get("fingerprint"),
            "asset_id": gen.get("asset_id"),
            "build03_action": gen.get("action"),
            "hash_changed": bool(old_hash and new_hash and old_hash != new_hash),
        }
    )

    # Re-observe (LIVE if keys supplied)
    sampled = sample_frames(
        new_path,
        out_dir=work / "repair_frames",
        asset_id=str(gen.get("asset_id") or new_path.name),
        beat_id=beat_id,
        scene_id=scene_id,
        customer_id=customer_id,
        channel_id=channel_id,
        max_samples=3,
    )
    reobs = None
    if sampled.get("frames"):
        reobs = observe_frame(
            sampled["frames"][0],
            expected={"subject": "", "entities": [], "location": ""},
            google_api_keys=list(google_api_keys or []),
            allow_heuristic_fixture=False,
        )

    st = str((reobs or {}).get("observation_status") or STATUS_UNKNOWN).upper()
    if st == "PASS" and not (reobs or {}).get("provider_verified"):
        st = STATUS_UNKNOWN  # never promote heuristic

    (work / "phase6e_repair_lineage.json").write_text(
        json.dumps(strip_secrets({"lineage": lineage, "handoff": handoff, "generation": {
            "ok": gen.get("ok"), "action": gen.get("action"), "fingerprint": gen.get("fingerprint"),
        }}), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return strip_secrets(
        {
            "execution": "EXECUTED",
            "repair_scope": "VISUAL_ASSET",
            "whole_video_regeneration": False,
            "unrelated_assets_regenerated": False,
            "max_repair_attempts": 1,
            "attempts_used": 1,
            "handoff": handoff,
            "lineage": lineage,
            "generation": {
                "ok": gen.get("ok"),
                "action": gen.get("action"),
                "fingerprint": gen.get("fingerprint"),
                "reused": gen.get("reused"),
                "provider_invocations": gen.get("provider_invocations"),
            },
            "reobservation": reobs,
            "reobservation_status": st,
            "build03_authority": "pipeline.idempotency.visual_runtime.execute_visual_request",
            "repair_authority": "BUILD-04F",
            "second_repair_engine": False,
            "unknown_as_pass": False,
            "completed_at": time.time(),
        }
    )
