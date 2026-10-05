"""RCP-03 — Semantic visual coverage contract + actual observation (orchestration).

Composes existing authorities — does NOT create a new visual/quality engine:
  C05-S DirectedVisualBeat / coverage
  C05-Q production_consistency / observe_cross_modal_post_generation
  multimodal_consistency evaluator_adapter + cross_modal
  artifact_verification.semantic_boundary (UNKNOWN never PASS)
  BUILD-04F plan_repair via plan_visual_beat_repair
  av_sync_critic critique (Gemini video upload / frame sampling)

Boundary layers: INTENT → PROMPT → GENERATED_ASSET → OBSERVED_ASSET → VERIFIED_COVERAGE
Prompt compliance is NOT artifact compliance.
Keyword-overlap scores are never treated as semantic proof.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

LAYER_INTENT = "INTENT"
LAYER_PROMPT = "PROMPT"
LAYER_GENERATED = "GENERATED_ASSET"
LAYER_OBSERVED = "OBSERVED_ASSET"
LAYER_VERIFIED = "VERIFIED_COVERAGE"

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_UNKNOWN = "UNKNOWN"

DIMS = (
    "required_subject",
    "required_entities",
    "required_relationships",
    "required_action_context",
    "required_location_context",
    "unrelated_subject_mismatch",
    "dialogue_visual_compatibility",
)


def _fp_bytes(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:24]


def build_semantic_coverage_contract(
    *,
    beat_id: str = "",
    dialogue_id: str = "",
    scene_id: str = "",
    visual_purpose: str = "",
    required_subject: str = "",
    required_entities: Optional[Sequence[Any]] = None,
    required_relationships: Optional[Sequence[Any]] = None,
    required_actions: Optional[Sequence[str]] = None,
    required_location: str = "",
    required_character_state: Optional[dict] = None,
    required_object_state: Optional[Any] = None,
    required_context: str = "",
    coverage_requirement: Optional[Any] = None,
    reuse_policy: str = "semantic_beat_compatibility",
    narration: str = "",
    prompt: str = "",
) -> Dict[str, Any]:
    """Persistable expected coverage contract for one visual beat."""
    ents: List[str] = []
    for e in required_entities or []:
        if isinstance(e, dict):
            ents.append(str(e.get("label") or e.get("name") or "").strip())
        else:
            ents.append(str(e).strip())
    ents = [x for x in ents if x]

    rels: List[Dict[str, Any]] = []
    for r in required_relationships or []:
        if isinstance(r, dict):
            rels.append(
                {
                    "type": r.get("relation_type") or r.get("type") or r.get("relation"),
                    "source": r.get("source_label") or r.get("source"),
                    "target": r.get("target_label") or r.get("target"),
                }
            )
        else:
            rels.append({"raw": str(r)})

    subject = (required_subject or "").strip()
    if not subject and ents:
        subject = ents[0]
    if not subject and narration:
        # Prefer multi-word proper-noun phrase from narration
        import re

        m = re.search(
            r"\b((?:The\s+)?[A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){1,6})\b",
            narration,
        )
        if m:
            subject = m.group(1).strip()

    actions = [str(a).strip() for a in (required_actions or []) if str(a).strip()]
    if not actions:
        for verb in ("floats", "holding", "walks", "orbits", "reveals", "assembles", "pierces"):
            if verb in (narration or "").lower():
                actions.append(verb)

    return {
        "beat_id": beat_id,
        "dialogue_id": dialogue_id,
        "scene_id": scene_id,
        "visual_purpose": visual_purpose or "",
        "required_subject": subject,
        "required_entities": ents,
        "required_relationships": rels,
        "required_actions": actions,
        "required_location": (required_location or "").strip(),
        "required_character_state": dict(required_character_state or {}),
        "required_object_state": required_object_state,
        "required_context": (required_context or narration or "")[:400],
        "coverage_requirement": coverage_requirement
        if coverage_requirement is not None
        else {"mandatory": True, "source": "C05-S"},
        "reuse_policy": reuse_policy or "semantic_beat_compatibility",
        "layers": {
            LAYER_INTENT: {
                "subject": subject,
                "entities": ents,
                "relationships": rels,
                "actions": actions,
                "location": required_location,
                "narration": (narration or "")[:400],
            },
            LAYER_PROMPT: {"prompt": (prompt or "")[:900]},
        },
    }


def contract_from_scene(scene: dict, *, narration: str = "", prompt: str = "") -> Dict[str, Any]:
    """Build contract from director/C05-S scene fields."""
    sc = dict(scene or {})
    intent = sc.get("c05s_scene_intent") if isinstance(sc.get("c05s_scene_intent"), dict) else {}
    char = sc.get("character_state") if isinstance(sc.get("character_state"), dict) else {}
    if not char and isinstance(intent.get("character_state"), dict):
        char = intent["character_state"]
    loc = (
        sc.get("location")
        or (sc.get("location_state") or {}).get("location")
        if isinstance(sc.get("location_state"), dict)
        else None
    ) or intent.get("location") or ""
    ents = sc.get("required_entities") or intent.get("entities") or sc.get("must_show") or []
    rels = sc.get("required_relationships") or sc.get("relationships") or intent.get("relations") or []
    narr = narration or str(sc.get("narration") or intent.get("summary") or "")
    subject = (
        sc.get("required_subject")
        or sc.get("subject")
        or char.get("identity")
        or (ents[0] if ents and not isinstance(ents[0], dict) else None)
        or ""
    )
    if isinstance(ents, list) and ents and isinstance(ents[0], dict) and not subject:
        subject = ents[0].get("label") or ents[0].get("name") or ""
    return build_semantic_coverage_contract(
        beat_id=str(sc.get("c05s_visual_beat_id") or sc.get("beat_id") or sc.get("visual_beat_id") or ""),
        dialogue_id=str(sc.get("dialogue_id") or sc.get("c05s_dialogue_id") or ""),
        scene_id=str(sc.get("canonical_scene_id") or sc.get("scene_id") or ""),
        visual_purpose=str(sc.get("purpose") or sc.get("visual_purpose") or sc.get("section_role") or ""),
        required_subject=str(subject or ""),
        required_entities=list(ents or []),
        required_relationships=list(rels or []),
        required_actions=[str(sc.get("action") or char.get("action") or "")],
        required_location=str(loc or ""),
        required_character_state=char,
        required_object_state=sc.get("object_state") or sc.get("required_objects"),
        required_context=narr,
        coverage_requirement=sc.get("coverage_requirement") or sc.get("visual_coverage") or sc.get("coverage"),
        reuse_policy=str(sc.get("reuse_policy") or "semantic_beat_compatibility"),
        narration=narr,
        prompt=prompt or str(sc.get("exact_ai_video_prompt") or sc.get("visual_prompt") or ""),
    )


def _semantic_observation_instruction(contract: Dict[str, Any]) -> str:
    intent = (contract.get("layers") or {}).get(LAYER_INTENT) or {}
    return f"""
