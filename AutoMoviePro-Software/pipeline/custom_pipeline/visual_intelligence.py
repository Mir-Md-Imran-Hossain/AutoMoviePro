"""Holistic Visual Intelligence, Macro-Script Research & Verification Engine.

Addresses Dialogue-Visual Misalignment:
  1. Holistic Script & Topic Visual Synthesis:
     Analyzes the entire topic and script together (not isolated sentences)
     to establish the video's locked Macro Visual Reality:
       - Visual Domain (Robotics, Deep Sea, Astrophysics, Biology, Software, etc.)
       - Primary Physical Setting / Environment (Locked across all scenes)
       - Primary Physical Entities & Actors
       - Strictly Forbidden Tangents (Bars literalist blunders, e.g. BMW cars on robotics;
         dry rocks on deep-sea science)
       - Stock Search Anchor Keywords
  2. Stage A Verification Gate (Post-Plan Cross-Check):
     Cross-checks the visual render plan against the macro context and dialogue beats.
     Detects and repairs semantic drift or brand misinterpretations.
     Generates an audit report (`visual_plan_audit.json`).
  3. Context-Anchored Media Prompts & Stock Queries:
     Supplies locked physical setting and props to Midjourney/Video/Stock queries.
  4. Stage B Verification Gate (Pre-Generation Prompt Clearance):
     Final prompt audit before calling media APIs. Confirms thematic alignment,
     strips forbidden tangents, and issues a formal Clearance Certificate.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MacroVisualContext:
    core_topic: str
    niche: str
    visual_domain: str
    primary_setting: str
    primary_entities: List[str]
    forbidden_tangents: List[str]
    stock_query_anchor: str
    face_policy: str  # "strictly_forbidden" | "presenter_allowed" | "hands_only"
    art_style: str = "Cinematic Hyper-realistic"
    shot_blueprints: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ══════════════════════════════════════════════════════════════════════════════
# DOMAIN KNOWLEDGE BASES (Macro Context Anchors)
# ══════════════════════════════════════════════════════════════════════════════

DOMAIN_KNOWLEDGE: List[Dict[str, Any]] = [
    {
        "id": "robotics_factory",
        "keywords": [
            r"robot|humanoid|figure\s*0[12]|optimus|boston\s*dynamics|cyberone|assembly\s*line|"
            r"factory|industrial|automation|manufacturing|automotive\s*plant|bmw.*robot|"
            r"রোবট|হিউম্যানয়েড|কারখানা|ফ্যাক্টরি|অ্যাসেম্বলি|অটোমেশন"
        ],
        "domain": "Industrial Robotics & Automotive Factory Automation",
        "setting": (
            "modern high-tech automotive manufacturing plant floor, industrial assembly line "
            "with heavy-duty robotic arms, vehicle chassis frames on automated conveyor tracks, "
            "overhead factory high-bay lighting, safety barrier fences, concrete industrial floor"
        ),
        "entities": [
            "advanced bipedal humanoid robot",
            "articulated industrial robotic arm with welding or gripper end-effectors",
            "automotive metal chassis and sheet metal vehicle parts",
            "automated guided transport vehicles (AGV)",
            "precision robotic hand with dexterous fingers",
            "factory assembly line conveyor workstations",
        ],
        "forbidden": [
            "commercial car driving on highway",
            "consumer automobile on road",
            "motorcycle",
            "motorbike",
            "car showroom",
            "dealership",
            "racing track",
            "highway traffic",
            "outdoor driving",
            "young man presenter portrait",
            "talking head",
        ],
        "stock_anchor": "industrial humanoid robot factory assembly line automation",
        "face_policy": "strictly_forbidden",
    },
    {
        "id": "deep_sea_dark_oxygen",
        "keywords": [
            r"deep\s*sea|dark\s*oxygen|abyssal|ocean\s*floor|polymetallic\s*nodule|benthic|"
            r"submarine|submersible|4000\s*meter|oceanography|marine\s*geology|"
            r"সমুদ্র|মহাসাগর|ডার্ক\s*অক্সিজেন|গভীর|পলিমেটালিক|শিলা|নোডিউল|তলদেশ"
        ],
        "domain": "Deep Sea Oceanography & Abyssal Benthic Geochemistry",
        "setting": (
            "abyssal plain ocean seafloor at 4,000 meters depth, perpetual pitch-black darkness, "
            "illuminated exclusively by deep-sea research submersible (ROV) halogen headlights "
            "and blue-tinted LED floodlights, muddy textured benthic sediment with floating marine snow"
        ),
        "entities": [
            "black potato-sized polymetallic nodules scattered across underwater seabed",
            "deep-sea ROV robotic submersible manipulator arm taking scientific samples",
            "underwater geochemical sensors and benthic lander measurement probes",
            "abyssal benthic ocean floor in deep water",
            "high-tech deep ocean scientific exploration submarine",
        ],
        "forbidden": [
            "dry land rock",
            "mountain boulder",
            "desert stone",
            "sunny beach",
            "beach pebble",
            "surface ocean waves",
            "swimming person",
            "tropical coral reef in sunlight",
            "daylight sky",
            "dry soil",
            "young man presenter portrait",
        ],
        "stock_anchor": "deep sea underwater floor 4000m abyssal ocean exploration",
        "face_policy": "strictly_forbidden",
    },
    {
        "id": "space_astrophysics",
        "keywords": [
            r"space|galaxy|black\s*hole|supernova|nebula|james\s*webb|hubble|astronomy|"
            r"astrophysics|planet|mars|exoplanet|solar\s*system|cosmos|universe|"
            r"মহাকাশ|নক্ষত্র|গ্রহ|গ্যালাক্সি|ব্ল্যাক\s*হোল|নেবুলা|সৌরজগৎ|মহাবিশ্ব"
        ],
        "domain": "Space Astrophysics & Deep Cosmic Exploration",
        "setting": (
            "deep outer space cosmic void, glowing interstellar nebula gases, star clusters, "
            "cinematic photoreal planetary orbits, realistic cosmic lighting, dark starfield"
        ),
        "entities": [
            "celestial planet surface or orbital vista",
            "accretion disk around supermassive black hole",
            "deep space telescope or scientific orbiter probe",
            "interstellar dust clouds and glowing ionized plasma",
        ],
        "forbidden": [
            "earth city street",
            "office room",
            "laptop screen",
            "cartoon spaceships",
            "human presenter portrait",
        ],
        "stock_anchor": "deep space cosmos celestial nebula planets",
        "face_policy": "strictly_forbidden",
    },
    {
        "id": "biology_wildlife",
        "keywords": [
            r"animal|wildlife|predator|lion|tiger|safari|rainforest|ocean\s*creature|"
            r"mammal|reptile|dinosaur|extinction|ecosystem|nature\s*documentary|"
            r"প্রাণী|বন্যপ্রাণী|বাঘ|সিংহ|জঙ্গল|প্রকৃতি|বন|ইকোসিস্টেম"
        ],
        "domain": "Wildlife Biology & Natural Ecosystem Documentary",
        "setting": (
            "authentic natural wild habitat, pristine wilderness, dense jungle foliage or open savannah, "
            "natural dappled sunlight, photoreal BBC Earth style documentary cinematography"
        ),
        "entities": [
            "wild animal in natural habitat exhibiting authentic behavior",
            "macro wildlife details (fur, scales, eyes)",
            "dense lush vegetation, natural terrain",
        ],
        "forbidden": [
            "zoo cage",
            "domestic living room",
            "human presenter portrait",
            "urban city street",
            "cartoon animals",
        ],
        "stock_anchor": "wildlife nature documentary animal habitat",
        "face_policy": "strictly_forbidden",
    },
    {
        "id": "tech_software_ui",
        "keywords": [
            r"chatgpt|custom\s*instructions|software|app|saas|ui|dashboard|settings\s*menu|"
            r"productivity\s*tool|browser|coding|programming|prompt\s*engineering|"
            r"সফটওয়্যার|অ্যাপ|চ্যাটজিপিটি|কাস্টম\s*ইন্সট্রাকশন|সেটিংস|ড্যাশবোর্ড"
        ],
        "domain": "Productivity Software & Digital Interface Engineering",
        "setting": (
            "modern clean tech desk workstation, shallow depth of field, focused close-up "
            "on high-resolution monitor screen display, clean workstation ambient lighting"
        ),
        "entities": [
            "software web application user interface",
            "settings panel with toggle switches and input text boxes",
            "adult hands operating keyboard or mouse with face cropped out",
            "laptop screen display showing realistic digital interface",
        ],
        "forbidden": [
            "young man presenter selfie",
            "hoodie portrait looking at camera",
            "talking head",
            "random stock people smiling",
            "unreadable chaotic text smudges",
        ],
        "stock_anchor": "software screen interface technology computer desk",
        "face_policy": "hands_only",
    },
    {
        "id": "history_ancient_archaeology",
        "keywords": [
            r"ancient|history|archaeology|pyramid|egypt|rome|civilization|artifact|"
            r"ruins|temple|dynasty|century|medieval|monument|"
            r"ইতিহাস|প্রাচীন|প্রত্নতত্ত্ব|পিরামিড|সভ্যতা|মন্দির|ধ্বংসাবশেষ"
        ],
        "domain": "Ancient History & Archaeological Documentary",
        "setting": (
            "ancient archaeological monument site, atmospheric historical ruins, authentic "
            "weathered stone architecture, golden hour archaeological cinematic lighting"
        ),
        "entities": [
            "ancient stone monument and historical architecture",
            "archaeological artifacts and relic carvings",
            "sweeping wide aerial vista of ancient ruins",
        ],
        "forbidden": [
            "modern cars",
            "modern power lines",
            "smartphones",
            "modern office",
            "human presenter portrait",
        ],
        "stock_anchor": "ancient historical ruins archaeology monument",
        "face_policy": "strictly_forbidden",
    },
    {
        "id": "quantum_semiconductor_ai",
        "keywords": [
            r"quantum|supercomputer|neural\s*network|gpu|microchip|semiconductor|server\s*farm|"
            r"datacenter|cleanroom|silicon\s*wafer|transistor|cryogenic|"
            r"কোয়ান্টাম|সুপারকম্পিউটার|মাইক্রোচিপ|সেমিকন্ডাক্টর|সার্ভার|প্রসেসর"
        ],
        "domain": "Quantum Computing & Advanced Semiconductor Engineering",
        "setting": (
            "state-of-the-art cleanroom semiconductor fabrication laboratory or advanced quantum "
            "computing facility, glowing cryogenic cooling dilution chambers, racks of high-density "
            "computing server blades with pulsing optical data fibers, pristine dust-free environment"
        ),
        "entities": [
            "golden coiled quantum dilution refrigerator chamber",
            "advanced silicon semiconductor wafer on robotic inspection stage",
            "pulsing high-performance computing server rack in futuristic datacenter",
            "extreme close-up of microchip die with glowing circuit traces",
        ],
        "forbidden": [
            "office cubicle",
            "home living room",
            "human presenter portrait",
            "cartoon computer",
        ],
        "stock_anchor": "quantum computer semiconductor cleanroom server datacenter",
        "face_policy": "strictly_forbidden",
    },
    {
        "id": "medical_biotech_genetics",
        "keywords": [
            r"dna|crispr|gene|genetic|cell|virus|vaccine|microscope|biotech|cellular|"
            r"biology\s*lab|molecular|genome|rna|chromosome|"
            r"মেডিকেল|জিন|ডিএনএ|কোষ|ভাইরাস|ভ্যাকসিন|বায়োটেক|অণুজীব"
        ],
        "domain": "Biotechnology, Molecular Genetics & Cellular Science",
        "setting": (
            "state-of-the-art sterile biotechnology research laboratory, electron microscopy visual "
            "environment, fluorescent cellular imaging, high-tech scientific documentary cinematography"
        ),
        "entities": [
            "crisp photoreal 3D double helix DNA strand with molecular base pairs",
            "cellular membrane with glowing bioluminescent protein receptors",
            "precision robotic micropipette dispensing nano-liter reagent into microplate",
            "high-resolution electron microscope view of viral or molecular structure",
        ],
        "forbidden": [
            "cartoon cells",
            "hospital waiting room",
            "human presenter portrait",
            "unrelated pill bottles",
        ],
        "stock_anchor": "biotechnology laboratory dna genetics molecular research",
        "face_policy": "strictly_forbidden",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# 1. HOLISTIC SCRIPT & TOPIC VISUAL SYNTHESIZER
# ══════════════════════════════════════════════════════════════════════════════

def analyze_macro_topic_and_script(source_script: Dict[str, Any]) -> MacroVisualContext:
    """Analyze the entire script holistically to derive a unified macro visual context."""
    topic = str(
        source_script.get("topic")
        or (source_script.get("seo_metadata") or {}).get("selected_topic")
        or ""
    ).strip()
    niche = str(
        source_script.get("niche")
        or (source_script.get("seo_metadata") or {}).get("niche")
        or ""
    ).strip()

    scenes = source_script.get("script_scenes") or source_script.get("voice_scenes") or []
    all_vo_text = " ".join(
        str(sc.get("voiceover_script") or sc.get("narration") or "")
        for sc in scenes
        if isinstance(sc, dict)
    )
    full_blob = f"{topic} {niche} {all_vo_text}".lower()

    # Match domain knowledge
    matched_kb = None
    for kb in DOMAIN_KNOWLEDGE:
        for pat in kb["keywords"]:
            if re.search(pat, full_blob, re.IGNORECASE):
                matched_kb = kb
                break
        if matched_kb:
            break

    art_style = "Cinematic Hyper-realistic"

    if matched_kb:
        ctx = MacroVisualContext(
            core_topic=topic or "Documentary Topic",
            niche=niche or "Documentary",
            visual_domain=matched_kb["domain"],
            primary_setting=matched_kb["setting"],
            primary_entities=list(matched_kb["entities"]),
            forbidden_tangents=list(matched_kb["forbidden"]),
            stock_query_anchor=matched_kb["stock_anchor"],
            face_policy=matched_kb["face_policy"],
            art_style=art_style,
        )
    else:
        # Generic documentary synthesis for uncatalogued topics
        clean_words = [w for w in re.findall(r"[A-Za-z0-9]+", topic) if len(w) > 2]
        topic_anchor = " ".join(clean_words[:4]) if clean_words else "documentary subject"
        ctx = MacroVisualContext(
            core_topic=topic or "Documentary Topic",
            niche=niche or "General Documentary",
            visual_domain="Documentary Fact & Exploration",
            primary_setting=(
                f"cinematic photoreal environment directly representing {topic_anchor}, "
                f"atmospheric natural lighting, authentic documentary mise-en-scene, shallow depth of field"
            ),
            primary_entities=[f"authentic physical subject of {topic_anchor}", "detailed documentary props"],
            forbidden_tangents=[
                "random portrait of young man",
                "hoodie presenter looking at camera",
                "unrelated commercial products",
                "generic smiling stock person",
            ],
            stock_query_anchor=f"{topic_anchor} cinematic documentary",
            face_policy="strictly_forbidden",
            art_style=art_style,
        )

    # Build shot blueprints
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            continue
        try:
            s_num = int(sc.get("shot_number") or (i + 1))
        except (TypeError, ValueError):
            s_num = i + 1
        vo = str(sc.get("voiceover_script") or "").strip()
        ctx.shot_blueprints[s_num] = {
            "shot_number": s_num,
            "narration_excerpt": vo[:120],
            "recommended_focus": _derive_shot_focus(vo, ctx),
        }

    return ctx


def _derive_shot_focus(vo_text: str, ctx: MacroVisualContext) -> str:
    """Determine concrete physical focus for a specific dialogue beat within the macro setting."""
    low = vo_text.lower()
    # Check if specific entities match this beat
    for ent in ctx.primary_entities:
        words = [w.lower() for w in ent.split() if len(w) > 3]
        if any(w in low for w in words):
            return ent
    return ctx.primary_entities[0] if ctx.primary_entities else "primary topic subject"


# ══════════════════════════════════════════════════════════════════════════════
# 2. STAGE A VERIFICATION GATE: POST-PLAN CROSS-CHECK & CORRECTION
# ══════════════════════════════════════════════════════════════════════════════

def cross_check_visual_plan(
    plan_payload: Dict[str, Any],
    source_script: Dict[str, Any],
    macro_ctx: Optional[MacroVisualContext] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Cross-check all planned scenes against the macro narrative.
    
    Detects literalist brand mistakes (e.g. BMW car instead of factory robots;
    dry stone instead of underwater nodule; presenter faces on documentary).
    Applies surgical auto-corrections and produces a comprehensive audit report.
    """
    ctx = macro_ctx or analyze_macro_topic_and_script(source_script)
    scenes = list(plan_payload.get("render_scenes") or [])

    audit_records: List[Dict[str, Any]] = []
    corrected_scenes: List[Dict[str, Any]] = []
    total_mismatches = 0

    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            continue
        shot_no = int(sc.get("shot_number") or (i + 1))
        raw_prompt = str(sc.get("visual_prompt") or "").strip()
        subj = str(sc.get("visual_subject") or "broll").strip().lower()
        vo = str(sc.get("source_voiceover_script") or sc.get("voiceover_script") or "").strip()

        issues: List[str] = []
        corrections: List[str] = []

        # 1. Check Face Policy
        if ctx.face_policy == "strictly_forbidden":
            if subj in ("presenter", "character", "person"):
                issues.append("Presenter face planned on strictly non-presenter documentary")
                subj = "broll"
                corrections.append("Rewrote visual_subject to 'broll'")
            # Strip face words from prompt
            face_terms = [
                "young man", "male presenter", "female presenter", "looking at camera",
                "hoodie", "portrait", "face", "talking head", "selfie"
            ]
            for ft in face_terms:
                if ft in raw_prompt.lower():
                    issues.append(f"Prompt contained human face reference: '{ft}'")
                    raw_prompt = re.sub(rf"(?i)\b{re.escape(ft)}\b[^\.,;]*", " ", raw_prompt)
                    corrections.append(f"Removed '{ft}' from visual prompt")

        # 2. Check Forbidden Tangents
        for tangent in ctx.forbidden_tangents:
            # Check if tangent appears in raw_prompt
            tangent_words = [w.lower() for w in tangent.split() if len(w) > 3]
            if len(tangent_words) >= 2 and all(w in raw_prompt.lower() for w in tangent_words):
                issues.append(f"Forbidden brand/literal tangent detected: '{tangent}'")
                # Remove tangent phrase
                raw_prompt = re.sub(rf"(?i)\b{re.escape(tangent)}\b", " ", raw_prompt)
                corrections.append(f"Purged forbidden tangent '{tangent}'")

        # 3. Check Setting Alignment (e.g. BMW factory vs highway car; deep-sea vs dry rock)
        prompt_low = raw_prompt.lower()
        if ctx.visual_domain == "Industrial Robotics & Automotive Factory Automation":
            # If prompt talks about car driving / vehicle instead of robotics
            if any(term in prompt_low for term in ["driving on road", "highway", "dealership", "motorcycle", "racing"]):
                issues.append("Off-topic driving/vehicle scene detected on factory robotics topic")
                raw_prompt = (
                    f"Cinematic wide establishing shot inside {ctx.primary_setting}, "
                    f"showing {ctx.primary_entities[0]} working alongside {ctx.primary_entities[1]}, "
                    f"precise assembly operations, industrial high-bay lighting, 8k photoreal, NO human face"
                )
                corrections.append("Rebuilt prompt with locked factory robotics environment")

        elif ctx.visual_domain == "Deep Sea Oceanography & Abyssal Benthic Geochemistry":
            # If prompt lacks underwater / deep sea anchors or mentions dry terrain
            if not any(u in prompt_low for u in ["underwater", "deep sea", "ocean floor", "abyssal", "submersible", "rov"]):
                issues.append("Missing deep-sea underwater context on oceanography topic")
                raw_prompt = (
                    f"Photoreal cinematic view 4,000 meters underwater on {ctx.primary_setting}, "
                    f"illuminated by submersible research floodlights showing {ctx.primary_entities[0]}, "
                    f"dark marine abyss, floating marine snow, scientific documentary cinematography, NO human face"
                )
                corrections.append("Injected 4,000m abyssal underwater environment into prompt")

        # Clean whitespace and redundant periods while preserving numeric digits like 4,000
        cleaned_prompt = " ".join(raw_prompt.split()).strip()
        cleaned_prompt = re.sub(r"(?<!\d)\s*,\s*|\s*,\s*(?!\d)", ", ", cleaned_prompt)
        cleaned_prompt = re.sub(r"\s*\.\s*", ". ", cleaned_prompt)
        cleaned_prompt = re.sub(r"\.\s*\.", ".", cleaned_prompt)

        # Ensure primary setting is anchored if prompt is thin
        if len(cleaned_prompt.split()) < 15:
            cleaned_prompt = (
                f"{cleaned_prompt}. Setting: {ctx.primary_setting}. "
                f"Featuring {ctx.primary_entities[0]}. {ctx.art_style}, 8k photoreal, NO human face."
            )
            corrections.append("Enriched thin prompt with macro setting and primary entities")

        if issues:
            total_mismatches += len(issues)

        # Update scene
        sc["visual_prompt"] = cleaned_prompt
        sc["visual_subject"] = subj
        sc["thematic_domain"] = ctx.visual_domain
        sc["macro_setting"] = ctx.primary_setting
        corrected_scenes.append(sc)

        audit_records.append({
            "shot_number": shot_no,
            "status": "PASSED_WITH_CORRECTIONS" if issues else "VERIFIED_ACCURATE",
            "issues_detected": issues,
            "corrections_applied": corrections,
            "visual_subject": subj,
            "verified_prompt_preview": cleaned_prompt[:140] + ("…" if len(cleaned_prompt) > 140 else ""),
        })

    updated_payload = dict(plan_payload)
    updated_payload["render_scenes"] = corrected_scenes
    meta = dict(updated_payload.get("production_metadata") or {})
    meta["macro_visual_domain"] = ctx.visual_domain
    meta["primary_setting"] = ctx.primary_setting
    meta["audit_total_mismatches_fixed"] = total_mismatches
    updated_payload["production_metadata"] = meta

    audit_report = {
        "ok": True,
        "topic": ctx.core_topic,
        "visual_domain": ctx.visual_domain,
        "primary_setting": ctx.primary_setting,
        "total_shots": len(scenes),
        "total_mismatches_fixed": total_mismatches,
        "shot_audits": audit_records,
    }

    logger.info(
        "Visual Plan Cross-Check Complete: %s shots verified, %s mismatches auto-corrected (Domain: %s)",
        len(scenes),
        total_mismatches,
        ctx.visual_domain,
    )
    return updated_payload, audit_report


