"""
Reuse previously generated TTS artifacts; only synthesize when missing/stale.

Policy (user): free TTS APIs — never regenerate just to wait/retry if a good
file already exists for the same text.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)


def _text_fingerprint(text: str) -> str:
    return hashlib.sha1((text or "").strip().encode("utf-8")).hexdigest()[:16]


def _sidecar(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".txt")


def write_tts_sidecar(audio_path: Path, text: str, *, voice_name: str = "") -> None:
    try:
        from pipeline.lang_config import MASTER_VOICE_NAME

        voice = (voice_name or MASTER_VOICE_NAME).strip() or MASTER_VOICE_NAME
        _sidecar(audio_path).write_text(
            f"sha1={_text_fingerprint(text)}\nvoice={voice}\n{(text or '').strip()}\n",
            encoding="utf-8",
        )
    except Exception:
        pass


def tts_sidecar_voice(audio_path: Path) -> str:
    side = _sidecar(audio_path)
    if not side.exists():
        return ""
    try:
        for line in side.read_text(encoding="utf-8").splitlines():
            if line.startswith("voice="):
                return line.split("=", 1)[1].strip()
    except Exception:
        return ""
    return ""


def tts_matches_text(audio_path: Path, text: str, *, voice_name: str = "") -> bool:
    side = _sidecar(audio_path)
    if not side.exists():
        return False
    try:
        lines = side.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0].strip() != f"sha1={_text_fingerprint(text)}":
            return False
        if voice_name:
            got = tts_sidecar_voice(audio_path)
            if got.lower() != voice_name.strip().lower():
                return False
        return True
    except Exception:
        return False


def find_reusable_tts(
    dest: Path,
    text: str,
    *,
    extra_candidates: Optional[Sequence[Path]] = None,
    lang: str = "en",
    voice_name: str = "",
) -> Optional[Path]:
    """Return an existing audio file usable for this text+voice, else None."""
    dest = Path(dest)
    cands: List[Path] = []
    for p in (
        dest,
        dest.with_suffix(".m4a"),
        dest.with_suffix(".mp3"),
        dest.parent / f"{dest.stem}.m4a",
        dest.parent / f"{dest.stem}.mp3",
    ):
        if p not in cands:
            cands.append(p)
    for p in extra_candidates or []:
        if p and Path(p) not in cands:
            cands.append(Path(p))

    for p in cands:
        if not p.exists() or p.stat().st_size < 800:
            continue
        if tts_matches_text(p, text, voice_name=voice_name):
            logger.info("TTS reuse (fingerprint+voice): %s", p.name)
            return p
    return None


def reuse_or_synthesize_tts(
    text: str,
    dest: Path,
    *,
    language_hint: str = "en",
    google_api_keys: Optional[List[str]] = None,
    voice_name: str = "",
    extra_candidates: Optional[Sequence[Path]] = None,
    work_dir: Optional[Path] = None,
    job_id: str = "",
    scene_id: int = 0,
    dialogue_id: str = "",
    part_index: int = 0,
    segment_id: str = "",
) -> Path:
    """
    Reuse existing TTS if valid; otherwise synthesize (Edge-first when preferred).
    When work_dir is provided, routes through BUILD-04B idempotent runtime.
    """
    if work_dir is not None:
        from pipeline.idempotency.tts_bridge import idempotent_reuse_or_synthesize_tts

        return idempotent_reuse_or_synthesize_tts(
            text,
            dest,
            work_dir=Path(work_dir),
            job_id=job_id or Path(work_dir).name,
            scene_id=scene_id,
            language_hint=language_hint,
            google_api_keys=google_api_keys,
            voice_name=voice_name,
            dialogue_id=dialogue_id,
            part_index=part_index,
            segment_id=segment_id,
            extra_candidates=extra_candidates,
        )
    text = (text or "").strip()
    if not text:
        raise RuntimeError("empty text for TTS")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    from pipeline.lang_config import MASTER_VOICE_NAME, resolve_edge_voice, resolve_locked_voice

    gemini_voice = resolve_locked_voice(voice_name, language_hint=language_hint)
    edge_voice = resolve_edge_voice(voice_name, language_hint=language_hint)
    hit = find_reusable_tts(
        dest,
        text,
        extra_candidates=extra_candidates,
        lang=language_hint,
        voice_name=gemini_voice,
    )
    if hit is None:
        hit = find_reusable_tts(
            dest,
            text,
            extra_candidates=extra_candidates,
            lang=language_hint,
            voice_name=edge_voice,
        )
    if hit is not None:
        if hit.resolve() != dest.with_suffix(hit.suffix).resolve():
            import shutil

            target = dest if dest.suffix else dest.with_suffix(hit.suffix)
            if target.suffix.lower() not in {".m4a", ".mp3", ".wav"}:
                target = dest.with_suffix(".m4a")
            shutil.copy2(hit, target)
            write_tts_sidecar(target, text)
            return target
        return hit

    prefer_edge = os.environ.get("AMP_PREFER_EDGE_TTS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    out: Optional[Path] = None
    used_voice = gemini_voice
    if prefer_edge or not google_api_keys:
        try:
            from pipeline.edge_tts_fallback import synthesize_edge_tts

            out = synthesize_edge_tts(
                text, dest, language_hint=language_hint, voice_name=edge_voice
            )
            used_voice = edge_voice
        except Exception as exc:
            logger.warning("Edge-TTS synth failed: %s", str(exc)[:140])
            out = None
    if out is None:
        from pipeline.tts_google import synthesize_narration

        out = synthesize_narration(
            text,
            dest.with_suffix("") if dest.suffix else dest,
            google_api_keys=list(google_api_keys or []),
            voice_name=gemini_voice,
            language_hint=language_hint,
        )
        used_voice = gemini_voice
    if out is None or not Path(out).exists():
        raise RuntimeError(f"TTS synthesize failed for lang={language_hint}")
    out_p = Path(out)
    write_tts_sidecar(out_p, text, voice_name=used_voice)
    logger.info("TTS synthesized fresh: %s voice=%s", out_p.name, used_voice)
    return out_p
