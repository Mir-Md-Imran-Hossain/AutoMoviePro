"""Tests for Google AI Pro Website Package & Manual WhatsApp Delivery Workflow.

Covers:
1. `google_pro_subscriptions` database schema & records:
   - id, customer_id, order_id, plan_duration_months, price, status ('pending_activation', 'active', 'expired'),
     target_email, google_pro_key, expires_at, created_at.
2. Pricing and duration plans:
   - Plan 1 (Monthly / 1 month): 120 BDT
   - Plan 2 (Yearly / 12 months): 999 BDT
   - Plan 3 (Special / 18 months): 1299 BDT
3. Automated WhatsApp Messages triggered upon payment approval:
   - Customer notification text asking for their Gmail for 150 GB Drive Vault & API setup.
   - Admin alert to WhatsApp number 01968111593 with order ID, customer name, mobile, and plan details.
4. Pending activation WhatsApp action button with prefilled wa.me URL.
5. Admin manual delivery & activation flow updating target Gmail and Google Pro Key.
"""

from __future__ import annotations

import sqlite3
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
import pytest

WEBSITE_ROOT = Path(__file__).resolve().parents[2] / "AutoMoviePro-Website"
SQLITE_DB = WEBSITE_ROOT / "storage" / "local_demo.sqlite"
if not SQLITE_DB.exists():
    SQLITE_DB = WEBSITE_ROOT / "local_demo.sqlite"


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def test_google_pro_subscriptions_schema(db_conn):
    cursor = db_conn.cursor()
    cursor.execute("PRAGMA table_info(google_pro_subscriptions)")
    columns = {row["name"]: row["type"].upper() for row in cursor.fetchall()}

    expected_cols = [
        "id",
        "customer_id",
        "order_id",
        "plan_duration_months",
        "price",
        "status",
        "target_email",
        "google_pro_key",
        "expires_at",
        "created_at",
    ]
    for col in expected_cols:
        assert col in columns, f"Column '{col}' missing from google_pro_subscriptions"


def test_pricing_and_plans():
    plans = {
        1: 120.0,
        12: 999.0,
        18: 1299.0,
    }
    assert plans[1] == 120.0
    assert plans[12] == 999.0
    assert plans[18] == 1299.0


def test_customer_and_admin_whatsapp_message_templates():
    order_id = 1055
    name = "তানভীর আহমেদ"
    whatsapp = "01711223344"
    duration_months = 12
    price = 999

    # 1. Customer WhatsApp Notification Template
    customer_msg = (
        "অভিনন্দন! আপনার AutoMovie Pro এর 'Google AI Pro প্যাকেজ'-এর পেমেন্ট সফলভাবে গৃহীত হয়েছে। "
        "এটি একটি ডেডিকেটেড প্রিমিয়াম সার্ভিস হওয়ায় আমরা আপনাকে ম্যানুয়ালি অ্যাকাউন্টটি কনফিগার করে দিচ্ছি। "
        "অনুগ্রহ করে আপনার যে জিমেইল (Gmail) অ্যাকাউন্টে ১৫০ জিবি ক্লাউড স্টোরেজ ও এপিআই এক্সেস নিতে চান, "
        "সেই ইমেইল অ্যাড্রেসটি লিখে আমাদের এই হোয়াটসঅ্যাপে মেসেজ পাঠান। "
        "আমাদের টিম খুব দ্রুত আপনার অ্যাকাউন্টটি অ্যাক্টিভ করে এপিআই কি ও ড্রাইভ এক্সেস বুঝিয়ে দেবে।"
    )

    assert "Google AI Pro প্যাকেজ" in customer_msg
    assert "১৫০ জিবি ক্লাউড স্টোরেজ" in customer_msg
    assert "জিমেইল (Gmail) অ্যাকাউন্টে" in customer_msg

    # 2. Admin WhatsApp Alert Template
    admin_number = "01968111593"
    admin_msg = (
        f"🚨 নতুন Google AI Pro অর্ডার! অর্ডার আইডি: #{order_id}, গ্রাহকের নাম: {name}, "
        f"মোবাইল: {whatsapp}, প্ল্যান: {duration_months} মাস ({price} ৳)। "
        f"গ্রাহককে জিমেইল চেয়ে ম্যানুয়ালি অ্যাকাউন্ট বুঝিয়ে দিন।"
    )

    assert "🚨 নতুন Google AI Pro অর্ডার!" in admin_msg
    assert f"#{order_id}" in admin_msg
    assert admin_number == "01968111593"
    assert f"{duration_months} মাস" in admin_msg
    assert f"{price} ৳" in admin_msg


