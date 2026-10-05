"""
Multi-account Google Drive rotation for archived assets.

Registry lives in SQLite (drive_accounts + asset_locations).
When active account usage >= 14GB, rotate to next enabled account.

Upload uses google-api-python-client when credentials are present;
otherwise assets stay local with migration_ready=False until configured.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app import db as store
from app.crypto import decrypt_text, encrypt_text

logger = logging.getLogger(__name__)

THRESHOLD_BYTES = 14 * 1024 * 1024 * 1024  # 14 GB


def ensure_drive_tables() -> None:
    with store.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS drive_accounts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT UNIQUE,
              label TEXT,
              credentials_enc TEXT,
              folder_id TEXT,
              bytes_used INTEGER DEFAULT 0,
              bytes_limit INTEGER DEFAULT 16106127360,
              enabled INTEGER DEFAULT 1,
              last_error TEXT,
              created_at TEXT,
              updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS asset_locations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              asset_id TEXT UNIQUE,
              drive_account_id INTEGER,
              drive_email TEXT,
              remote_audio_id TEXT,
              remote_video_id TEXT,
              remote_meta_id TEXT,
              remote_folder_id TEXT,
              local_vault_dir TEXT,
              migration_ready INTEGER DEFAULT 0,
              migrated_local INTEGER DEFAULT 0,
              local_server_path TEXT,
              manifest_json TEXT,
              created_at TEXT,
              updated_at TEXT
            );
            """
        )


