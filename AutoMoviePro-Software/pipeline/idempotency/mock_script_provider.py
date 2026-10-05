"""Deterministic mock script/director provider (BUILD-04C)."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MockScriptBehavior(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    NETWORK = "network"
    MALFORMED = "malformed"
    EMPTY = "empty"
    REJECTION = "rejection"
    SLOW = "slow"
    UNKNOWN = "unknown"
    INVALID_SCRIPT = "invalid_script"
    DUPLICATE_DIALOGUE_IDS = "duplicate_dialogue_ids"
    MISSING_DIALOGUE = "missing_dialogue"


def _valid_plan(*, topic: str = "Mock Topic", niche: str = "history") -> dict[str, Any]:
    """Budget-aware mock director plan — must meet short/long scene floor."""
    try:
        from pipeline.niche_director import _fallback_plan

        plan = _fallback_plan(
            niche=niche or "history",
            topic=topic or "Mock Topic",
            video_type="short",
            max_seconds=60,
            channel_name="Mock Channel",
            blocked_products=[],
        )
        plan["director_provider"] = "mock"
        plan["director_model"] = "script-mock-v1"
        # Ensure dialogue_ids for C05
        for i, sc in enumerate(plan.get("scenes") or []):
            if isinstance(sc, dict):
                sc.setdefault("dialogue_id", f"dlg-{i+1:02d}")
        return plan
    except Exception:
        return {
            "title": f"{topic} — Documentary",
            "topic": topic,
            "description": f"A cinematic short about {topic}. #Documentary #Science",
            "tags": ["mock", niche, "documentary", "science", "space", "history", "2026", "nasa"],
            "niche": niche,
            "language": "en",
            "scenes": [
                {
                    "element": "intro",
                    "dialogue_id": "dlg-01",
                    "narration": f"Wait — most people misunderstand {topic}. Here is the proof.",
                    "visual_query": f"{topic} establishing shot",
                    "visual_prompt": f"cinematic intro of {topic}",
                    "exact_ai_video_prompt": f"vertical cinematic intro {topic}",
                    "retention_role": "pattern_interrupt",
                    "emotional_intent": "curiosity",
                },
                {
                    "element": "discovery",
                    "dialogue_id": "dlg-02",
                    "narration": f"Researchers uncovered new evidence about {topic}.",
                    "visual_query": f"{topic} discovery",
                    "visual_prompt": f"artifact close-up {topic}",
                    "exact_ai_video_prompt": f"macro discovery shot {topic}",
                    "retention_role": "evidence",
                    "emotional_intent": "reveal",
                },
                {
                    "element": "technique",
                    "dialogue_id": "dlg-03",
                    "narration": f"The instruments measuring {topic} changed the entire model.",
                    "visual_query": f"{topic} instrument close up",
                    "visual_prompt": f"scientific instrument documentary {topic}",
                    "exact_ai_video_prompt": f"macro instrument {topic}",
                    "retention_role": "rehook",
                    "emotional_intent": "tension",
                },
                {
                    "element": "context",
                    "dialogue_id": "dlg-04",
                    "narration": f"Context matters: without the surrounding physics, {topic} looks like noise.",
                    "visual_query": f"{topic} wide environment",
                    "visual_prompt": f"wide documentary context {topic}",
                    "exact_ai_video_prompt": f"wide establishing {topic}",
                    "retention_role": "context",
                    "emotional_intent": "clarity",
                },
                {
                    "element": "legacy",
                    "dialogue_id": "dlg-05",
                    "narration": f"That legacy still shapes how labs approach {topic} today.",
                    "visual_query": f"{topic} legacy archive",
                    "visual_prompt": f"archive documentary {topic}",
                    "exact_ai_video_prompt": f"archive still motion {topic}",
                    "retention_role": "payoff",
                    "emotional_intent": "awe",
                },
                {
                    "element": "discovery",
                    "dialogue_id": "dlg-06",
                    "narration": f"One more twist: the data for {topic} contradicted the old textbook chart.",
                    "visual_query": f"{topic} data chart",
                    "visual_prompt": f"scientific chart reveal {topic}",
                    "exact_ai_video_prompt": f"data visualization {topic}",
                    "retention_role": "rehook",
                    "emotional_intent": "surprise",
                },
                {
                    "element": "technique",
                    "dialogue_id": "dlg-07",
                    "narration": f"Engineers now build missions around what {topic} forced them to learn.",
                    "visual_query": f"{topic} engineering bay",
                    "visual_prompt": f"mission engineering bay {topic}",
                    "exact_ai_video_prompt": f"cleanroom engineering {topic}",
                    "retention_role": "evidence",
                    "emotional_intent": "resolve",
                },
                {
                    "element": "outro",
                    "dialogue_id": "dlg-08",
                    "narration": f"That is why {topic} still matters — and the next briefing will go deeper.",
                    "visual_query": f"{topic} outro",
                    "visual_prompt": f"sunset silhouette {topic}",
                    "exact_ai_video_prompt": f"cinematic outro {topic}",
                    "retention_role": "ending",
                    "emotional_intent": "payoff",
                    "payoff_for": "main_open_loop",
                },
            ],
            "director_provider": "mock",
            "director_model": "script-mock-v1",
        }


@dataclass
class MockScriptProvider:
    behavior: MockScriptBehavior = MockScriptBehavior.SUCCESS
    slow_delay_sec: float = 0.05
    topic: str = "Mock Topic"
    niche: str = "history"
    invocation_count: int = field(default=0, init=False)
    last_generation_id: str = field(default="", init=False)

    def reset(self) -> None:
        self.invocation_count = 0
        self.last_generation_id = ""

    def generate(self, *, topic: str = "", niche: str = "") -> dict[str, Any]:
        self.invocation_count += 1
        self.last_generation_id = f"mock-script-{self.invocation_count:04d}"
        t = (topic or self.topic).strip() or "Mock Topic"
        n = (niche or self.niche).strip() or "history"

        if self.behavior == MockScriptBehavior.TIMEOUT:
            raise TimeoutError("script generation timeout — response lost")
        if self.behavior == MockScriptBehavior.NETWORK:
            raise ConnectionError("temporary network failure")
        if self.behavior == MockScriptBehavior.REJECTION:
            raise ValueError("invalid script prompt configuration")
        if self.behavior == MockScriptBehavior.UNKNOWN:
            raise TimeoutError("provider accepted but response lost")
        if self.behavior == MockScriptBehavior.SLOW:
            time.sleep(self.slow_delay_sec)
        if self.behavior == MockScriptBehavior.EMPTY:
            return {}
        if self.behavior == MockScriptBehavior.MALFORMED:
            raise ValueError("MALFORMED_JSON:{not valid")
        if self.behavior == MockScriptBehavior.INVALID_SCRIPT:
            return {"title": "", "scenes": []}
        if self.behavior == MockScriptBehavior.DUPLICATE_DIALOGUE_IDS:
            plan = _valid_plan(topic=t, niche=n)
            plan["scenes"][1]["dialogue_id"] = "dlg-01"
            return plan
        if self.behavior == MockScriptBehavior.MISSING_DIALOGUE:
            plan = _valid_plan(topic=t, niche=n)
            plan["scenes"][1]["narration"] = ""
            return plan

        return _valid_plan(topic=t, niche=n)


_GLOBAL_MOCK = MockScriptProvider()


def get_mock_script_provider() -> MockScriptProvider:
    return _GLOBAL_MOCK


def reset_mock_script_provider() -> None:
    _GLOBAL_MOCK.reset()
