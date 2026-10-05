"""Future multimodal evaluator adapter boundary (T004-C3)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from domain.scene_intent import SceneIntent


@dataclass
class EvaluatorResult:
    source: str  # HEURISTIC | OFFLINE_TEST_ONLY | PROVIDER_VERIFIED
    visual_analysis: dict[str, Any] = field(default_factory=dict)
    audio_analysis: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "visual_analysis": dict(self.visual_analysis),
            "audio_analysis": dict(self.audio_analysis),
            "confidence": self.confidence,
            "verified": self.verified,
        }


class MultimodalEvaluator(ABC):
    """Adapter for future VLM/VLM/ASR evaluators."""

    @abstractmethod
    def analyze_visual(self, intent: SceneIntent, asset_path: str) -> EvaluatorResult:
        ...


class OfflineFixtureEvaluator(MultimodalEvaluator):
    """OFFLINE_TEST_ONLY deterministic fixture evaluator."""

    def __init__(self, fixture: Optional[dict[str, Any]] = None) -> None:
        self.fixture = fixture or {}

    def analyze_visual(self, intent: SceneIntent, asset_path: str) -> EvaluatorResult:
        visual = dict(self.fixture.get("visual") or self.fixture)
        visual.setdefault("source", "OFFLINE_TEST_ONLY")
        visual.setdefault("dialogue_id", intent.dialogue_id)
        return EvaluatorResult(
            source="OFFLINE_TEST_ONLY",
            visual_analysis=visual,
            audio_analysis=dict(self.fixture.get("audio") or {}),
            confidence=1.0,
            verified=False,
        )


class HeuristicEvaluator(MultimodalEvaluator):
    """HEURISTIC prompt-derived analysis — not computer vision."""

    def analyze_visual(self, intent: SceneIntent, asset_path: str) -> EvaluatorResult:
        from pipeline.visual_semantic.boundary import build_heuristic_analysis

        analysis = build_heuristic_analysis(
            visual_prompt=intent.visual_emphasis,
            visual_description=intent.summary,
            dialogue_id=intent.dialogue_id,
        )
        return EvaluatorResult(
            source="HEURISTIC",
            visual_analysis=analysis.to_dict(),
            confidence=0.5,
            verified=False,
        )


def get_evaluator(
    *,
    fixture: Optional[dict[str, Any]] = None,
    strict: bool = False,
    google_api_keys: Optional[list] = None,
    prefer_provider: bool = True,
) -> MultimodalEvaluator:
    if fixture is not None:
        return OfflineFixtureEvaluator(fixture)
    if prefer_provider and google_api_keys:
        return ProviderVerifiedGeminiEvaluator(google_api_keys=list(google_api_keys))
    return HeuristicEvaluator()


class ProviderVerifiedGeminiEvaluator(MultimodalEvaluator):
    """Real pixel observation via existing Gemini video/frame critic path.

    HEURISTIC keyword overlap is NEVER used as verification proof.
    If observation cannot run, returns verified=False and source=UNAVAILABLE.
    """

    def __init__(self, google_api_keys: Optional[list] = None) -> None:
        self.google_api_keys = [str(k).strip() for k in (google_api_keys or []) if str(k).strip()]

    def analyze_visual(self, intent: SceneIntent, asset_path: str) -> EvaluatorResult:
        from pipeline.semantic_coverage import contract_from_scene, observe_semantic_coverage

        scene = {
            "dialogue_id": intent.dialogue_id,
            "scene_id": intent.scene_id,
            "narration": intent.summary,
            "required_entities": [e.label if hasattr(e, "label") else str(e) for e in (intent.entities or [])],
            "relationships": [
                r.model_dump() if hasattr(r, "model_dump") else (r if isinstance(r, dict) else {"raw": str(r)})
                for r in (intent.relations or [])
            ],
            "location": getattr(intent, "location", "") or "",
            "must_show": list(intent.required_objects or []),
            "visual_emphasis": intent.visual_emphasis,
        }
        contract = contract_from_scene(scene, narration=intent.summary, prompt=intent.visual_emphasis or "")
        obs = observe_semantic_coverage(
            video_path=Path(asset_path),
            contract=contract,
            google_api_keys=self.google_api_keys,
        )
        observed = (obs.get("layers") or {}).get("OBSERVED_ASSET") or {}
        visual = {
            "source": obs.get("observation_method") or "UNAVAILABLE",
            "description": observed.get("summary") or "",
            "objects": list(observed.get("entities") or observed.get("subjects") or []),
            "actions": list(observed.get("actions") or []),
            "dialogue_id": intent.dialogue_id,
            "overall": obs.get("overall"),
            "dimensions": obs.get("dimensions"),
            "wrong_actor": any(
                str((obs.get("dimensions") or {}).get(k, {}).get("status")).upper() == "FAIL"
                for k in ("unrelated_subject_mismatch", "required_subject")
            ),
            "contradiction": ";".join(obs.get("issues") or []) if obs.get("overall") == "FAIL" else "",
            "verified": bool(obs.get("provider_verified")),
        }
        return EvaluatorResult(
            source="PROVIDER_VERIFIED" if obs.get("provider_verified") else "UNAVAILABLE",
            visual_analysis=visual,
            confidence=0.85 if obs.get("provider_verified") else 0.0,
            verified=bool(obs.get("provider_verified") and obs.get("overall") == "PASS"),
        )
