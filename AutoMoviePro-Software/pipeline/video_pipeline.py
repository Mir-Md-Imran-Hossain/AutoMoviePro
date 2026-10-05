from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app import db as store
from app.api_client import LicenseClient
from app.config import OUTPUT_DIR, amp_skip_active, settings
from pipeline.compose import ffprobe_duration, make_color_clip
from pipeline.niche_director import plan_niche_production
from pipeline import product_registry as preg
from pipeline.scene_builder import build_dialogue_clip, concat_av_clips, mix_logo_safe
from pipeline.tts_google import synthesize_narration

logger = logging.getLogger(__name__)


# FIX: Niche-aware fallback instruction for gadget guard replan.
# Each niche gets the correct topic type — not generic "ancient civilizations".
_NICHE_REPLAN_INSTRUCTIONS = {
    "gadget": (
        "FORBIDDEN: generic tech without specific model. "
        "Pick ONE specific named gadget/product (exact brand + model) with strong review search volume."
    ),
    "history": (
        "FORBIDDEN: modern gadgets/phones/earbuds/smartphones. "
        "ONLY ancient/medieval history topics: civilizations, empires, battles, archaeology, lost cities. "
        "Elements must be history beats (intro, discovery, ritual, legacy, outro) — never camera/battery/display."
    ),
    "science": (
        "FORBIDDEN: modern tech product reviews. "
        "ONLY science topics: physics, biology, space, chemistry, engineering discoveries. "
        "Elements: intro/discovery/experiment/mechanism/reveal/outro."
    ),
    "islamic": (
        "FORBIDDEN: modern gadgets, celebrity gossip, political controversy. "
        "ONLY Islamic knowledge: Quran, Seerah, Islamic history, ethics, or spiritual topics. "
        "Faceless metaphors only. Elements: intro/context/wisdom/evidence/reflection/outro."
    ),
    "health": (
        "FORBIDDEN: product advertisements, miracle cures. "
        "ONLY evidence-based health/fitness/nutrition/sleep/mental-health topics. "
        "Elements: intro/habit/research/mechanism/tip/outro."
    ),
    "finance": (
        "FORBIDDEN: crypto moon-shots, get-rich-quick claims. "
        "ONLY finance/economics/investing topics with evidence-based claims. "
        "Elements: intro/market/mechanism/strategy/risk/outro."
    ),
    "motivation": (
        "FORBIDDEN: generic platitudes, overused slogans. "
        "Pick ONE specific psychological principle, habit study, or mindset framework. "
        "Elements: intro/challenge/research/mindset/action/outro."
    ),
    "mystery": (
        "FORBIDDEN: modern tech product reviews, celebrity gossip. "
        "ONLY unsolved mysteries, unexplained phenomena, or hidden history topics. "
        "Elements: intro/setup/evidence/twist/reveal/outro."
    ),
    "nature": (
        "FORBIDDEN: gadget reviews, human technology focus. "
        "ONLY wildlife, ecosystems, natural phenomena, animal behavior topics. "
        "Elements: intro/habitat/behavior/adaptation/revelation/outro."
    ),
    "news": (
        "FORBIDDEN: opinion pieces, unverified claims. "
        "ONLY factual current events with verifiable sources. "
        "Elements: intro/context/development/impact/outro."
    ),
    "true_crime": (
        "FORBIDDEN: graphic glorification of violence. "
        "ONLY factual crime investigation or forensic topics with documentary tone. "
        "Elements: intro/context/evidence/investigation/resolution/outro."
    ),
}


def _niche_replan_note(niche: str, channel_family: str) -> str:
    """Return niche-specific replan instruction for gadget guard fallback."""
    fam = (channel_family or niche or "").lower().strip()
    for key, instruction in _NICHE_REPLAN_INSTRUCTIONS.items():
        if key in fam:
            return instruction
    # Generic fallback for unknown niches
    return (
        f"FORBIDDEN: modern gadgets/phones/earbuds. "
        f"Pick a topic that EXACTLY fits the '{niche}' niche with strong viewer curiosity and SEO. "
        "Never force gadget elements (camera/battery/display) on non-gadget scripts."
    )


# FIX: Niche-aware fact banks for duplicate dialogue replacement.
# Previously only space + ancient library facts existed.
_NICHE_FACT_BANKS = {
    "space": [
        "Orion's ablative heat shield facing lunar-return plasma at 2760°C",
        "SLS twin solid boosters clearing the tower at liftoff with 8.8 million pounds of thrust",
        "the free-return loop that brings the crew home without a lunar burn",
        "service-module thrusters trimming the outbound coast with 110-newton precision",
        "crew displays locked to trajectory and heat-shield health via 1553 data bus",
        "translunar injection after core-stage burnout at 25,000 mph",
        "cislunar tracking passes confirming Orion's path every 8 hours",
        "heat-shield seam inspections requiring 115 separate bond-line checks before stacking",
        "booster separation motors firing at 126,000 feet to clear the core path",
        "Earth rise framing from the lunar free-return arc at 239,000 miles",
        "life-support margins sized for a 42-day mission at 0.5 psi above sea-level cabin pressure",
        "recovery teams positioned in the Pacific within a 17-mile splashdown window",
    ],
    "history": [
        "ash layers dated by carbon samples under a collapsed aisle",
        "bronze stylus tips bent from heavy papyrus use over 40-year service life",
        "harbor silt sealing a scroll niche after a 365 CE earthquake",
        "temple inventories listing loaned books by city name and return date",
        "water channels cut 1.2 meters deep to keep humidity off stacked cedar shelves",
        "trade marks from Rhodes and Antioch on crate clay seals",
        "scribe training graffiti scratched behind a reading bench in demotic script",
        "fire scars that stop abruptly at a thick mudbrick firewall",
        "astronomical notes aligned to a winter solstice sightline cut in the roof",
        "grain tax tallies reused as scratch paper by junior scribes",
        "mirror-polished limestone that reflected oil lamp light 18 meters deeper",
        "a side door sized for carts carrying 30-scroll bundles, not for ceremonial processions",
    ],
    "science": [
        "quantum entanglement measured at room temperature for the first time in 2023",
        "CRISPR base editing correcting a single letter in 3 billion DNA base pairs",
        "muon g-2 anomaly deviating 0.00000251 from Standard Model prediction",
        "James Webb's MIRI instrument detecting CO2 in an exoplanet atmosphere 39 light-years away",
        "graphene conducting electricity 200 times faster than silicon at room temperature",
        "mRNA vaccine platform showing 95% efficacy in randomized Phase III trials",
        "gravitational wave detector LIGO measuring a displacement of 1/10,000th a proton width",
        "tardigrades surviving vacuum, radiation, and -272°C in open space experiments",
        "photosynthesis converting sunlight at only 3-6% efficiency vs 22% for solar panels",
        "octopus RNA editing 60% of transcripts in real-time to adapt to temperature",
        "a single human brain synapse firing in 0.5 milliseconds via chemical gradient",
        "nuclear fusion at NIF releasing 3.15 megajoules from a 2.05-megajoule laser input",
    ],
    "health": [
        "cortisol peaks at 8 AM and reaches its daily trough between 2 and 4 AM",
        "slow-wave sleep consolidating declarative memory within the first 90-minute cycle",
        "a 10-minute walk raising BDNF (brain-derived neurotrophic factor) by 32% in studies",
        "the gut microbiome producing 90% of the body's serotonin outside the brain",
        "intermittent fasting activating autophagy after 16-18 hours without caloric intake",
        "cold exposure at 15°C for 3 minutes increasing brown adipose tissue metabolism by 250%",
        "magnesium glycinate crossing the blood-brain barrier better than magnesium oxide",
        "Zone 2 cardio at 60-70% max heart rate for 150 minutes weekly improving VO2 max",
        "sleep deprivation below 6 hours doubling amyloid plaque clearance failure rates",
        "breathing at 5.5 breaths per minute activating the parasympathetic nervous system",
        "creatine monohydrate showing 8% average strength increase in 12-week meta-analyses",
        "sunlight exposure before 10 AM anchoring the circadian clock 45 minutes earlier",
    ],
    "finance": [
        "dollar cost averaging outperforming lump-sum investing in 68% of 10-year back-tests",
        "the 4% withdrawal rule surviving 96% of 30-year retirement scenarios since 1926",
        "Warren Buffett's compound return averaging 19.8% annually over 58 years vs S&P 10.2%",
        "index fund expense ratios of 0.03% vs active fund average 0.82% fee drag",
        "the equity risk premium averaging 5.5% above Treasury bonds over a century",
        "behavioral bias causing retail investors to underperform the S&P by 1.7% annually",
        "cash holdings above 5% reducing portfolio Sharpe ratio by 0.4 in historical tests",
        "commercial real estate cap rates compressing 200 basis points in low-rate decades",
        "the yield curve inverting 6-18 months before every US recession since 1955",
        "inflation eroding 40% of purchasing power over 20 years at a 2.5% rate",
        "tax-loss harvesting saving 0.5-1.5% annually in after-tax returns for high earners",
        "momentum factor portfolios outperforming the market by 3-5% annually since 1927",
    ],
    "islamic": [
        "the first word revealed in the Quran was Iqra meaning Read — a command to seek knowledge",
        "Salah al-Din Ayyubi reportedly feeding enemy Richard I's troops during battle illness",
        "the House of Wisdom in Baghdad translating 200,000 manuscripts before 1258",
        "Ibn Battuta traveling 75,000 miles across 44 modern countries in the 14th century",
        "Al-Zahrawi inventing the surgical catgut suture in 10th-century Cordoba",
        "the Quran mentioning the expansion of the universe 14 centuries before Hubble",
        "the concept of zero and algebra both transmitted to Europe through Islamic scholars",
        "Fatima al-Fihri founding the world's oldest continually operating university in 859 CE",
        "Istanbul's Sultanahmet Mosque completed in 1616 with 14 tonnes of Iznik ceramic tiles",
        "the Hajj pilgrimage gathering over 2 million worshippers annually as one of the largest",
        "Ibn Sina's Canon of Medicine remaining a European medical textbook until the 18th century",
        "the Islamic lunar calendar making Ramadan cycle through all seasons every 33 years",
    ],
    "motivation": [
        "the 'implementation intention' strategy tripling follow-through rate in Gollwitzer's research",
        "identity-based habits outlasting outcome-based habits by 3x in 12-month studies",
        "social accountability partners increasing goal completion by 65% in Dominican's research",
        "the 66-day average (not 21 days) for habit formation per Phillippa Lally's UCL study",
        "decision fatigue depleting prefrontal cortex resources after 35,000 daily micro-decisions",
        "flow states requiring a 4% skill-challenge imbalance beyond current competence level",
        "intrinsic motivation outperforming extrinsic reward in creative tasks by 40% in Amabile's work",
        "reframing failure as data reducing cortisol spike by 22% in stress-mindset experiments",
        "the Zeigarnik effect making unfinished tasks occupy working memory more than completed ones",
        "morning routines completed before 9 AM correlating with higher reported self-efficacy scores",
        "the power of 'not yet' replacing 'failed' reducing anxiety in Dweck's growth-mindset trials",
        "visualization of the process (not the goal) improving performance 30% more than outcome imagery",
    ],
    "mystery": [
        "the Voynich Manuscript's carbon dating placing its vellum between 1404 and 1438 CE",
        "the Wow! signal lasting exactly 72 seconds on August 15, 1977 and never repeating",
        "the Zodiac Cipher's 340-character message decoded only in 2020 by a civilian team",
        "Dyatlov Pass showing internal organ damage with no external wounds on three bodies",
        "the Antikythera Mechanism containing 37 interlocking bronze gears accurate to hours",
        "Easter Island's moai weighing up to 86 tonnes moved without a wheel or draft animal",
        "the Nazca Lines visible only from 1,500 feet altitude with lines staying perfectly straight",
        "the Baghdad Battery producing 1.1 volts when filled with grape juice or vinegar",
        "Göbekli Tepe's T-pillars carved 6,000 years before Stonehenge with no metal tools",
        "the Mary Celeste found perfectly intact with 6 months of provisions and no crew in 1872",
        "the Taos Hum heard by only 2% of residents at a frequency of 30-80 Hz with no source found",
        "SCP-style anomalies inspiring official government UAP declassified footage in 2023",
    ],
    "nature": [
        "blue whales producing sounds at 188 decibels, louder than a jet engine at 140 dB",
        "a single oak tree supporting 500 species of insects, birds, and fungi",
        "Arctic terns migrating 71,000 km annually — equivalent to 3 trips around the Earth in a lifetime",
        "mantis shrimp striking at 50 mph with 1,500 newtons of force on a 3-cm punch",
        "mycorrhizal networks transferring carbon between trees across 300 meters underground",
        "migratory birds detecting Earth's magnetic field via cryptochrome proteins in their eyes",
        "a single gram of fertile soil containing 1 billion bacteria from 10,000 species",
        "whale fall carcasses supporting unique ecosystems for 50-100 years on the ocean floor",
        "poison dart frog toxins coming entirely from their wild diet, not produced internally",
        "elephant infrasound traveling 10 km through the ground at frequencies below 20 Hz",
        "coral reefs covering 0.1% of ocean floor but hosting 25% of all marine species",
        "bombardier beetles mixing hydrogen peroxide and hydroquinone at 100°C as a defense",
    ],
    "news": [
        "diplomatic back-channels often running 6-18 months before a public announcement",
        "economic sanctions historically reducing target GDP by 2-3% per year on average",
        "satellite imagery making military movement verification possible within 3 hours",
        "UN Security Council vetoes having been used 293 times since 1946",
        "currency swap lines between central banks providing up to $600 billion in emergency liquidity",
        "election interference campaigns documented in 81 countries between 1946 and 2000",
        "trade war tariffs typically raising domestic consumer prices by 0.5-2% annually",
        "climate attribution science now linking individual weather events to warming within months",
        "disinformation reaching 70% of audiences before corrections appear in studies",
        "G7 communiques binding member nations to voluntary commitments tracked by think-tanks",
        "refugee crises costing host nations an average of $12,000 per person in the first year",
        "cybersecurity attacks on critical infrastructure doubling year-over-year since 2020",
    ],
    "true_crime": [
        "forensic genealogy identifying Golden State Killer 40 years later via a 3rd-cousin DNA match",
        "Locard's exchange principle holding that every contact leaves a trace of evidence",
        "bite-mark evidence being discredited in 24 wrongful convictions by PCAST's 2016 report",
        "the FBI VICAP database linking crimes across 4,000 jurisdictions using 95 behavioral factors",
        "cold case DNA surviving 30+ years in porous bone marrow protected from UV exposure",
        "the Unabomber manifesto being recognized by his own brother via unique writing patterns",
        "undercover operations requiring judge-approved warrants renewed every 30 days",
        "confession evidence being false in 29% of DNA exoneration cases per Innocence Project data",
        "geographic profiling software reducing suspect zones to 5% of original search area",
        "digital forensics recovering deleted messages from phone chips via JTAG extraction",
        "victimology analysis predicting next target location within 2 miles in serial cases",
        "blood spatter pattern analysis requiring minimum 12-point calibration before court use",
    ],
}


