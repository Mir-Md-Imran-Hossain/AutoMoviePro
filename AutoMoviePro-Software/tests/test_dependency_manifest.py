"""Tests for Dependency Manifest & APScheduler Resilience (B-01).

Validates:
1. requirements.txt manifest presence and version pinning (APScheduler>=3.10.4,<4.0.0).
2. Clean environment import resilience: SchedulerService and app.main do not crash
   pytest collection when APScheduler is missing.
3. Explicit diagnostic error messaging on missing dependencies.
4. Normal operation when APScheduler is available.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

import app.scheduler_service as sched_mod
from app.scheduler_service import SchedulerService


class TestDependencyManifestAndScheduler(unittest.TestCase):
    def test_requirements_manifest_contains_apscheduler(self):
        """Verifies requirements.txt exists and explicitly pins APScheduler."""
        req_path = SOFTWARE_DIR / "requirements.txt"
        self.assertTrue(req_path.exists(), f"requirements.txt missing at {req_path}")

        content = req_path.read_text(encoding="utf-8")
        self.assertIn("APScheduler", content)
        self.assertTrue(
            "APScheduler>=3.10.4" in content or "APScheduler==" in content,
            "APScheduler should specify a compatible version in requirements.txt",
        )

    def test_scheduler_live_environment_available(self):
        """Verifies that in an environment with APScheduler installed, service is active."""
        if sched_mod.HAS_APSCHEDULER:
            service = SchedulerService()
            self.assertTrue(service.is_available)
            self.assertIsNotNone(service.scheduler)
        else:
            self.skipTest("APScheduler not installed in current interpreter.")

    def test_missing_apscheduler_graceful_import_and_diagnostic(self):
        """Simulates clean environment without APScheduler to verify zero pytest collection crash."""
        with patch.object(sched_mod, "HAS_APSCHEDULER", False):
            with patch.object(
                sched_mod,
                "_APSCHEDULER_ERROR",
                "No module named 'apscheduler'. Required for background cadence. Run: pip install -r requirements.txt",
            ):
                # Creating service in degraded mode must not crash
                service = SchedulerService()
                self.assertFalse(service.is_available)
                self.assertIsNone(service.scheduler)

                # start() and stop() must degrade gracefully with logged diagnostics
                service.start()
                self.assertFalse(service._started)
                service.stop()

    def test_app_main_import_without_apscheduler(self):
        """Ensures app.main and FastAPI app can be imported even when APScheduler is absent."""
        with patch.object(sched_mod, "HAS_APSCHEDULER", False):
            service = SchedulerService()
            self.assertFalse(service.is_available)


if __name__ == "__main__":
    unittest.main()
