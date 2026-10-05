#!/usr/bin/env python3
"""AMP-002 RV-012 — Reserve Queue + Topic Lifecycle re-verification."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.intelligence.bridge import pick_topic_from_reserve
from pipeline.intelligence.contracts import (
    ChannelProfile,
    ContentFormat,
    DEFAULT_RESERVE_MIN,
    TopicLifecycleStatus,
)
from pipeline.intelligence.duplicate import analyze_duplicate
from pipeline.intelligence.orchestrator import (
    refresh_topic_intelligence,
    run_topic_intelligence,
    select_topic_for_production,
)
from pipeline.intelligence.reserve_queue import (
    RESERVE_SCHEMA_VERSION,
    consume_top,
    load_reserve,
    merge_reserve_entries,
    normalize_reserve_entry,
    persistent_reserve_path,
    repair_reserve,
    reserve_path,
    reserve_refresh_fingerprint,
    reserve_topic_key,
    save_reserve,
    update_reserve,
    validate_reserve_integrity,
)


def _profile(cid: int = 4000, language: str = "en", niche: str = "tech") -> ChannelProfile:
    return ChannelProfile(channel_id=cid, niche=niche, language=language)


def _ranked(title: str, score: float, *, fmt: str = "LONG", cid: int = 4000, eligible: bool = True) -> dict:
    tid = f"tid-{reserve_topic_key({'title': title})}"
    return {
        "candidate": {
            "title": title,
            "canonical_topic": title,
            "topic_id": tid,
            "format": fmt,
            "channel_id": cid,
            "source": "pipeline",
        },
        "score": {"total_score": score, "hard_blocked": False},
        "eligible": eligible,
    }


class RV012SchemaTests(unittest.TestCase):
    def test_01_reserve_schema(self):
        entry = normalize_reserve_entry(
            {"title": "RV012 schema topic", "topic_id": "rv012-1", "canonical_topic": "RV012 schema topic"},
            score={"total_score": 0.9},
            channel_id=4001,
            language="en",
            fmt=ContentFormat.LONG,
        )
        self.assertEqual(entry.get("topic_id"), "rv012-1")
        self.assertEqual(entry.get("channel_id"), 4001)
        self.assertEqual(entry.get("format"), "LONG")
        self.assertEqual(entry.get("language"), "en")
        self.assertAlmostEqual(float(entry.get("score") or 0), 0.9)
        self.assertEqual(entry.get("status"), TopicLifecycleStatus.RESERVED.value)
        self.assertIsNotNone(entry.get("reserved_at"))
        self.assertIsNotNone(entry.get("refreshed_at"))
        self.assertEqual(entry.get("reserve_schema_version"), RESERVE_SCHEMA_VERSION)
        self.assertIsNotNone(entry.get("fingerprint"))


class RV012IsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_02_channel_isolation(self):
        for cid, title in ((4010, "Channel A topic"), (4020, "Channel B topic"), (4030, "Channel C topic")):
            update_reserve(
                self.tmp,
                ContentFormat.LONG,
                [_ranked(title, 0.9, cid=cid)],
                channel_id=cid,
                min_size=1,
            )
        a = load_reserve(self.tmp, ContentFormat.LONG, channel_id=4010)
        b = load_reserve(self.tmp, ContentFormat.LONG, channel_id=4020)
        c = load_reserve(self.tmp, ContentFormat.LONG, channel_id=4030)
        self.assertEqual([e["title"] for e in a], ["Channel A topic"])
        self.assertEqual([e["title"] for e in b], ["Channel B topic"])
        self.assertEqual([e["title"] for e in c], ["Channel C topic"])
        self.assertNotEqual(
            reserve_path(self.tmp, ContentFormat.LONG, channel_id=4010),
            reserve_path(self.tmp, ContentFormat.LONG, channel_id=4020),
        )

    def test_03_long_short_isolation(self):
        cid = 4040
        update_reserve(self.tmp, ContentFormat.LONG, [_ranked("RV012 long only", 0.91, cid=cid)], channel_id=cid, min_size=1)
        update_reserve(self.tmp, ContentFormat.SHORT, [_ranked("RV012 short only", 0.88, cid=cid, fmt="SHORT")], channel_id=cid, min_size=1)
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("RV012 long refresh", 0.95, cid=cid)],
            channel_id=cid,
            min_size=1,
        )
        long_entries = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)
        short_entries = load_reserve(self.tmp, ContentFormat.SHORT, channel_id=cid)
        long_titles = {e["title"] for e in long_entries}
        short_titles = {e["title"] for e in short_entries}
        self.assertIn("RV012 long refresh", long_titles)
        self.assertIn("RV012 short only", short_titles)
        self.assertNotIn("RV012 short only", long_titles)
        self.assertNotIn("RV012 long refresh", short_titles)

    def test_04_language_isolation(self):
        cid = 4050
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("English reserve topic", 0.9, cid=cid)],
            channel_id=cid,
            language="en",
            min_size=1,
        )
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("Bengali reserve topic", 0.9, cid=cid)],
            channel_id=cid,
            language="bn",
            min_size=1,
        )
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("Hindi reserve topic", 0.9, cid=cid)],
            channel_id=cid,
            language="hi",
            min_size=1,
        )
        en = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid, language="en")
        bn = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid, language="bn")
        hi = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid, language="hi")
        self.assertEqual([e["title"] for e in en], ["English reserve topic"])
        self.assertEqual([e["title"] for e in bn], ["Bengali reserve topic"])
        self.assertEqual([e["title"] for e in hi], ["Hindi reserve topic"])
        self.assertNotEqual(
            persistent_reserve_path(cid, ContentFormat.LONG, language="en"),
            persistent_reserve_path(cid, ContentFormat.LONG, language="bn"),
        )


class RV012MinimumReserveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cid = 4060

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed_count(self, count: int) -> None:
        entries = [
            {
                "title": f"Seed topic {i}",
                "canonical_topic": f"seed-topic-{i}",
                "topic_id": f"seed-{i}",
                "status": TopicLifecycleStatus.RESERVED.value,
                "score": 0.7,
                "rank": i + 1,
            }
            for i in range(count)
        ]
        save_reserve(self.tmp, ContentFormat.LONG, entries, channel_id=self.cid)

    def test_05_minimum_reserve(self):
        for count, expect_needs in ((0, True), (1, True), (4, True), (5, False), (6, False)):
            self._seed_count(count)
            rep = update_reserve(self.tmp, ContentFormat.LONG, [], channel_id=self.cid, min_size=DEFAULT_RESERVE_MIN)
            loaded = load_reserve(self.tmp, ContentFormat.LONG, channel_id=self.cid)
            self.assertEqual(len(loaded), count)
            self.assertEqual(rep["needs_discovery"], expect_needs, f"count={count}")


class RV012RankingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_06_ranking_order(self):
        ranked = [
            _ranked("Topic C", 0.65),
            _ranked("Topic A", 0.95),
            _ranked("Topic B", 0.80),
        ]
        update_reserve(self.tmp, ContentFormat.LONG, ranked, channel_id=4070, min_size=1)
        titles = [e["title"] for e in load_reserve(self.tmp, ContentFormat.LONG, channel_id=4070)]
        self.assertEqual(titles, ["Topic A", "Topic B", "Topic C"])

    def test_07_deterministic_tie_break(self):
        ranked = [
            _ranked("Topic Z tie", 0.80),
            _ranked("Topic A tie", 0.80),
        ]
        update_reserve(self.tmp, ContentFormat.LONG, ranked, channel_id=4071, min_size=1)
        first = [e["title"] for e in load_reserve(self.tmp, ContentFormat.LONG, channel_id=4071)]
        update_reserve(self.tmp, ContentFormat.LONG, ranked, channel_id=4071, min_size=1)
        second = [e["title"] for e in load_reserve(self.tmp, ContentFormat.LONG, channel_id=4071)]
        self.assertEqual(first, second)
        self.assertEqual(first[0], "Topic A tie")


class RV012RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_08_daily_refresh_reorder(self):
        cid = 4080
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("Topic A", 0.90, cid=cid), _ranked("Topic B", 0.80, cid=cid), _ranked("Topic C", 0.70, cid=cid)],
            channel_id=cid,
            min_size=1,
        )
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("Topic A", 0.90, cid=cid), _ranked("Topic B", 0.92, cid=cid), _ranked("Topic C", 0.70, cid=cid)],
            channel_id=cid,
            min_size=1,
        )
        titles = [e["title"] for e in load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)]
        self.assertEqual(titles[0], "Topic B")

    def test_09_repeated_refresh_stable(self):
        cid = 4081
        ranked = [_ranked("Stable A", 0.9, cid=cid), _ranked("Stable B", 0.8, cid=cid)]
        update_reserve(self.tmp, ContentFormat.LONG, ranked, channel_id=cid, min_size=1)
        after_first = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)
        update_reserve(self.tmp, ContentFormat.LONG, ranked, channel_id=cid, min_size=1)
        after_second = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)
        self.assertEqual(len(after_first), len(after_second))
        self.assertEqual(
            [reserve_topic_key(e) for e in after_first],
            [reserve_topic_key(e) for e in after_second],
        )


class RV012LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cid = 4090
        self.profile = _profile(self.cid)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_10_consume_lifecycle(self):
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("Consume top topic", 0.95, cid=0), _ranked("Second topic", 0.8, cid=0)],
            channel_id=0,
            min_size=1,
        )
        top, remaining = consume_top(self.tmp, ContentFormat.LONG, channel_id=0)
        self.assertEqual(top["title"], "Consume top topic")
        titles = [e["title"] for e in remaining]
        self.assertNotIn("Consume top topic", titles)
        self.assertEqual(titles, ["Second topic"])
        self.assertEqual(remaining[0]["rank"], 1)

    def test_11_failed_job_undefined_policy(self):
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("Failed job topic", 0.9, cid=0)],
            channel_id=0,
            min_size=1,
        )
        top, _ = consume_top(self.tmp, ContentFormat.LONG, channel_id=0)
        self.assertEqual(top["title"], "Failed job topic")
        remaining = load_reserve(self.tmp, ContentFormat.LONG, channel_id=0)
        self.assertEqual(len(remaining), 0)

    def test_12_successful_publication_blocks_rediscovery(self):
        published = "RV012 published lifecycle topic"
        profile = _profile(0)
        dup = analyze_duplicate(published, [published])
        self.assertEqual(dup.verdict.value, "DUPLICATE")
        result = run_topic_intelligence(
            self.tmp,
            profile,
            [{"title": published, "canonical_topic": published, "format": "LONG", "channel_id": 0, "source": "pipeline"}],
            historical_topics=[published],
            do_research=False,
        )
        reserve = load_reserve(self.tmp, ContentFormat.LONG, channel_id=0)
        titles = [e.get("title") for e in reserve]
        self.assertNotIn(published, titles)
        evaluated = result.get("evaluated") or []
        self.assertEqual(len(evaluated), 0)


class RV012MergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cid = 4100

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_13_refresh_merge(self):
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("Topic A", 0.9, cid=self.cid), _ranked("Topic B", 0.8, cid=self.cid), _ranked("Topic C", 0.7, cid=self.cid)],
            channel_id=self.cid,
            min_size=1,
        )
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [
                _ranked("Topic B", 0.81, cid=self.cid),
                _ranked("Topic C", 0.71, cid=self.cid),
                _ranked("Topic D", 0.65, cid=self.cid),
                _ranked("Topic E", 0.60, cid=self.cid),
            ],
            channel_id=self.cid,
            min_size=1,
        )
        entries = load_reserve(self.tmp, ContentFormat.LONG, channel_id=self.cid)
        keys = [reserve_topic_key(e) for e in entries]
        self.assertEqual(len(keys), len(set(keys)))
        titles = [e["title"] for e in entries]
        self.assertIn("Topic A", titles)
        self.assertIn("Topic D", titles)
        self.assertIn("Topic E", titles)

    def test_14_priority_update(self):
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("Topic A", 0.90, cid=self.cid), _ranked("Topic B", 0.80, cid=self.cid), _ranked("Topic C", 0.70, cid=self.cid)],
            channel_id=self.cid,
            min_size=1,
        )
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("Topic C", 0.95, cid=self.cid), _ranked("Topic A", 0.90, cid=self.cid), _ranked("Topic B", 0.80, cid=self.cid)],
            channel_id=self.cid,
            min_size=1,
        )
        titles = [e["title"] for e in load_reserve(self.tmp, ContentFormat.LONG, channel_id=self.cid)]
        self.assertEqual(titles[:3], ["Topic C", "Topic A", "Topic B"])


class RV012ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_15_concurrent_enqueue(self):
        cid = 4110
        errors: list[str] = []
        lock = threading.Lock()

        def worker(i: int):
            try:
                update_reserve(
                    self.tmp,
                    ContentFormat.LONG,
                    [_ranked(f"Concurrent topic {i % 5}", 0.5 + (i % 5) * 0.05, cid=cid)],
                    channel_id=cid,
                    min_size=1,
                )
            except Exception as exc:
                with lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertEqual(errors, [])
        entries = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)
        keys = [reserve_topic_key(e) for e in entries]
        self.assertEqual(len(keys), len(set(keys)))

    def test_16_concurrent_consume(self):
        cid = 4111
        entries = [
            {
                "title": f"Consume {i}",
                "canonical_topic": f"consume-{i}",
                "status": TopicLifecycleStatus.RESERVED.value,
                "rank": i + 1,
                "score": 0.8,
            }
            for i in range(15)
        ]
        save_reserve(self.tmp, ContentFormat.LONG, entries, channel_id=cid)
        consumed: list[str] = []
        lock = threading.Lock()

        def worker():
            top, _ = consume_top(self.tmp, ContentFormat.LONG, channel_id=cid)
            if top:
                with lock:
                    consumed.append(reserve_topic_key(top))

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertEqual(len(consumed), len(set(consumed)))
        remaining = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)
        self.assertEqual(len(remaining) + len(consumed), 15)

    def test_17_concurrent_refresh(self):
        cid = 4112
        base = [_ranked("Refresh Alpha", 0.9, cid=cid), _ranked("Refresh Beta", 0.8, cid=cid)]
        update_reserve(self.tmp, ContentFormat.LONG, base, channel_id=cid, min_size=1)
        errors: list[str] = []
        lock = threading.Lock()

        def worker(i: int):
            try:
                update_reserve(
                    self.tmp,
                    ContentFormat.LONG,
                    base + [_ranked(f"Refresh New {i % 3}", 0.6, cid=cid)],
                    channel_id=cid,
                    min_size=1,
                )
            except Exception as exc:
                with lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertEqual(errors, [])
        entries = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)
        keys = [reserve_topic_key(e) for e in entries]
        self.assertEqual(len(keys), len(set(keys)))


class RV012PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_18_crash_recovery_corrupt_quarantine(self):
        cid = 4120
        p = reserve_path(self.tmp, ContentFormat.LONG, channel_id=cid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{not valid json", encoding="utf-8")
        loaded = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)
        self.assertEqual(loaded, [])
        corrupt = list(p.parent.glob("*.corrupt"))
        self.assertTrue(corrupt)

    def test_19_persistence_reload(self):
        cid = 4121
        update_reserve(
            self.tmp,
            ContentFormat.LONG,
            [_ranked("Persist A", 0.9, cid=cid), _ranked("Persist B", 0.8, cid=cid)],
            channel_id=cid,
            min_size=1,
        )
        first = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)
        second = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)
        self.assertEqual([e["title"] for e in first], [e["title"] for e in second])
        self.assertEqual([e["rank"] for e in first], [e["rank"] for e in second])


class RV012CorruptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cid = 4130

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_20_corrupted_queue_repair(self):
        bad = [
            {"title": "Good topic", "canonical_topic": "good", "status": TopicLifecycleStatus.RESERVED.value, "score": 0.8, "rank": 1},
            {"title": "Good topic", "canonical_topic": "good", "status": TopicLifecycleStatus.RESERVED.value, "score": 0.7, "rank": 2},
            {"title": "", "status": TopicLifecycleStatus.RESERVED.value, "score": "bad", "rank": 3},
        ]
        save_reserve(self.tmp, ContentFormat.LONG, bad, channel_id=self.cid)
        rep = repair_reserve(self.tmp, ContentFormat.LONG, channel_id=self.cid)
        self.assertTrue(rep["repaired"])
        fixed = load_reserve(self.tmp, ContentFormat.LONG, channel_id=self.cid)
        ok, issues = validate_reserve_integrity(fixed)
        self.assertTrue(ok, issues)
        self.assertEqual(len(fixed), 1)

    def test_21_schema_mismatch_empty_file(self):
        p = reserve_path(self.tmp, ContentFormat.LONG, channel_id=self.cid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
        loaded = load_reserve(self.tmp, ContentFormat.LONG, channel_id=self.cid)
        self.assertEqual(loaded, [])


class RV012IdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_22_idempotent_refresh(self):
        cid = 4140
        ranked = [_ranked("Idem A", 0.9, cid=cid), _ranked("Idem B", 0.8, cid=cid)]
        fp1 = reserve_refresh_fingerprint(ranked, channel_id=cid, fmt=ContentFormat.LONG, language="en")
        fp2 = reserve_refresh_fingerprint(ranked, channel_id=cid, fmt=ContentFormat.LONG, language="en")
        self.assertEqual(fp1, fp2)
        update_reserve(self.tmp, ContentFormat.LONG, ranked, channel_id=cid, min_size=1)
        first = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)
        update_reserve(self.tmp, ContentFormat.LONG, ranked, channel_id=cid, min_size=1)
        second = load_reserve(self.tmp, ContentFormat.LONG, channel_id=cid)
        self.assertEqual(len(first), len(second))
        self.assertEqual([reserve_topic_key(e) for e in first], [reserve_topic_key(e) for e in second])

    def test_23_duplicate_prevention(self):
        cid = 4141
        merged = merge_reserve_entries(
            [{"title": "Dup", "canonical_topic": "dup", "score": 0.7, "status": TopicLifecycleStatus.RESERVED.value}],
            [{"title": "Dup", "canonical_topic": "dup", "score": 0.9, "status": TopicLifecycleStatus.RESERVED.value}],
            max_entries=10,
        )
        self.assertEqual(len(merged), 1)
        self.assertAlmostEqual(float(merged[0]["score"]), 0.9)


class RV012IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cid = 4150
        self.profile = _profile(self.cid)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_24_production_integration(self):
        cid = 4150
        update_reserve(
            None,
            ContentFormat.LONG,
            [_ranked("Bridge integration topic", 0.93, cid=cid)],
            channel_id=cid,
            min_size=1,
        )
        try:
            topic = pick_topic_from_reserve(self.tmp, {"id": cid, "niche": "tech"}, video_type="long")
            self.assertEqual(topic, "Bridge integration topic")
            self.assertEqual(load_reserve(None, ContentFormat.LONG, channel_id=cid), [])
        finally:
            save_reserve(None, ContentFormat.LONG, [], channel_id=cid)

    def test_25_bypass_audit_production_path(self):
        import pipeline.intelligence.orchestrator as orch
        import pipeline.intelligence.bridge as bridge_mod

        self.assertIn("update_reserve", orch.__dict__)
        self.assertIn("consume_top", orch.__dict__)
        self.assertIn("select_topic_for_production", bridge_mod.__dict__)
        # Direct save_reserve only used in tests — orchestrator uses update_reserve.
        src = Path(orch.__file__).read_text(encoding="utf-8")
        self.assertIn("update_reserve(", src)
        self.assertNotIn("save_reserve(", src)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-002 RV-012 TESTS: {passed} / {result.testsRun}")
    if not result.wasSuccessful():
        raise SystemExit(1)
