"""C05-S — Story-to-Scene Direction & Dialogue–Visual Alignment (orchestration only).

Composes existing authorities — does NOT replace:
  SceneIntent, VisualBible, ContinuityTracker, AudioPlan, production_consistency,
  multimodal_consistency, prompt_compiler, CreativeProductionPlan, Artifact Verification,
  BUILD-04F repair.

Defines EXPECTED visual planning only. Actual observation remains Artifact Verification /
multimodal / future VLM.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from domain.scene_intent import (
    AudioIntent,
    EntityRelation,
    SceneIntent,
    SemanticEntity,
)
from pipeline.creative_production.camera import ALLOWED_SHOTS
from pipeline.production_consistency import (
    CAPABILITY_LIMITATION,
    OBS_HEURISTIC,
    OBS_UNKNOWN,
    SceneEmotionState,
    VoiceIdentity,
    apply_voice_identity_to_audio_intent,
    plan_consistency_repair,
    record_tts_capability_limitations,
)
from pipeline.visual_intelligence import (
    MODE_IMAGE,
    MODE_IMAGE_WITH_MOTION,
    MODE_VIDEO,
    SUPPORTED_VISUAL_MODES,
    SceneVisualDelta,
    VisualBible,
    build_scene_visual_contract,
    compile_visual_prompt,
    decide_visual_mode,
    sanitize_visual_metadata,
)

# Location continuity
SAME_LOCATION = "SAME_LOCATION"
LOCATION_TRANSITION = "LOCATION_TRANSITION"
NEW_LOCATION = "NEW_LOCATION"

# Lighting continuity
LIGHTING_INHERITED = "INHERITED"
LIGHTING_INTENTIONAL_CHANGE = "INTENTIONAL_CHANGE"
LIGHTING_UNKNOWN = "UNKNOWN"

# Coverage
COVERAGE_FULL = "FULL"
COVERAGE_PARTIAL = "PARTIAL"
COVERAGE_NONE = "NONE"
COVERAGE_UNKNOWN = "UNKNOWN"

# Hold / risk
HOLD_SHORT = "SHORT"  # ~2–4s
HOLD_NORMAL = "NORMAL"  # ~4–6s
HOLD_LONG = "LONG"  # ~6–8s
VISUAL_HOLD_RISK = "VISUAL_HOLD_RISK"
VISUAL_REPETITION_RISK = "VISUAL_REPETITION_RISK"

# Camera intents (mapped onto existing ALLOWED_SHOTS)
CAMERA_INTENTS = {
    "ESTABLISHING": "establishing",
    "MEDIUM": "medium",
    "CLOSE": "close-up",
    "DETAIL": "close-up",
    "INSERT": "close-up",
    "OVER_SHOULDER": "over-the-shoulder",
    "PROFILE": "medium",
    "WIDE": "wide",
    "FOLLOW": "wide",
    "TRANSITION": "wide",
}

RELATION_TYPES = frozenset(
    {
        "beside",
        "next_to",
        "inside",
        "outside",
        "holding",
        "driving",
        "sitting",
        "standing",
        "standing_near",
        "sitting_in",
        "walking_toward",
        "looking_at",
        "speaking_to",
        "following",
        "entering",
        "exiting",
        "behind",
        "in_front_of",
        "left_of",
        "right_of",
        "wearing",
        "carrying",
        "on_top_of",
        "owns",
        "part_of",
        "located_at",
        "uses",
        "interacts_with",
    }
)

# Natural-language render for provider prompts — preserves semantic distinction
RELATION_PROMPT_PHRASE = {
    "beside": "is standing beside",
    "next_to": "is next to",
    "inside": "is inside",
    "outside": "is outside",
    "holding": "is holding",
    "driving": "is driving",
    "sitting": "is sitting",
    "standing": "is standing",
    "standing_near": "is standing near",
    "sitting_in": "is sitting in",
    "walking_toward": "is walking toward",
    "looking_at": "is looking at",
    "speaking_to": "is speaking to",
    "following": "is following",
    "entering": "is entering",
    "exiting": "is exiting",
    "behind": "is behind",
    "in_front_of": "is in front of",
    "left_of": "is to the left of",
    "right_of": "is to the right of",
    "wearing": "is wearing",
    "carrying": "is carrying",
    "on_top_of": "is on top of",
    "owns": "owns",
    "part_of": "is part of",
    "located_at": "is located at",
    "uses": "is using",
    "interacts_with": "is interacting with",
}


def canonical_relation_type(relation_type: str) -> str:
    """Normalize aliases without destroying spatial meaning."""
    t = (relation_type or "").strip().lower().replace(" ", "_")
    aliases = {
        "next-to": "next_to",
        "in_front": "in_front_of",
        "infront": "in_front_of",
        "left": "left_of",
        "right": "right_of",
        "look_at": "looking_at",
        "looks_at": "looking_at",
    }
    return aliases.get(t, t)


def render_relation_prompt_phrase(
    *,
    source_label: str,
    relation_type: str,
    target_label: str,
) -> str:
    """Faithful NL rendering — never collapse beside → located_at."""
    rel = canonical_relation_type(relation_type)
    phrase = RELATION_PROMPT_PHRASE.get(rel, f"has relation '{rel}' to")
    src = (source_label or "subject").strip()
    tgt = (target_label or "object").strip()
    return f"{src} {phrase} {tgt}"


ENTITY_TYPES = frozenset(
    {"person", "vehicle", "object", "location", "organization", "document", "building", "actor", "device", "component"}
)

_SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+")


@dataclass
class DialogueSegment:
    """Planning unit for one dialogue utterance — not TTS execution."""

    segment_id: str
    dialogue_id: str
    scene_id: str
    text: str
    speaker: str = ""
    language: str = "en"
    start_sec: float = 0.0
    end_sec: float = 0.0
    semantic_intent: str = ""
    entities: list[dict[str, Any]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    location: str = ""
    emotional_intent: str = ""
    emphasis: list[str] = field(default_factory=list)
    visual_relevance: str = "high"  # high | medium | low | none
    # C05-TRS additive (extends DialogueSegment — no duplicate class)
    semantic_purpose: str = ""
    intensity: float = 0.5
    evidence_references: list[str] = field(default_factory=list)
    visual_implication: str = ""  # semantic EXPECTED — not provider prompt
    temporal_context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def duration_sec(self) -> float:
        return max(0.0, float(self.end_sec) - float(self.start_sec))


@dataclass
class NarrativeBeat:
    """One meaningful storytelling unit — explains WHY a visual change is needed."""

    beat_id: str
    dialogue_segment_id: str
    semantic_subject: str = ""
    action: str = ""
    event: str = ""
    important_entity: str = ""
    important_object: str = ""
    location_change: str = SAME_LOCATION  # SAME_LOCATION | LOCATION_TRANSITION | NEW_LOCATION
    emotional_change: bool = False
    visual_change_candidate: bool = False
    visual_change_reason: str = ""
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GroundedEntity:
    entity_id: str
    entity_type: str
    label: str
    role: str = "subject"  # subject | object | location | prop | organization
    required: bool = True
    visual_representation: str = ""
    continuity: str = "MUST_PERSIST"  # MUST_PERSIST | MAY_CHANGE | EPHEMERAL

    def to_semantic_entity(self) -> SemanticEntity:
        et = self.entity_type if self.entity_type in (
            "actor", "object", "component", "location", "device"
        ) else (
            "actor" if self.entity_type == "person" else
            "location" if self.entity_type in ("location", "building") else
            "object"
        )
        return SemanticEntity(
            entity_id=self.entity_id,
            entity_type=et,
            label=self.label,
            attributes={
                "c05s_type": self.entity_type,
                "role": self.role,
                "required": "true" if self.required else "false",
                "continuity": self.continuity,
                "visual_representation": self.visual_representation or self.label,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GroundedRelation:
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str
    required: bool = True

    def to_entity_relation(self) -> EntityRelation:
        """Preserve canonical C05-S relation types (beside ≠ located_at).

        Optional schema_compat attribute retains legacy mapped vocabulary for
        older consumers — prompt_compiler must use relation_type / c05s_relation.
        """
        canon = canonical_relation_type(self.relation_type)
        legacy_compat = {
            "beside": "located_at",
            "next_to": "located_at",
            "inside": "located_at",
            "outside": "located_at",
            "holding": "uses",
            "carrying": "uses",
            "driving": "uses",
            "looking_at": "interacts_with",
            "speaking_to": "interacts_with",
            "on_top_of": "part_of",
            "standing_near": "located_at",
            "sitting_in": "located_at",
            "behind": "located_at",
            "in_front_of": "located_at",
            "left_of": "located_at",
            "right_of": "located_at",
        }.get(canon, canon)
        return EntityRelation(
            relation_id=self.relation_id,
            source_id=self.source_id,
            target_id=self.target_id,
            relation_type=canon if canon in RELATION_TYPES else self.relation_type,
            attributes={
                "c05s_relation": canon or self.relation_type,
                "schema_compat": legacy_compat,
                "required": str(self.required).lower(),
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VisualCoverage:
    """Intent-level coverage contract — NOT artifact observation."""

    subject: str = COVERAGE_UNKNOWN
    action: str = COVERAGE_UNKNOWN
    entity: str = COVERAGE_UNKNOWN
    object: str = COVERAGE_UNKNOWN
    relationship: str = COVERAGE_UNKNOWN
    location: str = COVERAGE_UNKNOWN
    temporal: str = COVERAGE_UNKNOWN
    overall: str = COVERAGE_UNKNOWN
    confidence: str = OBS_HEURISTIC
    note: str = "intent_planning_only_not_artifact_observation"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DirectedVisualBeat:
    """Canonical visual beat planning record (distinct from fallback Ken Burns VisualBeat)."""

    beat_id: str
    dialogue_segment_id: str
    narrative_beat_id: str
    scene_id: str
    visual_bible_id: str = ""
    visual_bible_version: str = ""
    scene_contract_id: str = ""
    required_entities: list[GroundedEntity] = field(default_factory=list)
    required_objects: list[str] = field(default_factory=list)
    relationships: list[GroundedRelation] = field(default_factory=list)
    character_state: dict[str, Any] = field(default_factory=dict)
    location_state: dict[str, Any] = field(default_factory=dict)
    environment_state: dict[str, Any] = field(default_factory=dict)
    camera_intent: str = "MEDIUM"
    lighting_intent: str = ""
    lighting_continuity: str = LIGHTING_INHERITED
    composition: str = ""
    emotional_visual_intent: str = ""
    previous_beat_id: str = ""
    next_beat_id: str = ""
    visual_mode: str = MODE_IMAGE
    duration_policy: str = HOLD_NORMAL
    duration_sec: float = 5.0
    transition_intent: str = "cut"
    coverage: VisualCoverage = field(default_factory=VisualCoverage)
    prompt_provenance: dict[str, Any] = field(default_factory=dict)
    risks: list[str] = field(default_factory=list)
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return sanitize_story_metadata(d)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DirectedVisualBeat":
        """Rehydrate planning beat from serialized handoff (no second engine)."""
        d = dict(data or {})
        ents = [
            GroundedEntity(**e) if isinstance(e, dict) else e
            for e in (d.get("required_entities") or [])
        ]
        rels = [
            GroundedRelation(**r) if isinstance(r, dict) else r
            for r in (d.get("relationships") or [])
        ]
        cov = d.get("coverage")
        if isinstance(cov, dict):
            cov = VisualCoverage(**{k: v for k, v in cov.items() if k in VisualCoverage.__dataclass_fields__})
        fields = cls.__dataclass_fields__
        payload = {k: v for k, v in d.items() if k in fields}
        payload["required_entities"] = ents
        payload["relationships"] = rels
        if cov is not None:
            payload["coverage"] = cov
        return cls(**payload)


def dialogue_segment_from_dict(data: dict[str, Any]) -> DialogueSegment:
    d = dict(data or {})
    fields = DialogueSegment.__dataclass_fields__
    return DialogueSegment(**{k: v for k, v in d.items() if k in fields})


def sanitize_story_metadata(obj: Any) -> Any:
    return sanitize_visual_metadata(obj)


def _fp(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))


def map_camera_intent(intent: str) -> str:
    """Map C05-S camera intent onto existing ALLOWED_SHOTS vocabulary."""
    key = (intent or "MEDIUM").strip().upper().replace("-", "_").replace(" ", "_")
    if key == "OVER_THE_SHOULDER":
        key = "OVER_SHOULDER"
    shot = CAMERA_INTENTS.get(key, "")
    if not shot:
        # allow direct ALLOWED_SHOTS values
        low = (intent or "").strip().lower()
        if low in ALLOWED_SHOTS:
            return low
        raise ValueError(f"unsupported_camera_intent:{intent}")
    return shot


def create_dialogue_segment(
    *,
    segment_id: str,
    dialogue_id: str,
    scene_id: str,
    text: str,
    speaker: str = "",
    language: str = "en",
    start_sec: float = 0.0,
    end_sec: float = 0.0,
    semantic_intent: str = "",
    actions: Optional[Sequence[str]] = None,
    location: str = "",
    emotional_intent: str = "",
    emphasis: Optional[Sequence[str]] = None,
    visual_relevance: str = "high",
    entities: Optional[Sequence[dict[str, Any]]] = None,
    semantic_purpose: str = "",
    intensity: float = 0.5,
    evidence_references: Optional[Sequence[str]] = None,
    visual_implication: str = "",
    temporal_context: str = "",
) -> DialogueSegment:
    if not (segment_id or "").strip():
        raise ValueError("segment_id_required")
    if not (text or "").strip():
        raise ValueError("dialogue_text_required")
    if float(end_sec) < float(start_sec):
        raise ValueError("invalid_timing_end_before_start")
    purpose = (semantic_purpose or semantic_intent or text.strip()[:120]).strip()
    return DialogueSegment(
        segment_id=segment_id.strip(),
        dialogue_id=(dialogue_id or segment_id).strip(),
        scene_id=scene_id.strip(),
        text=text.strip(),
        speaker=speaker,
        language=(language or "en").lower(),
        start_sec=float(start_sec),
        end_sec=float(end_sec) if end_sec else float(start_sec) + 4.0,
        semantic_intent=semantic_intent or purpose,
        entities=list(entities or []),
        actions=list(actions or []),
        location=location,
        emotional_intent=emotional_intent,
        emphasis=list(emphasis or []),
        visual_relevance=visual_relevance,
        semantic_purpose=purpose,
        intensity=float(intensity if intensity is not None else 0.5),
        evidence_references=list(evidence_references or []),
        visual_implication=visual_implication,
        temporal_context=temporal_context,
    )


def ground_entities_from_text(
    text: str,
    *,
    explicit: Optional[Sequence[GroundedEntity]] = None,
) -> list[GroundedEntity]:
    """Heuristic entity grounding — does not invent unsupported story entities when explicit given."""
    if explicit is not None:
        out = []
        for e in explicit:
            if e.entity_type.lower() not in ENTITY_TYPES and e.entity_type.lower() not in {
                "person", "vehicle", "object", "location", "organization", "document", "building"
            }:
                raise ValueError(f"unsupported_entity_type:{e.entity_type}")
            out.append(e)
        return out

    # Deterministic keyword heuristics only — labeled HEURISTIC at planning layer
    t = (text or "").lower()
    found: list[GroundedEntity] = []
    patterns = [
        (r"\b(officer|investigator|doctor|man|woman|person|shobha|he|she)\b", "person"),
        (r"\b(suzuki|car|truck|vehicle|motorcycle|bike|rover)\b", "vehicle"),
        (r"\b(document|paper|file|report|letter)\b", "document"),
        (r"\b(desk|table|phone|smartphone|bag|gun|book|spectrometer|regolith)\b", "object"),
        (r"\b(water ice|subsurface ice|ice)\b", "object"),
        (r"\b(office|hospital|station|kitchen|beach|studio|warehouse|building|moon|lunar surface|cislunar)\b", "location"),
        (r"\b(polar craters?|shadowed craters?|lunar craters?|craters?)\b", "location"),
        (r"\b(police|company|agency|organization|ministry)\b", "organization"),
    ]
    seen = set()
    for pat, etype in patterns:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        label = m.group(1)
        key = f"{etype}:{label.lower()}"
        if key in seen:
            continue
        seen.add(key)
        found.append(
            GroundedEntity(
                entity_id=f"ent-{etype}-{label.lower()}",
                entity_type=etype,
                label=label,
                role="subject" if etype == "person" else ("location" if etype == "location" else "object"),
                required=True,
                visual_representation=label,
                continuity="MUST_PERSIST" if etype in ("person", "vehicle", "location", "building") else "MAY_CHANGE",
            )
        )
    return found


def ground_relations_from_text(
    text: str,
    entities: Sequence[GroundedEntity],
    *,
    explicit: Optional[Sequence[GroundedRelation]] = None,
) -> list[GroundedRelation]:
    if explicit is not None:
        for r in explicit:
            if r.relation_type not in RELATION_TYPES:
                raise ValueError(f"invalid_relationship:{r.relation_type}")
        return list(explicit)

    t = (text or "").lower()
    by_type: dict[str, list[GroundedEntity]] = {}
    for e in entities:
        by_type.setdefault(e.entity_type, []).append(e)

    rels: list[GroundedRelation] = []
    def _add(rtype: str, src: GroundedEntity, tgt: GroundedEntity) -> None:
        rels.append(
            GroundedRelation(
                relation_id=f"rel-{src.entity_id}-{rtype}-{tgt.entity_id}",
                source_id=src.entity_id,
                target_id=tgt.entity_id,
                relation_type=rtype,
                required=True,
            )
        )

    persons = by_type.get("person", [])
    vehicles = by_type.get("vehicle", [])
    objects = by_type.get("object", []) + by_type.get("document", [])
    locations = by_type.get("location", []) + by_type.get("building", [])

    if "beside" in t and persons and vehicles:
        _add("beside", persons[0], vehicles[0])
    if ("next to" in t or "next_to" in t) and persons and vehicles:
        _add("next_to", persons[0], vehicles[0])
    if ("inside" in t or "in the" in t or "into" in t) and persons and (vehicles or locations):
        tgt = vehicles[0] if vehicles and ("car" in t or "vehicle" in t or "suzuki" in t) else (locations[0] if locations else vehicles[0])
        _add("inside", persons[0], tgt)
    if ("outside" in t) and persons and (vehicles or locations):
        tgt = vehicles[0] if vehicles else locations[0]
        _add("outside", persons[0], tgt)
    if ("holding" in t or "held" in t or "opened the document" in t or "open" in t) and persons and objects:
        _add("holding", persons[0], objects[0])
    if ("carrying" in t or "carried" in t) and persons and objects:
        _add("carrying", persons[0], objects[0])
    if ("driving" in t or "drove" in t or "drives" in t) and persons and vehicles:
        _add("driving", persons[0], vehicles[0])
    if ("looking at" in t or "looked at" in t) and persons and objects:
        _add("looking_at", persons[0], objects[0])
    if ("speaking to" in t or "spoke to" in t or "talking to" in t) and len(persons) >= 2:
        _add("speaking_to", persons[0], persons[1])
    if ("left of" in t or "to the left" in t) and persons and (vehicles or objects):
        _add("left_of", persons[0], vehicles[0] if vehicles else objects[0])
    if ("right of" in t or "to the right" in t) and persons and (vehicles or objects):
        _add("right_of", persons[0], vehicles[0] if vehicles else objects[0])
    if ("in front of" in t) and persons and (vehicles or objects or locations):
        tgt = vehicles[0] if vehicles else (objects[0] if objects else locations[0])
        _add("in_front_of", persons[0], tgt)
    if ("behind" in t and "desk" not in t) and persons and (vehicles or objects):
        _add("behind", persons[0], vehicles[0] if vehicles else objects[0])
    if ("on the" in t or "on top" in t) and objects:
        # object on table if table mentioned
        tables = [o for o in objects if "table" in o.label.lower() or "desk" in o.label.lower()]
        others = [o for o in objects if o not in tables]
        if tables and others:
            _add("on_top_of", others[0], tables[0])
        elif "desk" in t and persons:
            desk = next((o for o in objects if "desk" in o.label.lower()), None)
            if desk:
                _add("beside", persons[0], desk)  # seated behind desk → spatial
    if "behind the desk" in t and persons:
        desk = next((o for o in objects if "desk" in o.label.lower()), None)
        if desk is None:
            desk = GroundedEntity("ent-object-desk", "object", "desk", role="object")
            # don't mutate entities list here; relation still recorded if desk exists in text grounding
        if any(o.label.lower() == "desk" for o in objects):
            desk_e = next(o for o in objects if o.label.lower() == "desk")
            _add("beside", persons[0], desk_e)

    # Documentary / niche spatial relationships (PART-5C relationship identity)
    crater = next((e for e in locations if "crater" in e.label.lower()), None)
    surface = next((e for e in (locations + objects) if "surface" in e.label.lower() or "regolith" in e.label.lower()), None)
    ice = next((e for e in objects if "ice" in e.label.lower()), None)
    rover = next((e for e in (vehicles + objects) if "rover" in e.label.lower()), None)
    spectrometer = next((e for e in objects if "spectrometer" in e.label.lower()), None)
    if ("inside" in t or "within" in t or "in the" in t) and ice and crater:
        _add("inside", ice, crater)
    elif ("inside" in t or "within" in t) and objects and crater:
        _add("inside", objects[0], crater)
    if ("on the" in t or "across" in t or "along" in t) and rover and (surface or crater or locations):
        tgt = surface or crater or locations[0]
        _add("located_at", rover, tgt)
    if spectrometer and rover and ("beside" in t or "mounted" in t or "on the rover" in t or "spectrometer" in t):
        _add("beside", spectrometer, rover)
    if ("beneath" in t or "under" in t or "below" in t) and ice and (surface or crater):
        _add("inside", ice, surface or crater)
    if ("preserve" in t or "trap" in t or "hide" in t) and ice and crater and not any(
        r.relation_type == "inside" for r in rels
    ):
        _add("inside", ice, crater)
    return rels


_RELATION_CUES = (
    "beside",
    "next to",
    "inside",
    "outside",
    "holding",
    "carrying",
    "driving",
    "looking at",
    "speaking to",
    "in front of",
    "behind",
    "left of",
    "right of",
    "on top",
    "beneath",
    "under",
    "within",
    "mounted",
    "trapped inside",
    "preserved inside",
    "preserved within",
)


def text_has_relationship_cues(text: str) -> bool:
    t = (text or "").lower()
    return any(c in t for c in _RELATION_CUES)


def infer_lighting_contract(
    text: str,
    *,
    topic: str = "",
    previous: str = "",
    bible_lighting: str = "",
) -> dict[str, Any]:
    """Always produce a non-empty lighting contract for multi-beat creative direction.

    Marks explicit_lighting=True so ContinuityTracker treats it as contractual.
    """
    blob = f"{text or ''} {topic or ''}".lower()
    if any(k in blob for k in ("shadowed", "permanently shadowed", "dark crater", "no sunlight", "never see sunlight")):
        light = "cold blue shadowed crater floor, no direct sunlight"
    elif any(k in blob for k in ("night", "moonlight", "lunar night")):
        light = "harsh lunar night, low-angle moonlight"
    elif any(k in blob for k in ("sunrise", "sunset", "golden hour")):
        light = "low-angle sunrise rim light"
    elif any(k in blob for k in ("daylight", "sunlit", "bright day", "sunlight")):
        light = "hard daylight, high-contrast shadows"
    elif any(k in blob for k in ("interior", "inside", "control room", "lab")):
        light = "cool practical interior key light"
    elif previous.strip():
        light = previous.strip()
    elif bible_lighting.strip():
        light = bible_lighting.strip()
    else:
        light = "natural directional key, documentary clarity"
    return {
        "lighting_intent": light,
        "explicit_lighting": True,
        "method": "DETERMINISTIC_INFER",
    }


def ensure_relationship_identity(
    text: str,
    entities: Sequence[GroundedEntity],
    relationships: Sequence[GroundedRelation] | list[Any],
) -> dict[str, Any]:
    """Fail-closed when relational language exists but relationships are empty.

    Documentary niche fallback: if cues remain after grounding, synthesize a
    minimal spatial relation from grounded nouns (does not invent characters).
    """
    ents = list(entities or [])
    if not ents:
        ents = ground_entities_from_text(text)
    rels = list(relationships or [])
    if not rels and text_has_relationship_cues(text):
        rels = ground_relations_from_text(text, ents)
    # Synthesize documentary spatial identity when cues remain unresolved
    if text_has_relationship_cues(text) and not rels and len(ents) >= 2:
        a, b = ents[0], ents[1]
        t = (text or "").lower()
        rtype = "beside"
        if any(c in t for c in ("inside", "within", "beneath", "under")):
            rtype = "inside"
        elif any(c in t for c in ("looking at", "facing")):
            rtype = "looking_at"
        elif "located" in t or "at the" in t:
            rtype = "located_at"
        rels = [
            GroundedRelation(
                relation_id=f"rel-{a.entity_id}-{rtype}-{b.entity_id}",
                source_id=a.entity_id,
                target_id=b.entity_id,
                relation_type=rtype,
                required=True,
            )
        ]
    elif text_has_relationship_cues(text) and not rels and len(ents) == 1:
        # Single grounded noun + location cue → place entity at documentary setting
        loc = GroundedEntity("ent-loc-setting", "location", "documentary setting", role="location")
        ents = list(ents) + [loc]
        rels = [
            GroundedRelation(
                relation_id=f"rel-{ents[0].entity_id}-located_at-{loc.entity_id}",
                source_id=ents[0].entity_id,
                target_id=loc.entity_id,
                relation_type="located_at",
                required=True,
            )
        ]
    ok = True
    issues: list[str] = []
    if text_has_relationship_cues(text) and not rels:
        ok = False
        issues.append("relationship_cue_without_identity")
    return {"ok": ok, "relationships": rels, "issues": issues, "explicit_relationships": bool(rels), "entities": ents}


def _semantic_content_tokens(text: str) -> set[str]:
    """Content nouns/verbs for documentary dialogue boundary detection (RCP-02)."""
    stop = {
        "the", "a", "an", "and", "or", "but", "with", "from", "into", "that", "this",
        "our", "their", "these", "those", "just", "very", "more", "than", "about",
        "how", "what", "when", "where", "which", "while", "after", "before", "through",
        "over", "under", "onto", "onto", "for", "are", "is", "was", "were", "been",
        "being", "have", "has", "had", "will", "can", "may", "must", "should",
        "us", "we", "you", "they", "it", "its", "as", "to", "of", "in", "on", "at",
        "by", "not", "no", "yes", "also", "only", "even", "still", "already",
    }
    tokens = {
        t.lower()
        for t in re.findall(r"[A-Za-z\u0980-\u09FF]{4,}", text or "")
        if t.lower() not in stop
    }
    return tokens


def create_narrative_beat(
    *,
    beat_id: str,
    segment: DialogueSegment,
    order: int = 0,
    previous_location: str = "",
    previous_emotion: str = "",
    previous_subject: str = "",
    previous_object: str = "",
    previous_action: str = "",
    previous_content_tokens: Optional[set[str]] = None,
) -> NarrativeBeat:
    if segment.entities:
        entities = [
            GroundedEntity(**e) if isinstance(e, dict) else e for e in segment.entities
        ]
    else:
        entities = ground_entities_from_text(segment.text)

    subject = next((e.label for e in entities if e.entity_type == "person"), "")
    obj = next((e.label for e in entities if e.entity_type in ("object", "document", "vehicle")), "")
    # Documentary / non-person subjects (telescope, galaxy, etc.)
    if not obj:
        obj = next(
            (
                e.label
                for e in entities
                if e.entity_type in ("object", "document", "vehicle", "device", "component", "organization")
            ),
            "",
        )
    if not subject:
        # Prefer concrete grounded non-person as semantic subject for documentary beats
        subject = obj or next((e.label for e in entities if e.role == "subject"), "")
    loc = segment.location or next(
        (e.label for e in entities if e.entity_type in ("location", "building")), ""
    )
    action = (segment.actions[0] if segment.actions else "") or _infer_action(segment.text)
    content_tokens = _semantic_content_tokens(segment.text)

    if not previous_location or not loc:
        loc_change = SAME_LOCATION
    elif previous_location.lower() == loc.lower():
        loc_change = SAME_LOCATION
    elif any(w in segment.text.lower() for w in ("went to", "arrives", "moved to", "cut to", "enters")):
        loc_change = NEW_LOCATION
    else:
        loc_change = LOCATION_TRANSITION

    emo_change = bool(segment.emotional_intent) and segment.emotional_intent != previous_emotion
    subject_change = bool(subject) and bool(previous_subject) and subject.lower() != previous_subject.lower()
    object_change = bool(obj) and bool(previous_object) and obj.lower() != previous_object.lower()
    action_change = bool(action) and bool(previous_action) and action.lower() != previous_action.lower()
    prev_tokens = previous_content_tokens or set()
    # Dialogue semantic boundary: substantial content-token drift between segments
    token_delta = 0.0
    if prev_tokens and content_tokens:
        inter = len(prev_tokens & content_tokens)
        union = len(prev_tokens | content_tokens) or 1
        token_delta = 1.0 - (inter / union)
    semantic_boundary = bool(prev_tokens) and token_delta >= 0.45

    reasons = []
    if order == 0:
        reasons.append("dialogue_boundary:first_segment")
    if loc_change != SAME_LOCATION:
        reasons.append(f"location:{loc_change}")
    if emo_change:
        reasons.append("emotional_change")
    if subject_change:
        reasons.append("subject_change")
    if object_change:
        reasons.append("entity_object_change")
    if action_change:
        reasons.append(f"action_change:{action}")
    elif action and order == 0:
        reasons.append(f"action:{action}")
    if semantic_boundary:
        reasons.append(f"dialogue_semantic_boundary:delta={token_delta:.2f}")
    # Explanatory / claim shift when visual implication or purpose differs meaningfully
    purpose = (segment.semantic_purpose or segment.visual_implication or "").strip().lower()
    if purpose and previous_subject and purpose not in (previous_subject or "").lower():
        # section_role style hooks (hook/context/reveal) already imply visual purpose change
        if any(
            k in purpose
            for k in ("hook", "context", "development", "reveal", "payoff", "ending", "climax")
        ):
            reasons.append(f"explanatory_visual_change:{purpose[:40]}")

    visual_change = bool(reasons) and (
        order == 0
        or loc_change != SAME_LOCATION
        or emo_change
        or subject_change
        or object_change
        or action_change
        or semantic_boundary
        or any(r.startswith("explanatory_visual_change") for r in reasons)
        or (bool(action) and order == 0)
    )
    if not reasons:
        reasons.append("semantic_stable_hold_candidate")
        visual_change = False

    return NarrativeBeat(
        beat_id=beat_id,
        dialogue_segment_id=segment.segment_id,
        semantic_subject=subject or segment.speaker,
        action=action,
        event=segment.semantic_intent or segment.text[:80],
        important_entity=subject,
        important_object=obj,
        location_change=loc_change,
        emotional_change=emo_change,
        visual_change_candidate=visual_change,
        visual_change_reason=";".join(reasons),
        order=order,
    )


def _infer_action(text: str) -> str:
    t = (text or "").lower()
    for verb in (
        "stood beside", "stood", "sat behind", "sat", "opened", "holding", "looked at",
        "entered", "exits", "walked", "presents", "stopped",
        # Documentary / explanatory actions (RCP-02 — person-verb list was too narrow)
        "revolutionizing", "revealing", "captures", "capture", "formed", "form",
        "showing", "shows", "provide", "provides", "challenge", "challenges",
        "unlock", "unlocks", "unveil", "unveils", "see through", "seeing",
        "orbiting", "launch", "launched", "observe", "observes", "imaging",
    ):
        if verb in t:
            return verb
    return ""


def decide_visual_hold_policy(
    *,
    dialogue_duration_sec: float,
    semantic_beat_count: int = 1,
    information_density: str = "normal",  # low | normal | high
    visual_complexity: str = "normal",
    motion_available: bool = False,
    scene_importance: str = "normal",
    repetition_risk: bool = False,
) -> dict[str, Any]:
    """Asset-hold policy — HOW LONG one visual asset may cover dialogue.

    Does NOT set the production timeline duration. Timeline duration comes from
    dialogue segment durations. The 8.0s IMAGE hold cap forces a NEW visual beat
    when exceeded — it must never collapse/truncate the whole script.
    """
    dur = max(0.0, float(dialogue_duration_sec))
    density = (information_density or "normal").lower()
    importance = (scene_importance or "normal").lower()

    # Max time one static/held IMAGE asset may cover without a new beat
    max_hold_sec = 8.0
    if motion_available:
        max_hold_sec = 12.0 if importance in ("high", "hook", "payoff") else 10.0

    if semantic_beat_count > 1 or density == "high":
        policy = HOLD_SHORT
        target = min(4.0, max(2.0, dur / max(semantic_beat_count, 1)))
    elif dur <= 4.0 or density == "low":
        policy = HOLD_SHORT
        target = max(2.0, min(4.0, dur or 3.0))
    elif dur <= 6.0:
        policy = HOLD_NORMAL
        target = max(4.0, min(6.0, dur or 5.0))
    else:
        policy = HOLD_LONG
        # Cap describes asset hold budget, not script truncation
        target = max(6.0, min(max_hold_sec, dur if dur <= max_hold_sec else max_hold_sec))

    if motion_available and importance in ("high", "hook", "payoff"):
        target = min(max_hold_sec, target + 2.0)
        policy = HOLD_LONG if target >= 6.0 else policy

    if visual_complexity == "high" and policy == HOLD_SHORT:
        policy = HOLD_NORMAL
        target = max(target, 4.0)

    risks = []
    if not motion_available and dur >= 10.0 and semantic_beat_count <= 1:
        risks.append(VISUAL_HOLD_RISK)
    if repetition_risk:
        risks.append(VISUAL_REPETITION_RISK)
    if dur > max_hold_sec:
        risks.append(VISUAL_HOLD_RISK)

    return {
        "policy": policy,
        "duration_sec": round(target, 2),
        "max_hold_sec": round(max_hold_sec, 2),
        "risks": risks,
        "confidence": OBS_HEURISTIC,
        "note": "asset_hold_budget_not_timeline_duration;dialogue_drives_timeline",
    }


def detect_visual_repetition(
    beats: Sequence[DirectedVisualBeat],
) -> list[dict[str, Any]]:
    """HEURISTIC repetition detection across unrelated beats."""
    warnings = []
    sig_map: dict[str, list[str]] = {}
    for b in beats:
        ents = tuple(sorted(e.label.lower() for e in b.required_entities))
        rels = tuple(sorted(r.relation_type for r in b.relationships))
        loc = str((b.location_state or {}).get("location") or "").lower()
        action = str((b.character_state or {}).get("action") or "").lower()
        sig = _fp({"ents": ents, "rels": rels, "loc": loc, "action": action, "mode": b.visual_mode})
        sig_map.setdefault(sig, []).append(b.beat_id)
    for sig, ids in sig_map.items():
        if len(ids) > 1:
            # Same signature on multiple beats — risk if narrative reasons differ
            warnings.append(
                {
                    "code": VISUAL_REPETITION_RISK,
                    "beat_ids": ids,
                    "confidence": OBS_HEURISTIC,
                    "note": "same_visual_signature_across_beats",
                }
            )
    return warnings


def build_directed_visual_beat(
    *,
    beat_id: str,
    segment: DialogueSegment,
    narrative: NarrativeBeat,
    bible: VisualBible,
    previous: Optional[DirectedVisualBeat] = None,
    camera_intent: str = "MEDIUM",
    visual_mode: str = "",
    lighting_intent: str = "",
    lighting_continuity: str = "",
    emotional_visual_intent: str = "",
    entities: Optional[Sequence[GroundedEntity]] = None,
    relations: Optional[Sequence[GroundedRelation]] = None,
    order: int = 0,
) -> DirectedVisualBeat:
    ents = list(entities) if entities is not None else ground_entities_from_text(segment.text)
    if relations is not None:
        rels = list(relations)
    else:
        ensured = ensure_relationship_identity(segment.text, ents, [])
        rels = list(ensured.get("relationships") or [])

    # Lighting contract — always explicit for creative-direction continuity (PART-5C)
    lit = infer_lighting_contract(
        segment.text,
        topic=str(getattr(bible, "location", "") or ""),
        previous=(previous.lighting_intent if previous else ""),
        bible_lighting=str(getattr(bible, "lighting", "") or ""),
    )
    if not lighting_intent:
        lighting_intent = str(lit.get("lighting_intent") or "")
    # Location continuity — camera change must not invent location change
    loc = segment.location or next((e.label for e in ents if e.entity_type in ("location", "building")), "")
    if previous:
        prev_loc = str((previous.location_state or {}).get("location") or "")
        if narrative.location_change == SAME_LOCATION or not loc:
            loc = prev_loc or loc
        location_state = {
            "location": loc or prev_loc,
            "continuity": narrative.location_change if loc and prev_loc and loc.lower() != prev_loc.lower() else SAME_LOCATION,
            "inherited_from": previous.beat_id if narrative.location_change == SAME_LOCATION else "",
        }
        env = dict(previous.environment_state or {})
        if bible.environment:
            env.setdefault("environment", bible.environment)
        light_cont = lighting_continuity or LIGHTING_INHERITED
        light = lighting_intent or previous.lighting_intent or bible.lighting or str(lit.get("lighting_intent") or "")
        char_state = {
            "identity": narrative.semantic_subject or (previous.character_state or {}).get("identity") or bible.character_identity,
            "wardrobe": (previous.character_state or {}).get("wardrobe") or bible.wardrobe,
            "action": narrative.action,
            "emotion": segment.emotional_intent or (previous.character_state or {}).get("emotion") or "",
            "accessories": (previous.character_state or {}).get("accessories") or bible.props,
        }
        prev_id = previous.beat_id
    else:
        location_state = {"location": loc or bible.location, "continuity": SAME_LOCATION, "inherited_from": ""}
        env = {"environment": bible.environment or segment.location or ""}
        light_cont = lighting_continuity or LIGHTING_INHERITED
        light = lighting_intent or bible.lighting or str(lit.get("lighting_intent") or "")
        char_state = {
            "identity": narrative.semantic_subject or bible.character_identity or segment.speaker,
            "wardrobe": bible.wardrobe,
            "action": narrative.action,
            "emotion": segment.emotional_intent,
            "accessories": bible.props,
        }
        prev_id = ""

    # Visual mode — VIDEO primary via media_mode_engine
    if visual_mode:
        mode = visual_mode.strip().upper()
        if mode not in SUPPORTED_VISUAL_MODES:
            raise ValueError(f"unsupported_visual_mode:{mode}")
        mode_reason = f"explicit:{mode}"
    else:
        decision = decide_visual_mode(
            primary_action=narrative.action,
            narration=str(getattr(segment, "text", "") or ""),
            element=str(getattr(segment, "section_role", "") or getattr(narrative, "section_role", "") or ""),
            # Do NOT treat "no visual change" as static_sufficient — that forced IMAGE for whole films
            static_sufficient=False,
            controlled_motion_helps=False,
            visual_change_candidate=bool(getattr(narrative, "visual_change_candidate", True)),
            prefer_image_fallback=False,
        )
        if decision.get("ok") != "true":
            raise ValueError(decision.get("reason") or "visual_mode_undecided")
        mode = decision["mode"]
        mode_reason = decision["reason"]

    hold = decide_visual_hold_policy(
        dialogue_duration_sec=segment.duration_sec,
        semantic_beat_count=1,
        motion_available=(mode in (MODE_IMAGE_WITH_MOTION, MODE_VIDEO)),
        scene_importance="high" if segment.visual_relevance == "high" else "normal",
    )

    # Coverage at intent level
    coverage = evaluate_intent_coverage(
        segment=segment,
        entities=ents,
        relations=rels,
        location=location_state.get("location") or "",
        action=narrative.action,
    )

    shot = map_camera_intent(camera_intent)
    # RCP-02: timeline duration is dialogue-driven; hold policy is asset budget only.
    timeline_dur = float(segment.duration_sec) if segment.duration_sec > 0 else float(hold["duration_sec"])

    return DirectedVisualBeat(
        beat_id=beat_id,
        dialogue_segment_id=segment.segment_id,
        narrative_beat_id=narrative.beat_id,
        scene_id=segment.scene_id,
        visual_bible_id=bible.bible_id,
        visual_bible_version=bible.version,
        required_entities=ents,
        required_objects=[e.label for e in ents if e.entity_type in ("object", "document", "vehicle")],
        relationships=rels,
        character_state=char_state,
        location_state=location_state,
        environment_state=env,
        camera_intent=camera_intent.upper() if camera_intent else "MEDIUM",
        lighting_intent=light,
        lighting_continuity=light_cont,
        composition=shot,
        emotional_visual_intent=emotional_visual_intent or segment.emotional_intent,
        previous_beat_id=prev_id,
        visual_mode=mode,
        duration_policy=hold["policy"],
        duration_sec=timeline_dur,
        transition_intent="cut",
        coverage=coverage,
        prompt_provenance={
            "mode_reason": mode_reason,
            "camera_shot": shot,
            "confidence": OBS_HEURISTIC,
            "asset_hold_max_sec": hold.get("max_hold_sec"),
            "asset_hold_target_sec": hold.get("duration_sec"),
            "timeline_source": "dialogue_segment_duration",
            "covered_dialogue_ids": [segment.dialogue_id or segment.segment_id],
            "purpose": segment.semantic_purpose or narrative.event or "",
            "reuse_policy": "semantic_beat_compatibility",
        },
        risks=list(hold.get("risks") or []),
        order=order,
    )


def evaluate_intent_coverage(
    *,
    segment: DialogueSegment,
    entities: Sequence[GroundedEntity],
    relations: Sequence[GroundedRelation],
    location: str,
    action: str,
) -> VisualCoverage:
    """Intent planning coverage — never claims artifact observation."""
    required_ents = [e for e in entities if e.required]
    has_person = any(e.entity_type == "person" for e in required_ents)
    has_obj = any(e.entity_type in ("object", "document", "vehicle") for e in required_ents)
    has_rel = bool(relations)
    has_loc = bool((location or "").strip())
    has_act = bool((action or "").strip())

    def _dim(ok: bool, applicable: bool) -> str:
        if not applicable:
            return COVERAGE_UNKNOWN
        return COVERAGE_FULL if ok else COVERAGE_NONE

    subject = _dim(has_person or bool(segment.speaker), True)
    entity = _dim(bool(required_ents), True)
    obj = _dim(has_obj, has_obj or "object" in segment.text.lower() or "document" in segment.text.lower() or "car" in segment.text.lower())
    # If dialogue implies object but missing → NONE
    needs_obj = bool(re.search(r"\b(suzuki|car|truck|document|desk|phone|object)\b", segment.text, re.I))
    if needs_obj and not has_obj:
        obj = COVERAGE_NONE
    rel = _dim(has_rel, bool(re.search(r"\b(beside|inside|holding|looking|behind|on the)\b", segment.text, re.I)))
    if re.search(r"\b(beside|inside|holding|looking|behind)\b", segment.text, re.I) and not has_rel:
        rel = COVERAGE_NONE
    loc_c = _dim(has_loc, bool(re.search(r"\b(office|hospital|station|kitchen|beach|studio|room)\b", segment.text, re.I)) or has_loc)
    act_c = _dim(has_act, True)

    dims = [subject, entity, obj, rel, loc_c, act_c]
    if all(d == COVERAGE_FULL for d in dims if d != COVERAGE_UNKNOWN):
        overall = COVERAGE_FULL
    elif any(d == COVERAGE_NONE for d in dims):
        overall = COVERAGE_PARTIAL if any(d == COVERAGE_FULL for d in dims) else COVERAGE_NONE
    else:
        overall = COVERAGE_UNKNOWN

    return VisualCoverage(
        subject=subject,
        action=act_c,
        entity=entity,
        object=obj,
        relationship=rel,
        location=loc_c if loc_c != COVERAGE_UNKNOWN else (COVERAGE_FULL if has_loc else COVERAGE_UNKNOWN),
        temporal=COVERAGE_UNKNOWN,
        overall=overall,
        confidence=OBS_HEURISTIC,
    )


def visual_beat_to_scene_intent(
    beat: DirectedVisualBeat,
    segment: DialogueSegment,
    bible: VisualBible,
) -> SceneIntent:
    """Project directed visual beat onto canonical SceneIntent — no second scene engine."""
    entities = [e.to_semantic_entity() for e in beat.required_entities]
    relations = [r.to_entity_relation() for r in beat.relationships]
    shot = map_camera_intent(beat.camera_intent)
    return SceneIntent.model_validate(
        {
            "scene_id": beat.scene_id,
            "dialogue_id": segment.dialogue_id,
            "summary": segment.semantic_intent or segment.text,
            "dialogue_intent": segment.text,
            "primary_action": (beat.character_state or {}).get("action") or "",
            "actors": [beat.character_state.get("identity")] if beat.character_state.get("identity") else [],
            "entities": [e.model_dump() for e in entities],
            "relations": [r.model_dump() for r in relations],
            "location": (beat.location_state or {}).get("location") or bible.location,
            "environment": (beat.environment_state or {}).get("environment") or bible.environment,
            "required_objects": list(beat.required_objects),
            "emotional_intent": beat.emotional_visual_intent,
            "visual_intent": segment.text,
            "shot_type": shot,
            "shot_purpose": f"narrative:{beat.camera_intent}",
            "camera_motion": "",
            "framing": beat.composition,
            "transition_intent": beat.transition_intent,
            "visual_bible_id": bible.bible_id,
            "visual_bible_version": bible.version,
            "visual_mode": beat.visual_mode,
            "continuity_expected": True,
            "narrative_change_allowed": False,
            "continuity_refs": {
                "wardrobe": (beat.character_state or {}).get("wardrobe") or bible.wardrobe,
                "lighting": beat.lighting_intent or bible.lighting,
                "lighting_intent": beat.lighting_intent or bible.lighting,
                "camera_language": bible.camera_language,
                "lighting_continuity": beat.lighting_continuity,
                "explicit_lighting": bool(beat.lighting_intent or bible.lighting),
                "explicit_relationships": bool(beat.relationships),
                "required_relationships": [
                    f"{r.source_id}:{r.relation_type}:{r.target_id}" for r in (beat.relationships or [])
                ],
            },
            "metadata": {
                "style": bible.visual_style,
                "c05s_visual_beat_id": beat.beat_id,
                "c05s_narrative_beat_id": beat.narrative_beat_id,
                "explicit_lighting": bool(beat.lighting_intent or bible.lighting),
                "explicit_relationships": bool(beat.relationships),
            },
        }
    )


def compile_beat_prompt(
    *,
    beat: DirectedVisualBeat,
    segment: DialogueSegment,
    bible: VisualBible,
    delta: Optional[SceneVisualDelta] = None,
) -> dict[str, Any]:
    """Canonical prompt compiler via Visual Bible + SceneIntent."""
    intent = visual_beat_to_scene_intent(beat, segment, bible)
    delta = delta or SceneVisualDelta(
        must_appear=list(beat.required_objects),
        action=(beat.character_state or {}).get("action") or "",
        camera_intent=beat.camera_intent,
        must_persist=[e.label for e in beat.required_entities if e.continuity == "MUST_PERSIST"],
    )
    out = compile_visual_prompt(
        bible=bible, intent=intent, delta=delta, visual_mode=beat.visual_mode
    )
    beat.scene_contract_id = out["contract"]["contract_id"]
    beat.prompt_provenance = {
        **beat.prompt_provenance,
        **out["provenance"],
        "observation_claim": "EXPECTED_VISUAL_ONLY",
        "artifact_observation": False,
    }
    return {
        "ok": True,
        "beat": beat.to_dict(),
        "compiled": out["compiled"],
        "provenance": beat.prompt_provenance,
        "intent": out["intent"],
    }


def decompose_dialogue_to_visual_beats(
    *,
    segments: Sequence[DialogueSegment],
    bible: VisualBible,
    prefer_image_fallback: bool = False,
    default_camera: str = "MEDIUM",
) -> dict[str, Any]:
    """
    Dialogue → Narrative beats → Visual beats.

    VIDEO (Agnes) is primary. prefer_image_fallback only authorizes still plates
    for static-mood beats — it must NOT force IMAGE on every beat.
    """
    narrative_beats: list[NarrativeBeat] = []
    visual_beats: list[DirectedVisualBeat] = []
    prev_nb_loc = ""
    prev_emotion = ""
    prev_subject = ""
    prev_object = ""
    prev_action = ""
    prev_tokens: set[str] = set()
    prev_vb: Optional[DirectedVisualBeat] = None

    for i, seg in enumerate(segments):
        nb = create_narrative_beat(
            beat_id=f"nb-{seg.segment_id}",
            segment=seg,
            order=i,
            previous_location=prev_nb_loc,
            previous_emotion=prev_emotion,
            previous_subject=prev_subject,
            previous_object=prev_object,
            previous_action=prev_action,
            previous_content_tokens=prev_tokens,
        )
        narrative_beats.append(nb)

        # Visual hold vs new beat:
        # - expansion decides HOW MANY beats (semantic change → always new)
        # - hold policy decides WHETHER one asset may cover more dialogue (max_hold_sec)
        # - hold MUST NOT rewrite timeline duration down to 8s / truncate the script
        create_new = True
        if prev_vb is not None and not nb.visual_change_candidate:
            proposed = float(prev_vb.duration_sec) + float(seg.duration_sec)
            hold = decide_visual_hold_policy(
                dialogue_duration_sec=proposed,
                semantic_beat_count=1,
                motion_available=prev_vb.visual_mode != MODE_IMAGE,
            )
            max_hold = float(hold.get("max_hold_sec") or hold.get("duration_sec") or 8.0)
            if proposed <= max_hold + 1e-6:
                create_new = False
                prev_vb.duration_sec = proposed
                prev_vb.duration_policy = hold["policy"]
                covered = list((prev_vb.prompt_provenance or {}).get("covered_dialogue_ids") or [])
                did = seg.dialogue_id or seg.segment_id
                if did and did not in covered:
                    covered.append(did)
                prev_vb.prompt_provenance = dict(prev_vb.prompt_provenance or {})
                prev_vb.prompt_provenance["covered_dialogue_ids"] = covered
                prev_vb.prompt_provenance["hold_extended"] = True
                for r in hold.get("risks") or []:
                    if r not in prev_vb.risks:
                        prev_vb.risks.append(r)
            # else: hold budget exceeded → force new visual beat (same subject OK)
        if create_new:
            mode = ""
            if prefer_image_fallback:
                # Only authorize IMAGE_WITH_MOTION for clearly static plates.
                # Never blanket-force IMAGE for the whole film (industrial VIDEO-first).
                from pipeline.media_mode_engine import decide_media_mode

                md = decide_media_mode(
                    primary_action=nb.action,
                    narration=str(seg.text or ""),
                    element=str(getattr(seg, "section_role", "") or ""),
                    prefer_image_fallback=True,
                    visual_change_candidate=bool(nb.visual_change_candidate),
                    static_sufficient=not bool(nb.visual_change_candidate),
                    beat_index=i,
                    total_beats=len(segments),
                )
                mode = str(md.get("mode") or MODE_VIDEO)
            cam = "ESTABLISHING" if i == 0 else (
                "CLOSE" if "document" in seg.text.lower() or "opened" in seg.text.lower() else default_camera
            )
            vb = build_directed_visual_beat(
                beat_id=f"vb-{seg.segment_id}",
                segment=seg,
                narrative=nb,
                bible=bible,
                previous=prev_vb,
                camera_intent=cam,
                visual_mode=mode,
                order=len(visual_beats),
            )
            if prev_vb is not None:
                prev_vb.next_beat_id = vb.beat_id
            visual_beats.append(vb)
            prev_vb = vb

        prev_nb_loc = (prev_vb.location_state or {}).get("location") if prev_vb else seg.location
        prev_emotion = seg.emotional_intent or prev_emotion
        prev_subject = nb.semantic_subject or prev_subject
        prev_object = nb.important_object or prev_object
        prev_action = nb.action or prev_action
        prev_tokens = _semantic_content_tokens(seg.text)

    # Link next pointers
    for i in range(len(visual_beats) - 1):
        visual_beats[i].next_beat_id = visual_beats[i + 1].beat_id

    repetition = detect_visual_repetition(visual_beats)
    for w in repetition:
        for bid in w.get("beat_ids") or []:
            for vb in visual_beats:
                if vb.beat_id == bid and VISUAL_REPETITION_RISK not in vb.risks:
                    vb.risks.append(VISUAL_REPETITION_RISK)

    return sanitize_story_metadata(
        {
            "ok": True,
            "narrative_beats": [n.to_dict() for n in narrative_beats],
            "visual_beats": [v.to_dict() for v in visual_beats],
            "repetition_warnings": repetition,
            "image_fallback": prefer_image_fallback,
            "authorities": {
                "scene_intent": "domain.scene_intent.SceneIntent",
                "visual_bible": "pipeline.visual_intelligence.VisualBible",
                "continuity": "pipeline.visual_semantic.continuity.ContinuityTracker",
                "prompt": "pipeline.multimodal_consistency.prompt_compiler",
                "fallback_visual_beat": "pipeline.fallback_image_video.VisualBeat (adapter-local; not planning authority)",
            },
            "paid_api_calls": 0,
        }
    )


def validate_story_direction_plan(
    *,
    segments: Sequence[DialogueSegment],
    narrative_beats: Sequence[NarrativeBeat],
    visual_beats: Sequence[DirectedVisualBeat],
    bible: VisualBible,
) -> dict[str, Any]:
    """Pre-generation validation — BLOCK deterministic contradictions; HEURISTIC warnings; UNKNOWN observation."""
    blocks: list[str] = []
    warnings: list[str] = []
    unknowns: list[str] = []

    seg_ids = {s.segment_id for s in segments}
    for s in segments:
        if s.visual_relevance != "none" and not any(v.dialogue_segment_id == s.segment_id for v in visual_beats):
            # May be intentional hold covering prior visual — check narrative
            nb = next((n for n in narrative_beats if n.dialogue_segment_id == s.segment_id), None)
            if nb and nb.visual_change_candidate:
                blocks.append(f"dialogue_without_visual_intent:{s.segment_id}")
            elif not visual_beats:
                blocks.append(f"dialogue_without_visual_intent:{s.segment_id}")

    for vb in visual_beats:
        if vb.dialogue_segment_id not in seg_ids:
            blocks.append(f"orphan_visual_beat:{vb.beat_id}")
        if vb.coverage.overall == COVERAGE_NONE:
            blocks.append(f"required_coverage_none:{vb.beat_id}")
        if vb.coverage.relationship == COVERAGE_NONE:
            blocks.append(f"required_relationship_missing:{vb.beat_id}")
        # PART-5C: relational cue in covered dialogue without relationship identity
        seg = next((s for s in segments if s.segment_id == vb.dialogue_segment_id), None)
        if seg and text_has_relationship_cues(seg.text) and not (vb.relationships or []):
            blocks.append(f"relationship_cue_without_identity:{vb.beat_id}")
        if not str(vb.lighting_intent or "").strip() or vb.lighting_continuity == LIGHTING_UNKNOWN:
            blocks.append(f"missing_lighting_contract:{vb.beat_id}")
        if vb.coverage.object == COVERAGE_NONE:
            blocks.append(f"required_entity_missing:{vb.beat_id}")
        if vb.visual_mode not in SUPPORTED_VISUAL_MODES:
            blocks.append(f"unsupported_visual_mode:{vb.visual_mode}")
        try:
            map_camera_intent(vb.camera_intent)
        except ValueError as exc:
            blocks.append(str(exc))

        # Location contradiction: NEW_LOCATION without dialogue cue already handled in narrative;
        # camera change must preserve location when SAME_LOCATION
        if vb.previous_beat_id:
            prev = next((x for x in visual_beats if x.beat_id == vb.previous_beat_id), None)
            if prev:
                prev_loc = str((prev.location_state or {}).get("location") or "").lower()
                cur_loc = str((vb.location_state or {}).get("location") or "").lower()
                cont = str((vb.location_state or {}).get("continuity") or SAME_LOCATION)
                if cont == SAME_LOCATION and prev_loc and cur_loc and prev_loc != cur_loc:
                    blocks.append(f"contradictory_location:{vb.beat_id}")
                # Lighting: arbitrary reset blocked
                if (
                    vb.lighting_continuity == LIGHTING_INHERITED
                    and prev.lighting_intent
                    and vb.lighting_intent
                    and prev.lighting_intent != vb.lighting_intent
                    and not vb.lighting_intent.startswith(prev.lighting_intent)
                ):
                    blocks.append(f"invalid_lighting_transition:{vb.beat_id}")
                # Character identity drift
                prev_id = str((prev.character_state or {}).get("identity") or "").lower()
                cur_id = str((vb.character_state or {}).get("identity") or "").lower()
                if prev_id and cur_id and prev_id != cur_id:
                    # allow if narrative subject changed explicitly
                    nb = next((n for n in narrative_beats if n.beat_id == vb.narrative_beat_id), None)
                    if not nb or "subject_change" not in (nb.visual_change_reason or ""):
                        blocks.append(f"character_contradiction:{vb.beat_id}")

        if VISUAL_HOLD_RISK in (vb.risks or []):
            warnings.append(f"{VISUAL_HOLD_RISK}:{vb.beat_id}")
        if VISUAL_REPETITION_RISK in (vb.risks or []):
            warnings.append(f"{VISUAL_REPETITION_RISK}:{vb.beat_id}")

        # Localization: bible must match beat references
        if vb.visual_bible_id and vb.visual_bible_id != bible.bible_id:
            blocks.append(f"localization_visual_bible_mismatch:{vb.beat_id}")

        # Coverage UNKNOWN for temporal always
        if vb.coverage.temporal == COVERAGE_UNKNOWN:
            unknowns.append(f"temporal_coverage_unknown:{vb.beat_id}")

    # Unrelated dialogue cannot share one visual automatically — if one visual lists multiple segment ids (not supported) 
    # Check: multiple narrative change candidates mapped to fewer visuals without hold reason
    change_nbs = [n for n in narrative_beats if n.visual_change_candidate]
    if len(change_nbs) > len(visual_beats):
        warnings.append("unrelated_dialogue_may_share_visual")

    blocked = bool(blocks)
    return sanitize_story_metadata(
        {
            "ok": not blocked,
            "blocked": blocked,
            "blocks": blocks,
            "warnings": warnings,
            "unknowns": unknowns,
            "warning_confidence": OBS_HEURISTIC,
            "unknown_confidence": OBS_UNKNOWN,
            "observation_boundary": "artifact_verification + multimodal_consistency (not C05-S)",
            "paid_api_calls": 0,
        }
    )


def apply_emotion_to_segment(
    segment: DialogueSegment,
    voice: VoiceIdentity,
    emotion: SceneEmotionState,
) -> AudioIntent:
    """C05-Q emotion integration — voice stable, emotion may change."""
    base = AudioIntent(
        language=segment.language,
        emphasis=list(segment.emphasis or []),
    )
    ai = apply_voice_identity_to_audio_intent(base, voice, emotion)
    return record_tts_capability_limitations(ai, provider=voice.provider or "mock")


def localization_direction_safe(
    *,
    master_bible: VisualBible,
    lang_bible: VisualBible,
    master_beats: Sequence[DirectedVisualBeat],
    lang_beats: Sequence[DirectedVisualBeat],
) -> dict[str, Any]:
    """Language may change dialogue; visual identity must not unnecessarily change."""
    issues = []
    if master_bible.bible_id != lang_bible.bible_id or master_bible.character_identity != lang_bible.character_identity:
        issues.append("visual_bible_identity_drift")
    if master_bible.location != lang_bible.location:
        issues.append("location_identity_drift")
    if len(master_beats) != len(lang_beats):
        issues.append("beat_count_mismatch")
    else:
        for a, b in zip(master_beats, lang_beats):
            if (a.character_state or {}).get("identity") != (b.character_state or {}).get("identity"):
                issues.append(f"character_drift:{a.beat_id}")
            if (a.location_state or {}).get("location") != (b.location_state or {}).get("location"):
                issues.append(f"location_drift:{a.beat_id}")
            if a.camera_intent != b.camera_intent:
                issues.append(f"camera_language_drift:{a.beat_id}")
    return {
        "ok": not issues,
        "issues": issues,
        "note": "dialogue/subtitle/timing may differ; identity must not",
    }


def plan_visual_beat_repair(
    *,
    beat_id: str,
    scene_id: str,
    issue_message: str,
    all_beat_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Reuse BUILD-04F via C05-Q — no VisualRepairEngine."""
    out = plan_consistency_repair(
        scene_id=scene_id,
        issue_domain="visual",
        issue_message=f"{beat_id}:{issue_message}",
        all_scene_ids=list(all_beat_ids or [beat_id]),
    )
    out["affected_beat_id"] = beat_id
    out["visual_repair_engine"] = False
    return out


