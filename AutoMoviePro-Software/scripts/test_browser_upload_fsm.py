"""T010 — Browser upload FSM tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.browser_upload_fsm import BrowserUploadFSM, InvalidBrowserTransition


class BrowserUploadFSMTests(unittest.TestCase):
    def test_happy_dry_run(self):
        fsm = BrowserUploadFSM(dry_run=True)
        for s in (
            "SESSION_READY",
            "AUTHENTICATED",
            "NAVIGATING",
            "PAGE_READY",
            "FILE_SELECTED",
            "PROCESSING",
            "DETAILS",
            "METADATA_FILLED",
            "CHECKS",
            "PUBLISH",
        ):
            fsm.transition(s)
        fsm.transition("PUBLISHED", verified=True)
        fsm.transition("VERIFIED")
        self.assertEqual(fsm.state, "VERIFIED")

    def test_publish_requires_verify_flag(self):
        fsm = BrowserUploadFSM(dry_run=False)
        for s in (
            "SESSION_READY",
            "AUTHENTICATED",
            "NAVIGATING",
            "PAGE_READY",
            "FILE_SELECTED",
            "PROCESSING",
            "DETAILS",
            "METADATA_FILLED",
            "CHECKS",
            "PUBLISH",
        ):
            fsm.transition(s)
        with self.assertRaises(InvalidBrowserTransition):
            fsm.transition("PUBLISHED", verified=False)

    def test_one_captcha_incident(self):
        fsm = BrowserUploadFSM(dry_run=True)
        for s in (
            "SESSION_READY",
            "AUTHENTICATED",
            "NAVIGATING",
            "PAGE_READY",
            "FILE_SELECTED",
            "PROCESSING",
            "DETAILS",
            "METADATA_FILLED",
            "CHECKS",
            "PUBLISH",
        ):
            fsm.transition(s)
        fsm.transition("CAPTCHA_REQUIRED")
        with self.assertRaises(InvalidBrowserTransition):
            fsm.transition("CAPTCHA_REQUIRED")


if __name__ == "__main__":
    unittest.main()
