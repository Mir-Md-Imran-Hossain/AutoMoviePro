#!/usr/bin/env python3
"""AMP-003 T004-B — Scene contract model audit (B-1)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.common import SchemaVersionMismatchError
from domain.scene import Scene, ShotPlan, VisualPlan
from domain.validation import validate_contract_version
from pipeline.scene_contract import attach_contracts_to_plan


def _valid_scene_dict() -> dict:
    return {
        "schema_version": "1.0.0",
        "id": str(uuid4()),
        "scene_index": 0,
        "element": "intro",
        "visual_plan": {
            "schema_version": "1.0.0",
            "id": str(uuid4()),
            "scene_id": str(uuid4()),
            "shot": {
                "schema_version": "1.0.0",
                "id": str(uuid4()),
                "subject": "library",
                "action": "reveal",
                "environment": "ancient hall",
            },
        },
    }


class T004BContractTests(unittest.TestCase):
    def test_valid_scene_passes(self):
        s = Scene.model_validate(_valid_scene_dict())
        ok, _ = validate_contract_version(Scene, s.to_json_dict())
        self.assertTrue(ok)

    def test_missing_element_fails(self):
        d = _valid_scene_dict()
        d["element"] = ""
        with self.assertRaises(Exception):
            Scene.model_validate(d)

    def test_malformed_scene_index_fails(self):
        d = _valid_scene_dict()
        d["scene_index"] = -1
        with self.assertRaises(Exception):
            Scene.model_validate(d)

    def test_invalid_duration_fails(self):
        d = _valid_scene_dict()
        d["duration_target_sec"] = -1.0
        with self.assertRaises(Exception):
            Scene.model_validate(d)

    def test_wrong_schema_version_fails(self):
        d = _valid_scene_dict()
        d["schema_version"] = "2.0.0"
        with self.assertRaises(SchemaVersionMismatchError):
            Scene.from_json_dict(d)

    def test_unexpected_field_fails(self):
        d = _valid_scene_dict()
        d["bogus_field"] = True
        with self.assertRaises(Exception):
            Scene.model_validate(d)

    def test_attach_contracts_produces_preflight(self):
        plan = attach_contracts_to_plan(
            {
                "topic": "Alexandria",
                "scenes": [
                    {
                        "element": "intro",
                        "narration": "The library held scrolls from across the ancient world.",
                        "keyword_triggers": ["library"],
                    }
                ],
            }
        )
        self.assertTrue(plan["scene_contract_report"]["passed"])


if __name__ == "__main__":
    unittest.main()