def architecture_integrity_snapshot() -> dict[str, Any]:
    return {
        "scene_intent_authority": "domain.scene_intent.SceneIntent",
        "second_scene_intent": False,
        "visual_bible_authority": "pipeline.visual_intelligence.VisualBible",
        "second_visual_bible": False,
        "continuity_authority": "pipeline.visual_semantic.continuity.ContinuityTracker",
        "second_continuity_engine": False,
        "audio_authority": "domain.scene.AudioPlan",
        "second_audio_engine": False,
        "voice_identity_authority": "pipeline.production_consistency.VoiceIdentity",
        "quality_authority": "pipeline.quality",
        "second_quality_engine": False,
        "repair_authority": "pipeline.quality.repair_planner",
        "second_repair_engine": False,
        "second_camera_engine": False,
        "second_timeline_engine": False,
        "second_image_engine": False,
        "second_video_engine": False,
        "second_localization_engine": False,
        "prompt_authority": "pipeline.multimodal_consistency.prompt_compiler",
        "multimodal_authority": "pipeline.multimodal_consistency",
        "multimodal_evidence_projection": "pipeline.multimodal_consistency.evidence_projection",
        "multimodal_evidence_projection_is_not_publishability_gate": True,
        "multimodal_evidence_projection_is_not_second_semantic_gate": True,
        "artifact_authority": "pipeline.artifact_verification",
        "planning_visual_beat": "pipeline.story_visual_direction.DirectedVisualBeat",
        "fallback_visual_beat_non_authority": "pipeline.fallback_image_video.VisualBeat",
        "l3_status": "DEFERRED_UNKNOWN_WITHOUT_VLM_CV",
        "scene_boundary_observation": "pipeline.observation.scene_boundary",
        "scene_boundary_is_not_continuity_authority": True,
        "visual_retrieval": "pipeline.retrieval",
        "visual_retrieval_is_not_semantic_authority": True,
        "visual_retrieval_is_not_continuity_authority": True,
        "openmontage_agpl_imported": False,
        "frame_evidence_observation": "pipeline.observation.frame_evidence",
        "frame_sampling_observation": "pipeline.observation.frame_sampling",
        "frame_evidence_cross_beat": "pipeline.observation.frame_evidence.cross_beat",
        "frame_evidence_alignment": "pipeline.observation.frame_evidence.alignment",
        "frame_evidence_is_not_continuity_authority": True,
        "frame_evidence_is_not_semantic_gate": True,
        "frame_evidence_is_not_ffmpeg_engine": True,
        "frame_evidence_is_not_identity_certification_engine": True,
        "cross_beat_is_not_second_continuity_engine": True,
        "alignment_is_not_second_duration_engine": True,
        "alignment_is_not_second_pacing_authority": True,
        "alignment_is_not_second_audio_engine": True,
        "audio_evidence_observation": "pipeline.observation.audio_evidence",
        "audio_evidence_is_not_audio_authority": True,
        "audio_evidence_is_not_voice_identity_authority": True,
        "audio_evidence_is_not_asr_engine": True,
        "audio_evidence_is_not_subtitle_engine": True,
        "acoustic_voice_observation": "pipeline.observation.audio_evidence.acoustic",
        "acoustic_embedding_integrated": False,
        "acoustic_voice_identity_defaults_to_unknown": True,
    }


