"""BUILD-01 contract tests — offline, no external APIs."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain import (
    AudioPlan,
    Checkpoint,
    FactPack,
    Job,
    JobState,
    Scene,
    Script,
    Topic,
    ValidationResult,
    Verdict,
    fact_pack_from_legacy,
    scene_from_legacy_contract,
    script_from_plan,
    topic_from_plan,
    validation_from_preflight,
)
from domain.registry import CONTRACT_REGISTRY, all_contract_models
from pipeline.fact_pack import build_fact_pack
from pipeline.scene_contract import attach_contracts_to_plan, build_scene_contract


def _sample_plan() -> dict:
    return {
        "topic": "Lost Library of Alexandria",
        "title": "Lost Library of Alexandria",
        "video_type": "short",
        "scenes": [
            {
                "element": "intro",
                "narration": "Tonight we explore the vanished library.",
                "keyword_triggers": ["library", "alexandria"],
            }
        ],
    }


class ContractValidationTests(unittest.TestCase):
    def test_topic_valid(self):
        t = Topic(title="Test Topic")
        self.assertEqual(t.schema_version, "1.0.0")
        self.assertTrue(t.id)

    def test_topic_missing_title_fails(self):
        with self.assertRaises(Exception):
            Topic(title="")

    def test_invalid_schema_version(self):
        with self.assertRaises(Exception):
            Topic(title="x", schema_version="bad")

    def test_invalid_uuid_id(self):
        with self.assertRaises(Exception):
            Topic(title="x", id="not-a-uuid")

    def test_subtitle_end_before_start_fails(self):
        from domain import SubtitleCue

        with self.assertRaises(Exception):
            SubtitleCue(
                scene_id=str(uuid4()),
                cue_id="c1",
                start_time=5.0,
                end_time=2.0,
                text="bad",
            )


class SerializationTests(unittest.TestCase):
    def test_topic_roundtrip(self):
        t = Topic(title="Roundtrip")
        raw = t.model_dump(mode="json")
        t2 = Topic.model_validate(raw)
        self.assertEqual(t2.title, "Roundtrip")
        self.assertEqual(t2.id, t.id)

    def test_fact_pack_json_roundtrip(self):
        fp = FactPack(topic_title="T", claims=[])
        blob = json.dumps(fp.model_dump(mode="json"))
        fp2 = FactPack.model_validate(json.loads(blob))
        self.assertEqual(fp2.topic_title, "T")

    def test_all_registry_models_have_schema_version(self):
        for model in all_contract_models():
            fields = model.model_fields
            self.assertIn("schema_version", fields, msg=model.__name__)


class AdapterTests(unittest.TestCase):
    def test_topic_from_plan(self):
        topic = topic_from_plan(_sample_plan())
        self.assertEqual(topic.title, "Lost Library of Alexandria")

    def test_fact_pack_from_legacy(self):
        legacy = build_fact_pack("Chernobyl", notes="Reactor four exploded in 1986.")
        fp = fact_pack_from_legacy(legacy)
        self.assertEqual(fp.topic_title, "Chernobyl")
        self.assertGreaterEqual(len(fp.claims), 1)

    def test_scene_from_legacy_contract(self):
        plan = attach_contracts_to_plan(_sample_plan())
        sc = plan["scenes"][0]
        contract = sc["scene_contract"]
        scene = scene_from_legacy_contract(contract, scene_index=0)
        self.assertIsNotNone(scene.visual_plan)
        self.assertEqual(scene.legacy_scene_id, 0)

    def test_script_from_plan(self):
        script = script_from_plan(_sample_plan())
        self.assertGreaterEqual(len(script.sections), 1)

    def test_validation_from_preflight(self):
        contract = build_scene_contract(
            {"element": "intro", "narration": "Hello world test claim here."},
            scene_id=0,
            topic="Test",
        )
        from pipeline.scene_contract import preflight_scene_contract

        pf = preflight_scene_contract(contract)
        vr = validation_from_preflight(pf)
        self.assertIsInstance(vr, ValidationResult)


class IntegrationChainTests(unittest.TestCase):
    def test_topic_to_script_to_scene_chain(self):
        plan = attach_contracts_to_plan(_sample_plan())
        topic = topic_from_plan(plan)
        script = script_from_plan(plan, topic_id=topic.id)
        legacy_fp = build_fact_pack(topic.title, notes="Library held scrolls.")
        fp = fact_pack_from_legacy(legacy_fp, topic_id=topic.id)
        scene = scene_from_legacy_contract(
            plan["scenes"][0]["scene_contract"],
            script_id=script.id,
            scene_index=0,
        )
        self.assertEqual(topic.title, fp.topic_title)
        self.assertIsNotNone(scene.visual_plan)
        self.assertTrue(script.sections)

    def test_job_checkpoint_chain(self):
        job = Job(status=JobState.PLANNING, entity_id=str(uuid4()))
        cp = Checkpoint(job_id=job.id, stage="planning", state=JobState.PLANNING)
        self.assertEqual(cp.job_id, job.id)


class SchemaDriftTests(unittest.TestCase):
    """Detect accidental breaking changes to contract schemas."""

    EXPECTED_REQUIRED: dict[str, set[str]] = {
        "Topic": {"title", "schema_version", "id"},
        "FactPack": {"topic_title", "schema_version", "id"},
        "Scene": {"scene_index", "element", "schema_version", "id"},
        "Job": {"status", "schema_version", "id"},
        "ValidationResult": {"verdict", "passed", "schema_version", "id"},
    }

    def test_required_fields_present(self):
        by_name = {m.__name__: m for m in all_contract_models()}
        for name, required in self.EXPECTED_REQUIRED.items():
            model = by_name[name]
            fields = set(model.model_fields.keys())
            missing = required - fields
            self.assertFalse(missing, f"{name} missing fields: {missing}")

    def test_registry_count_stable(self):
        self.assertGreaterEqual(len(CONTRACT_REGISTRY), 15)

    def test_enum_values_stable(self):
        self.assertEqual(Verdict.PASS.value, "PASS")
        self.assertIn("CREATED", [s.value for s in JobState])


if __name__ == "__main__":
    unittest.main()
