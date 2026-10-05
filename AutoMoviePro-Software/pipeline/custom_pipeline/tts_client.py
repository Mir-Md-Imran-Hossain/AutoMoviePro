"""Google Gemini TTS client — locked single-narrator identity across shots.

Root cause of per-shot "different person" drift (research):
  - Gemini TTS has NO seed / voice-pin; each generateContent is independent.
  - Strong per-shot emotion prompts ("shocked", "amazed", "urgent") make the
    model reinterpret persona/timbre — Google docs warn style must align with
    the prebuilt voice (Charon = informative), or output drifts.
  - Changing director text per shot amplifies run-to-run identity drift.
  - Legacy pipeline intentionally omits emotion from the speak prompt.

Fix:
  1) Identical AUDIO PROFILE + DIRECTOR NOTES on every call (only transcript changes)
  2) Emotion → soft delivery knobs only (never character/timbre words)
  3) Continuous mode: ONE API call for all shots of a language, then split audio
     by word-count ratios → guaranteed same speaker within the language
"""

from __future__ import annotations

import base64
import logging
import os
import re
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import httpx

from pipeline.custom_pipeline.quota_rotate import (
    NeedMoreApiKeysError,
    is_quota_http_error,
    mark_exhausted,
    record_success,
)
from pipeline.custom_pipeline.session_keys import get_session_tts_key, rotate_tts_key
from pipeline.custom_pipeline.tts_routing import (
    ENGINE_CF_AURA,
    ENGINE_CF_MELOTTS,
    ENGINE_EDGE,
    ENGINE_GOOGLE,
    next_google_failover_key,
    normalize_lang_code,
    resolve_tts_route,
)
from pipeline.lang_config import LANG_DISPLAY, MASTER_VOICE_NAME, resolve_locked_voice, tts_contract

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TTS_MODELS = (
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
    "gemini-3.1-flash-tts-preview",
)

_DEFAULT_TTS_GAP_SEC = 120.0
_gap_lock = threading.Lock()
_last_tts_call_mono: float = 0.0
# Lock first successful model per language so mid-run model hops don't change timbre
_locked_model_by_lang: Dict[str, str] = {}
_last_tts_metadata_by_lang: Dict[str, Dict[str, Any]] = {}


def get_last_tts_metadata(language_code: str = "") -> Dict[str, Any]:
    """Return dictionary of engine, voice, model, and key_slot for the last synthesized audio."""
    code = (language_code or "").lower().strip()[:2]
    return dict(_last_tts_metadata_by_lang.get(code) or {})

# Words that push Gemini into "acting a different person"
_PERSONA_WORDS = re.compile(
    r"\b("
    r"shocked|amazed|terrified|scared|angry|furious|whisper|scream|shout|"
    r"conspiratorial|sinister|robotic|child|girl|boy|female|woman|manly|"
    r"comic|cartoon|dramatic|theatrical|villain|hero|news.?anchor"
    r")\b",
    re.I,
)


