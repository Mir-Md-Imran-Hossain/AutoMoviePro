"""Deterministic mock subtitle provider (BUILD-04E)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class MockSubtitleBehavior(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"
    MALFORMED = "malformed"
    EMPTY = "empty"
    OVERLAP = "overlap"
    WRONG_DIALOGUE = "wrong_dialogue"
    WRONG_SCENE = "wrong_scene"
    NEGATIVE_TIME = "negative_time"
    END_BEFORE_START = "end_before_start"


@dataclass
class MockSubtitleProvider:
    behavior: MockSubtitleBehavior = MockSubtitleBehavior.SUCCESS
    slow_delay_sec: float = 0.05
    invocation_count: int = field(default=0, init=False)
    last_generation_id: str = field(default="", init=False)

    def reset(self) -> None:
        self.invocation_count = 0
        self.last_generation_id = ""

    def generate(
        self,
        *,
        text: str,
        audio_duration_sec: float,
        scene_id: str = "0",
        dialogue_id: str = "d01",
        segment_id: str = "",
        language: str = "en",
    ) -> dict[str, Any]:
        self.invocation_count += 1
        self.last_generation_id = f"mock-sub-{self.invocation_count:04d}"

        if self.behavior == MockSubtitleBehavior.TIMEOUT:
            raise TimeoutError("subtitle timeout")
        if self.behavior == MockSubtitleBehavior.FAILURE:
            # Explicitly retryable wording — unlabeled errors are UNKNOWN (DEF-H3-007).
            raise RuntimeError("temporary subtitle generation failed")
        if self.behavior == MockSubtitleBehavior.UNKNOWN:
            raise TimeoutError("subtitle unknown state")
        if self.behavior == MockSubtitleBehavior.EMPTY:
            return {"cues": [], "srt": ""}

        dur = max(1.0, float(audio_duration_sec))
        cues = [
            {
                "cue_id": "1",
                "start_time": 0.0,
                "end_time": dur,
                "text": (text or "sample").strip(),
                "scene_id": scene_id,
                "dialogue_id": dialogue_id,
                "segment_id": segment_id,
                "language": language,
            }
        ]

        if self.behavior == MockSubtitleBehavior.WRONG_DIALOGUE:
            cues[0]["dialogue_id"] = "WRONG-DIALOGUE"
        if self.behavior == MockSubtitleBehavior.WRONG_SCENE:
            cues[0]["scene_id"] = "WRONG-SCENE"
        if self.behavior == MockSubtitleBehavior.NEGATIVE_TIME:
            cues[0]["start_time"] = -1.0
        if self.behavior == MockSubtitleBehavior.END_BEFORE_START:
            cues[0]["end_time"] = 0.0
        if self.behavior == MockSubtitleBehavior.OVERLAP:
            cues.append(
                {
                    "cue_id": "2",
                    "start_time": 0.5,
                    "end_time": dur,
                    "text": "overlap",
                    "scene_id": scene_id,
                    "dialogue_id": dialogue_id,
                    "segment_id": segment_id,
                    "language": language,
                }
            )
        if self.behavior == MockSubtitleBehavior.MALFORMED:
            return {"cues": cues, "srt": "NOT VALID SRT"}

        from pipeline.idempotency.subtitle_engine import cues_to_srt_file

        return {"cues": cues, "srt": cues_to_srt_file(cues)}


_GLOBAL = MockSubtitleProvider()


def get_mock_subtitle_provider() -> MockSubtitleProvider:
    return _GLOBAL


def reset_mock_subtitle_provider() -> None:
    _GLOBAL.reset()
