"""BUILD-00R minimal import regression tests (no network, no paid APIs)."""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CRITICAL = [
    "app.main",
    "app.db",
    "app.config",
    "pipeline.dialogue_sync",
    "pipeline.lang_config",
    "pipeline.av_sync_critic",
    "pipeline.av_quality_gates",
    "pipeline.media_assets",
    "pipeline.scene_builder",
    "pipeline.compose",
    "pipeline.resume_guard",
    "pipeline.nish_catalog",
    "publishers.human_browser",
    "publishers.session_vault",
]


class ImportRegression(unittest.TestCase):
    def test_critical_modules_import(self):
        failed = []
        for mod in CRITICAL:
            try:
                importlib.import_module(mod)
            except Exception as exc:
                failed.append(f"{mod}: {exc}")
        self.assertFalse(failed, "Import failures:\n" + "\n".join(failed))

    def test_dialogue_sync_symbols(self):
        ds = importlib.import_module("pipeline.dialogue_sync")
        for name in (
            "AGNES_AUDIO_CHUNK_MAX",
            "DIALOGUE_TAIL_PAD_SEC",
            "estimate_spoken_seconds",
            "pad_av_tail",
        ):
            self.assertTrue(hasattr(ds, name), f"missing {name}")

    def test_lang_config_edge_voice(self):
        lc = importlib.import_module("pipeline.lang_config")
        for name in ("edge_voice_chain", "resolve_edge_voice", "SOURCE_LANG_BCP47"):
            self.assertTrue(hasattr(lc, name), f"missing {name}")

    def test_av_critic_training_rules(self):
        av = importlib.import_module("pipeline.av_sync_critic")
        for name in ("load_training_rules", "apply_training_rule", "TRAINING_RULES_PATH"):
            self.assertTrue(hasattr(av, name), f"missing {name}")

    def test_nish_catalog_loads(self):
        nc = importlib.import_module("pipeline.nish_catalog")
        catalog = nc.load_niche_catalog()
        self.assertIsInstance(catalog, list)
        self.assertGreater(len(catalog), 0)


if __name__ == "__main__":
    unittest.main()
