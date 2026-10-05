"""Scene-to-scene continuity tracking — sole ContinuityTracker authority (T004-C3 + AMP-004 P03).

PREVENTION-FIRST: build structured constraints BEFORE generation.
Detection via validate_continuity remains a secondary safety net.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from domain.scene_intent import SceneIntent
from pipeline.visual_semantic.contracts import SemanticIssue, SemanticIssueCode, VisualAnalysisMetadata

CONTINUITY_STATE_FILE = "CONTINUITY_STATE.json"

# Mutually exclusive action groups (pre-generation)
_CONFLICT_PAIRS = [
    ({"drink", "drinking"}, {"eat", "eating"}),
    ({"drink", "drinking"}, {"cut", "cutting"}),
    ({"sit", "sitting", "seated"}, {"stand", "standing", "walk", "walking"}),
    ({"hold_phone", "holding phone"}, {"empty_hands", "hands empty"}),
]

# RCP-06C: exclusive camera / lighting families (only when BOTH sides explicit)
_CAMERA_FAMILIES: dict[str, set[str]] = {
    "close": {"close", "closeup", "close-up", "ecu", "cu", "tight", "macro"},
    "medium": {"medium", "ms", "waist", "medium-shot"},
    "wide": {"wide", "ws", "establishing", "long shot", "full shot", "full-shot"},
    "aerial": {"aerial", "drone", "top-down", "overhead", "bird"},
    "pov": {"pov", "first-person", "fpv", "subjective"},
}

_LIGHTING_FAMILIES: dict[str, set[str]] = {
    "day": {"day", "daylight", "sunny", "noon", "sunlit"},
    "night": {"night", "nocturnal", "moonlight", "moon-lit"},
    "dark": {"dark", "silhouette", "unlit", "low-key", "lowkey"},
    "bright": {"bright", "high-key", "highkey", "overexposed"},
    "warm": {"warm", "golden", "sunset", "candle", "tungsten"},
    "cool": {"cool", "blue hour", "cold", "fluorescent"},
}

# Exclusive family pairs (hard contradiction when both explicit)
_CAMERA_EXCLUSIVE = (
    ({"close"}, {"wide", "aerial"}),
    ({"pov"}, {"aerial"}),
    ({"close"}, {"aerial"}),
)
_LIGHTING_EXCLUSIVE = (
    ({"day"}, {"night"}),
    ({"bright"}, {"dark"}),
    ({"warm"}, {"cool"}),
)

_RELATION_NORMALIZE = {
    "beside": "beside",
    "next_to": "beside",
    "next-to": "beside",
    "adjacent": "beside",
    "alongside": "beside",
    "inside": "inside",
    "in": "inside",
    "within": "inside",
    "outside": "outside",
    "holding": "holding",
    "holds": "holding",
    "held_by": "holding",
    "uses": "holding",
    "sitting-with": "sitting_with",
    "sitting_with": "sitting_with",
    "sits_with": "sitting_with",
    "with": "sitting_with",
    "separated": "separated",
    "apart": "separated",
    "alone": "separated",
    "far": "far",
    "opposite": "far",
    "away": "far",
}

_RELATION_OPPOSITES: dict[str, set[str]] = {
    "beside": {"inside", "far", "outside"},
    "inside": {"beside", "outside", "far"},
    "outside": {"inside"},
    "holding": {"separated", "far"},
    "sitting_with": {"separated", "far"},
    "separated": {"sitting_with", "holding"},
    "far": {"beside", "inside", "sitting_with", "holding"},
}


def _family_hits(text: str, families: dict[str, set[str]]) -> set[str]:
    t = (text or "").lower()
    if not t.strip():
        return set()
    hits: set[str] = set()
    for name, keys in families.items():
        if any(k in t for k in keys):
            hits.add(name)
    return hits


def _exclusive_pair_hit(a: set[str], b: set[str], pairs: tuple[tuple[set[str], set[str]], ...]) -> bool:
    for left, right in pairs:
        if (a & left and b & right) or (a & right and b & left):
            return True
    return False


def _normalize_relation_type(raw: str) -> str:
    key = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    key = key.replace("__", "_")
    # also try hyphen form
    alt = (raw or "").strip().lower()
    if alt in _RELATION_NORMALIZE:
        return _RELATION_NORMALIZE[alt]
    if key in _RELATION_NORMALIZE:
        return _RELATION_NORMALIZE[key]
    # sitting_with variants
    if "sit" in key and "with" in key:
        return "sitting_with"
    if key in ("beside", "inside", "outside", "holding", "sitting_with", "separated", "far"):
        return key
    return key


def _parse_relationship_token(token: str) -> Optional[tuple[str, str, str]]:
    parts = [p.strip() for p in str(token or "").split(":")]
    if len(parts) != 3 or not parts[0] or not parts[1] or not parts[2]:
        return None
    return parts[0].lower(), _normalize_relation_type(parts[1]), parts[2].lower()


def _relationship_pair_key(src: str, tgt: str) -> tuple[str, str]:
    a, b = src.lower(), tgt.lower()
    return (a, b) if a <= b else (b, a)


def _relationships_contradict(prev_tokens: list[str], cur_tokens: list[str]) -> Optional[dict[str, Any]]:
    """Return evidence dict if explicit prior vs current relationship types oppose."""
    prev_map: dict[tuple[str, str], set[str]] = {}
    for tok in prev_tokens:
        parsed = _parse_relationship_token(tok)
        if not parsed:
            continue
        src, rel, tgt = parsed
        prev_map.setdefault(_relationship_pair_key(src, tgt), set()).add(rel)
    for tok in cur_tokens:
        parsed = _parse_relationship_token(tok)
        if not parsed:
            continue
        src, rel, tgt = parsed
        key = _relationship_pair_key(src, tgt)
        prior = prev_map.get(key) or set()
        if not prior:
            continue
        for p_rel in prior:
            opp = _RELATION_OPPOSITES.get(p_rel) or set()
            if rel in opp:
                return {
                    "pair": list(key),
                    "previous_relation": p_rel,
                    "current_relation": rel,
                    "note": "heuristic_contract_compare_not_provider_verified",
                }
    return None


def extract_explicit_camera_contract(intent: SceneIntent) -> str:
    """Non-empty only when camera is an explicit contract (not adapter filler)."""
    refs = intent.continuity_refs or {}
    meta = intent.metadata or {}
    flagged = bool(refs.get("explicit_camera") or meta.get("explicit_camera"))
    parts = [
        str(intent.camera_position or "").strip(),
        str(intent.camera_motion or "").strip(),
        str(intent.framing or "").strip(),
    ]
    field_joined = " ".join(p for p in parts if p).strip()
    if flagged:
        return (
            str(refs.get("camera_language") or refs.get("camera") or refs.get("camera_intent") or "").strip()
            or field_joined
            or str(intent.shot_type or "").strip()
        )
    # Field-level explicit without relying on default "medium" filler in refs
    return field_joined


def extract_explicit_lighting_contract(intent: SceneIntent) -> str:
    """Non-empty only when lighting is an explicit contract (not adapter filler)."""
    refs = intent.continuity_refs or {}
    meta = intent.metadata or {}
    flagged = bool(refs.get("explicit_lighting") or meta.get("explicit_lighting"))
    if not flagged:
        return ""
    return str(
        refs.get("lighting")
        or refs.get("lighting_intent")
        or meta.get("lighting")
        or ""
    ).strip()


def extract_explicit_relationships(intent: SceneIntent) -> list[str]:
    """Explicit entity relationships from SceneIntent.relations (contractual)."""
    out: list[str] = []
    for rel in intent.relations or []:
        src = str(getattr(rel, "source_id", "") or "").strip()
        tgt = str(getattr(rel, "target_id", "") or "").strip()
        rtype = str(getattr(rel, "relation_type", "") or "").strip()
        if src and tgt and rtype:
            out.append(f"{src}:{_normalize_relation_type(rtype)}:{tgt}")
    refs = intent.continuity_refs or {}
    meta = intent.metadata or {}
    if refs.get("explicit_relationships") or meta.get("explicit_relationships"):
        for item in refs.get("required_relationships") or meta.get("required_relationships") or []:
            if isinstance(item, str) and item.count(":") == 2:
                parsed = _parse_relationship_token(item)
                if parsed:
                    out.append(f"{parsed[0]}:{parsed[1]}:{parsed[2]}")
            elif isinstance(item, dict):
                src = str(item.get("source_id") or item.get("source") or "").strip()
                tgt = str(item.get("target_id") or item.get("target") or "").strip()
                rtype = str(item.get("relation_type") or item.get("type") or "").strip()
                if src and tgt and rtype:
                    out.append(f"{src}:{_normalize_relation_type(rtype)}:{tgt}")
    # de-dupe
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq[:24]


@dataclass
class ContinuityState:
    """Authoritative persistent continuity — bound to scene identity."""

    character_id: str = ""
    appearance_ref: str = ""
    wardrobe: str = ""
    location: str = ""
    environment: str = ""
    important_objects: list[str] = field(default_factory=list)
    held_object: str = ""
    object_states: dict[str, str] = field(default_factory=dict)
    posture: str = ""
    ongoing_action: str = ""
    action_completed: list[str] = field(default_factory=list)
    time_context: str = ""
    spatial_notes: list[str] = field(default_factory=list)
    lighting: str = ""
    camera_language: str = ""
    emotional_state: str = ""
    scene_id: str = ""
    dialogue_id: str = ""
    revision_id: str = ""
    fingerprint: str = ""
    # RCP-06C — set only when prior scene had an explicit contract
    explicit_camera: bool = False
    explicit_lighting: bool = False
    required_relationships: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "appearance_ref": self.appearance_ref,
            "wardrobe": self.wardrobe,
            "location": self.location,
            "environment": self.environment,
            "important_objects": list(self.important_objects),
            "held_object": self.held_object,
            "object_states": dict(self.object_states),
            "posture": self.posture,
            "ongoing_action": self.ongoing_action,
            "action_completed": list(self.action_completed),
            "time_context": self.time_context,
            "spatial_notes": list(self.spatial_notes),
            "lighting": self.lighting,
            "camera_language": self.camera_language,
            "emotional_state": self.emotional_state,
            "scene_id": self.scene_id,
            "dialogue_id": self.dialogue_id,
            "revision_id": self.revision_id,
            "fingerprint": self.fingerprint,
            "explicit_camera": bool(self.explicit_camera),
            "explicit_lighting": bool(self.explicit_lighting),
            "required_relationships": list(self.required_relationships),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContinuityState":
        return cls(
            character_id=str(data.get("character_id") or ""),
            appearance_ref=str(data.get("appearance_ref") or ""),
            wardrobe=str(data.get("wardrobe") or ""),
            location=str(data.get("location") or ""),
            environment=str(data.get("environment") or ""),
            important_objects=[str(x) for x in (data.get("important_objects") or [])],
            held_object=str(data.get("held_object") or ""),
            object_states={str(k): str(v) for k, v in (data.get("object_states") or {}).items()},
            posture=str(data.get("posture") or ""),
            ongoing_action=str(data.get("ongoing_action") or ""),
            action_completed=[str(x) for x in (data.get("action_completed") or [])],
            time_context=str(data.get("time_context") or ""),
            spatial_notes=[str(x) for x in (data.get("spatial_notes") or [])],
            lighting=str(data.get("lighting") or ""),
            camera_language=str(data.get("camera_language") or ""),
            emotional_state=str(data.get("emotional_state") or ""),
            scene_id=str(data.get("scene_id") or ""),
            dialogue_id=str(data.get("dialogue_id") or ""),
            revision_id=str(data.get("revision_id") or ""),
            fingerprint=str(data.get("fingerprint") or ""),
            explicit_camera=bool(data.get("explicit_camera") or False),
            explicit_lighting=bool(data.get("explicit_lighting") or False),
            required_relationships=[str(x) for x in (data.get("required_relationships") or [])],
        )

    def compute_fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class ContinuityConstraints:
    """Structured pre-generation constraints — not free-form 'maintain continuity'."""

    required: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    required_character: str = ""
    required_location: str = ""
    required_posture: str = ""
    required_objects: list[str] = field(default_factory=list)
    required_held_object: str = ""
    required_wardrobe: str = ""
    negative_constraints: list[str] = field(default_factory=list)
    spatial_required: list[str] = field(default_factory=list)
    temporal_notes: list[str] = field(default_factory=list)
    lighting: str = ""
    camera_language: str = ""
    emotional_state: str = ""
    source_scene_id: str = ""
    source_fingerprint: str = ""
    mandatory: bool = True
    # RCP-06C — hard-check only when prior contract was explicit
    require_camera_contract: bool = False
    require_lighting_contract: bool = False
    required_relationships: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": list(self.required),
            "forbidden": list(self.forbidden),
            "required_character": self.required_character,
            "required_location": self.required_location,
            "required_posture": self.required_posture,
            "required_objects": list(self.required_objects),
            "required_held_object": self.required_held_object,
            "required_wardrobe": self.required_wardrobe,
            "negative_constraints": list(self.negative_constraints),
            "spatial_required": list(self.spatial_required),
            "temporal_notes": list(self.temporal_notes),
            "lighting": self.lighting,
            "camera_language": self.camera_language,
            "emotional_state": self.emotional_state,
            "source_scene_id": self.source_scene_id,
            "source_fingerprint": self.source_fingerprint,
            "mandatory": self.mandatory,
            "require_camera_contract": bool(self.require_camera_contract),
            "require_lighting_contract": bool(self.require_lighting_contract),
            "required_relationships": list(self.required_relationships),
        }

    def structured_continuity_section(self) -> str:
        parts = []
        if self.required_character:
            parts.append(f"SAME_CHARACTER={self.required_character}")
        if self.required_wardrobe:
            parts.append(f"SAME_WARDROBE={self.required_wardrobe}")
        if self.required_location:
            parts.append(f"SAME_LOCATION={self.required_location}")
        if self.required_posture:
            parts.append(f"CONTINUED_POSTURE={self.required_posture}")
        if self.required_objects:
            parts.append("REQUIRED_OBJECTS=" + ",".join(self.required_objects))
        if self.required_held_object:
            parts.append(f"HELD_OBJECT={self.required_held_object}")
        if self.spatial_required:
            parts.append("SPATIAL=" + ";".join(self.spatial_required))
        if self.temporal_notes:
            parts.append("TEMPORAL=" + ";".join(self.temporal_notes))
        if self.lighting:
            parts.append(f"LIGHTING={self.lighting}")
        if self.camera_language:
            parts.append(f"CAMERA={self.camera_language}")
        if self.required:
            parts.append("REQUIRED=" + ";".join(self.required))
        return " | ".join(parts)


class ContinuityError(RuntimeError):
    """Mandatory continuity failure — must not silently PASS."""

    def __init__(self, message: str, *, issues: Optional[list[SemanticIssue]] = None) -> None:
        super().__init__(message)
        self.issues = list(issues or [])


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))


def validate_impossible_action_combinations(intent: SceneIntent) -> list[SemanticIssue]:
    """Pre-generation: mutually exclusive actions/postures/object locations."""
    issues: list[SemanticIssue] = []
    actions = _tokens(intent.primary_action) | _tokens(" ".join(intent.secondary_actions))
    for verb in intent.action_order:
        actions |= _tokens(verb.action)
    for a, b in _CONFLICT_PAIRS:
        if actions & a and actions & b:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.CONFLICTING_ACTION,
                    message="Impossible simultaneous / mutually exclusive actions in SceneIntent.",
                    severity="CRITICAL",
                    evidence={"group_a": sorted(actions & a), "group_b": sorted(actions & b)},
                )
            )

    posture = (intent.posture or "").lower()
    if ("sit" in posture or "seated" in posture) and ("stand" in posture or "walk" in posture):
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.POSTURE_MISMATCH,
                message="Incompatible postures declared simultaneously.",
                severity="CRITICAL",
                evidence={"posture": intent.posture},
            )
        )

    # Object cannot be held and on table without place/put transition
    summary_l = (intent.summary or "").lower()
    secondary_l = " ".join(intent.secondary_actions).lower()
    if ("holding" in secondary_l or "holding" in summary_l) and "on the table" in summary_l:
        if "place" not in summary_l and "put" not in summary_l and "sets" not in summary_l:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.TEMPORAL_CONTRADICTION,
                    message="Object cannot simultaneously be held and on table without explicit place/put transition.",
                    severity="CRITICAL",
                    evidence={"summary": intent.summary[:120]},
                )
            )

    # Silent object substitution via forbidden vs required overlap of different types
    for fo in intent.forbidden_objects:
        for req in intent.required_objects:
            if fo.lower() != req.lower() and fo.lower() in ("dslr", "camera") and "phone" in req.lower():
                issues.append(
                    SemanticIssue(
                        code=SemanticIssueCode.UNEXPECTED_OBJECT,
                        message="Forbidden camera/object conflicts with required phone continuity.",
                        severity="HIGH",
                        evidence={"forbidden": fo, "required": req},
                    )
                )
    return issues


class ContinuityTracker:
    """Sole continuity authority — tracks + builds PRE-generation constraints."""

    def __init__(self) -> None:
        self._state: Optional[ContinuityState] = None
        self._descriptions: list[str] = []
        self._history: list[dict[str, Any]] = []

    @property
    def state(self) -> Optional[ContinuityState]:
        return self._state

    @property
    def prior_descriptions(self) -> list[str]:
        return list(self._descriptions)

    def initialize_from_intent(self, intent: SceneIntent) -> ContinuityState:
        """First scene: seed continuity state (no prior constraints)."""
        analysis = VisualAnalysisMetadata(
            source="HEURISTIC",
            actions=[intent.primary_action] if intent.primary_action else [],
            objects=list(intent.required_objects),
            location=intent.location,
            posture=intent.posture,
            description=intent.summary or intent.visual_emphasis,
            dialogue_id=intent.dialogue_id,
        )
        self.update_from_intent(intent, analysis)
        assert self._state is not None
        return self._state

    def build_constraints_for_next(self, next_intent: SceneIntent) -> ContinuityConstraints:
        """Build structured constraints from prior state for Scene N+1 — BEFORE generation."""
        if self._state is None:
            raise ContinuityError(
                "missing mandatory continuity state for subsequent scene",
                issues=[
                    SemanticIssue(
                        code=SemanticIssueCode.CONTINUITY_BREAK,
                        message="Mandatory continuity state missing before generation.",
                        severity="CRITICAL",
                        evidence={"scene_id": next_intent.scene_id},
                    )
                ],
            )

        prev = self._state
        if next_intent.narrative_change_allowed:
            return ContinuityConstraints(
                mandatory=False,
                source_scene_id=prev.scene_id,
                source_fingerprint=prev.fingerprint,
                temporal_notes=[f"narrative_change:{next_intent.continuity_exception_reason or 'allowed'}"],
            )

        required: list[str] = []
        forbidden: list[str] = [
            "unexplained character replacement",
            "unexplained clothing change",
            "unexplained location change",
            "unexplained posture change",
            "object silently transforms into another object",
            "object changes ownership without explicit event",
        ]
        neg = list(forbidden)

        if prev.character_id:
            required.append(f"same character identity: {prev.character_id}")
        if prev.wardrobe:
            required.append(f"same wardrobe: {prev.wardrobe}")
            neg.append(f"different wardrobe than {prev.wardrobe}")
        if prev.location and next_intent.continuity_expected:
            required.append(f"same location: {prev.location}")
            neg.append(f"different location than {prev.location}")
        if prev.posture and next_intent.continuity_expected:
            # Only require posture continuity if next doesn't declare an explicit transition action
            narr = (next_intent.summary or "").lower()
            if not any(w in narr for w in ("stand up", "stands up", "sit down", "walks away", "leaves")):
                required.append(f"continued posture: {prev.posture}")
        if prev.important_objects:
            required.append("preserve objects: " + ", ".join(prev.important_objects[:6]))
        if prev.held_object:
            narr = (next_intent.summary or "").lower()
            if any(w in narr for w in ("place", "put", "sets down", "puts down")):
                required.append(f"transition: release held object {prev.held_object}")
            else:
                required.append(f"still holding: {prev.held_object}")
                neg.append(f"{prev.held_object} disappears")
                neg.append(f"{prev.held_object} becomes a different object")

        for obj, st in prev.object_states.items():
            required.append(f"object_state {obj}={st}")

        spatial = list(prev.spatial_notes)
        temporal = []
        if prev.ongoing_action:
            temporal.append(f"prior_action={prev.ongoing_action}")
        if prev.action_completed:
            temporal.append("completed=" + ",".join(prev.action_completed[-4:]))
            forbidden.append("completed action silently reverts without transition")

        require_camera = bool(prev.explicit_camera and (prev.camera_language or "").strip())
        require_lighting = bool(prev.explicit_lighting and (prev.lighting or "").strip())
        required_rels = list(prev.required_relationships) if prev.required_relationships else []

        return ContinuityConstraints(
            required=required,
            forbidden=forbidden,
            required_character=prev.character_id,
            required_location=prev.location if next_intent.continuity_expected else "",
            required_posture=prev.posture if next_intent.continuity_expected else "",
            required_objects=list(prev.important_objects[:8]),
            required_held_object=prev.held_object,
            required_wardrobe=prev.wardrobe,
            negative_constraints=neg,
            spatial_required=spatial,
            temporal_notes=temporal,
            lighting=prev.lighting,
            camera_language=prev.camera_language,
            emotional_state=prev.emotional_state if next_intent.emotional_intent else "",
            source_scene_id=prev.scene_id,
            source_fingerprint=prev.fingerprint,
            mandatory=bool(next_intent.continuity_expected),
            require_camera_contract=require_camera,
            require_lighting_contract=require_lighting,
            required_relationships=required_rels,
        )

    def apply_constraints_to_intent(
        self,
        intent: SceneIntent,
        constraints: ContinuityConstraints,
    ) -> SceneIntent:
        """Merge continuity constraints into SceneIntent fields (canonical semantic source)."""
        data = intent.model_dump()
        refs = dict(data.get("continuity_refs") or {})
        refs["continuity_constraints"] = constraints.to_dict()
        refs["prior_fingerprint"] = constraints.source_fingerprint
        refs["prior_scene_id"] = constraints.source_scene_id
        if constraints.required_character and not data.get("actors"):
            data["actors"] = [constraints.required_character]
        if constraints.required_location and not (data.get("location") or "").strip():
            data["location"] = constraints.required_location
            data["environment"] = data.get("environment") or constraints.required_location
        if constraints.required_posture and not (data.get("posture") or "").strip():
            data["posture"] = constraints.required_posture
        if constraints.required_wardrobe:
            refs["wardrobe"] = constraints.required_wardrobe
        req_objs = list(data.get("required_objects") or [])
        for o in constraints.required_objects:
            if o and o.lower() not in [x.lower() for x in req_objs]:
                req_objs.append(o)
        data["required_objects"] = req_objs[:16]
        forb = list(data.get("forbidden_objects") or [])
        forb_act = list(data.get("forbidden_actions") or [])
        neg = list(data.get("negative_constraints") or [])
        for f in constraints.forbidden + constraints.negative_constraints:
            if f and f not in neg:
                neg.append(f)
        # High-salience object substitutions
        if constraints.required_held_object and "phone" in constraints.required_held_object.lower():
            for bad in ("dslr", "broadcast camera", "cinema camera", "separate giant camera"):
                if bad not in forb:
                    forb.append(bad)
                if bad not in neg:
                    neg.append(bad)
        data["forbidden_objects"] = forb[:24]
        data["forbidden_actions"] = forb_act[:24]
        data["negative_constraints"] = neg[:32]
        data["continuity_refs"] = refs
        data["continuity_expected"] = constraints.mandatory or intent.continuity_expected
        return SceneIntent(**data)

    def validate_pre_generation(
        self,
        intent: SceneIntent,
        constraints: Optional[ContinuityConstraints] = None,
    ) -> list[SemanticIssue]:
        """Pre-generation checks: missing state, unexplained breaks, impossible combos."""
        issues: list[SemanticIssue] = []
        issues.extend(validate_impossible_action_combinations(intent))

        if intent.continuity_expected and not intent.narrative_change_allowed:
            if self._state is None and constraints is None:
                issues.append(
                    SemanticIssue(
                        code=SemanticIssueCode.CONTINUITY_BREAK,
                        message="Mandatory continuity state missing before generation.",
                        severity="CRITICAL",
                        evidence={"scene_id": intent.scene_id},
                    )
                )
                return issues

        if constraints is None or not constraints.mandatory:
            return issues

        prev = self._state
        if prev is None:
            return issues

        # Unexplained character change — only when a *person* character is replaced
        # by a different *person* character. Documentary B-roll object subjects
        # (telescope → nebula) are not character-identity breaks (C11 FINAL).
        if constraints.required_character and intent.actors:
            actor = intent.actors[0].lower().strip()
            req = constraints.required_character.lower().strip()
            if req not in actor and actor not in req:
                narr_l = intent.summary.lower()
                if "another person" not in narr_l and "different person" not in narr_l:
                    _personish = {
                        "subject",
                        "person",
                        "man",
                        "woman",
                        "user",
                        "host",
                        "narrator",
                        "speaker",
                        "presenter",
                        "character",
                        "actor",
                        "girl",
                        "boy",
                        "child",
                    }

                    def _is_personish(name: str) -> bool:
                        n = (name or "").lower().strip()
                        if not n:
                            return False
                        if n in _personish:
                            return True
                        return any(p in n.split() for p in ("man", "woman", "person", "host", "narrator"))

                    if _is_personish(req) and _is_personish(actor):
                        issues.append(
                            SemanticIssue(
                                code=SemanticIssueCode.CONTINUITY_BREAK,
                                message="Unexplained character identity change before generation.",
                                severity="CRITICAL",
                                evidence={"required": constraints.required_character, "actors": intent.actors},
                            )
                        )

        # Unexplained location jump — only when next intent already had an explicit different location
        explicit_loc = bool((intent.metadata or {}).get("explicit_location"))
        if explicit_loc and constraints.required_location and intent.location:
            if constraints.required_location.lower() not in intent.location.lower() and intent.location.lower() not in constraints.required_location.lower():
                narr = intent.summary.lower()
                if not any(w in narr for w in ("moves to", "goes to", "arrives at", "cut to", "meanwhile", "later")):
                    issues.append(
                        SemanticIssue(
                            code=SemanticIssueCode.CONTINUITY_BREAK,
                            message="Unexplained location change before generation.",
                            severity="CRITICAL",
                            evidence={"required": constraints.required_location, "intent": intent.location},
                        )
                    )

        # Object transformation: required phone vs required dslr in same intent
        req_join = " ".join(intent.required_objects).lower()
        if constraints.required_held_object and "phone" in constraints.required_held_object.lower():
            if "dslr" in req_join or "broadcast" in req_join:
                issues.append(
                    SemanticIssue(
                        code=SemanticIssueCode.UNEXPECTED_OBJECT,
                        message="Object transformation without explicit transition (phone → camera).",
                        severity="CRITICAL",
                        evidence={"held": constraints.required_held_object, "required_objects": intent.required_objects},
                    )
                )

        # RCP-06C CAMERA — hard-block only when BOTH prior and next contracts are explicit
        cur_cam = extract_explicit_camera_contract(intent)
        if constraints.require_camera_contract and cur_cam:
            prev_hits = _family_hits(constraints.camera_language, _CAMERA_FAMILIES)
            cur_hits = _family_hits(cur_cam, _CAMERA_FAMILIES)
            if prev_hits and cur_hits and _exclusive_pair_hit(prev_hits, cur_hits, _CAMERA_EXCLUSIVE):
                narr = (intent.summary or "").lower()
                transition_ok = any(
                    w in narr
                    for w in ("cut to", "camera moves", "push in", "pull back", "dolly", "whip pan", "smash cut")
                )
                if not transition_ok:
                    issues.append(
                        SemanticIssue(
                            code=SemanticIssueCode.CONTINUITY_BREAK,
                            message="Unexplained camera contract contradiction before generation.",
                            severity="CRITICAL",
                            evidence={
                                "previous_camera": constraints.camera_language,
                                "current_camera": cur_cam,
                                "previous_families": sorted(prev_hits),
                                "current_families": sorted(cur_hits),
                                "note": "heuristic_contract_compare_not_provider_verified",
                            },
                        )
                    )

        # RCP-06C LIGHTING — hard-block only when BOTH sides explicit
        cur_lit = extract_explicit_lighting_contract(intent)
        if constraints.require_lighting_contract and cur_lit:
            prev_hits = _family_hits(constraints.lighting, _LIGHTING_FAMILIES)
            cur_hits = _family_hits(cur_lit, _LIGHTING_FAMILIES)
            if prev_hits and cur_hits and _exclusive_pair_hit(prev_hits, cur_hits, _LIGHTING_EXCLUSIVE):
                narr = (intent.summary or "").lower()
                transition_ok = any(
                    w in narr
                    for w in ("later", "night falls", "sunrise", "sunset", "hours later", "next morning", "meanwhile")
                )
                if not transition_ok:
                    issues.append(
                        SemanticIssue(
                            code=SemanticIssueCode.CONTINUITY_BREAK,
                            message="Unexplained lighting contract contradiction before generation.",
                            severity="CRITICAL",
                            evidence={
                                "previous_lighting": constraints.lighting,
                                "current_lighting": cur_lit,
                                "previous_families": sorted(prev_hits),
                                "current_families": sorted(cur_hits),
                                "note": "heuristic_contract_compare_not_provider_verified",
                            },
                        )
                    )

        # RCP-06C RELATIONSHIP — only when prior had explicit relationships AND next declares opposing ones
        cur_rels = extract_explicit_relationships(intent)
        if constraints.required_relationships and cur_rels:
            conflict = _relationships_contradict(constraints.required_relationships, cur_rels)
            if conflict:
                narr = (intent.summary or "").lower()
                transition_ok = any(
                    w in narr
                    for w in (
                        "moves away",
                        "steps away",
                        "leaves",
                        "releases",
                        "puts down",
                        "stands apart",
                        "walks away",
                        "enters",
                        "exits",
                    )
                )
                if not transition_ok:
                    issues.append(
                        SemanticIssue(
                            code=SemanticIssueCode.CONTINUITY_BREAK,
                            message="Unexplained relationship contract contradiction before generation.",
                            severity="CRITICAL",
                            evidence={
                                **conflict,
                                "previous_relationships": list(constraints.required_relationships),
                                "current_relationships": list(cur_rels),
                            },
                        )
                    )

        return issues

    def validate_continuity(
        self,
        intent: SceneIntent,
        analysis: VisualAnalysisMetadata,
    ) -> list[SemanticIssue]:
        """Post-generation safety net (existing T004-C3 behavior, extended)."""
        issues: list[SemanticIssue] = []
        if not intent.continuity_expected or intent.narrative_change_allowed:
            return issues
        if self._state is None:
            return issues

        prev = self._state
        det_loc = (analysis.location or intent.location or "").lower()
        prev_loc = (prev.location or "").lower()
        if prev_loc and det_loc and prev_loc not in det_loc and det_loc not in prev_loc:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.CONTINUITY_BREAK,
                    message="Unexplained location change across consecutive scenes.",
                    severity="HIGH",
                    evidence={"previous": prev_loc, "current": det_loc},
                )
            )

        det_posture = (analysis.posture or intent.posture or "").lower()
        prev_posture = (prev.posture or "").lower()
        chair = {"chair", "seated", "sitting"}
        floor = {"floor", "ground"}
        if prev_posture and det_posture:
            prev_chair = any(t in prev_posture for t in chair)
            cur_floor = any(t in det_posture for t in floor)
            if prev_chair and cur_floor:
                issues.append(
                    SemanticIssue(
                        code=SemanticIssueCode.CONTINUITY_BREAK,
                        message="Unexplained posture/location continuity break (seated → floor).",
                        severity="HIGH",
                        evidence={"previous_posture": prev_posture, "current_posture": det_posture},
                    )
                )

        if prev.character_id and intent.actors:
            actor = intent.actors[0].lower()
            if prev.character_id.lower() not in actor and actor not in prev.character_id.lower():
                issues.append(
                    SemanticIssue(
                        code=SemanticIssueCode.CONTINUITY_BREAK,
                        message="Character identity may have changed without narrative justification.",
                        severity="MEDIUM",
                        evidence={"previous": prev.character_id, "current": actor},
                    )
                )

        if prev.held_object:
            objs = " ".join(analysis.objects).lower()
            held = prev.held_object.lower()
            if held and held not in objs and "phone" in held and "camera" in objs and "phone" not in objs:
                issues.append(
                    SemanticIssue(
                        code=SemanticIssueCode.UNEXPECTED_OBJECT,
                        message="Held phone appears transformed into separate camera in analysis.",
                        severity="CRITICAL",
                        evidence={"held": prev.held_object, "detected": analysis.objects},
                    )
                )
        return issues

    def update_from_intent(
        self,
        intent: SceneIntent,
        analysis: VisualAnalysisMetadata,
    ) -> None:
        refs = intent.continuity_refs or {}
        actor = intent.actors[0] if intent.actors else str(refs.get("character_id") or "")
        held = str(refs.get("held_object") or "")
        summary = (intent.summary or "").lower()
        if not held:
            if "phone" in summary or any("phone" in o for o in intent.required_objects):
                if any(w in summary for w in ("hold", "holding", "holding the", "picks up", "pick up")):
                    held = "smartphone"
                elif any(w in summary for w in ("place", "put", "sets down")):
                    held = ""
                else:
                    held = next((o for o in intent.required_objects if "phone" in o.lower()), "") or (
                        "smartphone" if "phone" in summary else ""
                    )

        wardrobe = str(refs.get("wardrobe") or "")
        if not wardrobe and intent.actors:
            wardrobe = str(refs.get("clothing") or "consistent wardrobe")

        spatial = list(refs.get("spatial_notes") or [])
        for rel in intent.relations:
            spatial.append(f"{rel.source_id}:{rel.relation_type}:{rel.target_id}")

        cam_contract = extract_explicit_camera_contract(intent)
        lit_contract = extract_explicit_lighting_contract(intent)
        rel_contracts = extract_explicit_relationships(intent)
        # Soft memory from refs when not explicit (prompt preference only — never hard-block)
        soft_cam = str(refs.get("camera_language") or refs.get("camera") or "").strip()
        soft_lit = str(refs.get("lighting") or "").strip()

        # PART-5J: drop off-niche contamination (e.g. tea/cup in lunar documentary)
        niche_blob = " ".join(
            [
                str(intent.summary or ""),
                str(intent.location or ""),
                str(intent.environment or ""),
                str(refs.get("topic") or ""),
                str(refs.get("niche") or ""),
            ]
        ).lower()
        objects = list(analysis.objects[:6]) or list(intent.required_objects[:6])
        if any(k in niche_blob for k in ("lunar", "moon", "artemis", "nasa", "space", "crater", "orion")):
            _OFF = {"tea", "cup", "mug", "coffee", "kitchen", "sofa", "living room"}
            objects = [o for o in objects if str(o).strip().lower() not in _OFF]

        state = ContinuityState(
            character_id=actor or str(refs.get("character_id") or ""),
            appearance_ref=str(refs.get("appearance_ref") or ""),
            wardrobe=wardrobe,
            location=analysis.location or intent.location or str(refs.get("location") or ""),
            environment=intent.environment or intent.location,
            important_objects=objects,
            held_object=held,
            object_states=dict(refs.get("object_states") or {}),
            posture=analysis.posture or intent.posture,
            ongoing_action=intent.primary_action,
            action_completed=[a.action for a in intent.action_order],
            time_context=str(refs.get("time_context") or ""),
            spatial_notes=spatial[:12],
            lighting=lit_contract or soft_lit,
            camera_language=cam_contract or soft_cam,
            emotional_state=intent.emotional_intent or str(refs.get("emotional_state") or ""),
            scene_id=intent.scene_id,
            dialogue_id=intent.dialogue_id,
            revision_id=intent.revision_id,
            explicit_camera=bool(cam_contract),
            explicit_lighting=bool(lit_contract),
            required_relationships=list(rel_contracts[:24]),
        )
        state.fingerprint = state.compute_fingerprint()
        self._state = state
        self._history.append(state.to_dict())
        desc = (analysis.description or intent.visual_emphasis or "").strip().lower()
        if desc:
            self._descriptions.append(desc)

    def to_persist_dict(self) -> dict[str, Any]:
        return {
            "state": self._state.to_dict() if self._state else None,
            "descriptions": list(self._descriptions),
            "history": list(self._history),
        }

    @classmethod
    def from_persist_dict(cls, data: dict[str, Any]) -> "ContinuityTracker":
        t = cls()
        if data.get("state"):
            t._state = ContinuityState.from_dict(data["state"])
        t._descriptions = [str(x) for x in (data.get("descriptions") or [])]
        t._history = list(data.get("history") or [])
        return t

    def persist(self, work_dir: Path) -> Path:
        path = Path(work_dir) / CONTINUITY_STATE_FILE
        path.write_text(json.dumps(self.to_persist_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, work_dir: Path) -> Optional["ContinuityTracker"]:
        path = Path(work_dir) / CONTINUITY_STATE_FILE
        if not path.is_file():
            return None
        try:
            return cls.from_persist_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None
