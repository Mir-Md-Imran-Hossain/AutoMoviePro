"""Actual frame observation — reuses RCP-03 Gemini path; never spends API in fixture mode."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, Sequence

from pipeline.observation.common import (
    STATUS_ABSENT,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNKNOWN,
    STATUS_UNAVAILABLE,
)
from pipeline.observation.frame_evidence.contract import empty_frame_evidence, normalize_observation_status
from pipeline.retrieval.common import strip_secrets

logger = logging.getLogger(__name__)


def _heuristic_from_caption(
    *,
    frame_meta: dict[str, Any],
    expected: dict[str, Any],
    caption: str,
) -> dict[str, Any]:
    """Test/fixture only — HEURISTIC, never provider_verified."""
    cap = (caption or "").lower()
    subj = str(expected.get("subject") or "").strip()
    ents = [str(e).lower() for e in (expected.get("entities") or []) if str(e).strip()]
    loc = str(expected.get("location") or "").strip().lower()
    rels = [str(r).lower() for r in (expected.get("relationships") or []) if str(r).strip()]

    observed_subjects = [subj] if subj and subj.lower() in cap else []
    observed_entities = [e for e in ents if e in cap]
    observed_location = loc if loc and any(t in cap for t in loc.split() if len(t) > 2) else ""
    observed_relationships = [r for r in rels if all(t in cap for t in r.split() if len(t) > 3)]

    ev = empty_frame_evidence(
        asset_id=str(frame_meta.get("asset_id") or ""),
        scene_id=str(frame_meta.get("scene_id") or ""),
        beat_id=str(frame_meta.get("beat_id") or ""),
        timestamp=float(frame_meta.get("timestamp") or 0),
        frame_path=str(frame_meta.get("frame_path") or ""),
        status=STATUS_UNKNOWN,
        provider="heuristic_caption_fixture",
        evidence_source="HEURISTIC",
    )
    ev.update(
        {
            "observed_subjects": observed_subjects,
            "observed_entities": observed_entities,
            "observed_relationships": observed_relationships,
            "observed_location": observed_location,
            "observed_actions": [],
            "observed_environment": str(expected.get("environment") or ""),
            "camera_observation": str(expected.get("camera") or ""),
            "lighting_observation": str(expected.get("lighting") or ""),
            "confidence": "HEURISTIC",
            "heuristic": True,
            "provider_verified": False,
            "observation_status": STATUS_UNKNOWN,  # HEURISTIC never PASS
            "note": "heuristic_never_provider_verified_never_semantic_pass",
        }
    )
    return strip_secrets(ev)


def observe_frame(
    frame_meta: dict[str, Any],
    *,
    expected: Optional[dict[str, Any]] = None,
    google_api_keys: Optional[Sequence[str]] = None,
    allow_heuristic_fixture: bool = False,
    fixture_caption: str = "",
) -> dict[str, Any]:
    """
    Observe one sampled frame.
    Provider path reuses existing Gemini frame bytes pattern via av_sync_critic helpers
    only when keys present. Phase 6C tests set paid APIs = 0 → UNKNOWN without keys.
    """
    expected = dict(expected or {})
    path = Path(str(frame_meta.get("frame_path") or ""))
    base = empty_frame_evidence(
        asset_id=str(frame_meta.get("asset_id") or ""),
        scene_id=str(frame_meta.get("scene_id") or ""),
        beat_id=str(frame_meta.get("beat_id") or ""),
        timestamp=float(frame_meta.get("timestamp") or 0),
        frame_path=str(path),
        status=STATUS_UNKNOWN,
    )
    if not path.exists():
        base["observation_status"] = STATUS_UNAVAILABLE
        base["reason"] = "missing_frame_path"
        base["issues"] = ["observation_unavailable:missing_frame"]
        return base

    keys = [str(k).strip() for k in (google_api_keys or []) if str(k).strip()]
    if not keys:
        if allow_heuristic_fixture:
            return _heuristic_from_caption(
                frame_meta=frame_meta, expected=expected, caption=fixture_caption or path.stem
            )
        base["observation_status"] = STATUS_UNKNOWN
        base["reason"] = "no_google_api_keys"
        base["issues"] = ["semantic_observation_unavailable:no_google_api_keys"]
        base["evidence_source"] = "UNAVAILABLE"
        # Missing mandatory expected fields → ABSENT signal for publishability bridge
        if expected.get("subject") or expected.get("entities"):
            base["mandatory_evidence"] = STATUS_ABSENT
        return base

    # Provider path — Google vision DISABLED by default (translate/localize-only policy).
    # Opt-in: AMP_ALLOW_GOOGLE_FRAME_OBSERVE=1
    import os

    if (os.environ.get("AMP_ALLOW_GOOGLE_FRAME_OBSERVE") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        base["observation_status"] = STATUS_UNKNOWN
        base["observation_executed"] = True
        base["provider"] = "SKIPPED_GOOGLE_POLICY"
        return base

    try:
        from google import genai
        from google.genai import types
        from pipeline.av_sync_critic import CRITIC_MODELS
        from pipeline.google_api_gate import circuit_is_open

        if circuit_is_open():
            base["observation_status"] = STATUS_UNKNOWN
            base["provider"] = "GOOGLE_CIRCUIT_OPEN"
            return base

        instruction = (
            "Return JSON only with keys: observed_subjects, observed_entities, "
            "observed_relationships, observed_location, observed_actions, "
            "observed_environment, camera_observation, lighting_observation, "
            "observation_status (PASS|FAIL|UNKNOWN), observation_executed. "
            f"EXPECTED={expected}"
        )
        data = None
        provider = ""
        for key in keys[:2]:
            client = genai.Client(api_key=key)
            parts = [
                types.Part.from_bytes(data=path.read_bytes(), mime_type="image/jpeg"),
                types.Part.from_text(text=instruction),
            ]
            for model in CRITIC_MODELS[:2]:
                try:
                    resp = client.models.generate_content(
                        model=model,
                        contents=[types.Content(role="user", parts=parts)],
                        config=types.GenerateContentConfig(response_mime_type="application/json"),
                    )
                    import json
                    from pipeline.av_sync_critic import _extract_json

                    text = getattr(resp, "text", None) or str(resp)
                    data = json.loads(_extract_json(text))
                    provider = f"PROVIDER_FRAME:{model}"
                    break
                except Exception as exc:
                    logger.debug("frame observe model fail: %s", exc)
                    continue
            if data:
                break
        if not data:
            base["observation_status"] = STATUS_UNKNOWN
            base["reason"] = "provider_no_response"
            return base
        st = normalize_observation_status(str(data.get("observation_status") or STATUS_UNKNOWN))
        base.update(
            {
                "observation_status": st,
                "provider": provider,
                "provider_verified": True,
                "heuristic": False,
                "evidence_source": "PROVIDER_VERIFIED",
                "observed_subjects": list(data.get("observed_subjects") or []),
                "observed_entities": list(data.get("observed_entities") or []),
                "observed_relationships": list(data.get("observed_relationships") or []),
                "observed_location": str(data.get("observed_location") or ""),
                "observed_actions": list(data.get("observed_actions") or []),
                "observed_environment": str(data.get("observed_environment") or ""),
                "camera_observation": str(data.get("camera_observation") or ""),
                "lighting_observation": str(data.get("lighting_observation") or ""),
                "confidence": "PROVIDER",
                "observation_executed": bool(data.get("observation_executed", True)),
            }
        )
        return strip_secrets(base)
    except Exception as exc:
        base["observation_status"] = STATUS_UNKNOWN
        base["reason"] = f"provider_error:{exc}"[:200]
        return base


def observe_frames(
    frames: Sequence[dict[str, Any]],
    *,
    expected: Optional[dict[str, Any]] = None,
    google_api_keys: Optional[Sequence[str]] = None,
    allow_heuristic_fixture: bool = False,
    fixture_caption: str = "",
) -> list[dict[str, Any]]:
    return [
        observe_frame(
            f,
            expected=expected,
            google_api_keys=google_api_keys,
            allow_heuristic_fixture=allow_heuristic_fixture,
            fixture_caption=fixture_caption,
        )
        for f in (frames or [])
    ]
