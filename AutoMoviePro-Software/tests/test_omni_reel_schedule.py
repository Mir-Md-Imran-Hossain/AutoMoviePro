"""Unit tests for OmniReel Publisher and Schedule Manager in AutoMoviePro-Software."""

import json
from datetime import datetime
from fastapi.testclient import TestClient
from app.db import (
    init_db,
    upsert_channel,
    get_channel,
    save_session,
    get_channel_reel_settings,
    update_channel_reel_settings,
)
from publishers.omni_reel_publisher import OmniReelPublisher
from app.main import app


def test_reel_database_schema_and_settings():
    init_db()
    cid = upsert_channel({
        "youtube_name": "Test YT",
        "facebook_name": "Test FB",
        "niche": "AI Automation",
        "reels_per_day": 3,
        "reel_schedule_times": '["10:00", "15:00", "20:00"]',
        "reel_topics": '["Topic Alpha", "Topic Beta"]',
    })
    assert cid > 0

    settings = get_channel_reel_settings(cid)
    assert settings["reels_per_day"] == 3
    assert settings["schedule_slots"] == ["10:00", "15:00", "20:00"]
    assert settings["topics_pool"] == ["Topic Alpha", "Topic Beta"]

    # Test update
    ok = update_channel_reel_settings(
        cid,
        reels_per_day=4,
        schedule_slots=["09:00", "13:00", "17:00", "21:00"],
        topics_pool=["Updated Topic 1", "Updated Topic 2"]
    )
    assert ok is True
    updated = get_channel_reel_settings(cid)
    assert updated["reels_per_day"] == 4
    assert len(updated["schedule_slots"]) == 4
    assert updated["topics_pool"] == ["Updated Topic 1", "Updated Topic 2"]


def test_omni_reel_publisher_quota_and_slots():
    init_db()
    cid = upsert_channel({
        "youtube_name": "Reel Channel",
        "niche": "Tech",
        "reels_per_day": 2,
        "reel_schedule_times": '["00:01", "23:59"]',
        "reel_topics": '["Topic 1", "Topic 2"]',
    })
    pub = OmniReelPublisher(channel_id=cid)
    cfg = pub.get_settings()
    assert cfg["reels_per_day"] == 2
    assert cfg["schedule_slots"] == ["00:01", "23:59"]

    can_pub, reason = pub.can_publish_reel_today()
    assert can_pub is True
    assert "Quota available" in reason

    due_slot = pub.get_due_schedule_slot()
    # 00:01 is earlier than current time during the day, so it should be due
    assert due_slot == "00:01"


def test_reels_schedule_api_endpoints():
    init_db()
    cid = upsert_channel({
        "youtube_name": "API Channel",
        "niche": "Finance",
        "owner_login_id": "reel_tester",
        "reels_per_day": 2,
        "reel_schedule_times": '["11:00", "18:00"]',
    })
    save_session("reel_tester", "tok_test", {"id": 99, "login_id": "reel_tester"}, "http://localhost:8000")

    client = TestClient(app)
    get_res = client.get(f"/api/reels/schedule?channel_id={cid}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["ok"] is True
    assert data["settings"]["reels_per_day"] == 2

    post_res = client.post("/api/reels/schedule", json={
        "channel_id": cid,
        "reels_per_day": 3,
        "schedule_slots": ["10:30", "15:30", "20:30"],
        "topics_pool": ["Finance AI", "Crypto Secrets"]
    })
    assert post_res.status_code == 200
    pdata = post_res.json()
    assert pdata["ok"] is True
    assert pdata["settings"]["reels_per_day"] == 3
    assert pdata["settings"]["schedule_slots"] == ["10:30", "15:30", "20:30"]
