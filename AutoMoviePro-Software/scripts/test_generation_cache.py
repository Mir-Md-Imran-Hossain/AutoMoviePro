"""T006 — Generation idempotency: 5 requests → 1 create, 4 reuse."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.generation_cache import GenerationCache, make_generation_key


class GenerationIdempotencyTests(unittest.TestCase):
    def test_key_stable(self):
        a = make_generation_key(
            scene_id=3,
            claim_id="C03",
            narration="hello",
            visual_prompt="ruins",
            provider="agnes",
            model="v1",
        )
        b = make_generation_key(
            scene_id=3,
            claim_id="C03",
            narration="hello",
            visual_prompt="ruins",
            provider="agnes",
            model="v1",
        )
        c = make_generation_key(
            scene_id=3,
            claim_id="C03",
            narration="hello DIFFERENT",
            visual_prompt="ruins",
            provider="agnes",
            model="v1",
        )
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_five_requests_one_create(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            cache = GenerationCache(work)
            key = make_generation_key(
                scene_id=1,
                claim_id="C01",
                narration="n",
                visual_prompt="p",
                provider="mock",
            )
            artifact = work / "scene_01.mp4"
            # Simulate first create
            r1 = cache.request_create(key, artifact=artifact)
            self.assertEqual(r1["action"], "create")
            artifact.write_bytes(b"0" * 5000)
            cache.commit(key, artifact)
            # Four more identical requests
            for _ in range(4):
                r = cache.request_create(key, artifact=artifact)
                self.assertEqual(r["action"], "reuse")
            st = cache.stats()
            self.assertEqual(st["create_count"], 1)
            self.assertEqual(st["reuse_count"], 4)


if __name__ == "__main__":
    unittest.main()
