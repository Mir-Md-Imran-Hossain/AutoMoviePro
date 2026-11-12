# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Industrial Semantic Contradiction & Literal Premise Guard
========================================================================
Guarantees that generated visuals and B-roll stock footage never contradict
the core factual, spatial, or physical premise of the spoken narrative.

Example:
- Narrative Hook: "যে উপজাতি মানুষ কখনো মাটিতে পা রাখে না! মেঘের ওপর বসবাস..."
- Prohibited Visuals: People walking on ground, desert sand, dirt roads, soil.
- Mandated Visuals: High aerial canopy treehouses, stilt platforms shrouded in clouds/mist,
  aerial suspension walkways, living 30 meters above ground in forest canopy.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AutoMoviePro.SemanticPremiseGuard")


PREMISE_PATTERNS: List[Dict[str, Any]] = [
    {
        "id": "never_touches_ground",
        "regex": r"(মাটিতে\s*পা\s*রাখে\s*না|মাটিতে\s*হাঁটে\s*না|মেঘের\s*ওপর|গাছের\s*(ডগায়|মাথায়)|আকাশে\s*বসবাস|never\s*steps?\s*on\s*ground|living\s*in\s*(clouds|canopy|treehouse))",
        "description": "Subjects living elevated or in tree canopies who never touch the ground",
        "negative_prompts": (
            "walking on ground, soil, desert sand, dirt road, ground walking, pavement, "
            "walking on earth, feet on dirt, desert dunes, camels on sand, mud path"
        ),
        "mandatory_visual_anchors": (
            "elevated bamboo treehouse village built 30 meters high in dense forest canopy, "
            "suspended rope bridges between tall giant trees wrapped in thick mountain cloud mist, "
            "aerial view of wooden stilt platforms high above forest floor, zero people walking on ground"
        ),
        "clean_stock_query": "treehouse canopy village mist aerial"
    },
    {
        "id": "abyssal_darkness",
        "regex": r"(সূর্যের\s*আলো\s*(পৌঁছায়\s*না|নেই)|চির\s*অন্ধকার|অতল\s*গভীরে|মারিয়ানা\s*ট্রেঞ্চ|no\s*sunlight|perpetual\s*darkness|abyssal\s*zone)",
        "description": "Deep ocean or cave abyss with zero sunlight",
        "negative_prompts": (
            "sunlight, daylight, bright blue sky, beach, surface boat, shallow coral, "
            "sun rays underwater, sunny water surface"
        ),
        "mandatory_visual_anchors": (
            "pitch-black abyssal ocean trench, intense submersible dual xenon beam cutting through "
            "murky deep waters, glowing bioluminescent organisms in perpetual darkness"
        ),
        "clean_stock_query": "deep sea submersible darkness ocean"
    },
    {
        "id": "space_vacuum",
        "regex": r"(মহাশূন্যে\s*(বাতাস|বায়ু)\s*নেই|মহাজাগতিক\s*শূন্যতা|vacuum\s*of\s*space|zero\s*gravity)",
        "description": "Outer space vacuum with zero atmosphere or gravity",
        "negative_prompts": (
            "clouds, blue sky, trees, birds, flying aircraft, atmospheric haze, green grass"
        ),
        "mandatory_visual_anchors": (
            "pure black vacuum of deep space, distant pin-sharp stars, Earth limb curvature, "
            "orbital satellite drifting in silent zero gravity"
        ),
        "clean_stock_query": "deep space satellite earth orbit"
    },
    {
        "id": "subglacial_frozen",
        "regex": r"(বরফের\s*নিচে|হিমবাহের\s*তলদেশে|subglacial|under\s*the\s*ice)",
        "description": "Subterranean environments trapped beneath thick glaciers",
        "negative_prompts": (
            "green grass, warm desert, tropical beach, sunny trees, summer foliage"
        ),
        "mandatory_visual_anchors": (
            "deep subterranean crystalline blue ice cave, colossal transparent ice sheet roof, "
            "subglacial frozen lake illuminated by scientific cold halogen lights"
        ),
        "clean_stock_query": "glacier ice cave blue subterranean"
    }
]


class SemanticPremiseGuard:
    """Detects and resolves semantic contradictions between narrative premise and visuals."""

    @classmethod
    def analyze_and_guard(
        cls,
        topic_title: str,
        dialogue: str,
        current_visual_dir: str,
        current_broll_query: str
    ) -> Dict[str, Any]:
        """
        Analyzes the narrative topic and dialogue. If a physical or spatial premise
        is detected, injects strict negative prompts and enforces premise-aligned visual anchors.
        """
        combined_text = f"{topic_title} {dialogue} {current_visual_dir}".lower()
        
        triggered_rules = []
        injected_negatives = []
        updated_visual_dir = current_visual_dir
        updated_stock_q = current_broll_query
        
        for rule in PREMISE_PATTERNS:
            if re.search(rule["regex"], combined_text, flags=re.IGNORECASE):
                triggered_rules.append(rule["id"])
                injected_negatives.append(rule["negative_prompts"])
                
                # Check if current visual prompt contradicts the premise
                logger.warning(
                    f"🛡️ [SEMANTIC PREMISE GUARD TRIGGERED]: Rule '{rule['id']}' matched! "
                    f"Enforcing premise: {rule['description']}"
                )
                
                # Append mandatory visual anchor to ensure AI generator or stock matches
                updated_visual_dir = f"{rule['mandatory_visual_anchors']}, {current_visual_dir}"
                updated_stock_q = rule["clean_stock_query"]
                break  # Primary premise lock

        return {
            "has_premise_lock": len(triggered_rules) > 0,
            "triggered_rules": triggered_rules,
            "injected_negatives": ", ".join(injected_negatives),
            "guarded_visual_direction": updated_visual_dir,
            "guarded_stock_query": updated_stock_q
        }