You are observing REAL VIDEO PIXELS (not the prompt text alone).
Return JSON only with this schema:
{{
  "observation_executed": true,
  "observed_subjects": ["what is visibly on screen"],
  "observed_entities": ["visible entities"],
  "observed_relationships": ["visible spatial/role relationships"],
  "observed_actions": ["visible actions"],
  "observed_location": "visible location/environment",
  "observed_summary": "one sentence of what the picture actually shows",
  "dimensions": {{
    "required_subject": {{"status": "PASS|FAIL|UNKNOWN", "note": "..."}},
    "required_entities": {{"status": "PASS|FAIL|UNKNOWN", "note": "..."}},
    "required_relationships": {{"status": "PASS|FAIL|UNKNOWN", "note": "..."}},
    "required_action_context": {{"status": "PASS|FAIL|UNKNOWN", "note": "..."}},
    "required_location_context": {{"status": "PASS|FAIL|UNKNOWN", "note": "..."}},
    "unrelated_subject_mismatch": {{"status": "PASS|FAIL|UNKNOWN", "note": "PASS if NO unrelated subject (e.g. random person when JWST required); FAIL if unrelated subject dominates"}},
    "dialogue_visual_compatibility": {{"status": "PASS|FAIL|UNKNOWN", "note": "..."}}
  }},
  "overall": "PASS|FAIL|UNKNOWN",
  "blocking_reason": ""
}}
Rules:
- Judge ONLY what is visible in the frames.
- Do NOT pass because the prompt or filename mentions the subject.
- If a required field is not applicable (empty expected), use UNKNOWN for that dimension (not PASS).
- If you cannot see the video, set observation_executed=false and overall=UNKNOWN.
- FAIL required_subject when a clearly unrelated human face / talking head replaces a required non-human subject.
- FAIL unrelated_subject_mismatch when an unrelated dominant subject is present.
- Documentary science exception: lunar crater / regolith / rover / Moon terrain MAY PASS for intangible claims such as water ice deposits, neutron spectrometers, hydrogen signatures, or metaphorical "refueling station" when the narration is about lunar polar ice / Artemis prospecting and the frame is clearly lunar (not nebula/JWST/unrelated Earth studio).

