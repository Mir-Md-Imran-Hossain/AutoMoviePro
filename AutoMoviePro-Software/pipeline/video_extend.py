"""
AV length fit without freezing the picture.

User policy (Chernobyl / localization):
  - Match audio↔video by mildly SLOWING (setpts > 1) or SPEEDING (setpts < 1)
    the picture so motion continues.
  - If the gap is too large for mild setpts, retune AUDIO with pitch-preserving
    atempo instead of hard-freezing frames.
  - Never stream_loop. Never tpad-clone for length matching.
  - Agnes often fades to BLACK at the end — trim that black first, then setpts
    on the remaining content (cloning black OR freezing last frame looks broken).

The old ~1s post-dialogue "hold" is silence on the AUDIO timeline while the
picture keeps moving (covered by setpts), not a frozen still.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pipeline.compose import ffmpeg_bin, ffprobe_duration

logger = logging.getLogger(__name__)

# Trailing black longer than this ⇒ fail gate / must trim before fit.
BLACK_TAIL_FAIL_SEC = 0.35
BLACKDETECT_MIN_DUR = 0.12
BLACKDETECT_PIX_TH = 0.12
BLACKDETECT_PIC_TH = 0.90

# Mild visual retiming band (same as localization).
MAX_VISUAL_STRETCH = 1.18  # slow video up to +18%
MIN_VISUAL_STRETCH = 0.85  # speed video down to -15%

# End freeze (identical frames) longer than this ⇒ fail (wrong repair path).
END_FREEZE_FAIL_SEC = 0.85


def _ffprobe_bin() -> str:
    ff = Path(ffmpeg_bin())
    name = "ffprobe.exe" if ff.suffix.lower() == ".exe" else "ffprobe"
    cand = ff.with_name(name)
    return str(cand if cand.exists() else "ffprobe")


def _atempo_filter(rate: float) -> str:
    rate = max(0.5, min(2.0, float(rate)))
    parts: List[str] = []
    r = rate
    while r > 2.0 + 1e-6:
        parts.append("atempo=2.0")
        r /= 2.0
    while r < 0.5 - 1e-6:
        parts.append("atempo=0.5")
        r /= 0.5
    parts.append(f"atempo={r:.5f}")
    return ",".join(parts)


def list_black_segments(media: Path) -> List[Dict[str, float]]:
    """Parse ffmpeg blackdetect segments: [{start, end, duration}, ...]."""
    media = Path(media)
    if not media.exists():
        return []
    vf = (
        f"blackdetect=d={BLACKDETECT_MIN_DUR}:pix_th={BLACKDETECT_PIX_TH}"
        f":pic_th={BLACKDETECT_PIC_TH}"
    )
    cmd = [
        ffmpeg_bin(),
        "-hide_banner",
        "-i",
        str(media),
        "-vf",
        vf,
        "-an",
        "-f",
        "null",
        "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    text = (r.stderr or "") + "\n" + (r.stdout or "")
    segs: List[Dict[str, float]] = []
    for m in re.finditer(
        r"black_start:\s*([0-9.]+)\s*black_end:\s*([0-9.]+)\s*black_duration:\s*([0-9.]+)",
        text,
    ):
        segs.append(
            {
                "start": float(m.group(1)),
                "end": float(m.group(2)),
                "duration": float(m.group(3)),
            }
        )
    return segs


def trailing_black_info(media: Path) -> Dict[str, Any]:
    """Describe black at the end of the clip; content_end_sec = last real picture."""
    media = Path(media)
    dur = max(0.1, ffprobe_duration(media))
    info: Dict[str, Any] = {
        "media": str(media),
        "duration_sec": round(dur, 3),
        "has_trailing_black": False,
        "black_start_sec": None,
        "black_duration_sec": 0.0,
        "content_end_sec": round(dur, 3),
    }
    segs = list_black_segments(media)
    info["segments"] = segs
    if not segs:
        return info
    tail = None
    for s in segs:
        if s["end"] + 0.12 >= dur or s["end"] >= dur - 0.05:
            tail = s
    if tail is None:
        last = max(segs, key=lambda s: s["end"])
        if last["end"] + 0.35 >= dur:
            tail = last
    if not tail:
        return info
    info["has_trailing_black"] = True
    info["black_start_sec"] = round(float(tail["start"]), 3)
    info["black_duration_sec"] = round(float(tail["duration"]), 3)
    # Back up before fade so setpts source still has visible picture
    content_end = max(0.2, float(tail["start"]) - 0.35)
    info["content_end_sec"] = round(min(content_end, dur), 3)
    return info


def detect_black_tail(
    media: Path,
    *,
    max_black_sec: float = BLACK_TAIL_FAIL_SEC,
) -> Dict[str, Any]:
    """Gate: fail when the clip ends on an extended black screen."""
    media = Path(media)
    result: Dict[str, Any] = {
        "check": "black_tail",
        "passed": True,
        "issues": [],
        "critical_issues": [],
        "media": str(media),
        "max_black_sec": max_black_sec,
    }
    if not media.exists():
        result["passed"] = False
        result["critical_issues"].append("missing_media")
        return result
    try:
        info = trailing_black_info(media)
    except Exception as exc:
        result["issues"].append(f"black_tail_probe_failed:{exc}")
        return result
    result.update({k: info[k] for k in info if k != "segments"})
    result["segments"] = info.get("segments") or []
    black_dur = float(info.get("black_duration_sec") or 0.0)
    if info.get("has_trailing_black") and black_dur >= float(max_black_sec):
        result["passed"] = False
        result["issues"].append(
            f"black_tail:{black_dur:.2f}s_black_at_end "
            f"(from {info.get('black_start_sec')}s)"
        )
        result["critical_issues"].append("black_tail_freeze")
    return result


def detect_end_freeze(
    media: Path,
    *,
    max_freeze_sec: float = END_FREEZE_FAIL_SEC,
) -> Dict[str, Any]:
    """
    Gate: fail when the picture hard-freezes at the end (tpad clone / still).
    Motion should continue via setpts; a long identical-frame tail is wrong.
    """
    media = Path(media)
    result: Dict[str, Any] = {
        "check": "end_freeze",
        "passed": True,
        "issues": [],
        "critical_issues": [],
        "media": str(media),
        "max_freeze_sec": max_freeze_sec,
    }
    if not media.exists():
        result["passed"] = False
        result["critical_issues"].append("missing_media")
        return result
    dur = max(0.1, ffprobe_duration(media))
    # Probe last ~2.5s for freeze
    ss = max(0.0, dur - 2.5)
    cmd = [
        ffmpeg_bin(),
        "-hide_banner",
        "-ss",
        f"{ss:.3f}",
        "-i",
        str(media),
        "-vf",
        "freezedetect=n=0.004:d=0.40",
        "-an",
        "-f",
        "null",
        "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    text = (r.stderr or "") + "\n" + (r.stdout or "")
    freezes: List[Tuple[float, float, float]] = []
    for m in re.finditer(
        r"freeze_start:\s*([0-9.]+).*?freeze_duration:\s*([0-9.]+).*?freeze_end:\s*([0-9.]+)",
        text,
        flags=re.S,
    ):
        freezes.append((float(m.group(1)), float(m.group(2)), float(m.group(3))))
    # freezedetect timestamps are relative to -ss input
    best = 0.0
    for _fs, fd, fe in freezes:
        # freeze that reaches near end of probed window
        if fe + 0.15 >= min(2.5, dur - ss) or fd >= max_freeze_sec:
            best = max(best, fd)
    result["freeze_sec"] = round(best, 3)
    result["duration_sec"] = round(dur, 3)
    if best >= float(max_freeze_sec):
        result["passed"] = False
        result["issues"].append(
            f"end_freeze:{best:.2f}s_static_tail — use setpts slow/fast, not frame hold"
        )
        result["critical_issues"].append("end_frame_freeze")
    return result


def trim_to_content_end(
    src: Path,
    dest: Path,
    *,
    content_end_sec: Optional[float] = None,
) -> Path:
    """Cut trailing black; keep audio/video through last content frame."""
    src = Path(src)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    info = trailing_black_info(src)
    end = float(content_end_sec) if content_end_sec is not None else float(info["content_end_sec"])
    dur = float(info["duration_sec"])
    if end <= 0.2 or end + 0.12 >= dur:
        if src.resolve() != dest.resolve():
            import shutil

            shutil.copy2(src, dest)
        return dest

    tmp = dest.with_suffix(".trim_black.tmp.mp4")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(src),
        "-t",
        f"{end:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 2000:
        logger.warning("trim_to_content_end failed: %s", (r.stderr or "")[-240:])
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
    logger.info("Trimmed trailing black: %.2fs → content_end=%.2fs (%s)", dur, end, dest.name)
    return dest


def _retime_audio(audio_src: Path, dest: Path, *, rate: float) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    af = _atempo_filter(rate)
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(audio_src),
        "-af",
        af,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        import shutil

        shutil.copy2(audio_src, dest)
    return dest


def fit_video_to_duration_setpts(
    src: Path,
    dest: Path,
    *,
    target_duration_sec: float,
    max_stretch: float = MAX_VISUAL_STRETCH,
    min_stretch: float = MIN_VISUAL_STRETCH,
    trim_black: bool = True,
) -> Dict[str, Any]:
    """
    Trim trailing black (optional), then setpts slow/fast so video length ≈ target.
    Returns meta including pts_factor and whether audio should be atempo'd by caller.
    """
    src = Path(src)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    work = dest.parent
    picture = src
    if trim_black:
        trimmed = work / f"{src.stem}_noblack_fit.tmp.mp4"
        trim_to_content_end(src, trimmed)
        picture = trimmed

    v_dur = max(0.2, ffprobe_duration(picture))
    target = max(0.5, float(target_duration_sec))
    raw_ratio = target / v_dur
    pts = max(float(min_stretch), min(float(max_stretch), raw_ratio))
    meta: Dict[str, Any] = {
        "v_dur": round(v_dur, 3),
        "target": round(target, 3),
        "raw_ratio": round(raw_ratio, 4),
        "pts_factor": round(pts, 4),
        "needs_audio_fit": abs(raw_ratio - pts) > 0.02,
        "audio_target_sec": round(v_dur * pts, 3),
    }

    tmp = dest.with_suffix(".setpts.tmp.mp4")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(picture),
        "-vf",
        f"setpts={pts:.6f}*PTS,fps=25,format=yuv420p",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-t",
        f"{(v_dur * pts) + 0.05:.3f}",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if picture != src:
        try:
            picture.unlink()
        except OSError:
            pass
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 2000:
        logger.warning("setpts fit failed: %s", (r.stderr or "")[-280:])
        if src.resolve() != dest.resolve():
            import shutil

            shutil.copy2(src, dest)
        meta["ok"] = False
        return meta
    import shutil

    shutil.move(str(tmp), str(dest))
    meta["ok"] = True
    meta["out_dur"] = round(ffprobe_duration(dest), 3)
    logger.info(
        "setpts fit pts=%.3f (raw=%.3f) %.2fs→~%.2fs %s",
        pts,
        raw_ratio,
        v_dur,
        meta.get("out_dur"),
        dest.name,
    )
    return meta


def mux_fit_av_setpts(
    *,
    video_src: Path,
    audio_src: Path,
    dest: Path,
    work: Path,
    stem: str,
    post_silence_sec: float = 1.0,
    max_stretch: float = MAX_VISUAL_STRETCH,
    min_stretch: float = MIN_VISUAL_STRETCH,
) -> Optional[Path]:
    """
    Canonical AV fit:
      1) trim Agnes black tail
      2) optional post-dialogue silence on audio (breathing room)
      3) setpts slow/fast video to match audio (motion continues)
      4) if gap > mild band → atempo audio toward picture (not freeze)
    """
    video_src = Path(video_src)
    audio_src = Path(audio_src)
    dest = Path(dest)
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    if not video_src.exists() or not audio_src.exists():
        return None

    # Post-dialogue silence on audio timeline (picture keeps moving via setpts)
    a_work = audio_src
    silence = max(0.0, float(post_silence_sec or 0.0))
    if silence >= 0.05:
        padded_a = work / f"{stem}_audio_apad.m4a"
        cmd_a = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(audio_src),
            "-af",
            f"apad=pad_dur={silence:.3f}",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(padded_a),
        ]
        r_a = subprocess.run(cmd_a, capture_output=True, text=True)
        if r_a.returncode == 0 and padded_a.exists():
            a_work = padded_a

    a_dur = max(0.5, ffprobe_duration(a_work))
    pic = work / f"{stem}_picture_setpts.mp4"
    meta = fit_video_to_duration_setpts(
        video_src,
        pic,
        target_duration_sec=a_dur,
        max_stretch=max_stretch,
        min_stretch=min_stretch,
        trim_black=True,
    )
    if not pic.exists():
        return None

    audio_for_mux = a_work
    if meta.get("needs_audio_fit"):
        # Retune audio to the mildly-stretched picture length (pitch-preserving)
        target_a = float(meta.get("audio_target_sec") or ffprobe_duration(pic))
        cur_a = max(0.2, ffprobe_duration(a_work))
        rate = cur_a / max(0.2, target_a)
        rate = max(0.82, min(1.22, rate))
        fitted_a = work / f"{stem}_audio_fit.m4a"
        _retime_audio(a_work, fitted_a, rate=rate)
        if fitted_a.exists():
            audio_for_mux = fitted_a
            logger.info(
                "atempo audio rate=%.3f to match setpts picture (no freeze)",
                rate,
            )

    tmp = work / f"{stem}_mux_setpts.tmp.mp4"
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(pic),
        "-i",
        str(audio_for_mux),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        logger.warning("mux_fit_av_setpts failed: %s", (r.stderr or "")[-240:])
        return None
    import shutil

    shutil.move(str(tmp), str(dest))
    return dest if dest.exists() else None


def repair_black_tail_with_setpts(
    src: Path,
    dest: Path,
    *,
    extra_silence_sec: float = 0.0,
) -> Path:
    """
    Replace trailing black by slowing the visible content (setpts) to cover the
    original timeline — continuous motion, not a frozen still.
    """
    src = Path(src)
    dest = Path(dest)
    info = trailing_black_info(src)
    dur = float(info["duration_sec"])
    extra = max(0.0, float(extra_silence_sec or 0.0))
    target = dur + extra
    if not info.get("has_trailing_black") and extra < 0.05:
        if src.resolve() != dest.resolve():
            import shutil

            shutil.copy2(src, dest)
        return dest

    # Extract audio to preserve dialogue, fit picture with setpts, remux
    work = dest.parent
    stem = f"{src.stem}_blksetpts"
    audio = work / f"{stem}_a.m4a"
    cmd = [
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
    subprocess.run(cmd, capture_output=True)
    if not audio.exists():
        # video-only: just setpts content to target
        fit_video_to_duration_setpts(src, dest, target_duration_sec=target, trim_black=True)
        return dest
    out = mux_fit_av_setpts(
        video_src=src,
        audio_src=audio,
        dest=dest,
        work=work,
        stem=stem,
        post_silence_sec=extra,
    )
    return out if out and out.exists() else dest


# --- Back-compat aliases (old freeze APIs now route to setpts) ---


def extend_hold_last_content_frame(
    src: Path,
    dest: Path,
    *,
    total_duration_sec: float,
    also_pad_audio_silence: bool = True,
) -> Path:
    """DEPRECATED name: now setpts-fits to total_duration (no frame freeze)."""
    meta = fit_video_to_duration_setpts(
        src, dest, target_duration_sec=total_duration_sec, trim_black=True
    )
    if also_pad_audio_silence and dest.exists():
        # If source had audio, retime file already video-only from fit; OK
        pass
    if not meta.get("ok") and src.resolve() != dest.resolve():
        import shutil

        shutil.copy2(src, dest)
    return dest


def replace_trailing_black_with_content_hold(
    src: Path,
    dest: Path,
    *,
    extra_hold_sec: float = 0.0,
) -> Path:
    """DEPRECATED name: black repair via setpts, not freeze hold."""
    return repair_black_tail_with_setpts(src, dest, extra_silence_sec=extra_hold_sec)


def prepare_picture_for_audio_mux(
    video_src: Path,
    *,
    audio_duration_sec: float,
    work: Path,
    stem: str,
    tail_hold_sec: float = 1.0,
) -> Path:
    """DEPRECATED name: setpts picture to audio+silence length."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    target_len = max(0.5, float(audio_duration_sec) + float(tail_hold_sec))
    out = work / f"{stem}_picture_ready.mp4"
    fit_video_to_duration_setpts(video_src, out, target_duration_sec=target_len, trim_black=True)
    return out
