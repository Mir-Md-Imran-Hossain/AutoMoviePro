from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)


NICHE_TOPIC_POOLS: Dict[str, List[Dict[str, str]]] = {
    "health": [
        {"name": "Circadian Rhythm Intermittent Fasting", "why_trending": "Breakthrough metabolic timing and insulin optimization", "search_query": "circadian rhythm fasting health benefits", "category": "health", "source": "fallback"},
        {"name": "Zone 2 Cardio Longevity Protocol", "why_trending": "Mitochondrial efficiency and cardiovascular longevity", "search_query": "zone 2 cardio protocol longevity", "category": "health", "source": "fallback"},
        {"name": "Cold Water Immersion Neurochemistry", "why_trending": "Dopamine release and brown adipose activation studies", "search_query": "cold plunge science dopamine metabolism", "category": "health", "source": "fallback"},
        {"name": "Gut Microbiome Prebiotic Diversity", "why_trending": "Immune regulation and gut-brain neurotransmitter pathways", "search_query": "gut microbiome diverse fiber nutrition", "category": "health", "source": "fallback"},
    ],
    "finance": [
        {"name": "AI Driven Quantitative Investing", "why_trending": "Algorithmic momentum and retail trading revolution", "search_query": "algorithmic AI investing strategies", "category": "finance", "source": "fallback"},
        {"name": "Layer 1 Blockchain Interoperability", "why_trending": "Next-generation decentralized finance liquidity routing", "search_query": "crypto layer 1 ecosystem interoperability", "category": "finance", "source": "fallback"},
        {"name": "High-Yield Cash Alternative Strategies", "why_trending": "Macro interest rate cycles and capital preservation", "search_query": "treasury cash management strategies high yield", "category": "finance", "source": "fallback"},
        {"name": "Fractional Real Estate Tokenization", "why_trending": "Asset diversification and passive dividend generation", "search_query": "real estate tokenization passive income", "category": "finance", "source": "fallback"},
    ],
    "cooking": [
        {"name": "Mastering Authentic Neapolitan Sourdough Pizza", "why_trending": "High-hydration fermentation and wood-fired blister crusts", "search_query": "authentic sourdough neapolitan pizza technique", "category": "cooking", "source": "fallback"},
        {"name": "Japanese Umami Dashi Secret Foundations", "why_trending": "Kombu and bonito glutamic acid extraction mastery", "search_query": "traditional japanese dashi extraction broth", "category": "cooking", "source": "fallback"},
        {"name": "Sous-Vide Reverse Sear Perfection", "why_trending": "Precision edge-to-edge culinary protein temperature control", "search_query": "reverse sear steak culinary science", "category": "cooking", "source": "fallback"},
        {"name": "Artisanal French Butter Croissant Lamination", "why_trending": "Pastry fold geometry and honeycomb crumb structure", "search_query": "croissant lamination honeycomb butter layers", "category": "cooking", "source": "fallback"},
    ],
    "motivation": [
        {"name": "The Dopamine Reset Protocol", "why_trending": "Overcoming digital overstimulation to restore deep focus", "search_query": "dopamine detox neuroplasticity discipline", "category": "motivation", "source": "fallback"},
        {"name": "Friction Elimination Micro-Habits", "why_trending": "Behavioral momentum systems that outlast willpower", "search_query": "atomic habit friction reduction systems", "category": "motivation", "source": "fallback"},
        {"name": "Deep Work Four-Hour Focus Blocks", "why_trending": "Cognitive defense in the hyper-distraction era", "search_query": "cal newport deep work focus strategy", "category": "motivation", "source": "fallback"},
        {"name": "Stoic Emotional Fortress Principles", "why_trending": "Managing external chaos with internal locus of control", "search_query": "stoic principles modern mental resilience", "category": "motivation", "source": "fallback"},
    ],
    "islamic": [
        {"name": "Lessons from Surah Al-Kahf for the Modern Mind", "why_trending": "Timeless reflections on faith, wealth, and spiritual trials", "search_query": "surah al kahf modern reflections faith", "category": "islamic", "source": "fallback"},
        {"name": "Golden Age of Islamic Science & Astronomy", "why_trending": "How House of Wisdom scholars mapped the cosmos", "search_query": "islamic golden age astronomy science discoveries", "category": "islamic", "source": "fallback"},
        {"name": "Prophetic Medicine & Holistic Wellness", "why_trending": "Scientific validation of traditional prophetic health practices", "search_query": "prophetic medicine black seed honey science", "category": "islamic", "source": "fallback"},
        {"name": "The Architecture of Ottoman Mosques & Sinan", "why_trending": "Acoustic and structural brilliance of historical masjids", "search_query": "mimar sinan mosque acoustic geometry", "category": "islamic", "source": "fallback"},
    ],
    "history": [
        {"name": "Engineering Secrets of the Bronze Age Collapse", "why_trending": "Civilization breakdown across the ancient Mediterranean", "search_query": "bronze age collapse climate trade disruption", "category": "history", "source": "fallback"},
        {"name": "Uncracked Scripts: The Indus Valley Enigma", "why_trending": "Linguistic and archaeological decoding efforts", "search_query": "indus valley script undeciphered archaeology", "category": "history", "source": "fallback"},
        {"name": "Roman Concrete Hydraulic Engineering Feats", "why_trending": "Self-healing pozzolanic volcanic ash longevity secrets", "search_query": "roman concrete pozzolanic self healing", "category": "history", "source": "fallback"},
        {"name": "Silk Road Desert Oasis Outposts", "why_trending": "Caravan routes and early global currency exchanges", "search_query": "silk road oasis trade networks archaeological finds", "category": "history", "source": "fallback"},
    ],
    "gadget": [
        {"name": "Google Pixel 9a", "why_trending": "Strong midrange computational camera interest", "search_query": "Pixel 9a review camera", "category": "phone", "source": "fallback"},
        {"name": "OnePlus 13", "why_trending": "Flagship Snapdragon performance benchmark reviews", "search_query": "OnePlus 13 performance review", "category": "phone", "source": "fallback"},
        {"name": "Sony WF-1000XM5", "why_trending": "Premium ANC earbuds acoustic comparison searches", "search_query": "Sony WF-1000XM5 ANC review", "category": "audio", "source": "fallback"},
        {"name": "DJI Osmo Pocket 3", "why_trending": "Creator vlog 1-inch sensor camera interest", "search_query": "DJI Osmo Pocket 3 review", "category": "camera", "source": "fallback"},
    ],
}


