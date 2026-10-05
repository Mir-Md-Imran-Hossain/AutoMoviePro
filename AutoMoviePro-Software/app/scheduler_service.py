from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    HAS_APSCHEDULER = True
    _APSCHEDULER_ERROR = ""
except (ImportError, ModuleNotFoundError) as exc:
    BackgroundScheduler = None  # type: ignore
    CronTrigger = None  # type: ignore
    HAS_APSCHEDULER = False
    _APSCHEDULER_ERROR = (
        f"{exc}. APScheduler is required for autonomous background cadence and timed publishing. "
        f"Please install it with: pip install 'APScheduler>=3.10.4,<4.0.0' or pip install -r requirements.txt"
    )

from app import db as store
from app.api_client import LicenseClient
from app.config import settings
from app.generation_guard import is_busy as generation_is_busy
from app.generation_guard import release as generation_release
from app.generation_guard import try_acquire as generation_try_acquire
from publishers.upload_meta import match_upload_window

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self) -> None:
        if not HAS_APSCHEDULER or BackgroundScheduler is None:
            logger.warning(
                "APScheduler dependency missing: %s. "
                "SchedulerService operating in degraded mode. "
                "Timed autonomous jobs will be disabled.",
                _APSCHEDULER_ERROR,
            )
            self.scheduler = None
        else:
            self.scheduler = BackgroundScheduler()
        self._started = False
        # Legacy mirror of generation_guard for local fast-path checks (C01-B: guard is authority)
        self._generating = False

    @property
    def is_available(self) -> bool:
        """Indicates whether APScheduler is installed and initialized."""
        return HAS_APSCHEDULER and self.scheduler is not None

    def is_generation_busy(self) -> bool:
        """Whether protected generate_video resource is held (C01-B)."""
        return bool(generation_is_busy() or self._generating)

    def start(self) -> None:
        if not self.is_available or self.scheduler is None:
            logger.warning(
                "Cannot start autonomous scheduler: APScheduler is not available. %s",
                _APSCHEDULER_ERROR,
            )
            return
        if self._started:
            return
        self.scheduler.add_job(self.heartbeat_job, "interval", minutes=5, id="heartbeat", replace_existing=True)
        # Timed upload check every minute
        self.scheduler.add_job(self.timed_upload_job, "interval", minutes=1, id="timed_upload", replace_existing=True)
        # Idle pre-generation while PC is free
        self.scheduler.add_job(
            self.idle_pregenerate_job,
            "interval",
            minutes=2,
            id="idle_pregenerate",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.comment_reply_job,
            "interval",
            minutes=20,
            id="comment_reply",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.captcha_watch_job,
            "interval",
            seconds=30,
            id="captcha_watch",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.asset_local_sync_job,
            "interval",
            minutes=30,
            id="asset_local_sync",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.hidden_engage_job,
            CronTrigger(hour=12, minute=0),
            id="hidden_engage",
            replace_existing=True,
        )
        # Staggered human trust-browse (≥5 min/hour) — check every 2 minutes
        self.scheduler.add_job(
            self.trust_browse_job,
            "interval",
            minutes=2,
            id="trust_browse",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.trust_browse_sync_job,
            "interval",
            minutes=15,
            id="trust_browse_sync",
            replace_existing=True,
        )
        # C06-G: customer job queue tick — orchestration only (no content generation here)
        self.scheduler.add_job(
            self.customer_queue_tick_job,
            "interval",
            seconds=30,
            id="customer_queue_tick",
            replace_existing=True,
        )
        # Keep legacy id so restarts replace old gen_upload job
        try:
            self.scheduler.remove_job("gen_upload")
        except Exception:
            pass
        self.scheduler.start()
        self._started = True
        logger.info("Scheduler started (idle pregen + timed upload + customer queue tick + comment replies)")

    def stop(self) -> None:
        if self._started and self.scheduler is not None:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                pass
        self._started = False

    def heartbeat_job(self) -> None:
        session = store.get_session()
        if not session:
            return
        try:
            from app.customer_auth import is_session_expired, clear_session, refresh_remote_account_state

            if is_session_expired(session):
                clear_session()
                return
            LicenseClient(session["api_base_url"], session["token"]).heartbeat()
            refresh_remote_account_state()
        except Exception as exc:
            logger.warning("heartbeat failed: %s", exc)

    def captcha_watch_job(self) -> None:
        try:
            from publishers.captcha_alerts import tick_captcha_watch

            tick_captcha_watch()
        except Exception as exc:
            logger.debug("captcha watch: %s", exc)

    def asset_local_sync_job(self) -> None:
        try:
            from pipeline.asset_archive import try_local_server_sync

            res = try_local_server_sync()
            if res.get("moved"):
                logger.info("Asset local sync moved %s bundles → %s", res.get("moved"), res.get("dest"))
        except Exception as exc:
            logger.debug("asset local sync: %s", exc)

    def hidden_engage_job(self) -> None:
        session = store.get_session()
        if not session:
            return
        today = datetime.now().date().isoformat()
        if store.get_meta("last_engage_day") == today:
            return
        try:
            from hidden_engage.worker import run_daily_engagement

            run_daily_engagement()
            store.set_meta("last_engage_day", today)
        except Exception as exc:
            logger.exception("hidden engage failed: %s", exc)

    def trust_browse_job(self) -> None:
        """Start a background trust-browse window when the staggered plan says so."""
        session = store.get_session()
        if not session:
            return
        try:
            from hidden_engage.trust_browse import tick_trust_browse

            res = tick_trust_browse()
            if res.get("started"):
                logger.info("trust browse started: %s", res)
        except Exception as exc:
            logger.exception("trust browse tick failed: %s", exc)

    def trust_browse_sync_job(self) -> None:
        session = store.get_session()
        if not session:
            return
        try:
            from hidden_engage.activity_log import sync_unsynced_to_website

            res = sync_unsynced_to_website()
            if res.get("synced"):
                logger.info("trust browse log synced: %s", res.get("synced"))
        except Exception as exc:
            logger.debug("trust browse sync: %s", exc)

    def comment_reply_job(self) -> None:
        session = store.get_session()
        if not session:
            return
        try:
            from publishers.comment_reply_agent import run_comment_reply_pass

            res = run_comment_reply_pass(max_posts=4, max_replies_each=2)
            if res.get("handled"):
                logger.info("comment reply pass: %s", res)
        except Exception as exc:
            logger.exception("comment reply failed: %s", exc)

    # ---- C06-G customer queue (orchestration only) ----

    def customer_queue_tick_job(self) -> None:
        """Claim+execute at most one customer queued job when generation_guard is free.

        C07-SCHED: also process due ScheduledPublish intents (timing only → C07-PUB).
        """
        try:
            from app.customer_job_automation import scheduler_tick

            res = scheduler_tick(worker_id="apscheduler:customer_queue_tick")
            if res.get("executed"):
                logger.info("C06-G queue tick executed job_id=%s", res.get("job_id"))
        except Exception as exc:
            logger.warning("C06-G customer_queue_tick failed: %s", exc)
        # C07-SCHED — extend existing scheduler authority (no second scheduler)
        try:
            from app.customer_publish_schedule import process_due_schedules

            sres = process_due_schedules(worker_id="apscheduler:publish_schedule", max_one=True)
            if sres.get("count"):
                logger.info("C07-SCHED due schedules processed count=%s", sres.get("count"))
        except Exception as exc:
            logger.warning("C07-SCHED publish schedule tick failed: %s", exc)

    # ---- Idle pre-generation (PC free → build queue) ----

    def idle_pregenerate_job(self) -> None:
        session = store.get_session()
        if not session:
            return
        if store.get_meta("live_lab_active") == "1":
            return
        # C01-B: refuse if customer Generate or another generation holds the shared slot
        if generation_is_busy() or self._generating:
            return
        try:
            from pipeline.live_activity import is_cancel_requested
            from pipeline.pc_load import should_run_background_generate
        except Exception:
            is_cancel_requested = lambda: False  # type: ignore
            should_run_background_generate = None  # type: ignore

        if is_cancel_requested():
            return
        channels = [c for c in store.list_channels() if c.get("enabled")]
        for channel in channels:
            # Cadence: at most 1 ready short + 1 ready long in the queue (daily publish 1+1)
            for video_type in ("short", "long"):
                limit = (
                    int(getattr(settings, "daily_short_limit", 1) or 1)
                    if video_type == "short"
                    else int(getattr(settings, "daily_long_limit", 1) or 1)
                )
                pending = store.count_pending_upload_jobs(int(channel["id"]), video_type)
                if pending >= max(1, limit):
                    continue
                day_up = f"upload_{channel['id']}_{video_type}_{datetime.now().date().isoformat()}"
                if store.get_meta(day_up) == "1":
                    # Already published this type today — do not pregen another
                    continue
                decision = (
                    should_run_background_generate(
                        has_pending_job=False,
                        cancel_requested=False,
                    )
                    if should_run_background_generate
                    else {"ok": True, "reason": "no_load_module"}
                )
                if not decision.get("ok"):
                    logger.debug(
                        "idle pregen paused (%s) ch=%s type=%s",
                        decision.get("reason"),
                        channel.get("id"),
                        video_type,
                    )
                    return
                self._pregenerate_one(channel, video_type)
                return  # one heavy generate per tick

    def _pregenerate_one(self, channel: Dict[str, Any], video_type: str) -> None:
        day_key = f"pregen_{channel['id']}_{video_type}_{datetime.now().date().isoformat()}"
        if not generation_try_acquire("idle_pregen"):
            logger.debug("idle pregen skipped — generation slot busy")
            return
        self._generating = True
        try:
            from pipeline.video_pipeline import generate_video

            logger.info(
                "Idle pre-generate start ch=%s type=%s",
                channel.get("id"),
                video_type,
            )
            result = generate_video(channel, video_type=video_type)
            job_id = result.get("job_id")
            if job_id:
                # H4: do not override generate_video publishability/packaging boundary.
                # ready_to_upload is set only inside generate_video after gates (+ loc packages).
                store.set_meta(day_key, str(job_id))
                logger.info(
                    "Idle pre-generate done job_id=%s upload_status=%s",
                    job_id,
                    result.get("upload_status"),
                )
        except Exception as exc:
            logger.exception("idle pregenerate failed: %s", exc)
        finally:
            self._generating = False
            generation_release("idle_pregen")

    # ---- Timed upload (use queue; fallback generate) ----

    def timed_upload_job(self) -> None:
        """Alias kept for clarity — replaces old generation_and_upload_job."""
        self.generation_and_upload_job()

    def generation_and_upload_job(self) -> None:
        session = store.get_session()
        if not session:
            return
        if store.get_meta("live_lab_active") == "1":
            return
        now = datetime.now().strftime("%H:%M")
        channels = [c for c in store.list_channels() if c.get("enabled")]
        for channel in channels:
            self._maybe_upload(channel, "short", channel.get("short_upload_time") or "12:00", now)
            self._maybe_upload(channel, "long", channel.get("long_upload_time") or "18:00", now)

    @staticmethod
    def _is_time_or_overdue(now_hhmm: str, target_hhmm: str) -> bool:
        """
        True if target upload time has arrived or passed today.
        Guarantees 1 Short + 1 Long per day even if computer was asleep or off at exact minute.
        """
        try:
            nh, nm = [int(x) for x in (now_hhmm or "00:00")[:5].split(":")]
            th, tm = [int(x) for x in (target_hhmm or "00:00")[:5].split(":")]
            now_m = nh * 60 + nm
            tgt_m = th * 60 + tm
            return now_m >= tgt_m
        except Exception:
            return False

    def _maybe_upload(
        self,
        channel: Dict[str, Any],
        video_type: str,
        target_time: str,
        now: str,
    ) -> None:
        if not self._is_time_or_overdue(now, target_time):
            return
        day_key = f"upload_{channel['id']}_{video_type}_{datetime.now().date().isoformat()}"
        legacy = f"gen_{channel['id']}_{video_type}_{datetime.now().date().isoformat()}"
        if store.get_meta(day_key) == "1" or store.get_meta(legacy) == "1":
            return
        try:
            from publishers.upload_service import upload_job

            job_id = self._claim_or_generate(channel, video_type)
            if not job_id:
                return
            result = upload_job(int(job_id), channel) or {}
            # Only mark the day complete when at least one platform succeeded.
            # Failed / quality-blocked uploads must remain retryable.
            if result.get("ok"):
                store.set_meta(day_key, "1")
                store.set_meta(legacy, "1")
            else:
                logger.warning(
                    "timed upload not marked done (ch=%s type=%s): %s",
                    channel.get("id"),
                    video_type,
                    result.get("error") or result.get("status") or "failed",
                )
        except Exception as exc:
            logger.exception("timed upload failed: %s", exc)
            try:
                from pipeline.error_notebook import note_exception

                note_exception(
                    subsystem="scheduler",
                    exc=exc,
                    fault_code="timed_upload_failed",
                    channel_id=int(channel.get("id") or 0) or None,
                    context={"video_type": video_type, "target": target_time},
                )
            except Exception:
                pass

    def _claim_or_generate(self, channel: Dict[str, Any], video_type: str) -> Optional[int]:
        pending = store.list_pending_upload_jobs(int(channel["id"]), video_type, limit=1)
        if pending:
            return int(pending[0]["id"])
        # Fallback: generate now if queue empty (PC may have been busy all day)
        if generation_is_busy() or self._generating:
            return None
        if not generation_try_acquire("timed_fallback"):
            return None
        self._generating = True
        try:
            from pipeline.video_pipeline import generate_video

            result = generate_video(channel, video_type=video_type)
            jid = result.get("job_id")
            return int(jid) if jid else None
        finally:
            self._generating = False
            generation_release("timed_fallback")
