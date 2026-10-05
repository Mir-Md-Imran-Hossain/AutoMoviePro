import os
import sys
import json
import sqlite3
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from admin_service import AdminAppService

class TestAdminApp(unittest.TestCase):
    def setUp(self):
        self.service = AdminAppService()

    def test_metrics_accuracy(self):
        """Verifies revenue is accurately calculated from database orders and never 487500."""
        metrics = self.service.get_dashboard_metrics()
        self.assertNotEqual(metrics["total_revenue_bdt"], 487500, "Should NEVER return imaginary 487500 Tk!")
        self.assertGreater(metrics["total_revenue_bdt"], 0)
        self.assertGreater(metrics["total_customers"], 0)

        # Cross-verify with database directly
        db_path = self.service._get_db_path()
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status IN ('approved', 'active')")
            expected_rev = float(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM customers")
            expected_cust = int(cur.fetchone()[0])
            conn.close()
            self.assertEqual(metrics["total_revenue_bdt"], expected_rev)
            self.assertEqual(metrics["total_customers"], expected_cust)

    def test_remote_killswitch_1click(self):
        """Tests 1-click killswitch instantly locks customer and updates status."""
        res = self.service.toggle_customer_killswitch("1", "banned")
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "banned")
        self.assertIn("লক কার্যকর", res["message"])

        # Check database license revocation
        db_path = self.service._get_db_path()
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("SELECT revoked FROM licenses WHERE customer_id = 1")
            row = cur.fetchone()
            if row:
                self.assertEqual(row[0], 1)
            conn.close()

    def test_broadcast_1click(self):
        """Tests 1-click broadcast writes to software announcement stream and database."""
        notice_text = "টেস্ট জরুরি ব্রডকাস্ট বার্তা"
        res = self.service.broadcast_announcement(notice_text, "Test urgent broadcast", "high")
        self.assertTrue(res["ok"])
        self.assertIn("সফটওয়্যার", res["message"])

        # Check announcements.json stream
        ann_file = APP_DIR.parent / "AutoMoviePro-Software" / "app" / "data" / "announcements.json"
        if ann_file.exists():
            with open(ann_file, "r", encoding="utf-8") as f:
                ann = json.load(f)
                self.assertTrue(any(notice_text in n.get("title_bn", "") for n in ann))


if __name__ == "__main__":
    unittest.main()
