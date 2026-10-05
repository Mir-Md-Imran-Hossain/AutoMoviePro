"""Optional offline Piper TTS fallback (AMP-owned; not OpenMontage).

Chain: Google Gemini TTS → Edge-TTS → Piper (if installed).
Missing Piper binary/model → explicit UNAVAILABLE (never silent PASS).
Does not replace AudioPlan / VoiceIdentity authorities.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.compose import ffmpeg_bin
from pipeline.lang_config import SOURCE_LANG

logger = logging.getLogger(__name__)

PROVIDER = "piper"


def piper_tool_available() -> Dict[str, Any]:
    """Probe Piper CLI or python package without claiming voice quality PASS."""
    exe = shutil.which("piper") or shutil.which("piper.exe")
    env_bin = (os.environ.get("AMP_PIPER_BIN") or "").strip()
    if env_bin and Path(env_bin).is_file():
        exe = env_bin
    model = (os.environ.get("AMP_PIPER_MODEL") or "").strip()
    try:
        import piper  # noqa: F401

        py_ok = True
    except Exception:
        py_ok = False
    available = bool(exe) or py_ok
    return {
        "available": available,
        "provider": PROVIDER,
        "binary": exe or "",
        "model_path": model,
        "python_package": py_ok,
        "status": "OK" if available else "UNAVAILABLE",
        "unknown_as_pass": False,
        "note": "optional_offline_tts_slot",
    }


def synthesize_piper_tts(
    text: str,
    out_path: Path,
    *,
    language_hint: str = SOURCE_LANG,
    voice_name: str = "",
    model_path: str = "",
) -> Path:
    """Synthesize via Piper when installed; raise with UNAVAILABLE otherwise."""
    text = (text or "").strip()
    if not text:
        raise RuntimeError("empty text for piper")
    avail = piper_tool_available()
    if not avail.get("available"):
        raise RuntimeError("piper_UNAVAILABLE:binary_or_package_missing")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wav = out_path.with_suffix(".wav")
    m4a = out_path.with_suffix(".m4a")
    model = (model_path or avail.get("model_path") or "").strip()
    exe = str(avail.get("binary") or "")

    if exe and model and Path(model).is_file():
        # Official Piper CLI: echo text | piper --model MODEL --output_file WAV
        proc = subprocess.run(
            [exe, "--model", model, "--output_file", str(wav)],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0 or not wav.is_file() or wav.stat().st_size < 200:
            raise RuntimeError(
                f"piper_cli_failed:{(proc.stderr or b'')[-200:].decode('utf-8', errors='ignore')}"
            )
    else:
        # Python package path (best-effort); still requires a configured voice model
        try:
            from piper import PiperVoice  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "piper_UNAVAILABLE:install_piper_cli_or_set_AMP_PIPER_MODEL"
            ) from exc
        if not model or not Path(model).is_file():
            raise RuntimeError("piper_UNAVAILABLE:AMP_PIPER_MODEL_not_set")
        voice = PiperVoice.load(model)
        with open(wav, "wb") as f:
            voice.synthesize(text, f)
        if not wav.is_file() or wav.stat().st_size < 200:
            raise RuntimeError("piper_python_empty_output")

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(wav),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(m4a),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not m4a.is_file():
        raise RuntimeError(f"piper_ffmpeg_mux_failed:{(r.stderr or '')[-200:]}")
    logger.info(
        "Piper TTS OK lang=%s voice_hint=%s out=%s",
        language_hint,
        voice_name or "default",
        m4a.name,
    )
    return m4a
