"""Visual generation request identity (BUILD-04A + AMP-003 T004-C1)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pipeline.idempotency.fingerprint import compute_fingerprint, hash_text


class GenerationMode(str, Enum):
    TEXT_TO_VIDEO = "TEXT_TO_VIDEO"
    IMAGE_TO_VIDEO = "IMAGE_TO_VIDEO"
    IMAGE_GENERATION = "IMAGE_GENERATION"
    IMAGE_WITH_MOTION = "IMAGE_WITH_MOTION"  # C05-V: still + controlled motion (existing fallback)
    OTHER = "OTHER"


class VisualIdentityError(ValueError):
    """Fail-closed visual request identity validation failure."""


@dataclass
class VisualRequestSpec:
    job_id: str
    scene_id: int
    visual_plan_id: str
    provider: str
    model: str
    generation_mode: GenerationMode
    prompt: str
    visual_prompt: str = ""
    narration_hint: str = ""
    element: str = ""
    product_name: str = ""
    size: str = "1080x1920"
    width: int = 0
    height: int = 0
    duration_sec: float = 0.0
    seed: Optional[int] = None
    reference_asset_id: str = ""
    reference_asset_hash: str = ""
    image_url_hash: str = ""
    niche: str = ""
    force_regenerate: bool = False
    # T004-C1 identity (mirror AudioRequestSpec pattern)
    dialogue_id: str = ""
    canonical_scene_id: str = ""
    script_id: str = ""
    part_index: int = 0
    segment_id: str = ""
    revision_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_inputs(self) -> dict[str, Any]:
        """Semantic inputs for fingerprint — excludes attempt/timestamp."""
        meta = dict(self.metadata or {})
        rel_fp = ""
        rels = meta.get("relationships") or []
        if isinstance(rels, list) and rels:
            joined = "|".join(
                f"{(r or {}).get('relation_type')}:{(r or {}).get('source_id')}:{(r or {}).get('target_id')}"
                if isinstance(r, dict)
                else str(r)
                for r in rels
            )
            rel_fp = hash_text(joined)[:16]
        return {
            "scene_id": int(self.scene_id),
            "canonical_scene_id": self.canonical_scene_id.strip(),
            "dialogue_id": self.dialogue_id.strip(),
            "script_id": self.script_id.strip(),
            "visual_plan_id": self.visual_plan_id.strip(),
            "segment_id": self.segment_id.strip(),
            "beat_id": str(meta.get("beat_id") or self.segment_id or "").strip(),
            "part_index": int(self.part_index or 0),
            "revision_id": self.revision_id.strip(),
            "generation_mode": self.generation_mode.value,
            "visual_mode": str(meta.get("visual_mode") or meta.get("actual_mode") or "").strip(),
            "prompt": self.prompt.strip(),
            "visual_prompt": self.visual_prompt.strip(),
            "canonical_prompt": str(meta.get("canonical_prompt") or "").strip(),
            "narration_hint": self.narration_hint.strip(),
            "element": self.element.strip().lower(),
            "product_name": self.product_name.strip(),
            "size": self.size.strip(),
            "width": int(self.width or 0),
            "height": int(self.height or 0),
            "duration_sec": round(float(self.duration_sec or 0.0), 3),
            "seed": self.seed,
            "reference_asset_id": self.reference_asset_id.strip(),
            "reference_asset_hash": self.reference_asset_hash.strip(),
            "image_url_hash": self.image_url_hash.strip(),
            "niche": self.niche.strip(),
            "location_identity": str(meta.get("location_identity") or "").strip(),
            "character_identity": str(meta.get("character_identity") or "").strip(),
            "relationship_fp": rel_fp,
            "coverage_overall": str((meta.get("coverage") or {}).get("overall") or "").strip()
            if isinstance(meta.get("coverage"), dict)
            else "",
            "timing_duration": round(float((meta.get("timing") or {}).get("duration_sec") or 0.0), 3)
            if isinstance(meta.get("timing"), dict)
            else 0.0,
            "continuity_fingerprint": str(meta.get("continuity_fingerprint") or "").strip(),
            "alignment_fingerprint": str(meta.get("alignment_fingerprint") or "").strip(),
            "customer_id": str(meta.get("customer_id") or "").strip(),
            "channel_id": str(meta.get("channel_id") or "").strip(),
            "generation_id": str(meta.get("generation_id") or "").strip(),
        }

    def fingerprint(self) -> str:
        return compute_visual_fingerprint(self)

    @property
    def prompt_hash(self) -> str:
        effective = self.prompt.strip() or self.visual_prompt.strip()
        return hash_text(effective)

    @property
    def entity_id(self) -> str:
        did = self.dialogue_id.strip() or self.visual_plan_id.strip()
        seg = self.segment_id.strip() or (f"p{self.part_index}" if self.part_index else "")
        base = f"scene-{int(self.scene_id):02d}-{did}"
        if seg:
            base = f"{base}-{seg}"
        rev = self.revision_id.strip()
        if rev:
            base = f"{base}-rev-{rev}"
        return base


def validate_visual_request_identity(
    spec: VisualRequestSpec,
    *,
    production: bool = False,
    expected_scene_index: Optional[int] = None,
    expected_dialogue_id: Optional[str] = None,
    expected_canonical_scene_id: Optional[str] = None,
) -> None:
    """Fail-closed identity validation. Raises VisualIdentityError on violation."""
    if not (spec.job_id or "").strip():
        raise VisualIdentityError("missing job_id")
    if spec.scene_id < 0:
        raise VisualIdentityError("invalid scene_id")
    if not (spec.visual_plan_id or "").strip():
        raise VisualIdentityError("missing visual_plan_id")
    if not (spec.provider or "").strip():
        raise VisualIdentityError("missing provider")
    if not (spec.model or "").strip():
        raise VisualIdentityError("missing model")
    if production:
        if not spec.dialogue_id.strip():
            raise VisualIdentityError("missing dialogue_id")
        if not spec.canonical_scene_id.strip():
            raise VisualIdentityError("missing canonical_scene_id")
    if expected_scene_index is not None and int(spec.scene_id) != int(expected_scene_index):
        raise VisualIdentityError(
            f"scene_index mismatch: spec={spec.scene_id} expected={expected_scene_index}"
        )
    if expected_dialogue_id and spec.dialogue_id.strip() and spec.dialogue_id.strip() != expected_dialogue_id.strip():
        raise VisualIdentityError("dialogue_id mismatch with expected handoff")
    if expected_canonical_scene_id and spec.canonical_scene_id.strip():
        if spec.canonical_scene_id.strip() != expected_canonical_scene_id.strip():
            raise VisualIdentityError("canonical_scene_id mismatch with expected handoff")


def build_visual_request_from_handoff(
    handoff: dict[str, Any],
    *,
    job_id: str,
    visual_plan_id: str,
    provider: str,
    model: str,
    generation_mode: GenerationMode,
    prompt: str,
    visual_prompt: str = "",
    narration_hint: str = "",
    element: str = "",
    product_name: str = "",
    size: str = "1080x1920",
    duration_sec: float = 0.0,
    seed: Optional[int] = None,
    part_index: int = 0,
    segment_id: str = "",
    revision_id: str = "",
    image_url_hash: str = "",
    niche: str = "",
    **extra: Any,
) -> VisualRequestSpec:
    """Build VisualRequestSpec from T004-B validated scene handoff — production path."""
    if not handoff.get("_validated"):
        raise VisualIdentityError("scene handoff not validated")
    scene_index = int(handoff.get("scene_index") if handoff.get("scene_index") is not None else -1)
    dialogue_id = str(handoff.get("dialogue_id") or "").strip()
    canonical_scene_id = str(handoff.get("canonical_scene_id") or "").strip()
    script_id = str(handoff.get("script_id") or "").strip()
    if scene_index < 0:
        raise VisualIdentityError("missing scene_index in handoff")
    if not dialogue_id:
        raise VisualIdentityError("missing dialogue_id in handoff")
    if not canonical_scene_id:
        raise VisualIdentityError("missing canonical_scene_id in handoff")
    spec = VisualRequestSpec(
        job_id=job_id,
        scene_id=scene_index,
        visual_plan_id=visual_plan_id,
        provider=provider,
        model=model,
        generation_mode=generation_mode,
        prompt=prompt,
        visual_prompt=visual_prompt,
        narration_hint=narration_hint,
        element=element or str(handoff.get("element") or ""),
        product_name=product_name,
        size=size,
        duration_sec=duration_sec,
        seed=seed,
        dialogue_id=dialogue_id,
        canonical_scene_id=canonical_scene_id,
        script_id=script_id,
        part_index=int(part_index or 0),
        segment_id=str(segment_id or "").strip(),
        revision_id=str(revision_id or "").strip(),
        image_url_hash=image_url_hash,
        niche=niche,
        metadata=dict(extra),
    )
    validate_visual_request_identity(
        spec,
        production=True,
        expected_scene_index=scene_index,
        expected_dialogue_id=dialogue_id,
        expected_canonical_scene_id=canonical_scene_id,
    )
    return spec


def compute_visual_fingerprint(spec: VisualRequestSpec) -> str:
    """Deterministic visual request fingerprint."""
    return compute_fingerprint(
        job_id=spec.job_id,
        stage="visual",
        entity_id=spec.entity_id,
        provider=spec.provider,
        model=spec.model,
        inputs=spec.normalized_inputs(),
    )


def image_url_identity(url: str) -> str:
    """Stable hash for reference URL — not filename."""
    return hash_text((url or "").strip()) if url else ""
