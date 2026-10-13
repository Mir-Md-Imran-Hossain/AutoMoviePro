"""C05-TRS — Topic → Research → Script → C05-S composition facade (orchestration only).

Reuses sole authorities:
  BUILD-04G intelligence (discovery/research/evidence/ranking/reserve/gate)
  BUILD-03 idempotent script runtime + niche_director
  C05-S story_visual_direction
  domain ScriptPlan (narrative meaning only)

Does NOT: rank, research, duplicate-detect, reserve, generate visuals/TTS/video,
score quality, or repair independently.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from domain.script import ScriptPlan, ScriptPlanBeat
from pipeline.creative_production.script_quality import validate_script_plan_preflight
from pipeline.idempotency.fingerprint import compute_fingerprint, hash_text
from pipeline.intelligence.factpack_gate import validate_fact_pack
from pipeline.intelligence.gate import GateVerdict, evaluate_gate_result
from pipeline.intelligence.research_provider import (
    CAPABILITY_EXTERNAL_LIVE,
    CAPABILITY_LOCAL_FACTPACK,
    CAPABILITY_MOCK,
    classify_research_capability,
    require_external_live_or_block,
)
from pipeline.story_visual_direction import (
    DialogueSegment,
    create_dialogue_segment,
    decompose_dialogue_to_visual_beats,
)
from pipeline.visual_intelligence import create_visual_bible

# Legacy niche_director visual fields — compatibility only, not canonical ownership
LEGACY_VISUAL_PROMPT_FIELDS = frozenset({
    "visual_prompt",
    "exact_ai_video_prompt",
    "visual_query",
})

SECTION_ROLES = ("hook", "context", "development", "reveal", "payoff", "ending", "cta")

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat()


def _fp(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def compute_trs_handoff_fingerprint(
    *,
    topic_fp: str,
    research_fp: str,
    script_fp: str,
    channel_id: int | str = "",
    fmt: str = "LONG",
) -> str:
    return compute_fingerprint(
        job_id=str(channel_id or "trs"),
        stage="c05_trs_handoff",
        entity_id="trs-handoff",
        contract_version="c05trs-1.0.0",
        provider="trs_facade",
        model="compose_only",
        inputs={
            "topic_fp": topic_fp,
            "research_fp": research_fp,
            "script_fp": script_fp,
            "format": fmt,
        },
    )


def map_factpack_status(gate: dict[str, Any] | None) -> str:
    """Map FactPack gate verdict → VALID|INVALID|INSUFFICIENT|CONFLICT|UNKNOWN."""
    g = dict(gate or {})
    v = str(g.get("verdict") or "").upper()
    if v in ("PASS", "OK", "VALID", "RESEARCH_OK"):
        return "VALID"
    if "CONFLICT" in v:
        return "CONFLICT"
    if v in ("RESEARCH_REQUIRED",) or "insufficient" in str(g.get("reason") or "").lower():
        return "INSUFFICIENT"
    if v in ("FAIL", "INVALID", "BLOCKED"):
        return "INVALID"
    if not gate:
        return "UNKNOWN"
    return "UNKNOWN"


def classify_visual_prompt_ownership(scene: dict[str, Any]) -> dict[str, Any]:
    """Identify semantic visual intent vs legacy provider-specific prompt text."""
    s = dict(scene or {})
    legacy = {k: s.get(k) for k in LEGACY_VISUAL_PROMPT_FIELDS if s.get(k)}
    semantic = str(
        s.get("visual_implication")
        or s.get("visual_intent")
        or s.get("visual_emphasis")
        or ""
    ).strip()
    return {
        "semantic_visual_intent": semantic,
        "legacy_provider_prompts": legacy,
        "legacy_fields_present": bool(legacy),
        "canonical_owner": "C05-S DirectedVisualBeat → prompt_compiler",
        "script_owns_provider_visual_prompts": False,
        "ownership": "LEGACY_DEPRECATED" if legacy else "NONE",
        "note": "visual_prompt/exact_ai_video_prompt are compatibility fields, not ScriptPlan authority",
    }


def normalize_niche_plan_to_script_plan(
    plan: dict[str, Any],
    *,
    topic_id: str = "",
    fmt: str = "LONG",
    language: str = "en",
    fact_pack: dict[str, Any] | None = None,
    target_duration_sec: float = 60.0,
) -> ScriptPlan:
    """Normalize niche_director / script runtime output → canonical ScriptPlan.

    Provider-specific visual prompts are moved to legacy_visual_prompts only.
    """
    plan = dict(plan or {})
    try:
        from pipeline.creative_production.script_quality import (
            enforce_dialogue_window_on_plan,
            enforce_opening_hook_on_plan,
            enforce_retention_cadence_on_plan,
        )

        plan = enforce_opening_hook_on_plan(plan)
        plan = enforce_retention_cadence_on_plan(plan)
        plan = enforce_dialogue_window_on_plan(plan)
    except Exception:
        pass
    topic = str(plan.get("topic") or plan.get("title") or plan.get("product") or "").strip()
    scenes = list(plan.get("scenes") or [])
    claims = []
    evidence_refs = []
    if fact_pack:
        for c in fact_pack.get("claims") or []:
            if isinstance(c, dict):
                claims.append(dict(c))
                cid = str(c.get("id") or c.get("claim_id") or "")
                if cid:
                    evidence_refs.append(cid)

    n = max(1, len(scenes))
    roles = list(SECTION_ROLES)
    # adaptive structure: distribute roles across scenes
    if n <= 3:
        assigned = ["hook", "development", "payoff"][:n]
    elif n <= 5:
        assigned = ["hook", "context", "development", "payoff", "ending"][:n]
    else:
        assigned = []
        for i in range(n):
            assigned.append(roles[min(i, len(roles) - 1)] if i < len(roles) else "development")

    beats: list[ScriptPlanBeat] = []
    legacy_prompts: list[dict[str, Any]] = []
    t = 0.0
    per = float(target_duration_sec) / n if n else 4.0

    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        narr = str(scene.get("narration") or scene.get("dialogue") or "").strip()
        ownership = classify_visual_prompt_ownership(scene)
        if ownership["legacy_fields_present"]:
            legacy_prompts.append({
                "scene_index": i,
                "fields": ownership["legacy_provider_prompts"],
                "ownership": "LEGACY_DEPRECATED",
            })
        role = assigned[i] if i < len(assigned) else "development"
        visual_impl = ownership["semantic_visual_intent"] or narr[:120]
        claim_ids = []
        if scene.get("claim_id"):
            claim_ids.append(str(scene["claim_id"]))
        # attach first evidence ref when available (traceability, not fabrication)
        ev_refs = list(claim_ids) or (evidence_refs[:1] if evidence_refs else [])
        beat = ScriptPlanBeat(
            beat_id=str(
                scene.get("dialogue_id")
                or scene.get("id")
                or scene.get("scene_id")
                or f"beat-{i+1}"
            ),
            order=i,
            section_role=role,
            narration=narr,
            speaker=str(scene.get("speaker") or "Narrator"),
            emotion=str(scene.get("emotion") or scene.get("emotional_intent") or ""),
            emotion_intensity=float(scene.get("emotion_intensity") or 0.5),
            action_intent=str(scene.get("action") or scene.get("action_intent") or ""),
            entity_refs=list(scene.get("entities") or scene.get("entity_refs") or []),
            location_ref=str(scene.get("location") or ""),
            temporal_context=str(scene.get("temporal_context") or ""),
            continuity_deps=list(scene.get("continuity_deps") or []),
            visual_implication=visual_impl,
            claim_ids=claim_ids,
            evidence_refs=ev_refs,
            estimated_duration_sec=float(scene.get("duration_sec") or per),
            metadata={
                "legacy_visual_prompt_ownership": ownership,
            },
        )
        beats.append(beat)
        t += beat.estimated_duration_sec

    hook = beats[0].narration if beats else ""
    ending = ""
    payoff = ""
    cta = ""
    for b in beats:
        if b.section_role == "ending":
            ending = b.narration
        if b.section_role == "payoff":
            payoff = b.narration
        if b.section_role == "cta":
            cta = b.narration
    if not ending and beats:
        ending = beats[-1].narration

    return ScriptPlan(
        topic_id=topic_id or str(plan.get("topic_id") or ""),
        topic=topic or "untitled",
        format=(fmt or "LONG").upper(),
        language=language or str(plan.get("language") or "en"),
        target_duration_sec=float(target_duration_sec),
        hook=hook,
        narrative_structure=[b.section_role for b in beats],
        sections=list(dict.fromkeys(b.section_role for b in beats)),
        beats=beats,
        claims=claims,
        evidence_refs=evidence_refs,
        fact_pack_id=str((fact_pack or {}).get("id") or plan.get("fact_pack_id") or ""),
        ending=ending,
        payoff=payoff,
        cta=cta,
        estimated_duration_sec=t,
        legacy_visual_prompts=legacy_prompts,
        metadata={
            "source": "niche_director_normalized",
            "visual_prompt_canonical_owner": "C05-S",
            "script_owns_provider_visual_prompts": False,
            "created_at": _now(),
        },
    )


def script_plan_to_dialogue_segments(
    plan: ScriptPlan,
    *,
    scene_id: str = "sc-1",
) -> list[DialogueSegment]:
    """Map ScriptPlan beats → existing C05-S DialogueSegment (no duplicate class)."""
    segs: list[DialogueSegment] = []
    t = 0.0
    for b in plan.beats:
        dur = float(b.estimated_duration_sec or 4.0)
        seg = create_dialogue_segment(
            segment_id=f"seg-{b.beat_id}",
            dialogue_id=b.beat_id,
            scene_id=scene_id,
            text=b.narration,
            speaker=b.speaker or "Narrator",
            language=plan.language,
            start_sec=t,
            end_sec=t + dur,
            semantic_intent=b.narration[:120],
            semantic_purpose=b.section_role or b.narration[:80],
            actions=[b.action_intent] if b.action_intent else [],
            location=b.location_ref,
            emotional_intent=b.emotion,
            intensity=float(b.emotion_intensity or 0.5),
            evidence_references=list(b.evidence_refs or b.claim_ids or []),
            visual_implication=b.visual_implication,
            temporal_context=b.temporal_context,
            entities=[{"label": e, "entity_type": "object"} for e in (b.entity_refs or [])],
            visual_relevance="high",
        )
        segs.append(seg)
        t += dur
    return segs


def run_topic_research_gate(
    work_dir: Path | str,
    channel: dict[str, Any],
    topic: str,
    *,
    video_type: str = "long",
    blocked_topics: Optional[Sequence[str]] = None,
    use_mock_research: bool | None = True,
    require_external_live: bool = False,
) -> dict[str, Any]:
    """Call existing BUILD-04G intelligence gate — no independent ranking/research."""
    from pipeline.intelligence.bridge import run_intelligence_gate

    work = Path(work_dir)
    try:
        result = run_intelligence_gate(
            work,
            channel,
            topic,
            video_type=video_type,
            blocked_topics=list(blocked_topics or []),
            use_mock_research=use_mock_research,
        )
    except RuntimeError as exc:
        # Preserve fail-closed gate errors (e.g. mock forbidden in production LIVE)
        return {
            "accepted": False,
            "reason": "INTELLIGENCE_GATE_BLOCKED",
            "gate_verdict": GateVerdict.FAIL.value,
            "gate_error": str(exc),
            "topic": topic,
        }
    verdict = evaluate_gate_result(result, context="c05_trs")
    result["gate_verdict"] = verdict.value

    # Research capability honesty
    intel = result.get("intelligence") or {}
    research = {}
    fact_pack = None
    # Pull research from evaluated payload when present
    for ev in intel.get("evaluated") or []:
        if isinstance(ev, dict) and ev.get("research"):
            research = dict(ev.get("research") or {})
            fact_pack = ev.get("fact_pack")
            break
    if not research and result.get("research"):
        research = dict(result.get("research") or {})
    if fact_pack is None:
        fact_pack = result.get("fact_pack")

    cap = classify_research_capability(research)
    result["research_capability"] = cap
    if research:
        research.update(cap)
        result["research"] = research

    ext = require_external_live_or_block(research, require_external=require_external_live)
    result["external_live_requirement"] = ext
    if require_external_live and not ext.get("ok"):
        result["accepted"] = False
        result["reason"] = ext.get("reason") or "external_live_research_unavailable"
        result["gate_verdict"] = GateVerdict.UNKNOWN.value

    fp_gate = validate_fact_pack(fact_pack) if fact_pack else {"verdict": "RESEARCH_REQUIRED", "reason": "missing_fact_pack"}
    result["factpack_gate"] = fp_gate
    result["evidence_status"] = map_factpack_status(fp_gate)
    result["fact_pack"] = fact_pack
    return result


def plan_script_for_trs(
    work_dir: Path | str,
    *,
    job_id: str,
    niche: str,
    channel_name: str,
    topic: str,
    video_type: str = "long",
    max_seconds: int = 60,
    research_notes: str = "",
    use_mock: bool = True,
    channel_specials: Optional[dict[str, str]] = None,
    niche_id: int | None = None,
    blocked_products: Optional[Sequence[str]] = None,
    google_api_keys: Optional[Sequence[str]] = None,
    openrouter_api: str = "",
    openrouter_keys: Optional[Sequence[str]] = None,
    revision_id: str = "",
    plan_filename: str = "director_plan.json",
) -> dict[str, Any]:
    """Existing script authority only — idempotent niche plan (mock/deterministic in tests)."""
    from pipeline.idempotency.script_bridge import idempotent_plan_niche_production

    work = Path(work_dir)
    return idempotent_plan_niche_production(
        work,
        job_id=job_id or work.name,
        niche=niche,
        niche_id=niche_id,
        channel_name=channel_name,
        video_type=video_type,
        topic=topic,
        research_notes=research_notes,
        max_seconds=max_seconds,
        channel_specials=channel_specials,
        blocked_products=list(blocked_products or []),
        google_api_keys=list(google_api_keys or []),
        openrouter_api=openrouter_api or "",
        openrouter_keys=list(openrouter_keys or []),
        use_mock=use_mock,
        revision_id=revision_id,
        plan_filename=plan_filename,
    )


def persist_trs_handoff(work_dir: Path | str, handoff: dict[str, Any]) -> Path:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    path = work / "trs_handoff.json"
    path.write_text(json.dumps(handoff, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def load_trs_handoff(work_dir: Path | str) -> dict[str, Any] | None:
    path = Path(work_dir) / "trs_handoff.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def resolve_canonical_visual_prompt(scene: dict[str, Any], *, narration: str = "") -> dict[str, Any]:
    """Production visual prompt precedence — ContinuityTracker final compile wins.

    Precedence (C05-GA):
      1. Final ContinuityTracker + prompt_compiler output when `_continuity_applied`
      2. `canonical_compiled_positive` (explicit final stamp)
      3. Intermediate C05-S `c05s_compiled_positive` only when continuity has NOT run
      4. LEGACY_COMPAT niche fields
      5. Narration fallback

    Stale C05-S compiled prompts MUST NOT override post-continuity authority.
    """
    sc = dict(scene or {})
    narr = narration or str(sc.get("narration") or "")
    source_flag = str(sc.get("visual_direction_source") or "").upper()
    c05s_pos = str(sc.get("c05s_compiled_positive") or "").strip()
    final_pos = str(sc.get("canonical_compiled_positive") or "").strip()
    compiled = str(sc.get("visual_prompt") or "").strip()
    legacy_exact = str(sc.get("legacy_exact_ai_video_prompt") or "").strip()
    legacy_vis = str(sc.get("legacy_visual_prompt") or "").strip()
    raw_exact = str(sc.get("exact_ai_video_prompt") or "").strip()
    raw_vis = str(sc.get("visual_prompt") or "").strip()
    continuity_done = bool(sc.get("_continuity_applied"))

    # 1–2: Final authoritative compile after ContinuityTracker
    if continuity_done and (final_pos or compiled):
        prompt = final_pos or compiled
        return {
            "prompt": prompt,
            "source": "CONTINUITY_COMPILER",
            "legacy_ignored": True,
            "stale_c05s_ignored": bool(c05s_pos and c05s_pos != prompt),
            "note": "ContinuityTracker + prompt_compiler is final authority after enrichment",
        }
    if final_pos:
        return {
            "prompt": final_pos,
            "source": "CANONICAL_FINAL",
            "legacy_ignored": True,
            "stale_c05s_ignored": bool(c05s_pos and c05s_pos != final_pos),
            "note": "canonical_compiled_positive stamp",
        }
    # 3: Intermediate C05-S only before continuity
    if source_flag == "C05-S" and c05s_pos and not continuity_done:
        return {
            "prompt": c05s_pos,
            "source": "C05-S",
            "legacy_ignored": True,
            "stale_c05s_ignored": False,
            "note": "DirectedVisualBeat intermediate compile (pre-continuity)",
        }
    if source_flag == "C05-S" and compiled and not continuity_done:
        return {
            "prompt": compiled,
            "source": "C05-S",
            "legacy_ignored": True,
            "stale_c05s_ignored": False,
            "note": "scene visual_prompt from C05-S stamp (pre-continuity)",
        }
    # Explicit legacy compatibility only when no C05-S / continuity direction
    if raw_exact or raw_vis or legacy_exact or legacy_vis:
        # Prefer non-legacy keys only when they are not stale C05-S leftovers without authority
        prompt = raw_exact or raw_vis or legacy_exact or legacy_vis
        if source_flag == "C05-S" and c05s_pos and continuity_done and c05s_pos == prompt:
            # Stale path — should have been caught above; force continuity note
            return {
                "prompt": prompt,
                "source": "STALE_C05S_BLOCKED_USE_FINAL",
                "legacy_ignored": True,
                "stale_c05s_ignored": False,
                "note": "unexpected stale state — prefer regenerating via continuity",
            }
        return {
            "prompt": prompt,
            "source": "LEGACY_COMPAT",
            "legacy_ignored": False,
            "stale_c05s_ignored": False,
            "note": "no DirectedVisualBeat — legacy niche visual fields as compatibility fallback",
        }
    return {
        "prompt": narr,
        "source": "NARRATION_FALLBACK",
        "legacy_ignored": False,
        "stale_c05s_ignored": False,
        "note": "no visual direction available",
    }


def apply_c05s_direction_to_director_plan(
    plan: dict[str, Any],
    c05s: dict[str, Any],
    *,
    dialogue_segments: Optional[Sequence[dict[str, Any]]] = None,
    bible: Any = None,
    topic: str = "",
    require_dialogue_id_binding: bool = True,
) -> dict[str, Any]:
    """Stamp C05-S DirectedVisualBeat → SceneIntent onto director plan scenes.

    C05-GA: bind by dialogue_id (primary), beat_id/scene_id secondary — index is
    ordering metadata only. Coverage + timing become first-class handoff fields.
    Legacy visual_prompt / exact_ai_video_prompt are moved aside and MUST NOT override
    canonical compiled direction when visual_direction_source=C05-S.
    """
    from pipeline.story_visual_direction import (
        DirectedVisualBeat,
        compile_beat_prompt,
        dialogue_segment_from_dict,
        visual_beat_to_scene_intent,
    )
    from pipeline.visual_intelligence import create_visual_bible

    out = dict(plan or {})
    scenes = [dict(s) if isinstance(s, dict) else s for s in (out.get("scenes") or [])]
    beats_raw = list((c05s or {}).get("visual_beats") or [])
    segs_raw = list(dialogue_segments or [])
    seg_by_id = {
        str(s.get("segment_id") or ""): dialogue_segment_from_dict(s)
        for s in segs_raw
        if isinstance(s, dict)
    }
    seg_by_dialogue = {
        str(s.get("dialogue_id") or ""): dialogue_segment_from_dict(s)
        for s in segs_raw
        if isinstance(s, dict) and s.get("dialogue_id")
    }

    # Index beats by dialogue_id / beat_id (stable) — index is fallback only
    beats_by_dialogue: dict[str, list[dict[str, Any]]] = {}
    beats_by_id: dict[str, dict[str, Any]] = {}
    for bd in beats_raw:
        if not isinstance(bd, dict):
            continue
        beats_by_id[str(bd.get("beat_id") or "")] = bd
        did = str(bd.get("dialogue_segment_id") or "")
        # dialogue_segment_id on visual beat links to segment; also try dialogue_id on segment
        seg = seg_by_id.get(did)
        dialogue_key = str((seg.dialogue_id if seg else "") or bd.get("dialogue_id") or did)
        if dialogue_key:
            beats_by_dialogue.setdefault(dialogue_key, []).append(bd)

    if bible is None:
        bible = create_visual_bible(
            bible_id=f"vb-trs-pw-{_fp(topic or out.get('topic') or 'x')[:10]}",
            subject_identity=str(topic or out.get("topic") or "subject"),
            character_identity="Narrator subject",
            visual_style="documentary",
            location="studio",
            environment="production set",
        )
    elif isinstance(bible, dict):
        bible = create_visual_bible(**bible)

    compiled_index: list[dict[str, Any]] = []
    binding_issues: list[str] = []
    used_beat_ids: set[str] = set()

    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        # Preserve legacy fields explicitly
        if scene.get("exact_ai_video_prompt") and not scene.get("legacy_exact_ai_video_prompt"):
            scene["legacy_exact_ai_video_prompt"] = scene.get("exact_ai_video_prompt")
        if scene.get("visual_prompt") and not scene.get("legacy_visual_prompt"):
            scene["legacy_visual_prompt"] = scene.get("visual_prompt")

        dialogue_id = str(
            scene.get("dialogue_id")
            or scene.get("c05s_dialogue_id")
            or (segs_raw[i].get("dialogue_id") if i < len(segs_raw) and isinstance(segs_raw[i], dict) else "")
            or ""
        ).strip()
        beat_dict = None
        binding_method = "none"
        if dialogue_id and dialogue_id in beats_by_dialogue:
            candidates = [b for b in beats_by_dialogue[dialogue_id] if str(b.get("beat_id")) not in used_beat_ids]
            beat_dict = candidates[0] if candidates else beats_by_dialogue[dialogue_id][0]
            binding_method = "dialogue_id"
        elif scene.get("c05s_visual_beat_id") and str(scene.get("c05s_visual_beat_id")) in beats_by_id:
            beat_dict = beats_by_id[str(scene.get("c05s_visual_beat_id"))]
            binding_method = "beat_id"
        elif dialogue_id and require_dialogue_id_binding:
            # Explicit dialogue_id present but unbound — do NOT silently steal neighbor via index
            beat_dict = None
            binding_method = "unbound"
            binding_issues.append(f"scene[{i}]:unbound_dialogue_id:{dialogue_id}")
        elif i < len(beats_raw) and isinstance(beats_raw[i], dict):
            # Ordered fallback only when dialogue_id absent
            beat_dict = beats_raw[i]
            binding_method = "index_fallback"
            if require_dialogue_id_binding and not dialogue_id:
                binding_issues.append(f"scene[{i}]:missing_dialogue_id_index_fallback")

        if not beat_dict:
            scene["visual_direction_source"] = scene.get("visual_direction_source") or "LEGACY_COMPAT"
            scene["c05s_binding_method"] = binding_method
            if require_dialogue_id_binding and dialogue_id:
                binding_issues.append(f"scene[{i}]:unbound_dialogue_id:{dialogue_id}")
            scenes[i] = scene
            continue

        beat = DirectedVisualBeat.from_dict(beat_dict)
        used_beat_ids.add(beat.beat_id)
        seg = (
            seg_by_dialogue.get(dialogue_id)
            or seg_by_id.get(beat.dialogue_segment_id)
            or (dialogue_segment_from_dict(segs_raw[i]) if i < len(segs_raw) and isinstance(segs_raw[i], dict) else None)
        )
        if seg is None:
            from pipeline.story_visual_direction import create_dialogue_segment

            seg = create_dialogue_segment(
                segment_id=beat.dialogue_segment_id or f"seg-{i}",
                dialogue_id=dialogue_id or str(scene.get("dialogue_id") or f"dlg-{i}"),
                scene_id=beat.scene_id or f"sc-{i}",
                text=str(scene.get("narration") or ""),
                speaker=str(scene.get("speaker") or "Narrator"),
                location=str((beat.location_state or {}).get("location") or scene.get("location") or ""),
                emotional_intent=str(beat.emotional_visual_intent or scene.get("emotion") or ""),
                start_sec=float(scene.get("start_sec") or 0.0),
                end_sec=float(scene.get("end_sec") or beat.duration_sec or 0.0),
            )
        if not dialogue_id:
            dialogue_id = str(seg.dialogue_id or "").strip()

        compiled = compile_beat_prompt(beat=beat, segment=seg, bible=bible)
        positive = str((compiled.get("compiled") or {}).get("positive") or "").strip()
        intent_dump = compiled.get("intent") or visual_beat_to_scene_intent(beat, seg, bible).model_dump()
        intent_dump = json.loads(json.dumps(intent_dump, default=str))

        cov = beat.coverage.to_dict() if hasattr(beat.coverage, "to_dict") else dict(beat.coverage or {})
        scene["dialogue_id"] = dialogue_id or seg.dialogue_id
        scene["c05s_dialogue_id"] = scene["dialogue_id"]
        scene["c05s_visual_beat_id"] = beat.beat_id
        scene["c05s_narrative_beat_id"] = beat.narrative_beat_id
        scene["c05s_scene_id"] = beat.scene_id
        scene["c05s_binding_method"] = binding_method
        scene["c05s_scene_intent"] = intent_dump
        scene["c05s_compiled_positive"] = positive  # intermediate; continuity may supersede
        scene["c05s_prompt_provenance"] = compiled.get("provenance") or {}
        scene["visual_direction_source"] = "C05-S"
        scene["visual_mode"] = beat.visual_mode
        scene["location"] = (beat.location_state or {}).get("location") or scene.get("location") or ""
        scene["environment"] = (beat.environment_state or {}).get("environment") or scene.get("environment") or ""
        scene["emotional_intent"] = beat.emotional_visual_intent or scene.get("emotional_intent") or ""
        scene["emotion"] = scene.get("emotional_intent")
        scene["emotion_intensity"] = float(getattr(seg, "intensity", None) or scene.get("emotion_intensity") or 0.5)
        scene["speaker_id"] = str(seg.speaker or scene.get("speaker") or "")
        scene["required_objects"] = list(beat.required_objects or [])
        scene["visual_coverage"] = cov
        scene["coverage_overall"] = str(cov.get("overall") or "UNKNOWN")
        scene["visual_timing"] = {
            "start_sec": float(getattr(seg, "start_sec", 0.0) or scene.get("start_sec") or 0.0),
            "end_sec": float(getattr(seg, "end_sec", 0.0) or scene.get("end_sec") or 0.0),
            "duration_sec": float(beat.duration_sec or 0.0),
            "hold_policy": beat.duration_policy,
            "transition_intent": beat.transition_intent,
            "semantic_boundary": True,
            "note": "adaptive_semantic_timing_not_fixed_interval",
        }
        scene["start_sec"] = scene["visual_timing"]["start_sec"]
        scene["end_sec"] = scene["visual_timing"]["end_sec"]
        scene["camera_intent"] = beat.camera_intent
        scene["lighting_intent"] = beat.lighting_intent
        scene["lighting_continuity"] = beat.lighting_continuity
        scene["character_state"] = dict(beat.character_state or {})
        scene["location_state"] = dict(beat.location_state or {})
        scene["environment_state"] = dict(beat.environment_state or {})
        scene["required_relationships"] = [
            r.to_dict() if hasattr(r, "to_dict") else dict(r) for r in (beat.relationships or [])
        ]
        if beat.character_state.get("identity"):
            scene["actors"] = [beat.character_state["identity"]]
        scene["subject"] = (beat.character_state or {}).get("identity") or scene.get("subject") or ""
        if positive:
            scene["visual_prompt"] = positive
            scene["exact_ai_video_prompt"] = positive
        compiled_index.append({
            "scene_index": i,
            "dialogue_id": scene["dialogue_id"],
            "beat_id": beat.beat_id,
            "binding_method": binding_method,
            "source": "C05-S",
            "coverage_overall": scene["coverage_overall"],
            "prompt_fingerprint": (compiled.get("provenance") or {}).get("prompt_fingerprint"),
        })
        scenes[i] = scene

    out["scenes"] = scenes
    out["c05s_visual_direction_applied"] = True
    out["c05s_compiled_index"] = compiled_index
    out["c05s_binding_issues"] = binding_issues
    # C05-MR: first-class beat lists on plan + per-scene dialogue-scoped beats
    all_beats = [dict(b) if isinstance(b, dict) else {} for b in beats_raw]
    out["c05s_visual_beats"] = all_beats
    for i, scene in enumerate(out["scenes"]):
        if not isinstance(scene, dict):
            continue
        did = str(scene.get("dialogue_id") or "")
        candidates = list(beats_by_dialogue.get(did) or [])
        normalized: list[dict[str, Any]] = []
        for bd in candidates:
            b = dict(bd)
            b["dialogue_id"] = did
            b["c05s_visual_beat_id"] = str(b.get("beat_id") or b.get("c05s_visual_beat_id") or "")
            loc_state = b.get("location_state") if isinstance(b.get("location_state"), dict) else {}
            b.setdefault("location", loc_state.get("location") or scene.get("location") or "")
            char_state = b.get("character_state") if isinstance(b.get("character_state"), dict) else {}
            b.setdefault("subject", char_state.get("identity") or scene.get("subject") or "")
            b.setdefault("required_relationships", b.get("relationships") or scene.get("required_relationships") or [])
            b.setdefault("required_objects", b.get("required_objects") or scene.get("required_objects") or [])
            b.setdefault("camera", b.get("camera_intent") or scene.get("camera_intent") or "")
            b.setdefault("lighting", b.get("lighting_intent") or scene.get("lighting_intent") or "")
            cov = b.get("coverage")
            if isinstance(cov, dict):
                b.setdefault("visual_coverage", cov)
            elif hasattr(cov, "to_dict"):
                b.setdefault("visual_coverage", cov.to_dict())
            else:
                b.setdefault("visual_coverage", scene.get("visual_coverage") or {})
            dur = float(b.get("duration_sec") or 0.0)
            b.setdefault(
                "visual_timing",
                {
                    "duration_sec": dur,
                    "start_sec": float(scene.get("start_sec") or 0.0),
                    "end_sec": float(scene.get("end_sec") or 0.0),
                    "transition": b.get("transition_intent") or "cut",
                },
            )
            b.setdefault("scene_id", b.get("scene_id") or scene.get("c05s_scene_id") or i)
            b.setdefault("visual_mode", b.get("visual_mode") or scene.get("visual_mode") or "")
            if b.get("c05s_visual_beat_id"):
                normalized.append(b)
        if not normalized and scene.get("c05s_visual_beat_id"):
            normalized = [
                {
                    "dialogue_id": did,
                    "beat_id": scene.get("c05s_visual_beat_id"),
                    "c05s_visual_beat_id": scene.get("c05s_visual_beat_id"),
                    "visual_mode": scene.get("visual_mode"),
                    "location": scene.get("location"),
                    "subject": scene.get("subject"),
                    "character_state": scene.get("character_state") or {},
                    "required_relationships": scene.get("required_relationships") or [],
                    "required_objects": scene.get("required_objects") or [],
                    "camera": scene.get("camera_intent"),
                    "lighting": scene.get("lighting_intent"),
                    "visual_timing": scene.get("visual_timing") or {},
                    "visual_coverage": scene.get("visual_coverage") or {},
                    "scene_id": scene.get("c05s_scene_id") or i,
                    "transition_intent": (scene.get("visual_timing") or {}).get("transition_intent"),
                }
            ]
        scene["c05s_visual_beats"] = normalized
        out["scenes"][i] = scene
    out["visual_prompt_canonical_owner"] = "C05-S"
    out["generation_alignment"] = {
        "binding_primary_key": "dialogue_id",
        "coverage_first_class": True,
        "timing_first_class": True,
        "index_is_ordering_only": True,
        "beats_first_class_on_scene": True,
    }
    return out


def refresh_c05s_from_director_plan(
    plan: dict[str, Any],
    *,
    channel_id: int | str = 0,
    topic: str = "",
    language: str = "en",
    fmt: str = "LONG",
    max_seconds: float = 60.0,
    fact_pack: dict[str, Any] | None = None,
    prefer_image_fallback: bool = False,
    visual_bible: Any = None,
) -> dict[str, Any]:
    """Re-run C05-S only from an updated director plan (no intelligence / no script provider)."""
    script_plan = normalize_niche_plan_to_script_plan(
        plan,
        topic_id=str(plan.get("topic_id") or ""),
        fmt=fmt,
        language=language,
        fact_pack=fact_pack,
        target_duration_sec=float(max_seconds),
    )
    segments = script_plan_to_dialogue_segments(script_plan, scene_id=f"sc-{channel_id or 1}")
    bible_fields = visual_bible or {
        "bible_id": f"vb-trs-{channel_id or 'x'}",
        "subject_identity": topic or script_plan.topic,
        "character_identity": "Narrator subject",
        "visual_style": "documentary",
        "location": segments[0].location if segments and segments[0].location else "studio",
        "environment": "production set",
    }
    if hasattr(visual_bible, "bible_id"):
        bible = visual_bible
    else:
        bible = create_visual_bible(**(visual_bible if isinstance(visual_bible, dict) else bible_fields))

    c05s = decompose_dialogue_to_visual_beats(
        segments=segments,
        bible=bible,
        prefer_image_fallback=prefer_image_fallback,
    )
    stamped = apply_c05s_direction_to_director_plan(
        plan,
        c05s,
        dialogue_segments=[s.to_dict() for s in segments],
        bible=bible,
        topic=topic or script_plan.topic,
    )
    return {
        "ok": True,
        "script_plan": script_plan.model_dump(),
        "dialogue_segments": [s.to_dict() for s in segments],
        "c05s": c05s,
        "director_plan": stamped,
        "bible": bible.to_dict() if hasattr(bible, "to_dict") else bible_fields,
    }


def assert_generation_alignment_preflight(
    scenes: Sequence[dict[str, Any]] | dict[str, Any],
    *,
    require_dialogue_id: bool = True,
    require_visual_binding: bool = True,
    block_mandatory_coverage_none: bool = True,
    block_mandatory_coverage_unknown: bool = False,
) -> dict[str, Any]:
    """Fail-closed deterministic checks before paid visual/TTS providers (C05-GA)."""
    blocks: list[str] = []
    warnings: list[str] = []
    unknowns: list[str] = []
    rows = scenes.get("scenes") if isinstance(scenes, dict) else scenes
    rows = list(rows or [])
    seen_dialogue: dict[str, int] = {}
    for i, sc in enumerate(rows):
        if not isinstance(sc, dict):
            blocks.append(f"scene[{i}]:not_dict")
            continue
        did = str(sc.get("dialogue_id") or sc.get("c05s_dialogue_id") or "").strip()
        if require_dialogue_id and not did:
            blocks.append(f"scene[{i}]:missing_dialogue_id")
        if did:
            if did in seen_dialogue:
                warnings.append(f"scene[{i}]:duplicate_dialogue_id:{did}")
            seen_dialogue[did] = i
        source = str(sc.get("visual_direction_source") or "").upper()
        if require_visual_binding and source == "C05-S":
            if not sc.get("c05s_visual_beat_id"):
                blocks.append(f"scene[{i}]:missing_visual_beat_binding")
            if not sc.get("c05s_scene_intent") and not sc.get("canonical_compiled_positive") and not sc.get("c05s_compiled_positive"):
                blocks.append(f"scene[{i}]:missing_scene_intent_or_compile")
        cov = sc.get("visual_coverage") if isinstance(sc.get("visual_coverage"), dict) else {}
        overall = str(sc.get("coverage_overall") or cov.get("overall") or "").upper()
        if block_mandatory_coverage_none and overall == "NONE":
            blocks.append(f"scene[{i}]:mandatory_coverage_none")
        if block_mandatory_coverage_unknown and overall == "UNKNOWN":
            blocks.append(f"scene[{i}]:mandatory_coverage_unknown")
            unknowns.append(f"scene[{i}]:coverage_UNKNOWN")
        # Contradictory location vs character wipe heuristics (deterministic markers)
        loc = str(sc.get("location") or "").strip().lower()
        loc_state = sc.get("location_state") if isinstance(sc.get("location_state"), dict) else {}
        if loc and loc_state.get("location") and str(loc_state.get("location")).strip().lower() not in ("", loc):
            if str(loc_state.get("continuity") or "").upper() == "SAME_LOCATION":
                blocks.append(f"scene[{i}]:contradictory_location_same_continuity")
        # Stale prompt detection: continuity applied but resolver would still prefer different stale
        if sc.get("_continuity_applied"):
            final_p = str(sc.get("canonical_compiled_positive") or sc.get("visual_prompt") or "")
            stale = str(sc.get("c05s_intermediate_compiled_positive") or "")
            if stale and final_p and stale == str(sc.get("c05s_compiled_positive") or "") and stale != final_p:
                # intermediate retained — OK if canonical_compiled_positive set
                pass
            if not final_p:
                blocks.append(f"scene[{i}]:continuity_without_final_prompt")
        mode = str(sc.get("visual_mode") or "").upper()
        if mode and mode not in ("", "IMAGE", "IMAGE_WITH_MOTION", "VIDEO"):
            blocks.append(f"scene[{i}]:unsupported_visual_mode:{mode}")
        # Required relationship absence when coverage says NONE for relationship and C05-S

    return {
        "ok": not blocks,
        "blocked": bool(blocks),
        "blocks": blocks,
        "warnings": warnings,
        "unknowns": unknowns,
        "paid_api_calls": 0,
        "authority": "C05-GA generation_alignment_preflight",
    }


def inspect_provider_request_integrity(scene: dict[str, Any], *, narration: str = "") -> dict[str, Any]:
    """Deterministic inspection of what would be sent to the visual provider (no paid calls)."""
    resolved = resolve_canonical_visual_prompt(scene, narration=narration)
    prompt = str(resolved.get("prompt") or "")
    intent = scene.get("c05s_scene_intent") if isinstance(scene.get("c05s_scene_intent"), dict) else {}
    rels = scene.get("required_relationships") or intent.get("relations") or []
    checks = {
        "has_prompt": bool(prompt.strip()),
        "source": resolved.get("source"),
        "stale_c05s_ignored": bool(resolved.get("stale_c05s_ignored")),
        "has_dialogue_id": bool(str(scene.get("dialogue_id") or scene.get("c05s_dialogue_id") or "").strip()),
        "has_beat_id": bool(str(scene.get("c05s_visual_beat_id") or "").strip()),
        "has_location": bool(str(scene.get("location") or intent.get("location") or "").strip()),
        "has_character": bool(
            (isinstance(scene.get("character_state"), dict) and scene["character_state"].get("identity"))
            or scene.get("actors")
            or (intent.get("actors") if isinstance(intent, dict) else None)
            or scene.get("subject")
        ),
        "has_camera": bool(str(scene.get("camera_intent") or intent.get("shot_type") or "").strip()),
        "has_lighting": bool(
            str(scene.get("lighting_intent") or (intent.get("continuity_refs") or {}).get("lighting") or "").strip()
        ),
        "has_emotion": bool(str(scene.get("emotional_intent") or intent.get("emotional_intent") or "").strip()),
        "has_visual_mode": bool(str(scene.get("visual_mode") or intent.get("visual_mode") or "").strip()),
        "has_coverage": bool(scene.get("visual_coverage") or scene.get("coverage_overall")),
        "has_timing": bool(scene.get("visual_timing") or scene.get("start_sec") is not None),
        "has_relationships": bool(rels),
        "relation_types": [
            str((r.get("relation_type") if isinstance(r, dict) else getattr(r, "relation_type", "")) or "")
            for r in (rels if isinstance(rels, list) else [])
        ],
        "prompt_contains_beside": "beside" in prompt.lower(),
        "prompt_degraded_located_at_for_beside": (
            "beside" in str(rels).lower() and "located at" in prompt.lower() and "beside" not in prompt.lower()
        ),
        "legacy_ignored": bool(resolved.get("legacy_ignored")),
    }
    failed = [k for k, v in checks.items() if k.startswith("has_") and v is False]
    if checks.get("prompt_degraded_located_at_for_beside"):
        failed.append("relation_semantic_degraded")
    return {
        "ok": not failed,
        "failed": failed,
        "checks": checks,
        "resolved": resolved,
        "prompt_preview": prompt[:400],
        "paid_api_calls": 0,
    }


def assert_trs_pre_provider_ready(handoff: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed deterministic checks before paid visual/audio providers."""
    blocks: list[str] = []
    unknowns: list[str] = []
    h = dict(handoff or {})
    if not h.get("ok"):
        blocks.append(f"trs_not_ok:{h.get('status') or h.get('reason') or 'blocked'}")
    intel = h.get("intelligence") or {}
    if intel.get("accepted") is not True and h.get("skip_intelligence") is not True:
        blocks.append("intelligence_not_accepted")
    ev = str(intel.get("evidence_status") or "")
    # Only re-assert evidence when caller requires VALID, or handoff already failed.
    # Successful TRS handoff remains authoritative (may carry UNKNOWN without fact_pack).
    if ev in ("INVALID", "INSUFFICIENT", "CONFLICT"):
        if h.get("require_evidence_valid") or not h.get("ok"):
            blocks.append(f"evidence_{ev.lower()}")
    if ev == "UNKNOWN" and h.get("require_evidence_valid"):
        blocks.append("evidence_unknown_mandatory")
        unknowns.append("evidence_status_UNKNOWN")
    plan = h.get("director_plan") or h.get("script_plan") or {}
    scenes = plan.get("scenes") if isinstance(plan, dict) else None
    beats = (h.get("script_plan") or {}).get("beats") if isinstance(h.get("script_plan"), dict) else None
    if not scenes and not beats:
        blocks.append("missing_script_plan_scenes")
    c05s = h.get("c05s") or {}
    if not (c05s.get("visual_beats") or []):
        blocks.append("missing_c05s_visual_beats")
    if not (c05s.get("narrative_beats") or []):
        blocks.append("missing_c05s_narrative_beats")
    if h.get("status") in ("BLOCKED", "INVALID", "UNKNOWN") and not h.get("ok"):
        blocks.append(f"handoff_status_{h.get('status')}")
    return {
        "ok": not blocks,
        "blocked": bool(blocks),
        "blocks": blocks,
        "unknowns": unknowns,
        "paid_api_calls": 0,
    }


