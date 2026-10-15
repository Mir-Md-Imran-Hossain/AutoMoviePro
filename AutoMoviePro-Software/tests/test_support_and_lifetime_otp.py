import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_request_otp_routes_whatsapp_telegram():
    with patch("app.customer_auth.request_password_otp") as mock_otp:
        mock_otp.return_value = {
            "ok": True,
            "message": "৬ ডিজিটের ওটিপি আপনার WhatsApp / Telegram নম্বরে সফলভাবে পাঠানো হয়েছে।"
        }

        # Test WhatsApp phone payload
        res = client.post("/api/auth/request-otp", json={
            "whatsapp": "01712345678",
            "api_base_url": "https://automoviepro.com"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "WhatsApp" in data["message"]
        mock_otp.assert_called_with("01712345678", "https://automoviepro.com")

        # Test Telegram / identifier payload
        res2 = client.post("/api/auth/request-otp", json={
            "identifier": "@mytelegramuser"
        })
        assert res2.status_code == 200
        assert res2.json()["ok"] is True


def test_reset_password_route():
    with patch("app.customer_auth.reset_password") as mock_reset:
        mock_reset.return_value = {
            "ok": True,
            "message": "পাসওয়ার্ড সফলভাবে পরিবর্তিত হয়েছে।"
        }

        res = client.post("/api/auth/reset-password", json={
            "whatsapp": "01712345678",
            "otp": "654321",
            "new_password": "NewSecretPassword123"
        })
        assert res.status_code == 200
        assert res.json()["ok"] is True
        mock_reset.assert_called_with("01712345678", "654321", "NewSecretPassword123", "https://automoviepro.com")


def test_support_ticket_submission_with_72h_promise():
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "ticket_id": "AMP-TK0099"
        }
        mock_post.return_value = mock_resp

        res = client.post("/api/support/ticket", json={
            "type": "New Feature Suggestion",
            "contact": "01968111593",
            "message": "আমাদের একটি স্পোর্টস ড্রামা শর্টস থিম যুক্ত করার পরামর্শ।"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "AMP-TK0099" in data["ticket_id"]
        assert "৭২ ঘণ্টা" in data["message"]


def test_feedback_review_submission():
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        res = client.post("/api/feedback/review", json={
            "name": "Zahid Hasan",
            "rating": 5,
            "review_text": "অসাধারণ অটোমেশন সিস্টেম! খুব সহজেই চ্যানেল গ্রো করছে।"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "ধন্যবাদ" in data["message"]