def _resolve_niche_key(niche: str) -> str:
    nl = (niche or "").lower()
    for k in ("islam", "deen", "quran", "muslim"):
        if k in nl:
            return "islamic"
    for k in ("cook", "food", "recipe", "baking"):
        if k in nl:
            return "cooking"
    for k in ("financ", "crypto", "money", "invest", "stock"):
        if k in nl:
            return "finance"
    for k in ("health", "fit", "diet", "sleep", "workout", "longevity"):
        if k in nl:
            return "health"
    for k in ("motivat", "habit", "mindset", "productiv", "discipline"):
        if k in nl:
            return "motivation"
    for k in ("histor", "ancient", "civiliz", "archaeolog"):
        if k in nl:
            return "history"
    return "gadget"


def _fallback_gadgets(n: int, niche: str = "") -> List[Dict[str, str]]:
    key = _resolve_niche_key(niche)
    pool = NICHE_TOPIC_POOLS.get(key) or NICHE_TOPIC_POOLS["gadget"]
    return pool[:n]


def find_trending_topics(
    google_api_keys: Optional[List[str]] = None,
    count: int = 2,
    *,
    niche: str = "",
    exclude_names: Optional[List[str]] = None,
    fetch_multiplier: int = 4,
) -> List[Dict[str, str]]:
    """
    Find trending topics for the specified niche without gadget bias.
    """
    exclude = [n for n in (exclude_names or []) if n]
    want = max(count * fetch_multiplier, count + len(exclude) + 2)
    topics: List[Dict[str, str]] = []
    try:
        topics = _via_gemini(google_api_keys or [], want, exclude_names=exclude, niche=niche)
    except Exception as exc:
        logger.warning("gemini trending search failed: %s", exc)

    if len(topics) < want:
        try:
            more = _via_duckduckgo(want, niche=niche)
            topics.extend(more)
        except Exception as exc:
            logger.warning("duckduckgo search failed: %s", exc)

    seen = set()
    unique: List[Dict[str, str]] = []
    for g in topics:
        name = (g.get("name") or "").strip()
        if not name:
            continue
        if _is_excluded(name, exclude):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(g)
        if len(unique) >= count:
            break

    if len(unique) < count:
        for g in _fallback_gadgets(12, niche=niche):
            name = g.get("name") or ""
            if _is_excluded(name, exclude):
                continue
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            unique.append(g)
            if len(unique) >= count:
                break

    selected = unique[:count]
    for topic_item in selected:
        if "competitor_analysis" not in topic_item:
            headlines = [h.get("title", "") for h in topic_item.get("google_hits", []) if isinstance(h, dict)]
            if not headlines:
                headlines = [topic_item.get("name", ""), topic_item.get("why_trending", "")]
            topic_item["competitor_analysis"] = analyze_competitor_patterns(headlines, niche=niche)
    return selected


