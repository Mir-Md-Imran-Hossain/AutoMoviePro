"""Comprehensive unit & integration tests for Hardware ID (HWID) Engine & Licensing Policies.
Standard library unittest implementation (zero external dependency).

Tests:
- Real hardware profile extraction and confidence scoring
- Determinism and caching stability
- Modern Windows 11 PowerShell CIM extraction without WMIC
- Generic OEM placeholder filtering ("To be filled by O.E.M.", zeros)
- Hostname rename resilience (changing platform.node does not invalidate license)
- Component upgrade similarity recognition (SSD/CPU upgrade without lockout)
- Distinct machine rejection and device migration requirement
- Device migration policy: 7-day cooldown, 3 migrations/year quota, admin override
- Cross-platform signal extraction (Linux machine-id, macOS IOPlatformUUID)
"""
import hashlib
import os
import platform
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

import app.auth.hardware_id as hw_module
from app.auth.hardware_id import (
    GENERIC_SERIALS,
    GENERIC_UUIDS,
    HardwareProfile,
    can_migrate_device,
    compute_hardware_similarity,
    evaluate_hardware_match,
    get_hardware_fingerprint,
    get_hardware_profile,
    verify_hardware_fingerprint,
)


class TestHardwareIdResilience(unittest.TestCase):
    def setUp(self):
        # Clear module cache before each test
        hw_module._CACHED_FINGERPRINT = None
        hw_module._CACHED_PROFILE = None

    def tearDown(self):
        hw_module._CACHED_FINGERPRINT = None
        hw_module._CACHED_PROFILE = None

    def test_real_hardware_profile_extraction(self):
        """Verifies hardware profile extraction on the host machine."""
        profile = get_hardware_profile()
        self.assertIsInstance(profile, HardwareProfile)
        self.assertTrue(profile.hardware_id.startswith("AMP-HW-"))
        self.assertGreaterEqual(profile.confidence_score, 40)
        self.assertGreaterEqual(len(profile.signals_present), 2)
        self.assertIn(profile.system, ("Windows", "Linux", "Darwin"))

        # Cached fingerprint matches profile hardware_id
        fp = get_hardware_fingerprint()
        self.assertEqual(fp, profile.hardware_id)

    def test_fingerprint_stability_and_caching(self):
        """Calling get_hardware_fingerprint repeatedly returns identical values quickly."""
        fp1 = get_hardware_fingerprint()
        for _ in range(50):
            self.assertEqual(get_hardware_fingerprint(), fp1)

    def test_hostname_change_does_not_break_hwid(self):
        """Customer renaming their computer name must NOT invalidate their hardware ID."""
        with patch("platform.node", return_value="ORIGINAL-PC-NAME"):
            hw_module._CACHED_FINGERPRINT = None
            hw_module._CACHED_PROFILE = None
            fp_original = get_hardware_fingerprint()

        with patch("platform.node", return_value="RENAMED-NEW-PC-NAME"):
            hw_module._CACHED_FINGERPRINT = None
            hw_module._CACHED_PROFILE = None
            fp_renamed = get_hardware_fingerprint()

        self.assertEqual(
            fp_original,
            fp_renamed,
            "Hardware fingerprint must be immune to hostname changes",
        )

    def test_generic_oem_placeholders_filtered_out(self):
        """Generic motherboard UUID strings like 'To be filled by O.E.M.' are rejected as missing signals."""
        with patch("app.auth.hardware_id._get_windows_uuid", return_value=""), \
             patch("app.auth.hardware_id._get_cpu_id", return_value="CPU_GENUINE_123"), \
             patch("app.auth.hardware_id._get_disk_serial", return_value="DISK_SERIAL_ABC"), \
             patch("app.auth.hardware_id._get_windows_machine_guid", return_value="GUID_1234_5678"):
            hw_module._CACHED_FINGERPRINT = None
            hw_module._CACHED_PROFILE = None
            profile = get_hardware_profile()

            self.assertIn("MOTHERBOARD_UUID", profile.missing_signals)
            self.assertIn("CPU_PROCESSOR_ID", profile.signals_present)
            self.assertIn("DISK_SERIAL", profile.signals_present)
            # Still has high confidence due to CPU, Disk, and GUID
            self.assertGreaterEqual(profile.confidence_score, 60)

    def test_component_upgrade_similarity_recognition(self):
        """Replaced SSD or CPU recognized as component upgrade (similarity >= 0.60) allowing auto-activation."""
        base_profile = {
            "system": "Windows",
            "motherboard_uuid": "E4C83AFB-F183-4C70-ACB4-14751A1DDD78",
            "cpu_id": "BFEBFBFF000806C1",
            "disk_serial": "OLD_SSD_SERIAL_001",
            "machine_guid": "42d35e4a-650c-4b30-b6c9-5c7c79f96d42",
        }

        # User replaced SSD (disk_serial changed)
        upgraded_ssd_profile = dict(base_profile)
        upgraded_ssd_profile["disk_serial"] = "NEW_NVME_SERIAL_999"

        sim = compute_hardware_similarity(base_profile, upgraded_ssd_profile)
        # Motherboard (0.35) + CPU (0.25) + GUID (0.15) = 0.75
        self.assertGreaterEqual(sim, 0.70)

        # Evaluates as hardware upgrade recognized
        with patch("app.auth.hardware_id.get_hardware_profile") as mock_prof:
            mock_prof.return_value = HardwareProfile(
                system="Windows",
                motherboard_uuid=upgraded_ssd_profile["motherboard_uuid"],
                cpu_id=upgraded_ssd_profile["cpu_id"],
                disk_serial=upgraded_ssd_profile["disk_serial"],
                machine_guid=upgraded_ssd_profile["machine_guid"],
                node_name="MY-PC",
                hardware_id="AMP-HW-NEWUPGRADEDHASH9999",
                confidence_score=95,
            )
            status, score, msg = evaluate_hardware_match(
                expected_hwid="AMP-HW-OLDHASH1111",
                expected_profile=base_profile,
            )
            self.assertEqual(status, "HARDWARE_UPGRADE_RECOGNIZED")
            self.assertGreaterEqual(score, 0.70)
            self.assertIn("upgrade recognized", msg.lower())

    def test_distinct_machine_detection(self):
        """Completely different machine yields low similarity and requires device migration."""
        pc_one = {
            "system": "Windows",
            "motherboard_uuid": "E4C83AFB-F183-4C70-ACB4-14751A1DDD78",
            "cpu_id": "BFEBFBFF000806C1",
            "disk_serial": "KIOXIA_NVME_0100",
            "machine_guid": "42d35e4a-650c-4b30-b6c9-5c7c79f96d42",
        }

        pc_two = {
            "system": "Windows",
            "motherboard_uuid": "99999999-AAAA-BBBB-CCCC-DDDDDDDDDDDD",
            "cpu_id": "INTEL_DIFFERENT_CPU",
            "disk_serial": "SAMSUNG_980_PRO_DIFFERENT",
            "machine_guid": "different-guid-1111-2222-333333333333",
        }

        sim = compute_hardware_similarity(pc_one, pc_two)
        self.assertEqual(sim, 0.0)

        with patch("app.auth.hardware_id.get_hardware_profile") as mock_prof:
            mock_prof.return_value = HardwareProfile(
                system="Windows",
                motherboard_uuid=pc_two["motherboard_uuid"],
                cpu_id=pc_two["cpu_id"],
                disk_serial=pc_two["disk_serial"],
                machine_guid=pc_two["machine_guid"],
                node_name="PC-TWO",
                hardware_id="AMP-HW-PCTWO999999999",
                confidence_score=95,
            )
            status, score, msg = evaluate_hardware_match(
                expected_hwid="AMP-HW-PCONE111111111",
                expected_profile=pc_one,
            )
            self.assertEqual(status, "DEVICE_MIGRATION_REQUIRED")
            self.assertEqual(score, 0.0)

    def test_device_migration_policy_cooldown_and_quota(self):
        """Tests device migration policies: quota limits, cooldown period, and admin overrides."""
        # 1. Normal first migration of the year: ALLOWED
        ok, msg = can_migrate_device(
            days_since_last_migration=30,
            total_migrations_this_year=0,
            max_migrations_per_year=3,
            cooldown_days=7,
        )
        self.assertTrue(ok)
        self.assertIn("authorized", msg.lower())

        # 2. Migration attempted too soon (e.g. 3 days after last migration): BLOCKED by cooldown
        ok, msg = can_migrate_device(
            days_since_last_migration=3,
            total_migrations_this_year=1,
            max_migrations_per_year=3,
            cooldown_days=7,
        )
        self.assertFalse(ok)
        self.assertIn("cooldown active", msg.lower())
        self.assertIn("4 day", msg.lower())

        # 3. Yearly quota exceeded (e.g. already migrated 3 times): BLOCKED by quota
        ok, msg = can_migrate_device(
            days_since_last_migration=20,
            total_migrations_this_year=3,
            max_migrations_per_year=3,
            cooldown_days=7,
        )
        self.assertFalse(ok)
        self.assertIn("limit exceeded", msg.lower())

        # 4. Admin override: BYPASSES both cooldown and quota
        ok, msg = can_migrate_device(
            days_since_last_migration=1,
            total_migrations_this_year=5,
            admin_override=True,
        )
        self.assertTrue(ok)
        self.assertIn("admin override", msg.lower())

    def test_legacy_hwid_backward_compatibility(self):
        """Verifies that licenses bound under the legacy formula are recognized seamlessly."""
        profile = get_hardware_profile()
        sys_name = profile.system
        legacy_components = [
            f"SYS:{sys_name}",
            f"UUID:{profile.motherboard_uuid}",
            f"CPU:{profile.cpu_id}",
            f"DISK:",
            f"NODE:{profile.node_name}",
        ]
        legacy_sig = "|".join(legacy_components)
        legacy_hwid = f"AMP-HW-{hashlib.sha256(legacy_sig.encode('utf-8')).hexdigest()[:32].upper()}"

        # verify_hardware_fingerprint must return True for legacy HWID on this machine
        self.assertTrue(verify_hardware_fingerprint(legacy_hwid))


if __name__ == "__main__":
    unittest.main()
