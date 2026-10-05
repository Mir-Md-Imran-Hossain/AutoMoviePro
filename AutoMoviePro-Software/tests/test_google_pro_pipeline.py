"""Tests for Google AI Pro Pipeline & 150 GB Google Drive Cloud Storage Vault.

Covers:
1. Google Pro API Key setup and per-language configuration in channel setup.
2. Highest priority (index 0) resolution in API Hub chains:
   - LLM Research & Script (gemini_pro_research, gemini_pro_script)
   - TTS (google_pro_tts)
   - Image generation (nano_banana_pro_image)
   - Video generation (veo3_pro_video)
3. Quota bypass for Google Pro keys.
4. Google Drive 150 GB Vault daily bundling (/AutoMoviePro_Vault/YYYY-MM-DD_VideoTitle/)
   with master .mp4, scene clips, audio tracks, thumbnail .png, and metadata .json.
5. FastAPI endpoints:
   - POST & GET /api/setup/google-pro-key
   - POST /api/storage/drive-config
   - POST /api/storage/sync-now
   - GET /api/storage/status
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api_matrix.api_hub import ApiHub, ApiMatrixConfig, KeyQuotaGuard, get_api_hub
from app.setup.channel_setup import ChannelSetupManager
from app.storage.google_drive_sync import GoogleDriveVaultSync
from app.main import app


@pytest.fixture
def temp_dirs():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        data_dir = tdp / "data"
        output_dir = tdp / "output"
        data_dir.mkdir(parents=True)
        output_dir.mkdir(parents=True)
        yield data_dir, output_dir


def test_channel_setup_google_pro_key(temp_dirs):
    data_dir, _ = temp_dirs
    cm = ChannelSetupManager(data_dir=data_dir)

    profile = cm.get_profile()
    assert "bn" in profile["unlocked_languages"]
    assert "en" in profile["unlocked_languages"]

    # Configure Google Pro Key for Bengali
    updated = cm.set_google_pro_key("bn", "AIzaSy_BN_PRO_KEY_SECRET_123")
    assert updated["profiles_by_language"]["bn"]["google_pro_key"] == "AIzaSy_BN_PRO_KEY_SECRET_123"
    assert cm.get_google_pro_key("bn") == "AIzaSy_BN_PRO_KEY_SECRET_123"

    # Configure Google Pro Key for English
    cm.set_google_pro_key("en", "AIzaSy_EN_PRO_KEY_SECRET_456")
    assert cm.get_google_pro_key("en") == "AIzaSy_EN_PRO_KEY_SECRET_456"


def test_api_hub_priority_injection(temp_dirs):
    data_dir, _ = temp_dirs
    hub = ApiHub(data_dir=data_dir / "api_matrix")
    hub.config = ApiMatrixConfig(
        google_pro_key="AIzaSy_GLOBAL_PRO_KEY",
        google_pro_keys_by_lang={"bn": "AIzaSy_BN_DEDICATED_PRO_KEY"},
        grok_primary_key="grok_key_sample",
    )

    # 1. LLM Chain: Google Pro research & script must be at index 0
    research_chain = hub.resolve_agent_llm_chain("bn")
    assert len(research_chain) > 0
    assert research_chain[0][0] == "google_pro"
    assert research_chain[0][1] == "AIzaSy_BN_DEDICATED_PRO_KEY"

    # 2. TTS Chain: google_pro_tts must be at index 0
    tts_chain = hub.resolve_tts_chain_for_language("bn")
    assert len(tts_chain) > 0
    assert tts_chain[0][0] == "google_pro_tts"
    assert tts_chain[0][1] == "AIzaSy_BN_DEDICATED_PRO_KEY"

    # 3. Image Generation Chain: google_pro_nano_banana must be at index 0
    img_chain = hub.resolve_image_generation_chain("bn")
    assert len(img_chain) > 0
    assert img_chain[0][0] == "google_pro_nano_banana"
    assert img_chain[0][1] == "AIzaSy_BN_DEDICATED_PRO_KEY"

    # 4. Video Generation Chain: google_pro_veo3 must be at index 0
    vid_chain = hub.resolve_video_generation_chain("bn")
    assert len(vid_chain) > 0
    assert vid_chain[0][0] == "google_pro_veo3"
    assert vid_chain[0][1] == "AIzaSy_BN_DEDICATED_PRO_KEY"


def test_key_quota_guard_pro_bypass():
    guard = KeyQuotaGuard(default_cooldown_seconds=600)
    test_key = "AIzaSy_TEST_PRO_KEY"

    # Mark quota as exhausted for free keys
    guard.mark_exhausted("gemini_free", test_key, "Rate limit exceeded (429)")

    # Standard free key is exhausted
    assert guard.is_available("gemini_free", test_key) is False

    # Google Pro key bypasses free limits
    assert guard.is_available("google_pro_tts", test_key) is True
    assert guard.is_available("google_pro_image", test_key) is True


def test_google_drive_vault_sync_bundling(temp_dirs):
    data_dir, output_dir = temp_dirs
    sync = GoogleDriveVaultSync(data_dir=data_dir, output_dir=output_dir)

    # Save initial config
    cfg = sync.save_config(
        auth_type="service_account",
        credentials='{"type": "service_account", "project_id": "automovie-vault-150gb"}',
        vault_folder_id="AutoMoviePro_Vault",
        target_email="creator@gmail.com",
    )
    assert cfg["is_connected"] is True
    assert cfg["target_email"] == "creator@gmail.com"
    assert cfg["storage_quota_gb"] == 150.0

    # Create dummy video production assets in output_dir
    video_file = output_dir / "vid_test_01.mp4"
    video_file.write_bytes(b"dummy_mp4_master_content" * 100)

    scene_1 = output_dir / "vid_test_01_scene1.mp4"
    scene_1.write_bytes(b"scene1_clip" * 50)

    audio_file = output_dir / "vid_test_01_audio.wav"
    audio_file.write_bytes(b"wav_voice_over" * 40)

    thumb_file = output_dir / "vid_test_01_thumb.png"
    thumb_file.write_bytes(b"png_thumbnail" * 30)

    # Bundle and sync to Google Drive Vault
    entry = sync.bundle_and_sync_video(
        video_id="vid_test_01",
        video_title="Amazing AI Documentary",
        date_str="2026-09-23",
        video_path=video_file,
        scene_paths=[scene_1],
        audio_paths=[audio_file],
        thumb_path=thumb_file,
        metadata={"duration_sec": 65, "resolution": "1080x1920"},
    )

    assert entry["status"] == "success"
    assert entry["vault_folder"] == "/AutoMoviePro_Vault/2026-09-23_Amazing_AI_Documentary/"
    assert "vid_test_01.mp4" in entry["files_uploaded"]
    assert "vid_test_01_scene1.mp4" in entry["files_uploaded"]
    assert "vid_test_01_audio.wav" in entry["files_uploaded"]
    assert "vid_test_01_thumb.png" in entry["files_uploaded"]
    assert "vid_test_01_metadata.json" in entry["files_uploaded"]
    assert entry["total_bytes"] > 0

    # Verify status report reflects the synced video
    st = sync.get_status()
    assert st["is_connected"] is True
    assert st["today_synced_count"] >= 1
    assert st["used_storage_gb"] >= 0.0


def test_api_endpoints():
    client = TestClient(app)

    # 1. POST /api/setup/google-pro-key
    res = client.post("/api/setup/google-pro-key", json={"lang": "bn", "google_pro_key": "AIzaSy_TEST_API_BN"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["language"] == "bn"
    assert data["configured"] is True

    # 2. GET /api/setup/google-pro-key
    res_get = client.get("/api/setup/google-pro-key")
    assert res_get.status_code == 200
    get_data = res_get.json()
    assert get_data["ok"] is True
    assert "bn" in get_data["keys"]
    assert get_data["keys"]["bn"]["configured"] is True

    # 3. POST /api/storage/drive-config
    res_drive = client.post(
        "/api/storage/drive-config",
        json={
            "auth_type": "oauth_token",
            "credentials": "ya29.mock_oauth_token",
            "vault_folder_id": "AutoMoviePro_Vault_Special",
            "target_email": "vip_user@gmail.com",
            "auto_sync_enabled": True,
        },
    )
    assert res_drive.status_code == 200
    drive_data = res_drive.json()
    assert drive_data["ok"] is True
    assert drive_data["config"]["is_connected"] is True
    assert drive_data["config"]["target_email"] == "vip_user@gmail.com"

    # 4. POST /api/storage/sync-now
    res_sync = client.post("/api/storage/sync-now")
    assert res_sync.status_code == 200
    sync_data = res_sync.json()
    assert sync_data["ok"] is True
    assert sync_data["sync_result"]["status"] == "success"

    # 5. GET /api/storage/status
    res_status = client.get("/api/storage/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["ok"] is True
    assert status_data["status"]["is_connected"] is True
    assert status_data["status"]["storage_quota_gb"] == 150.0
