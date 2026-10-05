from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from app import db as store
from app.api_client import LicenseClient
from app.config import settings

logger = logging.getLogger(__name__)


def upload_job(job_id: int, channel: Dict[str, Any]) -> Dict[str, Any]:
    jobs = {j["id"]: j for j in store.list_jobs(500)}
    job = jobs.get(job_id)
    if not job:
        return {"ok": False, "error": "job_not_found"}

    path = Path(job.get("local_path") or "")
    if not path.exists():
        store.update_job(job_id, upload_status="missing_file", error="file_not_found")
        return {"ok": False, "error": "file_not_found"}

    from pipeline.lang_destinations import resolve_destination
    from pipeline.lang_entitlement import channel_languages
    from pipeline.lang_config import folder_for_lang
    import json

    results = []

    # 1. Master (English) upload
    ch_en = resolve_destination(channel, "en")
    if ch_en.get("youtube_name") or ch_en.get("youtube_session"):
        results.append(_upload_youtube(job, ch_en, path))
    if ch_en.get("facebook_name") or ch_en.get("facebook_session"):
        results.append(_upload_facebook(job, ch_en, path))
    if ch_en.get("tiktok_name") or ch_en.get("tiktok_session"):
        results.append(_upload_tiktok(job, ch_en, path))

    # 2. Localized languages upload
    unlocked = channel_languages(channel)
    localized_root = path.parent / "LOCALIZED"
    for code in unlocked:
        if code == "en":
            continue
        folder_name = folder_for_lang(code)
        lang_video = localized_root / folder_name / "video.mp4"
        if not lang_video.exists():
            lang_video = localized_root / code / "video.mp4"
        if not lang_video.exists():
            continue

        ch_lang = resolve_destination(channel, code)
        loc_job = dict(job)
        loc_meta_path = lang_video.parent / "meta.json"
        if loc_meta_path.exists():
            try:
                loc_meta = json.loads(loc_meta_path.read_text(encoding="utf-8"))
                if loc_meta.get("title"):
                    loc_job["title"] = loc_meta["title"]
                if loc_meta.get("description"):
                    loc_job["description"] = loc_meta["description"]
            except Exception:
                pass

        if ch_lang.get("youtube_name") or ch_lang.get("youtube_session"):
            res = _upload_youtube(loc_job, ch_lang, lang_video)
            res["platform"] = f"youtube_{code}"
            results.append(res)
        if ch_lang.get("facebook_name") or ch_lang.get("facebook_session"):
            res = _upload_facebook(loc_job, ch_lang, lang_video)
            res["platform"] = f"facebook_{code}"
            results.append(res)
        if ch_lang.get("tiktok_name") or ch_lang.get("tiktok_session"):
            res = _upload_tiktok(loc_job, ch_lang, lang_video)
            res["platform"] = f"tiktok_{code}"
            results.append(res)

    if not results:
        results.append({"platform": "none", "ok": False, "error": "no_platform"})

    ok_any = any(r.get("ok") for r in results)
    remote = next((r.get("url") for r in results if r.get("url")), None)
    status = "uploaded" if ok_any else "upload_failed"
    if settings.dry_run_publish and ok_any:
        status = "dry_run_uploaded"

    store.update_job(
        job_id,
        upload_status=status,
        remote_url=remote,
        uploaded_at=datetime.now().isoformat(),
        platform=",".join(r.get("platform", "") for r in results),
        error="; ".join(r.get("error", "") for r in results if r.get("error")),
    )

    for r in results:
        if r.get("ok") and r.get("url"):
            plat = str(r.get("platform") or "")
            l_code = "en"
            if "_" in plat:
                l_code = plat.split("_")[-1]
            try:
                store.upsert_post_from_upload(
                    job_id=job_id,
                    channel_id=int(channel.get("id") or 0),
                    lang_code=l_code,
                    platform=plat,
                    title=str(job.get("title") or ""),
                    remote_url=str(r.get("url") or ""),
                    local_path=str(path),
                )
            except Exception as exc:
                logger.debug("upsert_post_from_upload failed: %s", exc)

    session = store.get_session()
    if session:
        try:
            LicenseClient(session["api_base_url"], session["token"]).sync_job(
                {
                    "channel_name": channel.get("youtube_name") or channel.get("facebook_name") or channel.get("tiktok_name"),
                    "video_type": job.get("video_type"),
                    "title": job.get("title"),
                    "description": job.get("description"),
                    "platform": ",".join(r.get("platform", "") for r in results),
                    "upload_status": status,
                    "remote_url": remote,
                    "local_path": str(path),
                    "uploaded_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
                }
            )
        except Exception as exc:
            logger.warning("sync after upload failed: %s", exc)

    return {"ok": ok_any, "results": results}


def _upload_youtube(job: Dict[str, Any], channel: Dict[str, Any], path: Path) -> Dict[str, Any]:
    if settings.dry_run_publish:
        logger.info("DRY RUN YouTube upload: %s", path)
        return {"ok": True, "platform": "youtube", "url": f"dry-run://youtube/{path.name}"}
    try:
        from publishers.youtube_uploader import upload_youtube

        url = upload_youtube(path, job, channel)
        return {"ok": True, "platform": "youtube", "url": url}
    except Exception as exc:
        logger.exception("youtube upload failed")
        return {"ok": False, "platform": "youtube", "error": str(exc)}


def _upload_facebook(job: Dict[str, Any], channel: Dict[str, Any], path: Path) -> Dict[str, Any]:
    if settings.dry_run_publish:
        logger.info("DRY RUN Facebook upload: %s", path)
        return {"ok": True, "platform": "facebook", "url": f"dry-run://facebook/{path.name}"}
    try:
        from publishers.facebook_uploader import upload_facebook

        url = upload_facebook(path, job, channel)
        return {"ok": True, "platform": "facebook", "url": url}
    except Exception as exc:
        logger.exception("facebook upload failed")
        return {"ok": False, "platform": "facebook", "error": str(exc)}


def _upload_tiktok(job: Dict[str, Any], channel: Dict[str, Any], path: Path) -> Dict[str, Any]:
    if settings.dry_run_publish:
        logger.info("DRY RUN TikTok upload: %s", path)
        return {"ok": True, "platform": "tiktok", "url": f"dry-run://tiktok/{path.name}"}
    try:
        from publishers.tiktok_uploader import upload_tiktok

        url = upload_tiktok(path, job, channel)
        return {"ok": True, "platform": "tiktok", "url": url}
    except Exception as exc:
        logger.exception("tiktok upload failed")
        return {"ok": False, "platform": "tiktok", "error": str(exc)}

