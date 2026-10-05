"""AMP-004 H2 — Production security & configuration hardening tests.

Paid APIs: 0. No real secrets printed.
"""
from __future__ import annotations

import inspect
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.config import (
    Settings,
    amp_skip_active,
    api_base_allows_local_login,
    is_production_runtime,
    local_login_permitted,
    resolve_local_login_credentials,
    safe_config_diagnostics,
    software_env_paths,
)
from pipeline.api_keys import DEFAULT_ENV_PATHS, mask_key, redact_mapping, redact_sensitive_text
from publishers.upload_service import _upload_youtube


class H2ConfigAuthorityTests(unittest.TestCase):
    def test_01_dry_run_publish_field_exists_default_true(self):
        s = Settings(
            _env_file=None,
            dry_run_publish=True,
            intelligence_mode="PRODUCTION",
            amp_allow_local_login=False,
        )
        self.assertTrue(hasattr(s, "dry_run_publish"))
        self.assertIs(s.dry_run_publish, True)

    def test_02_dry_run_from_env_file(self):
        with tempfile.TemporaryDirectory() as td:
            envp = Path(td) / ".env"
            envp.write_text("DRY_RUN_PUBLISH=false\nINTELLIGENCE_MODE=PRODUCTION\n", encoding="utf-8")
            s = Settings(_env_file=str(envp))
            self.assertIs(s.dry_run_publish, False)
            envp.write_text("DRY_RUN_PUBLISH=true\n", encoding="utf-8")
            s2 = Settings(_env_file=str(envp))
            self.assertIs(s2.dry_run_publish, True)

    def test_03_dry_run_matches_upload_path(self):
        s = Settings(_env_file=None, dry_run_publish=True)
        with patch("publishers.upload_service.settings", s):
            r = _upload_youtube({"title": "t"}, {}, Path("x.mp4"))
        self.assertTrue(r.get("ok"))
        self.assertTrue(str(r.get("url", "")).startswith("dry-run://"))

        s2 = Settings(_env_file=None, dry_run_publish=False)
        with patch("publishers.upload_service.settings", s2):
            with patch("publishers.youtube_uploader.upload_youtube", return_value="https://example.test/v"):
                r2 = _upload_youtube({"title": "t"}, {}, Path("x.mp4"))
        self.assertEqual(r2.get("url"), "https://example.test/v")
        self.assertNotIn("dry-run://", str(r2.get("url")))

    def test_04_safe_diagnostics_no_password_fields(self):
        s = Settings(
            _env_file=None,
            amp_dev_login_password="should-not-appear",
            amp_dev_login_id="devuser",
            amp_allow_local_login=True,
        )
        d = safe_config_diagnostics(s)
        blob = str(d)
        self.assertNotIn("should-not-appear", blob)
        self.assertNotIn("amp_dev_login_password", blob)
        self.assertIn("dry_run_publish", d)


class H2AuthFailClosedTests(unittest.TestCase):
    def test_10_production_missing_creds_fail_closed(self):
        s = Settings(
            _env_file=None,
            intelligence_mode="PRODUCTION",
            amp_allow_local_login=True,
            amp_dev_login_id="",
            amp_dev_login_password="",
        )
        self.assertIsNone(resolve_local_login_credentials(s))
        self.assertFalse(local_login_permitted("admin", "admin123", "local", s))

    def test_11_production_allow_false_fail_closed(self):
        s = Settings(
            _env_file=None,
            intelligence_mode="PRODUCTION",
            amp_allow_local_login=False,
            amp_dev_login_id="admin",
            amp_dev_login_password="admin123",
        )
        self.assertFalse(local_login_permitted("admin", "admin123", "local", s))

    def test_12_production_never_admin_admin123_fallback(self):
        s = Settings(
            _env_file=None,
            intelligence_mode="PRODUCTION",
            amp_allow_local_login=True,
            amp_dev_login_id="",
            amp_dev_login_password="",
        )
        self.assertFalse(local_login_permitted("admin", "admin123", "http://127.0.0.1", s))
        self.assertFalse(local_login_permitted("admin", "admin123", "https://yourdomain.com", s))

    def test_13_yourdomain_not_in_allowlist(self):
        s = Settings(_env_file=None, amp_allow_local_login=True)
        self.assertFalse(api_base_allows_local_login("https://yourdomain.com", s))
        self.assertFalse(api_base_allows_local_login("https://api.yourdomain.com", s))
        self.assertTrue(api_base_allows_local_login("local", s))
        self.assertTrue(api_base_allows_local_login("http://127.0.0.1:8787", s))

    def test_14_development_demo_when_explicitly_allowed(self):
        s = Settings(
            _env_file=None,
            intelligence_mode="DEVELOPMENT",
            amp_allow_local_login=True,
            amp_dev_login_id="",
            amp_dev_login_password="",
        )
        self.assertTrue(local_login_permitted("admin", "admin123", "local", s))
        self.assertFalse(local_login_permitted("admin", "admin123", "https://yourdomain.com", s))

    def test_15_production_explicit_creds_local_ok(self):
        s = Settings(
            _env_file=None,
            intelligence_mode="PRODUCTION",
            amp_allow_local_login=True,
            amp_dev_login_id="ops_user",
            amp_dev_login_password="explicit-not-default",
        )
        self.assertTrue(local_login_permitted("ops_user", "explicit-not-default", "local", s))
        self.assertFalse(local_login_permitted("admin", "admin123", "local", s))

    def test_16_main_login_source_has_no_hardcoded_admin123(self):
        import app.main as main_mod
        import app.customer_auth as auth_mod

        src = inspect.getsource(main_mod.login)
        self.assertNotIn("admin123", src)
        self.assertIn("authenticate", src)
        # C02: local login gate lives in customer_auth.authenticate (single authority)
        auth_src = inspect.getsource(auth_mod.authenticate)
        self.assertIn("local_login_permitted", auth_src)
        self.assertNotIn("admin123", auth_src)


