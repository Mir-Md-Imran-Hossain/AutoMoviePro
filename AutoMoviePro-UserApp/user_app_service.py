"""
AutoMovie Pro - UserApp Mobile Engine
Enables subscribers to monitor PC software rendering, review published links,
and remotely solve captchas directly from their smartphone.
"""

import time
import json
import urllib.request
from typing import Dict, Any, List, Optional


class UserAppService:
    """
    Connects with PC software API to stream telemetry and solve challenges.
    """

    def __init__(self, pc_endpoint: str = "http://127.0.0.1:8000"):
        self.pc_endpoint = pc_endpoint.rstrip("/")

    def get_software_status(self) -> Dict[str, Any]:
        """
        Fetches live pipeline health, active channels, and published counts.
        """
        url = f"{self.pc_endpoint}/api/mobile/status"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AutoMoviePro-UserApp/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data
        except Exception as e:
            # Truthful disconnected telemetry - NO fake youtube url, NO fake connected state
            return {
                "ok": False,
                "connected": False,
                "system_state": "disconnected",
                "active_channels": 0,
                "videos_generated_today": 0,
                "videos_published_today": 0,
                "last_published_url": None,
                "last_active_time": None,
                "error": f"পিসি সফটওয়্যারের সাথে সংযোগ বিচ্ছিন্ন: {e}"
            }

    def fetch_pending_captcha(self) -> Optional[Dict[str, Any]]:
        """
        Polls or receives push challenge for remote human-in-the-loop resolution.
        When a captcha is detected on PC, returns the live slider puzzle data.
        """
        url = f"{self.pc_endpoint}/api/mobile/captcha"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AutoMoviePro-UserApp/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data
        except Exception:
            return {"has_captcha": False}

    def submit_remote_solution(self, captcha_id: str, coordinates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatches touch/slider solution back to PC software and triggers real-time upload start.
        """
        url = f"{self.pc_endpoint}/api/mobile/captcha/solve"
        payload = json.dumps({"captcha_id": captcha_id, "coordinates": coordinates}).encode("utf-8")
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "AutoMoviePro-UserApp/1.0"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("ok"):
                    # Activate real-time upload resumption on PC
                    self.resume_realtime_upload(captcha_id)
                return res
        except Exception as e:
            # Disallow fake ok: True on connection failure - return truthful failure
            return {
                "ok": False,
                "captcha_id": captcha_id,
                "solution": coordinates,
                "error": "PC_CONNECTION_FAILED",
                "message": f"পিসি সফটওয়্যারের সাথে সংযোগ ব্যর্থ হয়েছে ({e})। নিশ্চিত করুন যে পিসিতে সফটওয়্যার চালু আছে।"
            }

    def resume_realtime_upload(self, captcha_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Signals PC software to immediately start/unblock upload in real time.
        """
        url = f"{self.pc_endpoint}/api/mobile/upload/resume"
        payload = json.dumps({"captcha_id": captcha_id, "action": "resume_upload", "timestamp": time.time()}).encode("utf-8")
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "AutoMoviePro-UserApp/1.0"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {
                "ok": False,
                "error": "RESUME_SIGNAL_FAILED",
                "message": f"পিসিতে রিয়েল-টাইমে আপলোড চালু করার সিগন্যাল ব্যর্থ: {e}"
            }
