from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Sequence

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
UI_DIR = ROOT / "ui" / "static"

logger = logging.getLogger(__name__)

# Explicit local-only API bases for offline/dev login (never includes marketing placeholders).
_DEFAULT_LOCAL_LOGIN_BASES = (
    "local",
    "localhost",
    "offline",
    "http://127.0.0.1",
    "http://localhost",
)


class Settings(BaseSettings):
    """Canonical runtime configuration authority (H2).

    Secrets (API keys) remain loaded via pipeline.api_keys — not stored here.
    """

    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_base_url: str = "https://yourdomain.com"
    local_host: str = "127.0.0.1"
    local_port: int = 8787
    short_target_seconds: int = 60
    short_max_seconds: int = 120
    long_target_seconds: int = 180
    long_max_seconds: int = 300
    intelligence_research_mode: str = "LIVE"
    intelligence_mode: str = "PRODUCTION"

    # Publish safety — default dry-run (fail-closed for live upload)
    dry_run_publish: bool = True

    # Local/dev login — production fail-closed (default deny)
    amp_allow_local_login: bool = False
    amp_dev_login_id: str = ""
    amp_dev_login_password: str = ""
    # Comma-separated; empty string means use built-in local defaults only
    amp_local_login_bases: str = ""


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def is_production_runtime(cfg: Optional[Settings] = None) -> bool:
    c = cfg or settings
    return str(c.intelligence_mode or "PRODUCTION").strip().upper() == "PRODUCTION"


def is_development_runtime(cfg: Optional[Settings] = None) -> bool:
    return not is_production_runtime(cfg)


def local_login_base_allowlist(cfg: Optional[Settings] = None) -> set[str]:
    c = cfg or settings
    raw = (c.amp_local_login_bases or "").strip()
    if raw:
        bases = {b.strip().lower().rstrip("/") for b in raw.split(",") if b.strip()}
    else:
        bases = {b.lower().rstrip("/") for b in _DEFAULT_LOCAL_LOGIN_BASES}
    bases.add("")  # empty api base treated as local-only
    return bases


def api_base_allows_local_login(api_base: str, cfg: Optional[Settings] = None) -> bool:
    """Explicit local bases only — never auto-allow marketing placeholders (e.g. yourdomain.com)."""
    base_norm = (api_base or "").strip().lower().rstrip("/")
    allowed = local_login_base_allowlist(cfg)
    if base_norm in allowed:
        return True
    if base_norm.startswith("http://127.0.0.1") or base_norm.startswith("http://localhost"):
        return True
    return False


def resolve_local_login_credentials(cfg: Optional[Settings] = None) -> Optional[tuple[str, str]]:
    """Return (id, password) only when local login is explicitly enabled.

    PRODUCTION: both AMP_DEV_LOGIN_ID and AMP_DEV_LOGIN_PASSWORD must be set — no defaults.
    DEVELOPMENT: defaults admin/admin123 allowed only when amp_allow_local_login is True.
    """
    c = cfg or settings
    if not bool(c.amp_allow_local_login):
        return None
    uid = (c.amp_dev_login_id or "").strip()
    pwd = (c.amp_dev_login_password or "").strip()
    if is_production_runtime(c):
        if not uid or not pwd:
            return None
        return uid, pwd
    # Development / non-production: intentional demo credentials only when allow flag set
    return (uid or "admin"), (pwd or "admin123")


def local_login_permitted(
    login_id: str, password: str, api_base: str, cfg: Optional[Settings] = None
) -> bool:
    creds = resolve_local_login_credentials(cfg)
    if creds is None:
        return False
    if not api_base_allows_local_login(api_base, cfg):
        return False
    expect_id, expect_pwd = creds
    return (login_id or "").strip() == expect_id and (password or "") == expect_pwd