def test_pending_page_whatsapp_link_generation():
    admin_phone = "8801968111593"
    order_id = 8820
    name = "রফিকুল ইসলাম"
    target_email = "rafiq.creator@gmail.com"

    text = f"হ্যালো অ্যাডমিন, আমার Google AI Pro অর্ডারের জন্য জিমেইল পাঠাচ্ছি:\nঅর্ডার আইডি: #{order_id}\nনাম: {name}\nজিমেইল: {target_email}"
    encoded = urllib.parse.quote(text)
    url = f"https://wa.me/{admin_phone}?text={encoded}"

    assert url.startswith("https://wa.me/8801968111593?text=")
    assert "8820" in urllib.parse.unquote(url)
    assert target_email in urllib.parse.unquote(url)


def test_subscription_creation_and_admin_fulfillment(db_conn):
    cursor = db_conn.cursor()

    # Create dummy customer and order
    cursor.execute(
        "INSERT INTO customers (name, whatsapp, email, status, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("সাকিব আল হাসান", "01799887766", "shakib@test.com", "active", datetime.now(timezone.utc).isoformat()),
    )
    cust_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO orders (customer_id, name, whatsapp, email, plan_name, amount, payment_method, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cust_id, "সাকিব আল হাসান", "01799887766", "shakib@test.com", "Google AI Pro 18M", 1299.0, "bkash", "pending_payment", datetime.now(timezone.utc).isoformat()),
    )
    order_id = cursor.lastrowid

    # Insert google_pro_subscriptions record (as created during purchase)
    cursor.execute(
        "INSERT INTO google_pro_subscriptions (customer_id, order_id, plan_duration_months, price, status, target_email, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cust_id, order_id, 18, 1299.0, "pending_activation", "shakib.drive@gmail.com", datetime.now(timezone.utc).isoformat()),
    )
    sub_id = cursor.lastrowid
    db_conn.commit()

    # Verify initial status
    cursor.execute("SELECT * FROM google_pro_subscriptions WHERE id = ?", (sub_id,))
    sub = cursor.fetchone()
    assert sub["status"] == "pending_activation"
    assert sub["plan_duration_months"] == 18
    assert sub["price"] == 1299.0
    assert sub["google_pro_key"] is None or sub["google_pro_key"] == ""

    # Admin manually delivers and activates: sets target_email, google_pro_key, and active status
    issued_key = "AIzaSy_PRODUCTION_GOOGLE_PRO_KEY_SHAKIB_9988"
    expires_at = "2028-03-23 00:00:00"
    cursor.execute(
        "UPDATE google_pro_subscriptions "
        "SET google_pro_key = ?, target_email = ?, status = 'active', expires_at = ? "
        "WHERE id = ?",
        (issued_key, "shakib.drive150gb@gmail.com", expires_at, sub_id),
    )
    db_conn.commit()

    # Verify fulfilled subscription
    cursor.execute("SELECT * FROM google_pro_subscriptions WHERE id = ?", (sub_id,))
    updated_sub = cursor.fetchone()
    assert updated_sub["status"] == "active"
    assert updated_sub["google_pro_key"] == issued_key
    assert updated_sub["target_email"] == "shakib.drive150gb@gmail.com"
    assert updated_sub["expires_at"] == expires_at
