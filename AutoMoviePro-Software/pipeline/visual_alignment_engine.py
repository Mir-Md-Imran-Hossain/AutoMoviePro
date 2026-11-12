# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Visual Alignment & Semantic Decomposition Engine
================================================================
Bridges dialogue, scene narration, and overarching video topic into
a rigorous "Visual Bible" and frame-level "Semantic Decomposition" (Subject, Action, Environment).

Key Responsibilities:
1. "The Visual Bible" Synthesis:
   - Establishes global era, color palette, lighting atmosphere, and universe constraints
     for the ENTIRE video to prevent thematic drift (e.g., modern elements in ancient history).
2. Semantic Intent Decomposition:
   - Decomposes every dialogue/narration line into:
     - concrete_subject (visible primary entity)
     - action_context (physical motion/state)
     - environment_setting (background/space)
     - camera_framing (wide, medium, close-up, drone)
3. Dual-Vector Grounded B-Roll Queries:
   - Formulates context-anchored 3-4 word queries (Subject + Setting)
     eliminating naive literal keywords (e.g., preventing car crashes for market crashes).
4. Authentic Category B Metric & Fact Extraction:
   - Generates real, highly relevant scientific, geographical, or historical data cards
     derived strictly from the dialogue and topic (Zero hardcoded nonsense).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pipeline.llm_router import chat_text, extract_json_object

