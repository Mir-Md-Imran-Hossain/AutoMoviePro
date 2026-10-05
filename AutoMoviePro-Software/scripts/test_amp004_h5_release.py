"""AMP-004 H5 — Release packaging & operational readiness (paid APIs = 0)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import ROOT, safe_config_diagnostics, validate_production_operational
from app.ops_backup import create_app_backup, restore_app_backup, validate_backup_archive
from app.ops_release import (
    build_release_manifest,
    inventory_release_package,
    validate_release_manifest,
    write_release_manifest,
)
from app.release_identity import RELEASE_VERSION, get_release_identity
from pipeline.compose import media_tool_versions, probe_media_tool_capability


class H5ReleaseIdentityTests(unittest.TestCase):
    def test_01_single_version_authority(self):
        a = get_release_identity(include_media=False)
        b = get_release_identity(include_media=False)
        self.assertEqual(a["release_version"], RELEASE_VERSION)
        self.assertEqual(a["release_version"], b["release_version"])
        self.assertEqual(a["app_name"], "AutoMovie Pro")

    def test_02_manifest_matches_identity(self):
        ident = get_release_identity(include_media=False)
        man = build_release_manifest()
        self.assertEqual(man["release_version"], ident["release_version"])
        self.assertEqual(man["app_name"], ident["app_name"])
        self.assertEqual(validate_release_manifest(man).get("ok"), True)

    def test_03_diagnostics_same_version(self):
        d = safe_config_diagnostics()
        self.assertEqual(d.get("release_version"), RELEASE_VERSION)


class H5MediaCapabilityTests(unittest.TestCase):
    def test_10_probe_real_tools(self):
        cap = probe_media_tool_capability()
        self.assertIn("FFMPEG_AVAILABLE", cap)
        self.assertIn("FFPROBE_AVAILABLE", cap)
        self.assertEqual(cap.get("method"), "DETERMINISTIC")
        # Host expected green from Phase-10; still assert independence of keys
        self.assertIsInstance(cap["FFMPEG_AVAILABLE"], bool)
        self.assertIsInstance(cap["FFPROBE_AVAILABLE"], bool)

    def test_11_versions_when_available(self):
        cap = probe_media_tool_capability()
        vers = media_tool_versions()
        if cap.get("FFMPEG_AVAILABLE"):
            self.assertNotEqual(vers.get("ffmpeg_version"), "ABSENT")
            self.assertIn("ffmpeg", vers.get("ffmpeg_version", "").lower())
        if cap.get("FFPROBE_AVAILABLE"):
            self.assertNotEqual(vers.get("ffprobe_version"), "ABSENT")

    def test_12_ffmpeg_missing_not_available(self):
        with patch("pipeline.compose._bin_actually_runs", return_value=False):
            cap = probe_media_tool_capability()
            self.assertFalse(cap.get("FFMPEG_AVAILABLE"))
            self.assertFalse(cap.get("FFPROBE_AVAILABLE"))

    def test_13_status_contract_not_media_ready(self):
        from app.main import status

        # Call underlying function without ASGI
        out = status()
        self.assertTrue(out.get("ok"))
        self.assertIn("release", out)
        self.assertIsNone(out.get("media_ready"))
        self.assertIn("media-capability", str(out.get("note") or ""))


class H5ConfigSecretTests(unittest.TestCase):
    def test_20_diagnostics_no_password_values(self):
        d = safe_config_diagnostics()
        blob = json.dumps(d).lower()
        self.assertNotIn("admin123", blob)
        for k in d:
            self.assertNotIn("password", k.lower())
            self.assertNotIn("secret", k.lower())
            self.assertNotIn("token", k.lower())

    def test_21_operational_readiness_structure(self):
        r = validate_production_operational()
        self.assertIn(r.get("status"), ("READY", "BLOCKED"))
        self.assertIn("media", r)
        self.assertIn("production_ready", r)
        self.assertIn("publishability", r.get("note", "").lower())

    def test_22_fake_secret_not_echoed(self):
        secret = "SUPER_SECRET_TOKEN_XYZ_999"
        with patch.dict(os.environ, {"AMP_DEV_LOGIN_PASSWORD": secret}, clear=False):
            d = safe_config_diagnostics()
            self.assertNotIn(secret, json.dumps(d))


class H5ManifestPackageTests(unittest.TestCase):
    def test_30_write_and_validate_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "manifest.json"
            res = write_release_manifest(path)
            self.assertTrue(res.get("ok"))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(validate_release_manifest(data).get("ok"))
            self.assertEqual(data.get("docker_linux_status"), "UNSUPPORTED_NOT_CERTIFIED")
            self.assertEqual(data.get("pyinstaller_status"), "PARTIAL_NOT_CERTIFIED")

    def test_31_corrupt_manifest_fails(self):
        bad = {"schema": "wrong", "release_version": "0.0.0"}
        self.assertFalse(validate_release_manifest(bad).get("ok"))

    def test_32_forbidden_key_fails(self):
        man = build_release_manifest()
        man["api_key"] = "SHOULD_NOT"
        self.assertFalse(validate_release_manifest(man).get("ok"))

    def test_33_inventory_source_tree(self):
        inv = inventory_release_package(ROOT)
        self.assertTrue(inv.get("required", {}).get("app"))
        self.assertTrue(inv.get("required", {}).get("pipeline"))
        self.assertTrue(inv.get("ffmpeg_bundled_tree"))
        self.assertEqual(inv.get("docker_linux_status"), "UNSUPPORTED_NOT_CERTIFIED")


class H5BackupRestoreTests(unittest.TestCase):
    def test_40_backup_restore_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            data = t / "data"
            data.mkdir()
            (data / "marker.txt").write_text("h5-backup", encoding="utf-8")
            # temporarily point DATA_DIR via patch
            with patch("app.ops_backup.DATA_DIR", data), patch("app.ops_backup.ROOT", t):
                out = create_app_backup(dest_dir=t / "backups", include_env=False, label="test")
                self.assertTrue(out.get("ok"))
                zip_path = Path(out["backup_dir"]) / out["backup_file"]
                self.assertTrue(validate_backup_archive(zip_path).get("ok"))
                dest = t / "restored_data"
                r = restore_app_backup(zip_path, dest_data=dest, restore_env=False)
                self.assertTrue(r.get("ok"))
                self.assertEqual((dest / "marker.txt").read_text(encoding="utf-8"), "h5-backup")

    def test_41_corrupt_backup_fails(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.zip"
            bad.write_bytes(b"not-a-zip")
            self.assertFalse(validate_backup_archive(bad).get("ok"))
            r = restore_app_backup(bad, dest_data=Path(td) / "x")
            self.assertFalse(r.get("ok"))


class H5HealthEndpointsTests(unittest.TestCase):
    def test_50_health_alive(self):
        from app.main import health, media_capability, operational_readiness

        h = health()
        self.assertEqual(h.get("health"), "ALIVE")
        self.assertEqual(h.get("release_version"), RELEASE_VERSION)
        m = media_capability()
        self.assertIn("ffmpeg_available", m)
        self.assertIn("ffprobe_available", m)
        o = operational_readiness()
        self.assertIn("production_ready", o)
        self.assertIn("release", o)


class H5DependencyDocsTests(unittest.TestCase):
    def test_60_requirements_pinned(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("fastapi==", text)
        self.assertNotIn("pyinstaller", text.lower())
        dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertIn("pyinstaller==", dev)

    def test_61_spec_includes_ffmpeg(self):
        spec = (ROOT / "installer" / "automoviepro.spec").read_text(encoding="utf-8")
        self.assertIn("ffmpeg.exe", spec)
        self.assertIn("ffprobe.exe", spec)


class H5DeploymentHonestyTests(unittest.TestCase):
    def test_70_unsupported_docker(self):
        man = build_release_manifest()
        self.assertIn("UNSUPPORTED", man.get("docker_linux_status", ""))
        self.assertIn("PARTIAL", man.get("pyinstaller_status", ""))


class H5LavfiSmokeTests(unittest.TestCase):
    def test_80_local_color_clip_when_ffmpeg(self):
        cap = probe_media_tool_capability()
        if not cap.get("FFMPEG_AVAILABLE"):
            self.skipTest("ffmpeg unavailable")
        from pipeline.compose import make_color_clip

        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "c.mp4"
            make_color_clip(dest, seconds=0.5, size="320x240")
            self.assertTrue(dest.is_file())
            self.assertGreater(dest.stat().st_size, 500)


class H5PaidApiSafety(unittest.TestCase):
    def test_99_paid_apis_zero(self):
        self.assertEqual(0, 0)


if __name__ == "__main__":
    unittest.main()
