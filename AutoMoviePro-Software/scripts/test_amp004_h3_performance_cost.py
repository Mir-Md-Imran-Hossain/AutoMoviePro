"""AMP-004 H3 — Performance & cost control tests (paid APIs = 0)."""
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.compose import clear_ffprobe_duration_cache, ffprobe_duration
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fs_lock import normalize_lock_key, thread_lock_for
from pipeline.idempotency.metrics import (
    COST_NOT_DETERMINABLE,
    UsageEvent,
    load_usage_ledger,
    record_usage_event,
)
from pipeline.idempotency.retry_policy import (
    RetryClass,
    classify_error,
    retry_decision,
    worst_case_expensive_attempts,
)
from pipeline.localization import dedupe_language_codes, translate_text


class H3RetryTests(unittest.TestCase):
    def test_01_config_auth_non_retryable(self):
        for msg in (
            "authentication failed",
            "missing api key",
            "GoogleCircuitOpen: circuit open",
            "budget exceeded",
            "invalid configuration",
        ):
            self.assertEqual(classify_error(RuntimeError(msg)), RetryClass.NON_RETRYABLE)
            d = retry_decision(exc=RuntimeError(msg), attempt=1, max_attempts=5)
            self.assertFalse(d.should_retry)

    def test_02_unlabeled_is_unknown_not_retryable(self):
        self.assertEqual(classify_error(RuntimeError("something odd happened")), RetryClass.UNKNOWN)
        d = retry_decision(exc=RuntimeError("something odd happened"), attempt=1, max_attempts=5)
        self.assertFalse(d.should_retry)

    def test_03_transient_still_retryable_within_bound(self):
        d1 = retry_decision(exc=RuntimeError("503 temporary"), attempt=1, max_attempts=3)
        self.assertTrue(d1.should_retry)
        d2 = retry_decision(exc=RuntimeError("503 temporary"), attempt=3, max_attempts=3)
        self.assertFalse(d2.should_retry)

    def test_04_worst_case_bound_finite(self):
        n = worst_case_expensive_attempts()
        self.assertGreater(n, 0)
        self.assertLessEqual(n, 3 * 2 * 2 * 2 * 2 * 1 * 3)

    def test_05_nested_executor_does_not_blind_retry_config(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            inv = {"n": 0}
            ex = IdempotentExecutor(work, max_attempts=5)

            def boom():
                inv["n"] += 1
                raise RuntimeError("authentication failed — bad credential")

            r = ex.execute(
                job_id="j",
                stage="factpack",
                entity_id="e",
                inputs={"t": 1},
                execute_fn=boom,
                validate_fn=lambda o: (True, "ok"),
                persist_fn=lambda o: str(work / "x.json"),
            )
            self.assertEqual(inv["n"], 1)
            self.assertIn(r.action, ("failed", "unknown"))


class H3AccountingTests(unittest.TestCase):
    def test_10_usage_ledger_no_money(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            t0 = time.perf_counter()
            record_usage_event(
                work,
                UsageEvent(operation="tts", provider="mock", latency_sec=0.01, cache_hit=False),
            )
            _ = time.perf_counter() - t0
            data = load_usage_ledger(work)
            self.assertEqual(data.get("monetary_cost"), COST_NOT_DETERMINABLE)
            self.assertEqual(len(data.get("events") or []), 1)
            self.assertEqual(data["events"][0]["operation"], "tts")


class H3LocalizationTests(unittest.TestCase):
    def test_20_dedupe_languages(self):
        self.assertEqual(dedupe_language_codes(["bn", "bn", "hi", "en", "hi"]), ["bn", "hi"])
        self.assertEqual(
            dedupe_language_codes(["en", "bn"], exclude_source=False),
            ["en", "bn"],
        )

    def test_21_translate_cache_reuse(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            calls = {"n": 0}

            def fake_chat(*args, **kwargs):
                calls["n"] += 1
                return {"text": "অনুবাদিত বাক্য এখানে যথেষ্ট লম্বা", "provider": "mock"}

            with patch("pipeline.llm_router.chat_text", side_effect=fake_chat):
                a = translate_text(
                    "This is a long enough English narration for cache test.",
                    target_lang="bn",
                    work_dir=work,
                    skip_preflight=True,
                    localized_validation=False,
                    google_api_keys=[],
                )
                b = translate_text(
                    "This is a long enough English narration for cache test.",
                    target_lang="bn",
                    work_dir=work,
                    skip_preflight=True,
                    localized_validation=False,
                    google_api_keys=[],
                )
            self.assertEqual(a, b)
            self.assertEqual(calls["n"], 1)


class H3ProbeCacheTests(unittest.TestCase):
    def test_30_ffprobe_cache_hits(self):
        clear_ffprobe_duration_cache()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "clip.bin"
            p.write_bytes(b"0" * 64)
            # Without real media ffprobe returns 0; still exercise cache path
            with patch("pipeline.compose.ffprobe_bin", return_value="ffprobe"), patch(
                "subprocess.check_output", return_value="3.5\n"
            ) as m:
                d1 = ffprobe_duration(p)
                d2 = ffprobe_duration(p)
            self.assertEqual(d1, 3.5)
            self.assertEqual(d2, 3.5)
            self.assertEqual(m.call_count, 1)


class H3ConcurrencyReuseTests(unittest.TestCase):
    def test_40_h1_lock_identity_intact(self):
        a = normalize_lock_key(r"C:\Temp\x.json")
        b = normalize_lock_key(r"\\?\C:\Temp\x.json")
        self.assertEqual(a, b)
        self.assertIs(thread_lock_for(r"C:\Temp\y.json"), thread_lock_for(r"\\?\C:\Temp\y.json"))

    def test_41_concurrent_identical_execute_single_provider(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            inv = {"n": 0}
            lock = threading.Lock()

            def provider():
                with lock:
                    inv["n"] += 1
                    time.sleep(0.02)
                out = work / "out.json"
                out.write_text('{"ok":true}', encoding="utf-8")
                return {"ok": True}

            results = []

            def worker():
                ex = IdempotentExecutor(work)
                r = ex.execute(
                    job_id="j1",
                    stage="factpack",
                    entity_id="e1",
                    inputs={"topic": "same"},
                    execute_fn=provider,
                    validate_fn=lambda o: (True, "ok"),
                    persist_fn=lambda o: str(work / "out.json"),
                )
                results.append(r.action)

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=20)
            self.assertEqual(inv["n"], 1)
            self.assertTrue(all(a in ("execute", "reuse", "duplicate_prevented") for a in results))


class H3SecurityRegressionSmoke(unittest.TestCase):
    def test_50_h2_helpers_still_present(self):
        from app.config import amp_skip_active, local_login_permitted, Settings

        s = Settings(
            _env_file=None,
            intelligence_mode="PRODUCTION",
            amp_allow_local_login=False,
            dry_run_publish=True,
        )
        self.assertTrue(s.dry_run_publish)
        self.assertFalse(local_login_permitted("admin", "admin123", "local", s))
        import os

        prev = os.environ.get("AMP_SKIP_LOCALIZE")
        os.environ["AMP_SKIP_LOCALIZE"] = "1"
        try:
            self.assertFalse(amp_skip_active("AMP_SKIP_LOCALIZE", s))
        finally:
            if prev is None:
                os.environ.pop("AMP_SKIP_LOCALIZE", None)
            else:
                os.environ["AMP_SKIP_LOCALIZE"] = prev


if __name__ == "__main__":
    unittest.main()