def find_trending_gadgets(
    google_api_keys: Optional[List[str]] = None,
    count: int = 2,
    *,
    exclude_names: Optional[List[str]] = None,
    fetch_multiplier: int = 4,
) -> List[Dict[str, str]]:
    return find_trending_topics(
        google_api_keys=google_api_keys,
        count=count,
        niche="",
        exclude_names=exclude_names,
        fetch_multiplier=fetch_multiplier,
    )


def _is_excluded(name: str, exclude: List[str]) -> bool:
    if not exclude:
        return False
    try:
        from pipeline.product_registry import is_same_product
        return any(is_same_product(name, e) for e in exclude)
    except Exception:
        nl = name.lower()
        return any(e.lower() in nl or nl in e.lower() for e in exclude if e)


def _via_gemini(
    api_keys: List[str],
    count: int,
    exclude_names: Optional[List[str]] = None,
    niche: str = "",
) -> List[Dict[str, str]]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise RuntimeError("google-genai not installed") from e

    block = "\n".join(f"- {n}" for n in (exclude_names or [])[:60]) or "(none)"
    from pipeline.prompt_engineering import trending_instruction

    prompt = trending_instruction(count=count, block_txt=block, year=2026, niche=niche)
    last_err = None
    try:
        from pipeline.llm_router import chat_text, extract_json_object

        hit = chat_text(prompt, google_api_keys=api_keys, json_mode=True, purpose="script")
        data = json.loads(extract_json_object(hit["text"]))
        items = data.get("gadgets") or data.get("topics") or []
        out = []
        for it in items:
            out.append(
                {
                    "name": str(it.get("name") or it.get("topic") or "").strip(),
                    "why_trending": str(it.get("why_trending") or "").strip(),
                    "search_query": str(it.get("search_query") or it.get("name") or "").strip(),
                    "category": str(it.get("category") or "other").strip(),
                    "source": f"trending:{hit.get('provider')}",
                }
            )
        if out:
            for g in out:
                g["google_hits"] = _google_like_hits(g["search_query"] or g["name"])
            return out
    except Exception as exc:
        last_err = exc
        logger.warning("trending llm_router failed: %s", exc)
    if last_err:
        raise last_err
    return []


