from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.config import settings


class LicenseClient:
    """Desktop app ↔ automoviepro.com license/subscription gateway."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = self._normalize_base(base_url or settings.api_base_url)
        self.token = token

    @staticmethod
    def _normalize_base(url: str) -> str:
        u = (url or "").strip().rstrip("/")
        if u.lower().startswith("http://") and "automoviepro.com" in u.lower():
            u = "https://" + u[7:]
        return u

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _offline(self) -> bool:
        base = (self.base_url or "").lower().rstrip("/")
        return base in {"", "local", "localhost", "offline"} or "127.0.0.1" in base

    def _parse(self, r: httpx.Response) -> Dict[str, Any]:
        try:
            data = r.json()
        except Exception:
            snippet = (r.text or "")[:180].replace("\n", " ")
            raise RuntimeError(f"non_json_{r.status_code}:{snippet}")
        if not isinstance(data, dict):
            raise RuntimeError("invalid_json_object")
        return data

    def _client(self, timeout: float, follow: bool = False) -> httpx.Client:
        return httpx.Client(timeout=timeout, follow_redirects=follow)

    def _get(self, path: str, timeout: float = 20.0) -> Dict[str, Any]:
        params: Dict[str, str] = {}
        if self.token:
            params["token"] = self.token
        with self._client(timeout, follow=True) as client:
            r = client.get(f"{self.base_url}{path}", headers=self._headers(), params=params)
            return self._parse(r)

    def _post(self, path: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Dict[str, Any]:
        body = dict(payload or {})
        if self.token:
            body.setdefault("token", self.token)
        with self._client(timeout, follow=False) as client:
            r = client.post(f"{self.base_url}{path}", json=body, headers=self._headers())
            return self._parse(r)

    def login(self, login_id: str, password: str, hwid: Optional[str] = None) -> Dict[str, Any]:
        if not hwid:
            try:
                from app.auth.hardware_id import get_hardware_fingerprint
                hwid = get_hardware_fingerprint()
            except Exception:
                hwid = ""
        payload = {"login_id": login_id, "password": password}
        if hwid:
            payload["hardware_id"] = hwid
        data = self._post("/api/login.php", payload, timeout=30.0)
        if not data.get("ok"):
            err = data.get("error") or "login_failed"
            msg = data.get("message") or err
            raise RuntimeError(f"{err}:{msg}")
        self.token = str(data.get("token") or "")
        if not self.token:
            raise RuntimeError("token_missing")
        return data

    def me(self) -> Dict[str, Any]:
        data = self._get("/api/me.php")
        if not data.get("ok"):
            raise RuntimeError(data.get("error") or "me_failed")
        return data

    def heartbeat(self, hwid: Optional[str] = None) -> Dict[str, Any]:
        if self._offline():
            return {"ok": True, "offline": True}
        if not hwid:
            try:
                from app.auth.hardware_id import get_hardware_fingerprint
                hwid = get_hardware_fingerprint()
            except Exception:
                hwid = ""
        payload = {}
        if hwid:
            payload["hardware_id"] = hwid
        data = self._post("/api/heartbeat.php", payload)
        if data.get("blocked"):
            err = data.get("error") or "account_blocked"
            msg = data.get("message") or "অ্যাকাউন্ট ব্লক করা হয়েছে।"
            raise RuntimeError(f"ACCOUNT_BLOCKED:{err}:{msg}")
        return data

    def request_password_otp(self, login_id_or_email: str) -> Dict[str, Any]:
        key = "email" if "@" in login_id_or_email else "login_id"
        data = self._post("/api/request_otp.php", {key: login_id_or_email}, timeout=20.0)
        if not data.get("ok"):
            raise RuntimeError(data.get("message") or data.get("error") or "otp_request_failed")
        return data

    def reset_password_with_otp(self, login_id_or_email: str, otp: str, new_password: str) -> Dict[str, Any]:
        key = "email" if "@" in login_id_or_email else "login_id"
        payload = {key: login_id_or_email, "otp": otp, "new_password": new_password}
        data = self._post("/api/reset_password.php", payload, timeout=25.0)
        if not data.get("ok"):
            raise RuntimeError(data.get("message") or data.get("error") or "password_reset_failed")
        return data

    def promo_links(self) -> List[Dict[str, Any]]:
        if self._offline():
            return []
        try:
            data = self._get("/api/promo-links.php")
        except Exception:
            return []
        if not data.get("ok"):
            return []
        return list(data.get("links") or [])

    def peer_videos(self, limit: int = 40) -> List[Dict[str, Any]]:
        """Other customers' uploaded YouTube/Facebook videos (trust-browse feed)."""
        if self._offline():
            return []
        try:
            data = self._get(f"/api/peer-videos.php?limit={int(limit)}")
        except Exception:
            return []
        if not data.get("ok"):
            return []
        return list(data.get("videos") or data.get("items") or [])

    def sync_engage_log(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._offline():
            return {"ok": True, "offline": True, "synced": 0}
        return self._post("/api/engage-log-sync.php", payload)

    def sync_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._offline():
            return {"ok": True, "offline": True}
        return self._post("/api/jobs-sync.php", payload)

    def language_status(self) -> Dict[str, Any]:
        if self._offline():
            return {"ok": True, "unlocked": ["en"], "offline": True}
        return self._get("/api/language-status.php")

    def language_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._offline():
            return {"ok": False, "error": "offline"}
        return self._post("/api/language-request.php", payload)

    def escalate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._offline():
            return {"ok": False, "error": "offline"}
        return self._post("/api/agent-escalate.php", payload)

    def health(self) -> Dict[str, Any]:
        if self._offline():
            return {"ok": True, "offline": True}
        with self._client(15.0, follow=True) as client:
            r = client.get(f"{self.base_url}/api/health.php")
            return self._parse(r)
