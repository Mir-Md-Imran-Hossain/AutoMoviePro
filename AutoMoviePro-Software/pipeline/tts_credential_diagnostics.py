"""Google TTS credential diagnostics — no secrets in evidence.

READY is only set after a real successful TTS response from a credential.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pipeline.api_keys import mask_key, redact_sensitive_text
from pipeline.provider_error_class import classify_provider_failure
from pipeline.quota_backoff import (
    PER_KEY_COOL_SEC,
    filter_usable_keys,
    key_fingerprint,
    key_is_cooling,
    record_key_quota_hit,
)

logger = logging.getLogger(__name__)

EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "docs" / "marathon" / "customer_product" / "rcp07_next_blocker_evidence"
READY_MARKER = Path(__file__).resolve().parent / "google_tts_ready_state.json"
TTS_MODEL = "gemini-3.1-flash-tts-preview"
TTS_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{TTS_MODEL}:generateContent"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def google_tts_is_ready() -> bool:
    if not READY_MARKER.is_file():
        return False
    try:
        data = json.loads(READY_MARKER.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(data.get("ready")) and bool(data.get("success_fingerprint12"))


def mark_tts_ready(*, fingerprint12: str, suffix: str, model: str, endpoint: str) -> None:
    READY_MARKER.write_text(
        json.dumps(
            {
                "ready": True,
                "success_fingerprint12": fingerprint12,
                "success_suffix": suffix,
                "model": model,
                "endpoint": endpoint,
                "proven_at": _now(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def clear_tts_ready() -> None:
    READY_MARKER.write_text(
        json.dumps({"ready": False, "reason": "cleared", "cleared_at": _now()}, indent=2),
        encoding="utf-8",
    )


def readiness_snapshot() -> Dict[str, Any]:
    if not READY_MARKER.is_file():
        return {"google_tts_ready": False, "reason": "no_success_probe"}
    try:
        data = json.loads(READY_MARKER.read_text(encoding="utf-8"))
    except Exception:
        return {"google_tts_ready": False, "reason": "unreadable_marker"}
    return {
        "google_tts_ready": bool(data.get("ready")),
        "success_fingerprint12": data.get("success_fingerprint12"),
        "success_suffix": data.get("success_suffix"),
        "model": data.get("model"),
        "proven_at": data.get("proven_at"),
        "reason": data.get("reason"),
    }


def _probe_one_key(api_key: str, *, slot: int) -> Dict[str, Any]:
    """One minimal REST TTS attempt — records HTTP status only, no secret."""
    import httpx

    fp = key_fingerprint(api_key)
    suffix = (api_key or "")[-4:]
    started = time.time()
    rec: Dict[str, Any] = {
        "slot": slot,
        "fingerprint12": fp,
        "suffix": suffix,
        "model": TTS_MODEL,
        "endpoint": TTS_ENDPOINT,
        "request_timestamp": _now(),
        "retry_count": 0,
        "cooldown_before": key_is_cooling(api_key),
        "cooldown_sec": PER_KEY_COOL_SEC if key_is_cooling(api_key) else 0,
        "duplicate_of_request": False,
        "http_status": None,
        "failure_class": None,
        "provider_reason": None,
        "project_identity": None,
        "tts_success": False,
        "audio_bytes": 0,
    }
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "Say only: ready."}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Charon"}}
            },
        },
    }
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=45.0) as client:
            r = client.post(TTS_ENDPOINT, headers=headers, json=payload)
        rec["http_status"] = int(r.status_code)
        body = r.text[:800]
        if r.status_code >= 400:
            classified = classify_provider_failure(f"HTTP {r.status_code}: {body}")
            rec["failure_class"] = classified["class"]
            rec["provider_reason"] = classified["provider_reason"]
            rec["project_identity"] = classified.get("project_identity")
            rec["safe_message"] = classified.get("safe_message")
            if classified["class"] in ("http_429_quota_or_rate", "http_403_permission_or_config"):
                record_key_quota_hit(api_key, "google")
                rec["cooldown_after"] = True
            return rec
        data = r.json()
        # success if any inline audio
        audio_ok = False
        nbytes = 0
        for cand in data.get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data") or {}
                b64 = inline.get("data") or ""
                if b64:
                    audio_ok = True
                    nbytes = max(nbytes, int(len(b64) * 0.75))
        rec["tts_success"] = bool(audio_ok)
        rec["audio_bytes"] = nbytes
        if audio_ok:
            mark_tts_ready(
                fingerprint12=fp,
                suffix=suffix,
                model=TTS_MODEL,
                endpoint=TTS_ENDPOINT,
            )
        else:
            rec["failure_class"] = "other"
            rec["provider_reason"] = "no_audio_in_response"
    except Exception as exc:
        classified = classify_provider_failure(exc)
        rec["http_status"] = classified.get("http_status")
        rec["failure_class"] = classified["class"]
        rec["provider_reason"] = classified["provider_reason"]
        rec["project_identity"] = classified.get("project_identity")
        rec["safe_message"] = classified.get("safe_message")
        if classified["class"] in ("http_429_quota_or_rate", "http_403_permission_or_config"):
            record_key_quota_hit(api_key, "google")
            rec["cooldown_after"] = True
    rec["elapsed_ms"] = int((time.time() - started) * 1000)
    return rec


def diagnose_google_tts_credentials(
    api_keys: Sequence[str],
    *,
    out_dir: Optional[Path] = None,
    max_keys: int = 40,
) -> Dict[str, Any]:
    """Probe each configured credential once; write redacted evidence JSON."""
    out_dir = Path(out_dir or EVIDENCE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = [k.strip() for k in (api_keys or []) if (k or "").strip()][: max(1, int(max_keys))]
    records: List[Dict[str, Any]] = []
    seen_fp = set()
    for i, key in enumerate(keys):
        fp = key_fingerprint(key)
        if fp in seen_fp:
            records.append(
                {
                    "slot": i,
                    "fingerprint12": fp,
                    "suffix": key[-4:],
                    "duplicate_credential": True,
                    "tts_success": False,
                    "request_timestamp": _now(),
                }
            )
            continue
        seen_fp.add(fp)
        logger.info("TTS credential probe slot=%s …%s", i, key[-4:])
        records.append(_probe_one_key(key, slot=i))

    projects = sorted({r.get("project_identity") for r in records if r.get("project_identity")})
    successes = [r for r in records if r.get("tts_success")]
    summary = {
        "collected_at": _now(),
        "credential_count": len(keys),
        "unique_fingerprints": len(seen_fp),
        "success_count": len(successes),
        "google_tts_ready": bool(successes),
        "success_slots": [
            {"slot": s["slot"], "fingerprint12": s["fingerprint12"], "suffix": s["suffix"]}
            for s in successes
        ],
        "observed_project_identities": projects,
        "same_project_evidence": (
            {
                "all_observed_errors_share_one_project": len(projects) == 1,
                "project": projects[0] if len(projects) == 1 else None,
                "note": "Based on provider error metadata only; success responses rarely expose project.",
            }
            if projects
            else {
                "all_observed_errors_share_one_project": None,
                "project": None,
                "note": "No project identity found in error metadata for probed keys.",
            }
        ),
        "class_counts": {},
        "records": records,
        "secrets_logged": False,
    }
    counts: Dict[str, int] = {}
    for r in records:
        c = str(r.get("failure_class") or ("success" if r.get("tts_success") else "unknown"))
        counts[c] = counts.get(c, 0) + 1
    summary["class_counts"] = counts
    path = out_dir / "GOOGLE_TTS_CREDENTIAL_DIAGNOSTICS.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["evidence_path"] = str(path)
    return summary


def append_synth_attempt(
    work_dir: Optional[Path],
    record: Dict[str, Any],
) -> None:
    """Append one synthesize attempt diagnostic (redacted) into job work dir."""
    if work_dir is None:
        return
    try:
        dest = Path(work_dir) / "TTS_ATTEMPT_DIAGNOSTICS.jsonl"
        safe = {k: v for k, v in record.items() if k != "api_key"}
        if "safe_message" in safe:
            safe["safe_message"] = redact_sensitive_text(str(safe["safe_message"]))
        with dest.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(safe, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("tts diagnostic append failed: %s", exc)
