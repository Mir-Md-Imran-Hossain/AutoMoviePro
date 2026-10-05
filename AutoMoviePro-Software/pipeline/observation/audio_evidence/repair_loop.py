"""ASR mismatch → scoped audio repair → re-observe (PART-5G).

Does not invent a second ASR engine. UNKNOWN never triggers repair.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _mismatch_scene_indices(gate: dict[str, Any]) -> List[int]:
    idxs: set[int] = set()
    for row in gate.get("per_scene") or []:
        if not isinstance(row, dict):
            continue
        st = str(row.get("status") or row.get("align_status") or "").upper()
        if st in ("FAIL", "MISMATCH", "PARTIAL"):
            did = str(row.get("dialogue_id") or row.get("scene_id") or "")
            m = re.search(r"(\d+)", did)
            if m:
                idxs.add(int(m.group(1)))
    for issue in gate.get("issues") or []:
        m = re.search(r"narration[_-](\d+)|scene[_-](\d+)|dialogue[_-](\d+)", str(issue), re.I)
        if m:
            for g in m.groups():
                if g is not None:
                    idxs.add(int(g))
    return sorted(idxs)


def _delete_scene_audio(work_dir: Path, idx: int) -> None:
    for ext in (".m4a", ".wav", ".mp3", ".aac"):
        p = work_dir / f"narration_{idx:02d}{ext}"
        if p.is_file():
            try:
                p.unlink()
            except OSError as exc:
                logger.warning("could not remove %s: %s", p.name, exc)


def execute_asr_repair_and_reobserve(
    work_dir: Path,
    *,
    gate: dict[str, Any],
    scenes: Sequence[Any],
    google_keys: Sequence[str],
    run_asr_gate: Callable[..., dict[str, Any]],
    synthesize_scene: Callable[[int, str], Optional[Path]],
    max_attempts: int = 2,
    job_id: str = "",
    final_path: Optional[Path] = None,
    language_hint: str = "en",
    customer_id: str = "",
    channel_id: str = "",
) -> dict[str, Any]:
    """On FAIL: repair mismatched narration audio, then re-run ASR gate.

    Returns final gate dict. If still FAIL after attempts, status remains FAIL.
    """
    from pipeline.observation.audio_evidence.observe import repair_handoff_from_audio_evidence

    work_dir = Path(work_dir)
    current = dict(gate or {})
    attempts_log: list[dict[str, Any]] = []

    for attempt in range(1, max(1, int(max_attempts)) + 1):
        st = str(current.get("status") or "").upper()
        if st not in ("FAIL", "FAILED", "BLOCKED"):
            break

        handoff = repair_handoff_from_audio_evidence(
            subject_id=f"job-{job_id or work_dir.name}",
            audio_bridge=current,
            work_dir=work_dir,
        )
        idxs = _mismatch_scene_indices(current)
        if not idxs and isinstance(scenes, (list, tuple)):
            idxs = list(range(min(len(scenes), 8)))

        repaired: list[int] = []
        for idx in idxs:
            narr = ""
            if isinstance(scenes, (list, tuple)) and 0 <= idx < len(scenes):
                sc = scenes[idx]
                if isinstance(sc, dict):
                    narr = str(sc.get("narration") or sc.get("text") or sc.get("dialogue") or "")
            sidecar = work_dir / f"narration_{idx:02d}.txt"
            if not narr and sidecar.is_file():
                try:
                    narr = sidecar.read_text(encoding="utf-8")
                except Exception:
                    narr = ""
            if not narr.strip():
                continue
            _delete_scene_audio(work_dir, idx)
            try:
                out = synthesize_scene(idx, narr)
                if out is not None:
                    repaired.append(idx)
            except Exception as exc:
                logger.warning("ASR audio repair synth failed scene %s: %s", idx, exc)

        attempts_log.append(
            {
                "attempt": attempt,
                "handoff": handoff,
                "mismatch_scenes": idxs,
                "repaired_scenes": repaired,
                "prior_status": st,
            }
        )
        if not repaired:
            current["repair_loop"] = {
                "attempts": attempts_log,
                "note": "no_scenes_repaired",
                "whole_video_regeneration": False,
            }
            break

        current = run_asr_gate(
            work_dir,
            job_id=job_id or work_dir.name,
            final_path=final_path,
            scenes=scenes,
            language_hint=language_hint,
            customer_id=customer_id,
            channel_id=channel_id,
        )
        current["repair_loop"] = {
            "attempts": attempts_log,
            "reobserve_after_repair": True,
            "whole_video_regeneration": False,
            "final_status": current.get("status"),
        }

    return current
