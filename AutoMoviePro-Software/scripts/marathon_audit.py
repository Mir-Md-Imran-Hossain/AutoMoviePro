"""
Marathon system health audit — sector-by-sector self-checks.

Run:
  venv\\Scripts\\python.exe scripts\\marathon_audit.py

Writes:
  data/marathon_audit/latest.json
  data/marathon_audit/history.jsonl

Designed to be re-run after fixes; exit code 1 if any critical fails.
"""
from __future__ import annotations

import importlib
import json
import py_compile
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "data" / "marathon_audit"


def _ok(name: str, detail: str = "") -> Dict[str, Any]:
    return {"name": name, "status": "pass", "detail": detail}


def _fail(name: str, detail: str, *, severity: str = "critical") -> Dict[str, Any]:
    return {"name": name, "status": "fail", "severity": severity, "detail": detail}


def _warn(name: str, detail: str) -> Dict[str, Any]:
    return {"name": name, "status": "warn", "severity": "medium", "detail": detail}


def sector_imports() -> List[Dict[str, Any]]:
    mods = [
        "app.config",
        "app.db",
        "app.scheduler_service",
        "app.main",
        "pipeline.video_pipeline",
        "pipeline.av_quality_gates",
        "pipeline.live_lab",
        "pipeline.tts_google",
        "publishers.upload_service",
        "publishers.youtube_uploader",
        "publishers.facebook_uploader",
        "publishers.human_browser",
        "publishers.browser_intel",
        "publishers.stealth_session",
        "publishers.api_collector",
        "publishers.login_signals",
        "hidden_engage.trust_browse",
        "hidden_engage.channel_fsm",
        "hidden_engage.seed_feed",
        "hidden_engage.schedule_plan",
    ]
    out = []
    for m in mods:
        try:
            importlib.import_module(m)
            out.append(_ok(f"import:{m}"))
        except Exception as exc:
            out.append(_fail(f"import:{m}", f"{type(exc).__name__}: {exc}"))
    return out


def sector_compile() -> List[Dict[str, Any]]:
    out = []
    for pkg in ("app", "pipeline", "publishers", "hidden_engage"):
        base = ROOT / pkg
        if not base.exists():
            out.append(_fail(f"compile:{pkg}", "missing package dir"))
            continue
        bad = []
        for p in base.rglob("*.py"):
            try:
                py_compile.compile(str(p), doraise=True)
            except Exception as exc:
                bad.append(f"{p.relative_to(ROOT)}: {exc}")
        if bad:
            out.append(_fail(f"compile:{pkg}", "; ".join(bad[:5])))
        else:
            out.append(_ok(f"compile:{pkg}"))
    return out


def sector_db() -> List[Dict[str, Any]]:
    out = []
    try:
        from app import db as store

        store.init_db()
        with store.db() as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        required = {
            "session",
            "channels",
            "jobs",
            "engage_state",
            "engage_activity",
            "posts",
            "error_notebook",
            "app_meta",
        }
        missing = sorted(required - tables)
        if missing:
            out.append(_fail("db:required_tables", f"missing={missing}"))
        else:
            out.append(_ok("db:required_tables", f"count={len(tables)}"))
    except Exception as exc:
        out.append(_fail("db:init", traceback.format_exc()[-400:]))
    return out


def sector_config() -> List[Dict[str, Any]]:
    out = []
    try:
        from app.config import settings

        out.append(
            _ok(
                "config:cadence",
                f"short={settings.daily_short_limit} long={settings.daily_long_limit} "
                f"dry_run={settings.dry_run_publish} port={settings.local_port}",
            )
        )
        if int(settings.daily_short_limit) < 1 or int(settings.daily_long_limit) < 1:
            out.append(_warn("config:limits", "daily limits < 1 may stall cadence"))
        if settings.dry_run_publish:
            out.append(_warn("config:dry_run", "DRY_RUN_PUBLISH=true — no live platform posts"))
        else:
            out.append(_ok("config:live_publish", "DRY_RUN_PUBLISH=false"))
    except Exception as exc:
        out.append(_fail("config", str(exc)))
    return out


def sector_quality_gates() -> List[Dict[str, Any]]:
    out = []
    try:
        from pipeline import av_quality_gates as g

        hard = getattr(g, "UNSHIPPABLE_HARD_GATES", None) or getattr(g, "HARD_GATES", None)
        if not hard:
            out.append(_warn("quality:hard_gates", "no UNSHIPPABLE_HARD_GATES exported"))
        else:
            out.append(_ok("quality:hard_gates", f"count={len(hard)}"))
        if not hasattr(g, "evaluate_master_shippable"):
            out.append(_fail("quality:evaluate_master_shippable", "missing function"))
        else:
            out.append(_ok("quality:evaluate_master_shippable"))
    except Exception as exc:
        out.append(_fail("quality", str(exc)))
    return out


