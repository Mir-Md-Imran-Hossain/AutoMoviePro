"""Deterministic offline E2E fixture (AMP-004 Phase-09). Real contracts, 0 paid APIs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.idempotency.fingerprint import hash_text
from pipeline.idempotency.mock_render_provider import _minimal_mp4

FIXTURE_TOPIC = "Industrial QA — smartphone camera quality"
FIXTURE_JOB_ID = "amp004-e2e-fixture-v1"
FIXTURE_VERSION = "1.0.0"


def build_e2e_director_plan(*, job_id: str = FIXTURE_JOB_ID) -> dict[str, Any]:
    scenes = [
        {
            "element": "hook",
            "narration": "The iPhone camera now captures cleaner night shots without a bulky cinema rig.",
            "dialogue_id": f"{job_id}-dlg-0",
            "canonical_scene_id": f"{job_id}-scene-0",
            "purpose": "hook: specific camera claim",
            "narrative_role": "hook",
            "shot_type": "close-up",
            "shot_purpose": "pattern_interrupt",
            "transition_intent": "cut",
            "emotional_intent": "serious",
            "keyword_triggers": ["iphone", "camera", "night"],
        },
        {
            "element": "evidence",
            "narration": "Hold the phone steady in the alley while the sensor gathers more light.",
            "dialogue_id": f"{job_id}-dlg-1",
            "canonical_scene_id": f"{job_id}-scene-1",
            "purpose": "evidence: hold phone, describe sensor",
            "narrative_role": "evidence",
            "shot_type": "medium",
            "shot_purpose": "show_claimed_subject",
            "transition_intent": "cut",
            "emotional_intent": "calm",
            "keyword_triggers": ["phone", "sensor", "light"],
        },
        {
            "element": "payoff",
            "narration": "That improvement stays an attribute of the phone camera module, not a separate body.",
            "dialogue_id": f"{job_id}-dlg-2",
            "canonical_scene_id": f"{job_id}-scene-2",
            "purpose": "payoff: attribute ownership",
            "narrative_role": "payoff",
            "shot_type": "medium",
            "shot_purpose": "deliver_payoff",
            "transition_intent": "cut",
            "emotional_intent": "informative",
            "keyword_triggers": ["module", "attribute", "phone"],
        },
    ]
    plan = {
        "topic": FIXTURE_TOPIC,
        "title": "iPhone camera low-light industrial fixture",
        "niche": "gadgets",
        "language": "en",
        "video_type": "short",
        "max_seconds": 45,
        "story_purpose": "Explain phone camera quality without transforming the device",
        "information_objective": FIXTURE_TOPIC,
        "emotional_objective": "serious_informative",
        "scenes": scenes,
        "fixture_version": FIXTURE_VERSION,
        "job_id": job_id,
        "paid_api_required": False,
    }
    plan["plan_fingerprint"] = hash_text(json.dumps(plan, sort_keys=True, ensure_ascii=False))[:24]
    return plan


def materialize_e2e_fixture(work_dir: Path, *, job_id: str = FIXTURE_JOB_ID) -> dict[str, Any]:
    """Write plan + deterministic clips into work_dir.

    When FFmpeg is discoverable, emit real lavfi color clips (A/V streams).
    Otherwise fall back to container-only placeholders (environment-limited).
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    plan = build_e2e_director_plan(job_id=job_id)
    (work_dir / "director_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    use_real = False
    try:
        from pipeline.compose import make_color_clip, probe_media_tool_capability

        cap = probe_media_tool_capability()
        use_real = bool(cap.get("FFMPEG_AVAILABLE"))
    except Exception:
        use_real = False

    clips: list[Path] = []
    duration_sec = 2.0 if use_real else 2.5
    media_kind = "REAL_LAVFI" if use_real else "CONTAINER_PLACEHOLDER"
    for i, sc in enumerate(plan["scenes"]):
        clip = work_dir / f"scene_{i:02d}.mp4"
        if use_real:
            make_color_clip(clip, seconds=duration_sec, size="1080x1920")
            if not clip.is_file() or clip.stat().st_size < 8000:
                _minimal_mp4(clip, size_bytes=12000)
                media_kind = "CONTAINER_PLACEHOLDER_FALLBACK"
        else:
            _minimal_mp4(clip, size_bytes=12000)
        sc["video_path"] = str(clip)
        sc["clip_path"] = str(clip)
        clips.append(clip)
        sid = {
            "job_id": job_id,
            "scene_id": sc["canonical_scene_id"],
            "dialogue_id": sc["dialogue_id"],
            "asset_fingerprint": hash_text(clip.read_bytes().hex()[:64] + sc["canonical_scene_id"])[:16],
        }
        (work_dir / f"scene_{i:02d}.identity.json").write_text(
            json.dumps(sid, indent=2), encoding="utf-8"
        )
    (work_dir / "director_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    srt = work_dir / "master.en.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,500\nThe iPhone camera now captures cleaner night shots.\n\n"
        "2\n00:00:02,500 --> 00:00:05,000\nHold the phone steady in the alley.\n\n"
        "3\n00:00:05,000 --> 00:00:08,000\nThat improvement stays an attribute of the phone camera module.\n",
        encoding="utf-8",
    )
    meta = {
        "job_id": job_id,
        "fixture_version": FIXTURE_VERSION,
        "topic": FIXTURE_TOPIC,
        "plan_path": str(work_dir / "director_plan.json"),
        "clips": [str(c) for c in clips],
        "durations_sec": [duration_sec] * len(clips),
        "subtitle_path": str(srt),
        "scene_ids": [s["canonical_scene_id"] for s in plan["scenes"]],
        "dialogue_ids": [s["dialogue_id"] for s in plan["scenes"]],
        "paid_api_required": False,
        "media_kind": media_kind,
        "render_profile": {"width": 1080, "height": 1920, "fps": 25.0, "size": "1080x1920"},
    }
    (work_dir / "E2E_FIXTURE.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta
