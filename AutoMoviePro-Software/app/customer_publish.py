"""C07-PUB — Customer Publishing Foundation (compose / admit / observe).

Connects approved production output to a provider-neutral publishing boundary.
Does NOT create second quality / retry / idempotency / ownership / event / secret engines.
Does NOT schedule. Does NOT regenerate media. Does NOT use browser automation.

States preserved:
  APPROVED ≠ READY_TO_UPLOAD ≠ UPLOADED(UPLOAD_ACCEPTED) ≠ REMOTE_PROCESSING ≠ PUBLISHED
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.config import DATA_DIR
from app.customer_job import get_job, job_owned_by_channels, sanitize_customer_error, to_customer_view
from app.customer_job_automation import append_lifecycle_event
from app.customer_preview_approval import compute_revision_id

CONTRACT_VERSION = "C07-PUB.1"
PUBLISH_STAGE = "c07_customer_publish"
PUBLISH_CONTRACT = "c07-pub-1.0.0"

# Distinct publication FSM (never collapse into one boolean)
PUBLISH_STATES = (
    "NOT_STARTED",
    "VALIDATION_FAILED",
    "AUTH_REQUIRED",
    "PUBLISH_REQUESTED",
    "UPLOAD_ACCEPTED",  # provider accepted upload — NOT published
    "REMOTE_PROCESSING",
    "RECONCILIATION_REQUIRED",
    "PUBLISHED",
    "FAILED",
)

PUBLISH_EVENT_TYPES = (
    "PUBLISH_REQUESTED",
    "PUBLISH_VALIDATION_FAILED",
    "PUBLISH_AUTH_REQUIRED",
    "PUBLISH_STARTED",
    "PUBLISH_UPLOAD_ACCEPTED",
    "PUBLISH_REMOTE_PROCESSING",
    "PUBLISH_REMOTE_SUCCEEDED",
    "PUBLISH_REMOTE_FAILED",
    "PUBLISH_RECONCILIATION_REQUIRED",
    "PUBLISH_FAILED",
    "PUBLISH_COMPLETED",
)

RECOVERABLE_ERRORS = frozenset(
    {
        "TRANSIENT_PROVIDER_FAILURE",
        "RATE_LIMITED",
        "NETWORK_FAILURE",  # recoverable only after reconciliation proves no prior accept
    }
)

_LOCK = threading.Lock()
_REAL_PROVIDER_CALLS = 0  # process counter for offline proof


def _now() -> str:
    return datetime.now().isoformat()


def real_provider_call_count() -> int:
    return int(_REAL_PROVIDER_CALLS)


def reset_real_provider_call_count() -> None:
    global _REAL_PROVIDER_CALLS
    _REAL_PROVIDER_CALLS = 0


def ensure_publish_columns() -> None:
    """Soft-migrate jobs for C07-PUB publication fields (extend existing jobs table)."""
    from app import db as store

    with store.db() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        migrations = [
            ("publish_status", "TEXT"),
            ("publish_provider", "TEXT"),
            ("publish_provider_video_id", "TEXT"),
            ("publish_provider_url", "TEXT"),
            ("publish_fingerprint", "TEXT"),
            ("publish_error_code", "TEXT"),
            ("publish_error", "TEXT"),
            ("publish_package_json", "TEXT"),
            ("publish_observed_at", "TEXT"),
            ("publish_attempt_count", "INTEGER DEFAULT 0"),
            ("publish_mock", "INTEGER DEFAULT 0"),
            ("publish_updated_at", "TEXT"),
        ]
        for name, typ in migrations:
            if name not in cols:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {typ}")


def scrub_secrets(obj: Any) -> Any:
    """Never expose OAuth/tokens in projections, events, or results."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if any(x in lk for x in ("token", "secret", "password", "authorization", "api_key", "session", "cookie")):
                out[k] = "[redacted]"
            else:
                out[k] = scrub_secrets(v)
        return out
    if isinstance(obj, list):
        return [scrub_secrets(x) for x in obj]
    if isinstance(obj, str):
        s = obj
        s = re.sub(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+", r"\1=[redacted]", s)
        s = re.sub(r"\bya29\.[0-9A-Za-z\-_.]+\b", "[redacted]", s)
        s = re.sub(r"\bAIza[0-9A-Za-z\-_]{10,}\b", "[redacted]", s)
        return s
    return obj


def _quality_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("quality_summary")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return {}


def _publishability_from_job(row: Dict[str, Any]) -> Dict[str, Any]:
    """Consume existing publishability authority evidence — do not invent a second engine.

    Prefer quality_summary.publishability / verdict; fall back to ready_to_upload writer outcome.
    """
    qs = _quality_dict(row)
    pub = qs.get("publishability") if isinstance(qs.get("publishability"), dict) else {}
    verdict = str(
        pub.get("verdict")
        or qs.get("publishability_verdict")
        or qs.get("verdict")
        or ""
    ).upper()
    publishable_flag = qs.get("publishable")
    if publishable_flag is None and isinstance(pub, dict) and "publishable" in pub:
        publishable_flag = pub.get("publishable")

    upload = str(row.get("upload_status") or "")
    # Sole production writer sets ready_to_upload only after PASS — treat as PASS evidence
    if not verdict:
        if upload == "ready_to_upload" and (publishable_flag is True or publishable_flag is None):
            verdict = "PUBLISHABLE"
            publishable_flag = True
        elif upload == "quality_blocked":
            verdict = "BLOCKED"
            publishable_flag = False
        else:
            verdict = "UNKNOWN"
            publishable_flag = False

    if verdict in ("PASS", "PUBLISHABLE"):
        verdict = "PUBLISHABLE"
        ok = True if publishable_flag is not False else False
    elif verdict in ("BLOCKED", "NOT_PUBLISHABLE", "REPAIR_REQUIRED"):
        ok = False
    elif verdict == "UNKNOWN":
        ok = False
    else:
        ok = False
        verdict = "UNKNOWN"

    return {
        "verdict": verdict,
        "publishable": bool(ok and verdict == "PUBLISHABLE"),
        "reason": pub.get("reason") or qs.get("publishability_reason") or qs.get("note"),
        "source": "pipeline.quality.publishability via job quality_summary / ready_to_upload",
    }


def _work_dir(job_id: int) -> Path:
    d = Path(DATA_DIR) / "customer_publish" / f"job{int(job_id)}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def compute_publish_fingerprint(
    *,
    login_id: str,
    job_id: int,
    revision_id: str,
    channel_id: int,
    provider: str,
    language: str,
    artifact_path: str,
    title: str,
) -> str:
    """Publish-specific input projection — storage/claim via BUILD-03 IdempotencyStore only."""
    from pipeline.idempotency.fingerprint import compute_fingerprint, hash_artifact

    art_hash = hash_artifact(artifact_path) if artifact_path and os.path.isfile(artifact_path) else ""
    return compute_fingerprint(
        job_id=str(job_id),
        stage=PUBLISH_STAGE,
        entity_id=f"ch{int(channel_id)}:{revision_id}",
        contract_version=PUBLISH_CONTRACT,
        provider=str(provider or "mock"),
        model="",
        inputs={
            "login_id": login_id,
            "revision_id": revision_id,
            "channel_id": int(channel_id),
            "language": language,
            "artifact_hash": art_hash,
            "title": title or "",
            # tokens NEVER included
        },
    )


def build_publish_request(
    *,
    login_id: str,
    job_id: int,
    channel_id: int,
    provider: str,
    language: str,
    revision_id: str,
    artifact_path: str,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    category: Optional[str] = None,
    privacy_status: str = "private",
    thumbnail_path: Optional[str] = None,
    publish_at: Optional[str] = None,
    fingerprint: str,
) -> Dict[str, Any]:
    """Canonical PublishRequest — request data only; schedule time is data, not executed."""
    return scrub_secrets(
        {
            "contract": CONTRACT_VERSION,
            "kind": "PublishRequest",
            "login_id": login_id,
            "job_id": int(job_id),
            "channel_id": int(channel_id),
            "provider": provider,
            "language": language,
            "revision_id": revision_id,
            "approved_revision": revision_id,
            "artifact_path": artifact_path,
            "title": title,
            "description": description or "",
            "tags": list(tags or []),
            "category": category,
            "privacy_status": privacy_status or "private",
            "thumbnail_path": thumbnail_path,
            "thumbnail_capability": "DEFERRED" if not thumbnail_path else "REFERENCE_ONLY",
            "publish_at": publish_at,  # data only — C07-PUB does not schedule
            "scheduling_implemented": False,
            "fingerprint": fingerprint,
        }
    )


def build_publish_package(request: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    """Immutable publication payload derived from approved production artifact — no media regen."""
    return scrub_secrets(
        {
            "contract": CONTRACT_VERSION,
            "kind": "PublishPackage",
            "immutable": True,
            "regenerates_media": False,
            "approved_revision": request.get("revision_id"),
            "artifact_path": request.get("artifact_path"),
            "title": request.get("title"),
            "description": request.get("description"),
            "tags": request.get("tags"),
            "category": request.get("category"),
            "privacy_status": request.get("privacy_status"),
            "thumbnail_path": request.get("thumbnail_path"),
            "thumbnail_capability": request.get("thumbnail_capability") or "NOT_SUPPORTED",
            "channel_id": request.get("channel_id"),
            "provider": request.get("provider"),
            "language": request.get("language"),
            "provenance": {
                "generation_fingerprint": row.get("generation_fingerprint"),
                "production_plan_id": row.get("production_plan_id"),
                "production_plan_revision": row.get("production_plan_revision"),
                "script_revision": row.get("script_revision"),
                "trace_id": row.get("trace_id"),
            },
            "build_revision": {
                "contract": CONTRACT_VERSION,
                "job_id": request.get("job_id"),
                "publish_fingerprint": request.get("fingerprint"),
            },
            "fingerprint": request.get("fingerprint"),
            "publish_at": request.get("publish_at"),
            "allow_live_provider": False,  # default offline-safe
        }
    )


def build_publish_result(
    *,
    state: str,
    provider: str,
    provider_video_id: Optional[str] = None,
    provider_url: Optional[str] = None,
    error_code: Optional[str] = None,
    error: Optional[str] = None,
    mock: bool = True,
    observed_at: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Distinguish accepted/uploaded vs remote processing vs published vs failed."""
    st = str(state or "UNKNOWN").upper()
    published = st == "PUBLISHED"
    uploaded = st in ("UPLOAD_ACCEPTED", "REMOTE_PROCESSING", "PUBLISHED")
    processing = st == "REMOTE_PROCESSING"
    return scrub_secrets(
        {
            "contract": CONTRACT_VERSION,
            "kind": "PublishResult",
            "state": st,
            "accepted": uploaded,
            "uploaded": uploaded and not published,
            "remote_processing": processing,
            "published": published,
            "failed": st == "FAILED",
            "reconciliation_required": st == "RECONCILIATION_REQUIRED",
            "provider": provider,
            "provider_video_id": provider_video_id,
            "provider_url": provider_url,
            "error_code": error_code,
            "error": sanitize_customer_error(error or "") if error else None,
            "mock": bool(mock),
            "mock_label": "MOCK — not real provider" if mock else "REAL_PROVIDER",
            "observed_at": observed_at or _now(),
            "note": "UPLOAD_ACCEPTED ≠ PUBLISHED; PROCESSING ≠ PUBLISHED; UNKNOWN ≠ PUBLISHED",
            **(extra or {}),
        }
    )


def _meta_from_job(row: Dict[str, Any], channel: Dict[str, Any]) -> Dict[str, Any]:
    """Receive already-approved publication metadata — do not invent SEO."""
    qs = _quality_dict(row)
    meta = qs.get("publication_metadata") if isinstance(qs.get("publication_metadata"), dict) else {}
    title = (
        meta.get("title")
        or row.get("title")
        or channel.get("youtube_name")
        or f"Job {row.get('id')}"
    )
    description = meta.get("description") or row.get("description") or ""
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    category = meta.get("category") or row.get("category")
    privacy = meta.get("privacy_status") or meta.get("privacy") or "private"
    thumb = meta.get("thumbnail_path") or row.get("thumbnail_path") or row.get("thumbnail")
    lang = row.get("lang_code") or channel.get("lang_code") or "en"
    return {
        "title": str(title).strip(),
        "description": str(description or ""),
        "tags": list(tags),
        "category": category,
        "privacy_status": str(privacy),
        "thumbnail_path": thumb,
        "language": str(lang),
    }


def validate_publish_gates(
    login_id: str,
    job_id: int,
    *,
    channel_ids: Sequence[int],
    channel_id: Optional[int] = None,
    revision_id: Optional[str] = None,
    provider: str = "mock",
    require_production_access: bool = True,
    identity: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fail-closed admit before any provider call."""
    ensure_publish_columns()
    blockers: List[str] = []

    if require_production_access:
        from app.customer_auth import evaluate_session

        ident = identity if identity is not None else evaluate_session()
        if ident.get("authenticated") is False:
            blockers.append("authentication_required")
        auth_ok = bool(
            ident.get("authenticated")
            or ident.get("auth_state") in ("AUTHENTICATED", "OK")
            or (ident.get("login_id") and ident.get("production_access") is True)
        )
        if not auth_ok and ident.get("production_access") is not True:
            if "authentication_required" not in blockers:
                blockers.append("authentication_required")
        if ident.get("account_state") in ("DISABLED", "INACTIVE", "SUSPENDED"):
            blockers.append("account_inactive")
        ent = str(ident.get("entitlement_state") or "")
        if ent in ("NONE", "EXPIRED", "SUSPENDED", "UNKNOWN", "INACTIVE"):
            blockers.append(f"entitlement_{ent.lower() or 'unknown'}")
        if ident.get("production_access") is False:
            blockers.append(str(ident.get("block_reason") or "production_access_denied"))
        elif "production_access" in ident and ident.get("production_access") is not True:
            if "authentication_required" not in blockers:
                blockers.append("production_access_denied")

    row = get_job(int(job_id))
    if not row:
        return {
            "ok": False,
            "admitted": False,
            "error": "job_not_found",
            "error_code": "VALIDATION_FAILURE",
            "blockers": ["job_not_found"],
        }

    owned = list(channel_ids or [])
    if not job_owned_by_channels(row, owned):
        return {
            "ok": False,
            "admitted": False,
            "error": "job_access_denied",
            "error_code": "OWNERSHIP_FAILURE",
            "blockers": ["foreign_job"],
        }
    requested = str(row.get("requested_by") or "").strip()
    if requested and requested != str(login_id).strip():
        return {
            "ok": False,
            "admitted": False,
            "error": "job_access_denied",
            "error_code": "OWNERSHIP_FAILURE",
            "blockers": ["foreign_login"],
        }

    job_ch = int(row.get("channel_id") or 0)
    target_ch = int(channel_id) if channel_id is not None else job_ch
    if target_ch != job_ch:
        return {
            "ok": False,
            "admitted": False,
            "error": "channel_mismatch",
            "error_code": "OWNERSHIP_FAILURE",
            "blockers": ["foreign_channel"],
        }
    if target_ch not in {int(x) for x in owned}:
        return {
            "ok": False,
            "admitted": False,
            "error": "channel_not_owned",
            "error_code": "OWNERSHIP_FAILURE",
            "blockers": ["unowned_channel"],
        }

    from app import db as store

    channel = store.get_channel(target_ch) or {}
    owner = str(channel.get("owner_login_id") or "").strip()
    # C04 claim/ownership — legacy unowned must follow existing authority (fail closed for publish)
    if owner and owner != str(login_id).strip():
        return {
            "ok": False,
            "admitted": False,
            "error": "channel_owner_mismatch",
            "error_code": "OWNERSHIP_FAILURE",
            "blockers": ["foreign_channel_owner"],
        }
    if not owner:
        return {
            "ok": False,
            "admitted": False,
            "error": "channel_unowned_claim_required",
            "error_code": "OWNERSHIP_FAILURE",
            "blockers": ["unowned_channel_legacy"],
        }

    approval = str(row.get("customer_approval") or "").upper()
    if approval != "APPROVED":
        blockers.append("not_approved")

    current_rev = compute_revision_id(row)
    if revision_id and str(revision_id).strip() and str(revision_id).strip() != current_rev:
        return {
            "ok": False,
            "admitted": False,
            "error": "stale_revision",
            "error_code": "VALIDATION_FAILURE",
            "blockers": ["foreign_or_stale_revision"],
            "current_revision": current_rev,
        }

    pub = _publishability_from_job(row)
    if pub["verdict"] == "UNKNOWN":
        blockers.append("publishability_UNKNOWN")
    elif pub["verdict"] in ("BLOCKED", "NOT_PUBLISHABLE", "REPAIR_REQUIRED") or not pub["publishable"]:
        blockers.append(f"publishability_{pub['verdict']}")

    upload = str(row.get("upload_status") or "")
    pstat_existing = str(row.get("publish_status") or "").upper()
    if upload != "ready_to_upload":
        # Idempotent re-entry / observe path — do not require ready_to_upload when publish FSM already advanced
        if pstat_existing not in (
            "PUBLISHED",
            "UPLOAD_ACCEPTED",
            "REMOTE_PROCESSING",
            "RECONCILIATION_REQUIRED",
            "PUBLISH_REQUESTED",
            "FAILED",
            "AUTH_REQUIRED",
        ):
            blockers.append("ready_to_upload_false")

    path = str(row.get("local_path") or "")
    if not path or not os.path.isfile(path):
        blockers.append("artifact_missing")
    else:
        try:
            from app.customer_generation_orchestrator import is_mock_or_invalid_media_artifact

            is_mock_art, reason = is_mock_or_invalid_media_artifact(path)
            if is_mock_art:
                if str(provider).lower() not in ("mock", "youtube_mock", ""):
                    blockers.append(f"mock_media_rejected_for_live_publish:{reason}")
                elif "empty" in reason or "truncated" in reason or "corrupt" in reason or "missing" in reason:
                    blockers.append(f"invalid_media_artifact:{reason}")
        except Exception:
            pass

    # Language entitlement — existing C04/lang authority
    meta = _meta_from_job(row, channel)
    lang = meta["language"]
    try:
        from pipeline.lang_entitlement import channel_languages

        unlocked = {str(x).lower() for x in channel_languages(channel)}
        if lang.lower() not in unlocked and unlocked:
            blockers.append("language_not_entitled")
    except Exception:
        blockers.append("language_entitlement_unknown")

    # Provider configuration
    from publishers.customer_publish_provider import get_publish_provider

    prov = get_publish_provider(provider, scenario="happy_path", allow_live=False)
    cfg = prov.validate_configuration(channel if provider not in ("mock", "youtube_mock") else channel)
    # Mock always validates unless scenario forced later; for gate use mock-ok for mock provider
    if str(provider).lower() in ("mock", "youtube_mock", ""):
        cfg = {"ok": True}
    elif not cfg.get("ok"):
        blockers.append("invalid_provider_config")

    # Required metadata
    if not str(meta.get("title") or "").strip():
        blockers.append("metadata_title_missing")

    if blockers:
        return scrub_secrets(
            {
                "ok": False,
                "admitted": False,
                "error": "publish_validation_failed",
                "error_code": "VALIDATION_FAILURE",
                "blockers": blockers,
                "publishability": pub,
                "approval": approval,
                "ready_to_upload": upload == "ready_to_upload",
                "revision_id": current_rev,
                "provider_config_ok": bool(cfg.get("ok")),
            }
        )

    return scrub_secrets(
        {
            "ok": True,
            "admitted": True,
            "approval": approval,
            "publishability": pub,
            "ready_to_upload": True,
            "revision_id": current_rev,
            "channel_id": target_ch,
            "language": lang,
            "artifact_path": path,
            "metadata": meta,
            "channel": {
                "id": target_ch,
                "youtube_name": channel.get("youtube_name"),
                "lang_code": channel.get("lang_code"),
                "owner_login_id": owner,
                # no tokens
            },
            "provider": provider,
            "provider_config_ok": True,
        }
    )


def _persist_publish_fields(job_id: int, **fields: Any) -> None:
    from app import db as store

    ensure_publish_columns()
    # Allow explicit None to clear error fields
    clearable = {"publish_error", "publish_error_code"}
    out = {}
    for k, v in fields.items():
        if v is not None or k in clearable:
            out[k] = v
    out["publish_updated_at"] = _now()
    store.update_job(int(job_id), **out)


def _idempotency_store(job_id: int):
    from pipeline.idempotency.store import IdempotencyStore

    return IdempotencyStore(_work_dir(job_id) / "idempotency")


def publish_customer_job(
    login_id: str,
    job_id: int,
    *,
    channel_ids: Sequence[int],
    channel_id: Optional[int] = None,
    revision_id: Optional[str] = None,
    provider: str = "mock",
    scenario: str = "happy_path",
    allow_live_provider: bool = False,
    identity: Optional[Dict[str, Any]] = None,
    publish_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Explicit publish action — never implied by approval.

    Uses BUILD-03 atomic_claim. Ambiguous network → RECONCILIATION_REQUIRED (no blind retry).
    """
    global _REAL_PROVIDER_CALLS
    ensure_publish_columns()

    with _LOCK:
        row0 = get_job(int(job_id))
        # Idempotent reuse when prior publication already SUCCEEDED (revision may shift after upload_status write)
        if row0 and str(row0.get("publish_status") or "").upper() == "PUBLISHED":
            prev_fp = str(row0.get("publish_fingerprint") or "")
            if prev_fp:
                from pipeline.idempotency.states import IdempotencyState

                existing = _idempotency_store(int(job_id)).get(prev_fp)
                if existing and existing.request_state == IdempotencyState.SUCCEEDED:
                    append_lifecycle_event(
                        int(job_id),
                        {
                            "event": "PUBLISH_REQUESTED",
                            "type": "PUBLISH_REQUESTED",
                            "at": _now(),
                            "reused": True,
                        },
                    )
                    return scrub_secrets(
                        {
                            "ok": True,
                            "reused": True,
                            "claimed": False,
                            "fingerprint": prev_fp,
                            "provider_called": False,
                            "result": build_publish_result(
                                state="PUBLISHED",
                                provider=row0.get("publish_provider") or provider,
                                provider_video_id=row0.get("publish_provider_video_id"),
                                provider_url=row0.get("publish_provider_url"),
                                mock=bool(int(row0.get("publish_mock") or 1)),
                                extra={"idempotent_reuse": True},
                            ),
                            "note": "BUILD-03 SUCCEEDED — no duplicate publish attempt",
                        }
                    )

        gate = validate_publish_gates(
            login_id,
            int(job_id),
            channel_ids=channel_ids,
            channel_id=channel_id,
            revision_id=revision_id,
            provider=provider,
            identity=identity,
        )
        if not gate.get("admitted"):
            append_lifecycle_event(
                int(job_id),
                {
                    "event": "PUBLISH_VALIDATION_FAILED",
                    "type": "PUBLISH_VALIDATION_FAILED",
                    "at": _now(),
                    "blockers": gate.get("blockers"),
                    "error_code": gate.get("error_code"),
                },
            )
            _persist_publish_fields(
                int(job_id),
                publish_status="VALIDATION_FAILED",
                publish_error_code=gate.get("error_code") or "VALIDATION_FAILURE",
                publish_error=sanitize_customer_error(str(gate.get("error") or "blocked")),
                publish_provider=provider,
            )
            return scrub_secrets(
                {
                    "ok": False,
                    **gate,
                    "result": build_publish_result(
                        state="VALIDATION_FAILED",
                        provider=provider,
                        error_code=gate.get("error_code"),
                        error=gate.get("error"),
                        mock=True,
                    ),
                    "provider_called": False,
                }
            )

        row = get_job(int(job_id)) or {}
        meta = gate["metadata"]
        rev = gate["revision_id"]
        path = gate["artifact_path"]
        ch_id = int(gate["channel_id"])
        lang = gate["language"]
        fp = compute_publish_fingerprint(
            login_id=login_id,
            job_id=int(job_id),
            revision_id=rev,
            channel_id=ch_id,
            provider=provider,
            language=lang,
            artifact_path=path,
            title=meta["title"],
        )
        request = build_publish_request(
            login_id=login_id,
            job_id=int(job_id),
            channel_id=ch_id,
            provider=provider,
            language=lang,
            revision_id=rev,
            artifact_path=path,
            title=meta["title"],
            description=meta["description"],
            tags=meta["tags"],
            category=meta.get("category"),
            privacy_status=meta.get("privacy_status") or "private",
            thumbnail_path=meta.get("thumbnail_path"),
            publish_at=publish_at,
            fingerprint=fp,
        )
        package = build_publish_package(request, row)
        package["allow_live_provider"] = bool(allow_live_provider)

        from pipeline.idempotency.states import IdempotencyState
        from pipeline.idempotency.store import IdempotencyRecord

        store_i = _idempotency_store(int(job_id))
        record = IdempotencyRecord(
            fingerprint=fp,
            job_id=str(job_id),
            stage=PUBLISH_STAGE,
            entity_id=f"ch{ch_id}:{rev}",
            provider=str(provider),
            max_attempts=3,
            metadata={"login_id": login_id, "mock": not allow_live_provider},
        )
        claimed, existing = store_i.atomic_claim(record, worker_id=f"publish:{login_id}")
        if not claimed:
            ex_state = existing.request_state if existing else None
            if existing and existing.request_state == IdempotencyState.SUCCEEDED:
                append_lifecycle_event(
                    int(job_id),
                    {"event": "PUBLISH_REQUESTED", "type": "PUBLISH_REQUESTED", "at": _now(), "reused": True},
                )
                return scrub_secrets(
                    {
                        "ok": True,
                        "reused": True,
                        "claimed": False,
                        "fingerprint": fp,
                        "provider_called": False,
                        "result": build_publish_result(
                            state="PUBLISHED" if (row.get("publish_status") == "PUBLISHED") else "UPLOAD_ACCEPTED",
                            provider=provider,
                            provider_video_id=row.get("publish_provider_video_id") or existing.result_reference,
                            provider_url=row.get("publish_provider_url"),
                            mock=bool(int(row.get("publish_mock") or 1)),
                            extra={"idempotent_reuse": True},
                        ),
                        "package": json.loads(row.get("publish_package_json") or "{}") or package,
                        "note": "BUILD-03 SUCCEEDED — no duplicate publish attempt",
                    }
                )
            if existing and existing.request_state == IdempotencyState.UNKNOWN:
                _persist_publish_fields(
                    int(job_id),
                    publish_status="RECONCILIATION_REQUIRED",
                    publish_fingerprint=fp,
                    publish_error_code="RECONCILIATION_REQUIRED",
                    publish_error="ambiguous_prior_outcome",
                    publish_provider=provider,
                )
                append_lifecycle_event(
                    int(job_id),
                    {
                        "event": "PUBLISH_RECONCILIATION_REQUIRED",
                        "type": "PUBLISH_RECONCILIATION_REQUIRED",
                        "at": _now(),
                        "fingerprint": fp,
                    },
                )
                return scrub_secrets(
                    {
                        "ok": False,
                        "claimed": False,
                        "fingerprint": fp,
                        "provider_called": False,
                        "result": build_publish_result(
                            state="RECONCILIATION_REQUIRED",
                            provider=provider,
                            error_code="RECONCILIATION_REQUIRED",
                            error="prior_outcome_unknown",
                            mock=True,
                        ),
                        "note": "Do not blind retry — reconciliation required",
                    }
                )
            # IN_PROGRESS or FAILED_FINAL
            return scrub_secrets(
                {
                    "ok": False if ex_state == IdempotencyState.FAILED_FINAL else True,
                    "claimed": False,
                    "in_progress": ex_state == IdempotencyState.IN_PROGRESS,
                    "fingerprint": fp,
                    "provider_called": False,
                    "result": build_publish_result(
                        state=str(row.get("publish_status") or "PUBLISH_REQUESTED"),
                        provider=provider,
                        provider_video_id=row.get("publish_provider_video_id"),
                        provider_url=row.get("publish_provider_url"),
                        mock=bool(int(row.get("publish_mock") or 1)),
                        extra={"duplicate_claim_blocked": True},
                    ),
                    "note": "Concurrent/duplicate claim blocked by BUILD-03",
                }
            )

        append_lifecycle_event(
            int(job_id),
            {"event": "PUBLISH_REQUESTED", "type": "PUBLISH_REQUESTED", "at": _now(), "fingerprint": fp},
        )
        append_lifecycle_event(
            int(job_id),
            {"event": "PUBLISH_STARTED", "type": "PUBLISH_STARTED", "at": _now(), "fingerprint": fp},
        )
        _persist_publish_fields(
            int(job_id),
            publish_status="PUBLISH_REQUESTED",
            publish_fingerprint=fp,
            publish_provider=provider,
            publish_package_json=json.dumps(package, ensure_ascii=False),
            publish_attempt_count=int(row.get("publish_attempt_count") or 0) + 1,
            publish_mock=0 if allow_live_provider else 1,
        )

        from publishers.customer_publish_provider import get_publish_provider

        use_live = bool(allow_live_provider) and str(provider).lower() in ("youtube", "yt")
        prov = get_publish_provider(
            "youtube" if use_live else provider,
            scenario=scenario,
            allow_live=use_live,
        )

        # Auth check
        from app import db as store

        channel = store.get_channel(ch_id) or {}
        auth = prov.authorize(channel)
        if not auth.get("ok"):
            code = auth.get("error_code") or "AUTH_FAILURE"
            _mark_idempotency_failed(store_i, fp, retryable=False, meta={"error_code": code})
            _persist_publish_fields(
                int(job_id),
                publish_status="AUTH_REQUIRED",
                publish_error_code=code,
                publish_error=sanitize_customer_error(str(auth.get("error") or "auth")),
            )
            append_lifecycle_event(
                int(job_id),
                {"event": "PUBLISH_AUTH_REQUIRED", "type": "PUBLISH_AUTH_REQUIRED", "at": _now()},
            )
            return scrub_secrets(
                {
                    "ok": False,
                    "claimed": True,
                    "fingerprint": fp,
                    "provider_called": False,
                    "result": build_publish_result(
                        state="AUTH_REQUIRED",
                        provider=getattr(prov, "name", provider),
                        error_code=code,
                        error=auth.get("error"),
                        mock=not use_live,
                    ),
                }
            )

        try:
            if use_live:
                _REAL_PROVIDER_CALLS += 1
            accepted = prov.upload(package, channel)
        except Exception as exc:
            code = prov.classify_error(exc)
            msg = sanitize_customer_error(str(exc))
            if code == "NETWORK_FAILURE" or "ambiguous" in str(exc).lower():
                # Ambiguous — do NOT mark SUCCEEDED or safe-to-retry blindly
                _mark_idempotency_unknown(store_i, fp, meta={"error_code": code, "error": msg})
                _persist_publish_fields(
                    int(job_id),
                    publish_status="RECONCILIATION_REQUIRED",
                    publish_error_code=code,
                    publish_error=msg,
                    publish_fingerprint=fp,
                )
                append_lifecycle_event(
                    int(job_id),
                    {
                        "event": "PUBLISH_RECONCILIATION_REQUIRED",
                        "type": "PUBLISH_RECONCILIATION_REQUIRED",
                        "at": _now(),
                        "error_code": code,
                    },
                )
                return scrub_secrets(
                    {
                        "ok": False,
                        "claimed": True,
                        "fingerprint": fp,
                        "provider_called": True,
                        "result": build_publish_result(
                            state="RECONCILIATION_REQUIRED",
                            provider=getattr(prov, "name", provider),
                            error_code=code,
                            error=msg,
                            mock=not use_live,
                        ),
                        "safe_to_retry": False,
                        "note": "Ambiguous outcome — reconciliation required; no blind duplicate upload",
                    }
                )

            retryable = code in RECOVERABLE_ERRORS
            _mark_idempotency_failed(store_i, fp, retryable=retryable, meta={"error_code": code})
            _persist_publish_fields(
                int(job_id),
                publish_status="FAILED",
                publish_error_code=code,
                publish_error=msg,
            )
            append_lifecycle_event(
                int(job_id),
                {
                    "event": "PUBLISH_FAILED",
                    "type": "PUBLISH_FAILED",
                    "at": _now(),
                    "error_code": code,
                },
            )
            return scrub_secrets(
                {
                    "ok": False,
                    "claimed": True,
                    "fingerprint": fp,
                    "provider_called": True,
                    "result": build_publish_result(
                        state="FAILED",
                        provider=getattr(prov, "name", provider),
                        error_code=code,
                        error=msg,
                        mock=not use_live,
                    ),
                    "retryable": retryable,
                }
            )

        # Upload accepted — NOT published
        is_mock = bool(getattr(accepted, "mock", True))
        _persist_publish_fields(
            int(job_id),
            publish_status="UPLOAD_ACCEPTED",
            publish_provider_video_id=accepted.provider_video_id,
            publish_provider_url=accepted.provider_url,
            publish_observed_at=_now(),
            publish_mock=1 if is_mock else 0,
            publish_error=None,
            publish_error_code=None,
            # Do NOT set upload_status=uploaded yet — preserves READY_TO_UPLOAD ≠ UPLOADED ≠ PUBLISHED
        )
        # Mark idempotency IN_PROGRESS→ keep as in-progress until observe says PUBLISHED,
        # but store provider id for restart recovery
        rec = store_i.get(fp)
        if rec:
            rec.result_reference = accepted.provider_video_id
            rec.metadata["upload_accepted"] = True
            rec.metadata["mock"] = is_mock
            rec.metadata["provider_url"] = accepted.provider_url
            # Leave IN_PROGRESS until remote succeeds OR mark SUCCEEDED only for terminal publish after observe
            store_i.put(rec)

        append_lifecycle_event(
            int(job_id),
            {
                "event": "PUBLISH_UPLOAD_ACCEPTED",
                "type": "PUBLISH_UPLOAD_ACCEPTED",
                "at": _now(),
                "provider_video_id": accepted.provider_video_id,
                "mock": is_mock,
            },
        )

        return scrub_secrets(
            {
                "ok": True,
                "claimed": True,
                "fingerprint": fp,
                "provider_called": True,
                "request": request,
                "package": package,
                "result": build_publish_result(
                    state="UPLOAD_ACCEPTED",
                    provider=getattr(prov, "name", provider),
                    provider_video_id=accepted.provider_video_id,
                    provider_url=accepted.provider_url,
                    mock=is_mock,
                ),
                "note": "Upload accepted — remote processing / published requires observe (refresh)",
            }
        )


def _mark_idempotency_failed(store_i, fingerprint: str, *, retryable: bool, meta: Dict[str, Any]) -> None:
    from pipeline.idempotency.states import IdempotencyState

    rec = store_i.get(fingerprint)
    if not rec:
        return
    rec.request_state = (
        IdempotencyState.FAILED_RETRYABLE if retryable else IdempotencyState.FAILED_FINAL
    )
    rec.metadata.update(scrub_secrets(meta))
    store_i.put(rec)


def _mark_idempotency_unknown(store_i, fingerprint: str, *, meta: Dict[str, Any]) -> None:
    from pipeline.idempotency.states import IdempotencyState

    rec = store_i.get(fingerprint)
    if not rec:
        return
    rec.request_state = IdempotencyState.UNKNOWN
    rec.metadata.update(scrub_secrets(meta))
    rec.metadata["safe_to_retry"] = False
    store_i.put(rec)


def _mark_idempotency_succeeded(store_i, fingerprint: str, *, result_ref: str, meta: Dict[str, Any]) -> None:
    from pipeline.idempotency.states import IdempotencyState
    import time

    rec = store_i.get(fingerprint)
    if not rec:
        return
    rec.request_state = IdempotencyState.SUCCEEDED
    rec.result_reference = result_ref
    rec.completed_at = time.time()
    rec.metadata.update(scrub_secrets(meta))
    store_i.put(rec)


def refresh_publish_status(
    login_id: str,
    job_id: int,
    *,
    channel_ids: Sequence[int],
    provider: Optional[str] = None,
    scenario: str = "happy_path",
) -> Dict[str, Any]:
    """Observe remote processing — never infer PUBLISHED from local upload success alone."""
    ensure_publish_columns()
    row = get_job(int(job_id))
    if not row:
        return {"ok": False, "error": "job_not_found", "error_code": "VALIDATION_FAILURE"}
    if not job_owned_by_channels(row, list(channel_ids)):
        return {"ok": False, "error": "job_access_denied", "error_code": "OWNERSHIP_FAILURE"}
    requested = str(row.get("requested_by") or "").strip()
    if requested and requested != str(login_id).strip():
        return {"ok": False, "error": "job_access_denied", "error_code": "OWNERSHIP_FAILURE"}

    vid = str(row.get("publish_provider_video_id") or "").strip()
    if not vid:
        st = str(row.get("publish_status") or "NOT_STARTED")
        if st == "RECONCILIATION_REQUIRED":
            return scrub_secrets(
                {
                    "ok": False,
                    "result": build_publish_result(
                        state="RECONCILIATION_REQUIRED",
                        provider=row.get("publish_provider") or provider or "mock",
                        error_code="RECONCILIATION_REQUIRED",
                        error="no_provider_id_after_ambiguous",
                        mock=bool(int(row.get("publish_mock") or 1)),
                    ),
                    "safe_to_retry": False,
                }
            )
        return scrub_secrets(
            {
                "ok": True,
                "result": build_publish_result(
                    state=st or "NOT_STARTED",
                    provider=row.get("publish_provider") or provider or "mock",
                    mock=bool(int(row.get("publish_mock") or 1)),
                ),
            }
        )

    from app import db as store
    from publishers.customer_publish_provider import get_publish_provider

    ch = store.get_channel(int(row.get("channel_id") or 0)) or {}
    prov_name = provider or row.get("publish_provider") or "mock"
    is_mock = bool(int(row.get("publish_mock") or 1))
    prov = get_publish_provider(prov_name if not is_mock else "mock", scenario=scenario, allow_live=not is_mock)
    obs = prov.observe(vid, ch)
    status = str(obs.status or "UNKNOWN").upper()

    if status == "UNKNOWN":
        append_lifecycle_event(
            int(job_id),
            {"event": "PUBLISH_REMOTE_PROCESSING", "type": "PUBLISH_REMOTE_PROCESSING", "at": _now(), "status": "UNKNOWN"},
        )
        # UNKNOWN must never become PUBLISHED
        return scrub_secrets(
            {
                "ok": True,
                "result": build_publish_result(
                    state="REMOTE_PROCESSING" if row.get("publish_status") == "UPLOAD_ACCEPTED" else str(row.get("publish_status") or "UNKNOWN"),
                    provider=getattr(prov, "name", prov_name),
                    provider_video_id=vid,
                    provider_url=obs.provider_url or row.get("publish_provider_url"),
                    mock=bool(obs.mock),
                    extra={"observation": "UNKNOWN", "published": False},
                ),
                "note": "UNKNOWN observation cannot become PUBLISHED",
            }
        )

    if status in ("UPLOAD_ACCEPTED", "PROCESSING"):
        mapped = "UPLOAD_ACCEPTED" if status == "UPLOAD_ACCEPTED" else "REMOTE_PROCESSING"
        _persist_publish_fields(
            int(job_id),
            publish_status=mapped,
            publish_observed_at=_now(),
            publish_provider_url=obs.provider_url or row.get("publish_provider_url"),
        )
        append_lifecycle_event(
            int(job_id),
            {
                "event": "PUBLISH_REMOTE_PROCESSING" if mapped == "REMOTE_PROCESSING" else "PUBLISH_UPLOAD_ACCEPTED",
                "type": "PUBLISH_REMOTE_PROCESSING" if mapped == "REMOTE_PROCESSING" else "PUBLISH_UPLOAD_ACCEPTED",
                "at": _now(),
            },
        )
        return scrub_secrets(
            {
                "ok": True,
                "result": build_publish_result(
                    state=mapped,
                    provider=getattr(prov, "name", prov_name),
                    provider_video_id=vid,
                    provider_url=obs.provider_url or row.get("publish_provider_url"),
                    mock=bool(obs.mock),
                ),
            }
        )

    if status in ("PROCESSING_FAILED",):
        _persist_publish_fields(
            int(job_id),
            publish_status="FAILED",
            publish_error_code="REMOTE_PROCESSING_FAILURE",
            publish_error="remote_processing_failed",
            publish_observed_at=_now(),
        )
        append_lifecycle_event(
            int(job_id),
            {"event": "PUBLISH_REMOTE_FAILED", "type": "PUBLISH_REMOTE_FAILED", "at": _now()},
        )
        fp = str(row.get("publish_fingerprint") or "")
        if fp:
            _mark_idempotency_failed(_idempotency_store(int(job_id)), fp, retryable=False, meta={"error_code": "REMOTE_PROCESSING_FAILURE"})
        return scrub_secrets(
            {
                "ok": False,
                "result": build_publish_result(
                    state="FAILED",
                    provider=getattr(prov, "name", prov_name),
                    provider_video_id=vid,
                    error_code="REMOTE_PROCESSING_FAILURE",
                    error="remote_processing_failed",
                    mock=bool(obs.mock),
                ),
            }
        )

    if status in ("PUBLISHED", "PROCESSING_SUCCEEDED"):
        # PROCESSING_SUCCEEDED may still need privacy check — only claim PUBLISHED when provider says so
        final = "PUBLISHED" if status == "PUBLISHED" else "REMOTE_PROCESSING"
        if status == "PROCESSING_SUCCEEDED":
            # succeeded processing but visibility may still be private — treat as remote succeeded event
            append_lifecycle_event(
                int(job_id),
                {"event": "PUBLISH_REMOTE_SUCCEEDED", "type": "PUBLISH_REMOTE_SUCCEEDED", "at": _now()},
            )
            # For mock/tests, processing_succeeded with private still not auto-public; map to REMOTE_PROCESSING unless published
            _persist_publish_fields(
                int(job_id),
                publish_status="REMOTE_PROCESSING",
                publish_observed_at=_now(),
            )
            return scrub_secrets(
                {
                    "ok": True,
                    "result": build_publish_result(
                        state="REMOTE_PROCESSING",
                        provider=getattr(prov, "name", prov_name),
                        provider_video_id=vid,
                        provider_url=obs.provider_url or row.get("publish_provider_url"),
                        mock=bool(obs.mock),
                        extra={"processing_succeeded": True, "published": False},
                    ),
                }
            )

        _persist_publish_fields(
            int(job_id),
            publish_status="PUBLISHED",
            publish_observed_at=_now(),
            publish_provider_url=obs.provider_url or row.get("publish_provider_url"),
            publish_error=None,
            publish_error_code=None,
        )
        # Only now mark pipeline upload_status for terminal published (mock → dry_run_uploaded)
        from app import db as store

        store.update_job(
            int(job_id),
            upload_status="dry_run_uploaded" if obs.mock else "uploaded",
            updated_at=_now(),
        )
        fp = str(row.get("publish_fingerprint") or "")
        if fp:
            _mark_idempotency_succeeded(
                _idempotency_store(int(job_id)),
                fp,
                result_ref=vid,
                meta={"published": True, "mock": bool(obs.mock)},
            )
        append_lifecycle_event(
            int(job_id),
            {"event": "PUBLISH_REMOTE_SUCCEEDED", "type": "PUBLISH_REMOTE_SUCCEEDED", "at": _now()},
        )
        append_lifecycle_event(
            int(job_id),
            {"event": "PUBLISH_COMPLETED", "type": "PUBLISH_COMPLETED", "at": _now(), "mock": bool(obs.mock)},
        )
        return scrub_secrets(
            {
                "ok": True,
                "result": build_publish_result(
                    state="PUBLISHED",
                    provider=getattr(prov, "name", provider or prov_name),
                    provider_video_id=vid,
                    provider_url=obs.provider_url or row.get("publish_provider_url"),
                    mock=bool(obs.mock),
                ),
            }
        )

    return scrub_secrets(
        {
            "ok": True,
            "result": build_publish_result(
                state="UNKNOWN",
                provider=getattr(prov, "name", prov_name),
                provider_video_id=vid,
                mock=bool(obs.mock),
                extra={"observation": status, "published": False},
            ),
            "note": "Unrecognized observation — not treated as PUBLISHED",
        }
    )


def reconcile_ambiguous_publish(
    login_id: str,
    job_id: int,
    *,
    channel_ids: Sequence[int],
    provider_video_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve RECONCILIATION_REQUIRED using provider identity when known — never blind re-upload."""
    ensure_publish_columns()
    row = get_job(int(job_id))
    if not row:
        return {"ok": False, "error": "job_not_found"}
    if not job_owned_by_channels(row, list(channel_ids)):
        return {"ok": False, "error": "job_access_denied", "error_code": "OWNERSHIP_FAILURE"}
    if str(row.get("publish_status") or "") != "RECONCILIATION_REQUIRED" and not provider_video_id:
        return {"ok": False, "error": "not_in_reconciliation", "safe_to_retry": False}

    vid = provider_video_id or row.get("publish_provider_video_id")
    if not vid:
        return scrub_secrets(
            {
                "ok": False,
                "safe_to_retry": False,
                "result": build_publish_result(
                    state="RECONCILIATION_REQUIRED",
                    provider=row.get("publish_provider") or "mock",
                    error_code="RECONCILIATION_REQUIRED",
                    error="provider_identity_unknown",
                    mock=True,
                ),
                "note": "Cannot prove absence of prior upload — do not blind retry",
            }
        )

    _persist_publish_fields(
        int(job_id),
        publish_provider_video_id=str(vid),
        publish_status="UPLOAD_ACCEPTED",
        publish_error=None,
        publish_error_code=None,
    )
    return refresh_publish_status(login_id, int(job_id), channel_ids=channel_ids)


def project_publishing(
    login_id: str,
    job_id: int,
    *,
    channel_ids: Sequence[int],
) -> Dict[str, Any]:
    """Workspace publishing projection — extends C06-H; not a second dashboard."""
    ensure_publish_columns()
    row = get_job(int(job_id))
    if not row:
        return {"ok": False, "error": "job_not_found", "error_code": "not_found"}
    if not job_owned_by_channels(row, list(channel_ids)):
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}
    requested = str(row.get("requested_by") or "").strip()
    if requested and requested != str(login_id).strip():
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}

    from app import db as store

    ch = store.get_channel(int(row.get("channel_id") or 0)) or {}
    pub = _publishability_from_job(row)
    approval = str(row.get("customer_approval") or "").upper() or "NOT_READY"
    ready = str(row.get("upload_status") or "") == "ready_to_upload"
    pstatus = str(row.get("publish_status") or "NOT_STARTED").upper()
    view = to_customer_view(row)

    blocking = None
    required_action = "None"
    if approval != "APPROVED":
        blocking = "not_approved"
        required_action = "Approve revision"
    elif not pub.get("publishable"):
        blocking = f"publishability_{pub.get('verdict')}"
        required_action = "Resolve quality / publishability"
    elif not ready:
        blocking = "ready_to_upload_false"
        required_action = "Complete generation to ready_to_upload"
    elif pstatus == "AUTH_REQUIRED":
        blocking = "auth_required"
        required_action = "Authorize provider OAuth"
    elif pstatus == "RECONCILIATION_REQUIRED":
        blocking = "reconciliation_required"
        required_action = "Refresh/reconcile — do not blind re-upload"
    elif pstatus == "FAILED":
        blocking = row.get("publish_error_code") or "publish_failed"
        required_action = "See failure classification"
    elif pstatus in ("NOT_STARTED", "VALIDATION_FAILED") and approval == "APPROVED" and ready and pub.get("publishable"):
        required_action = "PUBLISH"
    elif pstatus in ("UPLOAD_ACCEPTED", "REMOTE_PROCESSING"):
        required_action = "REFRESH STATUS"
    elif pstatus == "PUBLISHED":
        required_action = "None"

    can_publish = (
        approval == "APPROVED"
        and ready
        and pub.get("publishable")
        and pstatus in ("NOT_STARTED", "VALIDATION_FAILED", "FAILED")
        and str(row.get("publish_error_code") or "") not in ("RECONCILIATION_REQUIRED",)
    )
    # Permanent failures may block retry — FAILED_FINAL via fingerprint
    if pstatus == "RECONCILIATION_REQUIRED":
        can_publish = False

    events = []
    try:
        from app.customer_production_monitor import load_lifecycle_events

        events = [
            e
            for e in load_lifecycle_events(row, limit=80)
            if str(e.get("type") or e.get("event") or "").startswith("PUBLISH_")
        ]
    except Exception:
        events = []

    last_event = events[-1] if events else None

    return scrub_secrets(
        {
            "ok": True,
            "contract": CONTRACT_VERSION,
            "job_id": int(job_id),
            "approval_state": approval,
            "publishability": pub.get("verdict"),
            "publishability_detail": pub,
            "ready_to_upload": ready,
            "provider": row.get("publish_provider") or "mock",
            "channel": {
                "id": ch.get("id"),
                "name": ch.get("youtube_name"),
                "lang_code": ch.get("lang_code"),
            },
            "publication_state": pstatus,
            "provider_video_id": row.get("publish_provider_video_id"),
            "provider_url": row.get("publish_provider_url"),
            "last_publishing_event": last_event,
            "publish_events": events[-20:],
            "blocking_reason": blocking,
            "required_action": required_action,
            "actions": {
                "PUBLISH": bool(can_publish),
                "REFRESH_STATUS": pstatus
                in ("UPLOAD_ACCEPTED", "REMOTE_PROCESSING", "RECONCILIATION_REQUIRED", "PUBLISHED"),
                "CANCEL": False,  # cancel only when existing execution contract supports publish cancel — not in C07-PUB
                "SCHEDULE": False,
            },
            "mock": bool(int(row.get("publish_mock") or 0)) if row.get("publish_status") else None,
            "planes": {
                "approved": approval == "APPROVED",
                "ready_to_upload": ready,
                "upload_accepted": pstatus in ("UPLOAD_ACCEPTED", "REMOTE_PROCESSING", "PUBLISHED"),
                "remote_processing": pstatus == "REMOTE_PROCESSING",
                "published": pstatus == "PUBLISHED",
                "note": "APPROVED≠READY_TO_UPLOAD≠UPLOAD_ACCEPTED≠REMOTE_PROCESSING≠PUBLISHED",
            },
            "job": view,
            "secrets_excluded": True,
            "scheduling_implemented": False,
            "social_engagement": False,
        }
    )


def detect_duplicate_engines(source: str) -> List[str]:
    import re as _re

    bad = []
    for pat, label in (
        (r"(?m)^\s*def\s+generate_video\s*\(", "generate_video"),
        (r"(?m)^\s*class\s+SchedulerService\b", "SchedulerService"),
        (r"(?m)^\s*def\s+try_acquire\s*\(", "try_acquire"),
        (r"(?m)^\s*def\s+evaluate_publishability\s*\(", "evaluate_publishability"),
        (r"(?m)^\s*def\s+compute_fingerprint\s*\(", "compute_fingerprint"),
        (r"(?m)^\s*class\s+IdempotencyStore\b", "IdempotencyStore"),
        (r"publish_idempotency\.py", "publish_idempotency"),
        (r"publish_cache\.py", "publish_cache"),
    ):
        if _re.search(pat, source):
            bad.append(label)
    return bad
