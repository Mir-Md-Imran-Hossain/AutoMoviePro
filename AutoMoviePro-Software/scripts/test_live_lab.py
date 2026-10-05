"""Live Lab gate + login-signal tests (no network, no generate)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from publishers.login_signals import (  # noqa: E402
    cookies_indicate_login,
    patch_env_dry_run,
)
from app import db as store  # noqa: E402
from pipeline.live_lab import audit_job, gate  # noqa: E402

failed = 0
passed = 0


def expect(cond: bool, msg: str) -> None:
    global failed, passed
    if cond:
        passed += 1
        print(f"OK  {msg}")
    else:
        failed += 1
        print(f"FAIL {msg}")


def round_cookies() -> None:
    print("\n=== cookies ===")
    yt = {"cookies": [{"name": "SID"}, {"name": "LOGIN_INFO"}]}
    fb = {"cookies": [{"name": "c_user"}, {"name": "xs"}]}
    empty = {"cookies": [{"name": "NID"}]}
    expect(cookies_indicate_login("youtube", yt), "youtube SID+LOGIN_INFO")
    expect(not cookies_indicate_login("youtube", empty), "youtube NID only is not login")
    expect(cookies_indicate_login("facebook", fb), "facebook c_user")
    expect(not cookies_indicate_login("facebook", empty), "facebook NID only is not login")


def round_env() -> None:
    print("\n=== .env dry-run patch ===")
    src = "API_BASE_URL=https://automoviepro.com\nDRY_RUN_PUBLISH=true\nLOCAL_PORT=8787\n"
    out = patch_env_dry_run(src, False)
    expect("DRY_RUN_PUBLISH=false" in out, "flips to live")
    expect("API_BASE_URL=https://automoviepro.com" in out, "keeps other keys")
    expect(out.count("DRY_RUN_PUBLISH=") == 1, "single dry-run line")
    added = patch_env_dry_run("FOO=1\n", True)
    expect("DRY_RUN_PUBLISH=true" in added, "appends if missing")


def round_audit_gate() -> None:
    print("\n=== audit + gate ===")
    issues = audit_job({"title": "", "description": "", "tags": "", "local_path": "nope.mp4"})
    expect("missing_title" in issues, "title flagged")
    expect("missing_description" in issues, "description flagged")
    expect("missing_video_file" in issues, "missing file flagged")
    g = gate({"id": 1, "youtube_name": "", "facebook_name": ""})
    expect(g.get("ok") is False, "empty names not ready")
    expect("youtube_name_missing" in (g.get("blockers") or []), "yt name blocker")
    expect("facebook_name_missing" in (g.get("blockers") or []), "fb name blocker")


def round_readiness_mins() -> None:
    print("\n=== provider mins ===")
    from pipeline.channel_api_slots import min_for_provider

    expect(min_for_provider("google", required=True) == 2, "google min 2")
    expect(min_for_provider("pexels", required=True) == 1, "pexels min 1")
    expect(min_for_provider("pollinations", required=True) == 1, "pollinations min 1")
    expect(min_for_provider("huggingface", required=False) == 0, "optional min 0")


def round_chrome_helper() -> None:
    print("\n=== chrome helper ===")
    from publishers.real_chrome import CHROME_ARGS, chrome_candidates, free_port

    expect("--disable-extensions" in CHROME_ARGS, "extensions off for login")
    expect("--disable-blink-features=AutomationControlled" in CHROME_ARGS, "automation blink off")
    expect(len(chrome_candidates()) >= 3, "chrome path candidates")
    p = free_port()
    expect(isinstance(p, int) and p > 0, "free debug port")


if __name__ == "__main__":
    store.init_db()
    round_cookies()
    round_env()
    round_audit_gate()
    round_readiness_mins()
    round_chrome_helper()
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
