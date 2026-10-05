from __future__ import annotations

import base64
import logging
import os
import subprocess
import time
import wave
from pathlib import Path
from typing import List, Optional

import httpx

from pipeline.compose import ffmpeg_bin, ffprobe_duration
from pipeline.lang_config import LANG_DISPLAY, SOURCE_LANG, tts_contract, resolve_locked_voice

logger = logging.getLogger(__name__)

# Current Google AI Studio TTS models (newest first)
TTS_MODELS = [
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
]


def synthesize_narration(
    text: str,
    out_path: Path,
    *,
    google_api_keys: Optional[List[str]] = None,
    voice_name: str = "",
    language_hint: str = SOURCE_LANG,
    max_retries_per_key: int = 2,
    target_duration_sec: float = 0.0,
    idempotency_work_dir: Optional[Path] = None,
    idempotency_job_id: str = "",
    idempotency_scene_id: int = 0,
    idempotency_dialogue_id: str = "",
    idempotency_part_index: int = 0,
    idempotency_segment_id: str = "",
    allow_idempotent_edge_fallback: bool = True,
) -> Path:
    """
    Google AI Studio Gemini TTS → M4A/WAV.
    language_hint selects locale prompt + default voice (en/bn/hi/ur/ta/ml/…).
    target_duration_sec nudges documentary pace so clips match neighbors.
    """
    lang = (language_hint or SOURCE_LANG).lower().strip()
    contract = tts_contract(lang)
    voice = resolve_locked_voice(voice_name, language_hint=lang)
    if lang[:2] == SOURCE_LANG:
        try:
            from pipeline.master_lang import ensure_english_text, looks_like_english_master

            if not looks_like_english_master(text):
                text, meta = ensure_english_text(
                    text,
                    google_api_keys=google_api_keys,
                    field="narration",
                )
                logger.warning("TTS English choke repaired narration via=%s", meta.get("via"))
        except Exception as exc:
            logger.warning("TTS English choke skipped: %s", exc)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from pipeline.dialogue_uniqueness import sanitize_spoken_narration

        text = sanitize_spoken_narration(text)
    except Exception:
        pass
    keys = [k.strip() for k in (google_api_keys or []) if (k or "").strip()]
    if not keys:
        raise RuntimeError("Google AI Studio API key required for TTS")

    try:
        from pipeline.live_activity import note_api

        note_api(
            "google",
            f"tts:{lang}",
            "call",
            request=text[:120],
            dest=str(out_path),
        )
    except Exception:
        pass

    from pipeline.tts_key_map import (
        keys_for_tts_language_with_fallback,
        on_tts_key_rejected,
        on_tts_success,
    )

    # Deterministic failover list across configured Google credentials (cooled keys preferred-out)
    usable = keys_for_tts_language_with_fallback(keys, lang)
    if not usable:
        usable = [k for k in keys if (k or "").strip()][:1]

    speak_prompt = _speak_prompt(
        text,
        lang=lang,
        contract=contract,
        voice_name=voice,
        target_duration_sec=float(target_duration_sec or 0.0),
    )

    last_err: Optional[Exception] = None
    from pipeline.llm_router import is_daily_quota_zero
    from pipeline.quota_backoff import key_fingerprint, key_is_cooling, record_key_quota_hit
    from pipeline.google_api_gate import _record_call
    from pipeline.provider_error_class import (
        CLASS_403,
        CLASS_429,
        CLASS_503,
        classify_provider_failure,
    )
    from pipeline.tts_credential_diagnostics import append_synth_attempt, mark_tts_ready

    quota_rejects = 0
    keys_tried = 0
    last_reject_class = ""
    request_id = f"{lang}:{hash(text) & 0xFFFFFFFF:08x}:{out_path.name}"
    # FIX: Default "0" → Google Charon TTS is PRIMARY (premium quality).
    # Set AMP_PREFER_EDGE_TTS=1 only to force Edge TTS (e.g. quota emergency).
    abort_google = (os.environ.get("AMP_PREFER_EDGE_TTS") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    # Group 4 requirement: Indic languages (bn, ta, ml) strictly prioritize Google AI Studio
    # because direct Edge-TTS sounds robotic; Edge-TTS is only used as an absolute quota exhaustion fallback.
    if lang in ("bn", "ta", "ml"):
        abort_google = False

    # AMP_ALLOW_GOOGLE_TTS kept for backward compat (legacy override, now redundant)
    if (os.environ.get("AMP_ALLOW_GOOGLE_TTS") or "").strip().lower() in ("1", "true", "yes"):
        abort_google = False
    if abort_google:
        last_err = RuntimeError("AMP_PREFER_EDGE_TTS=1 (Google Charon TTS skipped by env — Edge fallback active)")
        last_reject_class = "prefer_edge"

    for key_i, key in enumerate(usable):
        if abort_google:
            break
        keys_tried += 1
        fp = key_fingerprint(key)
        for model in TTS_MODELS[:1]:  # ONE TTS model per key — no 3-model spray
            if abort_google:
                break
            for attempt in range(1, max_retries_per_key + 1):
                endpoint_used = "sdk:google.genai.models.generate_content"
                try:
                    try:
                        _record_call()
                    except Exception as budget_exc:
                        # Hourly gate exhausted — stop key spray; Edge/Piper fallback next
                        last_err = budget_exc
                        last_reject_class = "hourly_budget"
                        abort_google = True
                        raise RuntimeError(f"google_hourly_budget:{budget_exc}") from budget_exc
                    pcm = _tts_via_sdk(key, speak_prompt, model=model, voice_name=voice)
                    # REST only when SDK unavailable / parse miss — not after a raised quota error
                    if pcm is None:
                        endpoint_used = (
                            f"https://generativelanguage.googleapis.com/v1beta/models/"
                            f"{model}:generateContent"
                        )
                        pcm = _tts_via_rest(key, speak_prompt, model=model, voice_name=voice)
                    wav = out_path.with_suffix(".wav")
                    _pcm_to_wav(pcm, wav)
                    m4a = out_path.with_suffix(".m4a")
                    mark_tts_ready(
                        fingerprint12=fp,
                        suffix=key[-4:],
                        model=model,
                        endpoint=endpoint_used,
                    )
                    append_synth_attempt(
                        Path(idempotency_work_dir) if idempotency_work_dir else None,
                        {
                            "request_id": request_id,
                            "slot_order": key_i,
                            "fingerprint12": fp,
                            "suffix": key[-4:],
                            "model": model,
                            "endpoint": endpoint_used,
                            "http_status": 200,
                            "failure_class": None,
                            "retry_count": attempt - 1,
                            "cooldown_state": key_is_cooling(key),
                            "request_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "duplicate_of_request": False,
                            "tts_success": True,
                            "lang": lang,
                        },
                    )
                    if _wav_to_m4a(wav, m4a):
                        on_tts_success(lang)
                        try:
                            from pipeline.live_activity import note_api

                            note_api(
                                "google",
                                f"tts:{lang}",
                                "ok",
                                request=text[:80],
                                response=f"audio {m4a.name} slot…{key[-4:]}",
                                dest=str(m4a),
                            )
                        except Exception:
                            pass
                        return m4a
                    on_tts_success(lang)
                    try:
                        from pipeline.live_activity import note_api

                        note_api(
                            "google",
                            f"tts:{lang}",
                            "ok",
                            request=text[:80],
                            response=f"audio {wav.name} slot…{key[-4:]}",
                            dest=str(wav),
                        )
                    except Exception:
                        pass
                    return wav
                except Exception as exc:
                    last_err = exc
                    if "google_hourly_budget" in str(exc) or "hourly budget" in str(exc).lower():
                        last_reject_class = "hourly_budget"
                        abort_google = True
                        break
                    from pipeline.api_keys import redact_sensitive_text

                    classified = classify_provider_failure(exc)
                    msg = classified.get("safe_message") or redact_sensitive_text(str(exc))
                    logger.warning(
                        "Google TTS %s lang=%s voice=%s key…%s attempt %s class=%s http=%s: %s",
                        model,
                        lang,
                        voice,
                        key[-4:],
                        attempt,
                        classified["class"],
                        classified.get("http_status"),
                        msg[:200],
                    )
                    append_synth_attempt(
                        Path(idempotency_work_dir) if idempotency_work_dir else None,
                        {
                            "request_id": request_id,
                            "slot_order": key_i,
                            "fingerprint12": fp,
                            "suffix": key[-4:],
                            "model": model,
                            "endpoint": endpoint_used,
                            "http_status": classified.get("http_status"),
                            "failure_class": classified["class"],
                            "provider_reason": classified.get("provider_reason"),
                            "project_identity": classified.get("project_identity"),
                            "retry_count": attempt - 1,
                            "cooldown_state": key_is_cooling(key),
                            "request_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "duplicate_of_request": False,
                            "tts_success": False,
                            "lang": lang,
                            "safe_message": msg[:240],
                        },
                    )
                    fclass = classified["class"]
                    try:
                        from pipeline.idempotency.metrics import UsageEvent, record_usage_event

                        record_usage_event(
                            Path(idempotency_work_dir) if idempotency_work_dir else None,
                            UsageEvent(
                                operation="tts_google",
                                provider="google",
                                model=str(model or "google-tts"),
                                status_code_class=str(fclass),
                                outcome="retry" if fclass in (CLASS_429, CLASS_503) else "failure",
                                detail=str(msg)[:80],
                            ),
                        )
                    except Exception:
                        pass
                    if fclass == CLASS_429:
                        quota_rejects += 1
                        last_reject_class = CLASS_429
                        record_key_quota_hit(key, "google")
                        on_tts_key_rejected(
                            lang,
                            reason="daily_quota_zero" if is_daily_quota_zero(exc) else "429_or_quota",
                        )
                        break  # failover next key — no same-key retry
                    if fclass == CLASS_403:
                        last_reject_class = CLASS_403
                        record_key_quota_hit(key, "google")
                        on_tts_key_rejected(lang, reason="key_suspended_or_denied")
                        break  # config failure — no unnecessary retry
                    if fclass == CLASS_503:
                        last_reject_class = CLASS_503
                        # Controlled retry once on same key, then failover
                        if attempt < min(2, max_retries_per_key):
                            time.sleep(1.5 * attempt)
                            continue
                        on_tts_key_rejected(lang, reason="503_failover")
                        break
                    last_reject_class = classified.get("provider_reason") or "non_quota"
                    if attempt < max_retries_per_key:
                        time.sleep(1.5 * attempt)
                        continue
                    break
            else:
                continue
            break

    # Honest status: only claim pool exhaustion when every tried key hit quota/rate-limit
    all_quota = keys_tried > 0 and quota_rejects >= keys_tried
    safe_last = ""
    try:
        from pipeline.api_keys import redact_sensitive_text

        safe_last = redact_sensitive_text(str(last_err)[:160] if last_err else "none")
    except Exception:
        safe_last = (str(last_err)[:80] if last_err else "none")
    if all_quota:
        fail_note = (
            f"all_tried_keys_quota_or_rate_limit tried={keys_tried} "
            f"quota_rejects={quota_rejects} last={last_reject_class}"
        )
    else:
        fail_note = (
            f"google_tts_failed tried={keys_tried} quota_rejects={quota_rejects} "
            f"last_class={last_reject_class or 'unknown'} "
            f"last_err={safe_last}"
        )

    if idempotency_work_dir is not None and allow_idempotent_edge_fallback:
        try:
            from pipeline.idempotency.tts_bridge import idempotent_edge_tts

            logger.warning("Google TTS unavailable (%s) — idempotent Edge-TTS fallback", fail_note)
            return idempotent_edge_tts(
                Path(idempotency_work_dir),
                job_id=idempotency_job_id or Path(idempotency_work_dir).name,
                scene_id=idempotency_scene_id,
                dialogue_text=text,
                out_path=out_path,
                language_hint=lang,
                voice_name=voice_name,
                dialogue_id=idempotency_dialogue_id,
                part_index=idempotency_part_index,
                segment_id=idempotency_segment_id,
            )
        except Exception as edge_exc:
            logger.warning("Idempotent Edge-TTS fallback failed: %s", edge_exc)
    try:
        from pipeline.edge_tts_fallback import synthesize_edge_tts

        logger.warning("Google TTS unavailable (%s) — falling back to Edge-TTS", fail_note)
        return synthesize_edge_tts(
            text,
            out_path,
            language_hint=lang,
            voice_name="",
        )
    except Exception as edge_exc:
        logger.warning("Edge-TTS fallback failed: %s", edge_exc)

    # Optional offline Piper slot (UNAVAILABLE if binary/model missing)
    try:
        from pipeline.piper_tts_fallback import piper_tool_available, synthesize_piper_tts

        avail = piper_tool_available()
        if avail.get("available"):
            logger.warning(
                "Google+Edge TTS unavailable (%s) — trying Piper offline fallback",
                fail_note,
            )
            return synthesize_piper_tts(
                text,
                out_path,
                language_hint=lang,
                voice_name=voice_name or "",
            )
        logger.info(
            "Piper TTS slot UNAVAILABLE (optional offline) — %s",
            avail.get("status"),
        )
    except Exception as piper_exc:
        logger.warning("Piper TTS fallback failed/unavailable: %s", piper_exc)

    raise RuntimeError(f"Google AI Studio TTS failed: {fail_note}; last={last_err}") from last_err


def _speak_prompt(
    text: str,
    *,
    lang: str,
    contract: dict,
    voice_name: str = "",
    target_duration_sec: float = 0.0,
) -> str:
    from pipeline.lang_config import MASTER_VOICE_NAME

    name = LANG_DISPLAY.get(lang, contract.get("english_name") or lang)
    register = contract.get("register") or f"natural {name} narration"
    pace = contract.get("pace_hint") or "clear steady pace"
    identity = (voice_name or MASTER_VOICE_NAME).strip() or MASTER_VOICE_NAME
    last = ""
    words = [w for w in (text or "").replace("\n", " ").split(" ") if w.strip()]
    if words:
        last = words[-1].strip(".,!?;:\"'")
    dur_line = ""
    if target_duration_sec and target_duration_sec > 0.5:
        dur_line = (
            f"Fit the full transcript into about {target_duration_sec:.1f} seconds — "
            f"neither rushed nor dragged; match a calm documentary cadence. "
        )
    finish_line = (
        f"Enunciate every syllable of the FINAL word clearly"
        + (f" ('{last}')" if last else "")
        + "; never mumble, swallow, or cut the ending. "
        f"Leave a brief natural breath after the last word. "
    )
    en_lock = ""
    if lang[:2] == SOURCE_LANG:
        en_lock = (
            "The transcript is English master — speak English only. "
            "If any Bangla/Hindi/Hinglish slipped in, skip those words and stay English. "
        )
    return (
        f"Speak the following {name} narration in ONE consistent adult male documentary voice. "
        f"You are the locked narrator identity '{identity}' (Gemini prebuilt Charon timbre): "
        f"informative adult male, same pitch across every clip. "
        f"Do not sound female. Do not imitate Kore, Aoede, Leda, Jenny, or Zephyr. "
        f"Do not change gender, pitch character, or persona mid-script. "
        f"Style: {register}. Pace: {pace}. "
        f"{en_lock}{dur_line}{finish_line}"
        f"Do not add words beyond the transcript.\n"
        f"Transcript:\n{text}"
    )


def _tts_via_sdk(api_key: str, prompt: str, *, model: str, voice_name: str) -> Optional[bytes]:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None

    # google-genai AFC can hang indefinitely on a dead/slow key — hard-cap the wait.
    import concurrent.futures

    def _call():
        client = genai.Client(api_key=api_key)
        return client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                    )
                ),
            ),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_call)
        try:
            resp = fut.result(timeout=75.0)
        except concurrent.futures.TimeoutError as exc:
            raise RuntimeError(f"TTS SDK timeout after 75s model={model}") from exc

    try:
        parts = resp.candidates[0].content.parts
        for part in parts:
            inline = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
            if inline is not None:
                data = getattr(inline, "data", None)
                if data:
                    if isinstance(data, str):
                        return base64.b64decode(data)
                    return bytes(data)
    except Exception:
        pass
    return None


def _tts_via_rest(api_key: str, prompt: str, *, model: str, voice_name: str) -> bytes:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}
            },
        },
    }
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    with httpx.Client(timeout=75.0) as client:
        r = client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
        data = r.json()
    b64 = _extract_audio_b64(data)
    if not b64:
        raise RuntimeError("No audio in Google AI Studio TTS response")
    pcm = base64.b64decode(b64)
    if len(pcm) < 100:
        raise RuntimeError("Audio too small")
    return pcm


def _extract_audio_b64(data: dict) -> Optional[str]:
    for cand in data.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data") or {}
            if inline.get("data"):
                return inline["data"]
    return None


def _pcm_to_wav(pcm: bytes, path: Path, sample_rate: int = 24000) -> Path:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return path


def _wav_to_m4a(wav: Path, m4a: Path) -> bool:
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(wav),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(m4a),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and m4a.exists()


def audio_duration(path: Path) -> float:
    return ffprobe_duration(path)
