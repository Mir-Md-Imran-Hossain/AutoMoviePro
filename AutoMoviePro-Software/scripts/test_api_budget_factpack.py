"""T011 + T012 unit tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.api_budget import ApiBudget
from pipeline.fact_pack import build_fact_pack, claim_allowed


class ApiBudgetTests(unittest.TestCase):
    def test_consume_and_block(self):
        with tempfile.TemporaryDirectory() as td:
            b = ApiBudget(Path(td), limits={"max_tts_calls": 2})
            self.assertTrue(b.consume("tts")["ok"])
            self.assertTrue(b.consume("tts")["ok"])
            self.assertFalse(b.consume("tts")["ok"])


class FactPackTests(unittest.TestCase):
    def test_build_and_barrier(self):
        pack = build_fact_pack(
            "Lost Library of Alexandria",
            notes="Ash layers dated by carbon samples under a collapsed aisle. Harbor silt sealed niches.",
        )
        self.assertGreaterEqual(len(pack["claims"]), 1)
        ok = claim_allowed("Ash layers dated by carbon samples under a collapsed aisle.", pack)
        self.assertTrue(ok["allowed"], ok)
        bad = claim_allowed("The iPhone 15 Pro Max camera is the best in class for low light.", pack)
        self.assertFalse(bad["allowed"])


if __name__ == "__main__":
    unittest.main()
