"""
24h marathon tick — snapshot everything the supervising agent needs.

Usage:
  venv\\Scripts\\python.exe scripts\\marathon_tick.py

Writes data/marathon_24h/latest_tick.json + appends history.jsonl
Exit 0 = healthy/watch, 2 = needs_fix (error/stuck/captcha/quality)
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "marathon_24h"
STATE = OUT / "state.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_state() -> Dict[str, Any]:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(st: Dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_state() -> Dict[str, Any]:
    st = load_state()
    if not st.get("started_at"):
        st = {
            "started_at": _now(),
            "ends_at": (datetime.now() + timedelta(hours=24)).isoformat(timespec="seconds"),
            "tick_interval_sec": 720,
            "mode": "autonomous_24h",
            "auto_fix": True,
            "auto_captcha": True,
            "no_wait_for_human": True,
        }
        save_state(st)
    return st


def http_json(path: str) -> Dict[str, Any]:
    import urllib.request

    url = f"http://127.0.0.1:8787{path}"
    try:
        with urllib.request.urlopen(url, timeout=12) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"ok": False, "error": str(exc), "_path": path}


def collect() -> Dict[str, Any]:
    from app import db as store

    st = ensure_state()
    status = http_json("/api/status")
    activity = http_json("/api/activity")
    lab = http_json("/api/live-lab")
    captcha = http_json("/api/captcha-status")
    browse = http_json("/api/trust-browse/log?limit=40")
    notes = http_json("/api/error-notes?status=open")

    act = (activity or {}).get("activity") or activity or {}
    gate = (lab or {}).get("gate") or {}
    report = (lab or {}).get("report") or {}
    cap = (captcha or {}).get("captcha") or captcha or {}

    alerts: List[str] = []
    severity = "ok"

    if not status.get("ok") or not status.get("logged_in"):
        alerts.append("server_or_login_down")
        severity = "critical"
    if not status.get("app_active"):
        alerts.append("app_inactive_api")
        severity = "critical"
    if cap.get("locked"):
        alerts.append("captcha_locked")
        severity = "critical"
    phase = str((lab or {}).get("phase") or report.get("phase") or act.get("phase") or "")
    if phase == "failed" or (report.get("errors") and phase not in ("waiting_comments", "complete")):
        alerts.append("lab_failed_or_errors")
        severity = "critical"
    if act.get("active") and act.get("phase"):
        # stuck detection via state
        sticky = f"{act.get('kind')}|{act.get('phase')}|{act.get('scene')}"
        prev = st.get("last_sticky") or ""
        same_since = st.get("sticky_since") or _now()
        if sticky == prev:
            try:
                age = (datetime.now() - datetime.fromisoformat(same_since)).total_seconds()
            except Exception:
                age = 0
            if age > 25 * 60:
                alerts.append(f"stuck_same_scene_{int(age // 60)}m")
                severity = "critical"
        else:
            st["last_sticky"] = sticky
            st["sticky_since"] = _now()
    else:
        st["last_sticky"] = ""
        st["sticky_since"] = ""

    # Quality: recent jobs
    jobs = store.list_jobs(12)
    recent = []
    for j in jobs[:6]:
        recent.append(
            {
                "id": j.get("id"),
                "type": j.get("video_type"),
                "status": j.get("upload_status"),
                "title": (j.get("title") or "")[:80],
                "error": (j.get("error") or "")[:160],
                "path": j.get("local_path"),
                "created_at": j.get("created_at"),
            }
        )
        if j.get("upload_status") == "quality_blocked":
            alerts.append(f"quality_blocked_job_{j.get('id')}")
            if severity == "ok":
                severity = "warn"

    # Browser glitches
    glitches = (browse or {}).get("glitches") or []
    bad_glitch = [
        g
        for g in glitches[:15]
        if str(g.get("severity")) in ("error", "warn")
        and str(g.get("fault_code"))
        not in ("unit_test",)
    ]

    # Trust browse plan
    plan = (browse or {}).get("plan") or {}
    running_browse = bool((browse or {}).get("running"))

    # Ends check
    ends = st.get("ends_at") or ""
    remaining_h = None
    try:
        remaining_h = round(
            (datetime.fromisoformat(ends) - datetime.now()).total_seconds() / 3600.0, 2
        )
        if remaining_h <= 0:
            alerts.append("marathon_24h_complete")
    except Exception:
        pass

    open_notes = (notes or {}).get("notes") or []
    browser_notes = [
        n for n in open_notes if str(n.get("subsystem") or "").startswith("browser")
    ][:8]

    tick = {
        "ts": _now(),
        "severity": severity if not alerts else ("critical" if severity == "critical" else "warn"),
        "alerts": alerts,
        "remaining_hours": remaining_h,
        "state": {
            "started_at": st.get("started_at"),
            "ends_at": st.get("ends_at"),
            "auto_fix": True,
            "no_wait_for_human": True,
        },
        "status": {
            "logged_in": status.get("logged_in"),
            "app_active": status.get("app_active"),
            "dry_run": status.get("dry_run_publish"),
            "jobs": status.get("jobs"),
        },
        "activity": {
            "active": act.get("active"),
            "kind": act.get("kind"),
            "phase": act.get("phase"),
            "scene": act.get("scene"),
            "scene_total": act.get("scene_total"),
            "detail": (act.get("detail") or "")[:200],
        },
        "live_lab": {
            "phase": phase,
            "cycle": (lab or {}).get("cycle") or report.get("cycle"),
            "lab_active": (lab or {}).get("lab_active"),
            "gate_ok": gate.get("ok"),
            "errors": (report.get("errors") or [])[-6:],
            "uploads": report.get("uploads") or [],
            "watch_urls": report.get("watch_urls") or [],
            "yt_connected": (gate.get("youtube") or {}).get("connected"),
            "fb_connected": (gate.get("facebook") or {}).get("connected"),
            "live_publish": gate.get("live_publish"),
        },
        "captcha": {
            "locked": bool(cap.get("locked")),
            "status": cap.get("status"),
            "platform": cap.get("platform"),
            "url": cap.get("url"),
            "message": (cap.get("message") or "")[:160],
        },
        "trust_browse": {
            "running": running_browse,
            "plan_done": plan.get("done"),
            "plan_windows": plan.get("windows"),
            "recent_actions": [
                {
                    "action": e.get("action"),
                    "platform": e.get("platform"),
                    "ok": e.get("ok"),
                    "detail": (e.get("detail") or "")[:100],
                }
                for e in ((browse or {}).get("events") or [])[:8]
            ],
            "glitch_count": len(bad_glitch),
            "glitches": bad_glitch[:5],
        },
        "recent_jobs": recent,
        "browser_error_notes": [
            {"fault": n.get("fault_code"), "msg": (n.get("message") or "")[:120], "count": n.get("count")}
            for n in browser_notes
        ],
        "actions_for_agent": _recommend(alerts, phase, act, cap, report),
    }

    st["last_tick_at"] = _now()
    st["last_severity"] = tick["severity"]
    st["last_alerts"] = alerts
    save_state(st)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest_tick.json").write_text(
        json.dumps(tick, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (OUT / "history.jsonl").open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"ts": tick["ts"], "severity": tick["severity"], "alerts": alerts, "phase": phase},
                ensure_ascii=False,
            )
            + "\n"
        )
    return tick


def _recommend(alerts, phase, act, cap, report) -> List[str]:
    rec = []
    if "server_or_login_down" in alerts:
        rec.append("restart_server_and_verify_/api/status")
    if "captcha_locked" in alerts:
        rec.append("try_easy_captcha_solve_then_unlock_or_TTL; do_not_wait_for_human")
    if "lab_failed_or_errors" in alerts:
        rec.append("triage_live_lab_errors_with_3_agent_angles_then_fix_and_restart_cycle")
    if any(a.startswith("stuck_same_scene") for a in alerts):
        rec.append("inspect_scene_output_diagnose_clip_fix_or_skip_retry_generate")
    if phase in ("waiting_comments", "complete") and not act.get("active"):
        if phase == "waiting_comments":
            rec.append("run_comment_check_then_start_new_cycle_if_marathon_continues")
        else:
            rec.append("start_new_live_lab_cycle_for_next_short_plus_long")
    if phase in ("idle", "cancelled", "") and not act.get("active"):
        rec.append("POST_/api/live-lab/start_for_fresh_cycle")
    if not rec:
        rec.append("continue_monitoring_no_action")
    return rec


def main() -> int:
    tick = collect()
    print(json.dumps({"severity": tick["severity"], "alerts": tick["alerts"], "actions": tick["actions_for_agent"]}, indent=2))
    print(f"Wrote {OUT / 'latest_tick.json'}")
    if tick["severity"] == "critical":
        return 2
    if "marathon_24h_complete" in (tick.get("alerts") or []):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
