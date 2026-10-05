#!/usr/bin/env python3
"""AMP-003 T004-C2-1 — Agnes bridge boundary contract tests (offline mock)."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.agnes_bridge import idempotent_generate_agnes_beat
from pipeline.idempotency.checkpoint_store import CheckpointStore
from pipeline.idempotency.mock_visual_provider import (
    MockBehavior,
    MockVisualProvider,
    get_mock_provider,
    reset_mock_provider,
)
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyStore
from pipeline.idempotency.visual_provenance import load_visual_provenance
from pipeline.idempotency.visual_request import (
    GenerationMode,
    VisualIdentityError,
    VisualRequestSpec,
    build_visual_request_from_handoff,
    compute_visual_fingerprint,
    validate_visual_request_identity,
)
from pipeline.idempotency.visual_runtime import VisualGenerationResult, execute_visual_request


def _handoff(**overrides) -> dict:
    base = {
        "_validated": True,
        "scene_index": 2,
        "dialogue_id": "dlg-c2-uuid-002",
        "canonical_scene_id": "scene-c2-uuid-002",
        "script_id": "script-c2-uuid",
        "element": "feature",
    }
    base.update(overrides)
    return base


def _bridge_equivalent_spec(**overrides) -> VisualRequestSpec:
    """Spec matching agnes_bridge defaults (IMAGE_TO_VIDEO + catalog)."""
    data = dict(
        job_id="job-c2",
        scene_id=2,
        visual_plan_id="feature",
        provider="agnes",
        model="agnes-video-v2.0",
        generation_mode=GenerationMode.IMAGE_TO_VIDEO,
        prompt="Cinematic control room",
        visual_prompt="Cinematic control room",
        element="feature",
        product_name="TestProduct",
        size="1080x1920",
        duration_sec=5.0,
        dialogue_id="dlg-c2-uuid-002",
        canonical_scene_id="scene-c2-uuid-002",
        script_id="script-c2-uuid",
    )
    data.update(overrides)
    return VisualRequestSpec(**data)


def _prod_kwargs(tmp: Path) -> dict:
    return dict(
        work_dir=tmp,
        job_id="job-c2",
        scene_id=2,
        part_index=0,
        attempt=1,
        product_name="TestProduct",
        element="feature",
        visual_prompt="Cinematic control room",
        out_path=tmp / "agnes_out.mp4",
        dialogue_id="dlg-c2-uuid-002",
        canonical_scene_id="scene-c2-uuid-002",
        script_id="script-c2-uuid",
        use_mock=True,
    )


class T004C2BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_mock_provider()
        self.mock = get_mock_provider()
        self.mock.reset()
        self.mock.behavior = MockBehavior.SUCCESS

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # TEST-01
    def test_01_canonical_gateway_accepts_valid_request(self):
        path = idempotent_generate_agnes_beat(**_prod_kwargs(self.tmp))
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())
        self.assertEqual(self.mock.invocation_count, 1)

    # TEST-02
    def test_02_production_identity_reaches_gateway(self):
        path = idempotent_generate_agnes_beat(**_prod_kwargs(self.tmp))
        self.assertIsNotNone(path)
        spec = _bridge_equivalent_spec()
        fp = spec.fingerprint()
        prov = load_visual_provenance(self.tmp, fp)
        self.assertIsNotNone(prov)
        meta = prov["provenance"]["metadata"]
        self.assertEqual(meta["dialogue_id"], "dlg-c2-uuid-002")
        self.assertEqual(meta["canonical_scene_id"], "scene-c2-uuid-002")
        self.assertEqual(meta["entity_id"], spec.entity_id)

    # TEST-03
    def test_03_missing_scene_identity_rejected(self):
        kw = _prod_kwargs(self.tmp)
        kw["canonical_scene_id"] = ""
        with self.assertRaises(VisualIdentityError):
            idempotent_generate_agnes_beat(**kw)
        self.assertEqual(self.mock.invocation_count, 0)

    # TEST-04
    def test_04_missing_dialogue_identity_rejected(self):
        kw = _prod_kwargs(self.tmp)
        kw["dialogue_id"] = ""
        with self.assertRaises(VisualIdentityError):
            idempotent_generate_agnes_beat(**kw)
        self.assertEqual(self.mock.invocation_count, 0)

    # TEST-05
    def test_05_revision_identity_preserved(self):
        kw = _prod_kwargs(self.tmp)
        kw["revision_id"] = "repair-c2-01"
        path = idempotent_generate_agnes_beat(**kw)
        self.assertIsNotNone(path)
        spec = _bridge_equivalent_spec(revision_id="repair-c2-01")
        self.assertIn("rev-repair-c2-01", spec.entity_id)
        prov = load_visual_provenance(self.tmp, spec.fingerprint())
        self.assertEqual(prov["provenance"]["metadata"]["revision_id"], "repair-c2-01")

    # TEST-06
    def test_06_fingerprint_reaches_runtime_unchanged(self):
        spec = build_visual_request_from_handoff(
            _handoff(),
            job_id="job-c2",
            visual_plan_id="feature",
            provider="mock",
            model="mock-v1",
            generation_mode=GenerationMode.TEXT_TO_VIDEO,
            prompt="Cinematic control room",
        )
        expected_fp = compute_visual_fingerprint(spec)
        out = self.tmp / "fp_test.mp4"
        result = execute_visual_request(
            self.tmp, spec, out, use_mock=True, mock_provider=self.mock
        )
        self.assertEqual(result.fingerprint, expected_fp)

    # TEST-07
    def test_07_provider_execution_inside_canonical_runtime(self):
        runtime_calls: list[str] = []
        original = execute_visual_request

        def _track_runtime(*args, **kwargs):
            runtime_calls.append("execute_visual_request")
            return original(*args, **kwargs)

        with mock.patch(
            "pipeline.idempotency.agnes_bridge.execute_visual_request",
            side_effect=_track_runtime,
        ):
            idempotent_generate_agnes_beat(**_prod_kwargs(self.tmp))
        self.assertEqual(runtime_calls, ["execute_visual_request"])
        self.assertEqual(self.mock.invocation_count, 1)

    # TEST-08
    def test_08_successful_result_passes_validation(self):
        result = execute_visual_request(
            self.tmp,
            build_visual_request_from_handoff(
                _handoff(),
                job_id="job-c2",
                visual_plan_id="feature",
                provider="mock",
                model="mock-v1",
                generation_mode=GenerationMode.TEXT_TO_VIDEO,
                prompt="valid",
            ),
            self.tmp / "valid.mp4",
            use_mock=True,
            mock_provider=self.mock,
        )
        self.assertTrue(result.success)
        self.assertIn(result.action, ("execute", "reuse"))
        self.assertTrue(result.path and result.path.is_file())

    # TEST-09
    def test_09_invalid_result_not_success(self):
        self.mock.behavior = MockBehavior.INVALID_ASSET
        result = execute_visual_request(
            self.tmp,
            build_visual_request_from_handoff(
                _handoff(),
                job_id="job-c2",
                visual_plan_id="feature",
                provider="mock",
                model="mock-v1",
                generation_mode=GenerationMode.TEXT_TO_VIDEO,
                prompt="invalid asset test",
            ),
            self.tmp / "bad.mp4",
            use_mock=True,
            mock_provider=self.mock,
        )
        self.assertFalse(result.success)
        self.assertNotEqual(result.action, "reuse")
        self.assertNotEqual(result.state, IdempotencyState.SUCCEEDED)

    # TEST-10
    def test_10_provenance_fingerprint_matches_request(self):
        idempotent_generate_agnes_beat(**_prod_kwargs(self.tmp))
        spec = _bridge_equivalent_spec()
        fp = spec.fingerprint()
        prov = load_visual_provenance(self.tmp, fp)
        self.assertEqual(prov["provenance"]["input_hash"], fp)

    # TEST-11
    def test_11_checkpoint_written_on_success(self):
        idempotent_generate_agnes_beat(**_prod_kwargs(self.tmp))
        cps = CheckpointStore(self.tmp / "checkpoints").latest_for_job("job-c2")
        visual_cps = [c for c in cps if c.get("stage") == "visual"]
        self.assertTrue(len(visual_cps) >= 1)
        self.assertTrue(visual_cps[-1].get("output_hash"))

    # TEST-12
    def test_12_unknown_state_preserved(self):
        self.mock.behavior = MockBehavior.UNKNOWN
        spec = build_visual_request_from_handoff(
            _handoff(),
            job_id="job-c2",
            visual_plan_id="feature",
            provider="mock",
            model="mock-v1",
            generation_mode=GenerationMode.TEXT_TO_VIDEO,
            prompt="unknown test",
        )
        result = execute_visual_request(
            self.tmp, spec, self.tmp / "unk.mp4", use_mock=True, mock_provider=self.mock
        )
        self.assertEqual(result.action, "unknown")
        self.assertEqual(result.state, IdempotencyState.UNKNOWN)
        store = IdempotencyStore(self.tmp / "idempotency")
        rec = store.get(result.fingerprint)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.request_state, IdempotencyState.UNKNOWN)

    # TEST-13
    def test_13_unknown_no_blind_provider_retry(self):
        self.mock.behavior = MockBehavior.UNKNOWN
        spec = build_visual_request_from_handoff(
            _handoff(),
            job_id="job-c2",
            visual_plan_id="feature",
            provider="mock",
            model="mock-v1",
            generation_mode=GenerationMode.TEXT_TO_VIDEO,
            prompt="unknown retry test",
        )
        r1 = execute_visual_request(
            self.tmp, spec, self.tmp / "unk2.mp4", use_mock=True, mock_provider=self.mock
        )
        count_after_first = self.mock.invocation_count
        r2 = execute_visual_request(
            self.tmp, spec, self.tmp / "unk2.mp4", use_mock=True, mock_provider=self.mock
        )
        self.assertEqual(r1.action, "unknown")
        self.assertIn(r2.action, ("unknown", "duplicate_prevented", "failed"))
        self.assertEqual(self.mock.invocation_count, count_after_first)

    # TEST-14
    def test_14_same_request_reuses_success(self):
        kw = _prod_kwargs(self.tmp)
        p1 = idempotent_generate_agnes_beat(**kw)
        self.mock.invocation_count = 0
        p2 = idempotent_generate_agnes_beat(**kw)
        self.assertIsNotNone(p1)
        self.assertIsNotNone(p2)
        self.assertEqual(self.mock.invocation_count, 0)

    # TEST-15
    def test_15_meaningful_change_new_fingerprint(self):
        spec_a = build_visual_request_from_handoff(
            _handoff(),
            job_id="job-c2",
            visual_plan_id="feature",
            provider="mock",
            model="mock-v1",
            generation_mode=GenerationMode.TEXT_TO_VIDEO,
            prompt="prompt A",
        )
        spec_b = build_visual_request_from_handoff(
            _handoff(),
            job_id="job-c2",
            visual_plan_id="feature",
            provider="mock",
            model="mock-v1",
            generation_mode=GenerationMode.TEXT_TO_VIDEO,
            prompt="prompt B completely different",
        )
        self.assertNotEqual(spec_a.fingerprint(), spec_b.fingerprint())

    # TEST-16
    def test_16_split_no_fabricated_domain_segment_id(self):
        kw = _prod_kwargs(self.tmp)
        kw["part_index"] = 2
        kw["segment_id"] = ""
        with self.assertRaises(VisualIdentityError) as ctx:
            idempotent_generate_agnes_beat(**kw)
        self.assertIn("segment_id", str(ctx.exception).lower())
        handoff_spec = build_visual_request_from_handoff(
            _handoff(),
            job_id="job-c2",
            visual_plan_id="feature",
            provider="agnes",
            model="agnes-video-v2.0",
            generation_mode=GenerationMode.TEXT_TO_VIDEO,
            prompt="split",
            part_index=2,
            segment_id="seg-02",
        )
        self.assertEqual(handoff_spec.segment_id, "seg-02")
        self.assertNotIn("uuid", handoff_spec.segment_id.lower())

    # TEST-17
    def test_17_bridge_provider_boundary_explicit(self):
        import pipeline.idempotency.agnes_bridge as bridge_mod

        self.assertTrue(hasattr(bridge_mod, "idempotent_generate_agnes_beat"))
        self.assertTrue(hasattr(bridge_mod, "execute_visual_request"))
        source = Path(bridge_mod.__file__).read_text(encoding="utf-8")
        self.assertIn("execute_visual_request(", source)
        self.assertIn("generate_agnes_dialogue_clip", source)

    # TEST-18
    def test_18_gateway_contract_deterministic(self):
        spec = build_visual_request_from_handoff(
            _handoff(),
            job_id="job-c2",
            visual_plan_id="feature",
            provider="agnes",
            model="agnes-video-v2.0",
            generation_mode=GenerationMode.TEXT_TO_VIDEO,
            prompt="deterministic",
        )
        fp1 = compute_visual_fingerprint(spec)
        fp2 = compute_visual_fingerprint(spec)
        self.assertEqual(fp1, fp2)
        validate_visual_request_identity(spec, production=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
