import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

from app.config import ROOT, Settings
from app.main import app
from app import bootstrap_runtime


class TurnkeyAndCorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_cors_mobile_origin_headers(self):
        """Verify CORSMiddleware allows requests from mobile/local network devices with credentials."""
        mobile_origin = "http://192.168.1.105:3000"
        response = self.client.get(
            "/api/bootstrap/status",
            headers={"Origin": mobile_origin},
        )
        self.assertIn(response.status_code, (200, 401, 403, 404))
        self.assertEqual(response.headers.get("access-control-allow-origin"), mobile_origin)
        self.assertEqual(response.headers.get("access-control-allow-credentials"), "true")

    def test_cors_preflight_options_request(self):
        """Verify preflight OPTIONS requests from local network origins succeed with proper CORS headers."""
        mobile_origin = "http://192.168.1.250:8787"
        response = self.client.options(
            "/api/bootstrap/status",
            headers={
                "Origin": mobile_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), mobile_origin)
        self.assertEqual(response.headers.get("access-control-allow-credentials"), "true")
        allowed_methods = response.headers.get("access-control-allow-methods", "")
        self.assertTrue(
            "*" in allowed_methods or "POST" in allowed_methods,
            f"Unexpected allowed methods: {allowed_methods}",
        )

    def test_dry_run_publish_defaults_to_false_in_production(self):
        """Default dry_run_publish must be False in production so live publishing executes once credentials exist."""
        with patch.dict(os.environ, {}, clear=True):
            s = Settings(_env_file=None)
            self.assertIs(
                s.dry_run_publish,
                False,
                "dry_run_publish should default to False in production runtime",
            )

    def test_dry_run_publish_override_via_amp_dry_run(self):
        """Explicit AMP_DRY_RUN=1 overrides default to True for test harness and mock runs."""
        with patch.dict(os.environ, {"AMP_DRY_RUN": "1"}):
            s = Settings(_env_file=None)
            self.assertIs(s.dry_run_publish, True)

        with patch.dict(os.environ, {"AMP_DRY_RUN": "0"}):
            s = Settings(_env_file=None)
            self.assertIs(s.dry_run_publish, False)

    def test_dry_run_publish_explicit_kwargs(self):
        """Constructor kwargs take precedence over environment flags."""
        with patch.dict(os.environ, {"AMP_DRY_RUN": "1"}):
            s = Settings(_env_file=None, dry_run_publish=False)
            self.assertIs(s.dry_run_publish, False)

        with patch.dict(os.environ, {"AMP_DRY_RUN": "0"}):
            s = Settings(_env_file=None, dry_run_publish=True)
            self.assertIs(s.dry_run_publish, True)

    def test_launcher_scripts_structure_and_zero_crash_guard(self):
        """Ensure all turnkey launch scripts exist, detect embedded runtimes, and have fallback dialogs."""
        bat_launcher = ROOT / "Start_AutoMovie_Pro.bat"
        self.assertTrue(bat_launcher.is_file(), "Start_AutoMovie_Pro.bat must exist")
        bat_content = bat_launcher.read_text(encoding="utf-8", errors="ignore")

        # Verify runtime detection of both venv and python_embedded
        self.assertIn("venv\\Scripts\\python.exe", bat_content)
        self.assertIn("python_embedded\\python.exe", bat_content)

        # Verify non-crashing fallback dialog & setup invocation
        self.assertIn("setup_portable_runtime.bat", bat_content)
        self.assertIn("MessageBox", bat_content)
        self.assertIn("pause", bat_content)

        # Verify setup_portable_runtime.bat
        setup_bat = ROOT / "setup_portable_runtime.bat"
        self.assertTrue(setup_bat.is_file(), "setup_portable_runtime.bat must exist")
        setup_content = setup_bat.read_text(encoding="utf-8", errors="ignore")
        self.assertIn("bootstrap_runtime", setup_content)
        self.assertIn("python_embedded", setup_content)

        # Verify silent VBS launchers
        vbs_launcher = ROOT / "Start_AutoMovie_Pro.vbs"
        self.assertTrue(vbs_launcher.is_file(), "Start_AutoMovie_Pro.vbs must exist")
        vbs_content = vbs_launcher.read_text(encoding="utf-8", errors="ignore")
        self.assertIn("Start_AutoMovie_Pro.bat", vbs_content)
        self.assertIn(", 0, False", vbs_content)

        silent_vbs = ROOT / "Start_AutoMovie_Pro_Silent.vbs"
        self.assertTrue(silent_vbs.is_file(), "Start_AutoMovie_Pro_Silent.vbs must exist")

    def test_bootstrap_runtime_status_callable(self):
        """Ensure bootstrap_runtime status probe returns expected non-crashing structure."""
        st = bootstrap_runtime.status()
        self.assertTrue(st.get("ok"))
        self.assertEqual(st.get("bootstrap_version"), bootstrap_runtime.BOOTSTRAP_VERSION)
        self.assertIn("probes", st)
        self.assertIsInstance(st["probes"], dict)


if __name__ == "__main__":
    unittest.main()
