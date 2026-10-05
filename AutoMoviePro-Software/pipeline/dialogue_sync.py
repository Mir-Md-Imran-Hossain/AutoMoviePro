"""
Dialogue↔Agnes duration sync helpers.
Agnes reliable AV (video+audio) cap is ~10s; split longer narration into ≤9s parts.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pipeline.compose import ffmpeg_bin, ffprobe_duration

logger = logging.getLogger(__name__)

# Agnes reliable window (video+native audio): 7–10s. Hard gen cap ~10s.
AGNES_MIN_SECONDS = 7.0
AGNES_TARGET_SECONDS = 8.5
AGNES_MAX_SECONDS = 10.0
# Per-part audio / Agnes beat: never request more than 9s of spoken content.
AGNES_AUDIO_CHUNK_MAX = 9.0
# Hold last frame + silence after dialogue so the final words aren't cut off.
# Keep under dead_air silencedetect min_gap (1.0s) so padded tails don't fail master ratio.
DIALOGUE_TAIL_PAD_SEC = 0.85
# English speech estimate (~2.4 words/sec documentary pace)
EN_WORDS_PER_SEC = 2.4


def pad_av_tail(
    src: Path,
    dest: Path,
    pad_sec: float = DIALOGUE_TAIL_PAD_SEC,
) -> Path:
    """
    After dialogue: add ~pad_sec silence on audio and mildly SLOW the picture
    (setpts) so motion continues through the breathing room.

    Never freezes the last frame for length matching. Trims Agnes black first.
    """
    pad = max(0.0, float(pad_sec or 0.0))
    if pad < 0.05:
        if src.resolve() != dest.resolve():
            import shutil

            shutil.copy2(src, dest)
        return dest
    if not src.exists():
        raise FileNotFoundError(f"pad_av_tail missing source: {src}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        from pipeline.video_extend import mux_fit_av_setpts, trailing_black_info

        work = dest.parent
        stem = f"{src.stem}_tailsetpts"
        audio = work / f"{stem}_a.m4a"
        cmd_a = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(src),
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(audio),
        ]
        r_a = subprocess.run(cmd_a, capture_output=True, text=True)
        if r_a.returncode != 0 or not audio.exists():
            raise RuntimeError("pad_av_tail audio extract failed")
        # If already has black, mux_fit trims + setpts; post_silence adds pad
        out = mux_fit_av_setpts(
            video_src=src,
            audio_src=audio,
            dest=dest,
            work=work,
            stem=stem,
            post_silence_sec=pad,
        )
        if out and out.exists():
            logger.info("pad_av_tail via setpts +%.2fs silence → %s", pad, dest.name)
            return dest
    except Exception as exc:
        logger.warning("pad_av_tail setpts path failed (%s); minimal apad only", exc)

    # Minimal fallback: apad audio only (do not tpad-freeze video)
    tmp = dest.with_suffix(".tailpad.tmp.mp4")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(src),
        "-af",
        f"apad=pad_dur={pad:.3f}",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 2000:
        logger.warning("pad_av_tail fallback failed: %s", (r.stderr or "")[-400:])
        if src.resolve() != dest.resolve():
            import shutil

            shutil.copy2(src, dest)
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return dest
    import shutil

    shutil.move(str(tmp), str(dest))
    return dest


def estimate_spoken_seconds(text: str, *, lang: str = "en") -> float:
    words = len(re.findall(r"\S+", text or ""))
    if lang.lower().startswith("en"):
        return max(1.0, words / EN_WORDS_PER_SEC)
    # denser scripts (bn/hi…) ~ slightly slower
    return max(1.0, words / 2.0)


def plan_agnes_segments(
    narration: str,
    audio_duration: float,
    *,
    agnes_max: float = AGNES_AUDIO_CHUNK_MAX,
) -> List[Dict[str, object]]:
    """
    Prefer ONE 7–10s Agnes clip (spoken ≤9s). Split when duration exceeds chunk max.
    """
    chunk_max = float(agnes_max or AGNES_AUDIO_CHUNK_MAX)
    chunk_max = min(chunk_max, AGNES_MAX_SECONDS)
    audio_duration = max(1.0, float(audio_duration or 0) or AGNES_TARGET_SECONDS)
    if audio_duration <= chunk_max + 0.35:
        return [
            {
                "part_index": 0,
                "narration_part": narration,
                "duration_hint": min(
                    max(audio_duration, AGNES_MIN_SECONDS), chunk_max
                ),
                "need_split": False,
            }
        ]

    n = int((audio_duration + chunk_max - 0.01) // chunk_max) + 1
    # Hard cap 2 parts — 3+ Agnes creates blows scene budget and triggers false hard-fails
    n = max(2, min(2, n))
    parts = split_bangla_narration(narration, max_parts=n)
    if not parts:
        # Empty/unparsed narration + long audio must still produce ≥1 beat.
        blob = (narration or "").strip() or " "
        words = blob.split()
        if len(words) >= n:
            size = max(1, len(words) // n)
            parts = [" ".join(words[i * size : (i + 1) * size]) for i in range(n - 1)]
            parts.append(" ".join(words[(n - 1) * size :]))
            parts = [p.strip() for p in parts if p.strip()]
        if not parts:
            return [
                {
                    "part_index": 0,
                    "narration_part": blob,
                    "duration_hint": min(max(audio_duration, AGNES_MIN_SECONDS), chunk_max),
                    "need_split": audio_duration > chunk_max + 0.35,
                }
            ]
    while len(parts) < n and len(parts) >= 1:
        last = parts.pop()
        mid = max(1, len(last) // 2)
        sp = last.rfind(" ", 0, mid + 15)
        if sp < 5:
            sp = mid
        parts.extend([last[:sp].strip(), last[sp:].strip()])
    while len(parts) > n:
        parts[-2] = f"{parts[-2]} {parts[-1]}"
        parts.pop()

    weights = [max(1, len(p)) for p in parts]
    wsum = float(sum(weights))
    segs = []
    for i, p in enumerate(parts):
        hint = max(AGNES_MIN_SECONDS, min(chunk_max, audio_duration * (weights[i] / wsum)))
        if hint < AGNES_MIN_SECONDS:
            hint = AGNES_MIN_SECONDS
        # Never request more than audio-chunk max for a single Agnes beat
        hint = min(hint, chunk_max)
        segs.append(
            {
                "part_index": i,
                "narration_part": p,
                "duration_hint": hint,
                "need_split": True,
            }
        )
    return segs


def split_bangla_narration(text: str, *, max_parts: int = 4) -> List[str]:
    """
    Split narration into roughly equal dialogue parts on sentence boundaries.
    Works for English masters and later localized Bangla/Indic scripts.
    Prefer 2 parts when text is long; up to max_parts for very long beats.
    """
    text = (text or "").strip()
    if not text:
        return []
    # Split on Bangla/English sentence enders and dashes used as beats
    chunks = re.split(r"(?<=[।!?\.\!\?])\s+", text)
    chunks = [c.strip() for c in chunks if c.strip()]
    if len(chunks) <= 1:
        # hard split by commas / mid-length
        mid = max(1, len(text) // 2)
        # prefer space near mid
        sp = text.rfind(" ", 0, mid + 20)
        if sp < 8:
            sp = mid
        return [text[:sp].strip(), text[sp:].strip()] if len(text) > 40 else [text]

    # Merge into target_parts buckets
    # Estimate need: assume ~2.2 chars/sec Bangla spoken ≈ rough; better decided by caller via audio dur
    target = min(max_parts, max(2, len(chunks)))
    if len(chunks) <= target:
        return chunks

    # greedy pack into `target` groups of similar char length
    total = sum(len(c) for c in chunks)
    goal = total / target
    parts: List[str] = []
    buf = ""
    for c in chunks:
        if not buf:
            buf = c
            continue
        if len(buf) + 1 + len(c) <= goal * 1.25 or len(parts) >= target - 1:
            buf = f"{buf} {c}"
        else:
            parts.append(buf)
            buf = c
    if buf:
        parts.append(buf)
    return [p for p in parts if p][:max_parts]


split_master_narration = split_bangla_narration


def split_audio_file(
    audio_path: Path,
    dest_dir: Path,
    *,
    n_parts: int = 0,
    prefix: str = "part",
    max_chunk_sec: float = AGNES_AUDIO_CHUNK_MAX,
) -> List[Path]:
    """
    Split an audio file into parts.
    If n_parts <= 0, auto-split so each chunk is ≤ max_chunk_sec (~9s).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dur = max(0.5, ffprobe_duration(audio_path))
    chunk = max(1.0, float(max_chunk_sec or AGNES_AUDIO_CHUNK_MAX))
    if int(n_parts) <= 0:
        if dur <= chunk + 0.35:
            n_parts = 1
        else:
            n_parts = max(2, int((dur + chunk - 0.01) // chunk) + 1)
    n_parts = max(1, int(n_parts))
    if n_parts == 1:
        out = dest_dir / f"{prefix}_0{audio_path.suffix}"
        if not out.exists():
            import shutil

            shutil.copy2(audio_path, out)
        return [out]

    slice_len = dur / n_parts
    # Keep each slice at or under max_chunk_sec when possible
    if slice_len > chunk + 0.05:
        n_parts = max(n_parts, int((dur + chunk - 0.01) // chunk) + 1)
        slice_len = dur / n_parts
    outs: List[Path] = []
    for i in range(n_parts):
        start = i * slice_len
        length = slice_len if i < n_parts - 1 else max(0.2, dur - start)
        length = min(length, chunk + 0.05)
        out = dest_dir / f"{prefix}_{i}{audio_path.suffix or '.m4a'}"
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(audio_path),
            "-t",
            f"{length:.3f}",
            "-c",
            "copy",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not out.exists() or out.stat().st_size < 500:
            # re-encode fallback
            cmd = [
                ffmpeg_bin(),
                "-y",
                "-ss",
                f"{start:.3f}",
                "-i",
                str(audio_path),
                "-t",
                f"{length:.3f}",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(out.with_suffix(".m4a")),
            ]
            subprocess.run(cmd, capture_output=True)
            out = out.with_suffix(".m4a")
        outs.append(out)
        logger.info(
            "Audio split %s/%s start=%.2f len=%.2f → %s",
            i + 1,
            n_parts,
            start,
            length,
            out.name,
        )
    return outs


def duration_mismatch_issue(
    audio_dur: float,
    video_src_dur: float,
    *,
    agnes_max: float = AGNES_MAX_SECONDS,
) -> Optional[str]:
    """
    Return a critical issue string if Agnes source is far shorter than narration
    and would require unnatural looping.
    """
    if audio_dur <= 0 or video_src_dur <= 0:
        return None
    if audio_dur <= agnes_max + 0.5:
        # single-shot expected; allow small slack
        if video_src_dur + 1.5 < audio_dur:
            return (
                f"duration_mismatch: audio={audio_dur:.1f}s but Agnes source="
                f"{video_src_dur:.1f}s (should split or request longer Agnes)"
            )
        return None
    # long narration must have been split; a single short source is wrong
    if video_src_dur + 2.0 < min(audio_dur, agnes_max):
        return (
            f"duration_mismatch: long narration {audio_dur:.1f}s vs short Agnes "
            f"{video_src_dur:.1f}s — must split dialogue into multiple clips"
        )
    return None
