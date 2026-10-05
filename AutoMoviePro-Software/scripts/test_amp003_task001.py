#!/usr/bin/env python3
"""AMP-003 TASK-001 — Canonical Domain + Contract Integrity."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain import (
    CONTRACT_REGISTRY,
    FactPack,
    Job,
    JobState,
    Scene,
    Topic,
    ValidationResult,
    Verdict,
    fact_pack_from_legacy,
    get_contract_spec,
    job_from_fsm_dict,
    registry_model_names,
    scene_from_legacy_contract,
    topic_from_plan,
    validation_from_preflight,
)
from domain.common import (
    ContractBase,
    SchemaVersionMismatchError,
    new_id,
    parse_schema_version,
    schema_versions_compatible,
)
from domain.enums import ErrorCategory, EvidenceStatus, LifecycleStatus
from domain.errors import AppError
from domain.execution import Checkpoint, JobAttempt
from domain.registry import all_contract_models
from domain.validation import deserialize_contract, expected_schema_version, validate_contract_version
from pipeline.fact_pack import build_fact_pack
from pipeline.scene_contract import attach_contracts_to_plan, build_scene_contract, preflight_scene_contract


def _sample_plan() -> dict:
    return {
        "topic": "AMP003 contract integrity topic",
        "title": "AMP003 contract integrity topic",
        "video_type": "short",
        "scenes": [{"element": "intro", "narration": "Contract validation runtime test."}],
    }


class T001IdentityTests(unittest.TestCase):
    def test_01_uuid_identity_generated(self):
        topic = Topic(title="UUID test")
        UUID(topic.id)

    def test_02_uuid_identity_rejected_invalid(self):
        with self.assertRaises(Exception):
            Topic(title="bad id", id="not-a-uuid")

    def test_03_new_id_is_uuid(self):
        UUID(new_id())


class T001SchemaVersionTests(unittest.TestCase):
    def test_04_valid_schema_version(self):
        topic = Topic(title="valid", schema_version="1.0.0")
        self.assertEqual(topic.schema_version, "1.0.0")

    def test_05_invalid_schema_version_format(self):
        with self.assertRaises(Exception):
            Topic(title="x", schema_version="v1-beta")

    def test_06_version_mismatch_major_rejected(self):
        data = Topic(title="mismatch").model_dump(mode="json")
        data["schema_version"] = "2.0.0"
        with self.assertRaises(SchemaVersionMismatchError):
            Topic.from_json_dict(data)

    def test_07_version_compatible_minor_patch(self):
        data = Topic(title="compat").model_dump(mode="json")
        data["schema_version"] = "1.2.3"
        topic = Topic.from_json_dict(data)
        self.assertEqual(topic.schema_version, "1.2.3")

    def test_08_parse_schema_version(self):
        self.assertEqual(parse_schema_version("1.2.3"), (1, 2, 3))
        self.assertEqual(parse_schema_version("2.0"), (2, 0, 0))

    def test_09_schema_versions_compatible_helper(self):
        self.assertTrue(schema_versions_compatible("1.0.0", "1.0.0"))
        self.assertTrue(schema_versions_compatible("1.5.0", "1.0.0"))
        self.assertFalse(schema_versions_compatible("2.0.0", "1.0.0"))


class T001SerializationTests(unittest.TestCase):
    def test_10_serialization_roundtrip(self):
        topic = Topic(title="Roundtrip topic")
        raw = topic.model_dump(mode="json")
        restored = Topic.model_validate(raw)
        self.assertEqual(restored.title, topic.title)
        self.assertEqual(restored.id, topic.id)

    def test_11_json_deserialization(self):
        fp = FactPack(topic_title="JSON topic", claims=[])
        blob = json.dumps(fp.model_dump(mode="json"))
        fp2 = FactPack.model_validate(json.loads(blob))
        self.assertEqual(fp2.topic_title, "JSON topic")

    def test_12_unknown_field_rejected(self):
        with self.assertRaises(Exception):
            Topic.model_validate({"title": "x", "schema_version": "1.0.0", "unknown_field": True})

    def test_13_deserialize_contract_helper(self):
        data = Job(status=JobState.CREATED).model_dump(mode="json")
        job = deserialize_contract(Job, data)
        self.assertIsInstance(job, Job)


class T001TimestampTests(unittest.TestCase):
    def test_14_timestamps_present(self):
        topic = Topic(title="timestamped")
        self.assertIsInstance(topic.created_at, datetime)
        self.assertIsNotNone(topic.created_at.tzinfo)

    def test_15_timestamp_iso_parse(self):
        raw = Topic(title="iso").model_dump(mode="json")
        raw["created_at"] = "2026-01-15T10:00:00+00:00"
        topic = Topic.model_validate(raw)
        self.assertEqual(topic.created_at.year, 2026)


class T001StatusTaxonomyTests(unittest.TestCase):
    def test_16_job_state_enum_stable(self):
        self.assertEqual(JobState.CREATED.value, "CREATED")
        self.assertIn(JobState.PUBLISHED.value, [s.value for s in JobState])

    def test_17_verdict_enum_stable(self):
        self.assertEqual(Verdict.PASS.value, "PASS")
        self.assertEqual(Verdict.UNKNOWN.value, "UNKNOWN")

    def test_18_lifecycle_status_values(self):
        self.assertEqual(LifecycleStatus.PENDING.value, "pending")

    def test_19_evidence_status_values(self):
        self.assertEqual(EvidenceStatus.VERIFIED.value, "VERIFIED")


class T001AdapterTests(unittest.TestCase):
    def test_20_topic_from_plan_adapter(self):
        topic = topic_from_plan(_sample_plan())
        self.assertEqual(topic.title, "AMP003 contract integrity topic")

    def test_21_fact_pack_legacy_adapter(self):
        legacy = build_fact_pack("Chernobyl", notes="Reactor event in 1986.")
        fp = fact_pack_from_legacy(legacy)
        self.assertEqual(fp.topic_title, "Chernobyl")
        self.assertGreaterEqual(len(fp.claims), 1)

    def test_22_scene_legacy_adapter(self):
        plan = attach_contracts_to_plan(_sample_plan())
        scene = scene_from_legacy_contract(plan["scenes"][0]["scene_contract"], scene_index=0)
        self.assertIsNotNone(scene.visual_plan)

    def test_23_validation_from_preflight_adapter(self):
        contract = build_scene_contract(
            {"element": "intro", "narration": "Preflight adapter validation test claim."},
            scene_id=0,
            topic="Test",
        )
        vr = validation_from_preflight(preflight_scene_contract(contract))
        self.assertIsInstance(vr, ValidationResult)

    def test_24_job_fsm_adapter_backward_compat(self):
        job = job_from_fsm_dict({"state": "generate_short", "job_type": "video_generation"})
        self.assertEqual(job.status, JobState.GENERATING)


class T001RegistryTests(unittest.TestCase):
    def test_25_registry_complete_required_models(self):
        names = set(registry_model_names())
        required = {
            "Topic", "FactPack", "Script", "Scene", "Job", "Checkpoint",
            "ValidationResult", "AppError", "RenderJob", "EngagementAction",
        }
        missing = required - names
        self.assertFalse(missing, f"missing registry entries: {missing}")

    def test_26_all_models_have_schema_version(self):
        for model in all_contract_models():
            self.assertIn("schema_version", model.model_fields, msg=model.__name__)

    def test_27_get_contract_spec_lookup(self):
        spec = get_contract_spec("Topic")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.version, "1.0.0")

    def test_28_registry_count_stable(self):
        self.assertGreaterEqual(len(CONTRACT_REGISTRY), 24)


class T001ValidationHelperTests(unittest.TestCase):
    def test_29_validate_contract_version_pass(self):
        data = {"schema_version": "1.0.0", "title": "x"}
        ok, reason = validate_contract_version(Topic, data)
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_30_validate_contract_version_fail(self):
        data = {"schema_version": "9.0.0", "title": "x"}
        ok, reason = validate_contract_version(Topic, data)
        self.assertFalse(ok)
        self.assertIn("mismatch", reason or "")

    def test_31_expected_schema_version_default(self):
        self.assertEqual(expected_schema_version(Topic), "1.0.0")


class T001ErrorContractTests(unittest.TestCase):
    def test_32_app_error_contract(self):
        err = AppError(
            category=ErrorCategory.VALIDATION_ERROR,
            code="contract_invalid",
            message="test",
        )
        self.assertEqual(err.schema_version, "1.0.0")
        UUID(err.id)

    def test_33_job_attempt_contract(self):
        attempt = JobAttempt(job_id=str(uuid4()), attempt_number=1, status=JobState.GENERATING)
        self.assertEqual(attempt.schema_version, "1.0.0")


class T001BackwardCompatTests(unittest.TestCase):
    def test_34_legacy_fact_pack_version_mapping(self):
        from domain.adapters import legacy_version_to_semver

        self.assertEqual(legacy_version_to_semver("v1"), "1.0")
        self.assertEqual(legacy_version_to_semver("1.0.0"), "1.0.0")

    def test_35_checkpoint_chain_unchanged(self):
        job = Job(status=JobState.PLANNING, entity_id=str(uuid4()))
        cp = Checkpoint(job_id=job.id, stage="planning", state=JobState.PLANNING)
        self.assertEqual(cp.job_id, job.id)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-003 TASK-001 TESTS: {passed} / {result.testsRun}")
    if not result.wasSuccessful():
        raise SystemExit(1)
