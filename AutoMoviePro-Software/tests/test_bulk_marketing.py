import os
import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from marketing.bulk_marketing_engine import BulkMarketingEngine, GrokSalesCloserAgent

class TestBulkMarketing(unittest.TestCase):
    def setUp(self):
        self.engine = BulkMarketingEngine()

    def test_grok_sales_agent(self):
        # Test Price inquiry
        res_price = GrokSalesCloserAgent.answer_inquiry("অটোমুভি প্রো এর দাম কত ভাই?", lead_name="করিম ভাই", language="bn")
        self.assertEqual(res_price["intent"], "pricing")
        self.assertIn("২৯৯৯ টাকা", res_price["response"])
        self.assertIn("করিম ভাই", res_price["response"])

        # Test Payment inquiry
        res_pay = GrokSalesCloserAgent.answer_inquiry("বিকাশ বা নগদ নম্বর দিন", lead_name="Rahim", language="bn")
        self.assertEqual(res_pay["intent"], "payment_info")
        self.assertIn("জাহিদ ফার্মেসি", res_pay["response"])

    def test_lead_management(self):
        res = self.engine.add_lead(
            name="Shahidul Islam",
            phone_or_tg="+8801700112233",
            platform="whatsapp",
            niche="Islamic Stories"
        )
        self.assertTrue(res["ok"])
        lead = res["lead"]
        self.assertEqual(lead["status"], "new")

        # Update status
        updated = self.engine.update_lead_status("+8801700112233", "converted")
        self.assertTrue(updated)

        converted_leads = self.engine.get_leads(status="converted")
        self.assertTrue(any(l["contact"] == "+8801700112233" for l in converted_leads))

    def test_broadcast_campaign(self):
        recipients = ["+8801811223344", "+8801911223355"]
        res = self.engine.run_broadcast_simulation(
            campaign_name="Eid Mega Discount",
            template="Hello! Get AutoMovie Pro today at ৳2999.",
            lead_contacts=recipients,
            platform="whatsapp"
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["campaign"]["total_recipients"], 2)
        self.assertEqual(len(res["deliveries"]), 2)


if __name__ == "__main__":
    unittest.main()
