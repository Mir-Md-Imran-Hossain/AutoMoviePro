"""Production ASR / audio-evidence gate (Phase 6H → live generate_video).

Runs faster-whisper observation on narration / final audio.
Does NOT replace AudioPlan, VoiceIdentity, or subtitle planning authorities.
UNKNOWN ≠ PASS. FAIL (transcript mismatch when ASR worked) blocks publish.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, List, Optional, Sequence

logger = logging.getLogger(__name__)

GATE_NAME = "AUDIO_ASR_EVIDENCE_GATE.json"
EVIDENCE_NAME = "AUDIO_ASR_EVIDENCE.json"


def _clean_narration_text(raw: str) -> str:
    lines = []
    for ln in str(raw or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.lower().startswith("voice=") or s.lower().startswith("lang="):
            continue
        lines.append(s)
    return " ".join(lines).strip()


def _dialogue_segments_from_work(work_dir: Path, scenes: Optional[Sequence[Any]] = None) -> List[dict]:
    """Prefer narration_NN.txt + matching wav/m4a (actual spoken) over plan scenes."""
    segs: List[dict] = []
    work_dir = Path(work_dir)
    for p in sorted(work_dir.glob("narration_*.txt")):
        if not re.fullmatch(r"narration_\d+\.txt", p.name):
            continue
        try:
            text = _clean_narration_text(p.read_text(encoding="utf-8"))
        except Exception:
            text = ""
        if not text:
            continue
        idx = "".join(ch for ch in p.stem if ch.isdigit()) or "0"
        audio_cand = ""
        for ext in (".wav", ".m4a", ".mp3"):
            ap = work_dir / f"narration_{idx}{ext}"
            if ap.is_file() and ap.stat().st_size > 64:
                audio_cand = str(ap)
                break
        segs.append(
            {
                "dialogue_id": f"narration-{idx}",
                "scene_id": f"scene-{idx}",
                "text": text,
                "start_sec": 0.0,
                "end_sec": 0.0,
                "audio_path": audio_cand,
            }
        )
    if segs:
        return segs
    if scenes:
        for i, sc in enumerate(scenes):
            if not isinstance(sc, dict):
                continue
            did = str(sc.get("dialogue_id") or sc.get("c05s_dialogue_id") or f"beat-{i}")
            text = _clean_narration_text(
                str(sc.get("narration") or sc.get("text") or sc.get("dialogue") or "")
            )
            if not text:
                continue
            segs.append(
                {
                    "dialogue_id": did,
                    "scene_id": str(sc.get("scene_id") or sc.get("c05s_scene_id") or f"scene-{i}"),
                    "text": text,
                    "start_sec": float(sc.get("start_sec") or 0.0),
                    "end_sec": float(sc.get("end_sec") or sc.get("duration_sec") or 0.0),
                    "emotion": str(sc.get("emotion") or ""),
                    "audio_path": "",
                }
            )
    return segs


def _pick_audio(work_dir: Path, final_path: Optional[Path]) -> Optional[Path]:
    work_dir = Path(work_dir)
    candidates: List[Path] = []
    if final_path and Path(final_path).is_file():
        candidates.append(Path(final_path))
    for name in (
        "final_short.mp4",
        "body_av.mp4",
        "branded_av.mp4",
        "master.mp4",
        "final.mp4",
        "narration_en_tts.m4a",
        "narration_00.m4a",
        "narration_00.wav",
    ):
        p = work_dir / name
        if p.is_file() and p.stat().st_size > 64:
            candidates.append(p)
    for p in candidates:
        if p.suffix.lower() in {".m4a", ".wav", ".mp3", ".aac"}:
            return p
    return candidates[0] if candidates else None


def run_production_audio_asr_gate(
    work_dir: Path,
    *,
    job_id: str = "",
    final_path: Optional[Path] = None,
    scenes: Optional[Sequence[Any]] = None,
    language_hint: str = "en",
    customer_id: str = "",
    channel_id: str = "",
) -> dict[str, Any]:
    """Observe narration audio with faster-whisper; persist evidence + gate."""
    work_dir = Path(work_dir)
    job = job_id or work_dir.name
    dialogue = _dialogue_segments_from_work(work_dir, scenes)

    gate: dict[str, Any] = {
        "schema": "amp_audio_asr_evidence_gate_v1",
        "job_id": job,
        "status": "UNKNOWN",
        "asr_provider": "faster-whisper",
        "asr_authority": "pipeline.observation.speech_timing.observe_speech_timing",
        "audio_path": "",
        "dialogue_count": len(dialogue),
        "issues": [],
        "unknown_as_pass": False,
        "unknown_as_fail": False,
        "second_asr_engine": False,
        "multilingual_hint": str(language_hint or "en"),
        "multilingual_asr_status": (
            "PARTIAL" if str(language_hint or "").lower()[:2] != "en" else "EN_PRIMARY"
        ),
        "publishability_note": "ASR UNKNOWN never certifies dialogue coverage PASS",
        "per_scene": [],
        "has_timestamps": False,
        "transcript_preview": "",
    }

    try:
        from pipeline.observation.audio_evidence.observe import (
            MATCH,
            MISMATCH,
            PARTIAL,
            align_transcript_texts,
            observe_audio_production,
        )
        from pipeline.observation.speech_timing.observe import (
            observe_speech_timing,
            speech_tool_available,
        )

        avail = speech_tool_available()
        gate["tool_available"] = bool(avail.get("available"))
        if not avail.get("available"):
            gate["issues"].append("faster_whisper_not_installed")
            gate["status"] = "UNKNOWN"
            gate["tool_error"] = str(avail.get("error") or "")[:200]
            _persist(work_dir, gate, {"speech_tool": avail})
            return gate

        per_scene_audio = [
            d for d in dialogue if d.get("audio_path") and Path(str(d["audio_path"])).is_file()
        ]
        evidence: dict[str, Any] = {"mode": "", "scenes": []}

        if per_scene_audio:
            gate["audio_path"] = "per_scene_narration_*"
            evidence["mode"] = "per_scene"
            statuses: List[str] = []
            previews: List[str] = []
            any_ts = False
            for d in per_scene_audio:
                raw = observe_speech_timing(
                    d["audio_path"], language_hint=str(language_hint or "en")
                )
                transcript = str(raw.get("transcript") or "")
                conf = bool(transcript.strip()) and str(raw.get("status") or "").upper() in (
                    "PASS",
                    "OK",
                    "",
                )
                # Accept provider_verified or non-empty transcript as confidence
                if raw.get("provider_verified") or transcript.strip():
                    conf = True
                al = align_transcript_texts(
                    str(d.get("text") or ""),
                    transcript,
                    confidence_ok=conf,
                )
                row = {
                    "dialogue_id": d["dialogue_id"],
                    "audio_path": d["audio_path"],
                    "alignment": al,
                    "transcript": transcript[:240],
                    "has_timestamps": bool(raw.get("words") or raw.get("segments")),
                    "asr_status": str(raw.get("status") or "UNKNOWN"),
                }
                evidence["scenes"].append(row)
                gate["per_scene"].append(
                    {
                        "dialogue_id": d["dialogue_id"],
                        "class": al.get("class"),
                        "asr_status": row["asr_status"],
                    }
                )
                statuses.append(str(al.get("class") or "UNKNOWN"))
                if transcript:
                    previews.append(transcript)
                any_ts = any_ts or row["has_timestamps"]
                if not transcript.strip():
                    gate["issues"].append(f"asr_empty:{d['dialogue_id']}")

            gate["has_timestamps"] = any_ts
            gate["transcript_preview"] = " | ".join(previews)[:240]
            if any(s == MISMATCH for s in statuses):
                gate["status"] = "FAIL"
                gate["issues"].append("transcript_mismatch:per_scene")
            elif statuses and all(s in (MATCH, PARTIAL) for s in statuses):
                gate["status"] = "PASS"
                gate["speech_provider_verified"] = True
            else:
                gate["status"] = "UNKNOWN"
                gate["issues"].append("asr_alignment_unknown_or_mixed")
            _persist(work_dir, gate, evidence)
            return gate

        audio = _pick_audio(work_dir, Path(final_path) if final_path else None)
        gate["audio_path"] = str(audio) if audio else ""
        if audio is None:
            gate["issues"].append("no_audio_for_asr")
            gate["status"] = "UNKNOWN"
            _persist(work_dir, gate, {})
            return gate
        if not dialogue:
            dialogue = [
                {
                    "dialogue_id": "master",
                    "scene_id": "master",
                    "text": "",
                    "start_sec": 0.0,
                    "end_sec": 0.0,
                }
            ]
        evidence = observe_audio_production(
            audio_path=audio,
            dialogue_segments=dialogue,
            language_hint=str(language_hint or "en"),
            job_id=job,
            scene_id="master",
            customer_id=customer_id,
            channel_id=str(channel_id or ""),
            audio_asset_id=audio.name,
            materialized_dialogue_ids=[d["dialogue_id"] for d in dialogue if d.get("text")],
        )
        st = str(evidence.get("status") or "UNKNOWN").upper()
        gate["status"] = st if st in ("PASS", "FAIL", "UNKNOWN") else "UNKNOWN"
        gate["issues"] = list(evidence.get("issues") or [])
        gate["speech_provider_verified"] = bool(
            (evidence.get("speech") or {}).get("provider_verified")
        )
        gate["transcript_preview"] = str(
            (evidence.get("speech") or {}).get("transcript") or ""
        )[:240]
        gate["has_timestamps"] = bool(
            (evidence.get("speech") or {}).get("words")
            or (evidence.get("speech") or {}).get("segments")
        )
        _persist(work_dir, gate, evidence)
        return gate
    except Exception as exc:
        logger.warning("Audio ASR production gate error: %s", exc)
        gate["issues"].append(f"asr_gate_exception:{str(exc)[:180]}")
        gate["status"] = "UNKNOWN"
        _persist(work_dir, gate, {"error": str(exc)[:300]})
        return gate


def _persist(work_dir: Path, gate: dict[str, Any], evidence: dict[str, Any]) -> None:
    work_dir = Path(work_dir)
    (work_dir / GATE_NAME).write_text(
        json.dumps(gate, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (work_dir / EVIDENCE_NAME).write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


def load_audio_asr_gate_status(work_dir: Path) -> str:
    p = Path(work_dir) / GATE_NAME
    if not p.is_file():
        return "ABSENT"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return str(data.get("status") or "ABSENT").strip().upper() or "ABSENT"
    except Exception:
        return "UNKNOWN"