def amp_skip_active(flag_name: str, cfg: Optional[Settings] = None) -> bool:
    """Whether an AMP_SKIP_* env flag may take effect.

    In PRODUCTION, skip flags are ignored (gates remain active) — fail-closed.
    In DEVELOPMENT, env value ``1`` activates the skip.
    """
    raw = (os.environ.get(flag_name) or "").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return False
    if is_production_runtime(cfg):
        logger.error(
            "AMP_SKIP blocked in PRODUCTION: %s (intelligence_mode=PRODUCTION)",
            flag_name,
        )
        return False
    return True


def safe_config_diagnostics(cfg: Optional[Settings] = None) -> dict:
    """Non-secret configuration snapshot for diagnostics."""
    c = cfg or settings
    from app.release_identity import RELEASE_VERSION, get_release_identity

    identity = get_release_identity(include_media=False)
    return {
        "dry_run_publish": bool(c.dry_run_publish),
        "intelligence_mode": str(c.intelligence_mode),
        "intelligence_research_mode": str(c.intelligence_research_mode),
        "amp_allow_local_login": bool(c.amp_allow_local_login),
        "local_login_credentials_configured": bool(
            (c.amp_dev_login_id or "").strip() and (c.amp_dev_login_password or "").strip()
        ),
        "local_host": c.local_host,
        "local_port": c.local_port,
        "api_base_url_host_only": (c.api_base_url or "").split("://")[-1].split("/")[0],
        "api_base_url_configured": bool((c.api_base_url or "").strip()),
        "release_version": RELEASE_VERSION,
        "build_id": identity.get("build_id"),
        "database_configured": (DATA_DIR / "local.db").is_file() or DATA_DIR.is_dir(),
        "env_file_present": (ROOT / ".env").is_file(),
    }


def validate_production_operational(cfg: Optional[Settings] = None) -> dict:
    """H5 operational readiness (NOT publishability). Safe metadata only.

    Separates:
    - application can run
    - media tools available
    - production mode constraints
    """
    c = cfg or settings
    from pipeline.compose import probe_media_tool_capability

    issues: list[str] = []
    media = probe_media_tool_capability()
    ffmpeg_ok = bool(media.get("FFMPEG_AVAILABLE"))
    ffprobe_ok = bool(media.get("FFPROBE_AVAILABLE"))
    if not ffmpeg_ok:
        issues.append("ffmpeg_unavailable")
    if not ffprobe_ok:
        issues.append("ffprobe_unavailable")

    prod = is_production_runtime(c)
    # In PRODUCTION, AMP_SKIP must not be active (amp_skip_active already blocks)
    for flag in ("AMP_SKIP_LOCALIZE", "AMP_SKIP_ASSET_ARCHIVE"):
        raw = (os.environ.get(flag) or "").strip().lower()
        if raw in {"1", "true", "yes", "on"} and prod:
            # Flag present but must be ignored — record as blocked_attempt not active
            issues.append(f"skip_flag_present_ignored:{flag}")

    if not DATA_DIR.exists():
        issues.append("data_dir_missing")

    # Media is required for production media work; process can still be healthy.
    production_ready = ffmpeg_ok and ffprobe_ok and DATA_DIR.exists()
    return {
        "production_mode": prod,
        "production_ready": bool(production_ready),
        "status": "READY" if production_ready else "BLOCKED",
        "issues": issues,
        "media": {
            "ffmpeg_available": ffmpeg_ok,
            "ffprobe_available": ffprobe_ok,
            "ffmpeg_source": media.get("ffmpeg_source"),
            "ffprobe_source": media.get("ffprobe_source"),
        },
        "dry_run_publish": bool(c.dry_run_publish),
        "note": "production_ready means operational media prerequisites — not artifact publishability",
    }


def software_env_paths(extra: Optional[Sequence[Path]] = None) -> list[Path]:
    """Canonical .env search paths for secret loading (software root only)."""
    paths = [ROOT / ".env"]
    raw_extra = (os.environ.get("AMP_EXTRA_ENV_PATHS") or "").strip()
    if raw_extra:
        for part in raw_extra.split(os.pathsep):
            part = part.strip()
            if part:
                paths.append(Path(part))
    if extra:
        paths.extend(Path(p) for p in extra)
    return paths