def attach_frame_observation_evidence(
    *,
    media_path: str | Path,
    beat: DirectedVisualBeat | dict[str, Any],
    work_dir: str | Path,
    retrieval_evidence: Optional[dict[str, Any]] = None,
    customer_id: str = "",
    channel_id: str = "",
    visual_contract: Optional[dict[str, Any]] = None,
    continuity_constraints: Optional[dict[str, Any]] = None,
    allow_heuristic_fixture: bool = False,
    fixture_caption: str = "",
) -> dict[str, Any]:
    """Sample frames and attach observation/coverage evidence (not a new authority)."""
    from pipeline.observation.frame_evidence import (
        beat_frame_coverage,
        bridge_retrieval_to_frame_observation,
        compare_temporal_frames,
        observe_frames,
        repair_handoff_from_frame_evidence,
    )
    from pipeline.observation.frame_sampling import sample_frames

    if retrieval_evidence:
        bridged = bridge_retrieval_to_frame_observation(
            retrieval_evidence=retrieval_evidence,
            beat=beat,
            work_dir=work_dir,
            allow_heuristic_fixture=allow_heuristic_fixture,
            fixture_caption=fixture_caption,
            requester_customer_id=customer_id,
            requester_channel_id=channel_id,
            visual_contract=visual_contract,
            continuity_constraints=continuity_constraints,
        )
    else:
        b = beat.to_dict() if hasattr(beat, "to_dict") else dict(beat or {})
        sampled = sample_frames(
            media_path,
            out_dir=Path(work_dir) / "frame_samples",
            asset_id=str(b.get("beat_id") or ""),
            scene_id=str(b.get("scene_id") or ""),
            beat_id=str(b.get("beat_id") or ""),
            customer_id=customer_id,
            channel_id=channel_id,
        )
        expected = {
            "subject": (b.get("character_state") or {}).get("identity") or "",
            "entities": [
                (e.get("label") if isinstance(e, dict) else getattr(e, "label", str(e)))
                for e in (b.get("required_entities") or [])
            ],
            "location": (b.get("location_state") or {}).get("location") or "",
            "relationships": [],
            "camera": b.get("camera_intent") or "",
            "lighting": b.get("lighting_intent") or "",
        }
        observations = observe_frames(
            sampled.get("frames") or [],
            expected=expected,
            allow_heuristic_fixture=allow_heuristic_fixture,
            fixture_caption=fixture_caption,
        )
        bridged = {
            "status": sampled.get("status"),
            "sampling": sampled,
            "observations": observations,
            "temporal": compare_temporal_frames(
                observations,
                visual_contract=visual_contract,
                continuity_constraints=continuity_constraints,
            ),
            "coverage": beat_frame_coverage(b, observations),
            "unknown_as_pass": False,
        }

    repair = repair_handoff_from_frame_evidence(
        beat_id=str((beat.to_dict() if hasattr(beat, "to_dict") else beat).get("beat_id") or ""),
        scene_id=str((beat.to_dict() if hasattr(beat, "to_dict") else beat).get("scene_id") or ""),
        frame_bridge_or_temporal=bridged,
    )
    return {
        "frame_observation": bridged,
        "repair_handoff": repair,
        "creates_final_gate": False,
        "does_not_replace": [
            "DirectedVisualBeat",
            "ContinuityTracker",
            "semantic_coverage",
            "BUILD-04F",
            "compose.ffmpeg",
        ],
        "unknown_as_pass": False,
    }


