"""Speech timing observation via faster-whisper (optional dependency).

Selected over WhisperX for AutoMovie Pro Phase 6A / T1-A:
- already present in the Windows env
- lighter deps (no WhisperX align/diarize stack required)
- word timestamps via word_timestamps=True
- CPU fallback (compute_type int8)

Does NOT replace AudioPlan / VoiceIdentity / planned SRT authority.
Planned subtitle timing is never treated as actual PASS.
UNKNOWN/UNAVAILABLE never silently become PASS.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pipeline.observation.common import (
    SCHEMA_SPEECH,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNKNOWN,
    STATUS_UNAVAILABLE,
    unavailable,
)

logger = logging.getLogger(__name__)

ASR_TOOL = "faster-whisper"
ASR_ALTERNATE = "whisperx"  # not selected; documented for audit
SCHEMA_VERSION = "amp_observation_speech_timing_v1.1"

# Process-local lazy model cache: (model_size, device, compute_type, download_root) -> model
_MODEL_CACHE: Dict[Tuple[str, str, str, str], Any] = {}


def speech_tool_available() -> Dict[str, Any]:
    try:
        import faster_whisper  # noqa: F401

        ver = getattr(faster_whisper, "__version__", None) or "unknown"
        return {"available": True, "tool": ASR_TOOL, "import_ok": True, "tool_version": ver}
    except Exception as exc:
        return {
            "available": False,
            "tool": ASR_TOOL,
            "import_ok": False,
            "error": str(exc)[:200],
            "tool_version": None,
        }


def whisper_download_root() -> Path:
    """Deterministic Windows-friendly cache for Whisper weights."""
    env = (os.environ.get("AMP_WHISPER_CACHE") or "").strip()
    if env:
        root = Path(env)
    else:
        # Prefer project-local data/ so portable installs stay self-contained.
        try:
            from app.config import DATA_DIR

            root = Path(DATA_DIR) / "models" / "faster-whisper"
        except Exception:
            root = Path(__file__).resolve().parents[3] / "data" / "models" / "faster-whisper"
    root.mkdir(parents=True, exist_ok=True)
    return root


def source_media_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def validate_timestamp_evidence(
    *,
    segments: Sequence[Dict[str, Any]],
    words: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Deterministic bounds/monotonicity checks — observation hygiene only."""
    issues: List[str] = []
    prev_seg_end = -1.0
    for i, seg in enumerate(segments or []):
        try:
            start = float(seg.get("start"))
            end = float(seg.get("end"))
        except (TypeError, ValueError):
            issues.append(f"segment_malformed_timestamp:{i}")
            continue
        if start < 0 or end < 0:
            issues.append(f"segment_negative_timestamp:{i}")
        if end < start:
            issues.append(f"segment_impossible_duration:{i}")
        if start < prev_seg_end - 1e-3:
            issues.append(f"segment_non_monotonic:{i}")
        prev_seg_end = max(prev_seg_end, end)

    prev_word_end = -1.0
    for i, w in enumerate(words or []):
        s = w.get("start")
        e = w.get("end")
        if s is None and e is None:
            continue
        try:
            start = float(s) if s is not None else float(e or 0)
            end = float(e) if e is not None else start
        except (TypeError, ValueError):
            issues.append(f"word_malformed_timestamp:{i}")
            continue
        if start < 0 or end < 0:
            issues.append(f"word_negative_timestamp:{i}")
        if end < start:
            issues.append(f"word_impossible_duration:{i}")
        if start + 1e-6 < prev_word_end:
            issues.append(f"word_non_monotonic:{i}")
        prev_word_end = max(prev_word_end, end)

        # Word should fall inside some segment when segments exist
        if segments:
            inside = False
            for seg in segments:
                try:
                    ss = float(seg.get("start") or 0)
                    ee = float(seg.get("end") or 0)
                except (TypeError, ValueError):
                    continue
                if start >= ss - 0.05 and end <= ee + 0.05:
                    inside = True
                    break
            if not inside:
                issues.append(f"word_outside_segments:{i}")

    return {
        "ok": not issues,
        "issues": issues,
        "segment_count": len(list(segments or [])),
        "word_count": len([w for w in (words or []) if w.get("start") is not None]),
    }


