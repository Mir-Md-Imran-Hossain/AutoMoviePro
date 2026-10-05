"""T002 — ChannelDNA v0 unit tests (no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.channel_dna import (
    from_channel_row,
    infer_style_family,
    validate_topic_against_dna,
)
from pipeline.niche_director import _fallback_plan


class ChannelDNATests(unittest.TestCase):
    def test_ancient_civ_is_history(self):
        dna = from_channel_row({"id": 1, "niche": "Ancient Civilizations"})
        self.assertEqual(dna.style_family, "history")
        self.assertFalse(dna.allows_gadget_template())
        self.assertTrue(any("iphone" in x.lower() for x in dna.forbidden_topics))

    def test_gadget_niche(self):
        dna = from_channel_row({"id": 2, "niche": "Gadget Reviews"})
        self.assertEqual(dna.style_family, "gadget")
        self.assertTrue(dna.allows_gadget_template())

    def test_reject_iphone_on_history(self):
        dna = from_channel_row({"niche": "Ancient Civilizations"})
        r = validate_topic_against_dna("Apple iPhone 15 Pro unboxing", dna)
        self.assertFalse(r["passed"])
        self.assertEqual(r["verdict"], "FAIL")

    def test_accept_library_on_history(self):
        dna = from_channel_row({"niche": "Ancient Civilizations"})
        r = validate_topic_against_dna("Lost Library of Alexandria", dna)
        self.assertTrue(r["passed"])

    def test_fallback_history_for_ancient(self):
        plan = _fallback_plan(
            "Ancient Civilizations",
            "Sony WF-1000XM5",
            "short",
            58,
            "Ch",
            channel={"id": 1, "niche": "Ancient Civilizations"},
        )
        self.assertEqual(plan.get("style_family"), "history")
        elems = [str(s.get("element") or "") for s in plan.get("scenes") or []]
        self.assertNotIn("battery", elems)
        self.assertNotIn("camera", elems)
        # Forced gadget topic must not produce gadget hero script when DNA is history
        topic = str(plan.get("topic") or "")
        self.assertNotIn("sony", topic.lower())

    def test_infer_style_family_helpers(self):
        self.assertEqual(infer_style_family("Mystery Unexplained"), "mystery")
        self.assertEqual(infer_style_family("Science Facts"), "science")


if __name__ == "__main__":
    unittest.main()
