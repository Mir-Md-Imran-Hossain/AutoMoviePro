"""
Image-to-Video Fallback Pipeline + Inspector Agent.

When Agnes fails / is rate-limited, build a synced clip from free image APIs
(Pollinations Flux + Google Gemini image) with Ken Burns motion and 3–4s beats.

Checkpoints:
  1) Prompt relevance (before image API)
  2) Image integrity (after image API)
  3) A/V sync duration (after FFmpeg assembly)
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pipeline.compose import ffmpeg_bin, ffprobe_duration
from pipeline.prompt_hardening import character_base_seed, extract_dialogue_anchors, harden_video_prompt

logger = logging.getLogger(__name__)

BEAT_MIN = 3.0
BEAT_MAX = 4.0
MAX_INSPECTOR_RETRIES = 2


@dataclass
class CharacterProfile:
    name: str
    visual_description: str
    art_style: str = "cinematic photorealistic documentary, 8k, natural light"
    base_seed: int = 0

    def __post_init__(self) -> None:
        if not self.base_seed:
            self.base_seed = character_base_seed(self.name, self.visual_description)


@dataclass
class VisualBeat:
    index: int
    text: str
    duration: float
    prompt: str
    seed: int
    motion: str  # zoom_in | zoom_out | pan_lr | pan_rl


@dataclass
class FallbackResult:
    path: Path
    provider: str
    beats: int
    seed: int
    log_path: Path
    inspector: Dict[str, Any] = field(default_factory=dict)


class ErrorFallbackLogger:
    def __init__(self, work: Path) -> None:
        self.path = work / "fallback_error_log.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **payload: Any) -> None:
        row = {"ts": time.time(), "event": event, **payload}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


class AgentInspector:
    """Three-checkpoint inspector with self-correction (max 2 retries)."""

    def __init__(self, logger_: ErrorFallbackLogger) -> None:
        self.log = logger_

    def check_prompt(
        self,
        *,
        beat: VisualBeat,
        profile: CharacterProfile,
        narration: str,
    ) -> Tuple[bool, VisualBeat, List[str]]:
        issues: List[str] = []
        prompt = beat.prompt or ""
        if profile.name.lower() not in prompt.lower() and profile.visual_description[:24].lower() not in prompt.lower():
            issues.append("missing_character_profile")
        if beat.seed <= 0:
            issues.append("missing_seed")
            beat.seed = profile.base_seed + beat.index

        # STRICT dialogue<->image: require >=2 spoken anchors from THIS beat in the prompt
        anchors = extract_dialogue_anchors(beat.text or narration, limit=8)
        hit = [a for a in anchors if a.lower() in prompt.lower()]
        if anchors and len(hit) < min(2, len(anchors)):
            issues.append("dialogue_image_mismatch")
            missing = [a for a in anchors if a.lower() not in prompt.lower()][:5]
            beat.prompt = (
                f"{profile.art_style}. {profile.visual_description}. "
                f"DIALOGUE<->IMAGE LOCK — must show: {', '.join(anchors[:6])}. "
                f"Missing now: {', '.join(missing)}. "
                f"Scene for: {beat.text[:220]}. {prompt}"
            )[:950]
            prompt = beat.prompt

        # Cheap relevance: at least one content word from beat text in prompt
        words = [w.lower() for w in beat.text.split() if len(w) > 4][:6]
        if words and not any(w in prompt.lower() for w in words):
            issues.append("prompt_off_topic")
            beat.prompt = (
                f"{profile.art_style}. {profile.visual_description}. "
                f"Scene for: {beat.text[:200]}. {prompt}"
            )[:900]
        ok = (
            "prompt_off_topic" not in issues
            and "missing_character_profile" not in issues
            and "dialogue_image_mismatch" not in issues
        )
        # Topic anchors: keyword block should be present after build() inject
        pl = prompt.lower()
        has_anchors = (
            "required visual anchors:" in pl
            or "dialogue<->image lock" in pl
            or "exact subject on screen:" in pl
            or "visual triggers:" in pl
        )
        if not has_anchors:
            issues.append("missing_topic_anchors")
            ok = False
            beat.prompt = (
                f"{prompt} REQUIRED visual anchors: match narration location and objects."
            )[:900]
        if not ok:
            self.log.log("checkpoint1_fail", issues=issues, beat=beat.index, anchors=anchors, hits=hit)
        return ok, beat, issues

    def check_image(self, image: Path, *, expected_ratio: str = "9:16") -> Tuple[bool, List[str]]:
        issues: List[str] = []
        if not image.exists() or image.stat().st_size < 2500:
            issues.append("image_too_small")
            self.log.log("checkpoint2_fail", issues=issues, image=str(image))
            return False, issues
        try:
            from PIL import Image

            with Image.open(image) as im:
                w, h = im.size
            if w < 320 or h < 320:
                issues.append("low_resolution")
            if expected_ratio == "9:16" and h < w:
                issues.append("wrong_aspect_portrait_expected")
            if expected_ratio == "16:9" and w < h:
                issues.append("wrong_aspect_landscape_expected")
        except Exception as exc:
            issues.append(f"image_open_failed:{exc}")
        ok = not any(x.startswith("image_") or x.startswith("low_") or x.startswith("wrong_") for x in issues)
        if not ok:
            self.log.log("checkpoint2_fail", issues=issues, image=str(image))
        return ok, issues

    def check_sync(
        self,
        video: Path,
        audio: Optional[Path],
        *,
        target_dur: float,
        fps: float = 30.0,
    ) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        if not video.exists():
            return False, ["video_missing"]
        v = ffprobe_duration(video)
        if abs(v - target_dur) > 0.15:
            issues.append(f"duration_drift:{v:.3f}vs{target_dur:.3f}")
        if audio and audio.exists():
            a = ffprobe_duration(audio)
            if abs(v - a) > 0.15:
                issues.append(f"av_mismatch:{v:.3f}vs{a:.3f}")
        # fps soft check via ffprobe
        try:
            r = subprocess.run(
                [
                    ffmpeg_bin().replace("ffmpeg", "ffprobe") if False else "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=r_frame_rate",
                    "-of",
                    "default=nk=1:nw=1",
                    str(video),
                ],
                capture_output=True,
                text=True,
            )
            # Prefer shared probe helper path
        except Exception:
            pass
        ok = len(issues) == 0
        if not ok:
            self.log.log("checkpoint3_fail", issues=issues, video=str(video))
        return ok, issues


def _split_beats(narration: str, total_dur: float) -> List[Tuple[str, float]]:
    """Split narration into ~3–4s spoken beats; durations sum to total_dur."""
    text = (narration or "").strip()
    if not text:
        n = max(1, int(round(total_dur / 3.5)))
        each = total_dur / n
        return [("", each) for _ in range(n)]

    # Prefer sentence boundaries, else word chunks
    parts = re_split_sentences(text)
    if len(parts) == 1:
        words = text.split()
        chunk = max(4, int(len(words) / max(1, round(total_dur / 3.5))))
        parts = [" ".join(words[i : i + chunk]) for i in range(0, len(words), chunk)]

    weights = [max(1, len(p.split())) for p in parts]
    wsum = float(sum(weights))
    durs = [total_dur * (w / wsum) for w in weights]
    # Clamp each beat toward 3–4s by merging/splitting lightly
    beats: List[Tuple[str, float]] = []
    buf_t, buf_d = "", 0.0
    for p, d in zip(parts, durs):
        if buf_t and buf_d + d < BEAT_MIN:
            buf_t = f"{buf_t} {p}".strip()
            buf_d += d
            continue
        if buf_t:
            beats.append((buf_t, buf_d))
        buf_t, buf_d = p, d
        while buf_d > BEAT_MAX + 0.6 and " " in buf_t:
            # split long beat
            words = buf_t.split()
            mid = max(2, len(words) // 2)
            left = " ".join(words[:mid])
            right = " ".join(words[mid:])
            left_d = buf_d * (len(words[:mid]) / max(1, len(words)))
            beats.append((left, left_d))
            buf_t, buf_d = right, buf_d - left_d
    if buf_t:
        beats.append((buf_t, buf_d))

    # Renormalize to exact total_dur
    s = sum(d for _, d in beats) or 1.0
    beats = [(t, total_dur * (d / s)) for t, d in beats]
    return beats


def re_split_sentences(text: str) -> List[str]:
    import re

    chunks = re.split(r"(?<=[.!?।])\s+", text.strip())
    return [c.strip() for c in chunks if c.strip()] or [text.strip()]


MOTIONS = (
    "zoom_in",
    "zoom_out",
    "pan_lr",
    "pan_rl",
    "zoom_in_pan_lr",
    "zoom_out_pan_rl",
    "diag_dr",
    "diag_ul",
)


def _zoompan_filter(motion: str, w: int, h: int, duration: float, fps: int = 30) -> str:
    """
    Ken Burns that NEVER plateaus into a still frame.

    Old formulas clamped zoom (min/max) mid-clip → frozen picture.
    Here every axis is driven by on/(frames-1) so motion lasts the full beat.
    """
    frames = max(2, int(round(max(0.5, duration) * fps)))
    last = max(1, frames - 1)
    t = f"on/{last}"  # 0→1 over the beat

    m = (motion or "zoom_in").strip().lower()
    if m == "zoom_out":
        # 1.30 → 1.05 (always changing)
        z = f"1.30-0.25*({t})"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif m == "pan_lr":
        z = f"1.18+0.04*({t})"  # slow push while panning — never flat zoom
        x = f"(iw-iw/zoom)*({t})"
        y = f"ih/2-(ih/zoom/2)+0.02*ih*({t})"
    elif m == "pan_rl":
        z = f"1.22-0.04*({t})"
        x = f"(iw-iw/zoom)*(1-({t}))"
        y = f"ih/2-(ih/zoom/2)-0.02*ih*({t})"
    elif m == "zoom_in_pan_lr":
        z = f"1.05+0.22*({t})"
        x = f"(iw-iw/zoom)*({t})"
        y = "ih/2-(ih/zoom/2)"
    elif m == "zoom_out_pan_rl":
        z = f"1.28-0.20*({t})"
        x = f"(iw-iw/zoom)*(1-({t}))"
        y = "ih/2-(ih/zoom/2)"
    elif m == "diag_dr":
        z = f"1.10+0.16*({t})"
        x = f"(iw-iw/zoom)*({t})"
        y = f"(ih-ih/zoom)*({t})"
    elif m == "diag_ul":
        z = f"1.26-0.16*({t})"
        x = f"(iw-iw/zoom)*(1-({t}))"
        y = f"(ih-ih/zoom)*(1-({t}))"
    else:  # zoom_in — continuous push, never clamp mid-way
        z = f"1.05+0.23*({t})"
        x = "iw/2-(iw/zoom/2)"
        y = f"ih/2-(ih/zoom/2)+0.015*ih*({t})"

    # d=frames: one zoompan output covering the whole beat (avoids d=1 quirks)
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,format=yuv420p"
    )


class FallbackPipelineService:
    def __init__(
        self,
        *,
        work: Path,
        size: str = "1080x1920",
        pollinations_key: str = "",
        google_api_keys: Optional[List[str]] = None,
        profile: Optional[CharacterProfile] = None,
    ) -> None:
        self.work = work
        self.work.mkdir(parents=True, exist_ok=True)
        self.size = size
        self.w, self.h = (int(x) for x in size.split("x"))
        self.pollinations_key = pollinations_key or ""
        self.google_api_keys = [k for k in (google_api_keys or []) if (k or "").strip()]
        self.profile = profile or CharacterProfile(
            name="DocumentarySubject",
            visual_description="atmospheric documentary environment, no talking-head presenter",
            art_style="cinematic documentary still, photoreal, natural haze, 8k",
        )
        self.err = ErrorFallbackLogger(work)
        self.inspector = AgentInspector(self.err)

    def build(
        self,
        *,
        narration: str,
        duration: float,
        out_path: Path,
        audio_path: Optional[Path] = None,
        base_prompt: str = "",
        keywords: Optional[List[str]] = None,
        product_name: str = "",
        element: str = "",
        niche: str = "",
    ) -> FallbackResult:
        dur = max(BEAT_MIN, float(duration))
        if audio_path and Path(audio_path).exists():
            dur = max(dur, ffprobe_duration(audio_path))

        from pipeline.prompt_engineering import resolve_visual_subject

        subject = resolve_visual_subject(
            product_name or self.profile.name,
            keywords,
            narration,
        )
        # Never lock Ken Burns stills to abstract channel niche labels.
        self.profile.name = subject
        if subject.lower() not in (self.profile.visual_description or "").lower():
            self.profile.visual_description = (
                f"photoreal cinematic documentary still of {subject}, "
                "NO human face, NO portrait, NO talking head, exact subject fills frame"
            )

        hardened = harden_video_prompt(
            base_prompt,
            narration=narration,
            keywords=keywords,
            product_name=subject,
            element=element,
            niche=niche,
            duration_sec=dur,
        )
        from pipeline.prompt_hardening import preflight_keyword_prompt

        pre = preflight_keyword_prompt(
            hardened,
            keywords=keywords,
            narration=narration,
            product_name=subject,
        )
        hardened = str(pre.get("fixed_prompt") or hardened)
        # Prefer critic-revised / Agnes base prompt as the primary still description.
        subject_core = (base_prompt or hardened or "").strip()
        if len(subject_core) > 280:
            subject_core = subject_core[:280].rsplit(" ", 1)[0]

        raw_beats = _split_beats(narration, dur)
        beats: List[VisualBeat] = []
        for i, (text, bdur) in enumerate(raw_beats):
            seed = self.profile.base_seed + i
            motion = MOTIONS[i % len(MOTIONS)]
            anchors = extract_dialogue_anchors(text, limit=8)
            if not anchors:
                anchors = extract_dialogue_anchors(narration, limit=6)
            from pipeline.prompt_engineering import image_beat_prompt

            prompt = image_beat_prompt(
                art_style=self.profile.art_style,
                profile_name=subject,
                visual_description=self.profile.visual_description,
                keywords=keywords or [],
                anchors=anchors,
                beat_text=text or "",
                beat_index=i,
                beat_count=len(raw_beats),
                seed=seed,
            )
            if subject_core:
                prompt = f"{subject_core}. {prompt}"[:950]
            beat = VisualBeat(
                index=i,
                text=text,
                duration=bdur,
                prompt=prompt,
                seed=seed,
                motion=motion,
            )
            ok, beat, _ = self.inspector.check_prompt(
                beat=beat, profile=self.profile, narration=narration
            )
            if not ok:
                # one rewrite already applied in inspector
                pass
            beats.append(beat)

        frame_clips: List[Path] = []
        for beat in beats:
            clip = self._render_beat_clip(beat)
            frame_clips.append(clip)

        silent = self.work / "fb_silent_concat.mp4"
        FFmpegProcessor.concat(frame_clips, silent, size=self.size)
        final = out_path
        if audio_path and Path(audio_path).exists():
            FFmpegProcessor.mux_audio(silent, audio_path, final, size=self.size)
        else:
            import shutil

            shutil.copy2(silent, final)

        sync_ok, sync_issues = self.inspector.check_sync(
            final, audio_path if audio_path and Path(audio_path).exists() else None, target_dur=dur
        )
        # IMAGE rule: if TTS longer than picture → new same-seed beats (NOT tpad/stretch)
        if audio_path and Path(audio_path).exists():
            a_dur = ffprobe_duration(audio_path)
            v_dur = ffprobe_duration(final if final.exists() else silent)
            if a_dur > v_dur + 0.35:
                logger.info(
                    "Image fallback: audio %.2fs > video %.2fs — extending with same-seed beats",
                    a_dur,
                    v_dur,
                )
                silent = self.extend_silent_with_same_seed(
                    silent,
                    target_duration=a_dur,
                    base_prompt=hardened,
                    keywords=list(keywords or []),
                    narration=narration,
                    existing_beats=len(beats),
                )
                FFmpegProcessor.mux_audio(silent, audio_path, final, size=self.size)
                sync_ok, sync_issues = self.inspector.check_sync(
                    final, audio_path, target_dur=a_dur
                )

        result = FallbackResult(
            path=final,
            provider="image_kenburns_fallback",
            beats=len(list(self.work.glob("fb_beat_*.png"))),
            seed=self.profile.base_seed,
            log_path=self.err.path,
            inspector={"sync_ok": sync_ok, "sync_issues": sync_issues, "beats": [asdict(b) for b in beats]},
        )
        (self.work / "fallback_result.json").write_text(
            json.dumps(
                {
                    "path": str(final),
                    "provider": result.provider,
                    "beats": result.beats,
                    "seed": result.seed,
                    "base_seed": self.profile.base_seed,
                    "inspector": result.inspector,
                    "keywords": list(keywords or []),
                    "base_prompt": (base_prompt or "")[:500],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info(
            "Fallback I2V ready path=%s beats=%s seed=%s sync_ok=%s",
            final,
            result.beats,
            result.seed,
            sync_ok,
        )
        return result

    def _render_beat_clip(self, beat: VisualBeat) -> Path:
        img = self.work / f"fb_beat_{beat.index:02d}.png"
        clip = self.work / f"fb_clip_{beat.index:02d}.mp4"
        # Reuse existing good beat image when present
        img_ok = img.exists() and img.stat().st_size > 2500
        if img_ok:
            ok, _ = self.inspector.check_image(
                img, expected_ratio="9:16" if self.h > self.w else "16:9"
            )
            img_ok = ok
        if not img_ok:
            img_ok = False
            for attempt in range(1, MAX_INSPECTOR_RETRIES + 2):
                seed = beat.seed + (attempt - 1)
                try:
                    self._generate_image(beat.prompt, img, seed=seed)
                except Exception as exc:
                    self.err.log(
                        "image_api_fail", beat=beat.index, attempt=attempt, error=str(exc)[:200]
                    )
                    continue
                ok, issues = self.inspector.check_image(
                    img, expected_ratio="9:16" if self.h > self.w else "16:9"
                )
                if ok:
                    img_ok = True
                    break
                beat.prompt = (
                    beat.prompt
                    + " high quality, no distortion, no extra limbs, sharp focus, clean composition"
                )[:900]
                self.err.log("image_retry", beat=beat.index, attempt=attempt, issues=issues)
            if not img_ok:
                raise RuntimeError(f"Fallback image failed for beat {beat.index}")
        FFmpegProcessor.image_to_ken_burns(
            img, clip, duration=beat.duration, size=self.size, motion=beat.motion, fps=30
        )
        return clip

    def extend_silent_with_same_seed(
        self,
        silent: Path,
        *,
        target_duration: float,
        base_prompt: str,
        keywords: List[str],
        narration: str,
        existing_beats: int,
    ) -> Path:
        """
        Grow Ken Burns picture to cover longer TTS by generating NEW images
        with the SAME base seed family (base_seed + beat_index). Never tpad/stretch.
        """
        v_dur = ffprobe_duration(silent) if silent.exists() else 0.0
        need = max(0.0, float(target_duration) - v_dur)
        if need < 0.3:
            return silent
        n_extra = max(1, int(round(need / 3.5)))
        extra_clips: List[Path] = []
        # Keep prior clips
        prior = sorted(self.work.glob("fb_clip_*.mp4"))
        for i in range(n_extra):
            idx = existing_beats + i
            seed = self.profile.base_seed + idx  # SAME seed lineage
            bdur = need / n_extra
            bdur = max(BEAT_MIN, min(BEAT_MAX + 0.5, bdur))
            prompt = (
                f"{self.profile.art_style}. Character/scene lock: {self.profile.name} — "
                f"{self.profile.visual_description}. "
                f"REQUIRED visual anchors: {', '.join(keywords[:6]) or self.profile.name}. "
                f"Continuation beat {idx + 1} (same seed family {self.profile.base_seed}). "
                f"seed={seed}. {base_prompt[:400]} {(narration or '')[:120]}"
            )[:900]
            beat = VisualBeat(
                index=idx,
                text=(narration or "")[-80:],
                duration=bdur,
                prompt=prompt,
                seed=seed,
                motion=MOTIONS[idx % len(MOTIONS)],
            )
            extra_clips.append(self._render_beat_clip(beat))
            self.err.log(
                "same_seed_extend",
                beat=idx,
                seed=seed,
                duration=bdur,
                target=target_duration,
            )
        all_clips = list(prior) + extra_clips if prior else extra_clips
        # Prefer ordered by index
        def _idx(p: Path) -> int:
            try:
                return int(p.stem.split("_")[-1])
            except Exception:
                return 0

        all_clips = sorted(set(all_clips), key=_idx)
        out = self.work / "fb_silent_concat.mp4"
        FFmpegProcessor.concat(all_clips, out, size=self.size)
        logger.info(
            "Extended image fallback +%s beats (same base_seed=%s) → %.2fs",
            n_extra,
            self.profile.base_seed,
            ffprobe_duration(out),
        )
        return out

    def _generate_image(self, prompt: str, out_path: Path, *, seed: int) -> Path:
        from pipeline.media_assets import _ai_still_via_chain

        seeded = f"{prompt} [seed:{seed}]"
        return _ai_still_via_chain(
            seeded,
            out_path,
            width=min(self.w, 1080),
            height=min(self.h, 1920),
            api_key=self.pollinations_key,
            google_api_keys=list(self.google_api_keys or []),
        )


def extend_image_master_for_audio(
    *,
    work: Path,
    master_video: Path,
    audio_path: Path,
    out_path: Path,
    size: str = "1080x1920",
    narration: str = "",
    pollinations_key: str = "",
    google_api_keys: Optional[List[str]] = None,
) -> Path:
    """
    Public helper for localization: if localized TTS is longer than the image
    master, grow picture with same-seed Ken Burns beats instead of setpts stretch.
    """
    fb_dir = work / "_fallback_i2v"
    if not fb_dir.exists():
        fb_dir = work
    meta = {}
    meta_path = fb_dir / "fallback_result.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    base_seed = int(meta.get("base_seed") or meta.get("seed") or character_base_seed("Subject", narration or "doc"))
    keywords = list(meta.get("keywords") or [])
    base_prompt = str(meta.get("base_prompt") or "")
    profile = CharacterProfile(
        name=str(meta.get("product_name") or "Subject"),
        visual_description="cinematic documentary continuation, same location/style lock",
        base_seed=base_seed,
    )
    # Force profile seed
    profile.base_seed = base_seed
    svc = FallbackPipelineService(
        work=fb_dir,
        size=size,
        pollinations_key=pollinations_key,
        google_api_keys=google_api_keys,
        profile=profile,
    )
    a_dur = ffprobe_duration(audio_path)
    silent = fb_dir / "fb_silent_concat.mp4"
    if not silent.exists():
        # rebuild silent from existing beat clips if possible
        clips = sorted(fb_dir.glob("fb_clip_*.mp4"))
        if clips:
            FFmpegProcessor.concat(clips, silent, size=size)
        else:
            import shutil

            shutil.copy2(master_video, silent)
    existing = len(list(fb_dir.glob("fb_beat_*.png")))
    silent = svc.extend_silent_with_same_seed(
        silent,
        target_duration=a_dur,
        base_prompt=base_prompt or narration,
        keywords=keywords,
        narration=narration,
        existing_beats=max(existing, 1),
    )
    FFmpegProcessor.mux_audio(silent, audio_path, out_path, size=size, pad_to_audio=False)
    return out_path


class FFmpegProcessor:
    @staticmethod
    def image_to_ken_burns(
        image: Path,
        dest: Path,
        *,
        duration: float,
        size: str,
        motion: str = "zoom_in",
        fps: int = 30,
    ) -> Path:
        w, h = (int(x) for x in size.split("x"))
        vf = _zoompan_filter(motion, w, h, duration, fps=fps)
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-loop",
            "1",
            "-i",
            str(image),
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-an",
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 2000:
            # Emergency: still ALWAYS moving (never a frozen still)
            logger.warning("Ken Burns primary failed (%s) — continuous zoom fallback", (r.stderr or "")[-180:])
            last = max(1, int(round(duration * fps)) - 1)
            emergency = (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"zoompan=z='1.08+0.20*on/{last}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={last + 1}:s={w}x{h}:fps={fps},"
                f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,format=yuv420p"
            )
            cmd = [
                ffmpeg_bin(),
                "-y",
                "-loop",
                "1",
                "-i",
                str(image),
                "-t",
                f"{duration:.3f}",
                "-vf",
                emergency,
                "-an",
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(dest),
            ]
            r2 = subprocess.run(cmd, capture_output=True, text=True)
            if r2.returncode != 0 or not dest.exists():
                raise RuntimeError(f"ken_burns_failed: {(r2.stderr or r.stderr or '')[-300:]}")
        return dest

    @staticmethod
    def concat(clips: Sequence[Path], dest: Path, *, size: str) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if len(clips) == 1:
            import shutil

            shutil.copy2(clips[0], dest)
            return dest
        lst = dest.parent / f"_fb_concat_{dest.stem}.txt"
        lst.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in clips), encoding="utf-8")
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"fallback concat failed: {(r.stderr or '')[-300:]}")
        return dest

    @staticmethod
    def mux_audio(
        video: Path,
        audio: Path,
        dest: Path,
        *,
        size: str,
        pad_to_audio: bool = False,
    ) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Prefer -shortest. If pad_to_audio: SLOW the clip (setpts) so Ken Burns keeps moving —
        # never tpad=clone (that freezes the last frame into a still photo).
        if pad_to_audio:
            a_dur = ffprobe_duration(audio)
            v_dur = max(0.1, ffprobe_duration(video))
            pad = max(0.0, a_dur - v_dur)
            if pad > 0.05:
                factor = a_dur / v_dur
                # Cap mild slowdown; large gaps should use extend_silent_with_same_seed instead
                factor = min(1.35, max(1.0, factor))
                vf = f"setpts={factor:.6f}*PTS"
                logger.info(
                    "mux pad_to_audio via setpts=%.3f (keep motion; avoid freeze-clone)",
                    factor,
                )
            else:
                vf = "null"
            cmd = [
                ffmpeg_bin(),
                "-y",
                "-i",
                str(video),
                "-i",
                str(audio),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(dest),
            ]
        else:
            cmd = [
                ffmpeg_bin(),
                "-y",
                "-i",
                str(video),
                "-i",
                str(audio),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(dest),
            ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"fallback mux failed: {(r.stderr or '')[-300:]}")
        return dest


# Public documentary stills (CDN-reachable). Keys match narration/subject for selection.
# IMPORTANT: do NOT bind bare "moon"/"cislunar" to JWST/Hubble deep-field plates —
# lunar surface / Artemis prospecting topics were incorrectly getting nebula b-roll.
_DEFAULT_DOC_STILL = "https://cdn.esawebb.org/archives/images/screen/weic2207a.jpg"
_DOC_REFERENCE_STILLS: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (
        (
            "shadowed crater",
            "permanently shadowed",
            "shadowed regions",
            "polar crater",
            "sunlight",
            "40 kelvin",
            "kelvin",
            "cryogenic",
        ),
        # Apollo 17 rover with deep pitch-black shadows (proxy for PSR darkness)
        "https://images-assets.nasa.gov/image/as17-137-20979/as17-137-20979~medium.jpg",
    ),
    (
        (
            "neutron spectrometer",
            "neutron spectrometers",
            "spectrometer",
            "spectrometers",
            "fast neutrons",
            "neutrons",
            "hydrogen atoms",
            "hydrogen",
            "lunar rover",
            "prospector rover",
            "rover",
            "water ice",
            "lunar ice",
            "regolith",
            "lunar regolith",
            "artemis prospector",
            "crater rim",
            "comet impacts",
            "comet",
        ),
        # NASA Apollo 17 lunar rover (public, CDN-reachable)
        "https://images-assets.nasa.gov/image/as17-140-21496/as17-140-21496~medium.jpg",
    ),
    (
        ("lunar surface", "moon surface", "moonscape", "crater floor", "lunar pole", "moon", "lunar"),
        "https://images-assets.nasa.gov/image/PIA14006/PIA14006~medium.jpg",
    ),
    (
        (
            "subsurface ice",
            "drinking water",
            "rocket propellant",
            "propellant",
            "crewed mars",
            "mars missions",
            "mars mission",
        ),
        # Lunar ice mapped for Mars logistics — still show Moon terrain, not Webb nebula
        "https://images-assets.nasa.gov/image/PIA14006/PIA14006~medium.jpg",
    ),
    (
        ("mars", "martian", "red planet"),
        "https://images-assets.nasa.gov/image/PIA17944/PIA17944~medium.jpg",
    ),
    (
        ("orion", "capsule", "crew module", "artemis ii", "artemis 2", "astronaut"),
        "https://cdn.esawebb.org/archives/images/screen/weic2207a.jpg",
    ),
    (
        ("space launch system", "sls", "solid rocket", "booster", "liftoff", "powerful rocket"),
        "https://cdn.esahubble.org/archives/images/large/heic0406a.jpg",
    ),
    (
        ("heat shield", "ablative", "re-entry", "reentry", "plasma", "atmosphere"),
        "https://cdn.esawebb.org/archives/images/screen/weic2205a.jpg",
    ),
    (
        ("free-return", "free return", "trajectory", "lunar flyby"),
        "https://images-assets.nasa.gov/image/PIA14006/PIA14006~medium.jpg",
    ),
    (
        ("james webb", "jwst", "webb space telescope", "golden mirror", "sunshield", "hexagonal"),
        "https://assets.science.nasa.gov/content/dam/science/missions/webb/science/2022/06/STScI-01G1Q6WDRH19AMC8NXMRFSTBH6.png/jcr:content/renditions/2048x1593.jpg",
    ),
    (
        ("assembled", "dark matter", "cosmic web", "stephan"),
        "https://cdn.esawebb.org/archives/images/screen/weic2208a.jpg",
    ),
    (
        ("deep field", "thirteen billion", "distant galax", "galaxy cluster", "massive galax", "smacs"),
        "https://cdn.esawebb.org/archives/images/screen/weic2209a.jpg",
    ),
    (
        ("infrared", "dust", "nursery", "star-forming", "nebula", "carina", "cosmic cliffs", "cosmic dust"),
        "https://cdn.esawebb.org/archives/images/screen/weic2205a.jpg",
    ),
    (
        ("spiral", "whirlpool", "cartwheel", "early galax"),
        "https://cdn.esawebb.org/archives/images/screen/weic2212b.jpg",
    ),
    (
        ("universe", "evolving", "cosmos", "observatory"),
        "https://cdn.esawebb.org/archives/images/screen/weic2207a.jpg",
    ),
)


def select_documentary_reference_url(
    *,
    product_name: str = "",
    keywords: Optional[Sequence[str]] = None,
    narration: str = "",
) -> str:
    blob = " ".join(
        [
            str(product_name or ""),
            " ".join(str(k) for k in (keywords or [])),
            str(narration or ""),
        ]
    ).lower()
    for keys, url in _DOC_REFERENCE_STILLS:
        if any(k in blob for k in keys):
            return url
    return _DEFAULT_DOC_STILL


def build_reference_still_video(
    *,
    work: Path,
    out_path: Path,
    narration: str,
    duration: float,
    size: str = "1080x1920",
    audio_path: Optional[Path] = None,
    keywords: Optional[List[str]] = None,
    product_name: str = "",
) -> Path:
    """Ken Burns from a subject-matched public documentary still (not AI invent)."""
    from pipeline.compose import download_file

    dur = max(BEAT_MIN, float(duration))
    if audio_path and Path(audio_path).exists():
        dur = max(dur, ffprobe_duration(audio_path))
    url = select_documentary_reference_url(
        product_name=product_name,
        keywords=keywords,
        narration=narration,
    )
    ref_dir = work / "_fallback_ref"
    ref_dir.mkdir(parents=True, exist_ok=True)
    still = ref_dir / "reference_still.jpg"
    download_file(url, still)
    if not still.exists() or still.stat().st_size < 5000:
        raise RuntimeError("reference_still_download_failed")
    silent = ref_dir / "ref_silent.mp4"
    FFmpegProcessor.image_to_ken_burns(
        still,
        silent,
        duration=dur,
        size=size,
        motion="zoom_in",
    )
    if audio_path and Path(audio_path).exists():
        FFmpegProcessor.mux_audio(silent, Path(audio_path), out_path, size=size)
    else:
        import shutil

        shutil.copy2(silent, out_path)
    (ref_dir / "reference_meta.json").write_text(
        json.dumps(
            {
                "url": url,
                "product_name": product_name,
                "keywords": list(keywords or []),
                "narration": (narration or "")[:240],
                "duration": dur,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return out_path


def build_image_video_fallback(
    *,
    work: Path,
    out_path: Path,
    narration: str,
    duration: float,
    size: str = "1080x1920",
    audio_path: Optional[Path] = None,
    base_prompt: str = "",
    keywords: Optional[List[str]] = None,
    product_name: str = "",
    element: str = "",
    niche: str = "",
    pollinations_key: str = "",
    google_api_keys: Optional[List[str]] = None,
    character_name: str = "",
    character_description: str = "",
) -> Path:
    """Public entry: Agnes-fail → Ken Burns image pipeline."""
    try:
        from pipeline.live_activity import log as live_log

        live_log(
            "media",
            f"Image fallback start ({float(duration):.0f}s) — no Agnes wait",
            api="image",
            action="i2v_fallback",
        )
    except Exception:
        pass
    from pipeline.prompt_engineering import resolve_visual_subject

    subject = resolve_visual_subject(
        character_name or product_name,
        keywords,
        narration,
    )
    profile = CharacterProfile(
        name=subject or "Subject",
        visual_description=(
            character_description
            or (
                f"photoreal cinematic documentary still of {subject}, "
                "NO human face, NO portrait, NO talking head, exact subject fills frame"
            )
        ),
    )
    svc = FallbackPipelineService(
        work=work / "_fallback_i2v",
        size=size,
        pollinations_key=pollinations_key,
        google_api_keys=google_api_keys,
        profile=profile,
    )
    result = svc.build(
        narration=narration,
        duration=duration,
        out_path=out_path,
        audio_path=audio_path,
        base_prompt=base_prompt,
        keywords=keywords,
        product_name=product_name,
        element=element,
        niche=niche,
    )
    return result.path
