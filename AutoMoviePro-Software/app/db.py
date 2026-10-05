from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from app.config import DATA_DIR
from app.crypto import decrypt_text, encrypt_text

DB_PATH = DATA_DIR / "local.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS session (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              login_id TEXT,
              token TEXT,
              customer_json TEXT,
              api_base_url TEXT,
              updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS channels (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              youtube_name TEXT,
              facebook_name TEXT,
              niche TEXT,
              niche_id INTEGER,
              video_special TEXT,
              long_upload_time TEXT,
              short_upload_time TEXT,
              example_script TEXT,
              generation_special TEXT,
              title_desc_special TEXT,
              logo_path TEXT,
              intro_path TEXT,
              google_api_1 TEXT,
              google_api_2 TEXT,
              agnes_api TEXT,
              pollinations_api TEXT,
              pexels_api TEXT,
              tiktok_name TEXT,
              tiktok_session TEXT,
              youtube_session TEXT,
              facebook_session TEXT,
              enabled INTEGER DEFAULT 1,
              created_at TEXT,
              updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel_id INTEGER,
              video_type TEXT,
              title TEXT,
              description TEXT,
              tags TEXT,
              local_path TEXT,
              platform TEXT,
              upload_status TEXT,
              remote_url TEXT,
              error TEXT,
              created_at TEXT,
              uploaded_at TEXT
            );

            CREATE TABLE IF NOT EXISTS engage_state (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              platform TEXT,
              url TEXT,
              action TEXT,
              done_at TEXT
            );

            CREATE TABLE IF NOT EXISTS app_meta (
              key TEXT PRIMARY KEY,
              value TEXT
            );

            CREATE TABLE IF NOT EXISTS language_requests (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel_id INTEGER,
              lang_code TEXT NOT NULL,
              amount TEXT,
              payment_ref TEXT,
              payment_note TEXT,
              status TEXT NOT NULL DEFAULT 'pending',
              remote_id INTEGER,
              created_at TEXT,
              updated_at TEXT,
              approved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_escalations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              customer_login TEXT,
              message TEXT,
              reason TEXT,
              screenshot_note TEXT,
              activity_hint TEXT,
              status TEXT NOT NULL DEFAULT 'open',
              remote_ok INTEGER DEFAULT 0,
              created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS google_pro_orders (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              order_id TEXT UNIQUE,
              plan_id TEXT,
              plan_name TEXT,
              duration_months INTEGER,
              price INTEGER,
              target_email TEXT,
              whatsapp TEXT,
              trx_id TEXT,
              note TEXT,
              status TEXT NOT NULL DEFAULT 'pending',
              created_at TEXT,
              approved_at TEXT
            );
            """
        )
        # Soft migrations for existing DBs
        cols = {r[1] for r in conn.execute("PRAGMA table_info(channels)").fetchall()}
        if "niche_id" not in cols:
            conn.execute("ALTER TABLE channels ADD COLUMN niche_id INTEGER")
        if "api_keys_json" not in cols:
            conn.execute("ALTER TABLE channels ADD COLUMN api_keys_json TEXT")
        if "pollinations_api" not in cols:
            conn.execute("ALTER TABLE channels ADD COLUMN pollinations_api TEXT")
        if "languages_json" not in cols:
            conn.execute("ALTER TABLE channels ADD COLUMN languages_json TEXT")
        if "lang_destinations_json" not in cols:
            conn.execute("ALTER TABLE channels ADD COLUMN lang_destinations_json TEXT")
        if "tiktok_name" not in cols:
            conn.execute("ALTER TABLE channels ADD COLUMN tiktok_name TEXT")
        if "tiktok_session" not in cols:
            conn.execute("ALTER TABLE channels ADD COLUMN tiktok_session TEXT")

        job_cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "lang_code" not in job_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN lang_code TEXT DEFAULT 'en'")
        if "thumbnail_path" not in job_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN thumbnail_path TEXT")
        if "package_path" not in job_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN package_path TEXT")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS posts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              job_id INTEGER,
              channel_id INTEGER,
              lang_code TEXT DEFAULT 'en',
              platform TEXT,
              title TEXT,
              remote_url TEXT,
              local_path TEXT,
              views INTEGER DEFAULT 0,
              likes INTEGER DEFAULT 0,
              comments INTEGER DEFAULT 0,
              shares INTEGER DEFAULT 0,
              reach INTEGER DEFAULT 0,
              stats_json TEXT,
              created_at TEXT,
              updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS post_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              post_id INTEGER,
              platform TEXT,
              author TEXT,
              message TEXT,
              reply TEXT,
              lang_code TEXT,
              created_at TEXT
            );

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

            CREATE TABLE IF NOT EXISTS error_notebook (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              fingerprint TEXT UNIQUE,
              subsystem TEXT,
              fault_code TEXT,
              message TEXT,
              severity TEXT DEFAULT 'warn',
              job_id INTEGER,
              channel_id INTEGER,
              scene_idx INTEGER,
              context_json TEXT,
              count INTEGER DEFAULT 1,
              status TEXT DEFAULT 'open',
              owner_note TEXT,
              first_seen TEXT,
              last_seen TEXT
            );
            """
        )
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS engage_activity (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              day TEXT NOT NULL,
              platform TEXT,
              action TEXT,
              url TEXT,
              title TEXT,
              detail TEXT,
              ok INTEGER DEFAULT 1,
              meta_json TEXT,
              synced INTEGER DEFAULT 0,
              created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS app_settings (
              key TEXT PRIMARY KEY,
              value TEXT,
              updated_at TEXT
            );
            """
        )


def get_app_setting(key: str, default: str = "") -> str:
    try:
        with db() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else default
    except Exception:
        return default


def set_app_setting(key: str, value: str) -> None:
    now = datetime.utcnow().isoformat()
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO app_settings(key, value, updated_at) VALUES(?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, str(value), now),
            )
    except Exception:
        pass


def add_engage_activity(
    *,
    platform: str,
    action: str,
    url: str = "",
    title: str = "",
    detail: str = "",
    ok: bool = True,
    meta: Optional[Dict[str, Any]] = None,
    day: str = "",
) -> int:
    day = day or datetime.now().date().isoformat()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO engage_activity
              (day, platform, action, url, title, detail, ok, meta_json, synced, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                day,
                platform,
                action,
                url,
                title,
                detail,
                1 if ok else 0,
                json.dumps(meta or {}, ensure_ascii=False) if meta else None,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return int(cur.lastrowid)


def list_engage_activity(*, day: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    with db() as conn:
        if day:
            rows = conn.execute(
                "SELECT * FROM engage_activity WHERE day=? ORDER BY id DESC LIMIT ?",
                (day, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM engage_activity ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def list_engage_activity_unsynced(limit: int = 80) -> List[Dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM engage_activity WHERE synced=0 ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_engage_activity_synced(ids: List[int]) -> None:
    if not ids:
        return
    with db() as conn:
        conn.executemany(
            "UPDATE engage_activity SET synced=1 WHERE id=?",
            [(int(i),) for i in ids],
        )


def save_session(login_id: str, token: str, customer: Dict[str, Any], api_base: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM session")
        conn.execute(
            """
            INSERT INTO session (id, login_id, token, customer_json, api_base_url, updated_at)
            VALUES (1, ?, ?, ?, ?, ?)
            """,
            (login_id, token, json.dumps(customer), api_base, datetime.now().isoformat()),
        )


def get_session() -> Optional[Dict[str, Any]]:
    with db() as conn:
        row = conn.execute("SELECT * FROM session WHERE id = 1").fetchone()
        if not row:
            return None
        keys = set(row.keys())
        out: Dict[str, Any] = {
            "login_id": row["login_id"],
            "token": row["token"],
            "customer": json.loads(row["customer_json"] or "{}"),
            "api_base_url": row["api_base_url"],
            "updated_at": row["updated_at"],
        }
        # C02 soft-migrated columns (present after ensure_session_columns)
        for col in ("expires_at", "account_state", "entitlement_state", "auth_mode"):
            if col in keys:
                out[col] = row[col]
        return out


def clear_session() -> None:
    with db() as conn:
        conn.execute("DELETE FROM session")


def _encrypt_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(data)
    for key in (
        "google_api_1",
        "google_api_2",
        "agnes_api",
        "pexels_api",
        "pollinations_api",
        "api_keys_json",
        "tiktok_session",
        "youtube_session",
        "facebook_session",
    ):
        if key in out and out[key]:
            out[key] = encrypt_text(str(out[key]))
    return out


def _decrypt_channel(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for key in (
        "google_api_1",
        "google_api_2",
        "agnes_api",
        "pexels_api",
        "pollinations_api",
        "api_keys_json",
        "tiktok_session",
        "youtube_session",
        "facebook_session",
    ):
        if d.get(key):
            try:
                d[key] = decrypt_text(d[key])
            except Exception:
                pass
    return d


def upsert_channel(payload: Dict[str, Any], channel_id: Optional[int] = None) -> int:
    data = _encrypt_fields(payload)
    now = datetime.now().isoformat()
    # Soft-ensure owner column (C04)
    try:
        from app.customer_config import ensure_channel_owner_column

        ensure_channel_owner_column()
    except Exception:
        pass
    fields = [
        "youtube_name", "facebook_name", "tiktok_name", "niche", "niche_id", "video_special", "long_upload_time",
        "short_upload_time", "example_script", "generation_special", "title_desc_special",
        "logo_path", "intro_path", "google_api_1", "google_api_2", "agnes_api", "pexels_api",
        "pollinations_api", "api_keys_json", "languages_json", "lang_destinations_json",
        "youtube_session", "facebook_session", "tiktok_session", "enabled", "owner_login_id",
    ]
    with db() as conn:
        cols_present = {r[1] for r in conn.execute("PRAGMA table_info(channels)").fetchall()}
        use_fields = [f for f in fields if f in cols_present]
        if channel_id:
            sets = ", ".join(f"{f}=?" for f in use_fields) + ", updated_at=?"
            values = [data.get(f) for f in use_fields] + [now, channel_id]
            conn.execute(f"UPDATE channels SET {sets} WHERE id=?", values)
            return channel_id
        cols = ", ".join(use_fields + ["created_at", "updated_at"])
        placeholders = ", ".join("?" for _ in use_fields) + ", ?, ?"
        values = [data.get(f) for f in use_fields] + [now, now]
        cur = conn.execute(
            f"INSERT INTO channels ({cols}) VALUES ({placeholders})",
            values,
        )
        return int(cur.lastrowid)


def list_channels() -> List[Dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM channels ORDER BY id DESC").fetchall()
        return [_decrypt_channel(r) for r in rows]


def get_channel(channel_id: int) -> Optional[Dict[str, Any]]:
    with db() as conn:
        row = conn.execute("SELECT * FROM channels WHERE id=?", (channel_id,)).fetchone()
        return _decrypt_channel(row) if row else None


def add_job(job: Dict[str, Any]) -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (channel_id, video_type, title, description, tags, local_path,
              platform, upload_status, remote_url, error, created_at, uploaded_at, lang_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.get("channel_id"),
                job.get("video_type"),
                job.get("title"),
                job.get("description"),
                job.get("tags"),
                job.get("local_path"),
                job.get("platform"),
                job.get("upload_status", "generated"),
                job.get("remote_url"),
                job.get("error"),
                datetime.now().isoformat(),
                job.get("uploaded_at"),
                job.get("lang_code") or "en",
            ),
        )
        return int(cur.lastrowid)


def list_jobs(limit: int = 100) -> List[Dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_pending_upload_jobs(
    channel_id: int,
    video_type: str,
    *,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Jobs generated ahead of time and waiting for the upload timer."""
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE channel_id=? AND video_type=?
              AND upload_status IN ('generated', 'ready_to_upload')
            ORDER BY id ASC
            LIMIT ?
            """,
            (channel_id, video_type, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def count_pending_upload_jobs(channel_id: int, video_type: str) -> int:
    with db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM jobs
            WHERE channel_id=? AND video_type=?
              AND upload_status IN ('generated', 'ready_to_upload')
            """,
            (channel_id, video_type),
        ).fetchone()
        return int(row["c"] if row else 0)