def _via_duckduckgo(count: int, niche: str = "") -> List[Dict[str, str]]:
    niche_key = _resolve_niche_key(niche)
    if niche_key == "health":
        queries = ["latest health discoveries 2026", "trending nutrition sleep protocols", "viral wellness trends"]
    elif niche_key == "finance":
        queries = ["crypto and market trends this week", "top trending personal finance tips 2026", "global economy trends"]
    elif niche_key == "cooking":
        queries = ["trending recipes 2026", "viral culinary trends techniques", "popular food cooking ideas"]
    elif niche_key == "motivation":
        queries = ["trending productivity systems habits", "high performance mindset discipline", "stoic life principles"]
    elif niche_key == "islamic":
        queries = ["islamic history wisdom reflections", "golden age islamic science", "prophetic lifestyle lessons"]
    elif niche_key == "history":
        queries = ["archaeological discoveries recent", "unsolved ancient history mysteries", "fascinating historical events"]
    else:
        queries = [
            "most trending tech gadgets 2026",
            "best new tech this week",
            "viral gadgets review 2026",
        ]
    names: List[str] = []
    for q in queries:
        try:
            hits = _google_like_hits(q, limit=8)
            for h in hits:
                title = h.get("title") or ""
                cleaned_title = re.sub(r"[|\-:].*", "", title).strip()
                if len(cleaned_title) > 6:
                    names.append(cleaned_title)
        except Exception:
            continue
    unique = []
    seen = set()
    for n in names:
        k = n.lower()
        if k in seen:
            continue
        seen.add(k)
        unique.append(
            {
                "name": n,
                "why_trending": f"Trending web search interest in {niche_key or 'general'}",
                "search_query": f"{n}",
                "category": niche_key or "general",
                "source": "duckduckgo_web",
                "google_hits": [],
            }
        )
        if len(unique) >= count:
            break
    return unique