def attach_visual_retrieval_evidence(
    beat: DirectedVisualBeat | dict[str, Any],
    *,
    index_root: str | Path,
    local_corpus: str | Path | None = None,
    pexels_api_key: str = "",
    scene_intent: Optional[dict[str, Any]] = None,
    visual_contract: Optional[dict[str, Any]] = None,
    customer_id: str = "",
    channel_id: str = "",
    prior_assets: Optional[list[dict[str, Any]]] = None,
    allow_hash_embedder: bool = False,
) -> dict[str, Any]:
    """Candidate real-footage retrieval for a directed beat (evidence only).

    Does not replace SceneIntent / ContinuityTracker / C05-MR / semantic coverage.
    Does not publish, approve, repair, or grant publishability PASS.
    """
    from pipeline.retrieval.bridge import attach_retrieval_evidence

    return attach_retrieval_evidence(
        beat,
        index_root=str(index_root),
        local_corpus=str(local_corpus) if local_corpus else None,
        pexels_api_key=pexels_api_key,
        scene_intent=scene_intent,
        visual_contract=visual_contract,
        customer_id=customer_id,
        channel_id=channel_id,
        prior_assets=prior_assets,
        allow_hash_embedder=allow_hash_embedder,
    )


def attach_scene_boundary_evidence(
    video_path: str | Path,
    *,
    planned_beats: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Observe actual cuts and compare to C05-S planned beats (evidence only).

    Does not replace DirectedVisualBeat / ContinuityTracker / Director Plan.
    Does not create a final gate.
    """
    from pathlib import Path as _P

    from pipeline.observation.scene_boundary import (
        compare_planned_beats_vs_boundaries,
        observe_scene_boundaries,
    )

    obs = observe_scene_boundaries(_P(video_path))
    comparison = compare_planned_beats_vs_boundaries(
        planned_beats=list(planned_beats or []),
        observed=obs,
    )
    return {
        "scene_boundary_observation": obs,
        "planned_vs_observed": comparison,
        "creates_final_gate": False,
        "does_not_replace": ["DirectedVisualBeat", "ContinuityTracker", "DirectorPlan"],
        "unknown_as_pass": False,
    }
