"""

Live Lab — connect YouTube + Facebook, then run full generate → upload → comment cycles.

Cadence: one short + one long per cycle (daily production target is also 1 short + 1 long).

Used for the live soak: report every step, pause scheduler pre-generate while a cycle is active.

"""

from __future__ import annotations

import json

import logging

import time

from datetime import datetime

from pathlib import Path

from typing import Any, Dict, List, Optional

from app import db as store

from app.config import DATA_DIR, ROOT, settings

from publishers.login_signals import cookies_indicate_login, patch_env_dry_run

logger = logging.getLogger(__name__)

LAB_DIR = DATA_DIR / "live_lab"

META_ACTIVE = "live_lab_active"

META_CYCLE = "live_lab_cycle"

META_PHASE = "live_lab_phase"

def _now() -> str:

    return datetime.now().isoformat(timespec="seconds")

def is_lab_active() -> bool:

    return store.get_meta(META_ACTIVE, "") == "1"

def current_cycle_no() -> int:

    try:

        return int(store.get_meta(META_CYCLE, "0") or 0)

    except (TypeError, ValueError):

        return 0

def report_path(cycle: int) -> Path:

    LAB_DIR.mkdir(parents=True, exist_ok=True)

    return LAB_DIR / f"cycle_{int(cycle):03d}.json"

def load_report(cycle: Optional[int] = None) -> Dict[str, Any]:

    n = int(cycle or current_cycle_no() or 0)

    if n <= 0:

        return {}

    p = report_path(n)

    if not p.exists():

        return {"cycle": n, "phase": "missing"}

    try:

        return json.loads(p.read_text(encoding="utf-8"))

    except Exception:

        return {"cycle": n, "phase": "corrupt"}

def save_report(report: Dict[str, Any]) -> Path:

    n = int(report.get("cycle") or current_cycle_no() or 1)

    report["cycle"] = n

    report["updated_at"] = _now()

    p = report_path(n)

    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    latest = LAB_DIR / "latest.json"

    latest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return p

_last_mirror = 0.0

def mirror_activity(phase: str = "", detail: str = "", *, scene=None, total=None) -> None:

    """Heartbeat so this Cursor session can supervise while generate/upload runs."""

    global _last_mirror

    if store.get_meta(META_ACTIVE, "") != "1":

        return

    now = time.time()

    if now - _last_mirror < 4:

        return

    _last_mirror = now

    report = load_report() or {}

    if not report:

        return

    if phase:

        report["live_phase"] = phase

        store.set_meta(META_PHASE, phase)

    if detail:

        report["live_detail"] = str(detail)[:400]

    if scene is not None:

        report["scene"] = scene

        report["scene_total"] = total

    save_report(report)

def set_live_publish(enabled: bool) -> Dict[str, Any]:

    """False dry-run = real YouTube/Facebook upload. Persists to .env for restarts."""

    dry = not bool(enabled)

    settings.dry_run_publish = dry

    env_path = ROOT / ".env"

    try:

        text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

        env_path.write_text(patch_env_dry_run(text, dry), encoding="utf-8")

    except Exception as exc:

        logger.warning("could not persist DRY_RUN_PUBLISH: %s", exc)

    return {

        "ok": True,

        "live_publish": not dry,

        "dry_run_publish": dry,

    }

def _session_row(channel: Dict[str, Any], platform: str, lang_code: str = "en") -> Dict[str, Any]:
    from publishers.session_vault import session_status

    cid = int(channel.get("id") or 0)
    st = session_status(platform, cid, lang_code or "en")
    store_path = st.get("storage_state") or ""
    if st.get("status") != "connected" and store_path:
        if cookies_indicate_login(platform, store_path):
            st["status"] = "connected"
            st["connected"] = True
    return st


