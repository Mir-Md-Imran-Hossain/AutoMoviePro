"""
=============================================================================
OmniSocial AI Telemetry Engine - Micro-Action & Human Simulator Tracker
=============================================================================
Thread-safe, high-frequency JSON-backed event logging for:
- Mouse micro-movements, Bezier curve offsets, click coordinates
- Keyboard human-typing pauses, WPM variations
- Browser feed scrolling (wheel delta, viewport offset)
- Image OCR detection & target bounding boxes
- Network state, posting pipeline stages
- Real-time viewport frame capture for mini-screen live viewer
"""

import json
import time
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from omni_social_hub import atomic_write_json

TELEMETRY_FILE = Path(r"E:\AI Assistant\Social Media Hub\live_telemetry.json")
STATE_FILE = Path(r"E:\AI Assistant\Social Media Hub\master_schedule_state.json")
FRAME_FILE = Path(r"E:\AI Assistant\Social Media Hub\live_view_frame.png")
HUB_DIR = Path(r"E:\AI Assistant\Social Media Hub")
AUTOMATIONS_DIR = Path(r"E:\AI Assistant\Automations")

class OmniTelemetry:
    @staticmethod
    def capture_frame(page):
        """Captures a lightweight preview frame for the HUD mini screen viewer."""
        try:
            page.screenshot(path=str(FRAME_FILE), quality=50, type="jpeg")
        except Exception:
            try:
                page.screenshot(path=str(FRAME_FILE))
            except Exception:
                pass

    @staticmethod
    def clean_screenshot_artifacts(max_age_hours: float = 24.0, keep_proofs: int = 5) -> Dict[str, int]:
        """
        Intelligent Screenshot Garbage Collection:
        - Keeps only the latest live_view_frame.png for live stream.
        - Prunes temporary/ephemeral debug screenshots older than 24 hours.
        - Retains only the last `keep_proofs` (default 5) verified proof screenshots per entity.
        """
        now = time.time()
        age_threshold = max_age_hours * 3600
        pruned_debug = 0
        pruned_proofs = 0

        search_dirs = [HUB_DIR, AUTOMATIONS_DIR]
        profiles_dir = HUB_DIR / "Profiles"
        if profiles_dir.exists():
            for p_dir in profiles_dir.iterdir():
                if p_dir.is_dir():
                    search_dirs.append(p_dir)
                    search_dirs.append(p_dir / "assets")
                    search_dirs.append(p_dir / "generated_posts")

        debug_patterns = ["*temp*.png", "*debug*.png", "*snap*.png", "*test*.png", "*stealth_proof*.png", "*screen*.png"]
        proof_patterns = ["*verified_proof*.png", "*final_proof*.png", "*proof*.png"]

        # 1. Prune stale ephemeral debug screenshots > 24 hours
        for d in search_dirs:
            if not d.exists():
                continue
            for pat in debug_patterns:
                for img_path in d.glob(pat):
                    if img_path.name == "live_view_frame.png":
                        continue
                    try:
                        mtime = img_path.stat().st_mtime
                        if now - mtime > age_threshold:
                            img_path.unlink()
                            pruned_debug += 1
                    except Exception:
                        pass

        # 2. Retain only last `keep_proofs` for proofs in each directory
        for d in search_dirs:
            if not d.exists():
                continue
            found_proofs = []
            for pat in proof_patterns:
                for img_path in d.glob(pat):
                    if img_path.name == "live_view_frame.png":
                        continue
                    try:
                        found_proofs.append((img_path, img_path.stat().st_mtime))
                    except Exception:
                        pass
            
            # Sort newest first
            found_proofs.sort(key=lambda x: x[1], reverse=True)
            if len(found_proofs) > keep_proofs:
                for img_path, _ in found_proofs[keep_proofs:]:
                    try:
                        img_path.unlink()
                        pruned_proofs += 1
                    except Exception:
                        pass

        return {"pruned_debug": pruned_debug, "pruned_proofs": pruned_proofs}

    @staticmethod
    def log_micro_action(
        entity_id: str,
        stage: str,
        action_title: str,
        details: str,
        mouse_coords: tuple = None,
        keyboard_stats: str = "",
        scroll_delta: int = 0,
        page = None
    ):
        """Broadcasts real-time micro-action for the HUD and Agent streams with atomic writes."""
        now_ts = time.time()
        now_str = datetime.now().strftime("%I:%M:%S %p")
        
        # If active page given, capture live frame
        if page:
            OmniTelemetry.capture_frame(page)
        
        telemetry_entry = {
            "timestamp": now_ts,
            "time_str": now_str,
            "entity_id": entity_id,
            "stage": stage,
            "action_title": action_title,
            "details": details,
            "mouse_coords": mouse_coords,
            "keyboard_stats": keyboard_stats,
            "scroll_delta": scroll_delta
        }
        
        # 1. Update live_telemetry.json atomically (keeps last 30 micro events)
        try:
            history = []
            if TELEMETRY_FILE.exists():
                try:
                    with open(TELEMETRY_FILE, "r", encoding="utf-8") as f:
                        history = json.load(f)
                        if not isinstance(history, list):
                            history = []
                except Exception:
                    history = []
            
            history.append(telemetry_entry)
            if len(history) > 30:
                history = history[-30:]
                
            atomic_write_json(TELEMETRY_FILE, history)
        except Exception:
            pass

        # 2. Update master_schedule_state.json atomically
        try:
            cur_state = {}
            if STATE_FILE.exists():
                try:
                    with open(STATE_FILE, "r", encoding="utf-8") as f:
                        cur_state = json.load(f)
                except Exception:
                    cur_state = {}
                    
            is_live = (stage not in ["IDLE", "STANDBY", "SLEEP", "COMPLETED", "RETRY_WAIT"])
            
            # Record live session start epoch when transitioning to live
            if is_live:
                if not cur_state.get("is_live_active") or not cur_state.get("live_session_start_epoch"):
                    cur_state["live_session_start_epoch"] = now_ts
            else:
                cur_state["live_session_start_epoch"] = None

            cur_state["last_updated"] = datetime.now().isoformat()
            cur_state["current_entity"] = entity_id
            cur_state["current_action"] = action_title
            cur_state["details"] = details
            cur_state["is_live_active"] = is_live
            cur_state["micro_details"] = {
                "mouse": mouse_coords,
                "keyboard": keyboard_stats,
                "scroll": scroll_delta,
                "stage": stage
            }
            
            atomic_write_json(STATE_FILE, cur_state)
        except Exception:
            pass
            
        print(f"[{now_str}] [{entity_id}] [{stage}] {action_title} -> {details}", flush=True)

# Helper function
def log_step(entity_id: str, stage: str, title: str, details: str, mouse=None, kb="", scroll=0, page=None):
    OmniTelemetry.log_micro_action(entity_id, stage, title, details, mouse, kb, scroll, page)

