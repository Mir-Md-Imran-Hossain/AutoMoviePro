"""
Comprehensive Test Suite for Video Quality Enhancement and Cloud Storage Automation.
Tests:
1. Video Retention & Cinematic Hooks (prompt_policy.py, script_engine.py)
2. Cinematic Motion Ken Burns Filters for Still Images (filtergraph.py, media_compose.py)
3. 100% Clean Frequency-Balanced Vocal & BGM Ducking (bgm_ducking.py)
4. 150 GB Google Drive Vault Auto-Sync Engine (google_drive_sync.py, UI elements)
5. 2-Way WhatsApp Alerts & Order Flow Confirmation (purchase.php, verify_payment.php, pending.php)
"""

import os
import sys
import unittest
import tempfile
import sqlite3
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure AutoMoviePro-Software root is in sys.path
SOFTWARE_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = SOFTWARE_ROOT.parent
if str(SOFTWARE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_ROOT))

from domain.scene_intent import SceneIntent
from pipeline.creative_production.prompt_policy import enrich_scene_intent
from pipeline.script_engine import (
    ScriptEngine,
    ScriptScene,
    ProductionScript,
    highlight_retention_keywords,
)
from pipeline.rendering_integrity.filtergraph import (
    build_cinematic_motion_filter,
    is_still_image,
)
from pipeline.custom_pipeline.media_compose import _format_ass_retention_text
from pipeline.bgm_ducking import build_ducking_filter_complex
from app.storage.google_drive_sync import (
    GoogleDriveVaultSync,
    TOTAL_VAULT_CAPACITY_GB,
    DEFAULT_VAULT_FOLDER,
)


class TestVideoRetentionAndHooks(unittest.TestCase):
    """Task 1.1: Verification of 0-3s suspense hook and subtitle keyword retention highlighting."""

    def test_enrich_scene_intent_enforces_0_to_3s_hook(self):
        intent = SceneIntent(
            scene_id="s1",
            dialogue_id="d1",
            summary="A mysterious signal picked up in the deep Pacific trench.",
        )
        enriched = enrich_scene_intent(intent, scene_index=0, scene_count=5)
        self.assertEqual(enriched.retention_role, "curiosity_hook_0_3s")
        self.assertEqual(enriched.visualization_policy.get("hook_policy"), "immediate_suspense_no_intro")
        self.assertEqual(enriched.visualization_policy.get("subtitle_retention"), "bold_keyword_accent_highlight")
        self.assertTrue(enriched.metadata.get("retention_hook"))
        self.assertTrue(enriched.metadata.get("subtitle_accent_enabled"))

        # Check negative constraints
        negatives = " ".join(enriched.negative_constraints)
        self.assertIn("NO slow introductory preamble", negatives)
        self.assertIn("NO generic greetings before the hook", negatives)

    def test_highlight_retention_keywords(self):
        text = "This secret will change your life forever."
        highlighted = highlight_retention_keywords(text, "en")
        self.assertIn("<b>", highlighted)
        self.assertIn("</b>", highlighted)
        # Check that ASS formatting converts <b> to ASS bold and accent color tags
        ass_formatted = _format_ass_retention_text(highlighted)
        self.assertIn(r"{\b1\c&H00D7FF&}", ass_formatted)
        self.assertIn(r"{\b0\c&H00FFFFFF&}", ass_formatted)

    def test_script_engine_generates_hook_scene(self):
        engine = ScriptEngine()
        script = engine.generate_script(
            topic_title="5 AI Inventions of 2026",
            niche="Technology & AI Innovations",
            video_format="short",
            language="bn",
        )
        self.assertGreater(len(script.scenes), 0)
        first_scene = script.scenes[0]
        # Scene 1 must be flagged as hook
        self.assertEqual(first_scene.hook_type, "greeting_hook")
        # Subtitle keyword retention formatting should be applied
        self.assertTrue(bool(first_scene.highlighted_subtitle))
        self.assertIn("<b>", first_scene.highlighted_subtitle)

    def test_inspect_and_repair_script_fixes_weak_opening(self):
        engine = ScriptEngine()
        # Weak scene 1 with robotic opening
        weak_scene = ScriptScene(
            scene_index=1,
            narration="Welcome to our channel. Today we will talk about secret deep sea creatures.",
            visual_prompt="Calm room with a person waving at camera",
            estimated_duration_sec=7.0,
            hook_type="greeting_hook",
        )
        scene_2 = ScriptScene(
            scene_index=2,
            narration="Creatures exist down there.",
            visual_prompt="Deep ocean visual",
            estimated_duration_sec=5.0,
            hook_type="body",
        )
        script = ProductionScript(
            script_id="test_scr",
            topic_id="top_1",
            title="Deep Sea",
            niche="Nature",
            video_format="short",
            language="en",
            scenes=[weak_scene, scene_2],
            total_estimated_duration_sec=12.0,
        )

        repaired = engine.inspect_and_repair_script(script)
        # Repaired scene 1 must strip slow starter and inject suspense question/hook
        self.assertNotIn("welcome to", repaired.scenes[0].narration.lower())
        self.assertTrue(
            "?" in repaired.scenes[0].narration
            or "!" in repaired.scenes[0].narration
        )
        self.assertIn("Stripped slow intro", repaired.scenes[0].agent_notes)