def gate(channel: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What must be true before a live cycle can start."""
    blockers: List[str] = []
    channels = store.list_channels() if channel is None else [channel]
    ch = channels[0] if channels else None
    if not ch:
        blockers.append("channel_missing")
        return {
            "ok": False,
            "blockers": blockers,
            "channel": None,
            "api_ready": False,
            "youtube": {"status": "needs_login", "connected": False},
            "facebook": {"status": "needs_login", "connected": False},
            "tiktok": {"status": "needs_login", "connected": False},
            "live_publish": not bool(settings.dry_run_publish),
            "dry_run_publish": bool(settings.dry_run_publish),
            "message": "Channel tab-এ একবার নিশ সেটআপ করুন, তারপর প্ল্যাটফর্ম কানেক্ট করুন।",
        }

    from pipeline.channel_api_slots import evaluate_readiness

    ready = evaluate_readiness(channel=ch)
    api_ready = bool(ready.get("active"))
    if not api_ready:
        blockers.append("apis_inactive")

    yt = _session_row(ch, "youtube", "en")
    fb = _session_row(ch, "facebook", "en")
    tt = _session_row(ch, "tiktok", "en")
    if not yt.get("connected"):
        blockers.append("youtube_not_connected")
    if not fb.get("connected"):
        blockers.append("facebook_not_connected")
    if not (ch.get("youtube_name") or "").strip():
        blockers.append("youtube_name_missing")
    if not (ch.get("facebook_name") or "").strip():
        blockers.append("facebook_name_missing")

    live = not bool(settings.dry_run_publish)
    warnings = []
    if not live:
        warnings.append("dry_run_on — Start Cycle লাইভ আপলোড চালু করবে")

    msg = "Ready" if not blockers else " · ".join(blockers)
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "channel_id": ch.get("id"),
        "youtube_name": ch.get("youtube_name") or "",
        "facebook_name": ch.get("facebook_name") or "",
        "tiktok_name": ch.get("tiktok_name") or "",
        "niche": ch.get("niche") or "",
        "api_ready": api_ready,
        "api_message": ready.get("message") or "",
        "youtube": yt,
        "facebook": fb,
        "tiktok": tt,
        "live_publish": live,
        "dry_run_publish": bool(settings.dry_run_publish),
        "lab_active": is_lab_active(),
        "cycle": current_cycle_no(),
        "phase": store.get_meta(META_PHASE, "idle") or "idle",
        "message": msg,
    }


def save_connect_names(*, youtube_name: str = "", facebook_name: str = "", tiktok_name: str = "") -> Dict[str, Any]:
    rows = store.list_channels()
    if not rows:
        return {"ok": False, "error": "channel_missing"}
    ch = dict(rows[0])
    if youtube_name.strip():
        ch["youtube_name"] = youtube_name.strip()
    if facebook_name.strip():
        ch["facebook_name"] = facebook_name.strip()
    if tiktok_name.strip():
        ch["tiktok_name"] = tiktok_name.strip()
    try:
        from pipeline.lang_destinations import parse_lang_destinations, serialize_lang_destinations

        dest = parse_lang_destinations(ch.get("lang_destinations_json"))
        slot = dict(dest.get("en") or {})
        if youtube_name.strip():
            slot["youtube_name"] = youtube_name.strip()
        if facebook_name.strip():
            slot["facebook_name"] = facebook_name.strip()
        if tiktok_name.strip():
            slot["tiktok_name"] = tiktok_name.strip()
        dest["en"] = slot
        ch["lang_destinations_json"] = serialize_lang_destinations(dest)
    except Exception:
        pass
    store.upsert_channel(ch, int(ch["id"]))
    return {"ok": True, "gate": gate()}


def audit_job(job: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    if not str(job.get("title") or "").strip():
        issues.append("missing_title")
    if not str(job.get("description") or "").strip():
        issues.append("missing_description")
    tags = job.get("tags")
    if not tags or (isinstance(tags, str) and not tags.strip()) or tags in ("[]", "null"):
        issues.append("missing_tags")
    path = Path(str(job.get("local_path") or ""))
    if not path.exists():

        issues.append("missing_video_file")

    thumb = str(job.get("thumbnail_path") or "")

    if thumb and not Path(thumb).exists():

        issues.append("missing_thumbnail_file")

    elif not thumb:

        # package beside video

        if path.exists():

            pkg = path.parent / "UPLOAD_PACKAGE"

            found = list(path.parent.glob("thumbnail.*")) or list(pkg.glob("**/thumbnail.*")) if pkg.exists() else []

            if not found:

                issues.append("missing_thumbnail")

        else:

            issues.append("missing_thumbnail")

    return issues

def _job_by_id(job_id: int) -> Optional[Dict[str, Any]]:

    for j in store.list_jobs(400):

        if int(j.get("id") or 0) == int(job_id):

            return j

    return None

def status_payload() -> Dict[str, Any]:

    g = gate()

    cycle = current_cycle_no()

    report = load_report(cycle) if cycle else {}

    return {

        "ok": True,

        "gate": g,

        "cycle": cycle,

        "phase": store.get_meta(META_PHASE, "idle") or "idle",

        "lab_active": is_lab_active(),

        "report": report,

        "posts": store.list_posts(20),

    }

def _note(subsystem: str, exc: BaseException, fault_code: str, **ctx: Any) -> None:

    try:

        from pipeline.error_notebook import note_exception

        note_exception(

            subsystem=subsystem,

            exc=exc,

            fault_code=fault_code,

            channel_id=ctx.get("channel_id"),

            context={k: v for k, v in ctx.items() if k != "channel_id"},

        )

    except Exception:

        logger.debug("error notebook skipped", exc_info=True)

def _set_phase(phase: str, detail: str = "") -> None:

    store.set_meta(META_PHASE, phase)

    try:

        from pipeline.live_activity import set_phase

        set_phase(phase, detail or phase)

    except Exception:

        pass

def _reuse_recent_completed(video_type: str) -> Optional[Dict[str, Any]]:

    """Reuse a short/long already shipped in the last few live-lab cycles."""

    n = current_cycle_no()

    for cyc in range(n, max(0, n - 4), -1):

        rep = load_report(cyc) or {}

        job = next(

            (

                j

                for j in (rep.get("jobs") or [])

                if j.get("video_type") == video_type and j.get("path")

            ),

            None,

        )

        if not job:

            continue

        try:

            if not Path(str(job["path"])).exists():

                continue

        except Exception:

            continue

        ups = [u for u in (rep.get("uploads") or []) if u.get("video_type") == video_type]

        yt_ok = False

        for u in ups:

            for r in u.get("results") or []:

                if r.get("platform") == "youtube" and r.get("ok"):

                    yt_ok = True

        urls = [w for w in (rep.get("watch_urls") or []) if w.get("video_type") == video_type]

        return {

            "job": job,

            "uploads": ups,

            "watch_urls": urls,

            "youtube_ok": yt_ok,

            "cycle": cyc,

        }

    return None

def _find_ready_local_job(video_type: str) -> Optional[Dict[str, Any]]:

    """Newest local job already composed and waiting for upload."""

    try:

        jobs = store.list_jobs(80)

    except Exception:

        return None

    for j in jobs:

        if str(j.get("video_type") or "") != video_type:

            continue

        status = str(j.get("upload_status") or "")

        if status not in ("ready_to_upload", "generated"):

            continue

        path = Path(str(j.get("local_path") or ""))

        try:

            if path.exists() and path.stat().st_size > 50000:

                return j

        except OSError:

            continue

    return None

def _incomplete_cycle_to_resume() -> Optional[int]:

    """If soak died after long compose/localize, resume same cycle (do not burn a new topic)."""

    n = current_cycle_no()

    if n <= 0:

        return None

    rep = load_report(n) or {}

    phase = str(rep.get("phase") or store.get_meta(META_PHASE, "") or "")

    has_long_job = any(j.get("video_type") == "long" for j in (rep.get("jobs") or []))

    long_yt_ok = False

    for u in rep.get("uploads") or []:

        if u.get("video_type") != "long":

            continue

        for r in u.get("results") or []:

            if r.get("platform") == "youtube" and r.get("ok"):

                long_yt_ok = True

    ready = _find_ready_local_job("long")

    if ready and not long_yt_ok and (not has_long_job or phase in ("localize", "starting", "generate_long", "upload_long")):

        return n

    return None

def run_cycle(channel: Dict[str, Any], *, cycle: int, resume: bool = False) -> Dict[str, Any]:

    """Blocking full circle: short + long generate, live upload both, then wait for comments."""

    store.set_meta(META_ACTIVE, "1")

    store.set_meta(META_CYCLE, str(cycle))

    if resume:

        report = load_report(cycle) or {}

        report.setdefault("cycle", cycle)

        report.setdefault("jobs", [])

        report.setdefault("uploads", [])

        report.setdefault("errors", [])

        report.setdefault("audits", {})

        report.setdefault("watch_urls", [])

        report["phase"] = "resuming"

        report["resumed_at"] = _now()

    else:

        report = {

            "cycle": cycle,

            "started_at": _now(),

            "phase": "starting",

            "live_publish": not bool(settings.dry_run_publish),

            "jobs": [],

            "uploads": [],

            "errors": [],

            "audits": {},

            "comment_pass": None,

            "watch_urls": [],

        }

    save_report(report)

    g = gate(channel)

    if not g.get("ok"):

        report["phase"] = "blocked"

        report["errors"] = list(g.get("blockers") or [])

        save_report(report)

        store.set_meta(META_ACTIVE, "0")

        store.set_meta(META_PHASE, "blocked")

        return report

    # Cross-cycle circuit: stop burning APIs on the same hard fault

    try:

        from pipeline.cycle_circuit import preflight_for_cycle, record_cycle_outcome

        circ = preflight_for_cycle()

        report["circuit"] = {

            "safe_mode": circ.get("safe_mode"),

            "reason": circ.get("reason") or circ.get("state", {}).get("safe_mode_reason"),

            "hard_stop": not circ.get("ok"),

        }

        if not circ.get("ok"):

            report["phase"] = "blocked"

            report["errors"] = list(circ.get("blockers") or ["circuit_hard_stop"])

            save_report(report)

            store.set_meta(META_ACTIVE, "0")

            store.set_meta(META_PHASE, "blocked")

            try:

                from pipeline.live_activity import log as live_log

                live_log("lab", f"Circuit HARD STOP: {report['errors'][0]}", level="error")

            except Exception:

                pass

            return report

        if circ.get("safe_mode"):

            # Do NOT disable Agnes permanently — cooldown waits 1–2h then retries,

            # then image fallback. safe_mode only signals "be careful with quota".

            channel = dict(channel)

            channel["_agnes_respect_cooldown"] = True

            logger.warning(

                "Circuit note — Agnes will use cooldown waits (not hard-disabled). reason=%s",

                circ.get("reason"),

            )

            try:

                from pipeline.live_activity import log as live_log

                live_log(

                    "lab",

                    f"Agnes cooldown policy on: {circ.get('reason')}",

                    level="warn",

                )

            except Exception:

                pass

    except Exception as circ_exc:

        logger.warning("cycle circuit preflight skipped: %s", circ_exc)

    set_live_publish(True)

    report["live_publish"] = True

    channel = store.get_channel(int(channel["id"])) or channel

    # Preserve cooldown flag across channel reload

    if report.get("circuit", {}).get("safe_mode"):

        channel = dict(channel)

        channel["_agnes_respect_cooldown"] = True

    from pipeline.live_activity import is_cancel_requested, log as live_log, note_api

    from pipeline.video_pipeline import generate_video

    from publishers.upload_service import upload_job

    try:

        live_log(

            "lab",

            f"Live Lab cycle {cycle} {'resume' if resume else 'start'}",

            force_new=True,

        )

    except Exception:

        pass

    for video_type in ("short", "long"):

        if is_cancel_requested():

            report["phase"] = "cancelled"

            report["errors"].append("cancelled_by_user")

            save_report(report)

            store.set_meta(META_ACTIVE, "0")

            store.set_meta(META_PHASE, "cancelled")

            return report

        _set_phase(f"generate_{video_type}", f"Live Lab cycle {cycle}: generating {video_type}")

        note_api("pipeline", f"live_lab_{video_type}", "start")

        reused = _reuse_recent_completed(video_type)

        if reused and reused.get("youtube_ok") and video_type == "short":

            logger.info("Skip short generate/upload — already shipped this soak")

            if not any(j.get("video_type") == "short" for j in report.get("jobs") or []):

                report["jobs"].append(reused["job"])

            for up in reused.get("uploads") or []:

                if not any(

                    u.get("video_type") == "short" and u.get("job_id") == up.get("job_id")

                    for u in report.get("uploads") or []

                ):

                    report["uploads"].append(up)

            for url in reused.get("watch_urls") or []:

                if url not in (report.get("watch_urls") or []):

                    report["watch_urls"].append(url)

            save_report(report)

            continue

        # Resume: long already on disk (compose+localize done) — skip regenerate

        ready_job = _find_ready_local_job(video_type) if video_type == "long" else None

        long_upload_done = any(

            u.get("video_type") == "long"

            and any(r.get("platform") == "youtube" and r.get("ok") for r in (u.get("results") or []))

            for u in report.get("uploads") or []

        )

        result = None

        last_exc: Optional[BaseException] = None

        if ready_job and video_type == "long" and not long_upload_done:

            logger.info(

                "Resume long from ready job #%s — skip generate",

                ready_job.get("id"),

            )

            try:

                live_log(

                    "lab",

                    f"Resume long job #{ready_job.get('id')} — skip generate, go to upload",

                    dest=str(ready_job.get("local_path") or ""),

                    force_new=True,

                )

            except Exception:

                pass

            result = {

                "job_id": int(ready_job["id"]),

                "path": ready_job.get("local_path"),

                "title": ready_job.get("title"),

                "description": ready_job.get("description"),

                "tags": ready_job.get("tags"),

                "thumbnail": ready_job.get("thumbnail_path"),

                "topic": ready_job.get("topic") or "",

                "video_type": "long",

            }

        else:

            for attempt in range(2):

                try:

                    result = generate_video(channel, video_type=video_type)

                    last_exc = None

                    break

                except Exception as exc:

                    last_exc = exc

                    logger.exception("live lab generate %s attempt %s failed", video_type, attempt + 1)

                    _note(

                        "live_lab",

                        exc,

                        f"generate_{video_type}_failed",

                        channel_id=channel.get("id"),

                        attempt=attempt + 1,

                    )

                    if attempt == 0:

                        _set_phase(

                            f"generate_{video_type}",

                            f"Retry {video_type}: reuse passed clips, regen only agent-failed beats",

                        )

        if last_exc is not None or not result:

            report["phase"] = "failed"

            report["errors"].append(f"generate_{video_type}: {last_exc}")

            save_report(report)

            store.set_meta(META_ACTIVE, "0")

            store.set_meta(META_PHASE, "failed")

            try:

                from pipeline.cycle_circuit import record_cycle_outcome

                record_cycle_outcome(

                    cycle=cycle,

                    phase="failed",

                    error=f"generate_{video_type}: {last_exc}",

                )

            except Exception:

                pass

            raise RuntimeError(f"generate_{video_type}: {last_exc}")

        job_id = int(result.get("job_id") or 0)

        job_row = _job_by_id(job_id) or {}

        issues = audit_job(job_row or {

            "title": result.get("title"),

            "description": result.get("description"),

            "tags": result.get("tags"),

            "local_path": result.get("path"),

            "thumbnail_path": result.get("thumbnail"),

        })

        job_entry = {

            "job_id": job_id,

            "video_type": video_type,

            "title": result.get("title") or job_row.get("title"),

            "topic": result.get("topic"),

            "path": result.get("path") or job_row.get("local_path"),

            "thumbnail": result.get("thumbnail") or job_row.get("thumbnail_path"),

            "issues": issues,

        }

        if not any(int(j.get("job_id") or 0) == job_id for j in report.get("jobs") or []):

            report["jobs"].append(job_entry)

        report["audits"][video_type] = issues

        save_report(report)

        if long_upload_done and video_type == "long":

            continue

        _set_phase(f"upload_{video_type}", f"Live Lab cycle {cycle}: uploading {video_type}")

        try:

            live_log("upload", f"Upload {video_type} job #{job_id}", dest=str(result.get("path") or ""), force_new=True)

        except Exception:

            pass

        try:

            up = upload_job(job_id, channel)

        except Exception as exc:

            logger.exception("live lab upload %s failed", video_type)

            _note("live_lab", exc, f"upload_{video_type}_failed", channel_id=channel.get("id"))

            up = {"ok": False, "error": str(exc), "results": []}

        report["uploads"].append({"video_type": video_type, "job_id": job_id, **up})

        for r in up.get("results") or []:

            url = str(r.get("url") or "")

            if url and not url.startswith("dry-run://"):

                report["watch_urls"].append({"platform": r.get("platform"), "url": url, "video_type": video_type})

            if r.get("dry_run"):

                report["errors"].append(f"{video_type} still dry-run on {r.get('platform')}")

            if not r.get("ok"):

                report["errors"].append(f"{video_type} {r.get('platform')}: {r.get('error')}")

        save_report(report)

        note_api("pipeline", f"live_lab_{video_type}", "ok" if up.get("ok") else "fail")

    _set_phase("waiting_comments", "Upload done — comment on the YouTube video, then press Check replies")

    report["phase"] = "waiting_comments"

    report["waiting_since"] = _now()

    save_report(report)

    # Stay "active" so idle pregen does not steal the PC, but allow comment pass.

    return report

def start_cycle_background() -> Dict[str, Any]:

    g = gate()

    if not g.get("ok"):

        return {"ok": False, "error": "not_ready", "gate": g}

    phase = store.get_meta(META_PHASE, "") or "idle"

    if phase.startswith("generate") or phase.startswith("upload") or phase in ("starting", "comment_pass", "resuming"):

        return {"ok": False, "error": "already_running", "gate": g}

    from pipeline.live_activity import run_in_background

    ch = store.get_channel(int(g["channel_id"]))

    if not ch:

        return {"ok": False, "error": "channel_missing", "gate": g}

    resume_n = _incomplete_cycle_to_resume()

    if resume_n:

        nxt = resume_n

        resume = True

        # Clear stuck localize / crashed state so lab can continue

        store.set_meta(META_PHASE, "resuming")

    else:

        nxt = current_cycle_no() + 1

        resume = False

        store.set_meta(META_PHASE, "starting")

    store.set_meta(META_CYCLE, str(nxt))

    store.set_meta(META_ACTIVE, "1")

    set_live_publish(True)

    def _job():

        return run_cycle(ch, cycle=nxt, resume=resume)

    try:

        job_id = run_in_background(

            _job,

            kind="live_lab",

            channel_id=int(ch["id"]),

            channel_name=str(ch.get("youtube_name") or ch.get("facebook_name") or ""),

        )

    except RuntimeError as exc:

        store.set_meta(META_ACTIVE, "0")

        # Don't leave phase stuck at starting/resuming — blocks all future starts

        store.set_meta(META_PHASE, "idle")

        return {"ok": False, "error": str(exc), "gate": g}

    return {

        "ok": True,

        "started": True,

        "job_id": job_id,

        "cycle": nxt,

        "resume": resume,

        "gate": gate(),

    }

def run_comment_check() -> Dict[str, Any]:

    from publishers.comment_reply_agent import run_comment_reply_pass

    _set_phase("comment_pass", "Scanning comments and posting replies")

    try:

        res = run_comment_reply_pass(max_posts=8, max_replies_each=4)

    except Exception as exc:

        logger.exception("live lab comment pass failed")

        _note("live_lab", exc, "comment_pass_failed")

        res = {"ok": False, "error": str(exc), "handled": 0, "results": []}

    report = load_report() or {}

    report["comment_pass"] = {**res, "at": _now()}

    handled = int(res.get("handled") or 0)

    if handled > 0:

        report["phase"] = "complete"

        store.set_meta(META_PHASE, "complete")

        store.set_meta(META_ACTIVE, "0")

    else:

        report["phase"] = "waiting_comments"

        store.set_meta(META_PHASE, "waiting_comments")

        # keep lab active so next check is obvious

    save_report(report)

    return {"ok": bool(res.get("ok")), "report": report, "comment_pass": res}

def start_comment_check_background() -> Dict[str, Any]:

    from pipeline.live_activity import run_in_background

    chs = store.list_channels()

    name = (chs[0].get("youtube_name") if chs else "") or ""

    def _job():

        return run_comment_check()

    try:

        job_id = run_in_background(

            _job,

            kind="comment_pass",

            channel_id=int(chs[0]["id"]) if chs else None,

            channel_name=str(name),

        )

    except RuntimeError as exc:

        return {"ok": False, "error": str(exc)}

    return {"ok": True, "started": True, "job_id": job_id}

def stop_lab() -> Dict[str, Any]:

    store.set_meta(META_ACTIVE, "0")

    store.set_meta(META_PHASE, "cancelled")

    try:

        from pipeline.live_activity import request_stop

        request_stop()

    except Exception:

        pass

    report = load_report() or {}

    if report:

        report["phase"] = "cancelled"

        save_report(report)

    return status_payload()