def update_job(job_id: int, **fields: Any) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with db() as conn:
        conn.execute(f"UPDATE jobs SET {sets} WHERE id=?", [*fields.values(), job_id])


def mark_engage(platform: str, url: str, action: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO engage_state (platform, url, action, done_at) VALUES (?, ?, ?, ?)",
            (platform, url, action, datetime.now().isoformat()),
        )


def engage_done(platform: str, url: str, action: str) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM engage_state WHERE platform=? AND url=? AND action=? LIMIT 1",
            (platform, url, action),
        ).fetchone()
        return row is not None


def set_meta(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO app_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_meta(key: str, default: str = "") -> str:
    with db() as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def add_language_request(payload: Dict[str, Any]) -> int:
    now = datetime.now().isoformat()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO language_requests
              (channel_id, lang_code, amount, payment_ref, payment_note, status, remote_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("channel_id"),
                payload.get("lang_code"),
                payload.get("amount") or "",
                payload.get("payment_ref") or "",
                payload.get("payment_note") or "",
                payload.get("status") or "pending",
                payload.get("remote_id"),
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


def list_language_requests(limit: int = 50) -> List[Dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM language_requests ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_language_request(req_id: int) -> Optional[Dict[str, Any]]:
    with db() as conn:
        row = conn.execute("SELECT * FROM language_requests WHERE id=?", (req_id,)).fetchone()
        return dict(row) if row else None


def update_language_request(req_id: int, **fields: Any) -> None:
    if not fields:
        return
    fields = dict(fields)
    fields["updated_at"] = datetime.now().isoformat()
    sets = ", ".join(f"{k}=?" for k in fields)
    with db() as conn:
        conn.execute(f"UPDATE language_requests SET {sets} WHERE id=?", [*fields.values(), req_id])


def pending_language_for(lang_code: str) -> Optional[Dict[str, Any]]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM language_requests WHERE lang_code=? AND status='pending' ORDER BY id DESC LIMIT 1",
            (lang_code,),
        ).fetchone()
        return dict(row) if row else None


def save_agent_escalation(
    *,
    customer_login: str = "",
    message: str = "",
    reason: str = "",
    screenshot_note: str = "",
    activity_hint: str = "",
    remote_ok: bool = False,
) -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO agent_escalations
              (customer_login, message, reason, screenshot_note, activity_hint, status, remote_ok, created_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (
                customer_login,
                message[:4000],
                reason[:2000],
                screenshot_note[:4000],
                activity_hint[:2000],
                1 if remote_ok else 0,
                datetime.now().isoformat(),
            ),
        )
        return int(cur.lastrowid)


def list_agent_escalations(limit: int = 50) -> List[Dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_escalations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_post_from_upload(
    *,
    job_id: int,
    channel_id: int,
    lang_code: str,
    platform: str,
    title: str,
    remote_url: str,
    local_path: str,
) -> int:
    now = datetime.now().isoformat()
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM posts WHERE job_id=? AND platform=? AND lang_code=? LIMIT 1",
            (job_id, platform, lang_code or "en"),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE posts SET title=?, remote_url=?, local_path=?, updated_at=?
                WHERE id=?
                """,
                (title, remote_url, local_path, now, row["id"]),
            )
            return int(row["id"])
        cur = conn.execute(
            """
            INSERT INTO posts
              (job_id, channel_id, lang_code, platform, title, remote_url, local_path,
               views, likes, comments, shares, reach, stats_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, '{}', ?, ?)
            """,
            (
                job_id,
                channel_id,
                lang_code or "en",
                platform,
                title,
                remote_url,
                local_path,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


def list_posts(limit: int = 100, lang_code: str = "") -> List[Dict[str, Any]]:
    with db() as conn:
        if lang_code:
            rows = conn.execute(
                "SELECT * FROM posts WHERE lang_code=? ORDER BY id DESC LIMIT ?",
                (lang_code, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM posts ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        posts = [dict(r) for r in rows]
        for p in posts:
            msgs = conn.execute(
                "SELECT * FROM post_messages WHERE post_id=? ORDER BY id DESC LIMIT 40",
                (p["id"],),
            ).fetchall()
            p["messages"] = [dict(m) for m in msgs]
        return posts


def add_post_message(
    post_id: int,
    *,
    platform: str = "",
    author: str = "",
    message: str = "",
    reply: str = "",
    lang_code: str = "en",
) -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO post_messages (post_id, platform, author, message, reply, lang_code, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                platform,
                author,
                message,
                reply,
                lang_code or "en",
                datetime.now().isoformat(),
            ),
        )
        return int(cur.lastrowid)


def list_recent_post_messages(limit: int = 30) -> List[Dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT pm.*, p.title as post_title, p.remote_url 
            FROM post_messages pm
            LEFT JOIN posts p ON p.id = pm.post_id
            ORDER BY pm.id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_post_stats(post_id: int, **stats: Any) -> None:
    allowed = {"views", "likes", "comments", "shares", "reach", "stats_json", "remote_url", "title"}
    fields = {k: v for k, v in stats.items() if k in allowed}
    if not fields:
        return
    fields["updated_at"] = datetime.now().isoformat()
    sets = ", ".join(f"{k}=?" for k in fields)
    with db() as conn:
        conn.execute(f"UPDATE posts SET {sets} WHERE id=?", [*fields.values(), post_id])


def upsert_error_note(
    *,
    fingerprint: str,
    subsystem: str,
    fault_code: str,
    message: str,
    severity: str = "warn",
    job_id: Optional[int] = None,
    channel_id: Optional[int] = None,
    scene_idx: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
) -> int:
    now = datetime.now().isoformat()
    ctx = json.dumps(context or {}, ensure_ascii=False)
    with db() as conn:
        row = conn.execute(
            "SELECT id, count FROM error_notebook WHERE fingerprint=? LIMIT 1",
            (fingerprint,),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE error_notebook
                SET count=?, last_seen=?, message=?, severity=?, job_id=COALESCE(?, job_id),
                    channel_id=COALESCE(?, channel_id), scene_idx=COALESCE(?, scene_idx),
                    context_json=?, status='open'
                WHERE id=?
                """,
                (
                    int(row["count"] or 1) + 1,
                    now,
                    message,
                    severity,
                    job_id,
                    channel_id,
                    scene_idx,
                    ctx,
                    row["id"],
                ),
            )
            return int(row["id"])
        cur = conn.execute(
            """
            INSERT INTO error_notebook
              (fingerprint, subsystem, fault_code, message, severity, job_id, channel_id,
               scene_idx, context_json, count, status, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'open', ?, ?)
            """,
            (
                fingerprint,
                subsystem,
                fault_code,
                message,
                severity,
                job_id,
                channel_id,
                scene_idx,
                ctx,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


def list_error_notes(
    *,
    status: str = "open",
    subsystem: str = "",
    limit: int = 80,
) -> List[Dict[str, Any]]:
    with db() as conn:
        if subsystem and status:
            rows = conn.execute(
                """
                SELECT * FROM error_notebook
                WHERE status=? AND subsystem=?
                ORDER BY last_seen DESC LIMIT ?
                """,
                (status, subsystem, limit),
            ).fetchall()
        elif status:
            rows = conn.execute(
                """
                SELECT * FROM error_notebook WHERE status=?
                ORDER BY last_seen DESC LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM error_notebook ORDER BY last_seen DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def resolve_error_note(note_id: int, *, owner_note: str = "") -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE error_notebook
            SET status='resolved', owner_note=?, last_seen=?
            WHERE id=?
            """,
            (owner_note, datetime.now().isoformat(), note_id),
        )


def get_app_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve arbitrary key-value setting from app_meta table."""
    try:
        with db() as conn:
            row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
            if row:
                return str(row["value"])
    except Exception:
        pass
    return default


def set_app_setting(key: str, value: str) -> None:
    """Store or update key-value setting in app_meta table."""
    with db() as conn:
        conn.execute(
            """
            INSERT INTO app_meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )


def create_google_pro_order(data: Dict[str, Any]) -> Dict[str, Any]:
    """Store a customer order request for a Google Special Account."""
    import uuid
    order_id = str(data.get("order_id") or f"GPRO-{int(datetime.now().timestamp())}-{uuid.uuid4().hex[:4].upper()}")
    now = datetime.now().isoformat()
    plan_id = str(data.get("plan_id") or "1_month")
    plan_name = str(data.get("plan_name") or "মাসিক প্ল্যান (৩০ দিন)")
    duration_months = int(data.get("duration_months") or 1)
    price = int(data.get("price") or 120)
    target_email = str(data.get("target_email") or "").strip()
    whatsapp = str(data.get("whatsapp") or "").strip()
    trx_id = str(data.get("trx_id") or "").strip()
    note = str(data.get("note") or "").strip()

    with db() as conn:
        conn.execute(
            """
            INSERT INTO google_pro_orders (
              order_id, plan_id, plan_name, duration_months, price,
              target_email, whatsapp, trx_id, note, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (order_id, plan_id, plan_name, duration_months, price, target_email, whatsapp, trx_id, note, now),
        )
    return {
        "order_id": order_id,
        "plan_id": plan_id,
        "plan_name": plan_name,
        "price": price,
        "target_email": target_email,
        "whatsapp": whatsapp,
        "status": "pending",
        "created_at": now,
    }


def list_google_pro_orders() -> List[Dict[str, Any]]:
    """List all Google Special Account orders placed by customer."""
    try:
        with db() as conn:
            rows = conn.execute("SELECT * FROM google_pro_orders ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


def approve_google_pro_order(order_id: str) -> bool:
    """Admin accept/approve of a Google Special Account order."""
    now = datetime.now().isoformat()
    with db() as conn:
        res = conn.execute(
            "UPDATE google_pro_orders SET status = 'approved', approved_at = ? WHERE order_id = ? AND status = 'pending'",
            (now, order_id),
        )
        return res.rowcount > 0
