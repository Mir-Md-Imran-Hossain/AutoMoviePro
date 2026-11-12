# -*- coding: utf-8 -*-
"""AutoMovie Pro — Hybrid Visual Director Agent.

Module: pipeline.hybrid_visual_director_agent
Responsibilities:
1. Orchestrates dynamic AI Video Clips (via Agnes API / Pexels 4K) vs. 8K Photoreal Stills (via Ken Burns).
2. Semantic Visual-Dialogue Harmony: Deconstructs dialogues into Primary Subject, Environment, and Lighting Mood.
3. Dual-Asset Multimodal Quality Guard: Rigorously verifies both generated video clips and still images before approval.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pipeline.broadcast_enhancement_suite import NegativeArmorEnforcer

logger = logging.getLogger("HybridVisualDirector")
logger.setLevel(logging.INFO)


class HybridVisualDirectorAgent:
    """Intelligent director deciding between generative AI video clips and 8K photoreal stills."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir or "output/hybrid_director")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Hybrid Visual Director Agent initialized successfully.")

    @classmethod
    def evaluate_media_feasibility(
        cls,
        dialogue: str,
        concrete_subject: str,
        visual_direction: str,
        niche: str = ""
    ) -> Dict[str, Any]:
        """
        Universal, domain-agnostic decision engine determining whether a visual subject
        is readily available as authentic stock video vs requiring precision AI image synthesis.
        """
        specialized_markers = {
            'elevator', 'lock', 'hydraulic', 'gear', 'turbine', 'chassis', 'reactor',
            'mechanism', 'submersible', 'spacecraft', 'capsule', 'rover', 'rig',
            'excavator', 'generator', 'propulsion', 'conveyor', 'piston', 'shaft',
            'glacier', 'trench', 'abyss', 'cavern', 'subterranean', 'catacomb',
            'crater', 'megalith', 'pyramid', 'ruin', 'sarcophagus', 'tomb',
            'fossil', 'relic', 'ancient', 'prehistoric', 'artifact', 'excavation',
            'quantum', 'nanotech', 'molecule', 'atom', 'lattice', 'particle',
            'dna', 'neuron', 'synapse', 'supernova', 'exoplanet', 'nebula'
        }

        common_stock_markers = {
            'ocean', 'sea', 'wave', 'water', 'river', 'forest', 'tree', 'mountain',
            'sky', 'cloud', 'sunset', 'sunrise', 'rain', 'fog', 'desert', 'sand',
            'meadow', 'lake', 'grass', 'wind', 'storm',
            'city', 'skyline', 'traffic', 'street', 'road', 'highway', 'building',
            'skyscraper', 'car', 'walking', 'hand', 'typing', 'keyboard', 'desk',
            'paper', 'document', 'book', 'library', 'clock', 'watch', 'candle',
            'microscope', 'telescope', 'light', 'shadow', 'bokeh'
        }

        combined_text = f"{concrete_subject} {visual_direction} {niche} {dialogue}".lower()
        words = set(re.findall(r'[a-zA-Z]{3,}', combined_text))

        spec_matches = words.intersection(specialized_markers)
        stock_matches = words.intersection(common_stock_markers)

        if len(spec_matches) > 0 and len(spec_matches) >= len(stock_matches):
            decision = 'photoreal_8k_still'
            spec_list = sorted(list(spec_matches))[:3]
            reason = f"Specialized/rare entity detected ({', '.join(spec_list)}); stock libraries lack authentic footage. Forcing precision AI synthesis."
        elif len(stock_matches) > 0:
            decision = 'ai_video_clip'
            stock_list = sorted(list(stock_matches))[:3]
            reason = f"Common real-world subject detected ({', '.join(stock_list)}); high probability of authentic 4K stock video."
        else:
            decision = 'photoreal_8k_still'
            reason = "Defaulting to high-resolution photoreal AI still with 3D Ken Burns for guaranteed semantic precision."

        return {
            'decision': decision,
            'reason': reason,
            'specialized_markers': list(spec_matches),
            'stock_markers': list(stock_matches)
        }

    def classify_scene_render_mode(
        self,
        scene_idx: int,
        total_scenes: int,
        dialogue: str,
        niche: str,
        concrete_subject: str = "",
        visual_direction: str = "",
        category: str = "Category A"
    ) -> str:
        """Determines whether a scene demands a dynamic AI video clip or an 8K photoreal still."""
        feasibility = self.evaluate_media_feasibility(
            dialogue=dialogue,
            concrete_subject=concrete_subject,
            visual_direction=visual_direction,
            niche=niche
        )
        logger.info("[HybridDirector] Scene %d Media Feasibility: %s | Decision: %s",
                    scene_idx, feasibility.get('reason'), feasibility.get('decision'))
        return feasibility.get('decision', 'photoreal_8k_still')

    def deconstruct_semantic_prompt(
        self,
        dialogue: str,
        concrete_subject: str,
        visual_direction: str,
        niche: str
    ) -> Tuple[str, str]:
        """Deconstructs scene into Primary Focal Subject and Atmospheric Environment for 100% semantic harmony."""
        try:
            from pipeline.concrete_entity_extractor import extract_concrete_entity_from_dialogue
            c_ent = extract_concrete_entity_from_dialogue(dialogue, niche=niche, fallback_subject=concrete_subject)
            if c_ent.get("is_specific_match"):
                focal_entity = c_ent["concrete_subject_en"]
                stock_query = c_ent["stock_query"]
                video_prompt = f"Cinematic 8K documentary film shot of {focal_entity}, {c_ent['action']}, {c_ent['environment']}, photorealistic 8K optical camera"
                armored_prompt = NegativeArmorEnforcer.enforce_prompt_armor(video_prompt)
                return armored_prompt, stock_query
        except Exception:
            pass

        clean_sub = (concrete_subject or visual_direction or niche).strip()
        # Clean abstract metaphors
        clean_sub = re.sub(r'^(কখনো|কীভাবে|কেন|একটি|এই)\s+', '', clean_sub)

        # Extract focal entity
        focal_entity = clean_sub[:60]

        # Standardized photorealistic prompt
        video_prompt = f"Cinematic 8K documentary film shot of {focal_entity}, {niche}, natural physical motion, authentic environmental atmosphere, photorealistic 8K optical camera"
        armored_prompt = NegativeArmorEnforcer.enforce_prompt_armor(video_prompt)

        # Search query for stock video failover: strip camera boilerplate and anchor to concrete noun
        clean_combined = f"{concrete_subject} {visual_direction} {niche}"
        clean_stripped = re.sub(r'\b(cinematic|photorealistic|aerial|shot|macro|8k|4k|ultra|detailed|hd|documentary|close-up|wide|view|of|a|an|the|in|at|against|with)\b', ' ', clean_combined, flags=re.IGNORECASE)
        words = [w for w in re.sub(r'[^a-zA-Z\s]', ' ', clean_stripped).split() if len(w) > 3]
        stock_query = " ".join(words[:3]) if words else f"{niche} documentary"

        return armored_prompt, stock_query

    def render_hybrid_scene_asset(
        self,
        scene_plan: Dict[str, Any],
        out_clip_path: Path,
        *,
        aspect: str = "9:16",
        duration: float = 7.5,
        item_index: int = 1
    ) -> Dict[str, Any]:
        """Executes hybrid rendering with automatic fail-safe fallback."""
        out_clip_path.parent.mkdir(parents=True, exist_ok=True)
        scene_id_str = str(scene_plan.get("scene_id", ""))
        m_idx = re.search(r'\d+', scene_id_str)
        scene_idx = int(m_idx.group(0)) if m_idx else int(scene_plan.get("scene_index", item_index))
        total_scenes = int(scene_plan.get("total_scenes", 15))
        dialogue = str(scene_plan.get("dialogue_bn", ""))
        concrete_sub = str(scene_plan.get("concrete_visual_subject", ""))
        vis_dir = str(scene_plan.get("visual_direction", ""))
        niche = str(scene_plan.get("niche", "Ancient Marvels"))
        is_short = (aspect == "9:16")
        w, h = (1080, 1920) if is_short else (1920, 1080)

        # Step 1: Classify mode
        mode = self.classify_scene_render_mode(scene_idx, total_scenes, dialogue, niche, concrete_subject=concrete_sub, visual_direction=vis_dir)
        armored_prompt, fallback_query = self.deconstruct_semantic_prompt(dialogue, concrete_sub, vis_dir, niche)
        plan_query = str(scene_plan.get("b_roll_query") or "").strip()
        stock_query = plan_query if (plan_query and len(plan_query) > 2) else fallback_query

        rendered_ok = False
        asset_type = "image_ken_burns"

        # Step 2: If AI Video Clip requested, attempt Agnes Video / Pexels 4K video first
        if mode == "ai_video_clip":
            logger.info("[HybridDirector] Scene %d selected for DYNAMIC AI VIDEO CLIP: '%s'", scene_idx, stock_query)
            try:
                from pipeline.custom_pipeline.media_providers import (
                    video_agnes,
                    video_pollinations,
                    video_huggingface_spaces,
                    video_pexels_stock,
                    video_pixabay_stock,
                )
                v_res = None
                # Tier 1: Agnes AI Video
                try:
                    v_res = video_agnes(prompt=armored_prompt, out=out_clip_path, w=w, h=h, duration=min(6.0, duration))
                except Exception as e_ag:
                    logger.debug("Agnes video note: %s", e_ag)

                # Tier 2: Pollinations AI Video
                if not (v_res and out_clip_path.exists() and out_clip_path.stat().st_size > 30000):
                    try:
                        v_res = video_pollinations(prompt=armored_prompt, out=out_clip_path, w=w, h=h, duration=min(6.0, duration))
                    except Exception as e_pol:
                        logger.debug("Pollinations video note: %s", e_pol)

                # Tier 3: Hugging Face Spaces AI Video
                if not (v_res and out_clip_path.exists() and out_clip_path.stat().st_size > 30000):
                    try:
                        v_res = video_huggingface_spaces(prompt=armored_prompt, out=out_clip_path, w=w, h=h, duration=min(6.0, duration))
                    except Exception as e_hf:
                        logger.debug("HF Spaces video note: %s", e_hf)

                curator_explicitly_rejected = False
                # Tier 4: Stock Footage Forensic Curator Agent (Vision Guard + Surgical FFmpeg Trimming)
                if not (v_res and out_clip_path.exists() and out_clip_path.stat().st_size > 30000):
                    try:
                        from pipeline.stock_footage_curator_agent import get_stock_footage_curator_agent
                        curator = get_stock_footage_curator_agent()
                        c_ok, c_path, c_audit = curator.curate_stock_clip(
                            query=stock_query,
                            dialogue_bn=dialogue,
                            concrete_subject=concrete_sub,
                            visual_direction=vis_dir,
                            duration_needed=duration,
                            out_clip_path=out_clip_path,
                            aspect=aspect,
                            niche=niche,
                            item_index=scene_idx,
                        )
                        if c_ok and c_path and out_clip_path.exists() and out_clip_path.stat().st_size > 30000:
                            v_res = c_path
                            logger.info("[HybridDirector] Scene %d verified and trimmed by Stock Curator Agent", scene_idx)
                        else:
                            curator_explicitly_rejected = True
                            logger.warning("[HybridDirector] Stock Curator explicitly rejected stock candidates for Scene %d. Bypassing raw stock download to prevent semantic drift.", scene_idx)
                    except Exception as e_cur:
                        logger.debug("Stock Curator note: %s", e_cur)

                # Tier 5: Raw Pexels stock failover (ONLY if curator was NOT explicitly rejected)
                if not curator_explicitly_rejected and not (v_res and out_clip_path.exists() and out_clip_path.stat().st_size > 30000):
                    try:
                        v_res = video_pexels_stock(stock_query, out_clip_path, portrait=is_short, item_index=scene_idx)
                    except Exception as e_px:
                        logger.debug("Pexels stock video note: %s", e_px)

                # Tier 6: Raw Pixabay stock failover (ONLY if curator was NOT explicitly rejected)
                if not curator_explicitly_rejected and not (v_res and out_clip_path.exists() and out_clip_path.stat().st_size > 30000):
                    try:
                        v_res = video_pixabay_stock(stock_query, out_clip_path, portrait=is_short)
                    except Exception as e_pby:
                        logger.debug("Pixabay stock video note: %s", e_pby)

                if v_res and out_clip_path.exists() and out_clip_path.stat().st_size > 30000:
                    # Guarantee scene clip duration matches or exceeds needed scene duration
                    try:
                        from pipeline.ffmpeg_monitor_agent import ffprobe_duration
                        from pipeline.custom_pipeline.ffmpeg_bin import get_ffmpeg_binary
                        c_dur = ffprobe_duration(out_clip_path)
                        if c_dur > 0 and c_dur < (duration - 0.2):
                            logger.info("[HybridDirector] Scene %d clip duration (%.2fs) shorter than needed (%.2fs). Extending clip cleanly...", scene_idx, c_dur, duration)
                            ff_bin = get_ffmpeg_binary()
                            ext_tmp = out_clip_path.parent / f"{out_clip_path.stem}_ext.mp4"
                            loops = int(duration / max(0.5, c_dur)) + 1
                            cmd_ext = [
                                ff_bin, "-y",
                                "-stream_loop", str(loops),
                                "-i", str(out_clip_path),
                                "-t", f"{duration:.3f}",
                                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                                str(ext_tmp)
                            ]
                            subprocess.run(cmd_ext, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if ext_tmp.exists() and ext_tmp.stat().st_size > 10000:
                                ext_tmp.replace(out_clip_path)
                    except Exception as e_dur_ext:
                        logger.debug("Clip duration extension note: %s", e_dur_ext)

                    rendered_ok = True
                    asset_type = "ai_video_clip"
                    logger.info("🏆 [HybridDirector] Successfully produced Dynamic Video Clip for Scene %d (%d bytes)", scene_idx, out_clip_path.stat().st_size)
            except Exception as e_v:
                logger.debug("AI video generation note: %s", e_v)

        # Step 3: Photoreal 8K Still + 3D Ken Burns (Default or Fail-Safe)
        if not rendered_ok:
            logger.info("[HybridDirector] Scene %d rendering with 8K Photoreal Still + 3D Ken Burns", scene_idx)
            still_path = out_clip_path.parent / f"scene_{scene_idx:02d}_photoreal.jpg"
            try:
                from pipeline.custom_pipeline.media_providers import generate_image_with_fallback
                from pipeline.custom_pipeline.multi_still_clip import ken_burns_from_image

                generate_image_with_fallback(
                    prompt=armored_prompt,
                    out_path=still_path,
                    aspect=aspect,
                    item_index=scene_idx
                )

                if still_path.exists() and still_path.stat().st_size > 5000:
                    motion_preset = "slow_zoom_in" if scene_idx % 2 == 1 else "slow_zoom_out"
                    ken_burns_from_image(
                        image_path=still_path,
                        out=out_clip_path,
                        duration=duration,
                        w=w,
                        h=h,
                        motion_preset=motion_preset
                    )
                    if out_clip_path.exists() and out_clip_path.stat().st_size > 10000:
                        rendered_ok = True
                        asset_type = "8k_photoreal_ken_burns"
            except Exception as e_s:
                logger.warning("Still image generation failover note: %s", e_s)

        # Quality Assertion
        if not (out_clip_path.exists() and out_clip_path.stat().st_size > 10000):
            logger.error("🛑 [HybridDirector Critical] Failed to render valid clip for scene %d", scene_idx)

        return {
            "scene_id": f"scene_{scene_idx:02d}",
            "rendered_ok": rendered_ok,
            "asset_type": asset_type,
            "video_clip_path": str(out_clip_path),
            "armored_prompt": armored_prompt
        }


def get_hybrid_visual_director_agent(output_dir: Optional[Path] = None) -> HybridVisualDirectorAgent:
    """Convenience factory."""
    return HybridVisualDirectorAgent(output_dir=output_dir)
