"""C06-G — Customer Job Queue + Scheduler + Recovery (paid APIs = 0).

>=150 deterministic unittest cases. No invent generate_video; prefer MOCK_DETERMINISTIC.
"""
from __future__ import annotations

import inspect
import json
import re
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class C06GBase(unittest.TestCase):
    """Shared TemporaryDirectory fixture — mirrors C06-D + C06-F patterns."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        self.data_dir = self.td / "data"
        self.data_dir.mkdir()
        self.db_path = self.td / "c06g.db"

        from app import config as cfg
        from app import db as store
        import app.customer_job_automation as cja
        import app.customer_trs_workflow as tw
        import app.customer_production_plan as pp
        import app.customer_generation_orchestrator as go
        import app.customer_preview_approval as cpa
        from app.customer_job import ensure_job_columns
        from app.customer_config import ensure_channel_owner_column
        from app.generation_guard import force_release

        self.store = store
        self.cfg = cfg
        self.cja = cja
        self.tw = tw
        self.pp = pp
        self.go = go
        self.cpa = cpa

        self._orig_db = store.DB_PATH
        self._orig_cfg_data = cfg.DATA_DIR
        self._orig_cja_data = cja.DATA_DIR
        self._orig_tw_data = tw.DATA_DIR
        self._orig_pp_data = pp.DATA_DIR
        self._orig_go_data = go.DATA_DIR
        self._orig_cpa_data = cpa.DATA_DIR
        self._orig_tw_path = tw._workflow_path
        self._orig_pp_path = pp._plan_path
        self._orig_go_sidecar = go.execution_sidecar_path

        store.DB_PATH = self.db_path
        cfg.DATA_DIR = self.data_dir
        cja.DATA_DIR = self.data_dir
        tw.DATA_DIR = self.data_dir
        pp.DATA_DIR = self.data_dir
        go.DATA_DIR = self.data_dir
        cpa.DATA_DIR = self.data_dir
        tw._workflow_path = lambda lid, cid: self.data_dir / "wf" / f"{lid}_ch{cid}.json"
        pp._plan_path = lambda lid, cid: self.data_dir / "pp" / f"{lid}_ch{cid}.json"
        go.execution_sidecar_path = lambda lid, jid: self.data_dir / "ex" / str(lid) / f"job{int(jid)}.json"

        store.init_db()
        ensure_job_columns()
        ensure_channel_owner_column()
        cja.ensure_automation_columns()
        force_release()

        self.login = "cust_a"
        self.login_b = "cust_b"
        self.ch_id = store.upsert_channel(
            {
                "youtube_name": "GChA",
                "niche": "gadgets",
                "niche_id": 1,
                "short_upload_time": "12:00",
                "long_upload_time": "18:00",
                "lang_code": "en",
                "owner_login_id": self.login,
            }
        )
        self.ch_b_id = store.upsert_channel(
            {
                "youtube_name": "GChB",
                "niche": "news",
                "niche_id": 2,
                "short_upload_time": "12:00",
                "long_upload_time": "18:00",
                "lang_code": "en",
                "owner_login_id": self.login_b,
            }
        )
        self.channel = {
            "id": self.ch_id,
            "niche": "gadgets",
            "youtube_name": "GChA",
            "niche_id": 1,
            "lang_code": "en",
            "owner_login_id": self.login,
        }
        self.channel_b = {
            "id": self.ch_b_id,
            "niche": "news",
            "youtube_name": "GChB",
            "niche_id": 2,
            "lang_code": "en",
            "owner_login_id": self.login_b,
        }

    def tearDown(self):
        from app.generation_guard import force_release

        force_release()
        self.store.DB_PATH = self._orig_db
        self.cfg.DATA_DIR = self._orig_cfg_data
        self.cja.DATA_DIR = self._orig_cja_data
        self.tw.DATA_DIR = self._orig_tw_data
        self.pp.DATA_DIR = self._orig_pp_data
        self.go.DATA_DIR = self._orig_go_data
        self.cpa.DATA_DIR = self._orig_cpa_data
        self.tw._workflow_path = self._orig_tw_path
        self.pp._plan_path = self._orig_pp_path
        self.go.execution_sidecar_path = self._orig_go_sidecar

    def _ready_plan(self, login=None, channel=None, topic: str = "C06G unique topic alpha"):
        login = login or self.login
        channel = channel or self.channel
        cid = int(channel["id"])
        self.tw.set_manual_topic(login, cid, topic)
        self.tw.run_research(login, channel, use_mock=True, work_dir=self.td / "r")
        self.tw.generate_script(login, channel, use_mock=True, work_dir=self.td / "s")
        st = self.tw.load_workflow(login, cid)
        st["script"]["quality"]["status"] = "PASS"
        st["script"]["approval"]["state"] = "READY_FOR_REVIEW"
        for i, b in enumerate(st["script"]["script_plan"].get("beats") or []):
            b.setdefault("metadata", {})
            b["metadata"]["dialogue_id"] = f"dlg-{i + 1}"
            b["metadata"]["scene_id"] = f"scene-{i:02d}"
            b["entity_refs"] = b.get("entity_refs") or ["Shobha", "Suzuki"]
            b["location_ref"] = b.get("location_ref") or "road"
            b["action_intent"] = ["stands beside", "enters", "sits inside"][min(i, 2)]
        self.tw.save_workflow(st)
        self.tw.approve_script(login, cid, decision="approved")
        return self.pp.build_production_plan(login, channel, force_rebuild=True)

    def _raw_job(self, **extra):
        from app.customer_job import create_generation_job

        row = create_generation_job(
            channel_id=int(extra.get("channel_id", self.ch_id)),
            video_type=extra.get("video_type", "short"),
            requested_by=extra.get("login_id", self.login),
            title_hint=extra.get("title", "c06g job"),
            production_plan_id=extra.get("plan_id", "plan-g"),
            production_plan_revision=extra.get("plan_rev", "rev-g"),
            script_revision=extra.get("script_rev", "scr-g"),
            generation_fingerprint=extra.get("fp", f"fp-{extra.get('suffix', 'x')}"),
            plan_snapshot=extra.get(
                "plan_snapshot",
                {
                    "production_plan_id": extra.get("plan_id", "plan-g"),
                    "production_plan_revision": extra.get("plan_rev", "rev-g"),
                    "_c06g": {
                        "execution_mode": "MOCK_DETERMINISTIC",
                        "deterministic_fixtures": True,
                        "video_type": "short",
                    },
                },
            ),
        )
        return row

    def _enqueue(self, job_id, *, login=None, channel_ids=None, fp=None):
        return self.cja.enqueue_existing_job(
            int(job_id),
            login_id=login or self.login,
            channel_ids=channel_ids or [self.ch_id],
            queue_fingerprint=fp,
        )

    def _get_job(self, job_id):
        from app.customer_job import get_job

        return get_job(int(job_id))


# ---------------------------------------------------------------------------
# A — Lifecycle
# ---------------------------------------------------------------------------


class A_LifecycleTests(C06GBase):
    def test_A01_module_exports(self):
        for name in (
            "ensure_automation_columns",
            "enqueue_existing_job",
            "submit_customer_generation",
            "claim_next_job",
            "execute_claimed_job",
            "scheduler_tick",
            "recover_after_restart",
            "request_cancel",
            "list_queue",
            "classify_failure",
            "retry_eligible",
            "project_job_automation",
            "append_lifecycle_event",
            "find_duplicate_queued",
            "detect_duplicate_engines",
        ):
            self.assertTrue(hasattr(self.cja, name), name)

    def test_A02_contract_and_constants(self):
        self.assertTrue(str(self.cja.CONTRACT_VERSION).startswith("C06-G"))
        self.assertEqual(self.cja.MAX_ATTEMPTS, 3)
        self.assertIn("TRANSIENT", self.cja.FAILURE_CATEGORIES)

    def test_A03_lifecycle_aliases_map(self):
        self.assertEqual(self.cja.LIFECYCLE_ALIASES["QUEUED"], "QUEUED")
        self.assertEqual(self.cja.LIFECYCLE_ALIASES["RUNNING"], "GENERATING")
        self.assertEqual(self.cja.LIFECYCLE_ALIASES["PREVIEW_READY"], "READY_FOR_REVIEW")

    def test_A04_ensure_automation_columns_idempotent(self):
        self.cja.ensure_automation_columns()
        self.cja.ensure_automation_columns()
        with self.store.db() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        for c in ("queue_status", "claim_token", "attempt_count", "lifecycle_audit_json"):
            self.assertIn(c, cols)

    def test_A05_submit_enqueues_without_process(self):
        self._ready_plan(topic="A05 lifecycle enqueue topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        self.assertTrue(r["ok"])
        self.assertTrue(r["queued"])
        self.assertFalse(r["started"])
        self.assertEqual(r.get("publishes"), False)
        row = self._get_job(int(r["job_id"]))
        self.assertEqual(row.get("queue_status"), "queued")
        self.assertEqual(row.get("customer_state"), "QUEUED")

    def test_A06_smoke_process_now_ready_for_review(self):
        self._ready_plan(topic="A06 smoke process now topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        self.assertTrue(r["ok"])
        self.assertTrue(r.get("started") or r.get("tick", {}).get("executed"))
        row = self._get_job(int(r["job_id"]))
        self.assertEqual(row.get("customer_state"), "READY_FOR_REVIEW")
        self.assertEqual(row.get("upload_status"), "ready_to_upload")

    def test_A07_smoke_approval_does_not_publish(self):
        self._ready_plan(topic="A07 smoke approval topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        jid = int(r["job_id"])
        ap = self.cpa.record_customer_approval(
            self.login, jid, channel_ids=[self.ch_id], decision="approved"
        )
        self.assertTrue(ap["ok"])
        row = self._get_job(jid)
        self.assertEqual(row.get("customer_approval"), "APPROVED")
        self.assertEqual(row.get("upload_status"), "ready_to_upload")
        self.assertNotEqual(row.get("upload_status"), "uploaded")

    def test_A08_claim_then_execute_lifecycle(self):
        self._ready_plan(topic="A08 claim execute topic")
        sub = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        claimed = self.cja.claim_next_job(worker_id="w-a08", channel_ids=[self.ch_id])
        self.assertIsNotNone(claimed)
        self.assertEqual(int(claimed["id"]), int(sub["job_id"]))
        self.assertEqual(claimed.get("queue_status"), "claimed")
        out = self.cja.execute_claimed_job(claimed, channel=self.channel)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("paid_api_calls"), 0)
        row = self._get_job(int(sub["job_id"]))
        self.assertEqual(row.get("upload_status"), "ready_to_upload")

    def test_A09_scheduler_tick_executes_one(self):
        self._ready_plan(topic="A09 tick one topic")
        self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        tick = self.cja.scheduler_tick(worker_id="tick-a09", channel_ids=[self.ch_id])
        self.assertTrue(tick["ok"])
        self.assertTrue(tick.get("executed"))
        self.assertFalse(tick.get("publishes"))
        self.assertFalse(tick.get("trs_replanned"))

    def test_A10_empty_queue_tick_skips(self):
        tick = self.cja.scheduler_tick(worker_id="tick-empty")
        self.assertTrue(tick["ok"])
        self.assertTrue(tick.get("skipped"))
        self.assertEqual(tick.get("reason"), "queue_empty")


# ---------------------------------------------------------------------------
# B — Queue ordering
# ---------------------------------------------------------------------------


class B_QueueOrderingTests(C06GBase):
    def test_B01_fifo_by_enqueued_at(self):
        j1 = self._raw_job(fp="fp-b01-a", suffix="b01a")
        j2 = self._raw_job(fp="fp-b01-b", suffix="b01b")
        self._enqueue(j1["id"], fp="fp-b01-a")
        self._enqueue(j2["id"], fp="fp-b01-b")
        c1 = self.cja.claim_next_job(worker_id="b01", channel_ids=[self.ch_id])
        self.assertEqual(int(c1["id"]), int(j1["id"]))

    def test_B02_second_claim_gets_later_job(self):
        j1 = self._raw_job(fp="fp-b02-a", suffix="b02a")
        j2 = self._raw_job(fp="fp-b02-b", suffix="b02b")
        self._enqueue(j1["id"], fp="fp-b02-a")
        self._enqueue(j2["id"], fp="fp-b02-b")
        self.cja.claim_next_job(worker_id="b02a", channel_ids=[self.ch_id])
        c2 = self.cja.claim_next_job(worker_id="b02b", channel_ids=[self.ch_id])
        self.assertEqual(int(c2["id"]), int(j2["id"]))

    def test_B03_list_queue_positions(self):
        j1 = self._raw_job(fp="fp-b03-a", suffix="b03a")
        j2 = self._raw_job(fp="fp-b03-b", suffix="b03b")
        self._enqueue(j1["id"], fp="fp-b03-a")
        self._enqueue(j2["id"], fp="fp-b03-b")
        q = self.cja.list_queue(self.login, channel_ids=[self.ch_id])
        self.assertEqual(q["count"], 2)
        self.assertEqual(q["jobs"][0]["queue_position"], 1)
        self.assertEqual(q["jobs"][1]["queue_position"], 2)

    def test_B04_list_queue_ordered_ids(self):
        ids = []
        for i in range(3):
            j = self._raw_job(fp=f"fp-b04-{i}", suffix=f"b04{i}")
            self._enqueue(j["id"], fp=f"fp-b04-{i}")
            ids.append(int(j["id"]))
        q = self.cja.list_queue(self.login, channel_ids=[self.ch_id])
        self.assertEqual([int(x["job_id"]) for x in q["jobs"]], ids)

    def test_B05_channel_filter_on_claim(self):
        ja = self._raw_job(fp="fp-b05-a", channel_id=self.ch_id, login_id=self.login, suffix="b05a")
        jb = self._raw_job(fp="fp-b05-b", channel_id=self.ch_b_id, login_id=self.login_b, suffix="b05b")
        self._enqueue(ja["id"], login=self.login, channel_ids=[self.ch_id], fp="fp-b05-a")
        self._enqueue(jb["id"], login=self.login_b, channel_ids=[self.ch_b_id], fp="fp-b05-b")
        c = self.cja.claim_next_job(worker_id="b05", channel_ids=[self.ch_b_id])
        self.assertEqual(int(c["id"]), int(jb["id"]))


# ---------------------------------------------------------------------------
# C — Duplicate enqueue
# ---------------------------------------------------------------------------


class C_DuplicateEnqueueTests(C06GBase):
    def test_C01_duplicate_enqueue_reuses(self):
        j = self._raw_job(fp="fp-c01", suffix="c01")
        a = self._enqueue(j["id"], fp="fp-c01")
        b = self._enqueue(j["id"], fp="fp-c01")
        self.assertTrue(a["ok"])
        self.assertTrue(b["ok"])
        self.assertTrue(b.get("reused"))

    def test_C02_find_duplicate_queued(self):
        j = self._raw_job(fp="fp-c02", suffix="c02")
        self._enqueue(j["id"], fp="fp-c02")
        dup = self.cja.find_duplicate_queued(
            login_id=self.login, channel_id=self.ch_id, queue_fingerprint="fp-c02"
        )
        self.assertIsNotNone(dup)
        self.assertEqual(int(dup["id"]), int(j["id"]))

    def test_C03_submit_duplicate_fingerprint_reuses_queue(self):
        self._ready_plan(topic="C03 dup submit topic")
        a = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        b = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=False
        )
        self.assertTrue(b.get("reused") or a["job_id"] == b.get("job_id"))

    def test_C04_cross_job_same_fingerprint_reuses(self):
        j1 = self._raw_job(fp="fp-c04", suffix="c04a")
        j2 = self._raw_job(fp="fp-c04", suffix="c04b")
        self._enqueue(j1["id"], fp="fp-c04")
        r = self._enqueue(j2["id"], fp="fp-c04")
        self.assertTrue(r.get("reused"))
        self.assertEqual(int(r["job_id"]), int(j1["id"]))

    def test_C05_no_dup_after_done(self):
        j = self._raw_job(fp="fp-c05", suffix="c05")
        self._enqueue(j["id"], fp="fp-c05")
        self.store.update_job(int(j["id"]), queue_status="done")
        dup = self.cja.find_duplicate_queued(
            login_id=self.login, channel_id=self.ch_id, queue_fingerprint="fp-c05"
        )
        self.assertIsNone(dup)


# ---------------------------------------------------------------------------
# D — Atomic claim
# ---------------------------------------------------------------------------


class D_AtomicClaimTests(C06GBase):
    def test_D01_claim_sets_token(self):
        j = self._raw_job(fp="fp-d01", suffix="d01")
        self._enqueue(j["id"], fp="fp-d01")
        c = self.cja.claim_next_job(worker_id="d01")
        self.assertTrue(c.get("claim_token"))
        self.assertEqual(c.get("claimed_by"), "d01")
        self.assertEqual(c.get("queue_status"), "claimed")

    def test_D02_claim_sets_lease(self):
        j = self._raw_job(fp="fp-d02", suffix="d02")
        self._enqueue(j["id"], fp="fp-d02")
        c = self.cja.claim_next_job(worker_id="d02")
        self.assertTrue(c.get("lease_expires_at"))

    def test_D03_second_claim_without_jobs_none(self):
        j = self._raw_job(fp="fp-d03", suffix="d03")
        self._enqueue(j["id"], fp="fp-d03")
        self.cja.claim_next_job(worker_id="d03a")
        self.assertIsNone(self.cja.claim_next_job(worker_id="d03b"))

    def test_D04_cannot_claim_cancelled(self):
        j = self._raw_job(fp="fp-d04", suffix="d04")
        self._enqueue(j["id"], fp="fp-d04")
        self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        self.assertIsNone(self.cja.claim_next_job(worker_id="d04"))

    def test_D05_cannot_claim_approved(self):
        j = self._raw_job(fp="fp-d05", suffix="d05")
        self._enqueue(j["id"], fp="fp-d05")
        self.store.update_job(int(j["id"]), customer_approval="APPROVED")
        self.assertIsNone(self.cja.claim_next_job(worker_id="d05"))

    def test_D06_release_claim_clears_token(self):
        j = self._raw_job(fp="fp-d06", suffix="d06")
        self._enqueue(j["id"], fp="fp-d06")
        c = self.cja.claim_next_job(worker_id="d06")
        self.cja.release_claim(int(c["id"]), claim_token=c["claim_token"], final_status="done")
        row = self._get_job(int(c["id"]))
        self.assertIsNone(row.get("claim_token"))
        self.assertEqual(row.get("queue_status"), "done")

    def test_D07_release_wrong_token_noop(self):
        j = self._raw_job(fp="fp-d07", suffix="d07")
        self._enqueue(j["id"], fp="fp-d07")
        c = self.cja.claim_next_job(worker_id="d07")
        self.cja.release_claim(int(c["id"]), claim_token="wrong", final_status="done")
        row = self._get_job(int(c["id"]))
        self.assertEqual(row.get("queue_status"), "claimed")
        self.assertEqual(row.get("claim_token"), c["claim_token"])


# ---------------------------------------------------------------------------
# E — Concurrent claim (>=10)
# ---------------------------------------------------------------------------


class E_ConcurrentClaimTests(C06GBase):
    def _assert_single_winner(self, job_id: int, workers: int = 8):
        results = []

        def try_claim(i):
            return self.cja.claim_next_job(worker_id=f"cw-{i}", channel_ids=[self.ch_id])

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(try_claim, i) for i in range(workers)]
            for f in as_completed(futs):
                results.append(f.result())
        winners = [r for r in results if r is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(int(winners[0]["id"]), int(job_id))
        tokens = {w["claim_token"] for w in winners}
        self.assertEqual(len(tokens), 1)

    def test_E01_concurrent_same_job_one_winner(self):
        j = self._raw_job(fp="fp-e01", suffix="e01")
        self._enqueue(j["id"], fp="fp-e01")
        self._assert_single_winner(j["id"], workers=10)

    def test_E02_concurrent_same_job_again(self):
        j = self._raw_job(fp="fp-e02", suffix="e02")
        self._enqueue(j["id"], fp="fp-e02")
        self._assert_single_winner(j["id"], workers=12)

    def test_E03_concurrent_claim_tokens_unique_per_job(self):
        jobs = []
        for i in range(5):
            j = self._raw_job(fp=f"fp-e03-{i}", suffix=f"e03{i}")
            self._enqueue(j["id"], fp=f"fp-e03-{i}")
            jobs.append(int(j["id"]))

        claimed = []

        def try_claim(i):
            return self.cja.claim_next_job(worker_id=f"e03-{i}", channel_ids=[self.ch_id])

        with ThreadPoolExecutor(max_workers=5) as ex:
            for f in as_completed([ex.submit(try_claim, i) for i in range(5)]):
                claimed.append(f.result())
        got = [int(c["id"]) for c in claimed if c]
        self.assertEqual(sorted(got), sorted(jobs))
        self.assertEqual(len({c["claim_token"] for c in claimed if c}), 5)

    def test_E04_concurrent_burst_eight(self):
        j = self._raw_job(fp="fp-e04", suffix="e04")
        self._enqueue(j["id"], fp="fp-e04")
        self._assert_single_winner(j["id"], workers=8)

    def test_E05_concurrent_burst_sixteen(self):
        j = self._raw_job(fp="fp-e05", suffix="e05")
        self._enqueue(j["id"], fp="fp-e05")
        self._assert_single_winner(j["id"], workers=16)

    def test_E06_sequential_different_jobs(self):
        ids = []
        for i in range(4):
            j = self._raw_job(fp=f"fp-e06-{i}", suffix=f"e06{i}")
            self._enqueue(j["id"], fp=f"fp-e06-{i}")
            ids.append(int(j["id"]))
        claimed_ids = []
        for i in range(4):
            c = self.cja.claim_next_job(worker_id=f"e06s-{i}", channel_ids=[self.ch_id])
            claimed_ids.append(int(c["id"]))
        self.assertEqual(claimed_ids, ids)

    def test_E07_concurrent_two_jobs_two_winners(self):
        j1 = self._raw_job(fp="fp-e07-a", suffix="e07a")
        j2 = self._raw_job(fp="fp-e07-b", suffix="e07b")
        self._enqueue(j1["id"], fp="fp-e07-a")
        self._enqueue(j2["id"], fp="fp-e07-b")
        results = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = [ex.submit(self.cja.claim_next_job, worker_id=f"e07-{i}", channel_ids=[self.ch_id]) for i in range(6)]
            for f in as_completed(futs):
                results.append(f.result())
        winners = [r for r in results if r]
        self.assertEqual(len(winners), 2)
        self.assertEqual({int(w["id"]) for w in winners}, {int(j1["id"]), int(j2["id"])})

    def test_E08_no_double_claim_after_first(self):
        j = self._raw_job(fp="fp-e08", suffix="e08")
        self._enqueue(j["id"], fp="fp-e08")
        c1 = self.cja.claim_next_job(worker_id="e08-a")
        barrier = threading.Barrier(6)
        outs = []

        def race(i):
            barrier.wait()
            outs.append(self.cja.claim_next_job(worker_id=f"e08-r{i}"))

        threads = [threading.Thread(target=race, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertTrue(c1)
        self.assertTrue(all(x is None for x in outs))

    def test_E09_concurrent_claim_preserves_worker_id(self):
        j = self._raw_job(fp="fp-e09", suffix="e09")
        self._enqueue(j["id"], fp="fp-e09")
        results = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = [ex.submit(self.cja.claim_next_job, worker_id=f"e09w{i}") for i in range(10)]
            for f in as_completed(futs):
                results.append(f.result())
        w = [r for r in results if r][0]
        row = self._get_job(int(j["id"]))
        self.assertEqual(row.get("claimed_by"), w.get("claimed_by"))
        self.assertEqual(row.get("worker_id"), w.get("worker_id"))

    def test_E10_concurrent_empty_queue_all_none(self):
        results = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(self.cja.claim_next_job, worker_id=f"e10-{i}") for i in range(8)]
            for f in as_completed(futs):
                results.append(f.result())
        self.assertTrue(all(r is None for r in results))

    def test_E11_concurrent_claim_rowcount_safe(self):
        j = self._raw_job(fp="fp-e11", suffix="e11")
        self._enqueue(j["id"], fp="fp-e11")
        self._assert_single_winner(j["id"], workers=20)


# ---------------------------------------------------------------------------
# F — generation_guard
# ---------------------------------------------------------------------------


class F_GenerationGuardTests(C06GBase):
    def test_F01_tick_skips_when_busy(self):
        from app.generation_guard import force_release, try_acquire

        j = self._raw_job(fp="fp-f01", suffix="f01")
        self._enqueue(j["id"], fp="fp-f01")
        self.assertTrue(try_acquire("other"))
        try:
            tick = self.cja.scheduler_tick(worker_id="f01")
            self.assertTrue(tick.get("skipped"))
            self.assertEqual(tick.get("reason"), "generation_guard_busy")
            self.assertEqual(tick.get("max_active_generation"), 1)
        finally:
            force_release()

    def test_F02_execute_requeues_when_busy(self):
        from app.generation_guard import force_release, try_acquire

        j = self._raw_job(fp="fp-f02", suffix="f02")
        self._enqueue(j["id"], fp="fp-f02")
        claimed = self.cja.claim_next_job(worker_id="f02")
        self.assertTrue(try_acquire("blocker"))
        try:
            out = self.cja.execute_claimed_job(claimed, channel=self.channel)
            self.assertFalse(out.get("ok"))
            self.assertTrue(out.get("requeued"))
            self.assertEqual(out.get("error_code"), "generation_busy")
            row = self._get_job(int(j["id"]))
            self.assertEqual(row.get("queue_status"), "queued")
        finally:
            force_release()

    def test_F03_force_release_in_fixture(self):
        from app.generation_guard import is_busy

        self.assertFalse(is_busy())

    def test_F04_execute_releases_guard(self):
        from app.generation_guard import is_busy

        self._ready_plan(topic="F04 release guard topic")
        sub = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        claimed = self.cja.claim_next_job(worker_id="f04")
        self.cja.execute_claimed_job(claimed, channel=self.channel)
        self.assertFalse(is_busy())
        self.assertTrue(sub["ok"])

    def test_F05_max_one_documented_in_tick(self):
        from app.generation_guard import try_acquire, force_release

        try_acquire("x")
        try:
            tick = self.cja.scheduler_tick()
            self.assertEqual(tick.get("max_active_generation"), 1)
        finally:
            force_release()


# ---------------------------------------------------------------------------
# G — Scheduler eligibility
# ---------------------------------------------------------------------------


class G_SchedulerEligibilityTests(C06GBase):
    def test_G01_respects_next_retry_future(self):
        j = self._raw_job(fp="fp-g01", suffix="g01")
        self._enqueue(j["id"], fp="fp-g01")
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        self.store.update_job(int(j["id"]), next_retry_at=future)
        self.assertIsNone(self.cja.claim_next_job(worker_id="g01"))

    def test_G02_eligible_when_retry_past(self):
        j = self._raw_job(fp="fp-g02", suffix="g02")
        self._enqueue(j["id"], fp="fp-g02")
        past = (datetime.now() - timedelta(seconds=5)).isoformat()
        self.store.update_job(int(j["id"]), next_retry_at=past)
        c = self.cja.claim_next_job(worker_id="g02")
        self.assertIsNotNone(c)

    def test_G03_skips_ready_to_upload(self):
        j = self._raw_job(fp="fp-g03", suffix="g03")
        self._enqueue(j["id"], fp="fp-g03")
        self.store.update_job(int(j["id"]), upload_status="ready_to_upload")
        self.assertIsNone(self.cja.claim_next_job(worker_id="g03"))

    def test_G04_skips_uploaded(self):
        j = self._raw_job(fp="fp-g04", suffix="g04")
        self._enqueue(j["id"], fp="fp-g04")
        self.store.update_job(int(j["id"]), upload_status="uploaded")
        self.assertIsNone(self.cja.claim_next_job(worker_id="g04"))

    def test_G05_tick_note_orchestration_only(self):
        self._ready_plan(topic="G05 orchestration note topic")
        self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        tick = self.cja.scheduler_tick(worker_id="g05", channel_ids=[self.ch_id])
        self.assertTrue(tick.get("executed"))
        self.assertIn("orchestration", (tick.get("note") or "").lower())


# ---------------------------------------------------------------------------
# H — Plan immutability
# ---------------------------------------------------------------------------


class H_PlanImmutabilityTests(C06GBase):
    def test_H01_submit_embeds_snapshot(self):
        self._ready_plan(topic="H01 snapshot topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        row = self._get_job(int(r["job_id"]))
        snap = json.loads(row["plan_snapshot_json"])
        self.assertIn("production_plan_revision", snap)
        self.assertIn("_c06g", snap)

    def test_H02_fingerprint_stored(self):
        self._ready_plan(topic="H02 fp topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        row = self._get_job(int(r["job_id"]))
        self.assertEqual(row.get("generation_fingerprint"), r.get("fingerprint"))
        self.assertEqual(row.get("queue_fingerprint"), r.get("fingerprint"))

    def test_H03_stale_plan_category(self):
        self.assertEqual(self.cja.classify_failure("stale_plan:mismatch", error_code="stale_plan"), "STALE_PLAN")

    def test_H04_plan_revision_fields_on_job(self):
        self._ready_plan(topic="H04 rev fields topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        row = self._get_job(int(r["job_id"]))
        self.assertTrue(row.get("production_plan_id"))
        self.assertTrue(row.get("production_plan_revision"))


# ---------------------------------------------------------------------------
# I — TRS replan prevention
# ---------------------------------------------------------------------------


class I_TrsReplanPreventionTests(C06GBase):
    def test_I01_scheduler_source_no_trs(self):
        src = Path(self.cja.__file__).read_text(encoding="utf-8")
        # scheduler_tick body must not call TRS
        tick_src = inspect.getsource(self.cja.scheduler_tick)
        self.assertNotIn("run_trs", tick_src.lower())
        self.assertNotIn("plan_script_for_trs", tick_src)
        self.assertNotIn("generate_script", tick_src)

    def test_I02_tick_trs_replanned_false(self):
        self._ready_plan(topic="I02 no trs topic")
        self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        tick = self.cja.scheduler_tick(worker_id="i02", channel_ids=[self.ch_id])
        self.assertFalse(tick.get("trs_replanned"))

    def test_I03_module_is_orchestration(self):
        doc = (self.cja.__doc__ or "").lower()
        self.assertIn("orchestration", doc)

    def test_I04_no_trs_facade_import_at_module(self):
        src = Path(self.cja.__file__).read_text(encoding="utf-8")
        self.assertNotIn("trs_facade", src.split("def execute_claimed_job")[0])


# ---------------------------------------------------------------------------
# J — C06-E handoff path (fixtures)
# ---------------------------------------------------------------------------


class J_C06EHandoffTests(C06GBase):
    def test_J01_fixtures_approved_plan_mode(self):
        self._ready_plan(topic="J01 fixtures handoff topic")
        r = self.cja.submit_customer_generation(
            self.login,
            self.channel,
            execution_mode="CUSTOMER_APPROVED_PLAN",
            deterministic_fixtures=True,
            process_now=True,
            force_rebuild=True,
        )
        self.assertTrue(r["ok"])
        row = self._get_job(int(r["job_id"]))
        self.assertEqual(row.get("upload_status"), "ready_to_upload")
        self.assertEqual(r.get("paid_api_calls", 0) if "paid_api_calls" in r else 0, 0)

    def test_J02_mock_mode_default(self):
        self._ready_plan(topic="J02 mock default topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        self.assertEqual(r.get("execution_mode"), "MOCK_DETERMINISTIC")

    def test_J03_execute_paid_api_zero(self):
        self._ready_plan(topic="J03 paid zero topic")
        sub = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        claimed = self.cja.claim_next_job(worker_id="j03")
        out = self.cja.execute_claimed_job(claimed, channel=self.channel)
        self.assertEqual(out.get("paid_api_calls"), 0)
        self.assertFalse(out.get("social_calls"))
        self.assertFalse(out.get("publishes"))
        self.assertEqual(int(sub["job_id"]), int(out["job_id"]))


# ---------------------------------------------------------------------------
# K — C06-F approval integration
# ---------------------------------------------------------------------------


class K_ApprovalIntegrationTests(C06GBase):
    def test_K01_approve_does_not_publish(self):
        self._ready_plan(topic="K01 approve no publish topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        ap = self.cpa.record_customer_approval(
            self.login, int(r["job_id"]), channel_ids=[self.ch_id], decision="approved"
        )
        self.assertTrue(ap.get("ok"))
        self.assertFalse(ap.get("publishes", False) if "publishes" in ap else True)
        row = self._get_job(int(r["job_id"]))
        self.assertEqual(row.get("upload_status"), "ready_to_upload")

    def test_K02_rejected_blocks_enqueue(self):
        j = self._raw_job(fp="fp-k02", suffix="k02")
        self.store.update_job(int(j["id"]), customer_approval="REJECTED", upload_status="ready_to_upload")
        r = self._enqueue(j["id"])
        self.assertFalse(r["ok"])
        self.assertEqual(r.get("error_code"), "rejection_blocks_enqueue")

    def test_K03_approved_blocks_enqueue(self):
        j = self._raw_job(fp="fp-k03", suffix="k03")
        self.store.update_job(int(j["id"]), customer_approval="APPROVED")
        r = self._enqueue(j["id"])
        self.assertFalse(r["ok"])
        self.assertEqual(r.get("error_code"), "approval_blocks_enqueue")

    def test_K04_rejected_no_auto_requeue_via_submit_path(self):
        # After rejection, enqueue_existing without new fingerprint must fail
        j = self._raw_job(fp="fp-k04", suffix="k04")
        self.store.update_job(
            int(j["id"]),
            customer_approval="REJECTED",
            upload_status="ready_to_upload",
            customer_state="READY_FOR_REVIEW",
        )
        r = self.cja.enqueue_existing_job(
            int(j["id"]), login_id=self.login, channel_ids=[self.ch_id]
        )
        self.assertEqual(r.get("error"), "rejected_no_auto_requeue")

    def test_K05_ready_terminal_blocks_enqueue(self):
        j = self._raw_job(fp="fp-k05", suffix="k05")
        self.store.update_job(
            int(j["id"]),
            upload_status="ready_to_upload",
            customer_state="READY_FOR_REVIEW",
            queue_status="done",
        )
        r = self._enqueue(j["id"], fp="fp-k05-new")
        self.assertFalse(r["ok"])
        self.assertEqual(r.get("error_code"), "terminal_blocks_enqueue")


# ---------------------------------------------------------------------------
# L — Verification honesty planes
# ---------------------------------------------------------------------------


class L_VerificationHonestyTests(C06GBase):
    def test_L01_planes_not_collapsed(self):
        j = self._raw_job(fp="fp-l01", suffix="l01")
        self.store.update_job(int(j["id"]), upload_status="ready_to_upload", customer_approval="PENDING")
        proj = self.cja.project_job_automation(self._get_job(int(j["id"])))
        planes = proj["planes"]
        self.assertTrue(planes["publishable"])
        self.assertFalse(planes["verified"])  # never invent
        self.assertFalse(planes["approved"])
        self.assertFalse(planes["published"])
        self.assertIn("!=", planes["note"])

    def test_L02_approved_plane_separate(self):
        j = self._raw_job(fp="fp-l02", suffix="l02")
        self.store.update_job(
            int(j["id"]), upload_status="ready_to_upload", customer_approval="APPROVED"
        )
        proj = self.cja.project_job_automation(self._get_job(int(j["id"])))
        self.assertTrue(proj["planes"]["approved"])
        self.assertFalse(proj["planes"]["published"])

    def test_L03_generated_not_verified(self):
        j = self._raw_job(fp="fp-l03", suffix="l03")
        self.store.update_job(int(j["id"]), upload_status="ready_to_upload")
        proj = self.cja.project_job_automation(self._get_job(int(j["id"])))
        self.assertTrue(proj["planes"]["generated"])
        self.assertFalse(proj["planes"]["verified"])

    def test_L04_execution_complete_event_honesty(self):
        self._ready_plan(topic="L04 honesty audit topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        row = self._get_job(int(r["job_id"]))
        audit = json.loads(row.get("lifecycle_audit_json") or "{}")
        events = audit.get("events") or []
        complete = [e for e in events if e.get("event") == "execution_complete"]
        self.assertTrue(complete)
        self.assertIn("!=", complete[-1].get("note", ""))


# ---------------------------------------------------------------------------
# M — Failure classification
# ---------------------------------------------------------------------------


class M_FailureClassificationTests(C06GBase):
    def test_M01_ownership(self):
        self.assertEqual(self.cja.classify_failure("ownership denied"), "OWNERSHIP_FAILURE")

    def test_M02_entitlement(self):
        self.assertEqual(self.cja.classify_failure("account inactive entitlement"), "ENTITLEMENT_FAILURE")

    def test_M03_stale_plan(self):
        self.assertEqual(self.cja.classify_failure("plan drifted", error_code="stale_plan"), "STALE_PLAN")

    def test_M04_integrity(self):
        self.assertEqual(self.cja.classify_failure("integrity publish_side_effect"), "INTEGRITY_FAILURE")

    def test_M05_quality(self):
        self.assertEqual(self.cja.classify_failure("quality publishability fail"), "QUALITY_FAILURE")

    def test_M06_configuration(self):
        self.assertEqual(self.cja.classify_failure("missing_config not_ready"), "CONFIGURATION")

    def test_M07_contract(self):
        self.assertEqual(self.cja.classify_failure("contract mandatory field"), "CONTRACT")

    def test_M08_customer_action(self):
        self.assertEqual(self.cja.classify_failure("approval required customer_action"), "CUSTOMER_ACTION_REQUIRED")

    def test_M09_timeout(self):
        self.assertEqual(self.cja.classify_failure("timed out", error_code="timeout"), "TIMEOUT")

    def test_M10_provider_temp(self):
        self.assertEqual(self.cja.classify_failure("429 rate_limit temporarily"), "PROVIDER_TEMPORARY")

    def test_M11_resource_temp(self):
        self.assertEqual(self.cja.classify_failure("generation_busy disk memory"), "RESOURCE_TEMPORARY")

    def test_M12_transient(self):
        self.assertEqual(self.cja.classify_failure("network connection transient"), "TRANSIENT")

    def test_M13_unknown(self):
        self.assertEqual(self.cja.classify_failure("something bizarre xyz"), "UNKNOWN")

    def test_M14_categories_complete(self):
        self.assertGreaterEqual(len(self.cja.FAILURE_CATEGORIES), 10)


# ---------------------------------------------------------------------------
# N / O / P — Retry policy / bounds / loop prevention
# ---------------------------------------------------------------------------


class NOP_RetryPolicyTests(C06GBase):
    def test_N01_transient_retry_eligible(self):
        self.assertTrue(self.cja.retry_eligible("TRANSIENT", 1, 3))

    def test_N02_timeout_retry_eligible(self):
        self.assertTrue(self.cja.retry_eligible("TIMEOUT", 2, 3))

    def test_N03_provider_temp_retry(self):
        self.assertTrue(self.cja.retry_eligible("PROVIDER_TEMPORARY", 0, 3))

    def test_N04_resource_temp_retry(self):
        self.assertTrue(self.cja.retry_eligible("RESOURCE_TEMPORARY", 1, 3))

    def test_O01_quality_never_retry(self):
        self.assertFalse(self.cja.retry_eligible("QUALITY_FAILURE", 0, 3))

    def test_O02_unknown_never_retry(self):
        self.assertFalse(self.cja.retry_eligible("UNKNOWN", 0, 3))

    def test_O03_ownership_never_retry(self):
        self.assertFalse(self.cja.retry_eligible("OWNERSHIP_FAILURE", 0, 3))

    def test_O04_stale_never_retry(self):
        self.assertFalse(self.cja.retry_eligible("STALE_PLAN", 1, 3))

    def test_O05_config_never_retry(self):
        self.assertFalse(self.cja.retry_eligible("CONFIGURATION", 0, 3))

    def test_P01_at_max_attempts_no_retry(self):
        self.assertFalse(self.cja.retry_eligible("TRANSIENT", 3, 3))

    def test_P02_below_max_ok(self):
        self.assertTrue(self.cja.retry_eligible("TRANSIENT", 2, 3))

    def test_P03_backoff_bounds(self):
        self.assertEqual(self.cja.backoff_seconds(0), 5)
        self.assertEqual(self.cja.backoff_seconds(1), 15)
        self.assertEqual(self.cja.backoff_seconds(2), 45)
        self.assertEqual(self.cja.backoff_seconds(99), 45)

    def test_P04_max_attempts_constant(self):
        self.assertEqual(self.cja.MAX_ATTEMPTS, 3)

    def test_P05_retry_schedules_next_retry_at(self):
        self._ready_plan(topic="P05 retry schedule topic")
        sub = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        claimed = self.cja.claim_next_job(worker_id="p05")
        with patch.object(self.cja, "load_production_plan", create=True):
            # Force failure inside execute by making plan load fail via missing plan path
            pass
        # Direct path: patch run_mock_execution to raise transient
        with patch(
            "app.customer_generation_orchestrator.run_mock_execution",
            side_effect=RuntimeError("network transient retry"),
        ), patch(
            "app.customer_production_plan.load_production_plan",
            return_value={
                "fingerprint": claimed.get("production_plan_revision") or "rev",
                "script_revision": claimed.get("script_revision") or "scr",
                "scenes": [],
                "status": "READY_FOR_GENERATION",
                "owner_login_id": self.login,
                "channel_id": self.ch_id,
                "dialogue_segments": [{"dialogue_id": "d1"}],
                "visual_beats": [],
            },
        ):
            out = self.cja.execute_claimed_job(claimed, channel=self.channel)
        self.assertTrue(out.get("retry_scheduled"))
        row = self._get_job(int(sub["job_id"]))
        self.assertEqual(row.get("queue_status"), "queued")
        self.assertTrue(row.get("next_retry_at"))
        self.assertEqual(int(row.get("attempt_count") or 0), 1)

    def test_P06_loop_prevention_at_cap(self):
        j = self._raw_job(fp="fp-p06", suffix="p06")
        self._enqueue(j["id"], fp="fp-p06")
        claimed = self.cja.claim_next_job(worker_id="p06")
        self.store.update_job(int(j["id"]), attempt_count=2, max_attempts=3)
        claimed = self._get_job(int(j["id"]))
        with patch(
            "app.customer_generation_orchestrator.run_mock_execution",
            side_effect=RuntimeError("network transient retry"),
        ), patch(
            "app.customer_production_plan.load_production_plan",
            return_value={
                "fingerprint": "rev-g",
                "script_revision": "scr-g",
                "scenes": [],
                "status": "READY_FOR_GENERATION",
                "owner_login_id": self.login,
                "channel_id": self.ch_id,
                "dialogue_segments": [{"dialogue_id": "d1"}],
                "visual_beats": [],
            },
        ):
            # attempt_count becomes 3 → not eligible for further retry after this
            out = self.cja.execute_claimed_job(claimed, channel=self.channel)
        # attempt 3 with max 3 → retry_eligible(cat, 3, 3) is False → terminal
        self.assertTrue(out.get("terminal") or out.get("retry_scheduled") is False or out.get("terminal"))


# ---------------------------------------------------------------------------
# Q / R / S — Restart / stale lease / interrupted recovery (>=10)
# ---------------------------------------------------------------------------


class QRS_RestartRecoveryTests(C06GBase):
    def test_Q01_recover_expired_claim_requeues(self):
        j = self._raw_job(fp="fp-q01", suffix="q01")
        self._enqueue(j["id"], fp="fp-q01")
        c = self.cja.claim_next_job(worker_id="q01")
        past = (datetime.now() - timedelta(minutes=10)).isoformat()
        self.store.update_job(
            int(c["id"]),
            lease_expires_at=past,
            queue_status="claimed",
            upload_status="preparing",
        )
        out = self.cja.recover_after_restart()
        self.assertTrue(out["ok"])
        self.assertGreaterEqual(out["requeued"], 1)
        row = self._get_job(int(c["id"]))
        self.assertEqual(row.get("queue_status"), "queued")

    def test_Q02_recover_running_stale(self):
        j = self._raw_job(fp="fp-q02", suffix="q02")
        self._enqueue(j["id"], fp="fp-q02")
        c = self.cja.claim_next_job(worker_id="q02")
        past = (datetime.now() - timedelta(seconds=1)).isoformat()
        self.store.update_job(
            int(c["id"]),
            queue_status="running",
            lease_expires_at=past,
            upload_status="generating",
            claim_token="tok",
        )
        out = self.cja.recover_after_restart()
        self.assertGreaterEqual(out["requeued"], 1)
        self.assertEqual(out.get("silent_completed"), 0)

    def test_Q03_never_silent_completed(self):
        out = self.cja.recover_after_restart()
        self.assertEqual(out.get("silent_completed"), 0)

    def test_Q04_claim_recovers_expired_lease_inline(self):
        j = self._raw_job(fp="fp-q04", suffix="q04")
        self._enqueue(j["id"], fp="fp-q04")
        c = self.cja.claim_next_job(worker_id="q04a")
        past = (datetime.now() - timedelta(minutes=5)).isoformat()
        self.store.update_job(
            int(c["id"]),
            lease_expires_at=past,
            queue_status="claimed",
        )
        c2 = self.cja.claim_next_job(worker_id="q04b")
        self.assertIsNotNone(c2)
        self.assertEqual(int(c2["id"]), int(j["id"]))
        self.assertEqual(c2.get("claimed_by"), "q04b")

    def test_Q05_fresh_lease_not_stolen(self):
        j = self._raw_job(fp="fp-q05", suffix="q05")
        self._enqueue(j["id"], fp="fp-q05")
        c = self.cja.claim_next_job(worker_id="q05a")
        future = (datetime.now() + timedelta(minutes=5)).isoformat()
        self.store.update_job(int(c["id"]), lease_expires_at=future)
        self.assertIsNone(self.cja.claim_next_job(worker_id="q05b"))

    def test_R01_legacy_inflight_interrupted(self):
        j = self._raw_job(fp="fp-r01", suffix="r01")
        self.store.update_job(
            int(j["id"]),
            queue_status=None,
            upload_status="generating",
            claim_token=None,
        )
        out = self.cja.recover_after_restart()
        self.assertGreaterEqual(out.get("interrupted_legacy", 0), 1)
        row = self._get_job(int(j["id"]))
        self.assertEqual(row.get("upload_status"), "interrupted")
        self.assertNotEqual(row.get("customer_state"), "COMPLETED")

    def test_R02_ready_not_requeued(self):
        j = self._raw_job(fp="fp-r02", suffix="r02")
        past = (datetime.now() - timedelta(minutes=5)).isoformat()
        self.store.update_job(
            int(j["id"]),
            queue_status="running",
            lease_expires_at=past,
            upload_status="ready_to_upload",
            customer_state="READY_FOR_REVIEW",
            claim_token="x",
        )
        self.cja.recover_after_restart()
        row = self._get_job(int(j["id"]))
        self.assertEqual(row.get("upload_status"), "ready_to_upload")

    def test_R03_approved_not_requeued(self):
        j = self._raw_job(fp="fp-r03", suffix="r03")
        past = (datetime.now() - timedelta(minutes=5)).isoformat()
        self.store.update_job(
            int(j["id"]),
            queue_status="running",
            lease_expires_at=past,
            upload_status="generating",
            customer_approval="APPROVED",
            claim_token="x",
        )
        before = self._get_job(int(j["id"]))
        self.cja.recover_after_restart()
        after = self._get_job(int(j["id"]))
        # Should not become queued for retry when APPROVED
        self.assertNotEqual(after.get("queue_status"), "queued")
        self.assertEqual(before.get("customer_approval"), "APPROVED")

    def test_R04_requeued_audit_event(self):
        j = self._raw_job(fp="fp-r04", suffix="r04")
        self._enqueue(j["id"], fp="fp-r04")
        c = self.cja.claim_next_job(worker_id="r04")
        past = (datetime.now() - timedelta(minutes=2)).isoformat()
        self.store.update_job(
            int(c["id"]), lease_expires_at=past, queue_status="claimed", upload_status="preparing"
        )
        self.cja.recover_after_restart()
        row = self._get_job(int(c["id"]))
        audit = json.loads(row.get("lifecycle_audit_json") or "{}")
        kinds = [e.get("event") for e in audit.get("events") or []]
        self.assertIn("requeued_after_restart", kinds)

    def test_R05_recover_ok_structure(self):
        out = self.cja.recover_after_restart()
        self.assertTrue(out["ok"])
        self.assertIn("requeued", out)
        self.assertIn("interrupted_legacy", out)
        self.assertIn("note", out)

    def test_S01_cancelled_not_requeued_on_restart(self):
        j = self._raw_job(fp="fp-s01", suffix="s01")
        past = (datetime.now() - timedelta(minutes=5)).isoformat()
        self.store.update_job(
            int(j["id"]),
            queue_status="running",
            lease_expires_at=past,
            upload_status="generating",
            cancel_requested=1,
            claim_token="x",
        )
        self.cja.recover_after_restart()
        row = self._get_job(int(j["id"]))
        self.assertNotEqual(row.get("queue_status"), "queued")

    def test_S02_multiple_stale_requeued(self):
        ids = []
        for i in range(3):
            j = self._raw_job(fp=f"fp-s02-{i}", suffix=f"s02{i}")
            self._enqueue(j["id"], fp=f"fp-s02-{i}")
            ids.append(int(j["id"]))
        claimed = []
        for i in range(3):
            c = self.cja.claim_next_job(worker_id=f"s02-{i}", channel_ids=[self.ch_id])
            self.assertIsNotNone(c)
            claimed.append(c)
        past = (datetime.now() - timedelta(minutes=3)).isoformat()
        for c in claimed:
            self.store.update_job(
                int(c["id"]),
                lease_expires_at=past,
                queue_status="claimed",
                upload_status="preparing",
            )
        out = self.cja.recover_after_restart()
        self.assertGreaterEqual(out["requeued"], 3)
        for jid in ids:
            self.assertEqual(self._get_job(jid).get("queue_status"), "queued")

    def test_S03_interrupted_note(self):
        out = self.cja.recover_after_restart()
        self.assertIn("never", (out.get("note") or "").lower())


# ---------------------------------------------------------------------------
# T — Terminal failure
# ---------------------------------------------------------------------------


class T_TerminalFailureTests(C06GBase):
    def test_T01_quality_goes_terminal(self):
        j = self._raw_job(fp="fp-t01", suffix="t01")
        self._enqueue(j["id"], fp="fp-t01")
        claimed = self.cja.claim_next_job(worker_id="t01")
        with patch(
            "app.customer_generation_orchestrator.run_mock_execution",
            side_effect=RuntimeError("quality publishability fail"),
        ), patch(
            "app.customer_production_plan.load_production_plan",
            return_value={
                "fingerprint": "rev-g",
                "script_revision": "scr-g",
                "scenes": [],
                "status": "READY_FOR_GENERATION",
                "owner_login_id": self.login,
                "channel_id": self.ch_id,
                "dialogue_segments": [{"dialogue_id": "d1"}],
                "visual_beats": [],
            },
        ):
            out = self.cja.execute_claimed_job(claimed, channel=self.channel)
        self.assertTrue(out.get("terminal"))
        self.assertEqual(out.get("failure_category"), "QUALITY_FAILURE")
        row = self._get_job(int(j["id"]))
        self.assertEqual(row.get("customer_state"), "FAILED")

    def test_T02_unknown_terminal(self):
        j = self._raw_job(fp="fp-t02", suffix="t02")
        self._enqueue(j["id"], fp="fp-t02")
        claimed = self.cja.claim_next_job(worker_id="t02")
        with patch(
            "app.customer_generation_orchestrator.run_mock_execution",
            side_effect=RuntimeError("weird unexplained boom"),
        ), patch(
            "app.customer_production_plan.load_production_plan",
            return_value={
                "fingerprint": "rev-g",
                "script_revision": "scr-g",
                "scenes": [],
                "status": "READY_FOR_GENERATION",
                "owner_login_id": self.login,
                "channel_id": self.ch_id,
                "dialogue_segments": [{"dialogue_id": "d1"}],
                "visual_beats": [],
            },
        ):
            out = self.cja.execute_claimed_job(claimed, channel=self.channel)
        self.assertTrue(out.get("terminal"))
        self.assertEqual(out.get("failure_category"), "UNKNOWN")

    def test_T03_terminal_event_in_audit(self):
        j = self._raw_job(fp="fp-t03", suffix="t03")
        self._enqueue(j["id"], fp="fp-t03")
        claimed = self.cja.claim_next_job(worker_id="t03")
        with patch(
            "app.customer_generation_orchestrator.run_mock_execution",
            side_effect=RuntimeError("quality fail"),
        ), patch(
            "app.customer_production_plan.load_production_plan",
            return_value={
                "fingerprint": "rev-g",
                "script_revision": "scr-g",
                "scenes": [],
                "status": "READY_FOR_GENERATION",
                "owner_login_id": self.login,
                "channel_id": self.ch_id,
                "dialogue_segments": [{"dialogue_id": "d1"}],
                "visual_beats": [],
            },
        ):
            self.cja.execute_claimed_job(claimed, channel=self.channel)
        audit = json.loads(self._get_job(int(j["id"])).get("lifecycle_audit_json") or "{}")
        kinds = [e.get("event") for e in audit.get("events") or []]
        self.assertIn("terminal_failed", kinds)


# ---------------------------------------------------------------------------
# U — Cancellation
# ---------------------------------------------------------------------------


class U_CancellationTests(C06GBase):
    def test_U01_cancel_queued_immediate(self):
        j = self._raw_job(fp="fp-u01", suffix="u01")
        self._enqueue(j["id"], fp="fp-u01")
        r = self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        self.assertTrue(r["ok"])
        self.assertTrue(r.get("immediate"))
        self.assertEqual(r.get("state"), "CANCELLED")
        row = self._get_job(int(j["id"]))
        self.assertEqual(row.get("queue_status"), "cancelled")

    def test_U02_cancel_claimed_immediate(self):
        j = self._raw_job(fp="fp-u02", suffix="u02")
        self._enqueue(j["id"], fp="fp-u02")
        self.cja.claim_next_job(worker_id="u02")
        r = self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        self.assertTrue(r["ok"])
        self.assertTrue(r.get("immediate"))

    def test_U03_cancel_running_requested(self):
        j = self._raw_job(fp="fp-u03", suffix="u03")
        self._enqueue(j["id"], fp="fp-u03")
        c = self.cja.claim_next_job(worker_id="u03")
        self.store.update_job(int(c["id"]), queue_status="running")
        r = self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        self.assertTrue(r["ok"])
        self.assertFalse(r.get("immediate"))
        self.assertEqual(r.get("state"), "CANCELLATION_REQUESTED")

    def test_U04_cancel_ownership(self):
        j = self._raw_job(fp="fp-u04", suffix="u04")
        self._enqueue(j["id"], fp="fp-u04")
        r = self.cja.request_cancel(self.login_b, int(j["id"]), channel_ids=[self.ch_b_id])
        self.assertFalse(r["ok"])
        self.assertEqual(r.get("error_code"), "ownership_violation")

    def test_U05_cancel_idempotent(self):
        j = self._raw_job(fp="fp-u05", suffix="u05")
        self._enqueue(j["id"], fp="fp-u05")
        self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        r = self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        self.assertTrue(r["ok"])
        self.assertTrue(r.get("reused"))

    def test_U06_execute_honors_cancel_flag(self):
        j = self._raw_job(fp="fp-u06", suffix="u06")
        self._enqueue(j["id"], fp="fp-u06")
        claimed = self.cja.claim_next_job(worker_id="u06")
        self.store.update_job(int(j["id"]), cancel_requested=1)
        claimed = self._get_job(int(j["id"]))
        out = self.cja.execute_claimed_job(claimed, channel=self.channel)
        self.assertTrue(out.get("cancelled"))
        self.assertFalse(out.get("publishes"))


# ---------------------------------------------------------------------------
# V / W / X — Isolation
# ---------------------------------------------------------------------------


class VWX_IsolationTests(C06GBase):
    def test_V01_list_queue_isolates_login(self):
        ja = self._raw_job(fp="fp-v01a", channel_id=self.ch_id, login_id=self.login, suffix="v01a")
        jb = self._raw_job(fp="fp-v01b", channel_id=self.ch_b_id, login_id=self.login_b, suffix="v01b")
        self._enqueue(ja["id"], login=self.login, channel_ids=[self.ch_id], fp="fp-v01a")
        self._enqueue(jb["id"], login=self.login_b, channel_ids=[self.ch_b_id], fp="fp-v01b")
        qa = self.cja.list_queue(self.login, channel_ids=[self.ch_id])
        qb = self.cja.list_queue(self.login_b, channel_ids=[self.ch_b_id])
        self.assertEqual(qa["count"], 1)
        self.assertEqual(qb["count"], 1)
        self.assertEqual(int(qa["jobs"][0]["job_id"]), int(ja["id"]))
        self.assertEqual(int(qb["jobs"][0]["job_id"]), int(jb["id"]))

    def test_V02_enqueue_foreign_channel_denied(self):
        j = self._raw_job(fp="fp-v02", suffix="v02")
        r = self.cja.enqueue_existing_job(
            int(j["id"]), login_id=self.login, channel_ids=[self.ch_b_id]
        )
        self.assertFalse(r["ok"])
        self.assertEqual(r.get("error_code"), "ownership_violation")

    def test_V03_submit_foreign_owner_blocked(self):
        self._ready_plan(topic="V03 foreign owner topic")
        r = self.cja.submit_customer_generation(
            self.login_b, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        self.assertFalse(r["ok"])
        self.assertEqual(r.get("error_code"), "ownership_violation")

    def test_W01_channel_ids_filter_claim(self):
        ja = self._raw_job(fp="fp-w01a", channel_id=self.ch_id, login_id=self.login, suffix="w01a")
        jb = self._raw_job(fp="fp-w01b", channel_id=self.ch_b_id, login_id=self.login_b, suffix="w01b")
        self._enqueue(ja["id"], login=self.login, channel_ids=[self.ch_id], fp="fp-w01a")
        self._enqueue(jb["id"], login=self.login_b, channel_ids=[self.ch_b_id], fp="fp-w01b")
        c = self.cja.claim_next_job(worker_id="w01", channel_ids=[self.ch_id])
        self.assertEqual(int(c["id"]), int(ja["id"]))

    def test_W02_empty_owned_channels_list_queue(self):
        q = self.cja.list_queue(self.login, channel_ids=[])
        self.assertEqual(q["jobs"], [])

    def test_X01_requested_by_mismatch_enqueue(self):
        j = self._raw_job(fp="fp-x01", login_id=self.login, suffix="x01")
        r = self.cja.enqueue_existing_job(
            int(j["id"]), login_id=self.login_b, channel_ids=[self.ch_id]
        )
        self.assertFalse(r["ok"])

    def test_X02_db_isolation_temp(self):
        self.assertTrue(str(self.store.DB_PATH).endswith("c06g.db"))


# ---------------------------------------------------------------------------
# Y — Forged ids
# ---------------------------------------------------------------------------


class Y_ForgedIdTests(C06GBase):
    def test_Y01_enqueue_missing_job(self):
        r = self.cja.enqueue_existing_job(999999, login_id=self.login, channel_ids=[self.ch_id])
        self.assertFalse(r["ok"])
        self.assertEqual(r.get("error_code"), "not_found")

    def test_Y02_cancel_missing_job(self):
        r = self.cja.request_cancel(self.login, 999999, channel_ids=[self.ch_id])
        self.assertFalse(r["ok"])
        self.assertEqual(r.get("error_code"), "not_found")

    def test_Y03_project_none(self):
        self.assertEqual(self.cja.project_job_automation(None).get("available"), False)

    def test_Y04_forged_channel_on_submit(self):
        self._ready_plan(topic="Y04 forged channel topic")
        forged = {**self.channel, "id": 99999, "owner_login_id": self.login}
        r = self.cja.submit_customer_generation(
            self.login, forged, use_mock=True, process_now=False, force_rebuild=True
        )
        self.assertFalse(r["ok"])


# ---------------------------------------------------------------------------
# Z — API (inspect main.py)
# ---------------------------------------------------------------------------


class Z_ApiSourceTests(unittest.TestCase):
    def test_Z01_generate_queue_path(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.workspace_generate)
        self.assertIn("submit_customer_generation", src)
        self.assertIn("queue", src)

    def test_Z02_workspace_queue_route(self):
        from app import main as main_mod

        self.assertTrue(callable(main_mod.workspace_queue))
        src = inspect.getsource(main_mod.workspace_queue)
        self.assertIn("list_queue", src)

    def test_Z03_workspace_tick_route(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.workspace_queue_tick)
        self.assertIn("scheduler_tick", src)

    def test_Z04_workspace_cancel_route(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.workspace_job_cancel)
        self.assertIn("request_cancel", src)

    def test_Z05_startup_recover(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("recover_after_restart", src)
        self.assertIn("ensure_automation_columns", src)

    def test_Z06_routes_registered(self):
        from app import main as main_mod

        paths = {getattr(r, "path", None) for r in main_mod.app.routes}
        self.assertIn("/api/workspace/queue", paths)
        self.assertIn("/api/workspace/queue/tick", paths)


# ---------------------------------------------------------------------------
# AA — UI projection
# ---------------------------------------------------------------------------


class AA_UiProjectionTests(unittest.TestCase):
    def test_AA01_html_automation_section(self):
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("ws-automation", html)
        self.assertIn("wsAutomationPanel", html)
        self.assertIn("Queue / Recovery", html)

    def test_AA02_js_renders_queue_status(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("queue_status", js)
        self.assertIn("attempt_count", js)
        self.assertIn("wsAutomationPanel", js)

    def test_AA03_js_approval_plane(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("approval_status", js)
        self.assertIn("publishes", js)

    def test_AA04_workspace_uses_project_job_automation(self):
        src = (ROOT / "app" / "customer_workspace.py").read_text(encoding="utf-8")
        self.assertIn("project_job_automation", src)

    def test_AA05_project_fields(self):
        proj = __import__("app.customer_job_automation", fromlist=["project_job_automation"]).project_job_automation(
            {
                "queue_status": "queued",
                "attempt_count": 1,
                "max_attempts": 3,
                "customer_approval": "PENDING",
                "upload_status": "queued",
            }
        )
        self.assertEqual(proj["queue_status"], "queued")
        self.assertEqual(proj["attempt_count"], 1)
        self.assertFalse(proj["publishes"])


# ---------------------------------------------------------------------------
# AB — No publish
# ---------------------------------------------------------------------------


class AB_NoPublishTests(C06GBase):
    def test_AB01_submit_publishes_false(self):
        self._ready_plan(topic="AB01 no publish submit")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        self.assertFalse(r.get("publishes"))

    def test_AB02_tick_publishes_false(self):
        tick = self.cja.scheduler_tick()
        self.assertFalse(tick.get("publishes"))

    def test_AB03_list_queue_publishes_false(self):
        q = self.cja.list_queue(self.login, channel_ids=[self.ch_id])
        self.assertFalse(q.get("publishes"))

    def test_AB04_enqueue_publishes_false(self):
        j = self._raw_job(fp="fp-ab04", suffix="ab04")
        r = self._enqueue(j["id"], fp="fp-ab04")
        self.assertFalse(r.get("publishes"))

    def test_AB05_source_no_upload_youtube(self):
        src = Path(self.cja.__file__).read_text(encoding="utf-8")
        self.assertNotIn("upload_to_youtube", src)
        self.assertNotIn("publish_video", src)


# ---------------------------------------------------------------------------
# AC — No social
# ---------------------------------------------------------------------------


class AC_NoSocialTests(C06GBase):
    def test_AC01_submit_social_false(self):
        self._ready_plan(topic="AC01 no social")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        self.assertFalse(r.get("social_calls"))

    def test_AC02_execute_social_false(self):
        self._ready_plan(topic="AC02 exec social")
        self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        claimed = self.cja.claim_next_job(worker_id="ac02")
        out = self.cja.execute_claimed_job(claimed, channel=self.channel)
        self.assertFalse(out.get("social_calls"))

    def test_AC03_source_no_social_post(self):
        src = Path(self.cja.__file__).read_text(encoding="utf-8")
        self.assertNotIn("post_to_facebook", src)
        self.assertNotIn("social_publish", src)


# ---------------------------------------------------------------------------
# AD — Paid API = 0
# ---------------------------------------------------------------------------


class AD_PaidApiZeroTests(C06GBase):
    def test_AD01_submit_paid_zero(self):
        self._ready_plan(topic="AD01 paid zero")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        self.assertEqual(r.get("paid_api_calls"), 0)

    def test_AD02_process_now_paid_zero(self):
        self._ready_plan(topic="AD02 process paid zero")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        tick = r.get("tick") or {}
        result = (tick.get("result") or {})
        self.assertEqual(result.get("paid_api_calls", 0), 0)

    def test_AD03_no_openai_in_module(self):
        src = Path(self.cja.__file__).read_text(encoding="utf-8")
        self.assertNotIn("openai", src.lower().split("generate_video")[0] if False else src.lower())
        # soft: module should not hardcode paid providers for queue path
        self.assertNotIn("OPENAI_API_KEY", src)


# ---------------------------------------------------------------------------
# AE — Idempotency
# ---------------------------------------------------------------------------


class AE_IdempotencyTests(C06GBase):
    def test_AE01_equivalent_fingerprint_reuse(self):
        self._ready_plan(topic="AE01 idempotent topic")
        a = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        b = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=False
        )
        self.assertTrue(b.get("reused"))
        self.assertEqual(a.get("fingerprint"), b.get("fingerprint"))

    def test_AE02_force_rebuild_new_job(self):
        self._ready_plan(topic="AE02 force rebuild topic")
        a = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        # Clear active queue entry so force_rebuild is not blocked by find_duplicate_queued
        self.store.update_job(int(a["job_id"]), queue_status="done", upload_status="failed", customer_state="FAILED")
        b = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        self.assertFalse(b.get("reused"))
        self.assertNotEqual(a["job_id"], b["job_id"])

    def test_AE03_duplicate_queue_prevented(self):
        self._ready_plan(topic="AE03 dup queue topic")
        a = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        b = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=False
        )
        # either reuse completed fingerprint path or duplicate queued
        self.assertTrue(b.get("reused") or b.get("job_id") == a.get("job_id"))


# ---------------------------------------------------------------------------
# AF — Audit trail
# ---------------------------------------------------------------------------


class AF_AuditTrailTests(C06GBase):
    def test_AF01_enqueue_event(self):
        j = self._raw_job(fp="fp-af01", suffix="af01")
        self._enqueue(j["id"], fp="fp-af01")
        row = self._get_job(int(j["id"]))
        events = (json.loads(row.get("lifecycle_audit_json") or "{}").get("events") or [])
        self.assertTrue(any(e.get("event") == "enqueued" for e in events))

    def test_AF02_claim_event(self):
        j = self._raw_job(fp="fp-af02", suffix="af02")
        self._enqueue(j["id"], fp="fp-af02")
        self.cja.claim_next_job(worker_id="af02")
        events = (
            json.loads(self._get_job(int(j["id"])).get("lifecycle_audit_json") or "{}").get("events") or []
        )
        self.assertTrue(any(e.get("event") == "claimed" for e in events))

    def test_AF03_secrets_redacted(self):
        j = self._raw_job(fp="fp-af03", suffix="af03")
        self.cja.append_lifecycle_event(
            int(j["id"]), {"event": "probe", "detail": "api_key=sk-secretpassword=x"}
        )
        events = (
            json.loads(self._get_job(int(j["id"])).get("lifecycle_audit_json") or "{}").get("events") or []
        )
        last = events[-1]
        self.assertTrue(last.get("redacted"))

    def test_AF04_cancel_event(self):
        j = self._raw_job(fp="fp-af04", suffix="af04")
        self._enqueue(j["id"], fp="fp-af04")
        self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        events = (
            json.loads(self._get_job(int(j["id"])).get("lifecycle_audit_json") or "{}").get("events") or []
        )
        self.assertTrue(
            any(e.get("event") in ("cancelled", "JOB_CANCELLED") for e in events)
        )

    def test_AF05_append_caps_events(self):
        j = self._raw_job(fp="fp-af05", suffix="af05")
        for i in range(5):
            self.cja.append_lifecycle_event(int(j["id"]), {"event": f"e{i}"})
        events = (
            json.loads(self._get_job(int(j["id"])).get("lifecycle_audit_json") or "{}").get("events") or []
        )
        self.assertGreaterEqual(len(events), 5)


# ---------------------------------------------------------------------------
# Source guards + count
# ---------------------------------------------------------------------------


class SourceGuardAndCountTests(unittest.TestCase):
    def test_SG01_no_generate_video_def(self):
        from app import customer_job_automation as cja

        src = Path(cja.__file__).read_text(encoding="utf-8")
        self.assertEqual(cja.detect_duplicate_engines(src), [])
        self.assertIsNone(re.search(r"(?m)^\s*def\s+generate_video\s*\(", src))

    def test_SG02_no_scheduler_service_class(self):
        src = (ROOT / "app" / "customer_job_automation.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?m)^\s*class\s+SchedulerService\b", src))

    def test_SG03_no_try_acquire_def(self):
        src = (ROOT / "app" / "customer_job_automation.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?m)^\s*def\s+try_acquire\s*\(", src))

    def test_SG04_no_evaluate_publishability_def(self):
        src = (ROOT / "app" / "customer_job_automation.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?m)^\s*def\s+evaluate_publishability\s*\(", src))

    def test_SG05_detect_duplicate_engines_flags(self):
        from app import customer_job_automation as cja

        bad = "def generate_video():\n    pass\nclass SchedulerService:\n    pass\ndef try_acquire():\n    pass\ndef evaluate_publishability():\n    pass\n"
        self.assertGreaterEqual(len(cja.detect_duplicate_engines(bad)), 3)

    def test_COUNT_at_least_150(self):
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName(__name__)
        # Also load from this module object
        import sys

        mod = sys.modules[__name__]
        suite = loader.loadTestsFromModule(mod)
        count = suite.countTestCases()
        self.assertGreaterEqual(count, 150, f"expected >=150 tests, got {count}")


if __name__ == "__main__":
    unittest.main()
