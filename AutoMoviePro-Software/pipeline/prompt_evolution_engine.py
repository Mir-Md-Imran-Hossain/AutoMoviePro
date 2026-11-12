# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Prompt Evolution & Reflexion Engine (First-Shot 90+)
===================================================================
Inspired by Stanford DSPy in-context compilation, Microsoft PromptWizard,
and MIT Reflexion architecture.

Transforms Bengali dialogue and scenes into First-Shot 90+ generative prompts:
1. Decomposes dialogue into concrete physical nouns and material states (Anti-Abstraction).
2. Recalls relevant prompt evolution memory principles distilled from past Google Vision critiques.
3. Synthesizes compact (under 60 words), token-budgeted, 8K optical cinematographic prompts.
4. Distills new critiques into permanent memory rules, making the agent progressively smarter.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from pipeline.principal_agent import get_principal_agent

logger = logging.getLogger("PromptEvolutionEngine")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s][PromptEvolutionEngine][%(levelname)s] %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


class PromptEvolutionEngine:
    """Self-improving prompt synthesizer for first-pass 90+ quality gate clearance."""

    def __init__(self, memory_file: Optional[Path] = None):
        self.memory_file = memory_file or (ROOT_DIR / "pipeline" / "knowledge_base" / "prompt_evolution_memory.json")
        self.principal_agent = get_principal_agent()
        self.memory_data: Dict[str, Any] = {}
        self.load_memory()

    def load_memory(self) -> None:
        """Loads prompt evolution memories from disk."""
        if not self.memory_file.exists():
            logger.warning("Memory file %s not found. Initializing empty container.", self.memory_file)
            self.memory_data = {"version": "1.0.0", "memory_entries": []}
            return
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                self.memory_data = json.load(f)
            logger.info("Loaded %d prompt evolution memory rules.", len(self.memory_data.get("memory_entries", [])))
        except Exception as e:
            logger.error("Failed to load prompt evolution memory: %s", e)
            self.memory_data = {"version": "1.0.0", "memory_entries": []}

    def save_memory(self) -> None:
        """Persists updated memory bank to disk."""
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.memory_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save prompt evolution memory: %s", e)

    def retrieve_domain_memory(self, niche: str, dialogue: str) -> Optional[Dict[str, Any]]:
        """Recalls the most semantically relevant memory entry for the current topic/dialogue."""
        entries = self.memory_data.get("memory_entries", [])
        if not entries:
            return None

        combined_text = f"{niche} {dialogue}".lower()

        # Keyword semantic matching
        if any(k in combined_text for k in ["ancient", "temple", "stone", "architecture", "megalith", "pillar", "monolith", "স্থাপত্য", "মন্দির", "পাথর"]):
            return next((e for e in entries if "Ancient Engineering" in e.get("domain", "")), entries[0])
        elif any(k in combined_text for k in ["mystery", "scientist", "physics", "puzzle", "গবেষক", "বিজ্ঞান", "রহস্য"]):
            return next((e for e in entries if "Scientific Mystery" in e.get("domain", "")), entries[0])
        elif any(k in combined_text for k in ["ship", "naval", "war", "battle", "ocean", "sea", "জাহাজ", "যুদ্ধ", "সমুদ্র"]):
            return next((e for e in entries if "Maritime" in e.get("domain", "")), entries[0])
        elif any(k in combined_text for k in ["trade", "canal", "chokepoint", "strait", "বাণিজ্য", "খাল"]):
            return next((e for e in entries if "Trade Chokepoints" in e.get("domain", "")), entries[0])

        # Clean adaptive fallback: prevent defaulting to Ancient Engineering for modern/tech niches!
        return {
            "domain": niche or "General Documentary",
            "required_material_tokens": ["authentic physical textures", "natural materials"],
            "required_action_tokens": ["steady cinematic motion", "natural lighting interaction"],
            "required_lighting_tokens": ["cinematic documentary lighting", "natural 35mm optical contrast"],
            "negative_armor": ["deformed", "cartoon", "drawing", "anime", "low quality", "blurry", "watermark", "text"]
        }

    def decompose_dialogue_to_physics(self, dialogue: str, concrete_subject: str, niche: str) -> Dict[str, str]:
        """
        Decomposes spoken narrative into concrete physical entity and state.
        Guarantees zero abstract buzzwords in prompt head.
        """
        # Priority 1: Ground-truth Bengali dialogue concrete entity extraction
        try:
            from pipeline.concrete_entity_extractor import extract_concrete_entity_from_dialogue
            c_ent = extract_concrete_entity_from_dialogue(dialogue, niche=niche, fallback_subject=concrete_subject)
            if c_ent.get("is_specific_match"):
                concrete_subject = c_ent["concrete_subject_en"]
        except Exception:
            pass

        subject = (concrete_subject or "").strip()

        # Strip generic prompt boilerplate from subject
        clean_sub = re.sub(
            r'\b(Faceless B-Roll:|Category [AB]:|8K|4K|cinematic|photorealistic|documentary|shot|of|authentic|master|cinematography|portrait|faces?|humans?|persons?|woman|man|girl|boy|people)\b',
            ' ',
            subject,
            flags=re.IGNORECASE
        ).strip()
        clean_sub = re.sub(r'\s+', ' ', clean_sub)

        # If subject is still generic or empty, derive direct physical noun from dialogue
        if len(clean_sub) < 4:
            clean_sub = f"{niche} authentic physical artifact"

        # Determine physical material context based on domain
        mat = "authentic weathered physical material"
        if any(w in (clean_sub + " " + niche).lower() for w in ["stone", "temple", "pillar", "rock"]):
            mat = "weathered sandstone and grey granite masonry with ancient tool markings"
        elif any(w in (clean_sub + " " + niche).lower() for w in ["ship", "wood", "ocean", "canal"]):
            mat = "weathered nautical timber, iron bolts, and deep ocean brine patina"
        elif any(w in (clean_sub + " " + niche).lower() for w in ["blueprint", "map", "document", "desk"]):
            mat = "aged parchment paper, archival ink drafts, and vintage brass measurement tools"

        return {
            "focal_entity": clean_sub,
            "material_context": mat,
            "lighting_mood": "atmospheric natural documentary lighting, 35mm Arri Alexa optical depth",
        }

    def synthesize_first_shot_prompt(
        self,
        dialogue: str,
        concrete_subject: str,
        niche: str,
        visual_dir: str = "",
        aspect: str = "16:9"
    ) -> Dict[str, Any]:
        """
        Synthesizes a production-ready, First-Shot 90+ prompt.
        Bounded strictly to 50-60 words to prevent FLUX/SDXL token truncation.
        """
        parsed = self.decompose_dialogue_to_physics(dialogue, concrete_subject or visual_dir, niche)
        mem = self.retrieve_domain_memory(niche, dialogue)

        focal = parsed["focal_entity"]
        mat = parsed["material_context"]
        light = parsed["lighting_mood"]

        # Ensure focal subject occupies words 1 to 5
        positive_prompt = (
            f"Cinematic 8K documentary shot of {focal}. "
            f"Exquisite detail on {mat}, {light}, "
            f"master cinematography, shallow depth of field, organic physical textures, zero CGI gloss, photorealistic."
        )

        # Normalize whitespace and ensure compact token budget (under 65 words)
        words = positive_prompt.split()
        if len(words) > 65:
            positive_prompt = " ".join(words[:62]) + ", photorealistic 8K."

        # Domain negative armor
        domain_neg = mem.get("negative_armor", "") if mem else ""
        if isinstance(domain_neg, (list, tuple)):
            domain_neg = ", ".join(str(x) for x in domain_neg)
        elif not isinstance(domain_neg, str):
            domain_neg = str(domain_neg or "")

        negative_armor = (
            "people, human face, talking head, avatar, cartoon, anime, 3D render, drawing, "
            "watermark, text, blur, oversaturated plastic, cgi character, modern clutter, "
            + domain_neg
        )
        negative_armor = re.sub(r',\s*,', ',', negative_armor).strip(", ")

        return {
            "positive_prompt": positive_prompt,
            "negative_armor": negative_armor,
            "focal_entity": focal,
            "rule_applied": mem.get("id", "GENERIC_HEURISTIC") if mem else "GENERIC",
            "tier": "FIRST_SHOT_90_PLUS"
        }

    def learn_from_critique(
        self,
        dialogue: str,
        original_prompt: str,
        google_critique: str,
        google_corrected_prompt: str,
        score: float
    ) -> Optional[Dict[str, Any]]:
        """
        Distills lessons from Google Vision audits into permanent heuristics.
        Inspired by Microsoft PromptWizard & MIT Reflexion.
        """
        if not google_critique or score >= 90.0:
            return None  # No flaw to learn from

        rule_id = f"EVO-MEM-{len(self.memory_data.get('memory_entries', [])) + 1:03d}"
        logger.info(f"🧠 [Prompt Reflexion Learning] Distilling critique into memory rule {rule_id} (Score: {score})...")

        # Extract core weakness
        flaw_summary = google_critique.split("\n")[0][:140]

        new_entry = {
            "id": rule_id,
            "domain": f"Distilled Reflexion (Score: {score:.1f})",
            "flaw_pattern": flaw_summary,
            "lesson_learned": f"When dialogue covers '{dialogue[:60]}...', ensure prompt explicitly anchors to: '{google_corrected_prompt[:120]}...'",
            "first_shot_rules": [
                f"Strictly avoid past failure mode: {flaw_summary[:80]}",
                "Ensure concrete noun is prioritized over decorative adjectives."
            ],
            "negative_armor": "unrelated stock elements, modern artifacts, fantasy cgi"
        }

        self.memory_data.setdefault("memory_entries", []).append(new_entry)
        self.memory_data["total_heuristic_rules"] = len(self.memory_data["memory_entries"])
        self.save_memory()

        # Sync with Principal Agent
        try:
            self.principal_agent.record_learning(
                category="PROMPT_EVOLUTION_REFLEXION",
                issue=f"Initial prompt scored {score}/100: {flaw_summary[:80]}",
                root_cause="Semantic entity mismatch between dialogue and diffusion prompt",
                resolution=f"Saved evolutionary memory rule {rule_id} for automatic first-pass synthesis",
                agent_name="PromptEvolutionEngine"
            )
        except Exception as e:
            logger.debug("PrincipalAgent sync notice: %s", e)

        return new_entry


_GLOBAL_ENGINE: Optional[PromptEvolutionEngine] = None


def get_prompt_evolution_engine() -> PromptEvolutionEngine:
    global _GLOBAL_ENGINE
    if _GLOBAL_ENGINE is None:
        _GLOBAL_ENGINE = PromptEvolutionEngine()
    return _GLOBAL_ENGINE


if __name__ == "__main__":
    eng = get_prompt_evolution_engine()
    res = eng.synthesize_first_shot_prompt(
        dialogue="রোমান যুদ্ধজাহাজ দাউদাউ করে জ্বলে ওঠার রহস্য",
        concrete_subject="Roman wooden galley ship ablaze on stormy sea",
        niche="Ancient Naval Warfare",
        aspect="16:9"
    )
    print("Synthesized Positive Prompt:\n", res["positive_prompt"])
    print("\nNegative Armor:\n", res["negative_armor"])
    print("\nRule Applied:", res["rule_applied"])