def run_trs_pipeline(
    work_dir: Path | str,
    *,
    channel: dict[str, Any],
    topic: str,
    video_type: str = "long",
    language: str = "en",
    max_seconds: int = 60,
    blocked_topics: Optional[Sequence[str]] = None,
    use_mock_research: bool | None = True,
    use_mock_script: bool = True,
    require_external_live: bool = False,
    prefer_image_fallback: bool = False,
    visual_bible: Optional[dict[str, Any]] = None,
    job_id: str = "",
    research_notes: str = "",
    channel_specials: Optional[dict[str, str]] = None,
    google_api_keys: Optional[Sequence[str]] = None,
    openrouter_api: str = "",
    openrouter_keys: Optional[Sequence[str]] = None,
    niche_id: int | None = None,
    skip_intelligence: bool = False,
    production_wired: bool = False,
    allow_reserve_pick: bool = True,
    revision_id: str = "",
) -> dict[str, Any]:
    """
    Thin composition:

    CHANNEL → BUILD-04G gate → Script runtime → ScriptPlan → C05-S handoff

    Returns structured handoff. Does not generate video/TTS or call visual providers.
    """
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    job_id = job_id or work.name
    fmt = "SHORT" if str(video_type).lower() in ("short", "shorts", "reel") else "LONG"
    channel_id = int(channel.get("id") or channel.get("channel_id") or 0)
    niche = str(channel.get("niche") or channel.get("name") or "general")
    channel_name = str(
        channel.get("youtube_name")
        or channel.get("name")
        or channel.get("channel_name")
        or f"ch-{channel_id}"
    )
    if niche_id is None and channel.get("niche_id") is not None:
        try:
            niche_id = int(channel.get("niche_id"))
        except Exception:
            niche_id = None

    topic = str(topic or "").strip()
    if not topic and allow_reserve_pick and not skip_intelligence:
        from pipeline.intelligence.bridge import pick_topic_from_reserve

        reserved = pick_topic_from_reserve(work, channel, video_type=video_type)
        if reserved:
            topic = str(reserved).strip()

    if not topic and not skip_intelligence:
        return {
            "ok": False,
            "status": "BLOCKED",
            "stage": "intelligence",
            "reason": "missing_topic_and_empty_reserve",
            "paid_api_calls": 0,
            "authorities": _authorities(),
            "execution": {"trs": 1, "intelligence": 0, "script": 0},
        }

    # --- Topic / research (BUILD-04G sole authority) ---
    intel_count = 0
    if skip_intelligence:
        intel = {
            "accepted": True,
            "gate_verdict": GateVerdict.PASS.value,
            "evidence_status": "UNKNOWN",
            "research": {},
            "fact_pack": None,
            "research_capability": {"provider_capability": CAPABILITY_MOCK, "provider_mode": "SKIPPED"},
            "skipped": True,
        }
    else:
        intel_count = 1
        intel = run_topic_research_gate(
            work,
            channel,
            topic,
            video_type=video_type,
            blocked_topics=blocked_topics,
            use_mock_research=use_mock_research,
            require_external_live=require_external_live,
        )
        if not intel.get("accepted"):
            return {
                "ok": False,
                "status": "BLOCKED",
                "stage": "intelligence",
                "intelligence": intel,
                "reason": intel.get("reason") or intel.get("gate_verdict") or "intelligence_blocked",
                "paid_api_calls": 0,
                "authorities": _authorities(),
                "execution": {"trs": 1, "intelligence": intel_count, "script": 0},
            }

        # Fail closed on mandatory evidence insufficiency when research ran
        ev_status = intel.get("evidence_status")
        if ev_status in ("INVALID", "INSUFFICIENT", "CONFLICT", "UNKNOWN") and intel.get("fact_pack") is not None:
            if ev_status != "VALID":
                return {
                    "ok": False,
                    "status": "BLOCKED",
                    "stage": "evidence",
                    "intelligence": intel,
                    "evidence_status": ev_status,
                    "reason": f"evidence_{ev_status.lower()}",
                    "paid_api_calls": 0,
                    "authorities": _authorities(),
                    "execution": {"trs": 1, "intelligence": intel_count, "script": 0},
                }

    ev_status = intel.get("evidence_status")
    topic_fp = _fp({
        "topic": topic,
        "channel_id": channel_id,
        "format": fmt,
        "gate": intel.get("gate_verdict"),
    })
    research = dict(intel.get("research") or {})
    research_fp = _fp({
        "query": research.get("query") or topic,
        "capability": (intel.get("research_capability") or {}).get("provider_capability"),
        "evidence_status": ev_status,
        "fact_pack_id": (intel.get("fact_pack") or {}).get("id") if isinstance(intel.get("fact_pack"), dict) else "",
    })

    notes = (research_notes or "").strip()
    if research.get("query"):
        notes = (notes + f"\nResearch query: {research.get('query')}").strip()
    if not notes:
        notes = topic

    # --- Script (existing niche/script runtime) — exactly one call in this TRS invocation ---
    script_raw = plan_script_for_trs(
        work,
        job_id=job_id,
        niche=niche,
        niche_id=niche_id,
        channel_name=channel_name,
        topic=topic,
        video_type=video_type,
        max_seconds=max_seconds,
        research_notes=notes,
        use_mock=use_mock_script,
        channel_specials=channel_specials,
        blocked_products=blocked_topics,
        google_api_keys=google_api_keys,
        openrouter_api=openrouter_api,
        openrouter_keys=openrouter_keys,
        revision_id=revision_id,
    )
    script_count = 1
    # Normalize plan payload from runtime result
    plan_dict = {}
    if isinstance(script_raw, dict):
        plan_dict = dict(script_raw.get("plan") or script_raw.get("result") or script_raw)
        if "scenes" not in plan_dict and isinstance(script_raw.get("scenes"), list):
            plan_dict = script_raw

    script_plan = normalize_niche_plan_to_script_plan(
        plan_dict,
        topic_id=str(intel.get("topic_id") or topic_fp[:12]),
        fmt=fmt,
        language=language,
        fact_pack=intel.get("fact_pack") if isinstance(intel.get("fact_pack"), dict) else None,
        target_duration_sec=float(max_seconds),
    )

    # Industrial prompt-compliance proof BEFORE structural preflight handoff
    compliance_audit: dict = {}
    try:
        from pipeline.creative_production.prompt_compliance_auditor import (
            PromptComplianceError,
            audit_script_prompt_compliance,
        )

        compliance_audit = audit_script_prompt_compliance(
            plan_dict if isinstance(plan_dict, dict) else script_plan.model_dump(),
            work_dir=work,
            job_id=str(job_id or work.name),
            enable_llm_critic=None,
            repair=True,
            fail_closed=True,
            google_api_keys=google_api_keys,
            openrouter_keys=openrouter_keys,
        )
        if isinstance(compliance_audit.get("plan"), dict):
            plan_dict = compliance_audit["plan"]
            script_plan = normalize_niche_plan_to_script_plan(
                plan_dict,
                topic_id=str(intel.get("topic_id") or topic_fp[:12]),
                fmt=fmt,
                language=language,
                fact_pack=intel.get("fact_pack") if isinstance(intel.get("fact_pack"), dict) else None,
                target_duration_sec=float(max_seconds),
            )
    except PromptComplianceError as exc:
        return {
            "ok": False,
            "status": "BLOCKED",
            "stage": "prompt_compliance",
            "intelligence": intel,
            "script_plan": script_plan.model_dump(),
            "prompt_compliance": getattr(exc, "audit", {}) or {},
            "director_plan": plan_dict,
            "reason": "prompt_compliance_blocked",
            "error": str(exc),
            "paid_api_calls": 0,
            "authorities": _authorities(),
            "execution": {"trs": 1, "intelligence": intel_count, "script": script_count},
        }
    except Exception as exc:
        logger.warning("TRS prompt compliance soft-fail: %s", exc)

    preflight = validate_script_plan_preflight(script_plan.model_dump(), require_evidence=False)
    if preflight.get("blocked"):
        return {
            "ok": False,
            "status": "BLOCKED",
            "stage": "script_preflight",
            "intelligence": intel,
            "script_plan": script_plan.model_dump(),
            "script_preflight": preflight,
            "prompt_compliance": compliance_audit,
            "director_plan": plan_dict,
            "reason": "script_preflight_blocked",
            "paid_api_calls": 0,
            "authorities": _authorities(),
            "execution": {"trs": 1, "intelligence": intel_count, "script": script_count},
        }

    script_fp = _fp({
        "topic": script_plan.topic,
        "beats": [(b.beat_id, b.narration, b.section_role) for b in script_plan.beats],
        "format": script_plan.format,
    })

    # --- C05-S handoff ---
    segments = script_plan_to_dialogue_segments(script_plan, scene_id=f"sc-{channel_id or 1}")
    bible_fields = visual_bible or {
        "bible_id": f"vb-trs-{channel_id or 'x'}",
        "subject_identity": topic,
        "character_identity": "Narrator subject",
        "visual_style": "documentary",
        "location": segments[0].location if segments and segments[0].location else "studio",
        "environment": "production set",
    }
    if hasattr(visual_bible, "bible_id"):
        bible = visual_bible
    else:
        bible = create_visual_bible(**(visual_bible if isinstance(visual_bible, dict) else bible_fields))

    c05s = decompose_dialogue_to_visual_beats(
        segments=segments,
        bible=bible,
        prefer_image_fallback=prefer_image_fallback,
    )

    director_plan = apply_c05s_direction_to_director_plan(
        plan_dict,
        c05s,
        dialogue_segments=[s.to_dict() for s in segments],
        bible=bible,
        topic=topic,
    )

    handoff_fp = compute_trs_handoff_fingerprint(
        topic_fp=topic_fp,
        research_fp=research_fp,
        script_fp=script_fp,
        channel_id=channel_id,
        fmt=fmt,
    )

    handoff = {
        "ok": True,
        "status": "PASS",
        "stage": "c05s_handoff",
        "channel_id": channel_id,
        "format": fmt,
        "language": language,
        "topic": topic,
        "skip_intelligence": skip_intelligence,
        "intelligence": {
            "accepted": True,
            "gate_verdict": intel.get("gate_verdict"),
            "evidence_status": ev_status,
            "research_capability": intel.get("research_capability"),
            "external_live_requirement": intel.get("external_live_requirement"),
            "score": intel.get("score"),
            "skipped": bool(skip_intelligence),
        },
        "research": research,
        "fact_pack": intel.get("fact_pack"),
        "script_plan": script_plan.model_dump(),
        "script_preflight": preflight,
        "prompt_compliance": {
            "verdict": (compliance_audit or {}).get("verdict"),
            "overall_score": (compliance_audit or {}).get("overall_score"),
            "industrial_grade": (compliance_audit or {}).get("industrial_grade"),
            "artifact_path": (compliance_audit or {}).get("artifact_path"),
            "llm_critic_verdict": ((compliance_audit or {}).get("llm_critic") or {}).get("verdict"),
            "repairs_applied": (compliance_audit or {}).get("repairs_applied") or [],
        },
        "director_plan": director_plan,
        "legacy_visual_prompts": script_plan.legacy_visual_prompts,
        "dialogue_segments": [s.to_dict() for s in segments],
        "c05s": c05s,
        "fingerprints": {
            "topic": topic_fp,
            "research": research_fp,
            "script": script_fp,
            "trs_handoff": handoff_fp,
        },
        "compatibility": {
            "c05_v": "compatible_via_DirectedVisualBeat_visual_bible_mode",
            "c05_q": "compatible_via_SceneIntent_projection_and_emotion_fields",
            "scene_intent": "via_C05S_visual_beat_to_scene_intent",
            "continuity": "ContinuityTracker_unchanged",
            "audio_plan": "AudioIntent_fields_on_DialogueSegment",
            "generate_video_wired": bool(production_wired),
            "prompt_compiler": "pipeline.multimodal_consistency.prompt_compiler",
        },
        "claims": {
            "external_live_research": False,
            "human_written_script": False,
            "pixel_verification": False,
            "vlm_verification": False,
            "guaranteed_engagement": False,
        },
        "execution": {"trs": 1, "intelligence": intel_count, "script": script_count},
        "paid_api_calls": 0,
        "authorities": _authorities(),
    }
    try:
        persist_trs_handoff(work, handoff)
    except Exception:
        pass
    return handoff


