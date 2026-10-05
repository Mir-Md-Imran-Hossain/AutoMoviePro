"""
Multi-angle unit tests for Step 2:
Multi-Language Architecture & Per-Language 3-Channel Slots and SaaS Entitlements.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from app import db as store
from pipeline import lang_entitlement


class TestStep2Languages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db = Path(cls.temp_dir) / "test.db"
        store.DB_PATH = cls.test_db
        store.init_db()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_pricing_constants_and_base_entitlement(self):
        """Verify base SaaS package gives English + 1 chosen language (total 2), extra is 499 BDT."""
        self.assertEqual(lang_entitlement.DEFAULT_LANGUAGE_PRICE, "499")
        self.assertEqual(lang_entitlement.SETUP_LANGUAGE_COUNT, 2)
        self.assertEqual(lang_entitlement.MAX_LANGUAGES, 6)

        # Base setup: English + Bengali
        base = lang_entitlement.setup_languages("bn")
        self.assertEqual(base, ["en", "bn"])

        # Base setup: cannot pick English as second language
        with self.assertRaises(ValueError):
            lang_entitlement.setup_languages("en")

    def test_02_can_request_and_unlock_rules(self):
        """Verify eligibility rules for unlocking extra languages."""
        current = ["en", "bn"]
        # Can request Hindi
        res_hi = lang_entitlement.can_request("hi", current)
        self.assertTrue(res_hi.get("ok"))
        self.assertEqual(res_hi.get("code"), "hi")

        # Cannot request already unlocked language
        res_bn = lang_entitlement.can_request("bn", current)
        self.assertFalse(res_bn.get("ok"))
        self.assertEqual(res_bn.get("error"), "already_unlocked")

        # Cannot request english
        res_en = lang_entitlement.can_request("en", current)
        self.assertFalse(res_en.get("ok"))
        self.assertEqual(res_en.get("error"), "english_included")

        # Max languages constraint (max 6)
        max_unlocked = ["en", "bn", "hi", "ur", "ta", "ml"]
        res_max = lang_entitlement.can_request("es", max_unlocked)
        self.assertFalse(res_max.get("ok"))

    def test_03_language_request_db_lifecycle(self):
        """Verify DB operations for language purchase requests (Add-on 499 BDT)."""
        req_id = store.add_language_request(
            {
                "channel_id": 1,
                "lang_code": "hi",
                "amount": "499",
                "payment_ref": "TRX-BKASH-998811",
                "payment_note": "Payment for Hindi channel unlock",
                "status": "pending",
            }
        )
        self.assertGreater(req_id, 0)

        pending = store.pending_language_for("hi")
        self.assertIsNotNone(pending)
        self.assertEqual(pending["payment_ref"], "TRX-BKASH-998811")
        self.assertEqual(pending["amount"], "499")

        # Update status on approval
        store.update_language_request(req_id, status="approved")
        self.assertIsNone(store.pending_language_for("hi"))

        req = store.get_language_request(req_id)
        self.assertEqual(req["status"], "approved")


if __name__ == "__main__":
    unittest.main()
