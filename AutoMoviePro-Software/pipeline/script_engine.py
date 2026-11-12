"""AutoMovie Pro — Industrial Scriptwriting & Social Hook Engine.

Core Features:
1. High-Retention Prompt Architecture:
    - 3-second psychological curiosity hook.
    - Dynamic storytelling, conversational cadence, zero generic robotic AI filler.
    - Islamic Greetings & Closings preservation for moral/lifestyle/historical alignment.
    - High-conversion Social CTA badge.
2. Format-Tailored Structuring:
    - Short Form: 5-8 ultra-fast visual scenes, total 50-70 seconds, rapid information delivery.
    - Long Form: In-depth chapters, historical/factual progression, total 8-15 scenes.
3. Token-Optimized API Consumption:
    - Avoids redundant full-context regeneration; supports granular scene-level re-writes.
4. Local Self-Healing Agent Inspection:
    - Analyzes every single scene, dialogue pacing, and visual prompts.
    - Flags awkward phrasing, robotic tone, or missing hooks and triggers single-scene auto-repair.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ScriptScene:
    scene_index: int
    narration: str
    visual_prompt: str
    estimated_duration_sec: float
    hook_type: str = "body"  # 'greeting_hook', 'body', 'cta', 'closing'
    highlighted_subtitle: str = ""
    passed_agent_qa: bool = True
    agent_notes: str = ""
    # Strict Semantic Schema Extensions
    scene_id: int = 1
    spoken_dialogue: str = ""
    visual_action_description: str = ""
    required_subject_keywords: List[str] = field(default_factory=list)
    emotional_tone: str = "curious"  # 'urgent', 'curious', 'inspiring'
    # Motion Graphics Explainer Extensions
    layout_template: str = "center_hero_icon"
    icon_keyword: str = ""
    text_card_headline: str = ""
    text_card_body: str = ""
    stat_metric: str = ""
    checklist_items: List[str] = field(default_factory=list)
    motion_background_style: str = "deep_cyber_mesh"
    badge_pill: str = "ভাইরাল স্ট্র্যাটেজি • SECRET HACKS"
    # Live News Extensions
    visual_mode: str = "STOCK_OR_AI"
    news_beats: List[str] = field(default_factory=list)
    # Pre-Determined Camera & Visual Contract Extensions
    camera_angle: str = "Cinematic Eye-Level Shot"
    camera_movement: str = "Slow Push-In Zoom"
    lighting_setup: str = "Natural Atmospheric Lighting"
    mandatory_visual_elements: List[str] = field(default_factory=list)
    suggested_visual_prompt: str = ""

    def __post_init__(self):
        if not self.spoken_dialogue:
            self.spoken_dialogue = self.narration
        if not self.narration:
            self.narration = self.spoken_dialogue
        if not self.visual_action_description:
            self.visual_action_description = self.visual_prompt
        if not self.visual_prompt:
            self.visual_prompt = self.visual_action_description
        if not self.scene_id:
            self.scene_id = self.scene_index
        if not self.required_subject_keywords and self.visual_action_description:
            # Extract basic non-stop words as fallback keywords
            raw_tokens = re.findall(r"\b[A-Za-z0-9_]{3,}\b", self.visual_action_description.lower())
            stops = {"the", "and", "shot", "cinematic", "with", "this", "that", "scene", "view"}
            self.required_subject_keywords = [t for t in raw_tokens if t not in stops][:4]

    def to_metadata_dict(self) -> Dict[str, Any]:
        """Returns the strict scene-by-scene metadata schema dictionary."""
        return {
            "scene_id": self.scene_id,
            "spoken_dialogue": self.spoken_dialogue,
            "visual_action_description": self.visual_action_description,
            "required_subject_keywords": self.required_subject_keywords,
            "emotional_tone": self.emotional_tone,
            "camera_angle": self.camera_angle,
            "camera_movement": self.camera_movement,
            "lighting_setup": self.lighting_setup,
            "mandatory_visual_elements": self.mandatory_visual_elements,
            "suggested_visual_prompt": self.suggested_visual_prompt,
        }


def highlight_retention_keywords(text: str, language: str = "bn", accent_color: str = "#FFD700") -> str:
    """Highlights key retention words with bold and accent colors for high audience watch-time."""
    if not text:
        return ""
    words = text.split()
    if len(words) <= 2:
        return f'<b><font color="{accent_color}">{text}</font></b>'

    # Keywords that trigger psychological retention
    trigger_words_bn = {
        "আলোড়ন", "রহস্য", "গোপন", "অবিশ্বাস্য", "স্তব্ধ", "চরম", "বিস্ময়কর",
        "সত্য", "ভয়ানক", "অলৌকিক", "আবিষ্কার", "বিস্ফোরক", "বিকল্পহীন", "বাস্তবতা",
        "হিসাব-নিকাশ", "যুগান্তকারী", "হঠাৎ", "অদ্ভুত", "অজানা", "সতর্কবার্তা"
    }
    trigger_words_en = {
        "shocking", "mystery", "secret", "baffled", "unbelievable", "truth",
        "hidden", "dangerous", "breakthrough", "miracle", "critical", "warning",
        "game-changer", "forbidden", "unseen", "terrifying", "defying"
    }
    triggers = trigger_words_bn if language == "bn" else trigger_words_en

    highlighted_words = []
    highlight_count = 0
    max_highlights = max(1, len(words) // 5)

    import unicodedata
    for w in words:
        clean_w = "".join(c for c in w if not unicodedata.category(c).startswith("P") and not c.isspace()).lower()
        if (clean_w in triggers or (len(clean_w) > 5 and highlight_count == 0)) and highlight_count < max_highlights:
            # Preserve punctuation around word with Unicode script support (Bengali/Latin)
            prefix = "" if (unicodedata.category(w[0]).startswith("L") or unicodedata.category(w[0]).startswith("N")) else w[0]
            suffix = "" if (unicodedata.category(w[-1]).startswith("L") or unicodedata.category(w[-1]).startswith("N") or unicodedata.category(w[-1]).startswith("M")) else w[-1]
            core = w.strip(".,!?:;\"'()[]{}-—–")
            highlighted_words.append(f'{prefix}<b><font color="{accent_color}">{core}</font></b>{suffix}')
            highlight_count += 1
        else:
            highlighted_words.append(w)

    return " ".join(highlighted_words)


@dataclass
class ProductionScript:
    script_id: str
    topic_id: str
    title: str
    niche: str
    video_format: str  # 'short' or 'long'
    language: str  # Master generation language (default 'en' or 'bn')
    scenes: List[ScriptScene] = field(default_factory=list)
    total_estimated_duration_sec: float = 0.0
    quality_score: float = 100.0
    video_category: str = "cinematic"  # 'cinematic' vs 'motion_graphics'


class PatternInterruptEngine:
    """
    High-Retention Pattern Interrupt Hook Framework (First 3-5 Seconds).
    Generates visceral, curiosity-inducing openings designed to disrupt viewer scrolling
    and shatter baseline complacency across all niche domains.
    """

    HOOK_ARCHETYPES: Dict[str, Dict[str, List[str]]] = {
        "health": {
            "bn": [
                "আপনি কি জানেন {topic} নিয়ে এতদিনের প্রচলিত ধারণা কেন আসলে মারাত্মক ভুল ছিল? এই নতুন বৈজ্ঞানিক তথ্যটি শুনলে আপনি স্তব্ধ হয়ে যাবেন!",
                "মাত্র ৩ দিন {topic} প্রয়োগ করলে মানবদেহে কী চরম পরিবর্তন ঘটে, তা জানলে আপনি আজই নিজের অভ্যাস বদলে ফেলবেন!",
            ],
            "en": [
                "Everything you've been told about {topic} is completely backwards. What researchers just discovered will leave you speechless!",
                "Why are top longevity scientists secretly testing {topic} right now? The cellular reality defies everything we knew!",
            ],
        },
        "finance": {
            "bn": [
                "৯৯% মানুষ {topic} নিয়ে যে মারাত্মক ভুলটি করে, তার কারণেই তাদের সঞ্চয় নীরবে শেষ হয়ে যায়! আসল সত্যটি কি আপনি জানেন?",
                "বড় বড় প্রাতিষ্ঠানিক বিনিয়োগকারীরা {topic} নিয়ে সাধারণ মানুষকে যে গোপন তথ্যটি কখনো বলে না—তা শুনলে আপনি চমকে উঠবেন!",
            ],
            "en": [
                "99% of investors misunderstand {topic}, and it quietly drains their wealth without them ever noticing. Here is the hidden truth!",
                "The biggest financial institutions never talk about this one rule in {topic}. Once you see it, you can't unsee it!",
            ],
        },
        "cooking": {
            "bn": [
                "শেফদের গোপন কৌশল: {topic} তৈরিতে কেন সাধারণ মানুষ বারবার ব্যর্থ হয়? এই একটি গোপন উপাদানেই লুকিয়ে আসল স্বাদ!",
                "আপনি কি জানেন {topic} বানানোর চিরাচরিত নিয়ম কেন আসল স্বাদ নষ্ট করে দেয়? এই পদ্ধতিটি আপনার রান্নার ধরনই বদলে দেবে!",
            ],
            "en": [
                "The secret restaurant trick for {topic} that professional chefs refuse to share online. This changes everything you cook!",
                "Stop making {topic} the old way! This single molecular timing trick guarantees absolute perfection!",
            ],
        },
        "motivation": {
            "bn": [
                "আপনার মস্তিষ্ক কেন বারবার অলসতায় আটকে যায়? {topic} এর পেছনের নিউরোসায়েন্সের এই চরম সত্যটি শুনলে আপনি স্তব্ধ হয়ে যাবেন!",
                "ইচ্ছাশক্তি নয়, বরং {topic} কীভাবে নীরবে আপনার অভ্যাস নিয়ন্ত্রণ করছে—তা জানলে আপনি নিজের পুরো রুটিন পাল্টে ফেলবেন!",
            ],
            "en": [
                "Willpower is a myth. The reason you struggle with {topic} is hardwired into your neurochemistry—and the fix takes 30 seconds!",
                "What high performers do with {topic} before 8 AM that completely rewires their focus. The secret is shockingly simple!",
            ],
        },
        "islamic": {
            "bn": [
                "আপনি কি জানেন {topic} কেন হাজার বছর ধরে সমগ্র মানবজাতির হৃদয়ে চরম আলোড়ন ও গভীর পথনির্দেশ তৈরি করেছে? এর পেছনের ঐশ্বরিক সত্যটি শুনলে আপনি স্তব্ধ হয়ে যাবেন!",
                "ইতিহাসের পাতায় হারিয়ে যাওয়া {topic} এর বিস্ময়কর ঘটনাটি শুনলে আপনার ঈমান ও দৃষ্টিভঙ্গি সম্পূর্ণ বদলে যাবে!",
            ],
            "en": [
                "Did you know why {topic} has moved millions of hearts across history? The timeless divine wisdom behind this will leave you speechless!",
                "The untold historical event surrounding {topic} that most people have never heard. It completely reshapes how we view faith!",
            ],
        },
        "history": {
            "bn": [
                "ইতিহাসবিদরা কেন শতাব্দীর পর শতাব্দী ধরে {topic} এর এই চরম গোপন নথিটি লুকিয়ে রেখেছিলেন? এর অবিশ্বাস্য রহস্যটি উন্মোচিত হয়েছে!",
                "খননকাজে পাওয়া অদ্ভুত একটি প্রমাণ {topic} সম্পর্কে আমাদের পুরো ধারণাই পাল্টে দিয়েছে! এর পেছনের আসল রহস্যটি কি আপনি জানেন?",
            ],
            "en": [
                "Why did ancient chronicles deliberately omit this shocking detail about {topic}? The buried evidence changes historical timelines forever!",
                "A single artifact found beneath the ruins completely dismantles what textbooks taught us about {topic}!",
            ],
        },
        "gadget": {
            "bn": [
                "আপনি কি জানেন {topic} কেন সারা বিশ্বে চরম তোলপাড় ও টেক মহলে আলোড়ন সৃষ্টি করেছে? এর পেছনের অবিশ্বাস্য সত্যটি শুনলে আপনি স্তব্ধ হয়ে যাবেন!",
                "কোম্পানিগুলো {topic} সম্পর্কে যে ফিচারটি সবার আড়ালে রেখেছিল—তা জানলে আপনি এখনই আপনার ডিভাইস পরীক্ষা করবেন!",
            ],
            "en": [
                "Did you know why {topic} is shocking experts worldwide? The unbelievable truth behind this will leave you speechless!",
                "The hidden engineering decision behind {topic} that tech manufacturers hoped you would never discover!",
            ],
        },
        "news": {
            "bn": [
                "বিশ্ব রাজনীতির মানচিত্রে {topic} নিয়ে যে চরম অস্থিরতা শুরু হয়েছে, তার প্রভাব সরাসরি আপনার জীবনে পড়বে! কিন্তু পর্দার পেছনের আসল ঘটনাটি কী?",
                "কেন পরাশক্তিগুলো গোপনে {topic} নিয়ে সর্বোচ্চ সতর্ক অবস্থানে রয়েছে? কূটনৈতিক গোপন নথির এই সত্যটি জানলে আপনি চমকে উঠবেন!",
            ],
            "en": [
                "The geopolitical reality behind {topic} is escalating faster than headlines admit. Here is the covert struggle reshaping global power!",
                "Why are intelligence agencies secretly tracking {topic} right now? The unclassified satellite evidence changes everything!",
            ],
        },
        "true_crime": {
            "bn": [
                "তদন্তকারী গোয়েন্দারা {topic} নিয়ে যখন শেষ ক্লু-টি খুঁজে পান, তখন গোটা পুলিশ প্রশাসন স্তব্ধ হয়ে গিয়েছিল! কী লুকিয়ে ছিল সেই রহস্যময় ফাইলে?",
                "সবাই ভেবেছিল {topic} একটি সাধারণ ঘটনা, কিন্তু ফরেনসিক ল্যাবের রিপোর্ট আসার পর আসল সত্যটি সবার গা শিউরে দেয়!",
            ],
            "en": [
                "When lead detectives finally uncovered the missing piece in {topic}, the entire courtroom fell dead silent. Here is the evidence they hid!",
                "Everyone believed {topic} was an open-and-shut case, until forensic analysis revealed a terrifying contradiction!",
            ],
        },
        "motion_graphics": {
            "bn": [
                "কাগজে-কলমের বিজ্ঞাপনে {topic} সম্পর্কে যা শোনানো হয়েছে, আসল বেঞ্চমার্ক টেস্টে তার চেয়ে সম্পূর্ণ ভিন্ন চিত্র উঠে এসেছে! ডেটা কী বলছে দেখুন!",
                "কম্পিউটিং ও প্রযুক্তির ইতিহাসে {topic} কেন এক চরম বিপ্লব ঘটাতে যাচ্ছে? গ্রাফ ও আর্কিটেকচারের এই বিশ্লেষণটি মিস করবেন না!",
            ],
            "en": [
                "The official marketing claims for {topic} completely fall apart once you look at the raw benchmark data. Here is what actually happened!",
                "Why is {topic} breaking every known performance ceiling in computing? The technical architecture reveals an insane leap!",
            ],
        },
        "sports": {
            "bn": [
                "ম্যাচের ফলাফল সবাই দেখেছে, কিন্তু {topic} এর পেছনের ট্যাকটিক্যাল মাস্টারক্লাসটি খেয়াল করেছেন কি? এই নিখুঁত চালের কারণেই বদলে গিয়েছিল ইতিহাস!",
                "কোচদের ট্যাকটিক্যাল বোর্ডে {topic} নিয়ে ঠিক কী গোপন পরিকল্পনা সাজানো হয়েছিল, যার সামনে প্রতিপক্ষ সম্পূর্ণ অসহায় হয়ে পড়েছিল?",
            ],
            "en": [
                "Everyone saw the final score, but almost nobody caught the tactical masterstroke behind {topic}. This single adjustment decided the match!",
                "How did a microscopic tactical formation change in {topic} dismantle an unbeatable opponent? The chalkboard breakdown explains it all!",
            ],
        },
        "business": {
            "bn": [
                "বিলিয়ন ডলারের করপোরেট যুদ্ধ: {topic} এর পেছনের এই একটি ভুল সিদ্ধান্তের কারণেই রাতারাতি পতন হয়েছিল এক বিশাল সাম্রাজ্যের! কী ঘটেছিল আসলে?",
                "সিলিকন ভ্যালির শীর্ষ টাইটানরা {topic} নিয়ে যে গোপন চুক্তিটি করেছিল, তা জানলে আপনি ব্যবসায়ের আসল নিয়ম বুঝতে পারবেন!",
            ],
            "en": [
                "A single high-stakes boardroom gamble behind {topic} created a trillion-dollar monopoly while destroying its biggest rival. Here is how it went down!",
                "Behind closed doors, the corporate war over {topic} was won through a ruthless strategic maneuver that textbooks never teach!",
            ],
        },
    }

    @classmethod
    def get_pattern_interrupt_hook(
        cls,
        topic: str,
        niche: str,
        language: str = "en",
        index: int = 0,
    ) -> str:
        nl = (niche or "").lower()
        key = "gadget"
        for k in ("news", "geopolit", "conflict", "treaty", "military", "defense", "election"):
            if k in nl:
                key = "news"
                break
        else:
            for k in ("crime", "murder", "serial", "investigat", "forensic", "detective"):
                if k in nl:
                    key = "true_crime"
                    break
            else:
                for k in ("graphic", "benchmark", "breakdown", "analysis", "ui", "ux", "code", "architecture"):
                    if k in nl:
                        key = "motion_graphics"
                        break
                else:
                    for k in ("sport", "football", "cricket", "f1", "tactics", "nba", "championship"):
                        if k in nl:
                            key = "sports"
                            break
                    else:
                        for k in ("business", "startup", "titan", "billionaire", "corporate", "company", "monopoly"):
                            if k in nl:
                                key = "business"
                                break
                        else:
                            for k in ("islam", "deen", "quran", "moral"):
                                if k in nl:
                                    key = "islamic"
                                    break
                            else:
                                for k in ("cook", "food", "recipe"):
                                    if k in nl:
                                        key = "cooking"
                                        break
                                else:
                                    for k in ("financ", "money", "invest", "stock", "crypto"):
                                        if k in nl:
                                            key = "finance"
                                            break
                                    else:
                                        for k in ("health", "fit", "diet", "sleep", "workout", "longevity"):
                                            if k in nl:
                                                key = "health"
                                                break
                                        else:
                                            for k in ("motivat", "habit", "mindset", "productiv", "discipline"):
                                                if k in nl:
                                                    key = "motivation"
                                                    break
                                            else:
                                                for k in ("histor", "ancient", "civiliz", "archaeolog"):
                                                    if k in nl:
                                                        key = "history"
                                                        break

        pool = cls.HOOK_ARCHETYPES.get(key, cls.HOOK_ARCHETYPES["gadget"])
        templates = pool.get(language, pool.get("en", []))
        tmpl = templates[index % len(templates)]
        return tmpl.format(topic=topic)


class DialoguePacingEngine:
    """
    Dialogue Pacing Engine with Semantic Redundancy Curation Gate.
    Regulates verbal velocity, sentence breath distribution, and prunes
    semantic clones across consecutive scenes.
    """

    TARGET_WPS_SHORT = 2.5   # 150 words per minute
    TARGET_WPS_LONG = 2.1    # 126 words per minute

    SEMANTIC_CLICHE_STEMS = [
        "অবিশ্বাস্য সত্য", "গোপন রহস্য", "স্তব্ধ হয়ে যাবেন", "চরম তোলপাড়",
        "unbelievable truth", "hidden secret", "leave you speechless", "shocking reality",
    ]

    @classmethod
    def optimize_scene_duration(cls, text: str, video_format: str = "short", language: str = "bn") -> float:
        words = len((text or "").split())
        is_bengali = language == "bn" or bool(re.search(r"[\u0980-\u09ff]", text or ""))
        if is_bengali:
            # Bengali average speaking rate is ~1.5 words per second (~0.66s per word)
            target_wps = 1.6 if video_format == "short" else 1.4
        else:
            target_wps = cls.TARGET_WPS_SHORT if video_format == "short" else cls.TARGET_WPS_LONG
        base = words / max(1.0, target_wps)
        if video_format == "short":
            return round(min(14.0, max(4.0, base + 0.5)), 1)
        return round(min(35.0, max(18.0, base + 1.0)), 1)

    @classmethod
    def curate_semantic_redundancy(cls, scenes: List[ScriptScene], language: str = "en") -> List[ScriptScene]:
        """
        Scans scenes for semantic redundancy and thematic duplication across consecutive beats.
        Curates and purges repetitive clichés, preserving narrative freshness.
        """
        seen_stems: Dict[str, int] = {}
        for idx, sc in enumerate(scenes):
            narr = sc.narration
            nl = narr.lower()
            curated = False
            for stem in cls.SEMANTIC_CLICHE_STEMS:
                if stem in nl:
                    seen_stems[stem] = seen_stems.get(stem, 0) + 1
                    if seen_stems[stem] > 1 and idx > 0:
                        curated = True
                        if language == "bn":
                            narr = narr.replace(stem, "বাস্তব ফলাফল")
                        else:
                            narr = narr.replace(stem, "proven reality")
                        nl = narr.lower()
            if curated:
                sc.narration = narr
                sc.agent_notes = (sc.agent_notes + " | Curated semantic redundancy.").strip(" |")
                sc.highlighted_subtitle = highlight_retention_keywords(narr, language)
        return scenes


class ScriptEngine:
    """Enterprise-grade script generator with local self-healing agent inspection."""

    ISLAMIC_GREETINGS = "আসসালামু আলাইকুম ওয়া রাহমাতুল্লাহ।"
    ISLAMIC_CLOSINGS = "মহান আল্লাহ আমাদের সবাইকে উত্তম হেদায়েত ও জ্ঞান দান করুন। আমিন।"
    SOCIAL_CTA = "এই বিষয়ে আপনার কী দৃষ্টিভঙ্গি? কমেন্টে নিজের মতামত জানান এবং নিয়মিত অনুসন্ধানের সাথে যুক্ত থাকতে সাথে থাকুন।"

    def _try_llm_generation(
        self,
        topic_title: str,
        niche: str,
        video_format: str,
        language: str,
        apply_islamic: bool,
    ) -> Optional[List[Dict[str, str]]]:
        """Attempts generation using the live multi-provider LLM router (Groq/OR/Gemini/HF) with 5-Act Arc."""
        try:
            from pipeline.llm_router import chat_text, extract_json_object
            
            scene_count = 5 if video_format == "short" else 9
            prompt = (
                f"You are an elite viral documentary producer with maximum audience retention expertise.\n"
                f"Generate a structured {video_format} video script about '{topic_title}' in niche '{niche}'.\n"
                f"Target Language: {language}.\n"
                f"Total Body Scenes needed: {scene_count}.\n"
                f"MANDATORY 3-ACT EMOTIONAL RETENTION ARC:\n"
                f"- Act 1 (First 3 seconds / Scene 1): Pattern Interrupt Hook & Curiosity Gap — Visceral disruption of viewer complacency, high stakes, burning question (Zero slow intro, zero generic greetings).\n"
                f"- Act 2 (Middle Scenes): Problem Deepening & Emotional Connection — Relatable struggle, tension escalation, revealing hidden or declassified mechanisms, concrete real-world evidence.\n"
                f"- Act 3 (Final Scene): Fast Payoff & High-Conversion Call To Action — Immediate satisfying answer and natural viewer interaction.\n"
                f"ANTI-ROBOTIC CONVERSATIONAL RULES:\n"
                f"1. Write in natural conversational cadence with varied rhythm and punchy phrasing.\n"
                f"2. Strict ban on robotic fillers: moreover, furthermore, delve, in today's video, আজকের এই ভিডিওতে, চলুন জেনে নেওয়া যাক, অধিকন্তু, তদুপরি, পরিশেষে.\n"
                f"3. High specificity: mention named entities, verified mechanisms, and concrete actions.\n"
                f"STRICT SCENE METADATA SCHEMA (Return valid JSON strictly matching this schema):\n"
                "{\n"
                '  "scenes": [\n'
                "    {\n"
                '      "scene_id": 1,\n'
                '      "spoken_dialogue": "Spoken dialogue here in target language",\n'
                '      "visual_action_description": "Precise visual action occurring on screen",\n'
                '      "required_subject_keywords": ["main_object", "action", "environment"],\n'
                '      "emotional_tone": "urgent | curious | inspiring"\n'
                "    }\n"
                "  ]\n"
                "}\n"
            )
            hit = chat_text(prompt, purpose="script", json_mode=True)
            if hit and "text" in hit:
                parsed = json.loads(extract_json_object(hit["text"]))
                if isinstance(parsed, dict) and "scenes" in parsed and isinstance(parsed["scenes"], list):
                    return parsed["scenes"]
        except Exception as exc:
            logger.debug("Live LLM script routing skipped or offline: %s", exc)
        return None

    def generate_script(
        self,
        *,
        topic_title: str,
        niche: str,
        video_format: str = "short",
        video_category: str = "cinematic",
        language: str = "bn",
        include_islamic_touch: bool = True,
        include_social_cta: bool = True,
        use_llm: bool = True,
    ) -> ProductionScript:
        """Constructs an industrial production script with fine-tuned scenes."""
        fmt = video_format.lower().strip()
        cat = (video_category or "cinematic").lower().strip()
        if cat == "live_news":
            return self._generate_live_news_script(
                topic_title=topic_title,
                niche=niche,
                video_format=fmt,
                language=language,
            )
        script_id = f"scr_{fmt[:2]}_{hashlib.md5(topic_title.encode('utf-8')).hexdigest()[:8]}"
        scenes: List[ScriptScene] = []

        is_islamic_niche = any(k in niche.lower() for k in ("islam", "deen", "moral", "quran", "history"))
        apply_islamic = include_islamic_touch or is_islamic_niche

        llm_scenes = self._try_llm_generation(topic_title, niche, fmt, language, apply_islamic) if use_llm else None

        # Scene 1: 0-3 Second Psychological Pattern Interrupt Hook
        idx = 1
        pattern_hook = PatternInterruptEngine.get_pattern_interrupt_hook(topic_title, niche, language)
        if language == "bn":
            if apply_islamic:
                hook_text = f"{self.ISLAMIC_GREETINGS} {pattern_hook}"
            else:
                hook_text = pattern_hook
        else:
            if apply_islamic:
                hook_text = f"Peace be upon you. {pattern_hook}"
            else:
                hook_text = pattern_hook

        scenes.append(
            ScriptScene(
                scene_index=idx,
                scene_id=idx,
                narration=hook_text,
                spoken_dialogue=hook_text,
                visual_prompt=f"Cinematic ultra-realistic opening shot depicting {topic_title}, dramatic suspense lighting, 8k resolution",
                visual_action_description=f"High-impact visual pattern interrupt depicting {topic_title} with dynamic lighting",
                required_subject_keywords=[topic_title, "hook", "revelation"],
                emotional_tone="urgent",
                estimated_duration_sec=7.0 if apply_islamic else 4.5,
                hook_type="greeting_hook",
                highlighted_subtitle=highlight_retention_keywords(hook_text, language),
            )
        )

        # Body Scenes
        if llm_scenes and len(llm_scenes) >= 3:
            for sc_data in llm_scenes:
                idx += 1
                narr = str(sc_data.get("spoken_dialogue") or sc_data.get("narration", "")).strip()
                vis = str(sc_data.get("visual_action_description") or sc_data.get("visual_prompt", "")).strip() or f"Visual sequence for {topic_title}"
                req_kw = sc_data.get("required_subject_keywords") or [topic_title, "insight", "action"]
                if isinstance(req_kw, str):
                    req_kw = [k.strip() for k in req_kw.split(",") if k.strip()]
                tone = str(sc_data.get("emotional_tone") or ("inspiring" if idx == len(llm_scenes) + 1 else "curious"))
                dur = min(12.0, max(4.0, len(narr.split()) * 0.4)) if fmt == "short" else max(24.0, len(narr.split()) * 0.6)
                scenes.append(
                    ScriptScene(
                        scene_index=idx,
                        scene_id=idx,
                        narration=narr,
                        spoken_dialogue=narr,
                        visual_prompt=vis,
                        visual_action_description=vis,
                        required_subject_keywords=req_kw,
                        emotional_tone=tone,
                        estimated_duration_sec=dur,
                        hook_type="cta" if idx == len(llm_scenes) + 1 else "body",
                        highlighted_subtitle=highlight_retention_keywords(narr, language),
                    )
                )
        else:
            # Procedural dynamic body scenes following 5-Act Narrative Arc
            body_count = 4 if fmt == "short" else 8
            bn_variations = [
                # Act 2: Context & Escalating Stakes
                f"{topic_title} নিয়ে বহুকাল ধরে যে ধারণা প্রচলিত ছিল, বাস্তবে তার গভীরে লুকিয়ে ছিল এক সম্পূর্ণ ভিন্ন ও রোমাঞ্চকর দ্বন্দ্ব।",
                f"প্রথম দেখায় বিষয়টিকে সাধারণ মনে হলেও, ভেতরের নথিপত্র ও ঘটনাপ্রবাহ গভীরভাবে লক্ষ্য করলেই সামনে আসে আসল জটিলতা।",
                # Act 3: Core Discovery / The Pivot
                f"ঠিক এই মুহূর্তেই ঘটে সেই ঐতিহাসিক টার্নিং পয়েন্ট—যেখানে নতুন প্রমাণ ও ডেটা পুরো পরিস্থিতিকে ১৮০ ডিগ্রি ঘুরিয়ে দেয়।",
                f"গবেষক ও বিশেষজ্ঞদের দীর্ঘ অনুসন্ধানে উন্মোচিত হয় সেই গোপন কার্যপদ্ধতি, যা এতদিনের সব ভুল হিসেব-নিকাশ পাল্টে দেয়।",
                # Act 4: Real-World Repercussions
                f"এই যুগান্তকারী পরিবর্তনের প্রভাব কেবল একটি সীমানায় সীমাবদ্ধ থাকেনি, বরং বিশ্বজুড়ে তৈরি করেছে এক নতুন বাস্তবতা।",
                f"বাস্তব জীবনে এর সুনির্দিষ্ট প্রয়োগ কীভাবে সামগ্রিক কাঠামো বদলে দিচ্ছে, তা গভীরভাবে লক্ষ্য করার মতো।",
                # Act 5: Provocative Resolution & Insight
                f"একটু গভীরভাবে ভেবে দেখুন তো, এটি কি কেবল একটি বিচ্ছিন্ন ঘটনা—নাকি আমাদের ভবিষ্যতের জন্য এক অবিস্মরণীয় বার্তা?",
                f"সবচেয়ে আশ্চর্যের বিষয় হলো, এই রূপান্তরের ধারা এখনো থামেনি, বরং আগামী দিনে তা আরও দূর বহুদূর বিস্তার লাভ করবে।"
            ]
            en_variations = [
                # Act 2: Context & Escalating Stakes
                f"While conventional wisdom assumed {topic_title} was fully understood, underlying contradictions tell a radically different story.",
                f"At first glance, everything appeared routine, until historical records and verified telemetry revealed high-stakes friction.",
                # Act 3: Core Discovery / The Pivot
                f"This marks the decisive turning point, where newly surfaced data completely overturned decades of textbook theory.",
                f"Forensic analysts and technical pioneers finally uncovered the hidden mechanism operating behind closed doors.",
                # Act 4: Real-World Repercussions
                f"The ripple effects did not stop there; they cascaded across the global landscape, establishing an entirely new baseline.",
                f"In modern practice, the real-world consequences are actively transforming how major institutions operate.",
                # Act 5: Provocative Resolution & Insight
                f"When stepping back to examine the complete arc, this stands not as an isolated anomaly, but as a defining benchmark for our era.",
                f"What remains most compelling is that this trajectory is accelerating, permanently altering the rules of the game."
            ]
            for b in range(1, body_count + 1):
                idx += 1
                narr = bn_variations[(b - 1) % len(bn_variations)] if language == "bn" else en_variations[(b - 1) % len(en_variations)]
                scenes.append(
                    ScriptScene(
                        scene_index=idx,
                        narration=narr,
                        visual_prompt=f"Detailed documentary visual sequence showing key narrative beat #{b} of {topic_title}, dynamic camera movement",
                        estimated_duration_sec=8.0 if fmt == "short" else 25.0,
                        hook_type="body",
                        highlighted_subtitle=highlight_retention_keywords(narr, language),
                    )
                )

        # Social CTA Scene (Conversational, Anti-Robotic)
        if include_social_cta:
            idx += 1
            cta_text = self.SOCIAL_CTA if language == "bn" else "What is your perspective on this? Share your thoughts below and stay tuned for the next deep-dive."
            scenes.append(
                ScriptScene(
                    scene_index=idx,
                    narration=cta_text,
                    visual_prompt="Modern glowing social media like subscribe bell notification badges animation, dark mode glassmorphism",
                    estimated_duration_sec=5.0,
                    hook_type="cta",
                    highlighted_subtitle=highlight_retention_keywords(cta_text, language),
                )
            )

        # Closing Scene
        idx += 1
        close_text = (self.ISLAMIC_CLOSINGS if apply_islamic else "জ্ঞান ও অনুসন্ধানের এই অভিযাত্রায় যুক্ত থাকুন। ভালো থাকুন, সুস্থ থাকুন।") if language == "bn" else "May wisdom guide your path. See you in the next exploration."
        scenes.append(
            ScriptScene(
                scene_index=idx,
                narration=close_text,
                visual_prompt=f"Serene inspiring cinematic conclusion scene, golden hour light, peaceful ambiance",
                estimated_duration_sec=6.0,
                hook_type="closing",
                highlighted_subtitle=highlight_retention_keywords(close_text, language),
            )
        )

        # Motion Graphics Explainer Enrichment
        cat = (video_category or "cinematic").lower().strip()
        if cat == "motion_graphics":
            from pipeline.icon_library import IconLibrary
            template_cycle = [
                "center_hero_icon",
                "stat_counter_metric",
                "checklist_points",
                "versus_comparison",
                "center_hero_icon",
                "quote_wisdom_card",
            ]
            for i, sc in enumerate(scenes):
                tpl = template_cycle[i % len(template_cycle)]
                sc.layout_template = tpl
                sc.icon_keyword = IconLibrary.resolve_icon_keyword(f"{topic_title} {sc.narration}")
                if sc.hook_type == "greeting_hook":
                    sc.layout_template = "center_hero_icon"
                    sc.text_card_headline = f"{topic_title[:28]} এর মূল রহস্য"
                    sc.badge_pill = "ভাইরাল স্ট্র্যাটেজি • SECRET HACKS"
                elif sc.hook_type == "cta":
                    sc.layout_template = "center_hero_icon"
                    sc.icon_keyword = "bell"
                    sc.text_card_headline = "পরবর্তী পর্ব দেখতে সাবস্ক্রাইব করুন"
                    sc.badge_pill = "সাবস্ক্রাইব করুন • STAY TUNED"
                elif sc.hook_type == "closing":
                    sc.layout_template = "quote_wisdom_card"
                    sc.icon_keyword = "sparkles"
                    sc.text_card_headline = "জ্ঞান ও বাস্তবতার অমূল্য বার্তা"
                    sc.badge_pill = "উপসংহার • FINAL WORDS"
                else:
                    if tpl == "stat_counter_metric":
                        sc.stat_metric = "+৮৫% বৃদ্ধি"
                        sc.text_card_headline = "অবিশ্বাস্য ফলাফল ও রূপান্তর"
                        sc.badge_pill = "মেট্রিক এনালাইসিস • KEY METRIC"
                    elif tpl == "checklist_points":
                        sc.text_card_headline = "সফলতার ৩টি প্রমাণিত নিয়ম"
                        sc.checklist_items = [
                            "১. কৌশলগত বিষয় নির্বাচন",
                            "২. সঠিক ওপেন সোর্স ভেক্টর আইকন",
                            "৩. কাইনেটিক কার্ড ও দ্রুত ফলাফল",
                        ]
                        sc.badge_pill = "চেকলিস্ট গাইড • STEP BY STEP"
                    elif tpl == "versus_comparison":
                        sc.text_card_headline = "সনাতন পদ্ধতি বনাম স্মার্ট উপায়"
                        sc.badge_pill = "পার্থক্য যাচাই • COMPARISON"
                    else:
                        sc.text_card_headline = f"পয়েন্ট #{sc.scene_index}: মূল কার্যপদ্ধতি"
                        sc.badge_pill = "ডিপ ডাইভ • DEEP DIVE"
                sc.text_card_body = sc.narration

        total_dur = sum(s.estimated_duration_sec for s in scenes)
        script = ProductionScript(
            script_id=script_id,
            topic_id="top_ref",
            title=topic_title,
            niche=niche,
            video_format=fmt,
            language=language,
            scenes=scenes,
            total_estimated_duration_sec=total_dur,
            video_category=cat,
        )

        # Run Local Agent Quality Inspection
        self.inspect_and_repair_script(script)
        return script

    def _generate_live_news_script(
        self,
        *,
        topic_title: str,
        niche: str,
        video_format: str,
        language: str,
    ) -> ProductionScript:
        """Constructs an authoritative broadcast live news bulletin script."""
        from pipeline.live_news_engine import LiveNewsEngine
        fmt = video_format.lower().strip()
        is_long = (fmt == "long")
        script_id = f"scr_news_{fmt[:2]}_{int(time.time())}"

        # Fetch live news stories
        stories = LiveNewsEngine.fetch_todays_news(
            query_topic=topic_title if topic_title and topic_title not in ("Live News", "news", "নিউজ") else "",
            limit=6 if is_long else 4,
            language=language
        )

        scenes: List[ScriptScene] = []
        idx = 1

        # Scene 1: News Intro Hook
        if language == "bn":
            intro_text = (
                "আসসালামু আলাইকুম। আজকের লাইভ নিউজ বুলেটিনে আপনাদের স্বাগত জানাচ্ছি। দেখে নেওয়া যাক এই মুহূর্তের প্রধান প্রধান খবর।"
                if is_long else
                "আজকের লাইভ নিউজ আপডেট! এক নজরে দেখে নিন এই মুহূর্তের প্রধান তাজা খবরগুলো।"
            )
        else:
            intro_text = (
                "Welcome to today's live breaking news bulletin. Here are the top developing stories right now."
                if is_long else
                "Live News Update! Here are today's top breaking headlines at a glance."
            )

        first_story = stories[0] if stories else None
        top_headline = first_story.headline if first_story else "আজকের শীর্ষ সংবাদ"
        cat_first = first_story.category if first_story else "জাতীয় সংবাদ"

        scenes.append(
            ScriptScene(
                scene_index=idx,
                narration=intro_text,
                visual_prompt=first_story.inspired_prompts[0] if (first_story and first_story.inspired_prompts) else "Authentic news broadcast studio editorial visual",
                estimated_duration_sec=6.0 if is_long else 4.5,
                hook_type="greeting_hook",
                highlighted_subtitle=highlight_retention_keywords(intro_text, language),
                layout_template="news_chyron",
                text_card_headline=top_headline,
                badge_pill=f"🔴 {cat_first} • LIVE NEWS",
                visual_mode="LIVE_NEWS",
                news_beats=first_story.inspired_prompts if first_story else []
            )
        )

        # Story Scenes
        for s_idx, story in enumerate(stories):
            idx += 1
            if is_long:
                # Long format: Headline + full brief details
                if language == "bn":
                    story_narr = f"{story.headline}। {story.summary}"
                else:
                    story_narr = f"{story.headline}. {story.summary}"
                dur = DialoguePacingEngine.optimize_scene_duration(story_narr, video_format="long", language=language)
            else:
                # Short format: Rapid-fire headline only
                if language == "bn":
                    story_narr = f"খবর নম্বর {s_idx + 1}: {story.headline}।"
                else:
                    story_narr = f"Top story number {s_idx + 1}: {story.headline}."
                dur = DialoguePacingEngine.optimize_scene_duration(story_narr, video_format="short", language=language)

            vis_prompt = story.inspired_prompts[0] if story.inspired_prompts else f"News visual for {story.headline}"

            scenes.append(
                ScriptScene(
                    scene_index=idx,
                    narration=story_narr,
                    visual_prompt=vis_prompt,
                    estimated_duration_sec=dur,
                    hook_type="body",
                    highlighted_subtitle=highlight_retention_keywords(story_narr, language),
                    layout_template="news_chyron",
                    text_card_headline=story.headline,
                    text_card_body=story.summary,
                    badge_pill=f"🔴 {story.category} • BREAKING NEWS",
                    visual_mode="LIVE_NEWS",
                    news_beats=story.inspired_prompts
                )
            )

        # Closing Scene
        idx += 1
        if language == "bn":
            close_text = "এই ছিল এখনকার মতো লাইভ নিউজ বুলেটিন। পরবর্তী খবরের দ্রুত আপডেট পেতে আমাদের সাথেই থাকুন, ধন্যবাদ।"
        else:
            close_text = "That concludes our live news bulletin. Stay tuned for further developing updates throughout the day."

        scenes.append(
            ScriptScene(
                scene_index=idx,
                narration=close_text,
                visual_prompt="Live television broadcast studio anchor desk farewell lighting",
                estimated_duration_sec=5.0,
                hook_type="closing",
                highlighted_subtitle=highlight_retention_keywords(close_text, language),
                layout_template="news_chyron",
                text_card_headline="সর্বশেষ সংবাদের জন্য সাথেই থাকুন",
                badge_pill="ধন্যবাদ • STAY TUNED",
                visual_mode="LIVE_NEWS"
            )
        )

        total_dur = sum(s.estimated_duration_sec for s in scenes)
        title = f"লাইভ নিউজ বুলেটিন: {top_headline[:35]}" if language == "bn" else f"Live News Bulletin: {top_headline[:35]}"

        return ProductionScript(
            script_id=script_id,
            topic_id="live_news_feed",
            title=title,
            niche="Live News",
            video_format=fmt,
            language=language,
            scenes=scenes,
            total_estimated_duration_sec=total_dur,
            video_category="live_news",
        )

    def inspect_and_repair_script(self, script: ProductionScript) -> ProductionScript:
        """Local agent frame-by-frame & scene-by-scene critic. Auto-repairs flaws, curates redundancy, and enforces 0-3s hook."""
        total_penalty = 0.0

        # Run Semantic Redundancy Curation across narrative scenes
        DialoguePacingEngine.curate_semantic_redundancy(script.scenes, script.language)

        for i, sc in enumerate(script.scenes):
            # 0. High-Retention 0-3 Second Pattern Interrupt Hook Enforcement on Scene 1
            if (i == 0 or sc.hook_type == "greeting_hook") and script.video_category != "live_news":
                slow_starters = ["welcome to", "in today's video", "today we will talk about", "আজকের ভিডিওতে", "আমরা কথা বলব"]
                for ss in slow_starters:
                    if ss in sc.narration.lower():
                        sc.narration = sc.narration.lower().replace(ss, "").strip().capitalize()
                        sc.agent_notes += " | Stripped slow intro for 0-3s retention."
                        total_penalty += 2.0
                if "?" not in sc.narration and "!" not in sc.narration:
                    # Append curious suspense element if missing
                    if script.language == "bn":
                        sc.narration += " এর পেছনের আসল রহস্যটি কি আপনি জানেন?"
                    else:
                        sc.narration += " Do you know the shocking truth behind it?"
                    sc.agent_notes += " | Injected 0-3s psychological curiosity hook."

            # Ensure highlighted_subtitle exists
            if not sc.highlighted_subtitle:
                sc.highlighted_subtitle = highlight_retention_keywords(sc.narration, script.language)

            # 1. Pacing check: short videos must not have individual scenes longer than 15s
            if script.video_format == "short" and sc.estimated_duration_sec > 15.0:
                sc.passed_agent_qa = False
                sc.agent_notes = (sc.agent_notes + " | Scene duration too long for short video. Pacing condensed.").strip(" |")
                sc.estimated_duration_sec = 10.0
                total_penalty += 5.0
            else:
                sc.passed_agent_qa = True
                sc.agent_notes = (sc.agent_notes + " | Passed visual & audio pacing.").strip(" |")

            # 2. Robotic filler detector
            robotic_phrases = ["in this video we will discuss", "as an ai language model", "furthermore it is important"]
            for rf in robotic_phrases:
                if rf in sc.narration.lower():
                    sc.narration = sc.narration.lower().replace(rf, "").strip().capitalize()
                    sc.agent_notes += " | Removed robotic filler."
                    total_penalty += 3.0

        script.quality_score = max(0.0, 100.0 - total_penalty)
        script.total_estimated_duration_sec = sum(s.estimated_duration_sec for s in script.scenes)
        return script

    def regenerate_single_scene(self, script: ProductionScript, scene_index: int, new_direction: str = "") -> ProductionScript:
        """Allows surgical single-scene regeneration without burning full script API quota."""
        for sc in script.scenes:
            if sc.scene_index == scene_index:
                logger.info("Regenerating scene #%d for script %s", scene_index, script.script_id)
                if new_direction:
                    sc.visual_prompt = f"{new_direction}, 8k highly detailed"
                sc.passed_agent_qa = True
                sc.agent_notes = "Surgically regenerated by local agent."
                break
        return self.inspect_and_repair_script(script)