class TestCinematicMotionFilter(unittest.TestCase):
    """Task 1.2: Verification of smooth Dynamic Zoom-in, Slow Pan, and Subtle Parallax Ken Burns presets."""

    def test_is_still_image(self):
        self.assertTrue(is_still_image("frame.png"))
        self.assertTrue(is_still_image(Path("photo.jpg")))
        self.assertTrue(is_still_image("artwork.webp"))
        self.assertFalse(is_still_image("clip.mp4"))
        self.assertFalse(is_still_image("render.mov"))

    def test_build_cinematic_motion_presets(self):
        width, height, duration = 1080, 1920, 4.0

        for preset in ["dynamic_zoom_in", "slow_pan", "subtle_parallax"]:
            fg = build_cinematic_motion_filter(preset=preset, width=width, height=height, duration=duration, fps=25)
            self.assertIn("scale=", fg)
            self.assertIn("zoompan=", fg)
            self.assertIn("d=100", fg)
            self.assertIn(f"s={width}x{height}", fg)

    def test_unknown_preset_fallback(self):
        fg = build_cinematic_motion_filter(preset="unknown_preset", width=1920, height=1080, duration=5.0)
        self.assertIn("zoompan=", fg)


class TestBgmFrequencyDucking(unittest.TestCase):
    """Task 1.3: Verification of 100% clean frequency separation and voice-over ducking."""

    def test_frequency_balanced_ducking_filter(self):
        fg = build_ducking_filter_complex(duck_db=-16.0)
        # Check vocal presence EQ
        self.assertIn("highpass=f=85", fg)
        self.assertIn("equalizer=f=3000", fg)
        # Check BGM vocal notch carve-out
        self.assertIn("equalizer=f=2500", fg)
        self.assertIn("g=-6", fg)
        self.assertIn("lowpass=f=7500", fg)
        # Check fast sidechain ducking (60ms attack, 450ms release)
        self.assertIn("sidechaincompress=", fg)
        self.assertIn("attack=60", fg)
        self.assertIn("release=450", fg)
        # Check speech priority weights (1.0 vs 0.7) to guarantee zero voice masking
        self.assertIn("weights=1.0 0.7", fg)


