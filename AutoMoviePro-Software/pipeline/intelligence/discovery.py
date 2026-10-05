"""Topic discovery pipeline (BUILD-04G-H)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Sequence

from pipeline.idempotency.fingerprint import compute_fingerprint
from pipeline.intelligence.contracts import (
    INTELLIGENCE_CONTRACT_VERSION,
    ChannelProfile,
    ContentFormat,
    TopicCandidate,
)
from pipeline.intelligence.candidates import candidate_from_dict, validate_candidate_dict

DISCOVERY_PROVIDER = "local_discovery_v1"
DISCOVERY_SOURCE_TYPE = "local_generated"
DISCOVERY_EXTERNAL_API = False
DEFAULT_DISCOVERY_MAX_AGE_SEC = 86400 * 7


class DiscoveryUnavailableError(RuntimeError):
    """Raised when discovery cannot run (provider disabled/unavailable)."""


class DiscoveryEmptyError(RuntimeError):
    """Raised when discovery yields zero acceptable candidates."""


def _rotation_offset(*parts: Any) -> int:
    """Time-bucketed rotation so the same niche yields different lead topics over time."""
    # ~3h buckets → several distinct rotations per day without being random-noise
    bucket = int(time.time() // (3 * 3600))
    blob = "|".join(str(p) for p in parts) + f"|{bucket}"
    return int(hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8], 16)


def _rotate(items: list[str], offset: int) -> list[str]:
    if not items:
        return []
    i = offset % len(items)
    return items[i:] + items[:i]


def discovery_input_fingerprint(
    profile: ChannelProfile,
    *,
    fmt: ContentFormat,
    count: int,
    historical: Sequence[str],
    reserved: Sequence[str],
    blocked: Sequence[str],
) -> str:
    return compute_fingerprint(
        job_id=f"discovery-{profile.channel_id}",
        stage="discovery",
        entity_id=f"disc-{profile.channel_id}-{fmt.value}",
        contract_version=INTELLIGENCE_CONTRACT_VERSION,
        provider=DISCOVERY_PROVIDER,
        model="discovery-v1",
        inputs={
            "channel_id": profile.channel_id,
            "niche": profile.niche,
            "sub_niche": profile.sub_niche,
            "format": fmt.value,
            "count": count,
            "historical": sorted(historical),
            "reserved": sorted(reserved),
            "blocked": sorted(blocked),
            "rotation_bucket": int(time.time() // (3 * 3600)),
        },
    )


def _provenance_block(
    profile: ChannelProfile,
    *,
    fmt: ContentFormat,
    fingerprint: str,
    discovered_at: float,
) -> dict[str, Any]:
    return {
        "source": "discovery",
        "source_type": DISCOVERY_SOURCE_TYPE,
        "provider": DISCOVERY_PROVIDER,
        "external_api": DISCOVERY_EXTERNAL_API,
        "discovered_at": discovered_at,
        "discovery_fingerprint": fingerprint,
        "channel_id": profile.channel_id,
        "format": fmt.value,
        "query": f"channel:{profile.channel_id}:{profile.niche}:{fmt.value}",
    }


def is_discovery_stale(
    candidate: TopicCandidate,
    *,
    max_age_sec: float = DEFAULT_DISCOVERY_MAX_AGE_SEC,
    now: float | None = None,
) -> bool:
    prov = (candidate.metadata or {}).get("provenance") or {}
    ts = prov.get("discovered_at")
    if ts is None:
        return True
    try:
        age = float(now if now is not None else time.time()) - float(ts)
    except (TypeError, ValueError):
        return True
    return age > max_age_sec


def save_discovery_artifact(path: Path, candidates: Sequence[TopicCandidate], *, fingerprint: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fingerprint": fingerprint,
        "saved_at": time.time(),
        "provider": DISCOVERY_PROVIDER,
        "source_type": DISCOVERY_SOURCE_TYPE,
        "external_api": DISCOVERY_EXTERNAL_API,
        "candidates": [c.to_dict() for c in candidates],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_discovery_artifact(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("corrupted_discovery_artifact") from exc
    if not isinstance(data, dict) or "candidates" not in data:
        raise ValueError("invalid_discovery_artifact")
    return data


def discover_topic_candidates(
    profile: ChannelProfile,
    *,
    fmt: ContentFormat = ContentFormat.LONG,
    count: int = 8,
    historical: Sequence[str] = (),
    reserved: Sequence[str] = (),
    blocked: Sequence[str] = (),
    trend_hints: Sequence[dict[str, Any]] = (),
    provider_available: bool | None = None,
    require_non_empty: bool = False,
) -> list[TopicCandidate]:
    """Channel-aware local candidate generation with niche rotation (anti-repeat)."""
    available = provider_available
    if available is None:
        available = os.environ.get("INTELLIGENCE_DISCOVERY_DISABLED", "").lower() not in ("1", "true", "yes")
    if not available:
        raise DiscoveryUnavailableError("discovery provider unavailable")

    fingerprint = discovery_input_fingerprint(
        profile,
        fmt=fmt,
        count=count,
        historical=historical,
        reserved=reserved,
        blocked=blocked,
    )
    discovered_at = time.time()
    provenance = _provenance_block(profile, fmt=fmt, fingerprint=fingerprint, discovered_at=discovered_at)

    seeds: list[str] = []
    niche = profile.niche or "general"
    sub = profile.sub_niche or niche
    audience = profile.audience_profile or "general"
    niche_l = niche.lower()
    year = "2026"
    rot = _rotation_offset(profile.channel_id, niche_l, fmt.value)

    preferred = list(profile.preferred_topics or [])
    if preferred:
        seeds.extend(_rotate(preferred, rot)[:6])

    # Marathon niche production profile — rotate through ALL topic_seeds (not always first 6)
    niche_seeds: list[str] = []
    try:
        from pipeline.niche_production_profile import load_profile
        from pipeline.nish_catalog import get_niche_by_name

        nid = 0
        pack = get_niche_by_name(niche) if niche else None
        if pack:
            nid = int(pack.get("id") or 0)
        prof = load_profile(nid) if nid else None
        if prof:
            niche_seeds = [str(s) for s in list(prof.get("topic_seeds") or []) if s]
            for s in list(prof.get("seo_angles") or []):
                if s and str(s) not in niche_seeds:
                    niche_seeds.append(str(s))
    except Exception:
        pass
    if niche_seeds:
        for s in _rotate(niche_seeds, rot + 3):
            if s not in seeds:
                seeds.append(s)

    # Niche-grounded SEO templates (avoid "{niche} topic angle N" placeholders)
    space_bank = [
        f"How Artemis crews use neutron spectrometers to map lunar polar water ice in {year}",
        "Why permanently shadowed craters keep water ice colder than dry ice on the Moon",
        "What JWST mid-infrared spectra reveal about exoplanet atmospheres this week",
        "How solar wind strips Mars of atmosphere — the MAVEN evidence explained",
        "Why lunar south pole ice matters for propellant and drinking water on Mars missions",
        "How neutron albedo mapping finds hydrogen under the Moon's dark crater floors",
        f"What Parker Solar Probe discovered about the Sun's corona in {year}",
        "How Europa's ice shell could hide a salty ocean — the evidence so far",
        "Why Venus' thick clouds hide surface heat that melts lead — the physics",
        "How Starliner and commercial crew change ISS science return timelines",
        "What dark energy surveys measure when galaxies stretch apart",
        "How radio telescopes catch fast radio bursts from distant magnetars",
        f"Why lunar dust abrasion threatens Artemis spacesuits in {year}",
        "How gravitational-wave detectors hear black-hole mergers across the universe",
    ]
    science_bank = [
        f"How CRISPR base editing differs from cutting DNA — a {year} explainer",
        "Why mRNA vaccines train immunity faster than traditional shots",
        "How quantum sensors measure gravity without lasers for underground mapping",
        "Why antibiotic resistance spreads faster in hospital wastewater than soil",
        "How climate ice-core layers record volcanic winters century by century",
        "What fusion tokamak heat-exhaust tiles must survive during plasma pulses",
    ]
    if any(x in niche_l for x in ("space", "astro", "nasa", "lunar", "planet")):
        bank = space_bank
    elif any(x in niche_l for x in ("science", "research", "tech")):
        bank = science_bank + space_bank[:4]
    else:
        bank = [
            f"How {sub} works in plain English for {audience} — the mechanism most shorts skip",
            f"Why {sub} matters now — the counterintuitive evidence from {year}",
            f"What most {niche} explainers get wrong about {sub}",
            f"The {sub} detail experts watch first in {year}",
            f"How experts verify claims about {sub} before publishing",
            f"Hidden risks inside everyday {niche} advice — what to check",
            f"Which {sub} metric actually predicts outcomes for {audience}",
            f"Where {sub} breakthroughs stall — cost, risk, and proof gaps",
        ]

    bank = _rotate(bank, rot + 7)
    if fmt == ContentFormat.SHORT:
        seeds.extend(bank)
        seeds.extend(
            _rotate(
                [
                    f"Quick {sub} insight: the one mechanism viewers miss",
                    f"One verified fact about {niche} that changes the next 60 seconds",
                    f"60-second {sub} myth vs measurement — stay for the payoff",
                    f"The {year} {niche} detail most shorts skip (and why it matters)",
                    f"Why {sub} looks obvious — until you see this evidence",
                ],
                rot,
            )
        )
    else:
        seeds.extend(bank)
        seeds.extend(
            _rotate(
                [
                    f"Deep dive: {sub} explained for {audience} with a retention spine",
                    f"Full evidence chain: how {sub} claims are proven or rejected",
                    f"{year} {niche} investigation: open loops and closed payoffs on {sub}",
                    f"The complete guide to {niche} evidence in {year}",
                    f"Why {sub} matters now — full analysis with sources",
                    f"Case study: how {sub} evidence changed expert consensus",
                ],
                rot + 1,
            )
        )

    for hint in trend_hints[:3]:
        name = str(hint.get("name") or hint.get("title") or "").strip()
        if name:
            seeds.append(name)

    filler_angles = _rotate(
        [
            f"How researchers test claims about {sub} with primary data",
            f"What changes for {audience} if {sub} breakthroughs scale in {year}",
            f"Why {sub} timelines slipped — the engineering bottleneck explained",
            f"How to spot weak evidence in viral {niche} claims",
            f"Where {sub} meets real-world constraints — cost, risk, and proof",
            f"Which {sub} metric actually predicts outcomes (and which don't)",
            f"How field teams measure {sub} when lab results disagree",
            f"What happens when {sub} assumptions fail under edge cases",
        ],
        rot + 11,
    )
    fi = 0
    while len(seeds) < count + 8 and fi < len(filler_angles):
        seeds.append(filler_angles[fi])
        fi += 1
    while len(seeds) < count + 4:
        seeds.append(
            f"How {sub} field measurements contradict popular myths — case {(rot + len(seeds)) % 97 + 1}"
        )

    exclude_exact = {s.lower() for s in list(historical) + list(reserved) + list(blocked) if s}
    try:
        from pipeline.intelligence.topic_history import (
            dominant_entities,
            is_repeat_of_history,
            significant_tokens,
        )
        from pipeline.intelligence.topic_quality import validate_topic_quality

        dominated = dominant_entities(historical, recent_n=5)
    except Exception:
        dominated = set()

        def is_repeat_of_history(topic: str, historical: Sequence[str], *, recent_n: int = 12) -> bool:  # type: ignore
            return topic.lower() in exclude_exact

        def significant_tokens(text: str) -> set[str]:  # type: ignore
            return set()

        def validate_topic_quality(topic_text: str, *, niche: str = "") -> dict[str, Any]:  # type: ignore
            return {"ok": True}

    out: list[TopicCandidate] = []
    seen_keys: set[str] = set()
    ranked_seeds = list(dict.fromkeys(seeds))

    def _avoid_score(title: str) -> int:
        toks = significant_tokens(title)
        return len(toks & dominated)

    ranked_seeds.sort(key=_avoid_score)

    for raw in ranked_seeds:
        title = raw.strip()
        if not title or title.lower() in exclude_exact:
            continue
        if is_repeat_of_history(title, historical, recent_n=16):
            continue
        quality = validate_topic_quality(title, niche=niche)
        if not quality.get("ok"):
            continue
        blocked_hit = any(b and b.lower() in title.lower() for b in profile.forbidden_topics)
        if blocked_hit:
            continue
        cand_dict = {
            "title": title,
            "canonical_topic": title,
            "format": fmt.value,
            "channel_id": profile.channel_id,
            "niche": niche,
            "sub_niche": sub,
            "audience": audience,
            "language": profile.language,
            "source": "discovery",
            "relevance_reason": f"Channel niche {niche}",
            "novelty_reason": "Rotated niche seeds + anti-repeat history",
            "metadata": {
                "provenance": dict(provenance),
                "discovery_context": {
                    "channel_id": profile.channel_id,
                    "niche": niche,
                    "sub_niche": sub,
                    "audience": audience,
                    "language": profile.language,
                    "region": profile.target_region,
                    "format": fmt.value,
                    "historical_count": len(historical),
                    "reserved_count": len(reserved),
                    "rotation_offset": rot % 10_000,
                },
            },
        }
        ok, _issues = validate_candidate_dict(cand_dict)
        if not ok:
            continue
        c = candidate_from_dict(cand_dict)
        key = c.canonical_topic.lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(c)
        if len(out) >= count:
            break

    if require_non_empty and not out:
        raise DiscoveryEmptyError("discovery produced zero candidates")
    return out