def _get_proxy_url() -> Optional[str]:
    """Inspect environment variables for configured proxy URL."""
    for key in ("AMP_HTTP_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return None


def _create_resilient_client(*, proxy: Optional[str] = None, timeout: float = 12.0) -> httpx.Client:
    """Build httpx.Client with optional proxy configuration."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    kwargs: Dict[str, Any] = {
        "timeout": timeout,
        "follow_redirects": True,
        "headers": headers,
    }
    proxy_target = proxy or _get_proxy_url()
    if proxy_target:
        try:
            kwargs["proxy"] = proxy_target
        except Exception:
            pass
    return httpx.Client(**kwargs)


def _google_like_hits(
    query: str,
    limit: int = 5,
    *,
    max_retries: int = 2,
    proxy: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Use DuckDuckGo HTML results as Google-search proxy with resilient session retries & proxy fallback.
    """
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    hits: List[Dict[str, str]] = []

    # Attempt order: primary client (with optional proxy) -> fallback direct client if proxy failed
    clients_to_try = [
        {"proxy": proxy or _get_proxy_url(), "name": "primary"},
    ]
    if proxy or _get_proxy_url():
        clients_to_try.append({"proxy": None, "name": "direct_fallback"})

    for client_cfg in clients_to_try:
        current_proxy = client_cfg["proxy"]
        for attempt in range(max_retries + 1):
            try:
                with _create_resilient_client(proxy=current_proxy, timeout=12.0 + attempt * 3.0) as client:
                    r = client.post(url, data={"q": query})
                    if r.status_code == 200 and r.text:
                        html = r.text
                        for m in re.finditer(
                            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                            html,
                            flags=re.I | re.S,
                        ):
                            href = m.group(1)
                            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                            if title:
                                hits.append({"title": title, "url": href})
                            if len(hits) >= limit:
                                break
                        if hits:
                            return hits
            except Exception as exc:
                logger.debug(
                    "Search attempt %d failed for '%s' (mode=%s): %s",
                    attempt + 1,
                    query,
                    client_cfg["name"],
                    exc,
                )
                time.sleep(0.3 * (attempt + 1))
        if hits:
            break

    return hits


class CompetitorPatternAnalyzer:
    """
    Industrial Competitor Headline & Thumbnail Pattern Analysis Framework.
    Extracts viral curiosity hooks, emotional polarity, high-CTR thumbnail composition rules,
    and power word structures from trending competitor search hits.
    """

    CURIOSITY_PATTERNS = [
        r"\b(?:why|how|what happens|the truth about|the secret behind|nobody talks about)\b",
        r"\b(?:what they don't tell you|the real reason|the hidden|mystery of)\b",
        r"\b(?:exposed|revealed|uncovered|stop doing|never do this)\b",
    ]

    NEGATIVE_POLARITY_TERMS = {
        "never", "stop", "mistake", "warning", "danger", "ruining", "worst",
        "deadly", "fatal", "scam", "trap", "avoid", "risk", "disaster", "fail",
    }

    POWER_WORDS = {
        "shocking", "insane", "unbelievable", "genius", "banned", "ultimate",
        "secret", "truth", "proven", "massive", "exponential", "breakthrough",
        "game-changer", "revolutionary", "underground", "forbidden", "powerful",
    }

    THUMBNAIL_STYLES_BY_NICHE: Dict[str, Dict[str, Any]] = {
        "health": {
            "composition": "split_screen_transformation_or_focal_organ",
            "contrast_ratio": "high",
            "dominant_accents": ["#00FF88", "#FF3366"],
            "text_banner_style": "minimal_3_words_bold_sans",
            "facial_expression": "curious_intensity_or_alert_focus",
            "rule_of_thirds_anchor": "right_subject_left_vital_stat",
        },
        "finance": {
            "composition": "dynamic_chart_breakout_with_dramatic_subject",
            "contrast_ratio": "ultra_high",
            "dominant_accents": ["#FFCC00", "#FF2222", "#00E5FF"],
            "text_banner_style": "all_caps_heavy_drop_shadow",
            "facial_expression": "urgent_warning_or_calculating_confidence",
            "rule_of_thirds_anchor": "left_stat_metric_right_focal",
        },
        "cooking": {
            "composition": "macro_cross_section_golden_crust_steam",
            "contrast_ratio": "rich_warm",
            "dominant_accents": ["#FF8800", "#FFD700", "#FF4400"],
            "text_banner_style": "flavor_verdict_pill_tag",
            "facial_expression": "sensory_ecstasy_reaction",
            "rule_of_thirds_anchor": "center_hero_plate_macro",
        },
        "motivation": {
            "composition": "lone_figure_silhouette_cinematic_contrast",
            "contrast_ratio": "monochrome_with_vibrant_focal_flare",
            "dominant_accents": ["#FF0055", "#00FFFF"],
            "text_banner_style": "harsh_impact_font_stacked",
            "facial_expression": "stoic_unwavering_determination",
            "rule_of_thirds_anchor": "center_monumental_alignment",
        },
        "islamic": {
            "composition": "majestic_golden_geometric_illumination_heritage",
            "contrast_ratio": "serene_deep_contrast",
            "dominant_accents": ["#D4AF37", "#0F52BA", "#2E8B57"],
            "text_banner_style": "elegant_serif_calligraphic_accent",
            "facial_expression": "contemplative_reverence",
            "rule_of_thirds_anchor": "balanced_symmetry_with_skyline",
        },
        "history": {
            "composition": "ancient_relic_in_situ_dramatic_shadow_torchlight",
            "contrast_ratio": "dark_cinematic_chiaroscuro",
            "dominant_accents": ["#C5A059", "#8B0000", "#1A2421"],
            "text_banner_style": "weathered_chiseled_all_caps",
            "facial_expression": "forensic_historian_astonishment",
            "rule_of_thirds_anchor": "central_artifact_atmospheric_mist",
        },
        "gadget": {
            "composition": "exploded_view_or_stealth_matte_hero_macro",
            "contrast_ratio": "cyber_dark_neon",
            "dominant_accents": ["#00F0FF", "#7B2CBF", "#FF007F"],
            "text_banner_style": "futuristic_tech_spec_badge",
            "facial_expression": "eyebrow_raised_tech_skepticism",
            "rule_of_thirds_anchor": "diagonal_hero_tilt_spec_highlight",
        },
    }

    @classmethod
    def analyze_headlines(cls, headlines: List[str]) -> Dict[str, Any]:
        """
        Analyze a list of competitor titles to identify winning hooks,
        curiosity structures, number usage, and power vocabulary.
        """
        clean_heads = [h.strip() for h in headlines if h and len(h.strip()) > 5]
        if not clean_heads:
            return {
                "sample_count": 0,
                "curiosity_score": 0.5,
                "negative_polarity_score": 0.2,
                "numbers_present_ratio": 0.3,
                "power_word_density": 0.2,
                "dominant_hook_archetype": "mystery_curiosity",
                "recommended_headline_formula": "[Number] Shocking Secrets Behind [Topic] You Never Knew",
                "extracted_power_words": [],
            }

        curiosity_matches = 0
        neg_matches = 0
        num_matches = 0
        found_power_words = set()

        for h in clean_heads:
            hl = h.lower()
            if any(re.search(pat, hl) for pat in cls.CURIOSITY_PATTERNS):
                curiosity_matches += 1
            words = set(re.findall(r"\b\w+\b", hl))
            if words & cls.NEGATIVE_POLARITY_TERMS:
                neg_matches += 1
            if re.search(r"\b\d+\b", h):
                num_matches += 1
            matched_pw = words & cls.POWER_WORDS
            found_power_words.update(matched_pw)

        n = len(clean_heads)
        curiosity_ratio = curiosity_matches / n
        neg_ratio = neg_matches / n
        num_ratio = num_matches / n
        pw_density = len(found_power_words) / max(1, n)

        # Classify dominant hook archetype
        if neg_ratio > 0.4:
            archetype = "risk_avoidance_warning"
            formula = "Why Doing [Topic] Is Secretly Ruining Your Progress (Stop Now)"
        elif num_ratio > 0.4:
            archetype = "curated_list_authority"
            formula = "{Count} Incredible Breakthroughs in [Topic] That Change Everything"
        elif curiosity_ratio > 0.4:
            archetype = "deep_mystery_unveil"
            formula = "The Shocking Truth About [Topic] That Nobody Dares To Mention"
        else:
            archetype = "provocative_counter_intuitive"
            formula = "What Happens When You Finally Understand The Reality Of [Topic]"

        return {
            "sample_count": n,
            "curiosity_score": round(min(1.0, curiosity_ratio), 3),
            "negative_polarity_score": round(min(1.0, neg_ratio), 3),
            "numbers_present_ratio": round(min(1.0, num_ratio), 3),
            "power_word_density": round(min(1.0, pw_density), 3),
            "dominant_hook_archetype": archetype,
            "recommended_headline_formula": formula,
            "extracted_power_words": sorted(list(found_power_words)),
        }

    @classmethod
    def analyze_thumbnail_patterns(cls, niche: str = "") -> Dict[str, Any]:
        """
        Derive optimal thumbnail visual composition rules, contrast profiles,
        and accent colors tailored to competitor CTR benchmarks in the niche.
        """
        nkey = _resolve_niche_key(niche)
        spec = cls.THUMBNAIL_STYLES_BY_NICHE.get(nkey) or cls.THUMBNAIL_STYLES_BY_NICHE["gadget"]
        return {
            "niche": nkey,
            "visual_blueprint": spec,
            "target_ctr_multiplier": 1.25,
            "thumbnail_prompt_directives": [
                f"Ultra-high contrast {spec['composition']} composition",
                f"Vibrant focal accents in {', '.join(spec['dominant_accents'])}",
                f"Subject conveying {spec['facial_expression'].replace('_', ' ')}",
                f"Strict adherence to {spec['rule_of_thirds_anchor'].replace('_', ' ')}",
            ],
        }


def analyze_competitor_patterns(
    headlines: List[str],
    *,
    niche: str = "",
) -> Dict[str, Any]:
    """Convenience helper to extract both headline and thumbnail competitor intelligence."""
    hl_analysis = CompetitorPatternAnalyzer.analyze_headlines(headlines)
    thumb_analysis = CompetitorPatternAnalyzer.analyze_thumbnail_patterns(niche)
    return {
        "headline_intelligence": hl_analysis,
        "thumbnail_intelligence": thumb_analysis,
        "niche": _resolve_niche_key(niche),
    }

