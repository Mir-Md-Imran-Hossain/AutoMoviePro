"""Prompt version registry — scientific change tracking."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_REGISTRY: Dict[str, Dict[str, Any]] = {
    "director_system": {
        "version": "v12",
        "change_reason": "baseline niche director",
        "expected_improvement": "stable english master plans",
        "test_cases": ["history_fallback", "gadget_block"],
        "before_score": None,
        "after_score": None,
    },
    "scene_contract_compiler": {
        "version": "v1",
        "change_reason": "mandatory subject/action/environment fields",
        "expected_improvement": "fewer generic broll prompts",
        "test_cases": ["test_scene_contract"],
        "before_score": None,
        "after_score": None,
    },
    "human_speech_editor": {
        "version": "v1",
        "change_reason": "robot detector + speech naturalness",
        "expected_improvement": "lower buzzword / symmetry score",
        "test_cases": ["test_robot_detector"],
        "before_score": None,
        "after_score": None,
    },
}


def get_prompt_meta(name: str) -> Dict[str, Any]:
    return dict(_REGISTRY.get(name) or {"version": "unknown", "name": name})


def bump_prompt(
    name: str,
    *,
    version: str,
    change_reason: str,
    expected_improvement: str = "",
    test_cases: Optional[List[str]] = None,
    before_score: Any = None,
    after_score: Any = None,
) -> Dict[str, Any]:
    row = {
        "version": version,
        "change_reason": change_reason,
        "expected_improvement": expected_improvement,
        "test_cases": list(test_cases or []),
        "before_score": before_score,
        "after_score": after_score,
    }
    _REGISTRY[name] = row
    return dict(row)


def save_registry(path: Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(_REGISTRY, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_registry(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return dict(_REGISTRY)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        _REGISTRY.update(data)
    return dict(_REGISTRY)
