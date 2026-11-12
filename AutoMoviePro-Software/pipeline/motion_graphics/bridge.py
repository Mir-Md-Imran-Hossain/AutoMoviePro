# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Motion Graphics Engine Python Bridge
----------------------------------------------------
Orchestrates the headless Node.js/Remotion/Motion Canvas animation renderer and
pairs it with procedural micro-SFX sound design and FFmpeg muxing.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pipeline.audio_sfx_engine import ProceduralSFXEngine, SFXEvent
from pipeline.compose import ffmpeg_bin, ffprobe_duration

logger = logging.getLogger("MotionGraphicsBridge")
logger.setLevel(logging.INFO)

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR / "src"
BASE_DIR = CURRENT_DIR.parent.parent


class MotionGraphicsRenderer:
    """High-level Python bridge to the Headless Motion Graphics Renderer."""

    @classmethod
    def render_spec(
        cls,
        spec: Dict[str, Any],
        output_path: Union[str, Path],
        *,
        fps: int = 30,
        duration_sec: float = 3.5,
        width: int = 1080,
        height: int = 1920,
        transparent: bool = False,
    ) -> Path:
        """
        Renders a motion graphics composition JSON specification to a high-FPS video layer.
        Uses Node.js + Playwright + FFmpeg with pure-Python Playwright fallback.
        """
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump(spec, tf, ensure_ascii=False, indent=2)
            spec_file = Path(tf.name)

        cli_js = SRC_DIR / "cli.js"
        node_cmd = [
            "node",
            str(cli_js),
            "--spec", str(spec_file),
            "--output", str(out_p),
            "--fps", str(fps),
            "--duration", str(duration_sec),
            "--width", str(width),
            "--height", str(height),
        ]
        if transparent:
            node_cmd.append("--transparent")

        logger.info(f"[MotionGraphicsRenderer] Executing Node renderer for {out_p.name} ({duration_sec}s @ {fps}fps)...")

        # Run with current working dir set to CURRENT_DIR so node_modules resolves
        res = subprocess.run(
            node_cmd,
            cwd=str(CURRENT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

        try:
            if spec_file.exists():
                spec_file.unlink()
        except Exception:
            pass

        if res.returncode == 0 and out_p.exists() and out_p.stat().st_size > 1000:
            logger.info(f"[MotionGraphicsRenderer] Render complete: {out_p} ({out_p.stat().st_size} bytes)")
            return out_p

        logger.warning(
            f"[MotionGraphicsRenderer] Node CLI exited with code {res.returncode}. Stderr: {res.stderr[:400]}. "
            f"Attempting Python Playwright fallback..."
        )

        # Python Playwright Fallback
        return cls._render_with_python_playwright(
            spec=spec,
            output_path=out_p,
            fps=fps,
            duration_sec=duration_sec,
            width=width,
            height=height,
            transparent=transparent,
        )

    @classmethod
    def _render_with_python_playwright(
        cls,
        spec: Dict[str, Any],
        output_path: Path,
        fps: int = 30,
        duration_sec: float = 3.5,
        width: int = 1080,
        height: int = 1920,
        transparent: bool = False,
    ) -> Path:
        """Resilient Python-native Playwright renderer."""
        from playwright.sync_api import sync_playwright

        total_frames = max(1, int(round(duration_sec * fps)))
        browser_dir = BASE_DIR / "data" / "playwright_browsers"
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)

        harness_path = (SRC_DIR / "harness.html").resolve()
        harness_url = f"file:///{str(harness_path).replace(os.sep, '/')}"

        ffmpeg_exe = ffmpeg_bin()
        ffmpeg_cmd = [
            ffmpeg_exe,
            "-y",
            "-f", "image2pipe",
            "-vcodec", "png",
            "-r", str(fps),
            "-i", "-",
        ]
        if transparent:
            if str(output_path).lower().endswith(".mov"):
                ffmpeg_cmd.extend(["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le"])
            else:
                ffmpeg_cmd.extend(["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p"])
        else:
            ffmpeg_cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"])

        ffmpeg_cmd.append(str(output_path))

        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(harness_url)

            full_spec = dict(spec)
            full_spec.update({
                "width": width,
                "height": height,
                "fps": fps,
                "durationSec": duration_sec,
                "renderLayer1": not transparent and spec.get("renderLayer1", True),
                "renderLayer2": spec.get("renderLayer2", True),
                "renderLayer3": spec.get("renderLayer3", True),
            })

            page.evaluate("spec => window.__initHarness(spec)", full_spec)
            page.wait_for_timeout(100)

            canvas_loc = page.locator("#motionCanvas")

            for f in range(total_frames):
                page.evaluate("f => window.__renderFrame(f)", f)
                png_bytes = canvas_loc.screenshot(omit_background=transparent, type="png")
                proc.stdin.write(png_bytes)

            proc.stdin.close()
            proc.wait()
            browser.close()

        if output_path.exists() and output_path.stat().st_size > 1000:
            return output_path
        raise RuntimeError(f"Playwright fallback failed to produce valid output at {output_path}")

    @classmethod
    def render_complete_3layer_clip(
        cls,
        *,
        headline: str,
        template_type: str = "data_graph",  # "data_graph" or "glassmorphic_gauge"
        metric: str = "+৮৫%",
        badge: str = "KEY DATA INSIGHT",
        spoken_text: str = "",
        cues: Optional[List[Dict[str, Any]]] = None,
        duration_sec: float = 3.5,
        narration_audio: Optional[Path] = None,
        dest_path: Optional[Path] = None,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        enable_micro_sfx: bool = True,
    ) -> Path:
        """
        Builds and renders the full 3-Layer next-gen composition synchronized with procedural micro-SFX.
        Layer 1: Dark Cyberpunk Grid, Floating Neon Particles, Pulse Glow.
        Layer 2: Glassmorphic HUD Data Card with Spring Physics (Data graph or Radial gauge).
        Layer 3: Kinetic Typography with word highlights.
        Sound: Pop, Whoosh, Digital Click, Glitch procedural micro-SFX.
        """
        if narration_audio and Path(narration_audio).exists():
            duration_sec = max(2.5, ffprobe_duration(narration_audio))

        dest_clip = Path(dest_path or (CURRENT_DIR / f"test_clip_{template_type}.mp4")).resolve()
        dest_clip.parent.mkdir(parents=True, exist_ok=True)

        spec = {
            "templateType": template_type,
            "renderLayer1": True,
            "renderLayer2": True,
            "renderLayer3": True,
            "layer2Props": {
                "headline": headline,
                "metric": metric,
                "badge": badge,
                "percentage": 85 if "%" not in metric else int("".join([c for c in metric if c.isdigit()]) or "85"),
                "subtext": spoken_text or "সঠিক অটোমেশন ও এআই ব্যবহারে কাজের গতি বাড়ে বহু গুণ।",
            },
            "layer3Props": {
                "spokenText": spoken_text or headline,
                "cues": cues or [],
            },
        }

        # 1. Render Video Track
        with tempfile.NamedTemporaryFile("w", suffix=".mp4", delete=False) as tf_vid:
            temp_vid = Path(tf_vid.name)

        cls.render_spec(
            spec=spec,
            output_path=temp_vid,
            fps=fps,
            duration_sec=duration_sec,
            width=width,
            height=height,
            transparent=False,
        )

        # 2. Render Procedural Micro-SFX Audio Track
        sfx_events = [
            {"time": 0.08, "type": "whoosh", "gain": 0.70},       # Card arrival whoosh
            {"time": 0.28, "type": "pop", "gain": 0.90},          # Card snap pop-in
            {"time": 0.75, "type": "digital_click", "gain": 0.75}, # Data curve / gauge draw start
            {"time": 1.45, "type": "glitch", "gain": 0.65},       # Highlight / metric reveal
        ]

        with tempfile.NamedTemporaryFile("w", suffix=".wav", delete=False) as tf_sfx:
            sfx_wav = Path(tf_sfx.name)

        ProceduralSFXEngine.render_event_timeline_wav(
            events=sfx_events,
            total_duration_sec=duration_sec,
            out_wav_path=sfx_wav,
        )

        # 3. Audio Muxing (Narration + Micro-SFX)
        fb = ffmpeg_bin()
        if narration_audio and Path(narration_audio).exists():
            # Mix narration with micro-SFX
            cmd = [
                fb, "-y",
                "-i", str(temp_vid),
                "-i", str(narration_audio),
                "-i", str(sfx_wav),
                "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=first:weights=1.0 0.85[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{duration_sec:.2f}",
                str(dest_clip),
            ]
        else:
            # Just micro-SFX audio
            cmd = [
                fb, "-y",
                "-i", str(temp_vid),
                "-i", str(sfx_wav),
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{duration_sec:.2f}",
                str(dest_clip),
            ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for p in (temp_vid, sfx_wav):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

        return dest_clip
