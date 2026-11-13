"""
AutoMovie Pro — Part 11, 12, & 13: Main Website, Payments & Critical Audits Test Suite
Validates:
1. Part 11: Main Website Structure & Pricing (includes/features_catalog.php, index.php, sitemap.php)
2. Part 12: Payment System & SMS Verification Engine (PaymentApp/sms_parser.py)
3. Part 13: Technical Integrity & Internationalization Fonts (assets/fonts)
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

sys.path.insert(0, str(BASE_DIR / "AutoMoviePro-PaymentApp"))

from sms_parser import PaymentSMSParser

class Part11_12_13AuditTest(unittest.TestCase):

    def test_01_website_critical_pages_and_pricing(self):
        """Verify main website critical entry points and features catalog exist with ৳3999 pricing."""
        web_dir = BASE_DIR / "AutoMoviePro-Website"
        self.assertTrue((web_dir / "index.php").exists())
        self.assertTrue((web_dir / "order.php").exists())
        self.assertTrue((web_dir / "purchase.php").exists())
        self.assertTrue((web_dir / "pending.php").exists())
        self.assertTrue((web_dir / "download.php").exists())
        self.assertTrue((web_dir / "sitemap.php").exists())
        self.assertTrue((web_dir / "robots.txt").exists())

        catalog_path = web_dir / "includes" / "features_catalog.php"
        self.assertTrue(catalog_path.exists())
        catalog_text = catalog_path.read_text(encoding="utf-8")
        self.assertIn("3999", catalog_text)

    def test_02_payment_sms_parser_all_mfs_providers(self):
        """Verify bKash, Nagad, and Rocket SMS transaction parsing engine."""
        # 1. bKash Cash In
        bkash_sms = "Cash In Tk 3,999.00 from 01711223344 successful. Fee Tk 0.00. Balance Tk 50,000.00. TrxID BK99AX8811 at 12/11/2026 15:45"
        res_bkash = PaymentSMSParser.parse_sms("bKash", bkash_sms)
        self.assertIsNotNone(res_bkash)
        self.assertEqual(res_bkash["provider"], "bkash")
        self.assertEqual(res_bkash["txn_id"], "BK99AX8811")
        self.assertEqual(res_bkash["amount"], 3999.0)
        self.assertEqual(res_bkash["sender_phone"], "01711223344")

        # 2. Nagad Cash In
        nagad_sms = "Money received from 01611223344. Amount: Tk 3,999.00, TxnID: NG88YY7722, Balance: Tk 25,000.00"
        res_nagad = PaymentSMSParser.parse_sms("Nagad", nagad_sms)
        self.assertIsNotNone(res_nagad)
        self.assertEqual(res_nagad["provider"], "nagad")
        self.assertEqual(res_nagad["txn_id"], "NG88YY7722")
        self.assertEqual(res_nagad["amount"], 3999.0)
        self.assertEqual(res_nagad["sender_phone"], "01611223344")

        # 3. Rocket Cash In
        rocket_sms = "Received Tk.3999.00 from 01911223344, TxnId: RK77ZZ6633, Balance Tk.15,000.00"
        res_rocket = PaymentSMSParser.parse_sms("16216", rocket_sms)
        self.assertIsNotNone(res_rocket)
        self.assertEqual(res_rocket["provider"], "rocket")
        self.assertEqual(res_rocket["txn_id"], "RK77ZZ6633")
        self.assertEqual(res_rocket["amount"], 3999.0)

    def test_03_internationalization_fonts_presence(self):
        """Verify required Unicode Bengali and typography fonts exist for rendering."""
        fonts_dir = BASE_DIR / "AutoMoviePro-Software" / "assets" / "fonts"
        self.assertTrue(fonts_dir.exists(), "Fonts directory missing")
        fonts = [f.name for f in fonts_dir.iterdir() if f.is_file()]
        
        required_fonts = [
            "AnekBangla-Bold.ttf",
            "HindSiliguri-Bold.ttf",
            "Kalpurush.ttf",
            "NotoSansBengali-Bold.ttf"
        ]
        for rf in required_fonts:
            self.assertIn(rf, fonts, f"Required font {rf} missing from assets/fonts")


if __name__ == "__main__":
    unittest.main()