def tts_call_gap_seconds() -> float:
    raw = (os.environ.get("AMP_TTS_CALL_GAP_SEC") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return _DEFAULT_TTS_GAP_SEC


def _wait_tts_gap(*, package_root: str = "") -> None:
    from pipeline.custom_pipeline.google_pacing_guard import wait_pacing_gap

    raw = (os.environ.get("AMP_TTS_CALL_GAP_SEC") or "").strip()
    if raw:
        try:
            gap = max(0.0, float(raw))
            if gap <= 0:
                return
        except ValueError:
            pass

    wait_pacing_gap(
        modality="audio",
        provider="google_tts",
        reason="gemini_tts_gap",
        package_root=package_root,
    )


def resolve_tts_models(*, language: str = "") -> list[str]:
    primary = (os.environ.get("CUSTOM_PIPELINE_TTS_MODEL") or "").strip()
    locked = _locked_model_by_lang.get((language or "").strip())
    out: list[str] = []
    seen = set()
    for m in ((locked,) if locked else ()) + ((primary,) if primary else ()) + DEFAULT_TTS_MODELS:
        name = (m or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def normalize_emotion_to_delivery(emotion_tag: str) -> str:
    """Map free-form emotion tags → soft delivery-only guidance (no persona shift)."""
    raw = (emotion_tag or "").strip()
    if not raw:
        return "Keep baseline Charon delivery; tiny natural variation only."

    low = raw.lower()
    energy = "medium"
    if any(w in low for w in ("urgent", "excited", "energetic", "hooked", "amazed", "shock")):
        energy = "slightly brighter"
    elif any(w in low for w in ("serious", "caution", "grounded", "warning", "thoughtful")):
        energy = "slightly calmer"
    elif any(w in low for w in ("warm", "friendly", "hopeful", "reassur", "inviting")):
        energy = "slightly warmer"

    # Strip persona-trigger words from any leftover echo
    cleaned = _PERSONA_WORDS.sub("", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;")
    hint = cleaned[:80] if cleaned else "natural conversational narration"
    return (
        f"Delivery micro-adjust only: energy={energy} (hint: {hint}). "
        f"CRITICAL: do NOT change speaker identity, timbre, pitch character, accent, age, or gender. "
        f"Same man, same throat, same Charon voice — only a tiny energy shift."
    )


def locked_audio_profile(voice_name: str, language_display: str) -> str:
    """Byte-stable identity block reused on EVERY shot / continuous call."""
    identity = (voice_name or MASTER_VOICE_NAME).strip() or MASTER_VOICE_NAME
    return (
        f"# AUDIO PROFILE\n"
        f"Name: Locked Narrator ({identity})\n"
        f"Voice preset: Gemini prebuilt `{identity}` (informative adult male)\n"
        f"Language: native {language_display} only\n"
        f"Archetype: one consistent adult male documentary YouTube narrator\n"
        f"Fixed traits: mid-low pitch, clear diction, calm confidence, no accent drift\n"
        f"Forbidden: female tone, child tone, cartoon, news-anchor switch, new persona per paragraph\n"
    )


def locked_director_notes(
    *,
    language_display: str,
    register: str,
    pace: str,
    delivery_line: str = "",
    continuous: bool = False,
) -> str:
    para = (
        "Between paragraphs take only a brief natural breath; "
        "do NOT change voice identity between paragraphs.\n"
        if continuous
        else ""
    )
    return (
        f"# DIRECTOR'S NOTES\n"
        f"- Speak as the SAME locked narrator for the entire output.\n"
        f"- Style: {register}\n"
        f"- Pace: {pace}\n"
        f"- Stay aligned with Charon (informative) — never fight the voice profile.\n"
        f"- Do not imitate Kore, Aoede, Leda, Puck, Zephyr, Fenrir, or any other preset.\n"
        f"- Do not change gender, pitch character, timbre, accent, or persona.\n"
        f"{para}"
        f"- {delivery_line or 'Keep baseline delivery.'}\n"
        f"- Enunciate the final word clearly; leave a short breath at the end.\n"
        f"- Do not add words beyond the transcript. Do not read these notes aloud.\n"
        f"- Language: natural native {language_display} only.\n"
    )


def build_locked_speak_prompt(
    text: str,
    *,
    language_code: str,
    emotion_tag: str = "",
    voice_name: str = "",
    target_duration_sec: float = 0.0,
    continuous: bool = False,
) -> str:
    """Identity-first speak prompt — emotion cannot rewrite the speaker."""
    lang = (language_code or "en").lower().strip()[:2]
    contract = tts_contract(lang)
    name = LANG_DISPLAY.get(lang, contract.get("english_name") or lang)
    register = contract.get("register") or f"natural {name} narration"
    pace = contract.get("pace_hint") or "clear steady pace"
    identity = resolve_locked_voice(voice_name, language_hint=lang)
    delivery = normalize_emotion_to_delivery(emotion_tag)

    dur_line = ""
    if (not continuous) and target_duration_sec and target_duration_sec > 0.5:
        # Soft hint only — hard duration targets cause unnatural pace jumps between shots
        dur_line = (
            f"- Approximate length near {float(target_duration_sec):.0f}s without rushing; "
            f"never change voice to fit the clock.\n"
        )

    return (
        "════════════════════════════════════════════════════════════\n"
        "TTS SPEAK PROMPT (Locked Narrator — Cultural Voice)\n"
        "════════════════════════════════════════════════════════════\n"
        "Task: Read aloud ONLY the transcript as speech audio for a YouTube video.\n"
        "Strict rules:\n"
        "- Keep the SAME locked narrator identity for the entire output.\n"
        "- Do NOT change gender, pitch, timbre, accent, or persona between sentences.\n"
        "- Do NOT add words, translate, summarize, or comment — speak the transcript only.\n"
        "- Do NOT read the director notes or profile aloud.\n"
        "- Emotion may only soften delivery (pace/warmth); it must NEVER rewrite the voice persona.\n"
        "- Sound like a natural native speaker of the target language — human, not robotic.\n"
        "- Enunciate the final word clearly; leave a short breath at the end.\n\n"
        f"{locked_audio_profile(identity, name)}\n"
        f"{locked_director_notes(language_display=name, register=register, pace=pace, delivery_line=delivery, continuous=continuous)}"
        f"{dur_line}\n"
        f"# TRANSCRIPT (speak this exactly)\n"
        f"{text.strip()}\n"
    )


# Back-compat alias
def build_emotion_speak_prompt(*args, **kwargs) -> str:
    return build_locked_speak_prompt(*args, **kwargs)


def synthesize_shot_audio(
    text: str,
    out_path: Path,
    *,
    language: str,
    language_code: str,
    emotion_tag: str = "",
    voice_name: str = "",
    target_duration_sec: float = 0.0,
    api_key: Optional[str] = None,
    timeout: float = 90.0,
) -> Path:
    """Synthesize one shot with locked narrator prompt."""
    clean = (text or "").strip()
    if not clean:
        raise ValueError("TTS text is empty")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    voice = resolve_locked_voice(voice_name, language_hint=language_code)
    prompt = build_locked_speak_prompt(
        clean,
        language_code=language_code,
        emotion_tag=emotion_tag,
        voice_name=voice,
        target_duration_sec=target_duration_sec,
        continuous=False,
    )
    return _synthesize_to_path(
        prompt,
        out_path,
        language=language,
        language_code=language_code,
        voice_name=voice,
        api_key=api_key,
        timeout=timeout,
        raw_text=clean,
    )


def synthesize_continuous_narration(
    shot_texts: Sequence[str],
    out_full_path: Path,
    *,
    language: str,
    language_code: str,
    voice_name: str = "",
    emotion_tags: Optional[Sequence[str]] = None,
    api_key: Optional[str] = None,
    timeout: float = 180.0,
) -> Path:
    """One API call for all shots → single continuous audio (same speaker guaranteed)."""
    parts = [t.strip() for t in shot_texts if (t or "").strip()]
    if not parts:
        raise ValueError("No shot texts for continuous TTS")

    # Mild global delivery from first/last emotions only — still no persona words
    tags = list(emotion_tags or [])
    global_emotion = ""
    if tags:
        # Prefer a neutral blend cue rather than the strongest tag
        global_emotion = "warm, conversational, natural storytelling"

    body = "\n\n".join(parts)
    voice = resolve_locked_voice(voice_name, language_hint=language_code)
    prompt = build_locked_speak_prompt(
        body,
        language_code=language_code,
        emotion_tag=global_emotion,
        voice_name=voice,
        continuous=True,
    )
    out_full_path = Path(out_full_path)
    out_full_path.parent.mkdir(parents=True, exist_ok=True)
    return _synthesize_to_path(
        prompt,
        out_full_path,
        language=language,
        language_code=language_code,
        voice_name=voice,
        api_key=api_key,
        timeout=timeout,
        raw_text=body,
    )


def split_audio_by_word_ratios(
    source_audio: Path,
    shot_texts: Sequence[str],
    out_paths: Sequence[Path],
) -> List[Path]:
    """Split continuous narration into per-shot files by word-count time ratios."""
    src = Path(source_audio)
    if not src.is_file():
        raise FileNotFoundError(src)
    if len(shot_texts) != len(out_paths):
        raise ValueError("shot_texts and out_paths length mismatch")

    weights = [max(1, len((t or "").split())) for t in shot_texts]
    total_w = float(sum(weights)) or 1.0
    ratios = [w / total_w for w in weights]

    # Prefer wav for clean sample-accurate splits
    wav = src.with_suffix(".wav")
    if src.suffix.lower() != ".wav":
        if not _m4a_to_wav(src, wav):
            # fall back: re-encode via ffmpeg copy decode
            if not _any_to_wav(src, wav):
                raise RuntimeError(f"Cannot decode TTS audio for split: {src}")
    else:
        wav = src

    with wave.open(str(wav), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        pcm = wf.readframes(nframes)

    produced: List[Path] = []
    cursor = 0
    for i, (ratio, out_p) in enumerate(zip(ratios, out_paths)):
        out_p = Path(out_p)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        if i == len(ratios) - 1:
            take = nframes - cursor
        else:
            take = int(round(nframes * ratio))
            take = max(1, min(take, nframes - cursor - (len(ratios) - i - 1)))
        start_byte = cursor * nchannels * sampwidth
        end_byte = (cursor + take) * nchannels * sampwidth
        chunk = pcm[start_byte:end_byte]
        cursor += take

        part_wav = out_p.with_suffix(".wav")
        with wave.open(str(part_wav), "wb") as wf:
            wf.setnchannels(nchannels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(framerate)
            wf.writeframes(chunk)

        m4a = out_p.with_suffix(".m4a")
        if _wav_to_m4a(part_wav, m4a):
            try:
                part_wav.unlink()
            except Exception:
                pass
            produced.append(m4a)
        else:
            produced.append(part_wav)
    return produced


def _synthesize_via_edge(
    text: str,
    out_path: Path,
    *,
    language_code: str,
    voice: str,
) -> Path:
    from pipeline.edge_tts_fallback import synthesize_edge_tts

    c = (language_code or "").lower().strip()[:2]
    _last_tts_metadata_by_lang[c] = {
        "engine": ENGINE_EDGE,
        "voice": voice,
        "model": "edge-tts",
        "key_slot": "",
    }
    logger.info(
        "TTS route EDGE lang=%s voice=%s (no Google call)",
        language_code,
        voice,
    )
    return synthesize_edge_tts(
        text,
        out_path,
        language_hint=language_code,
        voice_name=voice,
        honor_voice=True,
    )


def _synthesize_to_path(
    prompt: str,
    out_path: Path,
    *,
    language: str,
    language_code: str = "",
    voice_name: str,
    api_key: Optional[str] = None,
    timeout: float = 90.0,
    raw_text: str = "",
) -> Path:
    """Route by Engine Allocation Matrix, then synthesize.

    en/hi/ur → Edge-TTS only.
    bn/ta/ml → Google dual-key with 90% preemptive switch + 429 secondary
               + Edge fallback when both Google keys are dead.
    """
    code = normalize_lang_code(language_code or language)
    route = resolve_tts_route(code)
    logger.info("TTS route decision %s", route.to_dict())

    # Explicit Edge (matrix free langs OR dual-key exhausted already)
    if route.engine == ENGINE_EDGE:
        speak = (raw_text or "").strip()
        if not speak:
            # prompt still works poorly for Edge — extract transcript block if present
            speak = prompt
            if "# TRANSCRIPT" in prompt:
                speak = prompt.split("# TRANSCRIPT", 1)[-1].strip()
        return _synthesize_via_edge(
            speak,
            out_path,
            language_code=code,
            voice=route.voice or route.fallback_voice,
        )

    # Cloudflare MeloTTS / Deepgram Aura path (free tier friendly)
    if route.engine in (ENGINE_CF_MELOTTS, ENGINE_CF_AURA):
        speak = (raw_text or "").strip()
        if not speak:
            speak = prompt
            if "# TRANSCRIPT" in prompt:
                speak = prompt.split("# TRANSCRIPT", 1)[-1].strip()
        try:
            from pipeline.custom_pipeline.tts_cloudflare import (
                synthesize_aura,
                synthesize_melotts,
            )
            if route.engine == ENGINE_CF_MELOTTS:
                return synthesize_melotts(
                    speak,
                    out_path,
                    language=code,
                    api_key=route.api_key,
                    account_id=route.cf_account_id,
                )
            else:
                return synthesize_aura(
                    speak,
                    out_path,
                    language=code,
                    speaker=route.aura_speaker,
                    api_key=route.api_key,
                    account_id=route.cf_account_id,
                )
        except Exception as exc:
            logger.warning(
                "Cloudflare TTS (%s) failed: %s. Falling back to %s (%s)",
                route.engine,
                exc,
                route.fallback_engine or ENGINE_EDGE,
                route.fallback_voice,
            )
            return _synthesize_via_edge(
                speak or prompt,
                out_path,
                language_code=code,
                voice=route.fallback_voice or route.voice or "en-US-JennyNeural",
            )

    # Contract guard: en / hi / ur are Edge-only languages and must NEVER call Google AI Studio
    if code in ("en", "hi", "ur"):
        logger.warning(
            "TTS policy guard: lang=%s is an Edge-only language per routing contract; ensuring Edge-TTS synthesis.",
            code,
        )
        speak = (raw_text or "").strip()
        if not speak and "# TRANSCRIPT" in prompt:
            speak = prompt.split("# TRANSCRIPT", 1)[-1].strip()
        return _synthesize_via_edge(
            speak or prompt,
            out_path,
            language_code=code,
            voice=route.voice or route.fallback_voice or "en-US-JennyNeural",
        )

    # Google AI Studio path with dual-key failover
    models = resolve_tts_models(language=language)
    last_err: Optional[Exception] = None
    decision = route
    attempts = 0
    while attempts < 6:
        attempts += 1
        if decision.engine == ENGINE_EDGE:
            speak = (raw_text or "").strip()
            if not speak and "# TRANSCRIPT" in prompt:
                speak = prompt.split("# TRANSCRIPT", 1)[-1].strip()
            return _synthesize_via_edge(
                speak or prompt,
                out_path,
                language_code=code,
                voice=decision.voice or decision.fallback_voice,
            )

        key = (api_key if attempts == 1 and api_key else "") or decision.api_key
        if not key:
            # Fall back to session sticky pool (legacy) then Edge
            try:
                key = get_session_tts_key(language, explicit=None)
                decision.api_key = key
                decision.key_slot = decision.key_slot or "pool"
            except NeedMoreApiKeysError:
                fb = next_google_failover_key(decision)
                if fb and fb.engine == ENGINE_EDGE:
                    decision = fb
                    continue
                raise

        rotated = False
        for model_id in models:
            try:
                _wait_tts_gap()
                pcm = _tts_via_rest(
                    key, prompt, model=model_id, voice_name=voice_name, timeout=timeout
                )
                wav = out_path.with_suffix(".wav")
                _pcm_to_wav(pcm, wav)
                _last_tts_metadata_by_lang[code] = {
                    "engine": ENGINE_GOOGLE,
                    "voice": voice_name or MASTER_VOICE_NAME,
                    "model": model_id,
                    "key_slot": decision.key_slot,
                    "key_tail": key[-4:] if len(key) >= 4 else "",
                }
                m4a = out_path.with_suffix(".m4a")
                if _wav_to_m4a(wav, m4a):
                    record_success("google_tts", key)
                    _locked_model_by_lang[language] = model_id
                    logger.info(
                        "TTS OK lang=%s engine=GOOGLE slot=%s model=%s key…%s → %s",
                        language,
                        decision.key_slot,
                        model_id,
                        key[-4:],
                        m4a.name,
                    )
                    try:
                        from pipeline.custom_pipeline.google_pacing_guard import post_generation_cooldown

                        post_generation_cooldown(modality="audio", provider="google_tts")
                    except Exception:
                        pass
                    return m4a
                record_success("google_tts", key)
                _locked_model_by_lang[language] = model_id
                try:
                    from pipeline.custom_pipeline.google_pacing_guard import post_generation_cooldown

                    post_generation_cooldown(modality="audio", provider="google_tts")
                except Exception:
                    pass
                return wav
            except NeedMoreApiKeysError:
                raise
            except Exception as exc:
                last_err = exc
                msg = str(exc)
                logger.warning(
                    "TTS %s lang=%s slot=%s key…%s failed: %s",
                    model_id,
                    language,
                    decision.key_slot,
                    key[-4:],
                    msg[:160],
                )
                if "503" in msg or "high demand" in msg.lower():
                    continue

                from pipeline.custom_pipeline.google_pacing_guard import analyze_quota_error

                qa = analyze_quota_error(msg)
                if qa.is_quota and qa.can_auto_wait:
                    logger.warning(
                        "TTS quota touched (%s, wait %s). Pausing pipeline to let quota refill...",
                        qa.window_type,
                        qa.human_duration,
                    )
                    time.sleep(qa.cooldown_seconds)
                    continue

                if (
                    is_quota_http_error(exc)
                    or "429" in msg
                    or "ResourceExhausted" in msg
                    or "403" in msg
                    or "401" in msg
                ):
                    try:
                        auth_like = any(
                            x in msg.lower()
                            for x in (
                                "401",
                                "403",
                                "permission",
                                "suspended",
                                "denied access",
                                "unauthorized",
                            )
                        )
                        hours = 24.0 if auth_like else max(1.0, qa.cooldown_seconds / 3600.0)
                        mark_exhausted(
                            "google_tts",
                            key,
                            reason=f"quota:{qa.window_type}" if not auth_like else msg[:80],
                            hours=hours,
                        )
                    except Exception:
                        pass
                    # Catch-block: secondary key, then Edge
                    nxt = next_google_failover_key(decision)
                    if nxt is None:
                        try:
                            rotate_tts_key(language, reason=msg[:80])
                        except NeedMoreApiKeysError:
                            # Break inner loop to trigger final Edge fallback below
                            break
                        rotated = True
                        break
                    decision = nxt
                    api_key = None  # don't reuse explicit after failover
                    rotated = True
                    break
                continue
        if rotated:
            continue
        break

    # Last resort: Edge fallback so the job never hard-fails on Google quota
    cfg_voice = (decision.fallback_voice or decision.voice or "").strip()
    if cfg_voice or code in ("bn", "ta", "ml"):
        from pipeline.custom_pipeline.tts_routing import lang_route

        voice = cfg_voice or str(lang_route(code).get("fallback_voice") or "")
        if voice:
            logger.warning(
                "TTS Google exhausted lang=%s — final Edge fallback voice=%s err=%s",
                language,
                voice,
                str(last_err)[:120],
            )
            speak = (raw_text or "").strip()
            if not speak and "# TRANSCRIPT" in prompt:
                speak = prompt.split("# TRANSCRIPT", 1)[-1].strip()
            return _synthesize_via_edge(
                speak or prompt,
                out_path,
                language_code=code,
                voice=voice,
            )

    raise RuntimeError(f"Custom pipeline TTS failed lang={language}: {last_err}")


def _tts_via_rest(
    api_key: str,
    prompt: str,
    *,
    model: str,
    voice_name: str,
    timeout: float,
) -> bytes:
    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice_name or MASTER_VOICE_NAME
                    }
                }
            },
        },
    }
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
        data = r.json()
    b64 = _extract_audio_b64(data)
    if not b64:
        raise RuntimeError("No audio in Gemini TTS response")
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