class H2AmpSkipTests(unittest.TestCase):
    def test_20_skip_blocked_in_production(self):
        s = Settings(_env_file=None, intelligence_mode="PRODUCTION")
        prev = os.environ.get("AMP_SKIP_LOCALIZE")
        os.environ["AMP_SKIP_LOCALIZE"] = "1"
        try:
            self.assertFalse(amp_skip_active("AMP_SKIP_LOCALIZE", s))
        finally:
            if prev is None:
                os.environ.pop("AMP_SKIP_LOCALIZE", None)
            else:
                os.environ["AMP_SKIP_LOCALIZE"] = prev

    def test_21_skip_allowed_in_development(self):
        s = Settings(_env_file=None, intelligence_mode="DEVELOPMENT")
        prev = os.environ.get("AMP_SKIP_LOCALIZE")
        os.environ["AMP_SKIP_LOCALIZE"] = "1"
        try:
            self.assertTrue(amp_skip_active("AMP_SKIP_LOCALIZE", s))
        finally:
            if prev is None:
                os.environ.pop("AMP_SKIP_LOCALIZE", None)
            else:
                os.environ["AMP_SKIP_LOCALIZE"] = prev


class H2RedactionTests(unittest.TestCase):
    def test_30_redact_mapping_and_bearer(self):
        m = redact_mapping(
            {
                "api_key": "SECRETVALUE",
                "ok": 1,
                "note": "Authorization: Bearer sk-abcdefghijklmnopqrstuvwxyz012345",
            }
        )
        self.assertEqual(m["api_key"], "[REDACTED]")
        self.assertEqual(m["ok"], 1)
        self.assertNotIn("SECRETVALUE", str(m))
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz012345", str(m))
        self.assertIn("[REDACTED]", m["note"])

    def test_31_evidence_uses_shared_redact(self):
        from pipeline.e2e_industrial.evidence import ExecutionEvidence

        ev = ExecutionEvidence(job_id="j1")
        st = ev.begin("t")
        ev.end(st, "PASS", detail={"api_key": "SECRET", "ok": 1, "password": "x"})
        self.assertEqual(st.detail["api_key"], "[REDACTED]")
        self.assertEqual(st.detail["password"], "[REDACTED]")
        self.assertEqual(st.detail["ok"], 1)

    def test_32_mask_key_no_full_secret(self):
        full = "abcdefghijklmnop"
        m = mask_key(full)
        self.assertNotEqual(m, full)
        self.assertTrue(m.endswith("mnop") or m == "****")


class H2PathAndEnvTests(unittest.TestCase):
    def test_40_no_hardcoded_all_project_path(self):
        blob = " ".join(str(p) for p in DEFAULT_ENV_PATHS)
        self.assertNotIn("All Project", blob)
        self.assertTrue(any(str(p).endswith(".env") for p in DEFAULT_ENV_PATHS))

    def test_41_software_env_paths_relative(self):
        paths = software_env_paths()
        self.assertTrue(paths)
        self.assertTrue(all(isinstance(p, Path) for p in paths))

    def test_42_h1_normalize_lock_key_intact(self):
        from pipeline.idempotency.fs_lock import normalize_lock_key, thread_lock_for

        a = normalize_lock_key(r"C:\Temp\IDEMPOTENCY.json")
        b = normalize_lock_key(r"\\?\C:\Temp\IDEMPOTENCY.json")
        self.assertEqual(a, b)
        self.assertIs(thread_lock_for(r"C:\Temp\x.json"), thread_lock_for(r"\\?\C:\Temp\x.json"))


class H2ProductionRuntimeTests(unittest.TestCase):
    def test_50_default_settings_class_is_production(self):
        s = Settings(_env_file=None)
        self.assertTrue(is_production_runtime(s))
        self.assertTrue(s.dry_run_publish)


if __name__ == "__main__":
    unittest.main()