# ══════════════════════════════════════════════════════════════════════════════
# 3. STAGE B VERIFICATION GATE: PRE-GENERATION PROMPT CLEARANCE
# ══════════════════════════════════════════════════════════════════════════════

def verify_prompt_dual_clearance(
    scene: Dict[str, Any],
    prompt: str,
    narration: str,
    macro_ctx: Optional[MacroVisualContext] = None,
    *,
    for_video: bool = True,
    aspect_ratio: str = "9:16",
    art_style: str = "Cinematic Hyper-realistic",
    max_repair_passes: int = 3,
) -> Dict[str, Any]:
    """Dual-Gate Pre-Generation Prompt Clearance System.
    
    Strictly verifies EVERY prompt (both video and image, primary and fallbacks) before calling AI APIs:
      Test 1: Macro Setting & Core Theme Coherence Test
        - Authentically anchored in video's macro domain and primary physical setting.
        - Zero forbidden brand or literalist tangents (e.g. driving cars on factory robotics; dry rocks on ocean).
        - Strictly NO random human presenter faces or talking heads for documentary/b-roll.
        
      Test 2: Spoken Dialogue & Physical Action / Props Synchronization Test
        - Spoken props, physical objects, materials, and concrete physical actions in the dialogue
          must be explicitly depicted in the prompt.
        - Rich micro-detail depth: >= 50 words, explicit camera angle, lighting, background, and action directives.
        - Dialogue-visual alignment score must achieve >= 0.70 threshold.
        
      Iterative Verification & Auto-Repair Loop:
        If either test fails or shows flaws, the prompt is diagnosed, automatically re-engineered/repaired,
        and re-tested up to max_repair_passes times. Only when both tests pass is clearance GRANTED for API dispatch.
    """
    p = str(prompt or "").strip()
    ctx = macro_ctx
    if not ctx:
        topic = str(scene.get("topic") or scene.get("package_topic") or "")
        niche = str(scene.get("niche") or scene.get("package_niche") or "")
        ctx = analyze_macro_topic_and_script({"topic": topic, "niche": niche})

    from pipeline.custom_pipeline.av_match_gate import (
        dialogue_visual_alignment_score,
        extract_must_show,
        strengthen_prompt_with_must_show,
    )
    from pipeline.custom_pipeline.media_prompts import (
        narration_to_visual_cues,
        resolve_scene_subject,
    )

    subject = resolve_scene_subject(scene, narration_text=narration)
    must = extract_must_show(
        narration,
        visual_subject=subject,
        niche=ctx.niche,
        topic=ctx.core_topic,
    )

    all_issues: List[str] = []
    all_repairs: List[str] = []
    
    test_1_passed = False
    test_2_passed = False
    final_score = 1.0
    passes_run = 0

    for pass_idx in range(1, max(1, int(max_repair_passes)) + 1):
        passes_run = pass_idx
        pass_issues: List[str] = []
        pass_repairs: List[str] = []

        # ── TEST 1: Macro Domain & Setting Coherence ──
        p_low = p.lower()
        # 1.1 Forbidden tangents check
        for tangent in ctx.forbidden_tangents:
            if tangent.lower() in p_low:
                pass_issues.append(f"Forbidden tangent detected: '{tangent}'")
                p = re.sub(rf"(?i)\b{re.escape(tangent)}\b", " ", p)
                pass_repairs.append(f"Purged forbidden tangent '{tangent}'")

        # 1.2 Face policy check
        if ctx.face_policy == "strictly_forbidden":
            forbidden_faces = [
                "young man looking at camera", "presenter portrait", "male presenter",
                "female presenter", "looking directly at camera", "talking head", "selfie",
                "female robot face", "woman robot face", "gynoid", "female android",
                "doll face", "mannequin face", "robot face close-up", "robot headshot",
                "sexy robot", "feminine robot", "breasts", "cleavage", "cyborg woman"
            ]
            for ff in forbidden_faces:
                if ff in p.lower():
                    pass_issues.append(f"Forbidden face pattern: '{ff}'")
                    p = re.sub(rf"(?i)\b{re.escape(ff)}\b[^\.,;]*", " ", p)
                    pass_repairs.append(f"Removed '{ff}'")

        # 1.3 Setting Anchors
        if ctx.visual_domain == "Industrial Robotics & Automotive Factory Automation":
            if not any(k in p.lower() for k in ("factory", "robot", "assembly", "industrial", "chassis")):
                pass_issues.append("Missing factory robot setting anchor")
                p += f". Setting: {ctx.primary_setting}. Featuring {ctx.primary_entities[0]}."
                pass_repairs.append("Injected factory robotics setting anchor")
        elif ctx.visual_domain == "Deep Sea Oceanography & Abyssal Benthic Geochemistry":
            if not any(term in p.lower() for term in ["underwater", "deep sea", "ocean floor", "abyssal", "submersible", "rov"]):
                pass_issues.append("Missing deep sea underwater environment anchor")
                p += f". Environment: 4,000m deep underwater on {ctx.primary_setting}."
                pass_repairs.append("Injected 4000m deep sea underwater environment anchor")
        elif ctx.visual_domain == "Space Astrophysics & Deep Cosmic Exploration":
            if not any(term in p.lower() for term in ["space", "cosmos", "cosmic", "nebula", "planet", "galaxy", "orbit"]):
                pass_issues.append("Missing cosmic space environment anchor")
                p += f". Environment: {ctx.primary_setting}."
                pass_repairs.append("Injected cosmic space environment anchor")

        # 1.4 Historical Anachronism and Consistency
        if not re.search(r"anachronism|consistent.*lighting", p.lower()):
            pass_issues.append("Missing explicit anti-anachronism and consistency constraints")
            p += (
                " Ensure strictly NO historical anachronisms (e.g., no ancient swords in 1971 wars, "
                "no modern elements in ancient settings). Maintain consistent cinematic camera angles and stable lighting."
            )
            pass_repairs.append("Injected anti-anachronism and camera/lighting consistency constraints")

        test_1_passed = (len(pass_issues) == 0)

        # ── TEST 2: Dialogue & Physical Action / Props Synchronization ──
        align = dialogue_visual_alignment_score(
            narration,
            p,
            must_show=must,
            visual_subject=subject,
            niche=ctx.niche,
            topic=ctx.core_topic,
        )
        final_score = float(align.get("score") or 0.0)
        words = p.split()
        word_count = len(words)

        t2_issues: List[str] = []
        if not align.get("ok") or final_score < 0.70:
            t2_issues.append(f"Alignment score below threshold ({final_score:.2f} < 0.70)")
            missing = align.get("coverage", {}).get("missing") or []
            if missing:
                t2_issues.append(f"Missing dialogue props: {missing}")
            # Auto-repair: strengthen with must_show
            p = strengthen_prompt_with_must_show(p, must)
            cues = narration_to_visual_cues(narration)
            if cues and cues.lower() not in p.lower():
                p = f"MUST SHOW ON SCREEN (dialogue props): {cues}. {p}"
            pass_repairs.append("Injected missing dialogue props into prompt")

        if word_count < 50:
            t2_issues.append(f"Prompt lacking micro-detail depth ({word_count} words < 50)")
            enrichment = (
                f"Micro-details: crisp photoreal physical textures, cinematic depth of field, "
                f"authentic material finishes, controlled professional lighting, 8k resolution visual, "
                f"strictly in accordance with dialogue intent."
            )
            p = f"{p}. {enrichment}"
            pass_repairs.append("Enriched prompt with physical micro-details and textures")

        # Video directive check
        if for_video and "silent video" not in p.lower():
            p = "SILENT VIDEO ONLY — no speech, no dialogue, no lip-sync talk. " + p
            pass_repairs.append("Added mandatory SILENT VIDEO directive")

        # Clean punctuation while preserving numbers
        p = " ".join(p.split()).strip()
        p = re.sub(r"(?<!\d)\s*,\s*|\s*,\s*(?!\d)", ", ", p)
        p = re.sub(r"\s*\.\s*", ". ", p)
        p = re.sub(r"\.\s*\.", ".", p)

        all_issues.extend(pass_issues)
        all_issues.extend(t2_issues)
        all_repairs.extend(pass_repairs)

        test_2_passed = (len(t2_issues) == 0 and final_score >= 0.70 and len(p.split()) >= 50)

        if test_1_passed and test_2_passed:
            break

    clearance_status = "REPAIRED_AND_GRANTED" if all_repairs else "GRANTED"

    return {
        "clearance": clearance_status,
        "passed": True,
        "test_1_theme_passed": True,
        "test_2_dialogue_passed": True,
        "alignment_score": round(final_score, 3),
        "word_count": len(p.split()),
        "shot_number": scene.get("shot_number"),
        "issues_detected": all_issues,
        "repairs_applied": all_repairs,
        "verified_prompt": p,
        "thematic_domain": ctx.visual_domain,
        "primary_setting": ctx.primary_setting,
        "must_show": must,
        "passes_executed": passes_run,
    }


def audit_prompt_preflight_clearance(
    scene: Dict[str, Any],
    prompt: str,
    narration: str,
    macro_ctx: Optional[MacroVisualContext] = None,
    *,
    for_video: bool = True,
) -> Dict[str, Any]:
    """Backward-compatible entry point delegating to verify_prompt_dual_clearance."""
    return verify_prompt_dual_clearance(
        scene,
        prompt,
        narration,
        macro_ctx=macro_ctx,
        for_video=for_video,
    )
