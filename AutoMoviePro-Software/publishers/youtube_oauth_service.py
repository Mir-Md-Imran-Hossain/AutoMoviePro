"""
YouTube Data API v3 - 1-Click Customer Channel OAuth Service
============================================================
Enables customers to connect their personal YouTube channels with 1 click.
Handles:
1. Authorization URL generation with required scopes (youtube.upload, youtube.readonly).
2. Code exchange for access_token and refresh_token.
3. Automated channel profile retrieval (channel_id, channel_title, handle, thumbnail).
4. Secure local encrypted storage via app.crypto.
5. Automated background token refresh so publishing never fails due to expired tokens.
6. Offline test simulation mode.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import httpx

from app import crypto
from app import db as store

logger = logging.getLogger(__name__)

# Official Google OAuth Endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_CHANNELS_API = "https://www.googleapis.com/youtube/v3/channels"

# Required Scopes for Video Publishing and Verification
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

DEFAULT_REDIRECT_URI = "http://localhost:8088/oauth2callback"


class YouTubeOAuthService:
    def __init__(self, *, client_id: str = "", client_secret: str = "", mock_mode: bool = False):
        self.client_id = client_id or "789123456789-automoviepro.apps.googleusercontent.com"
        self.client_secret = client_secret or "GOCSPX-automoviepro_secret"
        self.mock_mode = mock_mode

    def get_authorization_url(
        self,
        *,
        redirect_uri: str = DEFAULT_REDIRECT_URI,
        state: str = "customer_connect",
        prompt: str = "consent",
    ) -> str:
        """Constructs Google OAuth 2.0 authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(YOUTUBE_SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "state": state,
            "prompt": prompt,
        }
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_tokens(
        self,
        code: str,
        *,
        redirect_uri: str = DEFAULT_REDIRECT_URI,
    ) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        if not code:
            raise ValueError("oauth_code_required")

        if self.mock_mode or code.startswith("mock_code_"):
            now = datetime.now()
            expires_at = (now + timedelta(seconds=3600)).isoformat()
            return {
                "ok": True,
                "access_token": f"ya29.mock_access_token_{code[:12]}",
                "refresh_token": f"1//mock_refresh_token_{code[:12]}",
                "expires_in": 3600,
                "expires_at": expires_at,
                "scope": " ".join(YOUTUBE_SCOPES),
                "token_type": "Bearer",
                "mock": True,
            }

        payload = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        try:
            resp = httpx.post(GOOGLE_TOKEN_URL, data=payload, timeout=20.0)
            data = resp.json()
            if resp.status_code != 200 or "access_token" not in data:
                err_msg = data.get("error_description") or data.get("error") or f"HTTP {resp.status_code}"
                raise RuntimeError(f"oauth_token_exchange_failed: {err_msg}")

            expires_in = int(data.get("expires_in") or 3600)
            expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            return {
                "ok": True,
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token") or "",
                "expires_in": expires_in,
                "expires_at": expires_at,
                "scope": data.get("scope") or "",
                "token_type": data.get("token_type") or "Bearer",
                "mock": False,
            }
        except Exception as exc:
            logger.error("OAuth token exchange error: %s", exc)
            raise

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refreshes expired access token using refresh_token."""
        if not refresh_token:
            raise ValueError("refresh_token_required")

        if self.mock_mode or refresh_token.startswith("1//mock_"):
            now = datetime.now()
            expires_at = (now + timedelta(seconds=3600)).isoformat()
            return {
                "ok": True,
                "access_token": f"ya29.mock_refreshed_{now.strftime('%H%M%S')}",
                "expires_in": 3600,
                "expires_at": expires_at,
                "mock": True,
            }

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            resp = httpx.post(GOOGLE_TOKEN_URL, data=payload, timeout=15.0)
            data = resp.json()
            if resp.status_code != 200 or "access_token" not in data:
                err = data.get("error_description") or data.get("error") or f"HTTP {resp.status_code}"
                raise RuntimeError(f"oauth_token_refresh_failed: {err}")

            expires_in = int(data.get("expires_in") or 3600)
            expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            return {
                "ok": True,
                "access_token": data["access_token"],
                "expires_in": expires_in,
                "expires_at": expires_at,
                "mock": False,
            }
        except Exception as exc:
            logger.error("OAuth refresh error: %s", exc)
            raise

    def fetch_channel_profile(self, access_token: str) -> Dict[str, Any]:
        """Queries YouTube Data API to fetch channel title and metadata."""
        if not access_token:
            raise ValueError("access_token_required")

        if self.mock_mode or "mock" in access_token:
            return {
                "ok": True,
                "channel_id": "UC_MOCK_CHANNEL_12345",
                "channel_title": "AutoMovie Creator Channel",
                "custom_url": "@automovie_creator",
                "thumbnail_url": "https://example.invalid/yt_thumb.jpg",
                "video_count": 42,
                "mock": True,
            }

        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"part": "snippet,contentDetails,statistics", "mine": "true"}

        try:
            resp = httpx.get(YOUTUBE_CHANNELS_API, headers=headers, params=params, timeout=15.0)
            data = resp.json()
            items = data.get("items") or []
            if not items:
                raise RuntimeError("no_youtube_channel_found_for_account")

            ch = items[0]
            snippet = ch.get("snippet") or {}
            stats = ch.get("statistics") or {}

            return {
                "ok": True,
                "channel_id": ch.get("id") or "",
                "channel_title": snippet.get("title") or "My YouTube Channel",
                "custom_url": snippet.get("customUrl") or "",
                "thumbnail_url": (snippet.get("thumbnails") or {}).get("default", {}).get("url") or "",
                "video_count": int(stats.get("videoCount") or 0),
                "mock": False,
            }
        except Exception as exc:
            logger.error("Failed to fetch YouTube channel profile: %s", exc)
            raise

    def connect_customer_channel_1click(
        self,
        channel_id: int,
        auth_code_or_tokens: Any,
        *,
        login_id: str = "",
        redirect_uri: str = DEFAULT_REDIRECT_URI,
    ) -> Dict[str, Any]:
        """Full 1-Click integration: exchanges code, fetches profile, and stores encrypted in DB."""
        ensure_youtube_oauth_columns()

        ch = store.get_channel(channel_id)
        if not ch:
            raise ValueError(f"channel_not_found: {channel_id}")

        if login_id:
            owner = str(ch.get("owner_login_id") or "").strip()
            if owner and owner != login_id:
                raise PermissionError("customer_scope_denied")

        if isinstance(auth_code_or_tokens, dict) and "access_token" in auth_code_or_tokens:
            tokens = auth_code_or_tokens
        else:
            code = str(auth_code_or_tokens).strip()
            tokens = self.exchange_code_for_tokens(code, redirect_uri=redirect_uri)

        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token") or ""
        expires_at = tokens.get("expires_at") or (datetime.now() + timedelta(hours=1)).isoformat()

        # Fetch channel profile
        profile = self.fetch_channel_profile(access_token)

        # Encrypt tokens securely
        enc_access = crypto.encrypt_text(access_token)
        enc_refresh = crypto.encrypt_text(refresh_token) if refresh_token else ""

        with store.db() as conn:
            conn.execute(
                """
                UPDATE channels
                SET youtube_oauth_connected = 1,
                    youtube_channel_id = ?,
                    youtube_channel_title = ?,
                    youtube_access_token = ?,
                    youtube_refresh_token = ?,
                    youtube_token_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    profile["channel_id"],
                    profile["channel_title"],
                    enc_access,
                    enc_refresh,
                    expires_at,
                    datetime.now().isoformat(),
                    channel_id,
                ),
            )

        return {
            "ok": True,
            "channel_id": channel_id,
            "youtube_channel_id": profile["channel_id"],
            "youtube_channel_title": profile["channel_title"],
            "connected": True,
            "expires_at": expires_at,
            "token_exposed": False,
        }

    def get_valid_channel_token(self, channel_id: int) -> str:
        """Returns valid access token, auto-refreshing via refresh_token if expired."""
        ensure_youtube_oauth_columns()
        with store.db() as conn:
            row = conn.execute(
                """
                SELECT youtube_oauth_connected, youtube_access_token, youtube_refresh_token, youtube_token_expires_at
                FROM channels WHERE id = ?
                """,
                (channel_id,),
            ).fetchone()

        if not row or not row["youtube_oauth_connected"]:
            raise RuntimeError("youtube_channel_not_oauth_connected")

        enc_access = row["youtube_access_token"] or ""
        enc_refresh = row["youtube_refresh_token"] or ""
        expires_at_str = row["youtube_token_expires_at"] or ""

        access_token = crypto.decrypt_text(enc_access) if enc_access else ""
        refresh_token = crypto.decrypt_text(enc_refresh) if enc_refresh else ""

        is_expired = True
        if expires_at_str:
            try:
                exp_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00").split("+")[0])
                # Consider expired if within 4 minutes of expiry
                if datetime.now() + timedelta(minutes=4) < exp_dt:
                    is_expired = False
            except Exception:
                is_expired = True

        if not is_expired and access_token:
            return access_token

        # Needs refresh
        if not refresh_token:
            if access_token and not is_expired:
                return access_token
            raise RuntimeError("youtube_oauth_refresh_token_missing — please reconnect channel")

        logger.info("Auto-refreshing expired YouTube OAuth token for channel %s...", channel_id)
        refreshed = self.refresh_access_token(refresh_token)
        new_access = refreshed["access_token"]
        new_expires_at = refreshed["expires_at"]

        with store.db() as conn:
            conn.execute(
                """
                UPDATE channels
                SET youtube_access_token = ?,
                    youtube_token_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    crypto.encrypt_text(new_access),
                    new_expires_at,
                    datetime.now().isoformat(),
                    channel_id,
                ),
            )

        return new_access


def ensure_youtube_oauth_columns() -> None:
    """Soft migration: ensure YouTube OAuth columns exist in channels table."""
    with store.db() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(channels)").fetchall()}
        columns_to_add = [
            ("youtube_oauth_connected", "INTEGER DEFAULT 0"),
            ("youtube_channel_id", "TEXT"),
            ("youtube_channel_title", "TEXT"),
            ("youtube_access_token", "TEXT"),
            ("youtube_refresh_token", "TEXT"),
            ("youtube_token_expires_at", "TEXT"),
            ("product_tier", "TEXT"),
        ]
        for col_name, col_type in columns_to_add:
            if col_name not in cols:
                conn.execute(f"ALTER TABLE channels ADD COLUMN {col_name} {col_type}")
