#!/usr/bin/env python3
"""Unit smoke tests for E2E UI engine (no live browser required)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestE2EUIModules(unittest.TestCase):
    def test_imports(self):
        from pipeline.e2e_ui import (
            AlertHandler,
            BrowserEngine,
            HumanInteractionManager,
            WorkflowTaskRunner,
        )

        self.assertTrue(BrowserEngine)
        self.assertTrue(HumanInteractionManager)
        self.assertTrue(WorkflowTaskRunner)
        self.assertTrue(AlertHandler)

    def test_browser_engine_profile_path(self):
        from pipeline.e2e_ui.browser_engine import BrowserEngine

        eng = BrowserEngine(platform="youtube", user_data_dir=str(ROOT / "data" / "_e2e_test_profile"))
        self.assertTrue(Path(eng.user_data_dir).is_dir())

    def test_human_bezier_and_type_delays(self):
        from pipeline.e2e_ui.human_input import HumanInteractionManager

        page = MagicMock()
        page.mouse = MagicMock()
        page.keyboard = MagicMock()
        loc = MagicMock()
        loc.bounding_box.return_value = {"x": 10, "y": 20, "width": 100, "height": 40}
        loc.wait_for = MagicMock()
        loc.scroll_into_view_if_needed = MagicMock()
        page.locator.return_value.first = loc

        hum = HumanInteractionManager(page, seed=1)
        hum.move_to(200, 200, steps=5)
        self.assertTrue(page.mouse.move.called)
        hum.click("button#x")
        self.assertTrue(page.mouse.click.called)

    def test_challenge_selectors_present(self):
        from pipeline.e2e_ui.alert_handler import DEFAULT_CHALLENGE_SELECTORS

        self.assertGreater(len(DEFAULT_CHALLENGE_SELECTORS), 5)

    def test_workflow_result_shape(self):
        from pipeline.e2e_ui.workflows import WorkflowResult

        r = WorkflowResult(ok=True, task="content_discovery", detail="ok")
        self.assertEqual(r.task, "content_discovery")


if __name__ == "__main__":
    unittest.main()