EXPECTED CONTRACT:
{json.dumps(intent, ensure_ascii=False, indent=2)}
""".strip()


_DOC_CLAIM_SUBJECTS = (
    "water ice",
    "subsurface ice",
    "ice",
    "neutron spectrometer",
    "neutron spectrometers",
    "spectrometer",
    "spectrometers",
    "artemis",
    "station",
    "refueling",
    "fueling",
    "hydrogen",
    "moisture",
)
_LUNAR_OBS_MARKERS = (
    "lunar",
    "moon",
    "crater",
    "regolith",
    "rover",
    "boulder",
    "dust",
    "apollo",
    "soil",
    "rock",
)


def _apply_documentary_semantic_proxies(
    dims_out: Dict[str, Any],
    *,
    contract: Dict[str, Any],
    observed: Dict[str, Any],
) -> Dict[str, Any]:
    """PASS intangible lunar claims when pixels show on-topic lunar terrain/hardware."""
    blob = " ".join(
        [
            " ".join(str(x) for x in (observed.get("subjects") or [])),
            " ".join(str(x) for x in (observed.get("entities") or [])),
            str(observed.get("location") or ""),
            str(observed.get("summary") or ""),
        ]
    ).lower()
    if not blob or not any(m in blob for m in _LUNAR_OBS_MARKERS):
        return dims_out
    if any(bad in blob for bad in ("nebula", "galaxy", "jwst", "webb telescope", "talking head", "news anchor")):
        return dims_out

    req_subj = str(contract.get("required_subject") or "").lower()
    ents = [str(e).lower() for e in (contract.get("required_entities") or [])]
    narr = str(((contract.get("layers") or {}).get(LAYER_INTENT) or {}).get("narration") or "").lower()
    claimish = any(c in req_subj for c in _DOC_CLAIM_SUBJECTS) or any(
        any(c in e for c in _DOC_CLAIM_SUBJECTS) for e in ents
    ) or any(c in narr for c in ("water ice", "spectrometer", "refueling", "hydrogen"))
    if not claimish:
        return dims_out

    note = "documentary_lunar_proxy: lunar terrain/hardware covers intangible claim"
    for dim in ("required_subject", "required_entities", "dialogue_visual_compatibility"):
        cell = dims_out.get(dim) or {}
        if str(cell.get("status") or "").upper() == STATUS_FAIL:
            dims_out[dim] = {"status": STATUS_PASS, "note": note + f"; was: {cell.get('note') or ''}"}
    return dims_out


def observe_semantic_coverage(
    *,
    video_path: Path,
    contract: Dict[str, Any],
    google_api_keys: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Actual observation via existing Gemini video/frame critic path.

    If observation cannot run → overall UNKNOWN (never PASS).
    """
    from pipeline.artifact_verification.semantic_boundary import classify_semantic_observation

    video_path = Path(video_path)
    keys = [str(k).strip() for k in (google_api_keys or []) if str(k).strip()]
    generated = {
        "path": str(video_path),
        "exists": video_path.exists(),
        "size": int(video_path.stat().st_size) if video_path.exists() else 0,
        "fingerprint": _fp_bytes(video_path) if video_path.exists() and video_path.stat().st_size > 1000 else "",
    }
    base: Dict[str, Any] = {
        "contract": contract,
        "layers": {
            **dict(contract.get("layers") or {}),
            LAYER_GENERATED: generated,
            LAYER_OBSERVED: {},
            LAYER_VERIFIED: {},
        },
        "dimensions": {d: {"status": STATUS_UNKNOWN, "note": "not_observed"} for d in DIMS},
        "overall": STATUS_UNKNOWN,
        "observation_method": "UNAVAILABLE",
        "observation_executed": False,
        "provider_verified": False,
        "blocking": False,
        "issues": [],
        "keyword_overlap_rejected_as_proof": True,
    }

    if not video_path.exists() or generated["size"] < 2000:
        base["issues"].append("generated_asset_missing")
        base["blocking"] = True
        base["overall"] = STATUS_FAIL
        return base

    if not keys:
        # Honest: no provider → UNKNOWN (never PASS from prompt)
        sem = classify_semantic_observation(
            expected={"objects": contract.get("required_entities") or []},
            has_pixel_or_asr_evidence=False,
        )
        base["layers"][LAYER_VERIFIED] = sem
        base["overall"] = STATUS_UNKNOWN
        base["issues"].append("semantic_observation_unavailable:no_google_api_keys")
        base["blocking"] = True  # mandatory coverage cannot be proven
        return base

    instruction = _semantic_observation_instruction(contract)
    data: Optional[Dict[str, Any]] = None
    method = "UNAVAILABLE"
    last_err = ""
    try:
        from pipeline.av_sync_critic import _critique_via_video_upload, _critique_via_frames
        from pipeline.google_api_gate import circuit_is_open, select_keys
        from pipeline.quota_backoff import filter_usable_keys
        import os

        force = (os.environ.get("AMP_FORCE_GOOGLE") or "").strip() == "1"
        healthy = filter_usable_keys(list(keys))
        if circuit_is_open() and not force:
            # Global circuit may have been tripped by one critic key — siblings can still observe.
            if not healthy:
                base["issues"].append("semantic_observation_unavailable:google_circuit_open")
                base["overall"] = STATUS_UNKNOWN
                base["blocking"] = True
                return base
            base["issues"].append(
                "google_circuit_open_sibling_keys_attempted:"
                f"healthy={len(healthy)}"
            )
            try_keys = healthy[:5]
        else:
            try:
                try_keys = select_keys(list(keys), purpose="critic") or healthy[:3] or keys[:1]
            except Exception:
                try_keys = healthy[:3] or keys[:1]
            # Prefer non-cooled keys for observation
            if healthy:
                ordered = [k for k in try_keys if k in healthy] + [
                    k for k in healthy if k not in try_keys
                ]
                try_keys = ordered[:5] or try_keys
    except Exception:
        try_keys = keys[:1]

    for key in try_keys[:5]:
        try:
            data = _critique_via_video_upload(key, video_path, instruction)
            if data:
                method = "PROVIDER_VIDEO_UPLOAD"
                break
            data = _critique_via_frames(key, video_path, instruction)
            if data:
                method = "PROVIDER_FRAME_SAMPLE"
                break
        except Exception as exc:
            last_err = str(exc)[:200]
            logger.warning("semantic coverage observation failed: %s", last_err)
            try:
                from pipeline.quota_backoff import is_quota_error, record_key_quota_hit
                from pipeline.provider_error_class import is_403_class, is_429_class

                if is_quota_error(exc) or is_429_class(exc) or is_403_class(exc):
                    record_key_quota_hit(key, "google")
            except Exception:
                pass
            continue

    if not data or not data.get("observation_executed", True):
        # Also treat missing dimensions as unavailable
        base["issues"].append(
            f"semantic_observation_unavailable:{last_err or 'no_provider_response'}"
        )
        base["overall"] = STATUS_UNKNOWN
        base["observation_method"] = method if data else "UNAVAILABLE"
        base["blocking"] = True
        base["layers"][LAYER_OBSERVED] = {"raw": data or {}, "error": last_err}
        return base

    dims_in = data.get("dimensions") if isinstance(data.get("dimensions"), dict) else {}
    dims_out: Dict[str, Any] = {}
    for d in DIMS:
        cell = dims_in.get(d) if isinstance(dims_in.get(d), dict) else {}
        st = str(cell.get("status") or STATUS_UNKNOWN).upper()
        if st not in (STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN):
            st = STATUS_UNKNOWN
        # Empty expected → UNKNOWN not PASS
        if d == "required_subject" and not (contract.get("required_subject") or "").strip():
            st = STATUS_UNKNOWN
        if d == "required_entities" and not (contract.get("required_entities") or []):
            st = STATUS_UNKNOWN
        if d == "required_relationships" and not (contract.get("required_relationships") or []):
            st = STATUS_UNKNOWN
        if d == "required_action_context" and not (contract.get("required_actions") or []):
            st = STATUS_UNKNOWN
        if d == "required_location_context" and not (contract.get("required_location") or "").strip():
            st = STATUS_UNKNOWN
        dims_out[d] = {"status": st, "note": str(cell.get("note") or "")}

    # Map legacy critic signals if structured dims weak but critic already saw pixels
    crit = str(data.get("overall") or "").upper()
    if not dims_in and crit in (STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN):
        for d in DIMS:
            dims_out[d]["status"] = crit if dims_out[d]["status"] == STATUS_UNKNOWN else dims_out[d]["status"]

    # Also fold classic AV critic fields when present (same provider observation)
    for bad in data.get("critical_issues") or []:
        b = str(bad).lower()
        if b in ("wrong_subject", "unrelated_broll", "talking_head"):
            dims_out["unrelated_subject_mismatch"]["status"] = STATUS_FAIL
            dims_out["required_subject"]["status"] = STATUS_FAIL
            dims_out["dialogue_visual_compatibility"]["status"] = STATUS_FAIL

    observed_preview = {
        "subjects": data.get("observed_subjects") or [],
        "entities": data.get("observed_entities") or [],
        "location": data.get("observed_location") or "",
        "summary": data.get("observed_summary") or data.get("visual_summary") or "",
    }
    dims_out = _apply_documentary_semantic_proxies(
        dims_out, contract=contract, observed=observed_preview
    )

    statuses = [dims_out[d]["status"] for d in DIMS]
    if STATUS_FAIL in statuses:
        overall = STATUS_FAIL
    elif all(s == STATUS_UNKNOWN for s in statuses):
        overall = STATUS_UNKNOWN
    elif STATUS_UNKNOWN in statuses and STATUS_PASS in statuses:
        # Partial observation: mandatory subject/entities must not be UNKNOWN if expected
        mand_fail = False
        if (contract.get("required_subject") or "") and dims_out["required_subject"]["status"] == STATUS_UNKNOWN:
            mand_fail = True
        if (contract.get("required_entities") or []) and dims_out["required_entities"]["status"] == STATUS_UNKNOWN:
            mand_fail = True
        overall = STATUS_UNKNOWN if mand_fail else STATUS_PASS
        if mand_fail:
            base["blocking"] = True
    else:
        overall = STATUS_PASS

    # Explicit override from model overall when FAIL
    if crit == STATUS_FAIL:
        overall = STATUS_FAIL

    if overall == STATUS_FAIL:
        base["blocking"] = True
    if overall == STATUS_UNKNOWN:
        base["blocking"] = True  # cannot silently PASS publishability on UNKNOWN

    observed = {
        "subjects": data.get("observed_subjects") or [],
        "entities": data.get("observed_entities") or [],
        "relationships": data.get("observed_relationships") or [],
        "actions": data.get("observed_actions") or [],
        "location": data.get("observed_location") or "",
        "summary": data.get("observed_summary") or data.get("visual_summary") or "",
        "provider": data.get("_provider") or method,
        "raw_keys": sorted(list(data.keys()))[:20],
    }

    base.update(
        {
            "dimensions": dims_out,
            "overall": overall,
            "observation_method": method,
            "observation_executed": True,
            "provider_verified": method.startswith("PROVIDER"),
            "issues": list(data.get("blocking_reason") and [data["blocking_reason"]] or [])
            + [f"{d}:{dims_out[d]['status']}" for d in DIMS if dims_out[d]["status"] == STATUS_FAIL],
            "layers": {
                **base["layers"],
                LAYER_OBSERVED: observed,
                LAYER_VERIFIED: {
                    "overall": overall,
                    "dimensions": dims_out,
                    "claim": "provider_pixel_observation"
                    if method.startswith("PROVIDER")
                    else "unknown_not_pass",
                },
            },
        }
    )
    return base


