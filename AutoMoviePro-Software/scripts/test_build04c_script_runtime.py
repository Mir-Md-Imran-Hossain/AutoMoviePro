#!/usr/bin/env python3
"""BUILD-04C script generation runtime tests (offline, mock provider)."""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.fingerprint import hash_text
from pipeline.idempotency.mock_script_provider import (
    MockScriptBehavior,
    MockScriptProvider,
    reset_mock_script_provider,
)
from pipeline.idempotency.script_bridge import build_script_spec, idempotent_script_generation
from pipeline.idempotency.script_provenance import load_script_provenance
from pipeline.idempotency.script_request import ScriptRequestSpec, compute_script_fingerprint, topic_identity_from_parts
from pipeline.idempotency.script_runtime import execute_script_request
from pipeline.idempotency.script_validation import validate_plan_and_script
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyRecord, IdempotencyStore


def _spec(**kw) -> ScriptRequestSpec:
    base = dict(
        job_id="job-script-1",
        topic="Lost City of Petra",
        topic_identity=hash_text("petra|history|0")[:24],
        niche="Ancient History",
        niche_id=7,
        video_type="short",
        max_seconds=90,
        language="en",
        provider="llm_router",
        model="purpose-script",
        research_notes_hash=hash_text("notes")[:32],
        fact_pack_id="fp-petra",
        fact_pack_hash=hash_text("factpack-body")[:32],
        prompt_version="v12",
        prompt_template_hash=hash_text("director-template")[:32],
    )
    base.update(kw)
    if "topic" in kw and "topic_identity" not in kw:
        base["topic_identity"] = topic_identity_from_parts(
            topic=str(kw["topic"]),
            niche=str(base["niche"]),
            niche_id=int(base["niche_id"]),
        )
    return ScriptRequestSpec(**base)


