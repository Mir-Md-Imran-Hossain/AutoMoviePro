import os
import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from app.legal.consent_manager import ConsentManager, CURRENT_LEGAL_VERSION

class TestConsentManager(unittest.TestCase):
    def setUp(self):
        self.manager = ConsentManager()

    def test_get_terms(self):
        terms_bn = self.manager.get_terms("bn")
        self.assertEqual(terms_bn["version"], CURRENT_LEGAL_VERSION)
        self.assertIn("অটোমুভি প্রো", terms_bn["title"])
        self.assertGreater(len(terms_bn["sections"]), 0)

        terms_en = self.manager.get_terms("en")
        self.assertIn("AutoMovie Pro", terms_en["title"])

    def test_consent_lifecycle(self):
        import time
        user_id = f"test_user_consent_{int(time.time()*1000)}"
        hw_id = "HW-UUID-999-ABC"

        # Initially should not have consented
        self.assertFalse(self.manager.has_consented(user_id, hw_id))

        # Record consent
        res = self.manager.record_consent(user_id, hw_id, ip_address="192.168.1.10")
        self.assertTrue(res["ok"])

        # Now should have consented
        self.assertTrue(self.manager.has_consented(user_id, hw_id))

        # Different hardware ID should return False
        self.assertFalse(self.manager.has_consented(user_id, "DIFFERENT-HWID"))


if __name__ == "__main__":
    unittest.main()