def list_drive_accounts() -> List[Dict[str, Any]]:
    ensure_drive_tables()
    with store.db() as conn:
        rows = conn.execute(
            "SELECT id, email, label, folder_id, bytes_used, bytes_limit, enabled, last_error, updated_at "
            "FROM drive_accounts ORDER BY id"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["bytes_used_gb"] = round(int(d.get("bytes_used") or 0) / (1024**3), 2)
        d["near_limit"] = int(d.get("bytes_used") or 0) >= THRESHOLD_BYTES
        d["has_credentials"] = True  # don't leak; UI only needs connected flag
        out.append(d)
    # Mark has_credentials properly
    with store.db() as conn:
        for item in out:
            row = conn.execute(
                "SELECT credentials_enc FROM drive_accounts WHERE id=?", (item["id"],)
            ).fetchone()
            item["has_credentials"] = bool(row and (row["credentials_enc"] or "").strip())
    return out


def upsert_drive_account(
    *,
    email: str,
    credentials_json: str,
    label: str = "",
    folder_id: str = "",
) -> Dict[str, Any]:
    ensure_drive_tables()
    email = (email or "").strip().lower()
    if not email or not (credentials_json or "").strip():
        raise ValueError("email_and_credentials_required")
    enc = encrypt_text(credentials_json.strip())
    now = datetime.now().isoformat()
    with store.db() as conn:
        existing = conn.execute(
            "SELECT id FROM drive_accounts WHERE email=?", (email,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE drive_accounts
                SET credentials_enc=?, label=?, folder_id=COALESCE(NULLIF(?, ''), folder_id),
                    enabled=1, updated_at=?, last_error=''
                WHERE email=?
                """,
                (enc, label or email, folder_id, now, email),
            )
            aid = int(existing["id"])
        else:
            cur = conn.execute(
                """
                INSERT INTO drive_accounts
                  (email, label, credentials_enc, folder_id, bytes_used, bytes_limit, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, 1, ?, ?)
                """,
                (email, label or email, enc, folder_id, THRESHOLD_BYTES + 1024**3, now, now),
            )
            aid = int(cur.lastrowid)
    return {"ok": True, "id": aid, "email": email}


def _load_credentials(account_id: int):
    with store.db() as conn:
        row = conn.execute(
            "SELECT * FROM drive_accounts WHERE id=? AND enabled=1", (account_id,)
        ).fetchone()
    if not row:
        return None, None
    raw = decrypt_text(row["credentials_enc"] or "")
    try:
        data = json.loads(raw)
    except Exception:
        return dict(row), None
    return dict(row), data


def pick_active_account() -> Optional[Dict[str, Any]]:
    """First enabled account under 14GB threshold; else next with room."""
    ensure_drive_tables()
    accounts = list_drive_accounts()
    enabled = [a for a in accounts if a.get("enabled") and a.get("has_credentials")]
    if not enabled:
        return None
    for a in enabled:
        if int(a.get("bytes_used") or 0) < THRESHOLD_BYTES:
            return a
    # all near limit — still return last (caller may warn)
    return enabled[-1]


def refresh_account_usage(account_id: int) -> Dict[str, Any]:
    """Best-effort Drive about.get storageQuota."""
    acc, creds = _load_credentials(account_id)
    if not acc or not creds:
        return {"ok": False, "error": "no_credentials"}
    try:
        from google.oauth2.credentials import Credentials
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        if creds.get("type") == "service_account":
            credentials = service_account.Credentials.from_service_account_info(
                creds, scopes=["https://www.googleapis.com/auth/drive"]
            )
        else:
            credentials = Credentials.from_authorized_user_info(
                creds, scopes=["https://www.googleapis.com/auth/drive.file"]
            )
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        about = service.about().get(fields="storageQuota,user").execute()
        q = about.get("storageQuota") or {}
        used = int(q.get("usage") or q.get("usageInDrive") or 0)
        limit = int(q.get("limit") or (THRESHOLD_BYTES + 1024**3))
        email = ((about.get("user") or {}).get("emailAddress") or acc.get("email") or "").lower()
        with store.db() as conn:
            conn.execute(
                "UPDATE drive_accounts SET bytes_used=?, bytes_limit=?, email=COALESCE(NULLIF(?, ''), email), updated_at=? WHERE id=?",
                (used, limit, email, datetime.now().isoformat(), account_id),
            )
        return {"ok": True, "bytes_used": used, "bytes_limit": limit, "email": email, "near_limit": used >= THRESHOLD_BYTES}
    except Exception as exc:
        logger.warning("Drive usage refresh failed: %s", exc)
        with store.db() as conn:
            conn.execute(
                "UPDATE drive_accounts SET last_error=?, updated_at=? WHERE id=?",
                (str(exc)[:300], datetime.now().isoformat(), account_id),
            )
        return {"ok": False, "error": str(exc)[:300]}


def _upload_file(service, path: Path, folder_id: str, mime: str) -> str:
    from googleapiclient.http import MediaFileUpload

    meta = {"name": path.name}
    if folder_id:
        meta["parents"] = [folder_id]
    media = MediaFileUpload(str(path), mimetype=mime, resumable=True)
    created = (
        service.files()
        .create(body=meta, media_body=media, fields="id", supportsAllDrives=True)
        .execute()
    )
    return str(created.get("id") or "")


def upload_asset_bundle(
    *,
    asset_id: str,
    audio: Path,
    video: Path,
    metadata: Path,
    local_vault_dir: str,
    poster: str = "",
) -> Dict[str, Any]:
    """
    Upload compressed (or raw) modular files to active Drive account.
    Rotates if active account is over threshold.
    """
    ensure_drive_tables()
    active = pick_active_account()
    if not active:
        return {
            "ok": False,
            "skipped": True,
            "reason": "no_drive_account",
            "migration_ready": False,
            "hint": "Connect Google Drive accounts in Settings / see website guide.",
        }

    # Refresh + rotate if needed
    refresh_account_usage(int(active["id"]))
    active = pick_active_account() or active
    if int(active.get("bytes_used") or 0) >= THRESHOLD_BYTES:
        # try next
        accounts = [a for a in list_drive_accounts() if a.get("enabled") and a.get("has_credentials")]
        nxt = next((a for a in accounts if a["id"] != active["id"] and int(a.get("bytes_used") or 0) < THRESHOLD_BYTES), None)
        if nxt:
            logger.info("Drive rotate %s → %s (14GB threshold)", active.get("email"), nxt.get("email"))
            active = nxt
        else:
            return {
                "ok": False,
                "error": "all_accounts_near_14gb",
                "migration_ready": False,
            }

    acc, creds = _load_credentials(int(active["id"]))
    if not creds:
        return {"ok": False, "error": "credentials_unreadable", "migration_ready": False}

    try:
        from google.oauth2.credentials import Credentials
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        if creds.get("type") == "service_account":
            credentials = service_account.Credentials.from_service_account_info(
                creds, scopes=["https://www.googleapis.com/auth/drive"]
            )
        else:
            credentials = Credentials.from_authorized_user_info(
                creds, scopes=["https://www.googleapis.com/auth/drive.file"]
            )
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        folder_id = (acc or {}).get("folder_id") or ""

        audio_id = _upload_file(service, Path(audio), folder_id, "audio/mp4")
        video_id = _upload_file(service, Path(video), folder_id, "video/mp4")
        meta_id = _upload_file(service, Path(metadata), folder_id, "application/json")
        poster_id = ""
        if poster and Path(poster).exists():
            try:
                poster_id = _upload_file(service, Path(poster), folder_id, "image/webp")
            except Exception:
                pass

        size_add = sum(Path(p).stat().st_size for p in (audio, video, metadata) if Path(p).exists())
        now = datetime.now().isoformat()
        manifest = {
            "asset_id": asset_id,
            "drive_email": active.get("email"),
            "drive_account_id": active.get("id"),
            "remote_audio_id": audio_id,
            "remote_video_id": video_id,
            "remote_meta_id": meta_id,
            "remote_poster_id": poster_id,
            "folder_id": folder_id,
            "uploaded_at": now,
        }
        with store.db() as conn:
            conn.execute(
                "UPDATE drive_accounts SET bytes_used=bytes_used+?, updated_at=? WHERE id=?",
                (size_add, now, int(active["id"])),
            )
            conn.execute(
                """
                INSERT INTO asset_locations
                  (asset_id, drive_account_id, drive_email, remote_audio_id, remote_video_id,
                   remote_meta_id, remote_folder_id, local_vault_dir, migration_ready,
                   migrated_local, manifest_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                  drive_account_id=excluded.drive_account_id,
                  drive_email=excluded.drive_email,
                  remote_audio_id=excluded.remote_audio_id,
                  remote_video_id=excluded.remote_video_id,
                  remote_meta_id=excluded.remote_meta_id,
                  remote_folder_id=excluded.remote_folder_id,
                  local_vault_dir=excluded.local_vault_dir,
                  migration_ready=1,
                  manifest_json=excluded.manifest_json,
                  updated_at=excluded.updated_at
                """,
                (
                    asset_id,
                    int(active["id"]),
                    active.get("email"),
                    audio_id,
                    video_id,
                    meta_id,
                    folder_id,
                    local_vault_dir,
                    json.dumps(manifest, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return {"ok": True, "migration_ready": True, **manifest}
    except Exception as exc:
        logger.exception("Drive upload failed")
        return {"ok": False, "error": str(exc)[:300], "migration_ready": False}


def mark_migrated_local(asset_id: str, local_server_path: str) -> None:
    ensure_drive_tables()
    with store.db() as conn:
        conn.execute(
            """
            UPDATE asset_locations
            SET migrated_local=1, local_server_path=?, updated_at=?
            WHERE asset_id=?
            """,
            (local_server_path, datetime.now().isoformat(), asset_id),
        )


def list_migration_ready(limit: int = 100) -> List[Dict[str, Any]]:
    ensure_drive_tables()
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM asset_locations
            WHERE migration_ready=1 AND migrated_local=0
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
