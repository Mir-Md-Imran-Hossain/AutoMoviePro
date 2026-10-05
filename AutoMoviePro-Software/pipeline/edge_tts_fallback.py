"""
Keyless TTS fallback via Microsoft Edge online voices (edge-tts).

Used when Google Gemini TTS quota is exhausted. No API key required.
Always a locked male Neural voice — never Jenny/Nabanita/Gemini names.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional

from pipeline.compose import ffmpeg_bin
from pipeline.lang_config import SOURCE_LANG, edge_voice_chain, resolve_edge_voice

logger = logging.getLogger(__name__)


def synthesize_edge_tts(
    text: str,
    out_path: Path,
    *,
    language_hint: str = SOURCE_LANG,
    voice_name: str = "",
    honor_voice: bool = False,
) -> Path:
    """Synthesize via Microsoft Edge neural voices (keyless).

    honor_voice=True: use the exact Neural name from the TTS routing matrix
    (Jenny/Swara/Uzma/Nabanita/…). Default False keeps the legacy male-lock
    remap via resolve_edge_voice for older call sites.
    """
    text = (text or "").strip()
    if not text:
        raise RuntimeError("empty text for edge-tts")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lang = (language_hint or "en").lower().strip()[:2]
    requested = (voice_name or "").strip()
    if honor_voice and requested and "neural" in requested.lower():
        primary = requested
        chain = [primary]
        # Optional same-locale male/alt Neural if primary fails
        try:
            for alt in edge_voice_chain(lang):
                if alt.lower() != primary.lower():
                    chain.append(alt)
        except Exception:
            pass
    else:
        primary = resolve_edge_voice(voice_name, language_hint=lang)
        chain = [primary] + [
            v for v in edge_voice_chain(lang) if v.lower() != primary.lower()
        ]
    mp3 = out_path.with_suffix(".mp3")
    m4a = out_path.with_suffix(".m4a")

    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError(
            "edge-tts not installed. Run: pip install edge-tts"
        ) from exc

    last_err: Optional[Exception] = None
    used = primary
    for voice in chain:
        used = voice

        async def _run(v: str = voice) -> None:
            communicate = edge_tts.Communicate(text, v)
            await communicate.save(str(mp3))

        try:
            asyncio.run(_run())
            if mp3.exists() and mp3.stat().st_size >= 200:
                break
            last_err = RuntimeError(f"edge-tts empty for {voice}")
        except Exception as exc:
            last_err = exc
            logger.warning("Edge-TTS voice %s failed: %s", voice, str(exc)[:120])
            continue
    else:
        raise RuntimeError(f"edge-tts produced empty audio: {last_err}")

    if not mp3.exists() or mp3.stat().st_size < 200:
        raise RuntimeError("edge-tts produced empty audio")

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(mp3),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(m4a),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        if m4a.exists() and m4a.stat().st_size > 200:
            logger.info("Edge-TTS OK voice=%s → %s", used, m4a.name)
            return m4a
    except Exception as exc:
        logger.warning("edge-tts ffmpeg remux failed: %s", exc)
    return mp3