def assert_no_fake_external_live(handoff: dict[str, Any]) -> bool:
    """Guard: LOCAL_FACTPACK must not be advertised as EXTERNAL_LIVE."""
    cap = (handoff.get("intelligence") or {}).get("research_capability") or {}
    research = handoff.get("research") or {}
    if cap.get("provider_capability") == CAPABILITY_EXTERNAL_LIVE and not research.get("external_api"):
        return False
    if research.get("provider_capability") == CAPABILITY_LOCAL_FACTPACK and research.get("is_external_live"):
        return False
    if handoff.get("claims", {}).get("external_live_research") and cap.get("provider_capability") != CAPABILITY_EXTERNAL_LIVE:
        return False
    return True


def assert_script_does_not_own_visual_prompts(plan: ScriptPlan | dict[str, Any]) -> bool:
    """Canonical ScriptPlan must not treat provider visual prompts as ownership."""
    d = plan.model_dump() if hasattr(plan, "model_dump") else dict(plan)
    if d.get("metadata", {}).get("script_owns_provider_visual_prompts") is True:
        return False
    for b in d.get("beats") or []:
        if isinstance(b, dict) and b.get("exact_ai_video_prompt"):
            # beats should not carry provider prompts as canonical fields
            return False
    return True


def _authorities() -> dict[str, str]:
    return {
        "topic_intelligence": "pipeline.intelligence (BUILD-04G)",
        "research": "pipeline.intelligence.research_provider / research_runtime",
        "factpack": "domain.fact_pack + intelligence.factpack_gate",
        "script": "pipeline.idempotency.script_bridge + niche_director",
        "script_plan": "domain.script.ScriptPlan",
        "dialogue_narrative_visual": "pipeline.story_visual_direction (C05-S)",
        "visual_intelligence": "pipeline.visual_intelligence (C05-V)",
        "production_consistency": "pipeline.production_consistency (C05-Q)",
        "idempotency": "pipeline.idempotency (BUILD-03)",
        "quality_repair": "pipeline.quality (BUILD-04F)",
        "prompt_compiler": "pipeline.multimodal_consistency.prompt_compiler",
    }


# Re-export capability constants for tests
__all__ = [
    "run_trs_pipeline",
    "run_topic_research_gate",
    "plan_script_for_trs",
    "normalize_niche_plan_to_script_plan",
    "script_plan_to_dialogue_segments",
    "classify_visual_prompt_ownership",
    "classify_research_capability",
    "require_external_live_or_block",
    "map_factpack_status",
    "compute_trs_handoff_fingerprint",
    "assert_no_fake_external_live",
    "assert_script_does_not_own_visual_prompts",
    "assert_generation_alignment_preflight",
    "inspect_provider_request_integrity",
    "assert_trs_pre_provider_ready",
    "apply_c05s_direction_to_director_plan",
    "refresh_c05s_from_director_plan",
    "resolve_canonical_visual_prompt",
    "persist_trs_handoff",
    "load_trs_handoff",
    "CAPABILITY_LOCAL_FACTPACK",
    "CAPABILITY_EXTERNAL_LIVE",
    "CAPABILITY_MOCK",
    "LEGACY_VISUAL_PROMPT_FIELDS",
]