def sector_scheduler() -> List[Dict[str, Any]]:
    out = []
    try:
        from app.scheduler_service import SchedulerService
        import inspect

        src = inspect.getsource(SchedulerService._maybe_upload)
        if 'result.get("ok")' in src or "result.get('ok')" in src:
            out.append(_ok("scheduler:upload_ok_gate", "day meta only on success"))
        else:
            out.append(
                _fail(
                    "scheduler:upload_ok_gate",
                    "timed upload may mark day done without checking upload result",
                )
            )
        svc = SchedulerService()
        expected = {
            "heartbeat",
            "timed_upload",
            "idle_pregenerate",
            "comment_reply",
            "captcha_watch",
            "asset_local_sync",
            "hidden_engage",
            "trust_browse",
            "trust_browse_sync",
        }
        # jobs registered on start()
        svc.start()
        ids = {j.id for j in svc.scheduler.get_jobs()}
        svc.stop()
        missing = sorted(expected - ids)
        if missing:
            out.append(_fail("scheduler:jobs", f"missing={missing}"))
        else:
            out.append(_ok("scheduler:jobs", f"count={len(ids)}"))
    except Exception as exc:
        out.append(_fail("scheduler", str(exc)[:400]))
    return out


def sector_login_signals() -> List[Dict[str, Any]]:
    out = []
    try:
        from publishers.login_signals import cookies_indicate_login

        # Fake weak FB cookies should NOT pass
        weak = {"cookies": [{"name": "datr"}, {"name": "sb"}]}
        if cookies_indicate_login("facebook", weak):
            out.append(_fail("login:fb_weak_cookies", "datr/sb alone still accepted"))
        else:
            out.append(_ok("login:fb_weak_cookies_rejected"))
        strong = {"cookies": [{"name": "c_user"}, {"name": "xs"}]}
        if cookies_indicate_login("facebook", strong):
            out.append(_ok("login:fb_strong_cookies"))
        else:
            out.append(_fail("login:fb_strong_cookies", "c_user+xs rejected"))
    except Exception as exc:
        out.append(_fail("login_signals", str(exc)))
    return out


def sector_trust_browse() -> List[Dict[str, Any]]:
    out = []
    try:
        from hidden_engage.schedule_plan import get_day_plan
        from collections import defaultdict

        plan = get_day_plan()
        by = defaultdict(int)
        for w in plan.get("windows") or []:
            by[int(w["hour"])] += int(w["duration_min"])
        bad = [h for h, m in by.items() if m < 5]
        if len(by) < 20:
            out.append(_warn("trust:hour_coverage", f"only {len(by)} hours planned"))
        if bad:
            out.append(_fail("trust:min_5_per_hour", f"hours_under_5={bad[:8]}"))
        else:
            out.append(_ok("trust:min_5_per_hour", f"hours={len(by)} total_min={sum(by.values())}"))
    except Exception as exc:
        out.append(_fail("trust_browse", str(exc)))
    return out


SECTORS: List[tuple[str, Callable[[], List[Dict[str, Any]]]]] = [
    ("compile", sector_compile),
    ("imports", sector_imports),
    ("db", sector_db),
    ("config", sector_config),
    ("quality", sector_quality_gates),
    ("scheduler", sector_scheduler),
    ("login", sector_login_signals),
    ("trust_browse", sector_trust_browse),
]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "sectors": {},
        "summary": {},
    }
    all_rows: List[Dict[str, Any]] = []
    for name, fn in SECTORS:
        try:
            rows = fn()
        except Exception as exc:
            rows = [_fail(f"{name}:crash", str(exc))]
        report["sectors"][name] = rows
        all_rows.extend(rows)

    passes = sum(1 for r in all_rows if r["status"] == "pass")
    warns = sum(1 for r in all_rows if r["status"] == "warn")
    fails = sum(1 for r in all_rows if r["status"] == "fail")
    critical = sum(1 for r in all_rows if r["status"] == "fail" and r.get("severity") == "critical")
    report["summary"] = {
        "total": len(all_rows),
        "pass": passes,
        "warn": warns,
        "fail": fails,
        "critical": critical,
    }

    latest = OUT_DIR / "latest.json"
    latest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT_DIR / "history.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": report["ts"], "summary": report["summary"]}, ensure_ascii=False) + "\n")

    print(json.dumps(report["summary"], indent=2))
    for r in all_rows:
        if r["status"] != "pass":
            print(f"[{r['status'].upper()}] {r['name']}: {r.get('detail','')[:200]}")
    print(f"Wrote {latest}")
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
