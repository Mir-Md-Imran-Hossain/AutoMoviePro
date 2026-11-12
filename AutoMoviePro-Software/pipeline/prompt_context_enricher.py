"""
AutoMovie Pro — Prompt Context Enricher & Temporal/Environmental Synchronizer
=============================================================================
Enforces strict historical era accuracy, environmental coherence, and zero
anachronism across image generation, Agnes AI generative clips, and fallback pipelines.

Extracts:
  1. Era & Historical Setting (e.g. 1600s, Ancient, Medieval, Victorian, Sci-Fi)
  2. Physical Environment (e.g. Underwater Aquatic, Stormy Ocean, Desert Dunes, High-Tech Studio)
  3. Strict Era/Environment Negative Prompts (e.g. modern cruise ships, diesel engines, electric lights)
  4. Enriched Cinematic Prompts with authentic material anchors (wooden galleon, hemp rigging, canvas sails)
  5. Autonomous Prompt Self-Healing on Vision Audit Rejection.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("PromptContextEnricher")
logger.setLevel(logging.INFO)

# =============================================================================
# DETERMINISTIC ERA & ENVIRONMENT DICTIONARIES (Zero-Latency Rule Tables)
# =============================================================================

ERA_RULES = [
    {
        "keywords": ["1600", "১৬০০", "17th century", "seventeenth century", "গ্যালিয়ন", "galleon", "age of sail", "পালতোলা"],
        "era_name": "1600s / 17th Century (Age of Discovery)",
        "is_historical": True,
        "authentic_elements": [
            "17th century historical wooden galleon ship",
            "wooden masts and authentic hemp rope rigging",
            "weathered canvas sails",
            "carved oak wood hull",
            "period-accurate sailing vessel",
            "historical maritime aesthetic",
        ],
        "strict_negatives": [
            "modern cruise ship", "luxury liner", "cruise vessel", "metal hull",
            "steel ship", "diesel engine", "smokestack", "steamship", "container ship",
            "yacht", "speedboat", "modern clothing", "sunglasses", "electric lights",
            "radar antenna", "plastic", "contemporary", "futuristic", "power lines"
        ],
    },
    {
        "keywords": ["ancient rome", "রোম", "রোমান", "roman empire", "colosseum", "গ্ল্যাডিয়েটর", "gladiator"],
        "era_name": "Ancient Rome (Classical Antiquity)",
        "is_historical": True,
        "authentic_elements": [
            "classical Roman stone architecture", "authentic Roman tunics and togas",
            "marble pillars and Roman forum", "historical antique textures"
        ],
        "strict_negatives": [
            "modern buildings", "asphalt", "cars", "electric poles", "modern glass windows",
            "contemporary clothing", "wristwatches", "smartphones", "neon lights"
        ],
    },
    {
        "keywords": ["medieval", "মধ্যযুগ", "মধ্যযুগীয়", "middle ages", "castle", "knight", "তলোয়ার", "durbar"],
        "era_name": "Medieval Era (Middle Ages)",
        "is_historical": True,
        "authentic_elements": [
            "stone castle battlements", "iron armor and chainmail", "torchlight",
            "weathered wood and stone masonry"
        ],
        "strict_negatives": [
            "modern weapons", "guns", "electric lights", "vehicles", "paved asphalt",
            "modern fabrics", "printed logos", "contemporary"
        ],
    },
    {
        "keywords": ["1800", "১৮০০", "19th century", "victorian", "ভিক্টোরিয়ান", "industrial revolution"],
        "era_name": "19th Century / Victorian Era",
        "is_historical": True,
        "authentic_elements": [
            "Victorian cobblestone streets", "gas lamps", "vintage 19th-century attire",
            "brass and iron textures"
        ],
        "strict_negatives": [
            "automobiles", "neon signs", "smartphones", "airplanes", "modern skyscrapers",
            "plastic", "contemporary fashion"
        ],
    },
]


TECH_KEYWORDS = [
    "ai", "artificial intelligence", "tech", "technology", "প্রযুক্তি", "এআই", "রোবট", "robot",
    "robotics", "software", "সফটওয়্যার", "smartphone", "স্মার্টফোন", "gadget", "গ্যাজেট",
    "computer", "কম্পিউটার", "server", "সার্ভার", "coding", "কোডিং", "hardware", "device",
    "chip", "microprocessor", "algorithm", "অ্যালগরিদম", "neural network", "বিকাশ", "ইঞ্জিন"
]

ENVIRONMENT_RULES = [
    {
        "keywords": ["সমুদ্রের নিচে", "জলের নিচে", "পানির নিচে", "underwater", "সমুদ্রের নিচের বালু", "প্রবাল", "submerged", "marine depth"],
        "env_name": "Underwater Aquatic Environment",
        "authentic_elements": [
            "deep ocean underwater setting", "aquatic caustic light refraction",
            "floating plankton and water micro-particles", "submerged seabed with marine silt",
            "deep blue and turquoise underwater depth haze"
        ],
        "strict_negatives": [
            "dry desert sand", "desert dunes", "above water sky", "clouds in blue sky",
            "sunlight on dry land", "trees", "camels", "dry ground", "indoor room"
        ],
    },
    {
        "keywords": ["ঝড়", "উত্তাল", "উত্তাল রাত", "ঝড়ো সমুদ্র", "stormy ocean", "turbulent sea", "violent waves", "ocean voyage", "সমুদ্রযাত্রা"],
        "env_name": "Stormy Ocean / Turbulent Open Sea",
        "authentic_elements": [
            "turbulent crashing ocean waves", "violent sea spray and frothing water",
            "dark stormy skies with dramatic sea mist", "cinematic turbulent water dynamics"
        ],
        "strict_negatives": [
            "calm swimming pool", "sunny calm lagoon", "dry beach", "river bank", "desert", "dry land"
        ],
    },
    {
        "keywords": ["মরুভূমি", "মরুভূমির বালু", "desert sand", "sahara", "dunes"],
        "env_name": "Desert Dunes Environment",
        "authentic_elements": [
            "golden desert sand dunes", "wind-swept sand ridges", "scorching arid heat haze"
        ],
        "strict_negatives": [
            "underwater", "ocean", "lakes", "snow", "lush green grass", "rain", "swamp"
        ],
    },
]


class PromptContextEnricher:
    """
    Analyzes narration dialogue and context tags to synthesize era-accurate,
    environment-locked prompts with mandatory negative constraints.
    """

    @classmethod
    def analyze_dialogue_context(
        cls,
        narration: str,
        niche: str = "General",
        scene_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Extracts era and environment metadata using rule tables and contextual matching.
        """
        text = (narration or "").lower()
        context_dict = scene_context or {}

        # 1. Detect Era
        detected_era = None
        for rule in ERA_RULES:
            if any(k in text for k in rule["keywords"]) or any(k in str(context_dict.get("era", "")).lower() for k in rule["keywords"]):
                detected_era = rule
                break

        # 2. Detect Environment
        detected_env = None
        for rule in ENVIRONMENT_RULES:
            if any(k in text for k in rule["keywords"]) or any(k in str(context_dict.get("environment", "")).lower() for k in rule["keywords"]):
                detected_env = rule
                break

        # 3. Detect Tech / Gadget Focus
        is_tech = (niche or "").lower() in ("technology", "tech", "gadget", "ai") or any(k in text for k in TECH_KEYWORDS)

        is_historical = detected_era["is_historical"] if detected_era else False
        era_title = detected_era["era_name"] if detected_era else "Contemporary / Unspecified"
        env_title = detected_env["env_name"] if detected_env else "Natural Contextual Setting"

        # Collect negative prompts
        negatives: List[str] = [
            "ugly", "blurry", "low quality", "deformed", "watermark", "text overlay", "bad anatomy"
        ]
        if detected_era:
            negatives.extend(detected_era["strict_negatives"])
        if detected_env:
            negatives.extend(detected_env["strict_negatives"])
        # Universal Guardrail: Strictly ban gratuitous human faces, talking heads, and random portraits
        negatives.extend([
            "human portrait", "talking head", "human face close up", "human selfie",
            "random person looking at camera", "boardroom meeting", "business people in suits",
            "corporate handshake", "empty office conference room", "meeting table", "random faces", "politicians"
        ])

        return {
            "era_name": era_title,
            "is_historical": is_historical,
            "detected_era_rule": detected_era,
            "environment_name": env_title,
            "detected_env_rule": detected_env,
            "is_tech": is_tech,
            "strict_negatives": list(dict.fromkeys(negatives)),
            "niche": niche,
        }

    @classmethod
    def enrich_prompt(
        cls,
        narration: str,
        raw_prompt: str = "",
        niche: str = "General",
        scene_context: Optional[Dict[str, Any]] = None,
        api_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Takes raw prompt / narration and enriches it with era and environmental anchors.
        Returns a rich payload with positive prompt, negative prompt, era, and environment.
        """
        analysis = cls.analyze_dialogue_context(narration, niche=niche, scene_context=scene_context)
        era_rule = analysis.get("detected_era_rule")
        env_rule = analysis.get("detected_env_rule")

        positive_segments: List[str] = []

        # 1. Subject / Core Action & Subject Lock (Faceless Object-First Mandate)
        is_tech = analysis.get("is_tech", False)
        if is_tech and not analysis.get("is_historical", False):
            positive_segments.append("product focus, modern tech, high tech gadget, sleek device engineering, zero human portraits, no random faces")
        else:
            positive_segments.append("faceless cinematic framing, focus on physical objects and authentic environment, zero human portraits, no random faces")

        if raw_prompt and raw_prompt.strip():
            positive_segments.append(raw_prompt.strip())
        else:
            if is_tech:
                positive_segments.append(f"Futuristic technology hardware and digital neural interface representing: {narration[:80]}")
            else:
                positive_segments.append(f"Cinematic scene representing: {narration[:80]}")

        # 2. Era Enforcement
        if era_rule:
            positive_segments.extend(era_rule["authentic_elements"][:3])
            positive_segments.append(f"historically accurate {era_rule['era_name']}")
            positive_segments.append("strictly period-accurate craftsmanship, zero contemporary elements")

        # 3. Environment Enforcement
        if env_rule:
            positive_segments.extend(env_rule["authentic_elements"][:3])

        # 4. Cinema & Quality Aesthetics
        positive_segments.extend([
            "dramatic cinematic lighting", "photorealistic 8k documentary photograph",
            "masterpiece composition", "highly detailed textures"
        ])

        final_positive = ", ".join(positive_segments)
        final_negative = ", ".join(analysis["strict_negatives"])

        logger.info(f"[PromptContextEnricher] Enriched prompt for Era='{analysis['era_name']}', Env='{analysis['environment_name']}'")

        return {
            "positive_prompt": final_positive,
            "negative_prompt": final_negative,
            "is_tech": is_tech,
            "era_name": analysis["era_name"],
            "is_historical": analysis["is_historical"],
            "environment_name": analysis["environment_name"],
            "strict_negatives": analysis["strict_negatives"],
            "raw_prompt": raw_prompt,
            "narration": narration,
        }

    @classmethod
    def heal_prompt_on_audit_failure(
        cls,
        current_prompt: str,
        critique: str,
        detected_anachronisms: List[str],
        detected_env_mismatches: List[str],
        narration: str = "",
        scene_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Self-healing rewrite: explicitly removes detected anachronisms, fixes environment,
        and hard-codes reinforced negative anchors.
        """
        analysis = cls.analyze_dialogue_context(narration, scene_context=scene_context)
        negatives = list(analysis["strict_negatives"])

        # Add all detected anachronisms to negative prompts
        for item in detected_anachronisms:
            cleaned_item = item.strip().lower()
            if cleaned_item and cleaned_item not in negatives:
                negatives.append(cleaned_item)

        # Build repaired positive prompt
        healed_parts: List[str] = []

        if analysis.get("detected_era_rule"):
            rule = analysis["detected_era_rule"]
            healed_parts.append(", ".join(rule["authentic_elements"]))
            healed_parts.append(f"verified {rule['era_name']} historical accuracy")

        if analysis.get("detected_env_rule"):
            env = analysis["detected_env_rule"]
            healed_parts.append(", ".join(env["authentic_elements"]))

        # Explicit exclusion in the positive prompt itself for maximum diffusion steerability
        if detected_anachronisms:
            healed_parts.append(f"strictly NO {', NO '.join(detected_anachronisms)}")
        if detected_env_mismatches:
            healed_parts.append(f"strictly NO {', NO '.join(detected_env_mismatches)}")

        healed_parts.append("cinematic hyperrealistic 8k masterpiece, authentic period textures, documentary lighting")

        final_healed_positive = ", ".join(healed_parts)
        final_healed_negative = ", ".join(negatives)

        logger.warning(
            f"[PromptContextEnricher: Self-Healing] Re-engineered prompt. "
            f"Banned: {detected_anachronisms + detected_env_mismatches}"
        )

        return {
            "healed_positive_prompt": final_healed_positive,
            "healed_negative_prompt": final_healed_negative,
            "banned_elements": detected_anachronisms + detected_env_mismatches,
            "era_name": analysis["era_name"],
            "environment_name": analysis["environment_name"],
            "critique_addressed": critique,
        }