def _get_model(model_size: str, device: str, compute_type: str, download_root: Path):
    key = (model_size, device, compute_type, str(download_root))
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached, True
    from faster_whisper import WhisperModel

    model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
        download_root=str(download_root),
    )
    _MODEL_CACHE[key] = model
    return model, False


def observe_speech_timing(
    audio_path: Path | str,
    *,
    language_hint: str = "",
    model_size: str = "",
    device: str = "cpu",
    compute_type: str = "int8",
    beam_size: int = 1,
) -> Dict[str, Any]:
    """Transcribe actual audio → transcript + word/segment timestamps.

    On missing tool/model/runtime failure → OBSERVATION_UNAVAILABLE (never silent PASS).
    """
    path = Path(audio_path)
    observed_at = datetime.now(timezone.utc).isoformat()
    env_model = (os.environ.get("AMP_WHISPER_MODEL") or "").strip()
    model_size = (model_size or env_model or "tiny").strip() or "tiny"
    device = (device or "cpu").strip() or "cpu"
    compute_type = (compute_type or "int8").strip() or "int8"

    if not path.is_file() or path.stat().st_size < 64:
        out = {
            **unavailable(
                schema=SCHEMA_SPEECH,
                tool=ASR_TOOL,
                reason="INVALID_MEDIA",
                detail=str(path),
            ),
            "status": STATUS_FAIL,
            "reason": "INVALID_MEDIA",
            "issues": ["missing_or_tiny_audio"],
            "observed_at": observed_at,
            "segments": [],
            "words": [],
            "metrics": {},
            "provenance": {"audio_path": str(path)},
            "claims_semantic_truth": False,
        }
        return out

    avail = speech_tool_available()
    if not avail.get("available"):
        out = unavailable(
            schema=SCHEMA_SPEECH,
            tool=ASR_TOOL,
            reason="MODEL_UNAVAILABLE",
            detail=str(avail.get("error") or "faster_whisper_not_importable"),
        )
        out["reason"] = "MODEL_UNAVAILABLE"
        out["observed_at"] = observed_at
        out["segments"] = []
        out["words"] = []
        out["metrics"] = {}
        out["provenance"] = {"audio_path": str(path)}
        out["claims_semantic_truth"] = False
        return out

    try:
        from faster_whisper import WhisperModel  # noqa: F401
        import faster_whisper
    except Exception as exc:
        out = unavailable(
            schema=SCHEMA_SPEECH,
            tool=ASR_TOOL,
            reason="MODEL_UNAVAILABLE",
            detail=str(exc)[:200],
        )
        out["reason"] = "MODEL_UNAVAILABLE"
        out["observed_at"] = observed_at
        out["claims_semantic_truth"] = False
        return out

    tool_version = str(getattr(faster_whisper, "__version__", None) or avail.get("tool_version") or "unknown")
    download_root = whisper_download_root()
    try:
        src_hash = source_media_hash(path)
    except Exception as exc:
        src_hash = f"hash_failed:{exc}"[:64]

    t_load0 = time.perf_counter()
    try:
        model, from_cache = _get_model(model_size, device, compute_type, download_root)
    except Exception as exc:
        out = unavailable(
            schema=SCHEMA_SPEECH,
            tool=ASR_TOOL,
            reason="MODEL_UNAVAILABLE",
            detail=str(exc)[:300],
        )
        out["reason"] = "MODEL_UNAVAILABLE"
        out["model"] = model_size
        out["tool_version"] = tool_version
        out["source_hash"] = src_hash
        out["observed_at"] = observed_at
        out["segments"] = []
        out["words"] = []
        out["metrics"] = {}
        out["provenance"] = {
            "audio_path": str(path),
            "download_root": str(download_root),
            "source_hash": src_hash,
        }
        return out
    load_sec = round(time.perf_counter() - t_load0, 3)

    lang = (language_hint or "").strip().lower()[:8] or None
    t_asr0 = time.perf_counter()
    try:
        segments_iter, info = model.transcribe(
            str(path),
            language=lang,
            beam_size=max(1, int(beam_size)),
            word_timestamps=True,
            vad_filter=False,
        )
        segments: List[Dict[str, Any]] = []
        words: List[Dict[str, Any]] = []
        texts: List[str] = []
        for seg in segments_iter:
            texts.append(seg.text or "")
            seg_d = {
                "start": float(seg.start or 0.0),
                "end": float(seg.end or 0.0),
                "text": (seg.text or "").strip(),
            }
            segments.append(seg_d)
            for w in seg.words or []:
                words.append(
                    {
                        "word": (w.word or "").strip(),
                        "start": float(w.start or 0.0) if w.start is not None else None,
                        "end": float(w.end or 0.0) if w.end is not None else None,
                        "probability": float(w.probability) if w.probability is not None else None,
                    }
                )
    except Exception as exc:
        out = unavailable(
            schema=SCHEMA_SPEECH,
            tool=ASR_TOOL,
            reason="runtime_transcribe_failed",
            detail=str(exc)[:300],
        )
        out["reason"] = "runtime_transcribe_failed"
        out["model"] = model_size
        out["tool_version"] = tool_version
        out["source_hash"] = src_hash
        out["observed_at"] = observed_at
        out["segments"] = []
        out["words"] = []
        out["metrics"] = {"model_load_sec": load_sec, "from_cache": from_cache}
        out["provenance"] = {
            "audio_path": str(path),
            "download_root": str(download_root),
            "source_hash": src_hash,
        }
        return out
    asr_sec = round(time.perf_counter() - t_asr0, 3)

    transcript = " ".join(t.strip() for t in texts if t.strip()).strip()
    validation = validate_timestamp_evidence(segments=segments, words=words)
    word_ts_ok = bool(words) and any(w.get("start") is not None for w in words)

    issues: List[str] = list(validation.get("issues") or [])
    if not transcript and not segments and not words:
        issues.append("empty_transcript_and_timestamps")
    if segments and not word_ts_ok:
        issues.append("word_timestamps_absent")

    if validation.get("issues"):
        status = STATUS_FAIL
        reason = "timestamp_validation_failed"
    elif not transcript and not segments:
        status = STATUS_UNKNOWN
        reason = "empty_observation"
    else:
        status = STATUS_PASS
        reason = "observed"

    span = 0.0
    if segments:
        try:
            span = max(float(s.get("end") or 0) for s in segments) - min(
                float(s.get("start") or 0) for s in segments
            )
        except Exception:
            span = 0.0

    metrics = {
        "segment_count": len(segments),
        "word_count": len(words),
        "words_with_timestamps": sum(1 for w in words if w.get("start") is not None),
        "word_timestamps_requested": True,
        "word_timestamps_present": word_ts_ok,
        "duration_span_sec": round(max(0.0, span), 3),
        "model_load_sec": load_sec,
        "asr_execution_sec": asr_sec,
        "from_cache": from_cache,
        "audio_bytes": int(path.stat().st_size),
    }

    provenance = {
        "audio_path": str(path.resolve()) if path.exists() else str(path),
        "source_hash": src_hash,
        "download_root": str(download_root),
        "model": model_size,
        "device": device,
        "compute_type": compute_type,
        "beam_size": int(beam_size),
        "word_timestamps": True,
        "tool": ASR_TOOL,
        "tool_version": tool_version,
        "observed_at": observed_at,
        "schema_version": SCHEMA_VERSION,
    }

    return {
        "schema": SCHEMA_SPEECH,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "observation_executed": True,
        "provider_verified": True,
        "tool": ASR_TOOL,
        "tool_version": tool_version,
        "tool_alternate_rejected": ASR_ALTERNATE,
        "selection_reason": "windows_lighter_deps_cpu_fallback_already_installed",
        "model": model_size,
        "model_size": model_size,  # backward compatible
        "device": device,
        "compute_type": compute_type,
        "language_detected": getattr(info, "language", None),
        "language_probability": float(getattr(info, "language_probability", 0) or 0),
        "audio_path": str(path),
        "source_hash": src_hash,
        "observed_at": observed_at,
        "transcript": transcript,
        "segments": segments,
        "words": words,
        "speakers": [],
        "speaker_observation": "UNAVAILABLE",
        "speaker_note": "faster-whisper path does not claim diarization; pyannote deferred",
        "metrics": metrics,
        "provenance": provenance,
        "timestamp_validation": validation,
        "issues": issues,
        "unknown_as_pass": False,
        "authority": "observation_only",
        "does_not_replace": ["AudioPlan", "VoiceIdentity", "planned_srt"],
        "claims_semantic_truth": False,
    }