def _ffmpeg() -> str:
    try:
        from pipeline.compose import ffmpeg_bin

        return ffmpeg_bin()
    except Exception:
        return "ffmpeg"


def _wav_to_m4a(wav: Path, m4a: Path) -> bool:
    cmd = [_ffmpeg(), "-y", "-i", str(wav), "-c:a", "aac", "-b:a", "192k", str(m4a)]
    r = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return r.returncode == 0 and m4a.exists()


def _m4a_to_wav(m4a: Path, wav: Path) -> bool:
    return _any_to_wav(m4a, wav)


def _any_to_wav(src: Path, wav: Path) -> bool:
    cmd = [_ffmpeg(), "-y", "-i", str(src), "-ac", "1", "-ar", "24000", str(wav)]
    r = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return r.returncode == 0 and wav.exists()


def concat_audio_files(parts: list[Path], out_path: Path) -> Optional[Path]:
    usable = [p for p in parts if p and Path(p).is_file()]
    if not usable:
        return None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(usable) == 1:
        import shutil

        shutil.copy2(usable[0], out_path)
        return out_path
    list_file = out_path.with_suffix(".concat.txt")
    lines = []
    for p in usable:
        ap = str(Path(p).resolve()).replace("'", r"'\''")
        lines.append(f"file '{ap}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [
        _ffmpeg(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(out_path),
    ]
    r = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    try:
        list_file.unlink(missing_ok=True)
    except Exception:
        pass
    if r.returncode == 0 and out_path.exists():
        return out_path
    logger.warning("TTS concat failed: %s", (r.stderr or r.stdout or "")[:200])
    return None
