#!/usr/bin/env python3
"""RCP-07 next blocker — TTS classification/failover + semantic circuit sibling tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.provider_error_class import (
    CLASS_403,
    CLASS_429,
    CLASS_503,
    classify_provider_failure,
)
from pipeline.quota_backoff import reset_quota_state
from pipeline.tts_key_map import keys_for_tts_language_with_fallback, reset_english_rotation


class ProviderClassTests(unittest.TestCase):
    def test_01_classify_429_403_503(self):
        self.assertEqual(classify_provider_failure("429 RESOURCE_EXHAUSTED quota")["class"], CLASS_429)
        self.assertEqual(
            classify_provider_failure("403 PERMISSION_DENIED has been suspended")["class"],
            CLASS_403,
        )
        self.assertEqual(
            classify_provider_failure("503 UNAVAILABLE The service is currently unavailable")["class"],
            CLASS_503,
        )

    def test_02_project_identity_extracted_without_secret(self):
        msg = "Consumer 'projects/123456789012' quota exceeded for api_key:AIzaSyFAKESECRET_SHOULD_REDACT"
        c = classify_provider_failure(msg)
        self.assertEqual(c["project_identity"], "projects/123456789012")
        self.assertNotIn("AIzaSy", c["safe_message"])


class TtsRoutingTests(unittest.TestCase):
    def setUp(self):
        reset_english_rotation(0)
        reset_quota_state(keep_per_key=False)

    def tearDown(self):
        reset_quota_state(keep_per_key=False)

    def test_03_429_failsover_next_key(self):
        from pipeline import tts_google

        keys = ["bad_KEY1111", "good_KEY2222"]
        calls = []

        def fake_sdk(api_key, prompt, *, model, voice_name):
            calls.append(api_key[-4:])
            if api_key.endswith("1111"):
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return b"\x00\x00" * 8000

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "n.m4a"
            with mock.patch.object(tts_google, "_tts_via_sdk", side_effect=fake_sdk), mock.patch.object(
                tts_google, "_tts_via_rest", return_value=None
            ), mock.patch.object(tts_google, "_pcm_to_wav"), mock.patch.object(
                tts_google, "_wav_to_m4a", return_value=True
            ), mock.patch("pipeline.google_api_gate._record_call"), mock.patch(
                "pipeline.tts_key_map.on_tts_success"
            ):
                tts_google.synthesize_narration(
                    "Hello",
                    out,
                    language_hint="en",
                    google_api_keys=keys,
                    allow_idempotent_edge_fallback=False,
                )
        self.assertEqual(calls, ["1111", "2222"])

    def test_04_403_no_retry_same_key(self):
        from pipeline import tts_google

        keys = ["susp_KEY20hY", "good_KEY3333"]
        calls = []

        def fake_sdk(api_key, prompt, *, model, voice_name):
            calls.append(api_key[-4:])
            if api_key.endswith("20hY"):
                raise RuntimeError("403 PERMISSION_DENIED Consumer suspended")
            return b"\x00\x00" * 4000

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "n.m4a"
            with mock.patch.object(tts_google, "_tts_via_sdk", side_effect=fake_sdk), mock.patch.object(
                tts_google, "_tts_via_rest", return_value=None
            ), mock.patch.object(tts_google, "_pcm_to_wav"), mock.patch.object(
                tts_google, "_wav_to_m4a", return_value=True
            ), mock.patch("pipeline.google_api_gate._record_call"), mock.patch(
                "pipeline.tts_key_map.on_tts_success"
            ):
                tts_google.synthesize_narration(
                    "Hello",
                    out,
                    language_hint="en",
                    google_api_keys=keys,
                    allow_idempotent_edge_fallback=False,
                    max_retries_per_key=3,
                )
        self.assertEqual(calls.count("20hY"), 1)
        self.assertIn("3333", calls)

    def test_05_503_controlled_retry_then_failover(self):
        from pipeline import tts_google

        keys = ["tmp_KEY503A", "good_KEY4444"]
        calls = []

        def fake_sdk(api_key, prompt, *, model, voice_name):
            calls.append(api_key[-4:])
            if api_key.endswith("503A"):
                raise RuntimeError("503 UNAVAILABLE The service is currently unavailable")
            return b"\x00\x00" * 4000

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "n.m4a"
            with mock.patch.object(tts_google, "_tts_via_sdk", side_effect=fake_sdk), mock.patch.object(
                tts_google, "_tts_via_rest", return_value=None
            ), mock.patch.object(tts_google, "_pcm_to_wav"), mock.patch.object(
                tts_google, "_wav_to_m4a", return_value=True
            ), mock.patch("pipeline.google_api_gate._record_call"), mock.patch(
                "pipeline.tts_key_map.on_tts_success"
            ):
                tts_google.synthesize_narration(
                    "Hello",
                    out,
                    language_hint="en",
                    google_api_keys=keys,
                    allow_idempotent_edge_fallback=False,
                    max_retries_per_key=2,
                )
        self.assertEqual(calls.count("503A"), 2)  # one controlled retry
        self.assertIn("4444", calls)

    def test_06_cooldown_skips_key(self):
        from pipeline.quota_backoff import record_key_quota_hit

        keys = ["a_KEYAAAA", "b_KEYBBBB"]
        record_key_quota_hit(keys[0], "google")
        ordered = keys_for_tts_language_with_fallback(keys, "en")
        self.assertNotIn(keys[0], ordered)

    def test_07_ready_only_after_success_marker(self):
        from pipeline import tts_credential_diagnostics as diag

        diag.clear_tts_ready()
        self.assertFalse(diag.google_tts_is_ready())
        diag.mark_tts_ready(
            fingerprint12="abc123def456",
            suffix="ZZZZ",
            model="gemini-3.1-flash-tts-preview",
            endpoint="https://example.invalid",
        )
        self.assertTrue(diag.google_tts_is_ready())
        diag.clear_tts_ready()


class SemanticObserverTests(unittest.TestCase):
    def setUp(self):
        reset_quota_state(keep_per_key=False)

    def tearDown(self):
        reset_quota_state(keep_per_key=False)
        from pipeline.google_api_gate import close_circuit

        close_circuit()

    def test_08_circuit_open_with_healthy_siblings_attempts(self):
        from pipeline.google_api_gate import open_circuit, close_circuit
        from pipeline import semantic_coverage
        import tempfile
        from pathlib import Path

        open_circuit("critic_daily0")
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "beat.mp4"
            vid.write_bytes(b"\x00" * 5000)
            called = {"n": 0}

            def fake_upload(key, path, instruction):
                called["n"] += 1
                return {
                    "observation_executed": True,
                    "dimensions": {
                        d: {"status": "PASS", "note": "ok"}
                        for d in semantic_coverage.DIMS
                    },
                    "overall": "PASS",
                }

            with mock.patch(
                "pipeline.av_sync_critic._critique_via_video_upload", side_effect=fake_upload
            ), mock.patch(
                "pipeline.av_sync_critic._critique_via_frames", return_value=None
            ), mock.patch(
                "pipeline.semantic_coverage.circuit_is_open", create=True
            ), mock.patch(
                "pipeline.google_api_gate.circuit_is_open", return_value=True
            ), mock.patch(
                "pipeline.quota_backoff.filter_usable_keys", return_value=["k1", "k2"]
            ):
                out = semantic_coverage.observe_semantic_coverage(
                    video_path=vid,
                    contract={
                        "required_subject": "star",
                        "required_entities": ["star"],
                        "layers": {},
                    },
                    google_api_keys=["k1", "k2"],
                )
        close_circuit()
        self.assertGreaterEqual(called["n"], 1)
        self.assertEqual(out.get("observation_method"), "PROVIDER_VIDEO_UPLOAD")
        self.assertTrue(out.get("observation_executed") or out.get("overall") in ("PASS", "FAIL", "UNKNOWN"))
        # Must not hard-abort as UNAVAILABLE solely due to global circuit when siblings exist
        self.assertFalse(
            any(str(i) == "semantic_observation_unavailable:google_circuit_open" for i in (out.get("issues") or []))
        )

    def test_09_unknown_still_blocks_when_no_observation(self):
        from pipeline.google_api_gate import open_circuit, close_circuit
        from pipeline import semantic_coverage
        import tempfile
        from pathlib import Path

        open_circuit("critic_daily0")
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "beat.mp4"
            vid.write_bytes(b"\x00" * 5000)
            with mock.patch("pipeline.quota_backoff.filter_usable_keys", return_value=[]):
                out = semantic_coverage.observe_semantic_coverage(
                    video_path=vid,
                    contract={"required_subject": "x", "required_entities": [], "layers": {}},
                    google_api_keys=["dead"],
                )
        close_circuit()
        self.assertEqual(out["overall"], "UNKNOWN")
        self.assertTrue(out.get("blocking"))
        self.assertEqual(out.get("observation_method"), "UNAVAILABLE")

    def test_10_maybe_trip_circuit_respects_siblings(self):
        from pipeline.google_api_gate import (
            close_circuit,
            circuit_is_open,
            maybe_trip_circuit_if_pool_dead,
        )
        from pipeline.quota_backoff import record_key_quota_hit

        close_circuit()
        keys = ["k_AAA1", "k_BBB2"]
        record_key_quota_hit(keys[0], "google")
        tripped = maybe_trip_circuit_if_pool_dead(keys, reason="test_daily0")
        self.assertFalse(tripped)
        self.assertFalse(circuit_is_open())
        record_key_quota_hit(keys[1], "google")
        tripped2 = maybe_trip_circuit_if_pool_dead(keys, reason="test_daily0_all")
        self.assertTrue(tripped2)
        self.assertTrue(circuit_is_open())
        close_circuit()


if __name__ == "__main__":
    unittest.main()
