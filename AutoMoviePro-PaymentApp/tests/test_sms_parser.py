import os
import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from sms_parser import PaymentSMSParser

class TestPaymentSMSParser(unittest.TestCase):
    def test_bkash_parsing(self):
        msg = "You have received Tk 2,999.00 from 01711223344. Fee Tk 0.00. Balance Tk 50,000.00. TrxID BL928172KA at 21/09/2026 14:30"
        parsed = PaymentSMSParser.parse_sms("bKash", msg)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["provider"], "bkash")
        self.assertEqual(parsed["txn_id"], "BL928172KA")
        self.assertEqual(parsed["amount"], 2999.0)
        self.assertEqual(parsed["sender_phone"], "01711223344")
        self.assertEqual(parsed["sender_last_digits"], "3344")

    def test_nagad_parsing(self):
        msg = "Cash In Received. Amount: Tk 4,999.00. Sender: 01699887766. TxnID: 72JH891A. Balance: Tk 80,000"
        parsed = PaymentSMSParser.parse_sms("16167", msg)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["provider"], "nagad")
        self.assertEqual(parsed["txn_id"], "72JH891A")
        self.assertEqual(parsed["amount"], 4999.0)
        self.assertEqual(parsed["sender_last_digits"], "7766")

    def test_invalid_sms(self):
        msg = "Dear customer, your internet package will expire tomorrow."
        parsed = PaymentSMSParser.parse_sms("GP-Offer", msg)
        self.assertIsNone(parsed)


if __name__ == "__main__":
    unittest.main()