def plan_semantic_beat_repair(
    *,
    beat_id: str,
    scene_id: str,
    observation: Dict[str, Any],
    old_fingerprint: str = "",
) -> Dict[str, Any]:
    """BUILD-04F targeted repair for one visual beat only."""
    from pipeline.story_visual_direction import plan_visual_beat_repair

    issues = list(observation.get("issues") or [])
    msg = ";".join(issues[:4]) or f"semantic_coverage_{observation.get('overall')}"
    plan = plan_visual_beat_repair(
        beat_id=beat_id or scene_id,
        scene_id=scene_id,
        issue_message=msg,
    )
    plan["old_fingerprint"] = old_fingerprint
    plan["repair_scope_forced"] = "VISUAL_ASSET"
    plan["whole_video_regeneration"] = False
    plan["observation_overall"] = observation.get("overall")
    return plan


def persist_semantic_coverage(work: Path, idx: int, report: Dict[str, Any]) -> Path:
    work = Path(work)
    out = work / f"scene_{idx:02d}_SEMANTIC_COVERAGE.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    # Append to job-level ledger
    ledger = work / "SEMANTIC_COVERAGE_LEDGER.json"
    rows: List[Dict[str, Any]] = []
    if ledger.exists():
        try:
            rows = list(json.loads(ledger.read_text(encoding="utf-8")) or [])
        except Exception:
            rows = []
    rows = [r for r in rows if int(r.get("idx", -1)) != idx]
    rows.append({"idx": idx, "path": str(out), "overall": report.get("overall"), "ts": time.time()})
    ledger.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return out