def compare_planned_vs_observed_timing(
    *,
    planned_cues: Sequence[Dict[str, Any]],
    observed: Dict[str, Any],
    tolerance_sec: float = 0.75,
) -> Dict[str, Any]:
    """Compare planned subtitle cues to ASR observation.

    Planned timing alone never yields PASS for 'actual' alignment.
    """
    if not observed or observed.get("status") == STATUS_UNAVAILABLE:
        return {
            "status": STATUS_UNAVAILABLE,
            "issues": ["speech_observation_unavailable"],
            "planned_as_actual_pass": False,
            "unknown_as_pass": False,
        }
    if not observed.get("observation_executed"):
        return {
            "status": STATUS_UNKNOWN,
            "issues": ["speech_observation_not_executed"],
            "planned_as_actual_pass": False,
            "unknown_as_pass": False,
        }

    issues: List[str] = []
    words = [w for w in (observed.get("words") or []) if w.get("start") is not None]
    segs = list(observed.get("segments") or [])
    if not planned_cues:
        issues.append("no_planned_cues")
    if not words and not segs:
        issues.append("no_observed_timestamps")

    def _end(c: dict) -> float:
        return float(c.get("end_time") or c.get("end") or 0)

    def _start(c: dict) -> float:
        return float(c.get("start_time") or c.get("start") or 0)

    if planned_cues and (words or segs):
        planned_end = max(_end(c) for c in planned_cues)
        obs_end = 0.0
        if words:
            obs_end = max(float(w.get("end") or 0) for w in words)
        elif segs:
            obs_end = max(float(s.get("end") or 0) for s in segs)
        if abs(planned_end - obs_end) > max(tolerance_sec, planned_end * 0.2):
            issues.append(
                f"planned_vs_observed_end_delta:{planned_end:.2f}->{obs_end:.2f}"
            )
        planned_start = min(_start(c) for c in planned_cues)
        obs_start = float(words[0]["start"]) if words else float(segs[0]["start"])
        if abs(planned_start - obs_start) > tolerance_sec + 0.5:
            issues.append(
                f"planned_vs_observed_start_delta:{planned_start:.2f}->{obs_start:.2f}"
            )

    if not issues and observed.get("status") == STATUS_PASS:
        status = STATUS_PASS
    elif issues and any("unavailable" in i for i in issues):
        status = STATUS_UNAVAILABLE
    elif issues:
        status = STATUS_FAIL
    else:
        status = STATUS_UNKNOWN

    return {
        "status": status,
        "issues": issues,
        "planned_cue_count": len(list(planned_cues or [])),
        "observed_word_count": len(words),
        "observed_segment_count": len(segs),
        "planned_as_actual_pass": False,
        "tolerance_sec": tolerance_sec,
        "unknown_as_pass": False,
        "method": "PLANNED_VS_ASR_OBSERVATION",
    }