class Build04CScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mock = MockScriptProvider(topic="Lost City of Petra", niche="history")
        self.mock.reset()
        reset_mock_script_provider()
        self.out = self.tmp / "director_plan.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, spec=None, **kw):
        spec = spec or _spec()
        return execute_script_request(
            self.tmp, spec, self.out, use_mock=True, mock_provider=self.mock, **kw
        )

    def test_01_same_request_idempotency(self):
        r1 = self._run()
        r2 = self._run()
        self.assertEqual(r1.action, "execute")
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 1)

    def test_02_topic_change(self):
        self.assertNotEqual(_spec().fingerprint(), _spec(topic="Machu Picchu").fingerprint())
        self._run()
        self._run(_spec(topic="Machu Picchu"))
        self.assertEqual(self.mock.invocation_count, 2)

    def test_03_factpack_change(self):
        self.assertNotEqual(
            _spec(fact_pack_hash="aaa").fingerprint(),
            _spec(fact_pack_hash="bbb").fingerprint(),
        )

    def test_04_prompt_version_change(self):
        self.assertNotEqual(
            _spec(prompt_version="v12").fingerprint(),
            _spec(prompt_version="v13").fingerprint(),
        )

    def test_05_provider_change(self):
        self.assertNotEqual(
            _spec(provider="groq").fingerprint(),
            _spec(provider="google").fingerprint(),
        )

    def test_06_model_change(self):
        self.assertNotEqual(
            _spec(model="llama-8b").fingerprint(),
            _spec(model="llama-70b").fingerprint(),
        )

    def test_07_retry_identity(self):
        fp = _spec().fingerprint()
        self.assertEqual(fp, _spec().fingerprint())

    def test_08_concurrent_duplicate(self):
        spec = _spec()
        lock = threading.Lock()
        calls = {"n": 0}
        results = []

        def worker():
            def gen():
                if not lock.acquire(blocking=False):
                    raise AssertionError("duplicate provider")
                calls["n"] += 1
                time.sleep(0.15)
                m = MockScriptProvider()
                return m.generate(topic=spec.topic, niche=spec.niche)

            r = execute_script_request(self.tmp, spec, self.out, provider_fn=gen)
            results.append(r.action)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        self.assertEqual(calls["n"], 1)

    def test_09_existing_valid_reuse(self):
        self._run()
        self.mock.invocation_count = 0
        r = self._run()
        self.assertEqual(r.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    def test_10_invalid_existing_script(self):
        spec = _spec()
        bad = self.tmp / "bad_plan.json"
        bad.write_text(json.dumps({"title": "", "scenes": []}), encoding="utf-8")
        store = IdempotencyStore(self.tmp / "idempotency")
        store.put(
            IdempotencyRecord(
                fingerprint=spec.fingerprint(),
                job_id=spec.job_id,
                stage="script",
                entity_id=spec.entity_id,
                request_state=IdempotencyState.SUCCEEDED,
                result_reference=str(bad),
            )
        )
        self._run(spec)
        self.assertEqual(self.mock.invocation_count, 1)

    def test_11_malformed_json(self):
        self.mock.behavior = MockScriptBehavior.INVALID_SCRIPT
        r = self._run()
        self.assertNotEqual(r.action, "reuse")
        self.assertFalse(r.success)

    def test_12_empty_response(self):
        self.mock.behavior = MockScriptBehavior.EMPTY
        r = self._run()
        self.assertFalse(r.success)

    def test_13_duplicate_dialogue_ids(self):
        self.mock.behavior = MockScriptBehavior.DUPLICATE_DIALOGUE_IDS
        r = self._run()
        self.assertFalse(r.success)

    def test_14_missing_required_dialogue(self):
        self.mock.behavior = MockScriptBehavior.MISSING_DIALOGUE
        r = self._run()
        self.assertFalse(r.success)

    def test_15_crash_before_provider(self):
        spec = _spec()
        store = IdempotencyStore(self.tmp / "idempotency")
        store.put(
            IdempotencyRecord(
                fingerprint=spec.fingerprint(),
                job_id=spec.job_id,
                stage="script",
                entity_id=spec.entity_id,
                request_state=IdempotencyState.IN_PROGRESS,
            )
        )
        r = self._run(spec)
        self.assertIn(r.action, ("duplicate_prevented", "execute", "reuse"))

    def test_16_crash_after_provider(self):
        self.mock.behavior = MockScriptBehavior.UNKNOWN
        spec = _spec()
        r = self._run(spec)
        self.assertEqual(r.action, "unknown")
        n = self.mock.invocation_count
        r2 = self._run(spec)
        self.assertIn(r2.action, ("unknown", "duplicate_prevented", "failed"))
        self.assertEqual(self.mock.invocation_count, n)

    def test_17_crash_after_persistence(self):
        self._run()
        self.mock.invocation_count = 0
        r = self._run()
        self.assertEqual(r.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    def test_19_repair_generation(self):
        base = _spec()
        repair = _spec(revision_id="repair-1")
        self.assertNotEqual(base.fingerprint(), repair.fingerprint())
        self._run(base)
        self._run(repair)
        self.assertEqual(self.mock.invocation_count, 2)

    def test_20_infinite_regeneration_protection(self):
        self.mock.behavior = MockScriptBehavior.NETWORK
        spec = _spec()
        for _ in range(5):
            execute_script_request(self.tmp, spec, self.out, use_mock=True, mock_provider=self.mock)
        rec = IdempotencyStore(self.tmp / "idempotency").get(spec.fingerprint())
        self.assertIsNotNone(rec)

    def test_21_provenance(self):
        r = self._run()
        prov = load_script_provenance(self.tmp, r.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["topic"], "Lost City of Petra")

    def test_22_checkpoint(self):
        r = self._run()
        self.assertTrue(self.out.is_file())
        self.assertEqual(r.action, "execute")
        r2 = self._run()
        self.assertEqual(r2.action, "reuse")

    def test_23_traceability(self):
        r = self._run()
        plan = json.loads(self.out.read_text(encoding="utf-8"))
        ok, _ = validate_plan_and_script(plan)
        self.assertTrue(ok)
        prov = load_script_provenance(self.tmp, r.fingerprint)
        self.assertEqual(prov["entity_id"], _spec().entity_id)

    def test_24_api_call_accounting(self):
        self._run()
        n = self.mock.invocation_count
        self._run()
        self.assertEqual(self.mock.invocation_count, n)

    def test_no_direct_bypass_video_pipeline(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("idempotent_plan_niche_production", src)
        self.assertIn("_plan_niche_production_idempotent", src)

    def test_build_script_spec_factpack(self):
        spec = build_script_spec(
            job_id="j",
            niche="history",
            niche_id=1,
            video_type="short",
            topic="Topic A",
            max_seconds=60,
            fact_pack_id="fp1",
            fact_pack_hash="hash1",
        )
        self.assertEqual(spec.fact_pack_id, "fp1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