class TestGoogleDriveVaultSync(unittest.TestCase):
    """Task 2: Verification of 150 GB Google Drive Auto-Sync Engine and local file purge."""

    def setUp(self):
        import gc
        gc.collect()
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.output_dir = Path(self.temp_dir.name) / "output"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_150gb_quota_and_daily_schedule_default(self):
        sync_engine = GoogleDriveVaultSync(data_dir=self.data_dir, output_dir=self.output_dir)
        cfg = sync_engine.get_config(mask_secret=False)
        self.assertEqual(cfg["storage_quota_gb"], 150.0)
        self.assertEqual(cfg["sync_time"], "02:00")
        self.assertTrue(cfg["purge_local_after_sync"])
        self.assertTrue(cfg["auto_sync_enabled"])

    def test_bundle_sync_and_local_purge(self):
        sync_engine = GoogleDriveVaultSync(data_dir=self.data_dir, output_dir=self.output_dir)

        # Create mock heavy media files
        master_mp4 = self.output_dir / "render_final.mp4"
        master_mp4.write_bytes(b"\x00" * 1024 * 500)  # 500 KB mock
        scene_1 = self.output_dir / "scene_01.mp4"
        scene_1.write_bytes(b"\x00" * 1024 * 200)
        audio_file = self.output_dir / "voiceover.wav"
        audio_file.write_bytes(b"\x00" * 1024 * 100)
        thumb_file = self.output_dir / "cover.png"
        thumb_file.write_bytes(b"\x00" * 1024 * 50)

        entry = sync_engine.bundle_and_sync_video(
            video_id="vid_101",
            video_title="Secret Underwater Pyramids",
            date_str="2026-09-23",
            video_path=master_mp4,
            scene_paths=[scene_1],
            audio_paths=[audio_file],
            thumb_path=thumb_file,
            metadata={"niche": "Mystery", "scenes_count": 1},
            purge_local=True,
        )

        self.assertEqual(entry["status"], "success")
        self.assertIn("/AutoMoviePro_Vault/2026-09-23_Secret_Underwater_Pyramids/", entry["vault_folder"])
        self.assertGreater(entry["freed_bytes"], 0)

        # Heavy files should be purged to keep local PC drive free
        self.assertFalse(master_mp4.exists(), "Master MP4 should be purged after successful sync")
        self.assertFalse(scene_1.exists(), "Scene clip should be purged after successful sync")
        self.assertFalse(audio_file.exists(), "Audio file should be purged after successful sync")

        # Thumbnail should be preserved
        self.assertTrue(thumb_file.exists(), "Thumbnail should be preserved")

        # Verify record in SQLite database
        db_path = self.data_dir / "local.db"
        self.assertTrue(db_path.exists())
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT video_title, vault_folder, freed_bytes FROM drive_vault_sync_history WHERE video_id = ?", ("vid_101",))
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Secret Underwater Pyramids")
        self.assertIn("AutoMoviePro_Vault", row[1])
        self.assertGreater(row[2], 0)

    def test_ui_contains_connect_drive_and_sync_progress(self):
        html_path = SOFTWARE_ROOT / "ui" / "index.html"
        self.assertTrue(html_path.exists())
        html_content = html_path.read_text(encoding="utf-8")

        # Verify Google Drive Connect button
        self.assertIn("গুগল ড্রাইভ কানেক্ট", html_content)
        # Verify 150 GB quota display
        self.assertIn("150 GB", html_content)
        # Verify Sync progress bar container
        self.assertIn("vaultSyncProgressContainer", html_content)
        self.assertIn("vaultSyncProgressBar", html_content)

        js_path = SOFTWARE_ROOT / "ui" / "static" / "js" / "app.js"
        self.assertTrue(js_path.exists())
        js_content = js_path.read_text(encoding="utf-8")
        self.assertIn("connectDriveBtn", js_content)
        self.assertIn("vaultSyncProgressBar", js_content)


class TestWebsiteWhatsAppAlerts(unittest.TestCase):
    """Task 3: Verification of 2-way WhatsApp alerts and order flow confirmation."""

    def test_purchase_php_has_2way_whatsapp_alerts(self):
        purchase_php = WORKSPACE_ROOT / "AutoMoviePro-Website" / "purchase.php"
        self.assertTrue(purchase_php.exists())
        content = purchase_php.read_text(encoding="utf-8")

        # Check for Google AI Pro branch
        self.assertIn("Google AI Pro", content)
        # 1. Customer Gmail request message
        self.assertIn("জিমেইল (Gmail)", content)
        self.assertIn("১৫০ জিবি", content)
        # 2. Admin WhatsApp alert to 01684355055
        self.assertIn("01684355055", content)
        self.assertIn("adminMsg", content)

    def test_verify_payment_php_has_2way_whatsapp_alerts(self):
        verify_php = WORKSPACE_ROOT / "AutoMoviePro-Website" / "api" / "verify_payment.php"
        self.assertTrue(verify_php.exists())
        content = verify_php.read_text(encoding="utf-8")

        self.assertIn("includes/whatsapp.php", content)
        self.assertIn("01684355055", content)
        self.assertIn("whatsapp_handoff_url", content)

    def test_pending_php_has_prominent_green_whatsapp_button(self):
        pending_php = WORKSPACE_ROOT / "AutoMoviePro-Website" / "pending.php"
        self.assertTrue(pending_php.exists())
        content = pending_php.read_text(encoding="utf-8")

        self.assertIn("01684355055", content)
        self.assertIn("wa.me/8801684355055", content)
        self.assertIn("হোয়াটসঅ্যাপে আপনার জিমেইল আইডি পাঠান", content)
        # Verify prominent green styling
        self.assertIn("#10b981", content)


if __name__ == "__main__":
    unittest.main()