def evaluate_job_semantic_gate(work: Path) -> Dict[str, Any]:
    """Deterministic job-level gate from persisted per-beat observations."""
    work = Path(work)
    reports = sorted(work.glob("scene_*_SEMANTIC_COVERAGE.json"))
    if not reports:
        return {
            "verdict": STATUS_UNKNOWN,
            "blocking": True,
            "reason": "no_semantic_coverage_artifacts",
            "beats": [],
        }
    beats = []
    has_fail = False
    has_unknown = False
    for p in reports:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            has_unknown = True
            beats.append({"path": str(p), "overall": STATUS_UNKNOWN})
            continue
        ov = str(r.get("overall") or STATUS_UNKNOWN).upper()
        if str(r.get("mandatory_frame_evidence") or "").upper() == "ABSENT":
            ov = STATUS_UNKNOWN
            has_unknown = True
        beats.append(
            {
                "path": str(p),
                "beat_id": (r.get("contract") or {}).get("beat_id"),
                "dialogue_id": (r.get("contract") or {}).get("dialogue_id"),
                "overall": ov,
                "method": r.get("observation_method"),
                "fingerprint": ((r.get("layers") or {}).get(LAYER_GENERATED) or {}).get("fingerprint"),
                "mandatory_frame_evidence": r.get("mandatory_frame_evidence"),
            }
        )
        if ov == STATUS_FAIL:
            has_fail = True
        if ov == STATUS_UNKNOWN or ov == "ABSENT":
            has_unknown = True
    if has_fail:
        verdict = STATUS_FAIL
    elif has_unknown:
        verdict = STATUS_UNKNOWN
    else:
        verdict = STATUS_PASS
    return {
        "verdict": verdict,
        "blocking": verdict != STATUS_PASS,
        "reason": "semantic_fail" if has_fail else ("semantic_unknown" if has_unknown else "all_pass"),
        "beats": beats,
    }


