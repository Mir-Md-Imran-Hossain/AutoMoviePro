#!/usr/bin/env python3
"""AMP-002 RV-007 — Research → Evidence → FactPack → Ranking re-verification."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.intelligence.contracts import ContentFormat, ResearchRequest
from pipeline.intelligence.factpack_gate import validate_fact_pack
from pipeline.intelligence.fingerprint import compute_research_fingerprint
from pipeline.intelligence.orchestrator import _research_candidate, run_topic_intelligence
from pipeline.intelligence.ranking import rank_candidates
from pipeline.intelligence.research_runtime import execute_research_request, reset_cost_ledger
from pipeline.intelligence.scoring import channel_profile_from_row
from pipeline.intelligence.candidates import candidate_from_dict


def _profile(cid: int = 80707):
    from pipeline.intelligence.contracts import ChannelProfile
    return ChannelProfile(channel_id=cid, niche="tech", language="en")


def _cand(title: str, cid: int = 80707, fmt: str = "LONG"):
    return {"title": title, "canonical_topic": title, "format": fmt, "channel_id": cid}


class RV007OrderAndFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_08_research_before_ranking_order(self):
        order: list[str] = []
        import pipeline.intelligence.orchestrator as orch

        orig_research = orch._research_candidate
        orig_rank = orch.rank_candidates

        def _wrap_research(*a, **k):
            order.append("research")
            return orig_research(*a, **k)

        def _wrap_rank(*a, **k):
            order.append("rank")
            return orig_rank(*a, **k)

        with patch.object(orch, "_research_candidate", side_effect=_wrap_research), patch.object(
            orch, "rank_candidates", side_effect=_wrap_rank
        ):
            run_topic_intelligence(
                self.tmp,
                _profile(),
                [_cand("Order test topic A"), _cand("Order test topic B")],
                use_mock_research=True,
            )
        self.assertGreater(order.count("research"), 0)
        self.assertEqual(order[-1], "rank")
        self.assertLess(order.index("research"), order.index("rank"))

    def test_positive_integration_chain(self):
        profile = _profile(80771)
        result = run_topic_intelligence(
            self.tmp,
            profile,
            [_cand("Integration chain topic alpha", 80771)],
            use_mock_research=True,
        )
        tid = result["evaluated"][0]["candidate"]["topic_id"]
        trace = {
            "research": tid in result["research"],
            "gate_pass": result["research"][tid]["gate"]["verdict"] == "PASS",
            "scored": not result["evaluated"][0]["score"].get("hard_blocked"),
            "ranked": len(result["ranked_long"]) >= 1,
            "reserve": result["long_reserve"]["count"] >= 1,
        }
        self.assertTrue(all(trace.values()), trace)
        artifact = self.tmp / "intelligence" / "topic_intelligence_result.json"
        self.assertTrue(artifact.is_file())
        body = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertIn("research", body)
        self.assertIn("ranked_long", body)
        fp = result["research"][tid].get("fingerprint")
        self.assertTrue(fp)


class RV007NegativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_research_missing_blocks_ranking_eligibility(self):
        profile = _profile()
        with patch("pipeline.intelligence.orchestrator.execute_research_request") as mock_rr:
            from pipeline.intelligence.research_runtime import ResearchResult
            from pipeline.idempotency.states import IdempotencyState

            mock_rr.return_value = ResearchResult(
                success=False,
                action="failed",
                fingerprint="fp-fail",
                research={"status": "PROVIDER_UNAVAILABLE"},
                fact_pack=None,
                state=IdempotencyState.FAILED_FINAL,
                provider_mode="MOCK",
            )
            result = run_topic_intelligence(
                self.tmp, profile, [_cand("No research topic")], use_mock_research=True
            )
        ranked = result["ranked_long"]
        self.assertTrue(all(not r.get("eligible") for r in ranked))

    def test_02_evidence_missing_blocks(self):
        profile = _profile()
        with patch("pipeline.intelligence.orchestrator.execute_research_request") as mock_exec:
            mock_exec.return_value = type("RR", (), {
                "success": False,
                "fact_pack": {"claims": []},
                "research": {},
                "fingerprint": "abc",
                "action": "failed",
                "provider_mode": "MOCK",
            })()
            result = run_topic_intelligence(
                self.tmp, profile, [_cand("Empty evidence topic")], use_mock_research=True
            )
        self.assertTrue(result["evaluated"][0]["score"]["hard_blocked"])
        self.assertTrue(all(not r.get("eligible") for r in result["ranked_long"]))

    def test_03_invalid_factpack_blocks(self):
        gate = validate_fact_pack({"claims": [{"claim": "x", "evidence": "UNVERIFIED", "source": ""}]})
        self.assertEqual(gate["verdict"], "RESEARCH_REQUIRED")
        profile = _profile()
        with patch("pipeline.intelligence.orchestrator.execute_research_request") as mock_exec:
            mock_exec.return_value = type("RR", (), {
                "success": True,
                "fact_pack": {"claims": [{"claim": "x", "evidence": "UNVERIFIED", "source": ""}]},
                "research": {"query": "bad"},
                "fingerprint": "bad",
                "action": "execute",
                "provider_mode": "MOCK",
            })()
            result = run_topic_intelligence(self.tmp, profile, [_cand("Bad factpack")], use_mock_research=True)
        self.assertTrue(result["evaluated"][0]["score"]["hard_blocked"])

    def test_04_conflicting_evidence(self):
        gate = validate_fact_pack({"claims": [
            {"claim": "Price increased 50%", "evidence": "secondary", "source": "a"},
            {"claim": "Price decreased 50%", "evidence": "secondary", "source": "b"},
        ]})
        self.assertEqual(gate["verdict"], "RESEARCH_CONFLICT")

    def test_05_fingerprint_changes_on_prompt_version(self):
        r1 = ResearchRequest(topic_id="t", canonical_topic="topic", query="topic", prompt_version="v1")
        r2 = ResearchRequest(topic_id="t", canonical_topic="topic", query="topic", prompt_version="v2")
        self.assertNotEqual(compute_research_fingerprint(r1), compute_research_fingerprint(r2))

    def test_06_duplicate_topic_blocked(self):
        profile = _profile()
        existing = ["Exact duplicate topic title"]
        result = run_topic_intelligence(
            self.tmp,
            profile,
            [_cand("Exact duplicate topic title")],
            existing_topics=existing,
            use_mock_research=True,
        )
        self.assertEqual(len(result["evaluated"]), 0)

    def test_07_cross_topic_contamination(self):
        profile = _profile(80777)
        titles = ["RV007 unique alpha topic", "RV007 unique beta topic"]
        result = run_topic_intelligence(
            self.tmp,
            profile,
            [_cand(t, 80777) for t in titles],
            use_mock_research=True,
        )
        fps: dict[str, str] = {}
        for ev in result["evaluated"]:
            tid = ev["candidate"]["topic_id"]
            title = ev["candidate"]["title"]
            rr = result["research"][tid]
            fps[tid] = rr["fingerprint"]
            claims = (rr.get("fact_pack") or {}).get("claims") or []
            claim_text = " ".join(str(c.get("claim") or "") for c in claims).lower()
            self.assertIn("rv007", claim_text)
            self.assertIn(title.split()[-2], claim_text)
        self.assertEqual(len(fps), 2)
        self.assertEqual(len(set(fps.values())), 2)

    def test_09_ranking_after_factpack_gate(self):
        profile = _profile()
        with patch("pipeline.intelligence.orchestrator.validate_fact_pack") as mock_gate:
            mock_gate.return_value = {"verdict": "RESEARCH_REQUIRED", "reason": "blocked"}
            with patch("pipeline.intelligence.orchestrator.execute_research_request") as mock_exec:
                mock_exec.return_value = type("RR", (), {
                    "success": True,
                    "fact_pack": {"claims": [
                        {"claim": "a", "evidence": "secondary", "source": "s1"},
                        {"claim": "b", "evidence": "supporting", "source": "s2"},
                    ]},
                    "research": {"query": "x"},
                    "fingerprint": "fp",
                    "action": "execute",
                    "provider_mode": "MOCK",
                })()
                result = run_topic_intelligence(
                    self.tmp, profile, [_cand("Gate blocked topic")], use_mock_research=True
                )
        self.assertTrue(result["evaluated"][0]["score"]["hard_blocked"])
        self.assertTrue(all(not r.get("eligible") for r in result["ranked_long"]))

    def test_10_invalid_cached_research_not_eligible(self):
        profile = _profile()
        result = run_topic_intelligence(
            self.tmp, profile, [_cand("Cache invalid topic")], use_mock_research=True
        )
        tid = result["evaluated"][0]["candidate"]["topic_id"]
        path = self.tmp / "research" / f"{tid}.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            data["fact_pack"]["claims"] = [{"claim": "tampered", "evidence": "x", "source": ""}]
            path.write_text(json.dumps(data), encoding="utf-8")
        r2 = run_topic_intelligence(
            self.tmp, profile, [_cand("Cache invalid topic")], use_mock_research=True
        )
        self.assertTrue(r2["evaluated"][0]["score"]["hard_blocked"])


class RV007ScoringIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_evidence_not_applied_to_b(self):
        profile = _profile(80788)
        high = "RV007 high evidence unique stellar topic"
        low = "RV007 low evidence unique minimal topic"
        result = run_topic_intelligence(
            self.tmp,
            profile,
            [_cand(high, 80788), _cand(low, 80788)],
            use_mock_research=True,
        )
        by_title: dict[str, dict] = {}
        for ev in result["evaluated"]:
            title = ev["candidate"]["title"]
            tid = ev["candidate"]["topic_id"]
            by_title[title] = {
                "score": ev["score"]["total_score"],
                "fingerprint": result["research"][tid]["fingerprint"],
                "evidence_count": result["research"][tid]["evidence_count"],
            }
        self.assertEqual(len(by_title), 2)
        fps = {v["fingerprint"] for v in by_title.values()}
        self.assertEqual(len(fps), 2, "each topic must have distinct research fingerprint")
        for title, meta in by_title.items():
            self.assertGreaterEqual(meta["evidence_count"], 2)
            self.assertGreater(meta["score"], 0.0)


class RV007IdempotencyCostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_cost_ledger()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_input_reuse(self):
        from pipeline.intelligence.mock_research_provider import get_mock_research_provider

        mp = get_mock_research_provider()
        mp.reset()
        profile = _profile(80799)
        title = "Idempotent reuse topic"
        run_topic_intelligence(self.tmp, profile, [_cand(title, 80799)], use_mock_research=True)
        calls_after_first = len(mp.calls)
        run_topic_intelligence(self.tmp, profile, [_cand(title, 80799)], use_mock_research=True)
        self.assertEqual(len(mp.calls), calls_after_first)

    def test_concurrent_same_topic_one_provider_call(self):
        from pipeline.intelligence.mock_research_provider import get_mock_research_provider

        mp = get_mock_research_provider()
        mp.reset()
        work = self.tmp / "conc"
        work.mkdir()
        req = ResearchRequest(topic_id="conc-rv7", canonical_topic="Concurrent RV7", query="concurrent rv7")

        def _run():
            execute_research_request(work, req, job_id="conc", use_mock=True, mock_provider=mp)

        threads = [threading.Thread(target=_run) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(mp.calls), 1)


class RV007FactpackGateCases(unittest.TestCase):
    def test_case_a_valid_pass(self):
        g = validate_fact_pack({"claims": [
            {"claim": "a", "evidence": "secondary", "source": "s1"},
            {"claim": "b", "evidence": "supporting", "source": "s2"},
        ]})
        self.assertEqual(g["verdict"], "PASS")

    def test_case_b_no_evidence(self):
        g = validate_fact_pack(None)
        self.assertEqual(g["verdict"], "RESEARCH_REQUIRED")

    def test_case_c_missing_source(self):
        g = validate_fact_pack({"claims": [
            {"claim": "a", "evidence": "secondary", "source": "s1"},
            {"claim": "b", "evidence": "supporting", "source": ""},
        ]})
        self.assertIn(g["verdict"], ("PASS", "RESEARCH_REQUIRED"))
        self.assertTrue(g.get("issues"))

    def test_case_d_unsupported(self):
        g = validate_fact_pack({"claims": [{"claim": "x", "evidence": "UNVERIFIED", "source": "s"}]})
        self.assertEqual(g["verdict"], "RESEARCH_REQUIRED")

    def test_case_f_insufficient(self):
        g = validate_fact_pack({"claims": [{"claim": "only one", "evidence": "secondary", "source": "s"}]})
        self.assertEqual(g["verdict"], "RESEARCH_REQUIRED")


class RV007RankingGuardTests(unittest.TestCase):
    def test_missing_score_not_rescored_without_research(self):
        profile = _profile()
        c = candidate_from_dict(_cand("Guard topic"))
        from pipeline.intelligence.scoring import score_candidate

        sr = score_candidate(c, profile, evidence_count=0)
        ranked = rank_candidates([c], profile, scores={})
        self.assertEqual(len(ranked), 1)
        self.assertFalse(ranked[0]["eligible"])
        self.assertEqual(ranked[0]["score"]["block_reason"], "MISSING_RESEARCH_SCORE")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-002 RV-007: {passed} / {result.testsRun}")
    sys.exit(0 if result.wasSuccessful() else 1)