def _plan_niche_production_idempotent(work: Path, **kwargs) -> Dict[str, Any]:
    """Canonical script generation with BUILD-04C idempotency; legacy fallback on bridge failure."""
    try:
        from pipeline.idempotency.script_bridge import idempotent_plan_niche_production

        return idempotent_plan_niche_production(work, job_id=work.name, **kwargs)
    except Exception as exc:
        logger.warning("script_bridge failed (%s) — legacy plan_niche_production", str(exc)[:120])
        return plan_niche_production(**kwargs)


def _live(phase: str = "", detail: str = "", *, scene=None, total=None, api: str = "", action: str = "") -> None:
    """Best-effort live activity updates (no-op if bus unused)."""
    try:
        from pipeline.live_activity import is_cancel_requested, note_api, set_phase, set_scene

        if is_cancel_requested():
            raise RuntimeError("cancelled_by_user")
        if phase:
            set_phase(phase, detail or phase)
        if scene is not None:
            set_scene(scene, total, detail or "")
        if api:
            note_api(api, action or detail or phase or "call", "call", dest=detail or phase or "")
    except RuntimeError:
        raise
    except Exception:
        pass


def generate_video(
    channel: Dict[str, Any],
    video_type: str = "short",
    *,
    topic: str = "",
    research_notes: str = "",
    work_dir: Optional[Path] = None,
    allow_duplicate: bool = False,
    existing_job_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Full pipeline:
      niche/topic director → dialogue scenes → Google AI Studio TTS → element-matched footage → mux → concat
    Strong duplicate guard: refuses same product already reviewed on this channel.

    existing_job_id: when set (C01-A customer Generate), update that jobs row instead of insert.
    Scheduler / idle pregenerate omit this and keep add_job behavior.
    """
    video_type = "long" if video_type == "long" else "short"
    from pipeline.duration_budget import (
        assert_all_planned_scenes_produced,
        raise_if_budget_would_drop_scenes,
        resolve_duration_contract,
        trim_would_cut_coverage,
    )

    duration_contract = resolve_duration_contract(video_type)
    max_seconds = int(duration_contract["max_seconds"])
    plan_budget_seconds = int(duration_contract["target_seconds"])
    from pipeline.aspect_lock import coerce_size, render_profile, size_for_video_type

    # Hard lock: short=9:16 vertical, long=16:9 horizontal (never inverted)
    size = size_for_video_type(video_type)
    size = coerce_size(size, video_type)
    aspect_profile = render_profile(video_type)

    from pipeline.api_keys import load_api_bundle

    bundle = load_api_bundle(channel=channel)
    google_keys = list(bundle["google_keys"] or [])
    agnes_keys = list(bundle["agnes_keys"] or [])
    openrouter_keys = list(bundle.get("openrouter_keys") or [])
    pollinations_key = str(bundle.get("pollinations_key") or channel.get("pollinations_api") or "")
    pexels_key = str(bundle.get("pexels_key") or channel.get("pexels_api") or "")
    # Keep channel dict in sync so downstream still works if it reads channel fields
    if agnes_keys and not (channel.get("agnes_api") or "").strip():
        channel = {**channel, "agnes_api": agnes_keys[0]}
    if openrouter_keys and not (channel.get("openrouter_api") or "").strip():
        channel = {**channel, "openrouter_api": openrouter_keys[0]}
    if pollinations_key and not (channel.get("pollinations_api") or "").strip():
        channel = {**channel, "pollinations_api": pollinations_key}
    if pexels_key and not (channel.get("pexels_api") or "").strip():
        channel = {**channel, "pexels_api": pexels_key}

    # C05-GX: image fallback is EXCEPTION-only (VIDEO/Agnes is industrial primary)
    from pipeline.media_mode_engine import allow_image_fallback_default

    allow_image_fallback = allow_image_fallback_default(channel)
    customer_id = str(
        channel.get("customer_id")
        or channel.get("owner_id")
        or channel.get("user_id")
        or ""
    ).strip()
    language_entitlement = str(
        channel.get("language") or channel.get("primary_language") or ""
    ).strip()

    from pipeline.niche_agent import apply_niche_to_channel, director_notes_from_channel

    channel = apply_niche_to_channel(channel, overwrite_empty_only=True)
    niche = channel.get("niche") or "Custom"
    niche_id = channel.get("niche_id")
    channel_id = channel.get("id")
    blocked = preg.blocked_names(channel_id=channel_id, niche=niche)
    research_notes = (research_notes or "") + "\n" + director_notes_from_channel(channel)

    if topic and not allow_duplicate:
        dup, matched = preg.is_duplicate(topic, channel_id=channel_id, niche=niche)
        if dup:
            raise RuntimeError(
                f"Duplicate product blocked: {topic!r} matches already-reviewed {matched!r}"
            )
        # Record early so the next discovery/selection rotates away even if this run fails later
        try:
            from pipeline.intelligence.topic_history import record_topic_use

            if channel_id:
                record_topic_use(
                    int(channel_id),
                    str(topic),
                    source="generate_video_start",
                    video_type=str(video_type or ""),
                    niche=str(niche or ""),
                )
        except Exception:
            pass

    from pipeline.resume_guard import (
        clear_scene_fail_marker,
        clip_fingerprint,
        find_resumable_work,
        list_accepted_scene_indexes,
        should_reuse_existing_clip,
        write_resume_meta,
    )

    if work_dir is not None:
        work = Path(work_dir)
    else:
        found = find_resumable_work(
            OUTPUT_DIR, channel_id=channel.get("id"), video_type=video_type
        )
        if found:
            work = found
            logger.info("Resuming incomplete %s from %s", video_type, work.name)
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            work = OUTPUT_DIR / f"ch{channel.get('id')}_{video_type}_{stamp}"
    work.mkdir(parents=True, exist_ok=True)

    plan_path = work / "director_plan.json"
    plan: Optional[Dict[str, Any]] = None
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            if not (plan.get("scenes") or []):
                plan = None
            else:
                logger.info("Resuming with existing director_plan.json (%s scenes)", len(plan["scenes"]))
        except Exception:
            plan = None

    # C06-E: CUSTOMER_APPROVED_PLAN lock — approved Production Plan is source of truth.
    # Do NOT re-run TRS / topic intelligence / ScriptPlan / humanize rewrites.
    from app.customer_plan_adapter import is_customer_approved_plan

    customer_approved_lock = bool(plan and is_customer_approved_plan(plan))
    if (work / "c06e_customer_approved_plan.lock").exists() and plan is not None:
        customer_approved_lock = True
        if isinstance(plan, dict):
            plan["plan_source"] = plan.get("plan_source") or "CUSTOMER_APPROVED_PLAN"
            plan["trs_replanning_forbidden"] = True

    # C05-TRS-PW: single TRS composition replaces separate intelligence + script blocks.
    # Old run_intelligence_gate + _plan_niche_production_idempotent must NOT both run with TRS.
    trs_handoff: Optional[Dict[str, Any]] = None
    resuming_plan = plan is not None
    accepted_idxs = list_accepted_scene_indexes(work) if resuming_plan else []
    skip_plan_rebuild = resuming_plan and (
        bool(accepted_idxs)
        or (work / "content_human_audit.json").exists()
        or customer_approved_lock
    )
    if customer_approved_lock:
        logger.info(
            "C06-E CUSTOMER_APPROVED_PLAN lock active — skip TRS/script/humanize replan (%s scenes)",
            len((plan or {}).get("scenes") or []),
        )
        # Additive montage enrichment only (slots/checklist) — never replan TRS/dialogue.
        try:
            from pipeline.montage_brain import apply_montage_brain_to_plan

            plan = apply_montage_brain_to_plan(
                plan if isinstance(plan, dict) else {},
                video_type=video_type,
            )
            plan_path.write_text(
                json.dumps(plan, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            logger.info(
                "montage_brain (approved-lock): checklist_ok=%s",
                (plan.get("montage_checklist") or {}).get("ok"),
            )
        except Exception as mm_exc:
            logger.warning("montage_brain approved-lock soft-fail: %s", mm_exc)

    if plan is None:
        from pipeline.intelligence.config import get_research_mode, require_fail_closed
        from pipeline.intelligence.gate import GATE_BLOCKED_MARKER
        from pipeline.trs_facade import (
            assert_trs_pre_provider_ready,
            run_trs_pipeline,
        )

        _live("trs", f"C05-TRS planning — {niche}", api="llm", action="run_trs_pipeline")
        mock_research = True if get_research_mode().value == "MOCK" else None
        # Production uses real script bridge unless AMP skip / explicit mock env
        use_mock_script = bool(amp_skip_active("AMP_SKIP_SCRIPT_LLM"))
        trs_handoff = run_trs_pipeline(
            work,
            channel=channel,
            topic=topic,
            video_type=video_type,
            language=str(channel.get("language") or "en"),
            max_seconds=plan_budget_seconds,
            blocked_topics=blocked,
            use_mock_research=mock_research,
            use_mock_script=use_mock_script,
            research_notes=research_notes,
            google_api_keys=google_keys,
            openrouter_api=channel.get("openrouter_api") or "",
            openrouter_keys=openrouter_keys,
            niche_id=int(niche_id) if niche_id else None,
            channel_specials={
                "video_special": channel.get("video_special") or "",
                "generation_special": channel.get("generation_special") or "",
                "title_desc_special": channel.get("title_desc_special") or "",
            },
            job_id=work.name,
            skip_intelligence=bool(allow_duplicate),
            production_wired=True,
            allow_reserve_pick=not allow_duplicate,
        )
        if not trs_handoff.get("ok"):
            reason = str(trs_handoff.get("reason") or trs_handoff.get("status") or "trs_blocked")
            raise RuntimeError(f"{GATE_BLOCKED_MARKER}: c05_trs stage={trs_handoff.get('stage')} detail={reason}")

        preflight = assert_trs_pre_provider_ready(trs_handoff)
        if preflight.get("blocked"):
            raise RuntimeError(
                f"{GATE_BLOCKED_MARKER}: c05_trs_preflight detail={','.join(preflight.get('blocks') or [])}"
            )

        plan = dict(trs_handoff.get("director_plan") or {})
        if not (plan.get("scenes") or []):
            raise RuntimeError(f"{GATE_BLOCKED_MARKER}: c05_trs missing director_plan scenes")
        topic = str(trs_handoff.get("topic") or topic or plan.get("topic") or "").strip()
        score = (trs_handoff.get("intelligence") or {}).get("score") or {}
        if isinstance(score, dict) and score.get("total_score") is not None:
            research_notes = (research_notes or "") + f"\nBUILD-04G score: {score.get('total_score')}"
        research_notes = (research_notes or "") + f"\nResearch mode: {get_research_mode().value}"
        research_notes = (research_notes or "") + "\nC05-TRS: wired"

        planned_topic = str(plan.get("topic") or topic or "").strip()
        if planned_topic and not allow_duplicate:
            dup, matched = preg.is_duplicate(planned_topic, channel_id=channel_id, niche=niche)
            if dup:
                # Intentional single-authority replan via TRS script path (revision), not parallel old+new
                logger.warning("Planned topic %r duplicates %r — TRS script replan", planned_topic, matched)
                # Script-only replan (revision) — do NOT re-invoke BUILD-04G for the same job
                trs_handoff = run_trs_pipeline(
                    work,
                    channel=channel,
                    topic="",
                    video_type=video_type,
                    language=str(channel.get("language") or "en"),
                    max_seconds=plan_budget_seconds,
                    blocked_topics=list(blocked) + [planned_topic, matched],
                    use_mock_research=mock_research,
                    use_mock_script=use_mock_script,
                    research_notes=(research_notes or "") + f"\nAvoid duplicate of: {matched}",
                    google_api_keys=google_keys,
                    openrouter_api=channel.get("openrouter_api") or "",
                    openrouter_keys=openrouter_keys,
                    niche_id=int(niche_id) if niche_id else None,
                    channel_specials={
                        "video_special": channel.get("video_special") or "",
                        "generation_special": channel.get("generation_special") or "",
                        "title_desc_special": channel.get("title_desc_special") or "",
                    },
                    job_id=work.name,
                    skip_intelligence=True,
                    production_wired=True,
                    revision_id=f"dedupe-{matched}"[:48],
                )
                if not trs_handoff.get("ok"):
                    raise RuntimeError(
                        f"Could not find non-duplicate topic via TRS (blocked: {trs_handoff.get('reason')})"
                    )
                plan = dict(trs_handoff.get("director_plan") or {})
                planned_topic = str(plan.get("topic") or "").strip()
                dup2, matched2 = preg.is_duplicate(planned_topic, channel_id=channel_id, niche=niche)
                if dup2:
                    raise RuntimeError(
                        f"Could not find non-duplicate topic (still matches {matched2!r})"
                    )
                topic = planned_topic

        plan_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        if require_fail_closed() and not (topic or "").strip():
            raise RuntimeError(f"{GATE_BLOCKED_MARKER}: c05_trs empty topic after planning")


    planned_topic = str(plan.get("topic") or topic or "").strip()
    # Hard reject gadget templates on non-gadget niches (e.g. Sony earbuds on Ancient Civ)
    # C06-E: approved customer plan must never be rewritten by gadget/script replan.
    if customer_approved_lock:
        if planned_topic:
            topic = planned_topic
        logger.info("C06-E: skipping gadget/TRS script replan under CUSTOMER_APPROVED_PLAN lock")
    else:
      try:
        from pipeline.dialogue_uniqueness import (
            GADGET_ELEMENTS,
            niche_uses_gadget_template,
        )

        # Use CHANNEL style only — director often mis-tags style_family=gadget
        channel_family = str(channel.get("style_family") or "")
        if not niche_uses_gadget_template(str(niche or ""), channel_family):
            def _gadget_hits(p: dict) -> list:
                return [
                    str(s.get("element") or "").lower()
                    for s in (p.get("scenes") or [])
                    if isinstance(s, dict)
                    and str(s.get("element") or "").lower() in GADGET_ELEMENTS
                ]

            def _looks_gadget_topic(t: str) -> bool:
                tl = (t or "").lower()
                return any(
                    x in tl
                    for x in (
                        "sony",
                        "iphone",
                        "samsung",
                        "pixel",
                        "earbuds",
                        "headphones",
                        "galaxy",
                        "wh-1000",
                        "airpods",
                        "xiaomi",
                        "oneplus",
                        "nothing phone",
                        "buds",
                        "smartwatch",
                        "apple watch",
                        "galaxy watch",
                        "gadget",
                        "smartphone",
                    )
                )

            for _attempt in range(2):
                gadget_hits = _gadget_hits(plan or {})
                planned_topic = str((plan or {}).get("topic") or planned_topic or "").strip()
                if len(gadget_hits) < 3 and not _looks_gadget_topic(planned_topic):
                    break
                logger.warning(
                    "Director returned gadget plan on niche %r topic=%r hits=%s — TRS script replan",
                    niche,
                    planned_topic,
                    gadget_hits[:6],
                )
                from pipeline.trs_facade import plan_script_for_trs, refresh_c05s_from_director_plan

                # FIX: niche-aware replan instruction — each niche gets the correct topic type
                _replan_note = _niche_replan_note(str(niche or ""), channel_family)
                plan = plan_script_for_trs(
                    work,
                    job_id=work.name,
                    niche=niche,
                    niche_id=int(niche_id) if niche_id else None,
                    channel_name=channel.get("youtube_name") or "AutoMovie Pro",
                    video_type=video_type,
                    topic="",
                    research_notes=(research_notes or "") + "\n" + _replan_note,
                    google_api_keys=google_keys,
                    openrouter_api=channel.get("openrouter_api") or "",
                    openrouter_keys=openrouter_keys,
                    max_seconds=plan_budget_seconds,
                    blocked_products=blocked + ([planned_topic] if planned_topic else []),
                    channel_specials={
                        "video_special": channel.get("video_special") or "",
                        "generation_special": channel.get("generation_special") or "",
                        "title_desc_special": channel.get("title_desc_special") or "",
                    },
                    use_mock=bool(amp_skip_active("AMP_SKIP_SCRIPT_LLM")),
                    revision_id=f"gadget-guard-{_attempt}",
                )
                if isinstance(plan, dict) and "scenes" not in plan and isinstance(plan.get("plan"), dict):
                    plan = plan["plan"]
                planned_topic = str(plan.get("topic") or "").strip()
                # FIX: preserve the actual channel niche family, not always "history"
                if isinstance(plan, dict):
                    plan["style_family"] = channel_family or niche or "history"
                refreshed = refresh_c05s_from_director_plan(
                    plan,
                    channel_id=channel_id or 0,
                    topic=planned_topic,
                    language=str(channel.get("language") or "en"),
                    fmt="SHORT" if video_type == "short" else "LONG",
                    max_seconds=float(plan_budget_seconds),
                    prefer_image_fallback=False,
                )
                plan = refreshed.get("director_plan") or plan
                trs_handoff = {
                    **(trs_handoff or {}),
                    "c05s": refreshed.get("c05s"),
                    "script_plan": refreshed.get("script_plan"),
                    "dialogue_segments": refreshed.get("dialogue_segments"),
                    "director_plan": plan,
                    "ok": True,
                }
                plan_path.write_text(
                    json.dumps(plan, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            gadget_hits = _gadget_hits(plan or {})
            planned_topic = str((plan or {}).get("topic") or "").strip()
            if len(gadget_hits) >= 3 or _looks_gadget_topic(planned_topic):
                # LLM keep returning gadgets — hard local history plan (no LLM)
                from pipeline.niche_director import _fallback_history_plan

                logger.warning(
                    "niche_template_guard: using hard history fallback after gadget replan "
                    "(was topic=%r hits=%s)",
                    planned_topic,
                    gadget_hits[:6],
                )
                plan = _fallback_history_plan(
                    niche=str(niche or "Ancient Civilizations"),
                    topic="",
                    video_type=video_type,
                    max_seconds=plan_budget_seconds,
                    channel_name=channel.get("youtube_name") or "AutoMovie Pro",
                    blocked=blocked + ([planned_topic] if planned_topic else []),
                )
                planned_topic = str(plan.get("topic") or "").strip()
                try:
                    from pipeline.trs_facade import refresh_c05s_from_director_plan

                    refreshed = refresh_c05s_from_director_plan(
                        plan,
                        channel_id=channel_id or 0,
                        topic=planned_topic,
                        language=str(channel.get("language") or "en"),
                        fmt="SHORT" if video_type == "short" else "LONG",
                        max_seconds=float(plan_budget_seconds),
                    )
                    plan = refreshed.get("director_plan") or plan
                    trs_handoff = {
                        **(trs_handoff or {}),
                        "c05s": refreshed.get("c05s"),
                        "director_plan": plan,
                        "ok": True,
                    }
                except Exception as refresh_exc:
                    logger.warning("C05-S refresh after history fallback skipped: %s", refresh_exc)
                plan_path.write_text(
                    json.dumps(plan, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
      except Exception as exc:
        logger.warning("niche template guard skipped: %s", exc)

    from pipeline.master_lang import (
        looks_like_english_master,
        narration_sidecar_matches,
        require_english_master_plan,
    )

    if skip_plan_rebuild:
        logger.info(
            "Keeping existing plan/clips (%s accepted) — skip director/humanize rebuild",
            len(accepted_idxs),
        )
        _live(
            "scenes",
            f"Resume {len(accepted_idxs)} accepted clips — only failed/missing beats regen",
            total=len(plan.get("scenes") or []),
        )
    else:
        plan = require_english_master_plan(
            plan,
            google_api_keys=google_keys,
            openrouter_keys=openrouter_keys,
        )
        planned_topic = str(plan.get("topic") or topic or "").strip()
        try:
            from pipeline.content_humanizer import humanize_plan
            from pipeline.error_notebook import note_error

            _live("humanize", "Human-voice audit on title/script", api="llm", action="humanize")
            hum = humanize_plan(
                plan,
                google_api_keys=google_keys,
                openrouter_keys=openrouter_keys,
                work_dir=work,
                use_llm=True,
            )
            plan = hum.get("plan") or plan
            if not hum.get("passed"):
                note_error(
                    subsystem="content_humanizer",
                    fault_code="human_voice_weak",
                    message=f"avg={hum.get('audit_after', {}).get('avg_score')} issues={hum.get('audit_after', {}).get('issues')}",
                    severity="warn",
                    job_id=None,
                    channel_id=channel_id,
                    context={"issues": (hum.get("audit_after") or {}).get("issues") or []},
                )
            planned_topic = str(plan.get("topic") or topic or "").strip()
        except Exception as exc:
            logger.warning("content humanize skipped: %s", exc)
            try:
                from pipeline.error_notebook import note_error

                note_error(
                    subsystem="content_humanizer",
                    fault_code="humanize_exception",
                    message=str(exc)[:400],
                    severity="warn",
                    channel_id=channel_id,
                )
            except Exception:
                pass
        # C05-TRS-PW: refresh C05-S from final narrations (no intelligence / no script provider)
        try:
            from pipeline.trs_facade import persist_trs_handoff, refresh_c05s_from_director_plan

            refreshed = refresh_c05s_from_director_plan(
                plan if isinstance(plan, dict) else {},
                channel_id=channel_id or 0,
                topic=planned_topic or topic,
                language=str(channel.get("language") or "en"),
                fmt="SHORT" if video_type == "short" else "LONG",
                max_seconds=float(plan_budget_seconds),
                fact_pack=(trs_handoff or {}).get("fact_pack") if isinstance(trs_handoff, dict) else None,
                prefer_image_fallback=False,
            )
            plan = refreshed.get("director_plan") or plan
            try:
                from pipeline.media_mode_engine import enforce_video_primary_on_plan, summarize_modes

                plan = enforce_video_primary_on_plan(plan if isinstance(plan, dict) else {})
                logger.info("media_mode_engine video-primary: %s", summarize_modes(plan))
                from pipeline.montage_brain import apply_montage_brain_to_plan

                plan = apply_montage_brain_to_plan(
                    plan if isinstance(plan, dict) else {},
                    video_type=video_type,
                )
                logger.info(
                    "montage_brain: checklist_ok=%s slots=%s",
                    (plan.get("montage_checklist") or {}).get("ok"),
                    len((plan.get("scenes") or [])),
                )
            except Exception as mm_exc:
                logger.warning("media_mode_engine/montage enforce soft-fail: %s", mm_exc)
            trs_handoff = {
                **(trs_handoff or {"ok": True, "status": "PASS"}),
                "c05s": refreshed.get("c05s"),
                "script_plan": refreshed.get("script_plan"),
                "dialogue_segments": refreshed.get("dialogue_segments"),
                "director_plan": plan,
                "compatibility": {
                    **((trs_handoff or {}).get("compatibility") or {}),
                    "generate_video_wired": True,
                    "c05s_refreshed_after_humanize": True,
                },
            }
            persist_trs_handoff(work, trs_handoff)
        except Exception as exc:
            logger.warning("C05-S post-humanize refresh skipped: %s", exc)
        try:
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    if planned_topic and not allow_duplicate:
        dup, matched = preg.is_duplicate(planned_topic, channel_id=channel_id, niche=niche)
        if dup and not plan_path.exists():
            raise RuntimeError(
                f"Duplicate product blocked: {planned_topic!r} matches already-reviewed {matched!r}"
            )

    # BUILD-02 / AMP-003: canonical contract wiring gate (fail-closed before scene generation)
    try:
        from pipeline.contract_wiring.production_bridge import assert_production_plan_wiring

        assert_production_plan_wiring(
            plan if isinstance(plan, dict) else {},
            job_id=work.name,
            work_dir=work,
            research_notes=research_notes or "",
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"contract_wiring_gate_error:{exc}") from exc

    scenes = list(plan.get("scenes") or [])
    clips: List[Path] = []
    av_report: List[Dict[str, Any]] = []
    try:
        from pipeline.dialogue_uniqueness import (
            detect_dialogue_uniqueness,
            detect_wrong_template,
            enforce_unique_scene_narrations,
            sanitize_spoken_narration,
        )

        scenes = enforce_unique_scene_narrations(scenes)
        for sc in scenes:
            if isinstance(sc, dict):
                sc["narration"] = sanitize_spoken_narration(str(sc.get("narration") or ""))
        plan["scenes"] = scenes
        uniq = detect_dialogue_uniqueness(scenes)
        tmpl = detect_wrong_template(
            scenes, niche=str(niche or ""), style_family=str(channel.get("style_family") or "")
        )
        if not uniq.get("passed") or not tmpl.get("passed"):
            logger.warning(
                "Director plan dialogue issues uniq=%s tmpl=%s — rewriting flagged beats",
                uniq.get("issues"),
                tmpl.get("issues"),
            )
            _live("director", "Fixing repeated / wrong-template dialogue", api="llm", action="dedupe_dialogue")
            seen_ok: List[str] = []
            from pipeline.dialogue_uniqueness import pair_overlap_ratio

            for si, sc in enumerate(scenes):
                if not isinstance(sc, dict):
                    continue
                narr = str(sc.get("narration") or "")
                if any(pair_overlap_ratio(narr, prev) >= 0.36 for prev in seen_ok):
                    topic_bit = (planned_topic or niche or "this topic")[:48]
                    el = str(sc.get("element") or "moment").replace("_", " ").strip() or "moment"
                    # Avoid "beat beat" when element already is "beat"
                    if el.lower() in {"beat", "beats"}:
                        el = "moment"
                    niche_l = f"{str(niche or '')} {str(planned_topic or '')}".lower()
                    if any(t in niche_l for t in ("islam", "deen", "quran", "muslim", "hadith")):
                        fact_bank = [
                            "classical scholars emphasized sincerity and inward discipline above public acclaim",
                            "historical records highlight how early communities preserved knowledge through rigorous oral chains",
                            "tradition notes how patience in hardship reshapes character and strengthens resolve",
                            "historical accounts show practical wisdom guiding decisions during intense uncertainty",
                            "reflection upon these events demonstrates the profound connection between faith and steadfast action",
                            "early manuscripts document ethical guidelines that protected communities during crisis",
                        ]
                    elif any(t in niche_l for t in ("financ", "invest", "crypto", "money", "wealth", "stock")):
                        fact_bank = [
                            "long-term investors prioritize risk-adjusted return and defensive capital allocation",
                            "compounding returns reward systematic discipline over unpredictable market timing",
                            "institutional data confirms that controlling portfolio drawdowns protects lifetime wealth",
                            "diversification across uncorrelated asset classes serves as the primary cushion against volatility",
                            "liquidity reserves ensure you never have to liquidate assets during market distress",
                            "audited performance figures underscore how fee drag quietly erodes wealth over decades",
                        ]
                    elif any(t in niche_l for t in ("health", "fitness", "nutrition", "diet", "sleep", "workout")):
                        fact_bank = [
                            "metabolic research demonstrates how circadian rhythm directly regulates insulin sensitivity",
                            "clinical studies indicate that restorative deep sleep drives neural recovery and immune balance",
                            "cellular biology shows that gradual resistance training stimulates bone mineral density",
                            "nutritional science reveals that gut microbiome diversity supports systemic energy regulation",
                            "consistent hydration and electrolyte balance stabilize cognitive focus during physical stress",
                            "physiologists emphasize sustainable recovery protocols over extreme short-term exertion",
                        ]
                    elif any(t in niche_l for t in ("motivat", "habit", "mindset", "discipline", "productivity")):
                        fact_bank = [
                            "daily execution systems build durable momentum long after initial inspiration fades",
                            "high performers deliberately reduce friction to automate essential daily habits",
                            "psychological studies confirm that mental clarity follows physical action, not passive waiting",
                            "resilience is forged through deliberate exposure to manageable daily resistance",
                            "structuring deep work blocks protects focus from constant digital fragmentation",
                            "long-term mastery belongs to those who embrace the unglamorous consistency of routine",
                        ]
                    elif any(t in niche_l for t in ("space", "science", "artemis", "nasa", "astronomy", "physics")):
                        fact_bank = [
                            "laboratory telemetry isolates thermal thresholds governing reactions under extreme pressure",
                            "orbital mechanics dictate trajectory trimming passes across cislunar flight paths",
                            "ablative heat shield materials are engineered specifically to survive atmospheric reentry plasma",
                            "spectroscopic readings confirm molecular compositions matching theoretical predictive models",
                            "calibrated sensors eliminate external interference to confirm genuine physical measurements",
                            "instrumentation margins ensure full life-support redundancy throughout the mission timeline",
                        ]
                    elif any(t in niche_l for t in ("nature", "wildlife", "animal", "ocean", "predator", "jungle")):
                        fact_bank = [
                            "predator tracking patterns adapt instantly to seasonal herd movements across the terrain",
                            "underwater acoustics show how marine species coordinate navigation across vast distances",
                            "botanical defenses deploy chemical signals to deter threats across interconnected ecosystems",
                            "extreme biome survival relies on specialized insulation and reduced metabolic expenditure",
                            "ecosystem surveys highlight how keystone species maintain ecological equilibrium",
                            "aerial telemetry confirms instinctive navigation guided by natural geomagnetic cues",
                        ]
                    elif any(t in niche_l for t in ("myster", "crime", "unexplain", "detective", "secret", "horror")):
                        fact_bank = [
                            "investigators uncovered conflicting timelines between initial statements and physical records",
                            "forensic analysis recovered microscopic evidence that pointed toward an overlooked angle",
                            "archival files reveal an anomaly recorded hours before the incident was formally reported",
                            "cross-referencing eyewitness accounts exposed a critical gap in the official chronology",
                            "sealed documents describe unexpected movements that initial investigators failed to pursue",
                            "physical evidence and timeline mapping provided the missing link that altered the inquiry",
                        ]
                    elif any(t in niche_l for t in ("gadget", "tech", "phone", "review", "laptop")):
                        fact_bank = [
                            "chassis ergonomics and balanced weight distribution dictate comfortable all-day handling",
                            "thermal profiling demonstrates how sustained workloads impact processor clock speeds",
                            "display panel calibration delivers natural color balance and outdoor peak brightness",
                            "battery discharge curves confirm dependable endurance throughout demanding days",
                            "real-world sensor performance resolves fine edge details even in challenging backlighting",
                            "haptic response and tactile button feedback provide immediate physical reassurance",
                        ]
                    elif any(t in niche_l for t in ("histor", "ancient", "war", "civilization", "archaeolog")):
                        fact_bank = [
                            "excavated administrative records document trade networks spanning hundreds of miles",
                            "architectural analysis reveals sophisticated drainage systems beneath ancient avenues",
                            "pivotal battle records show how supply logistics determined the political outcome",
                            "inscribed stone tablets preserve legal agreements and civic responsibilities",
                            "metallurgical testing proves early artisans mastered precise furnace temperature control",
                            "eyewitness chronicles describe strategic decisions that transformed the royal court",
                        ]
                    else:
                        fact_bank = [
                            "verified findings demonstrate how this crucial factor directly shapes the final result",
                            "practical evidence confirms that subtle underlying mechanisms drive the broader outcome",
                            "field observations clarify distinctions that casual observers routinely overlook",
                            "in-depth analysis reveals how interconnected variables determine long-term success",
                            "concrete case studies show why conventional assumptions frequently fail in practice",
                            "systematic review reveals the pivotal dynamic behind this distinctive phenomenon",
                        ]
                    rewritten = ""
                    try:
                        from pipeline.llm_router import chat_text
                        prompt = (
                            f"Rewrite this documentary scene narration to be completely unique and engaging, "
                            f"specifically discussing '{topic_bit}' and visual '{sc.get('visual') or 'the subject'}'. "
                            f"Do NOT repeat prior lines. Length: 15 to 22 spoken words. Spoken narration only:\n\n"
                            f"Original: {sc.get('narration')}"
                        )
                        hit = chat_text(prompt, google_api_keys=google_keys, purpose="script")
                        candidate = (hit.get("text") or "").strip().strip('"')
                        if candidate and len(candidate.split()) >= 8:
                            rewritten = sanitize_spoken_narration(candidate)
                    except Exception as llm_exc:
                        logger.debug("Dialogue dynamic LLM rewrite fallback: %s", llm_exc)

                    if rewritten and not any(pair_overlap_ratio(rewritten, prev) >= 0.36 for prev in seen_ok):
                        sc["narration"] = rewritten
                    else:
                        fact = fact_bank[si % len(fact_bank)]
                        sc["narration"] = sanitize_spoken_narration(
                            f"Examining {topic_bit}, {fact}."
                        )
                        narr2 = str(sc.get("narration") or "")
                        if any(pair_overlap_ratio(narr2, prev) >= 0.36 for prev in seen_ok):
                            alt_fact = fact_bank[(si + 3) % len(fact_bank)]
                            sc["narration"] = sanitize_spoken_narration(
                                f"Looking deeper at {topic_bit}, {alt_fact}."
                            )
                if sc.get("narration"):
                    seen_ok.append(str(sc["narration"]))
            plan["scenes"] = scenes
            try:
                plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
    except Exception as exc:
        logger.warning("dialogue uniqueness sanitize skipped: %s", exc)

    # C05-GA: generation alignment fail-closed before scene providers
    try:
        from pipeline.trs_facade import assert_generation_alignment_preflight

        align = assert_generation_alignment_preflight(
            plan if isinstance(plan, dict) else {},
            require_dialogue_id=bool(trs_handoff),
            require_visual_binding=bool(trs_handoff),
            block_mandatory_coverage_none=False,
        )
        if align.get("blocked") and trs_handoff:
            raise RuntimeError(
                "generation_alignment_blocked:" + ",".join(align.get("blocks") or ["align_fail"])
            )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.warning("generation alignment preflight skipped: %s", exc)

    from pipeline.scene_runtime import SceneValidationError, assert_production_scenes_validated

    try:
        _canonical_scenes, scenes = assert_production_scenes_validated(
            plan if isinstance(plan, dict) else {},
            job_id=work.name,
            work_dir=work,
        )
        if isinstance(plan, dict):
            plan["scenes"] = scenes
            plan["script_id"] = _canonical_scenes[0].script_id if _canonical_scenes else plan.get("script_id")
    except SceneValidationError as exc:
        raise RuntimeError(f"scene_contract_blocked:{exc}") from exc

    _live("scenes", f"{len(scenes)} scenes — {planned_topic or niche}", total=len(scenes))

    # RCP-06B: bind duration contract (plan may carry target/max); persist for certification
    from pipeline.duration_budget import contract_from_plan

    if isinstance(plan, dict):
        duration_contract = contract_from_plan({**plan, "video_type": video_type})
        max_seconds = int(duration_contract["max_seconds"])
        plan_budget_seconds = int(duration_contract["target_seconds"])
        plan["duration_contract"] = duration_contract
        plan["max_seconds"] = max_seconds
        plan["target_duration_sec"] = plan_budget_seconds
    (work / "DURATION_CONTRACT.json").write_text(
        json.dumps(duration_contract, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        from pipeline.quality.trs_chain import persist_trs_chain_artifacts

        persist_trs_chain_artifacts(
            work,
            topic=str(plan.get("topic") or planned_topic or topic or ""),
            research=plan.get("research") if isinstance(plan.get("research"), dict) else None,
            fact_pack=plan.get("fact_pack") if isinstance(plan.get("fact_pack"), dict) else None,
            script_plan=plan if isinstance(plan, dict) else None,
            job_id=work.name,
        )
    except Exception as trs_exc:
        logger.warning("TRS chain persist soft-fail: %s", trs_exc)

    # Optional branded intro — keep under leading_silence gate (max ~0.7s)
    if channel.get("intro_path") and Path(channel["intro_path"]).exists():
        intro_norm = work / "intro_av.mp4"
        if not (intro_norm.exists() and intro_norm.stat().st_size > 5000):
            _intro_with_silence(Path(channel["intro_path"]), intro_norm, size, seconds=0.35)
        if intro_norm.exists():
            clips.append(intro_norm)

    scenes_produced = 0
    # RCP-06D: lock / verify VoiceIdentity before any scene TTS or ship path
    try:
        from pipeline.production_consistency import (
            assert_voice_identity_continuity_or_raise,
            extract_scene_voice_ref,
            resolve_canonical_voice_identity,
            voice_identity_from_mapping,
        )

        _vi = None
        if isinstance(plan, dict):
            _vi = voice_identity_from_mapping(plan.get("voice_identity") or {})
        if _vi is None:
            for _sc in scenes or []:
                if isinstance(_sc, dict) and _sc.get("voice_identity"):
                    _vi = voice_identity_from_mapping(_sc.get("voice_identity") or {})
                    if _vi:
                        break
        if _vi is None:
            _vi = resolve_canonical_voice_identity(
                language=str((plan or {}).get("language") or "en") if isinstance(plan, dict) else "en"
            )
        if isinstance(plan, dict):
            plan["voice_identity"] = _vi.to_dict()
        for _sc in scenes or []:
            if not isinstance(_sc, dict):
                continue
            ref = extract_scene_voice_ref(_sc)
            # Stamp only when scene has no voice contract yet (do not invent PASS for conflicts)
            if not ref.get("voice_identity_id") and not ref.get("voice_profile"):
                _sc["voice_identity"] = _vi.to_dict()
                _sc["voice_profile"] = _vi.vocal_profile
                _sc["voice_identity_id"] = _vi.voice_identity_id
                ap = _sc.get("audio_plan")
                if isinstance(ap, dict):
                    ap = dict(ap)
                    ap["voice_profile"] = _vi.vocal_profile
                    meta = dict(ap.get("metadata") or {})
                    meta["voice_identity_id"] = _vi.voice_identity_id
                    ap["metadata"] = meta
                    _sc["audio_plan"] = ap
        assert_voice_identity_continuity_or_raise(canonical=_vi, scene_refs=list(scenes or []))
    except RuntimeError:
        raise
    except Exception as _vi_exc:
        raise RuntimeError(f"VOICE_IDENTITY_CONTINUITY_BLOCKED:preflight:{type(_vi_exc).__name__}") from _vi_exc

    for idx, scene in enumerate(scenes):
        narr = scene["narration"]
        element = scene.get("element") or "feature"
        from pipeline.trs_facade import resolve_canonical_visual_prompt

        vis_res = resolve_canonical_visual_prompt(scene if isinstance(scene, dict) else {}, narration=narr)
        canonical_visual = str(vis_res.get("prompt") or "")
        fp = clip_fingerprint(
            narration=narr,
            visual_prompt=canonical_visual,
            element=element,
            size=size,
        )
        existing_clip = work / f"scene_{idx:02d}_{element}.mp4"
        cand_ok, why = should_reuse_existing_clip(
            existing_clip, work=work, idx=idx, element=element, fingerprint=fp
        )
        reuse_ok = bool(cand_ok)
        if (
            not reuse_ok
            and why not in ("agent_failed", "fingerprint_mismatch")
            and existing_clip.exists()
            and existing_clip.stat().st_size > 20000
        ):
            try:
                from pipeline.av_quality_gates import any_hard_gate_failed
                from pipeline.av_self_repair_agent import diagnose_clip

                _live(
                    "scene",
                    f"Agent check scene {idx + 1}/{len(scenes)} — existing clip",
                    scene=idx + 1,
                    total=len(scenes),
                )
                diag = diagnose_clip(
                    existing_clip,
                    narration=narr,
                    lang="en",
                    prompt=canonical_visual,
                    product_name=planned_topic,
                    keywords=list(scene.get("keyword_triggers") or plan.get("keywords") or []),
                    work=work,
                    idx=idx,
                )
                if diag.get("passed") and not any_hard_gate_failed(diag):
                    reuse_ok = True
                    why = "agent_pass"
                    try:
                        write_resume_meta(work, idx, element, fingerprint=fp, extra={"agent_passed": True})
                    except Exception:
                        pass
                else:
                    logger.warning(
                        "Scene %s existing clip failed agent analysis %s — regenerating",
                        idx,
                        diag.get("hard_hits") or diag.get("critical_issues"),
                    )
            except Exception as exc:
                logger.warning("Resume agent check failed for scene %s (%s) — regenerating", idx, exc)

        if reuse_ok:
            _live(
                "scene",
                f"Reusing scene {idx + 1}/{len(scenes)} — already generated",
                scene=idx + 1,
                total=len(scenes),
            )
            logger.info("Skip regen scene %s (%s)", idx, why)
            try:
                import os

                if not amp_skip_active("AMP_SKIP_LOCALIZE"):
                    from pipeline.lang_entitlement import channel_languages
                    from pipeline.localization import localize_scene_clip

                    _langs = channel_languages(channel)
                    pack = work / "SCENE_LOCAL" / f"{idx:02d}"
                    if len(_langs) > 1 and not (pack / "manifest.json").exists():
                        loc_res = localize_scene_clip(
                            scene_video=existing_clip,
                            english_narration=narr,
                            scene_idx=idx,
                            work=work,
                            google_api_keys=google_keys,
                            languages=_langs,
                            size=size,
                            pollinations_key=pollinations_key or "",
                        )
                        if isinstance(loc_res, dict) and loc_res.get("ok") is False:
                            raise RuntimeError(
                                f"scene_localize_incomplete:{idx}:"
                                + ",".join(
                                    k
                                    for k, v in (loc_res.get("languages") or {}).items()
                                    if isinstance(v, dict) and not v.get("ok")
                                )
                            )
            except Exception as loc_exc:
                # Multilingual: prefer per-scene packs, but allow master remux fallback when
                # AMP_MASTER_LOCALIZE_FALLBACK=1 (cert / stock-doc path) instead of aborting mid-job.
                _ml = False
                try:
                    from pipeline.lang_entitlement import channel_languages as _cl

                    _ml = len([x for x in _cl(channel) if str(x).lower()[:2] != "en"]) >= 1
                except Exception:
                    _ml = False
                # AMP_MASTER_LOCALIZE_FALLBACK=1: allow master-level localize instead of per-scene
                # (useful for cert/stock-doc paths where per-scene packs aren't required)
                soft = str(os.environ.get("AMP_MASTER_LOCALIZE_FALLBACK", "") or "").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                )
                if _ml and not soft:
                    logger.error("per-scene localize (reuse) failed closed scene %s: %s", idx, loc_exc)
                    raise RuntimeError(f"scene_localize_failed:{idx}:{loc_exc}") from loc_exc
                # FIX: removed duplicate log — keep only one warning
                logger.warning(
                    "per-scene localize (reuse) skipped scene %s (AMP_MASTER_LOCALIZE_FALLBACK active): %s",
                    idx,
                    loc_exc,
                )
            try:
                existing_clip = _observe_and_maybe_repair_semantic(
                    work=work,
                    idx=idx,
                    scene=scene if isinstance(scene, dict) else {},
                    clip=existing_clip,
                    narr=narr,
                    canonical_visual=canonical_visual,
                    element=element,
                    size=size,
                    audio=None,
                    google_keys=google_keys,
                    planned_topic=planned_topic or str(plan.get("topic") or topic or ""),
                    niche=niche,
                    pexels_key=pexels_key or "",
                    pollinations_key=pollinations_key or "",
                    agnes_keys=agnes_keys,
                    allow_image_fallback=allow_image_fallback,
                    customer_id=customer_id or "",
                    channel_id=str(channel_id or ""),
                    language_entitlement=language_entitlement or "",
                    channel=channel if isinstance(channel, dict) else {},
                    plan=plan if isinstance(plan, dict) else {},
                    video_type=video_type,
                )
            except Exception as sem_exc:
                logger.warning("Scene %s semantic coverage (reuse) failed: %s", idx, sem_exc)
            clips.append(existing_clip)
            scenes_produced += 1
            av_report.append(_load_scene_av_summary(work, idx, element, resumed=True))
            total = sum(ffprobe_duration(c) for c in clips)
            raise_if_budget_would_drop_scenes(
                scene_index=idx,
                scene_count=len(scenes),
                accumulated_sec=total,
                max_seconds=max_seconds,
            )
            continue

        _live(
            "scene",
            f"Scene {idx + 1}/{len(scenes)} — {element}"
            + (" (regen after agent fail)" if why == "agent_failed" else ""),
            scene=idx + 1,
            total=len(scenes),
        )

        audio_path = work / f"narration_{idx:02d}"
        audio = None
        for ext in (".m4a", ".wav", ".mp3"):
            cand = audio_path.with_suffix(ext)
            if cand.exists() and cand.stat().st_size > 1000:
                audio = cand
                logger.info("Reusing TTS audio scene %s: %s", idx, cand.name)
                break
        sidecar = audio_path.with_suffix(".txt")
        if audio is not None:
            stored = sidecar.read_text(encoding="utf-8") if sidecar.exists() else ""
            lang_repaired = bool(plan.get("master_lang_repairs") or plan.get("master_lang_force_fallback"))
            if sidecar.exists() and not narration_sidecar_matches(stored, narr):
                logger.info("TTS sidecar mismatch scene %s — regenerating English audio", idx)
                audio = None
            elif not sidecar.exists() and (lang_repaired or not looks_like_english_master(narr)):
                logger.info("TTS missing sidecar after language lock scene %s — regenerating", idx)
                audio = None
        if audio is None:
            try:
                _live("tts", f"TTS scene {idx + 1}", api="tts", action=f"scene_{idx}")
                try:
                    from pipeline.idempotency.tts_bridge import idempotent_synthesize_narration
                    from pipeline.production_consistency import resolve_locked_tts_voice_name

                    audio = idempotent_synthesize_narration(
                        work,
                        job_id=work.name,
                        scene_id=idx,
                        dialogue_text=narr,
                        out_path=audio_path,
                        google_api_keys=google_keys,
                        voice_name=resolve_locked_tts_voice_name(
                            scene,
                            canonical=plan.get("voice_identity") or scene.get("voice_identity"),
                        ),
                        language_hint=str(
                            (scene.get("audio_plan") or {}).get("language")
                            or scene.get("language")
                            or "en"
                        ),
                        dialogue_id=str(
                            scene.get("dialogue_id")
                            or scene.get("c05s_dialogue_id")
                            or f"scene-{idx:02d}"
                        ),
                        emotion=str(
                            (scene.get("audio_plan") or {}).get("emotion")
                            or scene.get("emotional_intent")
                            or scene.get("emotion")
                            or "neutral"
                        ),
                    )
                except Exception as bridge_exc:
                    # H3 DEF-H3-002: canonical path is tts_bridge; legacy direct synthesize only once
                    # and never for deterministic config/auth failures.
                    from pipeline.idempotency.retry_policy import RetryClass, classify_error
                    from pipeline.idempotency.metrics import UsageEvent, record_usage_event

                    rc = classify_error(bridge_exc)
                    if rc == RetryClass.NON_RETRYABLE:
                        raise
                    if audio_path.exists() and audio_path.stat().st_size > 1000:
                        audio = audio_path
                        logger.info("tts_bridge failed but artifact present — reuse %s", audio_path.name)
                    else:
                        logger.warning(
                            "tts_bridge failed (%s) — legacy synthesize_narration once",
                            str(bridge_exc)[:120],
                        )
                        try:
                            from pipeline.idempotency.store import IdempotencyStore

                            IdempotencyStore(work / "idempotency").increment_metric("tts_legacy_fallback")
                        except Exception:
                            pass
                        record_usage_event(
                            work,
                            UsageEvent(
                                operation="tts_legacy_fallback",
                                provider="google_tts_direct",
                                call_count=1,
                                detail=str(bridge_exc)[:80],
                            ),
                        )
                        audio = synthesize_narration(
                            narr,
                            audio_path,
                            google_api_keys=google_keys,
                            voice_name="",
                            language_hint="en",
                        )
                try:
                    sidecar.write_text(
                        f"voice=Charon\n{narr.strip()}\n",
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            except Exception as exc:
                raise RuntimeError(f"Google AI Studio TTS failed at scene {idx}: {exc}") from exc

        _live("visual", f"Visual scene {idx + 1}", api="media", action=f"scene_{idx}")
        from pipeline.media_mode_engine import require_agnes_for_mode

        scene_visual_mode = str(scene.get("visual_mode") or "").strip().upper() or "VIDEO"
        scene_require_agnes = require_agnes_for_mode(
            scene_visual_mode, allow_image_fallback=allow_image_fallback
        )
        clip = build_dialogue_clip(
            work=work,
            idx=idx,
            narration_audio=audio,
            visual_query=scene.get("visual_query") or plan.get("topic") or "gadget",
            visual_prompt=canonical_visual or narr,
            element=element,
            size=size,
            product_name=planned_topic or str(plan.get("topic") or topic or ""),
            pexels_api=pexels_key or channel.get("pexels_api") or "",
            pollinations_key=pollinations_key or channel.get("pollinations_api") or "",
            agnes_api=agnes_keys[0] if agnes_keys else (channel.get("agnes_api") or ""),
            agnes_api_keys=agnes_keys,
            google_api_keys=google_keys,
            subtitle_text="",
            narration=narr,
            keyword_triggers=scene.get("keyword_triggers") or [],
            exact_ai_video_prompt=canonical_visual,
            niche=niche,
            max_av_retries=min(1, int(channel.get("max_av_retries") or 1)),
            require_agnes=scene_require_agnes,
            allow_image_fallback=allow_image_fallback if not scene_require_agnes else allow_image_fallback,
            job_id=work.name,
            dialogue_id=scene.get("dialogue_id") or "",
            canonical_scene_id=scene.get("canonical_scene_id") or "",
            script_id=str(scene.get("script_id") or plan.get("script_id") or ""),
            visual_mode=scene_visual_mode,
            scene_context={
                **(scene if isinstance(scene, dict) else {}),
                "visual_mode": scene_visual_mode,
                "customer_id": customer_id or scene.get("customer_id") or "",
                "channel_id": str(channel_id or scene.get("channel_id") or ""),
                "language_entitlement": language_entitlement or scene.get("language_entitlement") or "",
            },
            customer_id=customer_id,
            channel_id=str(channel_id or ""),
            language_entitlement=language_entitlement,
        )
        if clip.exists():
            try:
                write_resume_meta(
                    work, idx, element, fingerprint=fp, extra={"agent_passed": True}
                )
                clear_scene_fail_marker(work, idx)
            except Exception:
                pass
            # Per-scene localize: burn matching-language subtitles into THIS scene only
            try:
                import os

                if not amp_skip_active("AMP_SKIP_LOCALIZE"):
                    from pipeline.lang_entitlement import channel_languages
                    from pipeline.localization import localize_scene_clip

                    _langs = channel_languages(channel)
                    if len(_langs) > 1:
                        loc_res = localize_scene_clip(
                            scene_video=clip,
                            english_narration=narr,
                            scene_idx=idx,
                            work=work,
                            google_api_keys=google_keys,
                            languages=_langs,
                            size=size,
                            pollinations_key=pollinations_key or "",
                        )
                        if isinstance(loc_res, dict) and loc_res.get("ok") is False:
                            raise RuntimeError(
                                f"scene_localize_incomplete:{idx}:"
                                + ",".join(
                                    k
                                    for k, v in (loc_res.get("languages") or {}).items()
                                    if isinstance(v, dict) and not v.get("ok")
                                )
                            )
            except Exception as loc_exc:
                _ml = False
                try:
                    from pipeline.lang_entitlement import channel_languages as _cl

                    _ml = len([x for x in _cl(channel) if str(x).lower()[:2] != "en"]) >= 1
                except Exception:
                    _ml = False
                soft = str(os.environ.get("AMP_MASTER_LOCALIZE_FALLBACK", "") or "").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                )
                if _ml and not soft:
                    logger.error("per-scene localize failed closed scene %s: %s", idx, loc_exc)
                    raise RuntimeError(f"scene_localize_failed:{idx}:{loc_exc}") from loc_exc
                logger.warning(
                    "per-scene localize soft-continue scene %s: %s (master localize fallback)",
                    idx,
                    loc_exc,
                )
            try:
                clip = _observe_and_maybe_repair_semantic(
                    work=work,
                    idx=idx,
                    scene=scene if isinstance(scene, dict) else {},
                    clip=clip,
                    narr=narr,
                    canonical_visual=canonical_visual,
                    element=element,
                    size=size,
                    audio=audio,
                    google_keys=google_keys,
                    planned_topic=planned_topic or str(plan.get("topic") or topic or ""),
                    niche=niche,
                    pexels_key=pexels_key or "",
                    pollinations_key=pollinations_key or "",
                    agnes_keys=agnes_keys,
                    allow_image_fallback=allow_image_fallback,
                    customer_id=customer_id or "",
                    channel_id=str(channel_id or ""),
                    language_entitlement=language_entitlement or "",
                    channel=channel if isinstance(channel, dict) else {},
                    plan=plan if isinstance(plan, dict) else {},
                    video_type=video_type,
                )
            except Exception as sem_exc:
                logger.warning("Scene %s semantic coverage hook failed: %s", idx, sem_exc)
            clips.append(clip)
            scenes_produced += 1
            av_report.append(_load_scene_av_summary(work, idx, element, resumed=False))
            total = sum(ffprobe_duration(c) for c in clips)
            raise_if_budget_would_drop_scenes(
                scene_index=idx,
                scene_count=len(scenes),
                accumulated_sec=total,
                max_seconds=max_seconds,
            )

    if not clips:
        raise RuntimeError("No scene clips produced")

    # RCP-06B: never ship with silently dropped planned scenes
    assert_all_planned_scenes_produced(
        planned_scene_count_n=len(scenes),
        produced_scene_count=scenes_produced,
    )

    # RCP-03 job-level semantic gate (UNKNOWN/FAIL never silently PASS)
    try:
        from pipeline.semantic_coverage import evaluate_job_semantic_gate

        sem_gate = evaluate_job_semantic_gate(work)
        sem_payload = json.dumps(sem_gate, indent=2, ensure_ascii=False)
        (work / "SEMANTIC_COVERAGE_GATE.json").write_text(sem_payload, encoding="utf-8")
        # RCP-06A: dual-write legacy alias so publishability bridge never sees ABSENT by filename mismatch
        (work / "SEMANTIC_GATE.json").write_text(sem_payload, encoding="utf-8")
        sem_verdict = str(sem_gate.get("verdict") or "UNKNOWN").upper()
        soft_unknown = str(os.environ.get("AMP_SEMANTIC_UNKNOWN_SOFT", "") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if sem_gate.get("blocking") and sem_verdict == "FAIL":
            soft_fail = soft_unknown  # same cert flag: observer noise must not kill live compose
            if soft_fail:
                logger.warning(
                    "SEMANTIC_COVERAGE_GATE FAIL soft-continue (%s) AMP_SEMANTIC_UNKNOWN_SOFT=1",
                    sem_gate.get("reason"),
                )
                sem_gate = {
                    **sem_gate,
                    "blocking": False,
                    "soft_continue": True,
                    "soft_reason": "AMP_SEMANTIC_UNKNOWN_SOFT",
                    "original_verdict": "FAIL",
                }
                (work / "SEMANTIC_COVERAGE_GATE.json").write_text(
                    json.dumps(sem_gate, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                (work / "SEMANTIC_GATE.json").write_text(
                    json.dumps(sem_gate, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            else:
                logger.error("SEMANTIC_COVERAGE_GATE FAIL — %s", sem_gate.get("reason"))
                raise RuntimeError(f"SEMANTIC_COVERAGE_BLOCKED:{sem_gate.get('reason')}")
        elif sem_gate.get("blocking") and sem_verdict == "UNKNOWN":
            if soft_unknown:
                # Cert/live documentary: Gemini/file-observer quota often yields UNKNOWN.
                # Continue compose; gate artifact remains honest UNKNOWN for operators.
                logger.warning(
                    "SEMANTIC_COVERAGE_GATE UNKNOWN soft-continue (%s) AMP_SEMANTIC_UNKNOWN_SOFT=1",
                    sem_gate.get("reason"),
                )
                sem_gate = {
                    **sem_gate,
                    "blocking": False,
                    "soft_continue": True,
                    "soft_reason": "AMP_SEMANTIC_UNKNOWN_SOFT",
                }
                (work / "SEMANTIC_COVERAGE_GATE.json").write_text(
                    json.dumps(sem_gate, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                (work / "SEMANTIC_GATE.json").write_text(
                    json.dumps(sem_gate, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            else:
                logger.error(
                    "SEMANTIC_COVERAGE_GATE UNKNOWN — observation incomplete; blocking compose (%s)",
                    sem_gate.get("reason"),
                )
                raise RuntimeError(f"SEMANTIC_COVERAGE_BLOCKED:UNKNOWN:{sem_gate.get('reason')}")
        elif sem_verdict != "PASS" and not soft_unknown:
            logger.error("SEMANTIC_COVERAGE_GATE not PASS (%s) — blocking compose", sem_verdict)
            raise RuntimeError(f"SEMANTIC_COVERAGE_BLOCKED:NOT_PASS:{sem_verdict}")
    except RuntimeError:
        raise
    except Exception as gate_exc:
        # RCP-06A: fail-closed — cannot certify semantic if gate write/eval failed
        logger.error("semantic coverage gate failed closed: %s", gate_exc)
        raise RuntimeError(f"SEMANTIC_COVERAGE_BLOCKED:gate_error:{gate_exc}") from gate_exc

    _live("compose", "Concat + logo + trim", api="ffmpeg", action="compose")
    report_path = work / "plan_av_report.json"
    report_path.write_text(
        json.dumps(
            {
                "topic": planned_topic,
                "niche": niche,
                "scenes": av_report,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    body = work / "body_av.mp4"
    logo = Path(channel["logo_path"]) if channel.get("logo_path") else None
    try:
        from pipeline.idempotency.render_bridge import idempotent_compose_final_video

        final = idempotent_compose_final_video(
            work,
            job_id=work.name,
            clips=clips,
            logo=logo,
            video_type=video_type,
            size=size,
            max_seconds=max_seconds,
        )
    except Exception as exc:
        logger.warning("render_bridge failed (%s) — legacy compose", str(exc)[:120])
        concat_av_clips(clips, body, size)
        branded = work / "branded_av.mp4"
        mix_logo_safe(body, logo, branded)
        final = work / f"final_{video_type}.mp4"
        _trim_reencode(branded if branded.exists() else body, final, max_seconds, size)

    # Master audio with royalty-free BGM sidechain ducking (-14dB to -18dB) under dialogue
    try:
        from pipeline.bgm_ducking import apply_bgm_ducking

        ducked_final = work / f"final_{video_type}_mastered.mp4"
        final = apply_bgm_ducking(final, ducked_final, niche=str(niche or ""), duck_db=-16.0)
    except Exception as bgm_exc:
        logger.warning("BGM ducking soft fallback: %s", bgm_exc)

    duration = ffprobe_duration(final)
    # Gate A: reconcile observed final duration vs duration_budget contract (never treat planned as actual)
    duration_reconciliation: dict = {}
    try:
        from pipeline.duration_budget import (
            reconcile_rendered_duration,
            raise_if_rendered_duration_blocks,
            write_duration_reconciliation,
        )

        _planned_proxy = None
        try:
            _planned_proxy = float(
                (duration_contract or {}).get("target_seconds")
                or plan_budget_seconds
                or 0
            ) or None
        except Exception:
            _planned_proxy = None
        duration_reconciliation = reconcile_rendered_duration(
            actual_duration_sec=float(duration) if duration is not None else None,
            contract=duration_contract if isinstance(duration_contract, dict) else {},
            scene_count=len(scenes) if isinstance(scenes, list) else None,
            planned_duration_sec=_planned_proxy,
        )
        write_duration_reconciliation(work, duration_reconciliation)
        raise_if_rendered_duration_blocks(reconciliation=duration_reconciliation)
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("duration reconciliation failed closed: %s", exc)
        raise RuntimeError(f"duration_reconciliation_error:{exc}") from exc

    # Validate audio stream exists
    if not _has_audio(final):
        raise RuntimeError("Final video has no audio stream — pipeline bug")

    en_narr = " ".join(
        str(s.get("narration") or "") for s in scenes if isinstance(s, dict)
    ).strip()
    try:
        from pipeline.dialogue_uniqueness import sanitize_spoken_narration

        en_narr = sanitize_spoken_narration(en_narr)
    except Exception:
        pass

    # Hard ship gate — do not mark ready_to_upload if master is broken
    ship: dict = {}
    try:
        from pipeline.av_quality_gates import evaluate_master_shippable

        ship = evaluate_master_shippable(
            media=final,
            scenes=scenes,
            work_dir=work,
            niche=str(niche or ""),
            narration_text=en_narr,
        )
        (work / "MASTER_SHIP_GATE.json").write_text(
            json.dumps(ship, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        if ship.get("unshippable") or not ship.get("ok"):
            logger.error("Master unshippable: %s", ship.get("critical_issues") or ship.get("issues"))
            raise RuntimeError(
                "master_unshippable:"
                + ",".join(ship.get("critical_issues") or ship.get("issues") or ["quality_failed"])
            )
    except RuntimeError:
        raise
    except Exception as exc:
        # Fail-closed: a broken gate must not ship as ready_to_upload
        logger.error("master ship gate failed closed: %s", exc)
        try:
            from pipeline.error_notebook import note_exception

            note_exception(
                subsystem="quality_gate",
                exc=exc,
                fault_code="master_ship_gate_exception",
                channel_id=int(channel.get("id") or 0) or None,
            )
        except Exception:
            pass
        raise RuntimeError(f"master_ship_gate_error:{exc}") from exc

    try:
        from pipeline.localization import write_srt

        if en_narr:
            en_audio = work / "narration_en_tts.m4a"
            if not en_audio.is_file():
                en_audio = work / "narration_en_from_agnes.m4a"
            if not en_audio.is_file():
                en_audio = final
            write_srt(
                en_narr,
                en_audio,
                work / "english_master.srt",
                work_dir=work,
                job_id=work.name,
                scene_id="master",
                dialogue_id="master-en",
                language="en",
            )
    except Exception as exc:
        logger.warning("English master SRT sidecar skipped: %s", exc)

    # AMP-004 Phase-04: industrial artifact verification (observe actual media) before publishability
    artifact_gate: dict = {}
    try:
        from pipeline.artifact_verification.production import run_production_artifact_verification

        artifact_gate = run_production_artifact_verification(
            work,
            final_path=Path(final) if final else None,
            scenes=scenes if isinstance(scenes, list) else [],
            job_id=work.name,
        )
        if str(artifact_gate.get("status") or "").upper() in ("BLOCKED", "FAIL", "FAILED"):
            logger.error("Artifact verification blocked: %s", artifact_gate.get("reason"))
            raise RuntimeError(
                "artifact_verification_blocked:"
                + str(artifact_gate.get("reason") or "artifact_fail")
            )
        if str(artifact_gate.get("status") or "").upper() == "UNKNOWN":
            logger.error("Artifact verification UNKNOWN (unverified): %s", artifact_gate.get("reason"))
            raise RuntimeError(
                "artifact_verification_unknown:"
                + str(artifact_gate.get("reason") or "unverified_final")
            )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("Artifact verification failed closed: %s", exc)
        raise RuntimeError(f"artifact_verification_error:{exc}") from exc

    # AMP-004 Phase-05: industrial audio design observation + gate
    audio_design_gate: dict = {}
    try:
        from pipeline.audio_design.production import run_production_audio_design_gate

        audio_design_gate = run_production_audio_design_gate(
            work,
            job_id=work.name,
            final_audio_or_video=Path(final) if final else None,
        )
        if str(audio_design_gate.get("status") or "").upper() in ("BLOCKED", "FAIL", "FAILED"):
            logger.error("Audio design gate blocked: %s", audio_design_gate.get("issues"))
            raise RuntimeError(
                "audio_design_blocked:"
                + ",".join(audio_design_gate.get("issues") or ["audio_fail"])
            )
        if str(audio_design_gate.get("status") or "").upper() == "UNKNOWN":
            logger.error("Audio design UNKNOWN: %s", audio_design_gate.get("issues"))
            raise RuntimeError(
                "audio_design_unknown:"
                + ",".join(audio_design_gate.get("issues") or ["unverified_audio"])
            )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("Audio design gate failed closed: %s", exc)
        raise RuntimeError(f"audio_design_error:{exc}") from exc

    # Phase 6H → production: faster-whisper ASR evidence (UNKNOWN ≠ PASS; FAIL → repair → re-observe)
    audio_asr_gate: dict = {}
    try:
        from pipeline.observation.audio_evidence.production import run_production_audio_asr_gate
        from pipeline.observation.audio_evidence.repair_loop import execute_asr_repair_and_reobserve

        audio_asr_gate = run_production_audio_asr_gate(
            work,
            job_id=work.name,
            final_path=Path(final) if final else None,
            scenes=scenes if isinstance(scenes, list) else [],
            language_hint="en",
            customer_id=str((channel or {}).get("owner_login_id") or ""),
            channel_id=str(channel_id or (channel or {}).get("id") or ""),
        )
        asr_st = str(audio_asr_gate.get("status") or "UNKNOWN").upper()
        if asr_st in ("FAIL", "FAILED", "BLOCKED"):
            logger.warning(
                "Audio ASR FAIL — attempting scoped AUDIO_ASSET repair + re-observe: %s",
                audio_asr_gate.get("issues"),
            )

            def _synth_scene(idx: int, narr_text: str):
                from pipeline.idempotency.tts_bridge import idempotent_synthesize_narration
                from pipeline.production_consistency import resolve_locked_tts_voice_name

                sc = {}
                if isinstance(scenes, list) and 0 <= idx < len(scenes) and isinstance(scenes[idx], dict):
                    sc = scenes[idx]
                out_base = work / f"narration_{idx:02d}"
                return idempotent_synthesize_narration(
                    work,
                    job_id=work.name,
                    scene_id=idx,
                    dialogue_text=narr_text,
                    out_path=out_base,
                    google_api_keys=google_keys,
                    voice_name=resolve_locked_tts_voice_name(
                        sc,
                        canonical=(plan.get("voice_identity") if isinstance(plan, dict) else None)
                        or sc.get("voice_identity"),
                    ),
                    language_hint=str(
                        (sc.get("audio_plan") or {}).get("language") or sc.get("language") or "en"
                    ),
                    dialogue_id=str(
                        sc.get("dialogue_id") or sc.get("c05s_dialogue_id") or f"scene-{idx:02d}"
                    ),
                    emotion=str(
                        (sc.get("audio_plan") or {}).get("emotion")
                        or sc.get("emotional_intent")
                        or sc.get("emotion")
                        or "neutral"
                    ),
                )

            audio_asr_gate = execute_asr_repair_and_reobserve(
                work,
                gate=audio_asr_gate,
                scenes=scenes if isinstance(scenes, list) else [],
                google_keys=google_keys or [],
                run_asr_gate=run_production_audio_asr_gate,
                synthesize_scene=_synth_scene,
                max_attempts=2,
                job_id=work.name,
                final_path=Path(final) if final else None,
                language_hint="en",
                customer_id=str((channel or {}).get("owner_login_id") or ""),
                channel_id=str(channel_id or (channel or {}).get("id") or ""),
            )
            asr_st = str(audio_asr_gate.get("status") or "UNKNOWN").upper()
            if asr_st in ("FAIL", "FAILED", "BLOCKED"):
                logger.error("Audio ASR evidence FAIL after repair: %s", audio_asr_gate.get("issues"))
                raise RuntimeError(
                    "audio_asr_blocked:"
                    + ",".join(audio_asr_gate.get("issues") or ["asr_fail"])
                )
        if asr_st == "UNKNOWN":
            logger.warning(
                "Audio ASR evidence UNKNOWN (not treated as PASS): %s",
                audio_asr_gate.get("issues"),
            )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.warning("Audio ASR gate soft-failed to UNKNOWN: %s", exc)
        audio_asr_gate = {
            "status": "UNKNOWN",
            "issues": [f"asr_gate_error:{exc}"],
            "unknown_as_pass": False,
        }

    # Phase 6A → production: PySceneDetect scene-boundary observation (evidence only)
    scene_boundary_gate: dict = {}
    try:
        from pipeline.observation.scene_boundary.production import (
            run_production_scene_boundary_gate,
        )

        scene_boundary_gate = run_production_scene_boundary_gate(
            work,
            job_id=work.name,
            final_path=Path(final) if final else None,
            scenes=scenes if isinstance(scenes, list) else [],
        )
        sb_st = str(scene_boundary_gate.get("status") or "UNKNOWN").upper()
        if sb_st == "UNKNOWN":
            logger.warning(
                "Scene boundary observation UNKNOWN (not authority): %s",
                scene_boundary_gate.get("issues"),
            )
        else:
            logger.info(
                "Scene boundary observation status=%s tool=%s observed=%s planned=%s",
                sb_st,
                scene_boundary_gate.get("tool"),
                scene_boundary_gate.get("observed_scene_count"),
                scene_boundary_gate.get("planned_beat_count"),
            )
    except Exception as exc:
        logger.warning("Scene boundary gate soft-failed to UNKNOWN: %s", exc)
        scene_boundary_gate = {
            "status": "UNKNOWN",
            "issues": [f"scene_boundary_error:{exc}"],
            "is_production_authority": False,
            "unknown_as_pass": False,
        }

    # Optional CLIP/FAISS readiness evidence (UNAVAILABLE ≠ PASS)
    try:
        from pipeline.retrieval.backend_gate import run_retrieval_backend_gate

        run_retrieval_backend_gate(work)
    except Exception as exc:
        logger.debug("retrieval backend gate skipped: %s", exc)

    # Final-master Gemini video understanding (evidence; UNKNOWN on provider fail)
    try:
        from pipeline.observation.final_video_review import run_final_video_gemini_review

        fin_rev = run_final_video_gemini_review(
            work,
            final_path=Path(final) if final else None,
            job_id=work.name,
        )
        if str(fin_rev.get("status") or "").upper() == "UNKNOWN":
            logger.warning(
                "Final Gemini review UNKNOWN (not treated as PASS): %s",
                fin_rev.get("issues"),
            )
    except Exception as exc:
        logger.warning("Final Gemini review soft-failed: %s", exc)

    # AMP-004 Phase-06: localization / subtitle / text consistency gate
    localization_gate: dict = {}
    multilingual = False
    try:
        from pipeline.localization_consistency.production import run_production_localization_gate
        from pipeline.lang_entitlement import channel_languages

        langs = []
        try:
            langs = channel_languages(channel) if channel else []
        except Exception:
            langs = []
        multilingual = len([x for x in (langs or []) if str(x).lower()[:2] != "en"]) >= 1 and len(langs or []) > 1
        localization_gate = run_production_localization_gate(
            work,
            job_id=work.name,
            multilingual=multilingual,
            final_path=Path(final) if final else None,
        )
        loc_st = str(localization_gate.get("status") or "ABSENT").upper()
        if loc_st in ("BLOCKED", "FAIL", "FAILED"):
            logger.error("Localization gate blocked: %s", localization_gate.get("issues"))
            raise RuntimeError(
                "localization_blocked:"
                + ",".join(localization_gate.get("issues") or ["localization_fail"])
            )
        if loc_st == "UNKNOWN" and multilingual:
            logger.error("Localization UNKNOWN (mandatory): %s", localization_gate.get("issues"))
            raise RuntimeError(
                "localization_unknown:"
                + ",".join(localization_gate.get("issues") or ["unverified_localization"])
            )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("Localization gate failed closed: %s", exc)
        raise RuntimeError(f"localization_gate_error:{exc}") from exc

    # AMP-004 Phase-07: creative production / retention gate
    creative_production_gate: dict = {}
    try:
        from pipeline.creative_production.production import run_production_creative_gate

        creative_production_gate = run_production_creative_gate(
            work,
            job_id=work.name,
            plan=plan if isinstance(plan, dict) else {},
            final_path=Path(final) if final else None,
        )
        cr_st = str(creative_production_gate.get("status") or "UNKNOWN").upper()
        if cr_st in ("BLOCKED", "FAIL", "FAILED", "BLOCK"):
            logger.error("Creative production gate blocked: %s", creative_production_gate.get("issues"))
            raise RuntimeError(
                "creative_production_blocked:"
                + ",".join(creative_production_gate.get("issues") or ["creative_fail"])
            )
        if cr_st == "UNKNOWN":
            logger.error("Creative production UNKNOWN: %s", creative_production_gate.get("issues"))
            raise RuntimeError(
                "creative_production_unknown:"
                + ",".join(creative_production_gate.get("issues") or ["unverified_creative"])
            )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("Creative production gate failed closed: %s", exc)
        raise RuntimeError(f"creative_production_gate_error:{exc}") from exc

    # AMP-004 Phase-08: rendering integrity gate (Layer-E observe of final)
    rendering_integrity_gate: dict = {}
    try:
        from pipeline.rendering_integrity.production import run_production_rendering_gate

        rendering_integrity_gate = run_production_rendering_gate(
            work,
            job_id=work.name,
            final_path=Path(final) if final else None,
            size=str(size or size_for_video_type(video_type)),
            video_type=str(video_type or "short"),
            require_output=True,
        )
        ri_st = str(rendering_integrity_gate.get("status") or "UNKNOWN").upper()
        if ri_st in ("BLOCKED", "FAIL", "FAILED", "BLOCK"):
            logger.error("Rendering integrity gate blocked: %s", rendering_integrity_gate.get("issues"))
            raise RuntimeError(
                "rendering_integrity_blocked:"
                + ",".join(rendering_integrity_gate.get("issues") or ["render_fail"])
            )
        if ri_st == "UNKNOWN":
            logger.error("Rendering integrity UNKNOWN: %s", rendering_integrity_gate.get("issues"))
            raise RuntimeError(
                "rendering_integrity_unknown:"
                + ",".join(rendering_integrity_gate.get("issues") or ["unverified_render"])
            )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("Rendering integrity gate failed closed: %s", exc)
        raise RuntimeError(f"rendering_integrity_gate_error:{exc}") from exc

    # BUILD-04F: Creative quality gate + audience + publishability (fail-closed before ready_to_upload)
    creative_report: dict = {}
    publishability: dict = {}
    audience_gate: dict = {}
    try:
        from pipeline.quality.bridge import run_creative_quality_gate, run_publishability_gate
        from pipeline.quality.audience_quality import run_audience_quality_gate
        from pipeline.quality.lineage_audit import persist_lineage_audit

        creative_report = run_creative_quality_gate(
            work,
            job_id=work.name,
            plan=plan if isinstance(plan, dict) else {},
            technical_ship=ship,
        )
        audience_gate = run_audience_quality_gate(
            work,
            plan=plan if isinstance(plan, dict) else {},
            scene_boundary_gate=scene_boundary_gate if isinstance(scene_boundary_gate, dict) else {},
            creative_report=creative_report,
        )
        # RCP-06A: explicit semantic certification status (PASS required for PUBLISHABLE)
        _sem_cert = "ABSENT"
        try:
            from pipeline.quality.bridge import load_semantic_certification_status

            _sem_cert = load_semantic_certification_status(work)
        except Exception:
            _sem_cert = "ABSENT"
        publishability = run_publishability_gate(
            work,
            technical_ship=ship,
            require_artifact_gate=True,
            artifact_status=str(artifact_gate.get("status") or "UNKNOWN"),
            require_audio_design_gate=True,
            audio_status=str(audio_design_gate.get("status") or "UNKNOWN"),
            require_localization_gate=bool(multilingual),
            localization_status=str(localization_gate.get("status") or "ABSENT"),
            require_creative_production_gate=True,
            creative_production_status=str(creative_production_gate.get("status") or "UNKNOWN"),
            require_rendering_integrity_gate=True,
            rendering_integrity_status=str(rendering_integrity_gate.get("status") or "UNKNOWN"),
            semantic_status=_sem_cert,
            duration_status=str(duration_reconciliation.get("status") or "UNKNOWN"),
            require_duration_gate=True,
            asr_evidence_status=str(audio_asr_gate.get("status") or "UNKNOWN"),
            scene_boundary_status=str(scene_boundary_gate.get("status") or "UNKNOWN"),
            audience_status=str(audience_gate.get("status") or "ABSENT"),
        )
        if not publishability.get("publishable"):
            logger.error(
                "Publishability gate blocked: %s (creative=%s audience=%s)",
                publishability.get("reason"),
                creative_report.get("overall_verdict"),
                audience_gate.get("status"),
            )
            raise RuntimeError(
                "publishability_blocked:"
                + str(publishability.get("reason") or creative_report.get("overall_verdict") or "quality_failed")
            )
        try:
            persist_lineage_audit(work, job_id=work.name)
        except Exception as lin_exc:
            logger.warning("lineage audit soft-fail: %s", lin_exc)
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("Creative quality gate failed closed: %s", exc)
        raise RuntimeError(f"creative_quality_gate_error:{exc}") from exc

    title = plan.get("title") or f"{plan.get('topic')} review"
    description = plan.get("description") or ""
    tags_list = plan.get("tags") or []
    tags = ",".join(tags_list)

    if existing_job_id is not None:
        from app.customer_job import apply_existing_job_update

        job_id = int(existing_job_id)
        apply_existing_job_update(
            job_id,
            title=title,
            description=description,
            tags=tags,
            local_path=str(final),
        )
    else:
        job_id = store.add_job(
            {
                "channel_id": channel.get("id"),
                "video_type": video_type,
                "title": title,
                "description": description,
                "tags": tags,
                "local_path": str(final),
                "platform": "local",
                "upload_status": "generated",
                "dry_run_publish": bool(settings.dry_run_publish),
            }
        )

    thumb_path = work / "thumbnail.jpg"
    package_dir = None
    localize_manifest = None
    upload_status = "generated"
    try:
        import os

        from pipeline.media_assets import generate_thumbnail

        generate_thumbnail(
            title,
            planned_topic or title,
            thumb_path,
            pollinations_key=pollinations_key,
            google_api_keys=google_keys,
            niche=str(niche or ""),
        )
    except Exception as exc:
        logger.warning("thumbnail generate skipped: %s", exc)
        thumb_path = Path(thumb_path) if thumb_path.exists() else None

    try:
        from pipeline.package_export import export_upload_package

        package_dir = export_upload_package(
            dest_root=work / "UPLOAD_PACKAGE",
            channel_name=str(channel.get("youtube_name") or channel.get("facebook_name") or "AutoMovie Pro"),
            gadget={"name": planned_topic or title},
            video_type=video_type,
            video_path=final,
            title=title,
            description=description,
            tags=list(tags_list or []),
            thumbnail_path=thumb_path if thumb_path and Path(thumb_path).exists() else None,
            extra={
                "job_id": job_id,
                "dry_run_publish": bool(settings.dry_run_publish),
                "master_lang": "en",
            },
        )
        logger.info("Upload package ready: %s", package_dir)
    except Exception as exc:
        logger.warning("upload package skipped: %s", exc)

    # H4 DEF-H4-001: multilingual remux packages BEFORE ready_to_upload (fail-closed).
    # Publishability already AND'd the localization *gate*; packaging is the upload artifact step.
    if multilingual:
        try:
            from pipeline.lang_entitlement import channel_languages
            from pipeline.localization import localization_packages_complete, localize_master_clip

            langs = []
            try:
                langs = channel_languages(channel) if channel else []
            except Exception:
                langs = []
            if amp_skip_active("AMP_SKIP_LOCALIZE"):
                raise RuntimeError(
                    "localization_packaging_skipped:AMP_SKIP_LOCALIZE_blocks_multilingual_ready"
                )
            _live("localize", f"Localize {len(langs)} languages", api="tts", action="localize")
            loc = localize_master_clip(
                master_video=final,
                english_narration=en_narr,
                out_dir=work / "LOCALIZED",
                google_api_keys=google_keys,
                slug=f"job{job_id}",
                size=size,
                languages=langs,
                pollinations_key=pollinations_key,
                work_for_scene_local=work,
                scene_indexes=list(range(len(clips))),
            )
            localize_manifest = loc
            (work / "LOCALIZE_RESULT.json").write_text(
                json.dumps(loc, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            ok_pkgs, failed_langs = localization_packages_complete(loc, langs)
            if not ok_pkgs:
                raise RuntimeError(
                    "localization_packaging_incomplete:" + ",".join(failed_langs or ["unknown"])
                )
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("localize_master_clip failed closed (multilingual): %s", exc)
            raise RuntimeError(f"localization_packaging_failed:{exc}") from exc

    # Sole production ready_to_upload writer for generate_video — only after publishability
    # AND (when multilingual) successful localization packaging.
    upload_status = "ready_to_upload"
    try:
        store.update_job(
            int(job_id),
            thumbnail_path=str(thumb_path) if thumb_path and Path(thumb_path).exists() else None,
            package_path=str(package_dir) if package_dir else None,
            upload_status=upload_status,
        )
    except Exception as exc:
        logger.debug("job thumbnail meta update skipped: %s", exc)

    try:
        import os

        pub_note = work / "PUBLISH_STATUS.txt"
        if settings.dry_run_publish:
            pub_note.write_text(
                "DRY_RUN_PUBLISH=true\n"
                "This job is generated locally. Upload will be recorded as dry_run_uploaded "
                "until DRY_RUN_PUBLISH=false in .env.\n",
                encoding="utf-8",
            )
            logger.warning("Publish is DRY-RUN — set DRY_RUN_PUBLISH=false to go live")
        else:
            pub_note.write_text("DRY_RUN_PUBLISH=false — live upload enabled\n", encoding="utf-8")
    except Exception:
        pass

    # Decouple + compress (+ Drive if configured) — does not block publish path on failure
    try:
        import os

        if not amp_skip_active("AMP_SKIP_ASSET_ARCHIVE"):
            from pipeline.asset_archive import archive_finished_clip

            narr = work / "narration_en_tts.m4a"
            if not narr.exists():
                narr = work / "narration_en_from_agnes.m4a"
            archive_finished_clip(
                asset_id=f"job{job_id}_{video_type}",
                source_video=final,
                source_audio=narr if narr.exists() else None,
                script=description or title,
                visual_tags=list(tags_list or []),
                keywords=list(tags_list or []),
                lang_code="en",
                channel_id=int(channel.get("id") or 0),
                niche=str(niche or ""),
                upload_drive=os.environ.get("AMP_DRIVE_UPLOAD", "1").strip() != "0",
                extra={"job_id": job_id, "work": str(work)},
            )
    except Exception as exc:
        logger.warning("asset archive after generate skipped: %s", exc)

    # Canonical Output/{Short|Long}/{NN}_{Title}/{Lang}/… package (per-title, per-language)
    curated_package: Optional[Dict[str, Any]] = None
    try:
        import os

        if os.environ.get("AMP_SKIP_CURATED_OUTPUT", "").strip() != "1":
            from pipeline.curated_output_export import export_curated_package
            from pipeline.lang_entitlement import channel_languages

            curated_langs: List[str] = ["en"]
            try:
                curated_langs = list(channel_languages(channel) if channel else []) or ["en"]
            except Exception:
                curated_langs = ["en"]
            if "en" not in curated_langs:
                curated_langs = ["en", *curated_langs]
            curated_package = export_curated_package(
                work,
                title=str(planned_topic or title or "").strip() or title,
                video_type=video_type,
                final_path=final,
                job_id=job_id,
                languages=curated_langs,
            )
            if curated_package and curated_package.get("ok"):
                logger.info(
                    "Curated output package: %s (%s assets)",
                    curated_package.get("package_root"),
                    curated_package.get("asset_count"),
                )
                try:
                    store.update_job(
                        int(job_id),
                        package_path=str(
                            curated_package.get("package_root") or package_dir or ""
                        )
                        or None,
                    )
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("curated output export skipped: %s", exc)

    # Lock product so future runs cannot re-review the same model
    preg.register_product(
        planned_topic or title,
        channel_id=channel_id,
        niche=niche,
        video_type=video_type,
        job_id=job_id,
        title=title,
    )

    session = store.get_session()
    if session:
        try:
            LicenseClient(session["api_base_url"], session["token"]).sync_job(
                {
                    "channel_name": channel.get("youtube_name") or channel.get("facebook_name"),
                    "video_type": video_type,
                    "title": title,
                    "description": description,
                    "platform": "local",
                    "upload_status": "generated",
                    "local_path": str(final),
                    "meta": {
                        "tags": tags_list,
                        "duration": duration,
                        "topic": plan.get("topic"),
                        "director": plan.get("analysis"),
                        "has_audio": True,
                    },
                }
            )
        except Exception as exc:
            logger.warning("job sync failed: %s", exc)

    return {
        "job_id": job_id,
        "path": str(final),
        "title": title,
        "description": description,
        "tags": tags_list,
        "duration": duration,
        "max_seconds": max_seconds,
        "video_type": video_type,
        "bundle": plan,
        "work_dir": str(work),
        "has_audio": True,
        "topic": plan.get("topic"),
        "director_provider": plan.get("director_provider"),
        "av_report": av_report,
        "av_report_path": str(report_path),
        "thumbnail": str(thumb_path) if thumb_path and Path(thumb_path).exists() else None,
        "upload_package": str(package_dir) if package_dir else None,
        "curated_output": curated_package,
        "package_root": (curated_package or {}).get("package_root") if curated_package else None,
        "video_uid": (curated_package or {}).get("video_uid") if curated_package else None,
        "dry_run_publish": bool(settings.dry_run_publish),
        "localized": localize_manifest,
        "upload_status": upload_status,
    }


def _observe_and_maybe_repair_semantic(
    *,
    work: Path,
    idx: int,
    scene: Dict[str, Any],
    clip: Path,
    narr: str,
    canonical_visual: str,
    element: str,
    size: str,
    audio: Optional[Path],
    google_keys: List[str],
    planned_topic: str,
    niche: str,
    pexels_key: str,
    pollinations_key: str,
    agnes_keys: List[str],
    allow_image_fallback: bool,
    customer_id: str,
    channel_id: str,
    language_entitlement: str,
    channel: Dict[str, Any],
    plan: Dict[str, Any],
    video_type: str = "short",
) -> Path:
    """RCP-03: observe real pixels; BUILD-04F repair only this beat on FAIL."""
    from pipeline.semantic_coverage import (
        STATUS_FAIL,
        STATUS_UNKNOWN,
        contract_from_scene,
        observe_semantic_coverage,
        persist_semantic_coverage,
        plan_semantic_beat_repair,
    )

    contract = contract_from_scene(scene if isinstance(scene, dict) else {}, narration=narr, prompt=canonical_visual)
    # Strengthen unambiguous subjects from narration when C05-S left subject empty
    if not contract.get("required_subject"):
        contract = contract_from_scene(
            {**(scene if isinstance(scene, dict) else {}), "narration": narr},
            narration=narr,
            prompt=canonical_visual,
        )

    obs = observe_semantic_coverage(
        video_path=Path(clip),
        contract=contract,
        google_api_keys=google_keys,
    )
    old_fp = ((obs.get("layers") or {}).get("GENERATED_ASSET") or {}).get("fingerprint") or ""
    repair_meta: Dict[str, Any] = {"attempted": False}

    if obs.get("overall") == STATUS_FAIL:
        repair = plan_semantic_beat_repair(
            beat_id=str(contract.get("beat_id") or f"beat-{idx}"),
            scene_id=str(contract.get("scene_id") or f"scene-{idx:02d}"),
            observation=obs,
            old_fingerprint=old_fp,
        )
        repair_meta = {"attempted": True, "plan": repair, "old_fingerprint": old_fp}
        logger.warning(
            "Scene %s semantic FAIL — targeted VISUAL_ASSET repair beat=%s",
            idx,
            contract.get("beat_id"),
        )
        # Rebuild ONLY this scene clip (not whole video)
        try:
            subject = str(contract.get("required_subject") or planned_topic or "subject")
            revised = (
                f"{'Vertical 9:16' if video_type == 'short' else 'Horizontal 16:9'} "
                f"cinematic documentary of {subject}. "
                f"Must show: {', '.join(contract.get('required_entities') or [subject])}. "
                f"Action/context: {', '.join(contract.get('required_actions') or [])}. "
                f"Location: {contract.get('required_location') or 'as narrated'}. "
                f"NO unrelated human face, NO talking head. Narration lock: {narr[:180]}"
            )
            # Remove prior scene outputs so BUILD-03 does not reuse the failed asset
            for p in work.glob(f"scene_{idx:02d}_*"):
                if p.suffix.lower() in {".mp4", ".txt"} and "SEMANTIC" not in p.name and "narration" not in p.name:
                    try:
                        if "beat" in p.name or p.name.endswith(f"_{element}.mp4") or "docref" in p.name:
                            p.unlink(missing_ok=True)  # type: ignore[arg-type]
                    except Exception:
                        pass
            from pipeline.media_mode_engine import require_agnes_for_mode as _req_agnes

            new_clip = build_dialogue_clip(
                work=work,
                idx=idx,
                narration_audio=audio,
                visual_query=subject,
                visual_prompt=revised,
                element=element,
                size=size,
                product_name=subject,
                pexels_api=pexels_key or channel.get("pexels_api") or "",
                pollinations_key=pollinations_key or channel.get("pollinations_api") or "",
                agnes_api=agnes_keys[0] if agnes_keys else (channel.get("agnes_api") or ""),
                agnes_api_keys=agnes_keys,
                google_api_keys=google_keys,
                subtitle_text="",
                narration=narr,
                keyword_triggers=list(contract.get("required_entities") or scene.get("keyword_triggers") or []),
                exact_ai_video_prompt=revised,
                niche=niche,
                max_av_retries=1,
                require_agnes=_req_agnes(
                    str(scene.get("visual_mode") or "VIDEO"),
                    allow_image_fallback=allow_image_fallback,
                ),
                allow_image_fallback=allow_image_fallback,
                job_id=work.name,
                dialogue_id=scene.get("dialogue_id") or contract.get("dialogue_id") or "",
                canonical_scene_id=scene.get("canonical_scene_id") or contract.get("scene_id") or "",
                script_id=str(scene.get("script_id") or plan.get("script_id") or ""),
                visual_mode=str(scene.get("visual_mode") or "VIDEO"),
                scene_context={
                    **(scene if isinstance(scene, dict) else {}),
                    "customer_id": customer_id,
                    "channel_id": str(channel_id or ""),
                    "language_entitlement": language_entitlement,
                    "semantic_repair": True,
                    "required_subject": subject,
                },
                customer_id=customer_id,
                channel_id=str(channel_id or ""),
                language_entitlement=language_entitlement,
            )
            if new_clip.exists() and new_clip.stat().st_size > 8000:
                clip = new_clip
                obs2 = observe_semantic_coverage(
                    video_path=Path(clip),
                    contract=contract,
                    google_api_keys=google_keys,
                )
                new_fp = ((obs2.get("layers") or {}).get("GENERATED_ASSET") or {}).get("fingerprint") or ""
                repair_meta.update(
                    {
                        "reobserved": True,
                        "new_fingerprint": new_fp,
                        "fingerprint_changed": bool(old_fp and new_fp and old_fp != new_fp),
                        "post_repair_overall": obs2.get("overall"),
                        "other_assets_untouched": True,
                    }
                )
                obs = obs2
                obs["repair"] = repair_meta
            else:
                repair_meta["reobserved"] = False
                repair_meta["error"] = "repair_clip_missing"
                obs["repair"] = repair_meta
        except Exception as exc:
            repair_meta["error"] = str(exc)[:240]
            obs["repair"] = repair_meta
            logger.warning("Scene %s targeted semantic repair failed: %s", idx, exc)
    elif obs.get("overall") == STATUS_UNKNOWN:
        obs["repair"] = {"attempted": False, "reason": "UNKNOWN_not_repaired_cannot_PASS"}
        obs["blocking"] = True
    else:
        obs["repair"] = {"attempted": False}

    persist_semantic_coverage(work, idx, obs)
    return Path(clip)


def _load_scene_av_summary(
    work: Path,
    idx: int,
    element: str,
    *,
    resumed: bool,
) -> Dict[str, Any]:
    """Pick the latest critique JSON for a scene, if any."""
    best: Optional[Dict[str, Any]] = None
    best_attempt = 0
    for p in sorted(work.glob(f"scene_{idx:02d}_critique_attempt*.json")):
        try:
            name = p.stem  # scene_00_critique_attempt1
            attempt = int(name.split("attempt")[-1])
        except Exception:
            attempt = 0
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if attempt >= best_attempt:
            best_attempt = attempt
            best = data
    fail_path = work / f"scene_{idx:02d}_AV_FAIL.txt"
    return {
        "idx": idx,
        "element": element,
        "resumed": resumed,
        "attempt": best_attempt,
        "match_score": (best or {}).get("match_score"),
        "passed": (best or {}).get("passed"),
        "issues": (best or {}).get("issues") or [],
        "failed_hard": fail_path.exists(),
    }


def _has_audio(path: Path) -> bool:
    import json
    import subprocess
    from pipeline.compose import ffprobe_bin

    try:
        raw = subprocess.check_output(
            [
                ffprobe_bin(),
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                str(path),
            ]
        )
        data = json.loads(raw)
        return any(s.get("codec_type") == "audio" for s in data.get("streams") or [])
    except Exception:
        return False


def _make_silent_audio(path: Path, seconds: float) -> Path:
    import subprocess
    from pipeline.compose import ffmpeg_bin

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-t",
        str(seconds),
        "-c:a",
        "aac",
        str(path),
    ]
    subprocess.run(cmd, capture_output=True)
    return path


def _intro_with_silence(intro: Path, dest: Path, size: str, seconds: float = 0.35) -> Path:
    import subprocess
    from pipeline.compose import ffmpeg_bin

    w, h = size.split("x")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(intro),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-t",
        str(seconds),
        "-vf",
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=25,format=yuv420p",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
        str(dest),
    ]
    subprocess.run(cmd, capture_output=True)
    if not dest.exists():
        make_color_clip(dest, seconds, size)
    return dest


def _trim_reencode(src: Path, dest: Path, max_seconds: int, size: str) -> Path:
    import subprocess
    from pipeline.compose import ffmpeg_bin, ffprobe_duration
    from pipeline.duration_budget import trim_would_cut_coverage

    w, h = size.split("x")
    src_dur = ffprobe_duration(src)
    # RCP-06B: never hard-cut mid-dialogue / covered visuals to force max_seconds.
    if trim_would_cut_coverage(src_dur, float(max_seconds)):
        raise RuntimeError(
            "PRODUCTION_INCOMPLETE:final_trim_would_cut_coverage:"
            f"src={float(src_dur):.2f}:max={float(max_seconds):.2f}"
        )
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(src),
        "-vf",
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=25,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    subprocess.run(cmd, capture_output=True)
    return dest