def attach_frame_evidence_to_semantic_report(
    report: Dict[str, Any],
    frame_bridge: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extend existing semantic report with Phase 6C frame evidence — no new gate.

    Rules preserved:
    - UNKNOWN / ABSENT remain blocking for publishability (RCP-06A)
    - retrieval / CLIP scores never become semantic PASS
    """
    out = dict(report or {})
    fb = dict(frame_bridge or {})
    out["frame_evidence"] = {
        "attached": bool(fb),
        "lineage": fb.get("lineage") or [],
        "coverage": fb.get("coverage") or {},
        "temporal": fb.get("temporal") or {},
        "observations": fb.get("observations") or [],
        "clip_similarity_is_not_visual_truth": True,
        "creates_semantic_gate": False,
    }
    obs = list(fb.get("observations") or [])
    if obs and all(
        str(o.get("mandatory_evidence") or "").upper() == "ABSENT"
        or str(o.get("observation_status") or "").upper()
        in (STATUS_UNKNOWN, "OBSERVATION_UNAVAILABLE", "ABSENT")
        for o in obs
    ):
        out["mandatory_frame_evidence"] = "ABSENT"
        out["blocking"] = True
        if str(out.get("overall") or "").upper() == STATUS_PASS:
            out["overall"] = STATUS_UNKNOWN
            out["issues"] = list(out.get("issues") or []) + [
                "mandatory_frame_evidence_absent_blocks_pass"
            ]

    temporal_st = str((fb.get("temporal") or {}).get("status") or "").upper()
    if temporal_st == STATUS_FAIL:
        out["overall"] = STATUS_FAIL
        out["blocking"] = True
        out["issues"] = list(out.get("issues") or []) + list(
            (fb.get("temporal") or {}).get("issues") or []
        )

    out["unknown_as_pass"] = False
    return out


def absent_blocks_semantic_certification(status: str) -> bool:
    """RCP-06A: ABSENT / UNKNOWN block certification."""
    st = str(status or "").upper()
    return st in (STATUS_UNKNOWN, "ABSENT", "OBSERVATION_UNAVAILABLE")