logger = logging.getLogger("AutoMoviePro.VisualAlignmentEngine")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s][VisualAlignmentEngine][%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
    logger.setLevel(logging.INFO)


@dataclass
class VisualBible:
    """Master visual style and thematic constraints for the entire video."""
    topic_title: str
    niche: str
    era_classification: str = "Contemporary Documentary"
    visual_world: str = "Cinematic Photorealistic Documentary"
    color_palette: List[str] = field(default_factory=lambda: ["#0B132B", "#1C2541", "#5BC0BE"])
    lighting_style: str = "Natural atmospheric directional lighting with soft volumetric haze"
    negative_universe_constraints: str = "no cartoon, no 3D render, no CGI artifacts, no modern plastic"
    aspect_ratio: str = "9:16"


@dataclass
class SemanticSceneDecomposition:
    """Decomposition of a single dialogue line into concrete visual elements."""
    scene_id: str
    dialogue_bn: str
    concrete_subject: str
    action_context: str
    environment_setting: str
    camera_framing: str
    grounded_broll_query: str
    positive_cinematic_prompt: str
    category_b_card_title: str
    category_b_metrics: List[str]
    category_b_facts: List[str]


class VisualAlignmentEngine:
    """Core engine ensuring 100% semantic harmony between narration and visual rendering."""

    _instance: Optional[VisualAlignmentEngine] = None

    @classmethod
    def get_instance(cls) -> VisualAlignmentEngine:
        if cls._instance is None:
            cls._instance = VisualAlignmentEngine()
        return cls._instance

    def __init__(self):
        self.cached_bibles: Dict[str, VisualBible] = {}

    def construct_visual_bible(
        self,
        topic_title: str,
        niche: str,
        category: str = "Category A",
        aspect_ratio: str = "9:16"
    ) -> VisualBible:
        """
        Synthesizes the master Visual Bible for the video, establishing global era and aesthetic constraints.
        """
        cache_key = f"{topic_title}_{niche}_{aspect_ratio}"
        if cache_key in self.cached_bibles:
            return self.cached_bibles[cache_key]

        era = self._infer_era(topic_title, niche)
        visual_world = self._infer_visual_world(niche, era, category)
        lighting = self._infer_lighting(era, niche)
        negatives = self._infer_negative_universe(era, niche)

        bible = VisualBible(
            topic_title=topic_title,
            niche=niche,
            era_classification=era,
            visual_world=visual_world,
            lighting_style=lighting,
            negative_universe_constraints=negatives,
            aspect_ratio=aspect_ratio
        )
        self.cached_bibles[cache_key] = bible
        logger.info("🎬 [VisualBible] Constructed for '%s' | Era: %s | World: %s", topic_title[:35], era, visual_world[:30])
        return bible

    def decompose_scene_dialogue(
        self,
        scene: Dict[str, Any],
        scene_idx: int,
        total_scenes: int,
        bible: VisualBible
    ) -> SemanticSceneDecomposition:
        """
        Decomposes a scene's narration into Concrete Subject, Action, Environment,
        and generates context-locked B-Roll queries and Category B infographic cards.
        """
        scene_id = scene.get("scene_id", f"scene_{scene_idx:02d}")
        dialogue = str(scene.get("dialogue_bn") or scene.get("narration") or "").strip()
        raw_subject = str(scene.get("concrete_visual_subject") or scene.get("visual_direction") or "").strip()

        # Shot Variety: Establish -> Context -> Action -> Reveal -> Wrap
        shot_type = self._determine_shot_progression(scene_idx, total_scenes)

        # Decompose narration
        subject, action, env = self._extract_semantic_triplet(dialogue, raw_subject, bible)

        # Build grounded B-Roll query (Subject + Setting)
        try:
            from pipeline.concrete_entity_extractor import extract_concrete_entity_from_dialogue
            c_info = extract_concrete_entity_from_dialogue(dialogue, niche=bible.niche, fallback_subject=raw_subject)
            if c_info.get("is_specific_match") and c_info.get("stock_query"):
                broll_query = c_info["stock_query"]
            else:
                broll_query = self._synthesize_grounded_broll_query(subject, env, bible)
        except Exception:
            broll_query = self._synthesize_grounded_broll_query(subject, env, bible)

        # Positive cinematic prompt fully locked to Visual Bible
        positive_prompt = (
            f"{shot_type} of {subject}, {action}, located in {env}. "
            f"{bible.lighting_style}, authentic {bible.era_classification} details, "
            f"cinematic 8k photorealistic documentary style, sharp focus, 35mm film aesthetic, high dynamic range."
        )

        # Category B Authentic Data & Metrics (Never Mariana Trench or random numbers!)
        card_title, metrics, facts = self._synthesize_authentic_category_b_data(
            dialogue=dialogue,
            topic=bible.topic_title,
            scene_idx=scene_idx,
            total_scenes=total_scenes
        )

        return SemanticSceneDecomposition(
            scene_id=scene_id,
            dialogue_bn=dialogue,
            concrete_subject=subject,
            action_context=action,
            environment_setting=env,
            camera_framing=shot_type,
            grounded_broll_query=broll_query,
            positive_cinematic_prompt=positive_prompt,
            category_b_card_title=card_title,
            category_b_metrics=metrics,
            category_b_facts=facts
        )

    # -------------------------------------------------------------------------
    # Internal Heuristics & Grounding Logic
    # -------------------------------------------------------------------------

    def _infer_era(self, topic: str, niche: str) -> str:
        text = f"{topic} {niche}".lower()
        if any(k in text for k in ["ancient", "egypt", "pyramid", "temple", "rome", "greek", "stone age", "medieval", "emperor", "monument", "archaeology", "প্রাচীন", "মন্দির", "পিরামিড"]):
            return "Ancient Historical Antiquity (B.C. to Classical Era)"
        elif any(k in text for k in ["space", "universe", "planet", "galaxy", "mars", "moon", "astronomy", "মহাকাশ", "গ্রহ"]):
            return "Deep Space & Cosmic Science"
        elif any(k in text for k in ["chokepoint", "strait", "canal", "shipping", "trade", "cargo", "বাণিজ্য", "নৌপথ", "জাহাজ"]):
            return "Modern Maritime Geopolitics & Global Infrastructure"
        elif any(k in text for k in ["ocean", "marine", "underwater", "trench", "coral", "sea", "তিমি", "সাগর", "সমুদ্র"]):
            return "Marine Biology & Oceanography"
        elif any(k in text for k in ["ai", "robot", "quantum", "computer", "future", "tech", "প্রযুক্তি", "রোবট"]):
            return "Cutting-Edge Technology & Artificial Intelligence"
        return "Contemporary Documentary"

    def _infer_visual_world(self, niche: str, era: str, category: str) -> str:
        if "Ancient" in era:
            return "Ancient archaeological stonework, natural sandstone textures, historical authenticity"
        elif "Space" in era:
            return "Photorealistic interstellar phenomena, orbital perspectives, high-clarity telemetry"
        elif "Maritime" in era:
            return "Industrial maritime logistics, colossal container vessels, deep blue coastal waters and straits"
        elif category == "Category B":
            return "High-end broadcast analytical documentary, data-driven infographics, crisp architectural schematics"
        return "National Geographic style photorealistic cinematic documentary"

    def _infer_lighting(self, era: str, niche: str) -> str:
        if "Ancient" in era:
            return "Golden hour natural directional sunlight with warm shadows and airborne atmospheric dust"
        elif "Space" in era:
            return "Stark contrast cosmic star-light, solar rim lighting with deep pitch-black space backdrop"
        elif "Maritime" in era:
            return "Overhead daylight marine atmosphere, glistening ocean water reflections, crisp horizon clarity"
        return "Soft three-point cinematic lighting with natural ambient depth"

    def _infer_negative_universe(self, era: str, niche: str) -> str:
        base = (
            "cartoon, anime, 3d cgi render, videogame, plastic texture, doll face, oversaturated, "
            "watermark, stock photo logo, blurry, out of focus, distorted, disfigured, text overlay"
        )
        if "Ancient" in era:
            base += ", modern vehicles, modern cars, asphalt roads, electric wires, modern buildings, modern clothing, wristwatches, concrete highways"
        elif "Space" in era:
            base += ", clouds in space, sci-fi laser battles, fantasy spaceships, cartoon aliens"
        elif "Maritime" in era:
            base += ", wooden ancient galleys (unless historical), toy ships, bathtub water, unrealistic waves"
        return base

    def _determine_shot_progression(self, idx: int, total: int) -> str:
        if idx == 1:
            return "Extreme Wide Establishing Cinematic Shot"
        elif idx == 2:
            return "Wide Contextual Tracking Shot"
        elif idx == total:
            return "Grand Panoramic Wide Exit Shot"
        elif idx % 3 == 0:
            return "Intimate Close-up Macro Insert Shot"
        elif idx % 3 == 1:
            return "Medium Kinetic Motion Shot"
        else:
            return "High-Angle Dynamic Overview Shot"

    def _extract_semantic_triplet(
        self,
        dialogue: str,
        raw_subject: str,
        bible: VisualBible
    ) -> Tuple[str, str, str]:
        """
        Extracts Concrete Subject, Action, and Environment.
        Removes filler words and grounds entities to the Visual Bible.
        """
        # Priority 1: Ground-truth Bengali dialogue concrete entity extraction
        try:
            from pipeline.concrete_entity_extractor import extract_concrete_entity_from_dialogue
            c_ext = extract_concrete_entity_from_dialogue(dialogue, niche=bible.niche, fallback_subject=raw_subject)
            if c_ext.get("is_specific_match"):
                return c_ext["concrete_subject_en"], c_ext["action"], c_ext["environment"]
        except Exception:
            pass

        # Clean input
        clean_sub = re.sub(
            r'\b(Faceless B-Roll:|Category [AB]:|8K|4K|cinematic|photorealistic|documentary|shot|of|authentic|master)\b',
            ' ', raw_subject, flags=re.IGNORECASE
        ).strip()
        clean_sub = re.sub(r'\s+', ' ', clean_sub)

        # If raw_subject is already descriptive, extract elements
        if len(clean_sub.split()) >= 4:
            subject = clean_sub
            action = "captured in sharp steady motion"
            env = f"authentic {bible.era_classification} setting"
            return subject, action, env

        # Fallback heuristic mapping based on era & topic
        if "Ancient" in bible.era_classification:
            subject = clean_sub if clean_sub else "ancient monolithic stone structure"
            action = "standing colossal with intricate historical stonework"
            env = "sun-drenched historical archaeological valley"
        elif "Space" in bible.era_classification:
            subject = clean_sub if clean_sub else "celestial planetary body"
            action = "rotating slowly against deep cosmic starfield"
            env = "deep space orbital view"
        elif "Maritime" in bible.era_classification:
            subject = clean_sub if clean_sub else "colossal container cargo vessel"
            action = "navigating through narrow strategic shipping passage"
            env = "deep blue ocean strait under clear sky"
        else:
            subject = clean_sub if clean_sub else f"{bible.niche} primary subject"
            action = "exhibiting clear realistic motion"
            env = "natural cinematic environment"

        return subject, action, env

    def _synthesize_grounded_broll_query(self, subject: str, env: str, bible: VisualBible) -> str:
        """
        Synthesizes a clean 2-4 word search query combining Subject + Context
        (e.g., 'ancient temple carving' or 'cargo ship strait')
        avoiding generic single words.
        """
        # Strip punctuation & filler
        words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', f"{subject} {env}")]
        forbidden = {
            "the", "and", "with", "from", "into", "that", "this", "shot", "view", "scene",
            "cinematic", "photorealistic", "documentary", "ultra", "master", "lighting",
            "historical", "ancient", "modern", "authentic", "primary", "standing", "located"
        }
        filtered = [w for w in words if w not in forbidden]

        # Topic contextual anchor
        topic_words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', f"{bible.topic_title} {bible.niche}")]
        topic_anchor = [w for w in topic_words if w not in forbidden]

        combined = []
        for w in (filtered + topic_anchor):
            if w not in combined and len(combined) < 4:
                combined.append(w)

        if not combined:
            return "cinematic documentary landscape"
        return " ".join(combined[:3])

    def _synthesize_authentic_category_b_data(
        self,
        dialogue: str,
        topic: str,
        scene_idx: int,
        total_scenes: int
    ) -> Tuple[str, List[str], List[str]]:
        """
        Universally generates authentic, dialogue-grounded facts and metrics for Category B.
        Zero hardcoded templates or fake checklist items across all niches.
        """
        from pipeline.category_b_visual_director import extract_category_b_visual_spec
        spec = extract_category_b_visual_spec(
            dialogue_bn=dialogue,
            niche=topic,
            scene_idx=scene_idx,
            total_scenes=total_scenes,
            is_widescreen=False
        )

        callout = spec["callout"]
        actor = spec["motion_actor"]

        headline = f"{callout['icon']} {callout['title']}"
        metrics = [
            f"{callout['title'].upper()}: {callout['detail']}",
            f"{actor['icon']} {actor['label']}: ACTIVE"
        ]
        facts = [
            f"{callout['icon']} {callout['title']}",
            f"{callout['detail']}",
            f"{actor['icon']} {actor['label']}"
        ]

        return headline, metrics, facts


# Global Accessor
def get_visual_alignment_engine() -> VisualAlignmentEngine:
    return VisualAlignmentEngine.get_instance()
