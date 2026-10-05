#!/usr/bin/env python3
"""AMP-003 T004-C1 — Visual request identity + fingerprint hardening."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.mock_visual_provider import MockVisualProvider, reset_mock_provider
from pipeline.idempotency.visual_provenance import load_visual_provenance, save_visual_provenance
from pipeline.idempotency.visual_request import (
    GenerationMode,
    VisualIdentityError,
    VisualRequestSpec,
    build_visual_request_from_handoff,
    compute_visual_fingerprint,
    validate_visual_request_identity,
)
from pipeline.idempotency.visual_runtime import execute_visual_request


def _base(**overrides) -> VisualRequestSpec:
    data = dict(
        job_id="job-c1",
        scene_id=1,
        visual_plan_id="feature",
        provider="mock",
        model="mock-v1",
        generation_mode=GenerationMode.TEXT_TO_VIDEO,
        prompt="Cinematic reactor control room",
        visual_prompt="control room",
        element="feature",
        product_name="Chernobyl",
        size="1080x1920",
        duration_sec=5.0,
        seed=42,
        dialogue_id="dlg-uuid-001",
        canonical_scene_id="scene-uuid-001",
        script_id="script-uuid-001",
    )
    data.update(overrides)
    return VisualRequestSpec(**data)


def _handoff(**overrides) -> dict:
    base = {
        "_validated": True,
        "scene_index": 1,
        "dialogue_id": "dlg-uuid-001",
        "canonical_scene_id": "scene-uuid-001",
        "script_id": "script-uuid-001",
        "element": "feature",
    }
    base.update(overrides)
    return base


class T004C1VisualIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mock = MockVisualProvider()
        self.mock.reset()
        reset_mock_provider()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, spec: VisualRequestSpec):
        out = self.tmp / "out.mp4"
        return execute_visual_request(
            self.tmp,
            spec,
            out,
            use_mock=True,
            mock_provider=self.mock,
        )

    # TEST-01
    def test_01_same_request_same_fingerprint(self):
        fp1 = _base().fingerprint()
        fp2 = _base().fingerprint()
        self.assertEqual(fp1, fp2)
        r1 = self._run(_base())
        r2 = self._run(_base())
        self.assertEqual(r1.fingerprint, r2.fingerprint)
        self.assertEqual(self.mock.invocation_count, 1)

    # TEST-02
    def test_02_prompt_change_different_fingerprint(self):
        self.assertNotEqual(
            _base().fingerprint(),
            _base(prompt="Different cinematic prompt").fingerprint(),
        )

    # TEST-03
    def test_03_scene_change_different_fingerprint(self):
        self.assertNotEqual(_base(scene_id=1).fingerprint(), _base(scene_id=2).fingerprint())

    # TEST-04
    def test_04_dialogue_change_different_fingerprint(self):
        self.assertNotEqual(
            _base(dialogue_id="dlg-a").fingerprint(),
            _base(dialogue_id="dlg-b").fingerprint(),
        )

    # TEST-05
    def test_05_segment_change_different_fingerprint(self):
        self.assertNotEqual(
            _base(part_index=1, segment_id="seg-01").fingerprint(),
            _base(part_index=2, segment_id="seg-02").fingerprint(),
        )

    # TEST-06
    def test_06_provider_change_different_fingerprint(self):
        self.assertNotEqual(
            _base(provider="mock").fingerprint(),
            _base(provider="agnes").fingerprint(),
        )

    # TEST-07
    def test_07_model_change_different_fingerprint(self):
        self.assertNotEqual(
            _base(model="mock-v1").fingerprint(),
            _base(model="mock-v2").fingerprint(),
        )

    # TEST-08
    def test_08_resolution_change_different_fingerprint(self):
        self.assertNotEqual(
            _base(size="1080x1920").fingerprint(),
            _base(size="1280x720").fingerprint(),
        )

    # TEST-09
    def test_09_seed_change_different_fingerprint(self):
        self.assertNotEqual(_base(seed=1).fingerprint(), _base(seed=2).fingerprint())

    # TEST-10
    def test_10_revision_change_different_fingerprint(self):
        self.assertNotEqual(
            _base(revision_id="").fingerprint(),
            _base(revision_id="rev-001").fingerprint(),
        )

    # TEST-11
    def test_11_json_ordering_same_fingerprint(self):
        a = _base()
        b = _base()
        fp_a = compute_visual_fingerprint(a)
        fp_b = compute_visual_fingerprint(b)
        self.assertEqual(fp_a, fp_b)
        payload_a = json.loads(json.dumps(a.normalized_inputs(), sort_keys=True))
        payload_b = json.loads(json.dumps(dict(reversed(list(b.normalized_inputs().items())))))
        self.assertEqual(payload_a, payload_b)

    # TEST-12
    def test_12_whitespace_normalization_stable(self):
        fp1 = _base(prompt="  hello world  ", dialogue_id="  dlg-uuid-001  ").fingerprint()
        fp2 = _base(prompt="hello world", dialogue_id="dlg-uuid-001").fingerprint()
        self.assertEqual(fp1, fp2)

    # TEST-13
    def test_13_missing_mandatory_identity_block(self):
        spec = _base(dialogue_id="", canonical_scene_id="")
        with self.assertRaises(VisualIdentityError):
            validate_visual_request_identity(spec, production=True)
        with self.assertRaises(VisualIdentityError):
            build_visual_request_from_handoff(
                _handoff(dialogue_id=""),
                job_id="job-c1",
                visual_plan_id="feature",
                provider="mock",
                model="mock-v1",
                generation_mode=GenerationMode.TEXT_TO_VIDEO,
                prompt="test",
            )

    # TEST-14
    def test_14_invalid_identity_block(self):
        spec = _base(scene_id=-1)
        with self.assertRaises(VisualIdentityError):
            validate_visual_request_identity(spec)
        spec2 = _base()
        with self.assertRaises(VisualIdentityError):
            validate_visual_request_identity(
                spec2,
                production=True,
                expected_scene_index=99,
            )

    # TEST-15
    def test_15_cross_scene_contamination_block(self):
        spec = _base(scene_id=1, canonical_scene_id="scene-uuid-001")
        with self.assertRaises(VisualIdentityError):
            validate_visual_request_identity(
                spec,
                production=True,
                expected_scene_index=2,
                expected_canonical_scene_id="scene-uuid-002",
            )

    # TEST-16
    def test_16_cross_dialogue_contamination_block(self):
        spec = _base(dialogue_id="dlg-wrong")
        with self.assertRaises(VisualIdentityError):
            validate_visual_request_identity(
                spec,
                production=True,
                expected_dialogue_id="dlg-expected",
            )

    # TEST-17
    def test_17_split_segment_collision_block(self):
        from pipeline.idempotency.agnes_bridge import idempotent_generate_agnes_beat

        with self.assertRaises(VisualIdentityError):
            idempotent_generate_agnes_beat(
                work_dir=self.tmp,
                job_id="job-c1",
                scene_id=1,
                part_index=2,
                attempt=1,
                product_name="p",
                element="feature",
                visual_prompt="prompt",
                out_path=self.tmp / "x.mp4",
                dialogue_id="dlg-uuid-001",
                canonical_scene_id="scene-uuid-001",
                segment_id="",
                use_mock=True,
            )

    # TEST-18
    def test_18_intentional_revision_new_identity(self):
        base_fp = _base(revision_id="").fingerprint()
        rev_fp = _base(revision_id="repair-1").fingerprint()
        self.assertNotEqual(base_fp, rev_fp)
        r1 = self._run(_base(revision_id=""))
        r2 = self._run(_base(revision_id="repair-1"))
        self.assertNotEqual(r1.fingerprint, r2.fingerprint)
        self.assertEqual(self.mock.invocation_count, 2)

    def test_handoff_builder_production(self):
        spec = build_visual_request_from_handoff(
            _handoff(),
            job_id="job-c1",
            visual_plan_id="feature",
            provider="mock",
            model="mock-v1",
            generation_mode=GenerationMode.TEXT_TO_VIDEO,
            prompt="test prompt",
        )
        self.assertEqual(spec.dialogue_id, "dlg-uuid-001")
        self.assertEqual(spec.canonical_scene_id, "scene-uuid-001")

    def test_provenance_fingerprint_match(self):
        spec = _base()
        fp = spec.fingerprint()
        save_visual_provenance(
            self.tmp,
            spec=spec,
            fingerprint=fp,
            asset_path=str(self.tmp / "fake.mp4"),
            asset_hash="abc123",
        )
        prov = load_visual_provenance(self.tmp, fp)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["provenance"]["input_hash"], fp)
        self.assertEqual(prov["provenance"]["metadata"]["dialogue_id"], "dlg-uuid-001")
        self.assertEqual(prov["provenance"]["metadata"]["entity_id"], spec.entity_id)

    def test_idempotency_reuse_zero_provider_calls(self):
        spec = _base()
        r1 = self._run(spec)
        self.mock.invocation_count = 0
        r2 = self._run(spec)
        self.assertEqual(r1.fingerprint, r2.fingerprint)
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
