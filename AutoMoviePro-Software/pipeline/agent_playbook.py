"""
Chernobyl / AV history playbook — durable lessons for the repair agent.

This encodes WHY the user asked for each change and HOW the agent must detect
+ fix it WITHOUT burning Gemini/Agnes API calls when ffmpeg + gates suffice.

Cost policy (mandatory):
  1) Prefer deterministic gates + local ffmpeg repair over Gemini critic.
  2) At most ONE Agnes create per scene (max_av_retries≤1).
  3) Skip multimodal critic when self-repair agent already PASSED.
  4) Skip meta-audit when agent_passed and no visual hard-fail codes.
  5) TTS only when needed (cutoff/pace/last-word/clarity) or one clarity pass;
     never hammer TTS across all models on daily-quota 0 keys.
  6) Never sleep mid-scene for Google quota — cool down only between clips.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PLAYBOOK_PATH = Path(__file__).resolve().parent / "agent_playbook.json"

# History faults → detect codes → repair recipe → avoid (wrong past fixes)
FAULT_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "dialogue_cutoff",
        "user_symptom": "ডায়লগ শেষ হওয়ার আগে ভিডিও শেষ / মাঝপথে কথা কাটা",
        "why_change": "English Agnes often ends mid-syllable; soft-accept hid it.",
        "detect": ["dialogue_cutoff", "last_word_incomplete"],
        "repair": "mux_fit_av_setpts with complete paced TTS over Agnes picture",
        "never_do": ["soft-accept on critic 429", "another Agnes regen as first fix"],
        "api_cost": "1 TTS max; 0 Gemini; 0 Agnes",
    },
    {
        "id": "early_end_long_freeze",
        "user_symptom": "কথা শেষ, ভিডিও আটকে থাকে / লোকালাইজে ফ্রিজ",
        "why_change": "stream_loop / extreme setpts looked like freeze while speech continued.",
        "detect": ["localize_freeze_risk", "end_frame_freeze", "missing_tail_hold"],
        "repair": "mild setpts≤1.18 + atempo speech; apad ~1s silence AFTER speech",
        "never_do": ["stream_loop", "tpad freeze for length match", "stretch >18%"],
        "api_cost": "0",
    },
    {
        "id": "speech_pace_pitch",
        "user_symptom": "কোনো ডায়লগ তাড়াতাড়ি, কোনো ধীর; 'crime'→cryme",
        "why_change": "Agnes native pace inconsistent; closing words mumbled.",
        "detect": ["speech_pace_too_fast", "speech_pace_too_slow", "last_word_incomplete"],
        "repair": "Charon TTS + atempo normalize to ~2.3 wps; same voice across clips",
        "never_do": ["keep rushed Agnes audio when pace gate fails"],
        "api_cost": "1 TTS when pace/last-word fails",
    },
    {
        "id": "black_tail_pad",
        "user_symptom": "অডিও মেলাতে শেষে কালো স্ক্রিন",
        "why_change": "Agnes fades to black; tpad cloned the black frame.",
        "detect": ["black_tail_freeze"],
        "repair": "trim trailing black then setpts slow/fast on content",
        "never_do": ["tpad=clone on black last frame"],
        "api_cost": "0",
    },
    {
        "id": "freeze_instead_of_setpts",
        "user_symptom": "লাস্টে ফ্রেম থামিয়ে দেয় — স্লো/ফাস্ট চাই",
        "why_change": "User policy: match AV by setpts/atempo, not freeze-hold.",
        "detect": ["end_frame_freeze"],
        "repair": "mux_fit_av_setpts (motion continues through post-silence)",
        "never_do": ["extend_hold_last_content_frame / tpad for duration fit"],
        "api_cost": "0",
    },
    {
        "id": "critic_outage_soft_accept",
        "user_symptom": "এজেন্ট ভাঙা ক্লিপ রেখে দেয় যখন Gemini 429",
        "why_change": "Critic fallback was treated as pass without local repair.",
        "detect": ["any HARD_QUALITY_GATES fail"],
        "repair": "run_av_self_repair_agent BEFORE accept; never soft-accept hard gates",
        "never_do": ["return CRITIC_OUTAGE keep without agent repair"],
        "api_cost": "0 Gemini when agent already passed",
    },
    {
        "id": "mid_scene_quota_sleep",
        "user_symptom": "রিপেয়ারের আগে ঘণ্টার cool-down — ভাঙা ফাইল থেকে যায়",
        "why_change": "Shared Google quota sleep blocked Agnes regen mid-clip.",
        "detect": ["quota_backoff during scene"],
        "repair": "cool down only in train loop between clips; repair with local ffmpeg/TTS",
        "never_do": ["wait_for_quota_if_needed inside _resolve_footage / mid-mux"],
        "api_cost": "saves wasted idle + avoids skip-storm",
    },
    {
        "id": "wrong_deliverable_file",
        "user_symptom": "agnes_*.mp4 দেখে মনে হয় ফিক্স হয়নি",
        "why_change": "Raw Agnes is not the master; repaired scene_*.mp4 is.",
        "detect": ["missing scene_00_master_for_localize.txt"],
        "repair": "write master marker; localize from repaired master not raw Agnes",
        "never_do": ["ship agnes_*.mp4 as final"],
        "api_cost": "0",
    },
    {
        "id": "api_churn",
        "user_symptom": "১২–১৫ ঘণ্টা / বারবার API / ৩× regen",
        "why_change": "Too many critic+Agnes loops; first-shot must be strong.",
        "detect": ["attempt>2", "critic_api_failed spam"],
        "repair": "harden prompt once; agent repair; max 1 Agnes regen; skip critic if agent ok",
        "never_do": ["3 soft critic loops", "meta-audit on every quota fallback"],
        "api_cost": "target ≤1 Agnes + ≤1 TTS + 0 Gemini when gates green",
    },
]

# Short durable rules synced into av_sync_training_rules.json
HISTORY_TRAINING_RULES: List[str] = [
    "Finish every spoken word before clip end; leave ~1s silence AFTER the last syllable while picture keeps moving (setpts) — never cut mid-word.",
    "AV length match MUST use mild setpts (slow/fast) and/or pitch-preserving atempo — NEVER tpad/freeze last frame and NEVER clone trailing black.",
    "Trim Agnes trailing black BEFORE any length fit; ending on a black screen while audio plays is a critical fail.",
    "Speech pace must stay near documentary ~2.3 words/sec; rushed closing nouns (e.g. crime→cryme) require Charon TTS remux.",
    "When Gemini critic is on 429/outage: run deterministic AV self-repair agent; NEVER soft-accept hard gates (cutoff/pace/black/freeze/hold).",
    "Never sleep mid-scene for Google quota; cool down only between clips. Mid-scene sleep leaves broken masters on disk.",
    "Deliverable master is scene_XX_*.mp4 (agent-repaired), never raw agnes_XX_*.mp4. Write scene_XX_master_for_localize.txt.",
    "API budget: prefer local gates+ffmpeg; max 1 Agnes create per scene; skip multimodal critic when self-repair already PASSED; avoid meta-audit spam.",
    "Localization: replace audio+subs only; mild setpts≤1.18 else atempo speech — no stream_loop, no mid-speech freeze.",
    "Master English: Agnes picture + consistent Charon narration when native Agnes pace/cutoff fails; keep pitch consistent across neighboring clips.",
]


def sync_history_rules_to_training(*, source: str = "history_playbook") -> int:
    """Idempotently append HISTORY_TRAINING_RULES into the critic rules file."""
    from pipeline.av_sync_critic import apply_training_rule

    n = 0
    for rule in HISTORY_TRAINING_RULES:
        before = len(__import__("pipeline.av_sync_critic", fromlist=["load_training_rules"]).load_training_rules())
        apply_training_rule(rule, source=source)
        after = len(__import__("pipeline.av_sync_critic", fromlist=["load_training_rules"]).load_training_rules())
        if after > before:
            n += 1
    _write_playbook_json()
    # Remove obsolete contradictory freeze-clone rule if still present
    _scrub_obsolete_rules()
    logger.info("Synced %s new history training rules", n)
    return n


def _scrub_obsolete_rules() -> None:
    """Drop rules that teach the wrong freeze/black-clone pad (superseded by setpts)."""
    from pipeline.av_sync_critic import TRAINING_RULES_PATH, load_training_rules

    rules = load_training_rules()
    bad_bits = (
        "tpad clone only after content",
        "trim/replace black with the last non-black content frame (tpad",
    )
    cleaned = [r for r in rules if not any(b.lower() in r.lower() for b in bad_bits)]
    if len(cleaned) != len(rules):
        TRAINING_RULES_PATH.write_text(
            json.dumps(
                {"rules": cleaned[-80:], "updated_by": "history_playbook_scrub"},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def _write_playbook_json() -> None:
    PLAYBOOK_PATH.write_text(
        json.dumps(
            {
                "cost_policy": [
                    "gates+ffmpeg first",
                    "max 1 Agnes per scene",
                    "skip Gemini critic when agent PASSED",
                    "no mid-scene quota sleep",
                    "TTS only on clarity/pace/cutoff need",
                ],
                "faults": FAULT_CATALOG,
                "training_rules": HISTORY_TRAINING_RULES,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def should_skip_gemini_critic(
    agent_report: Optional[Dict[str, Any]],
    *,
    visual_passed: bool = False,
) -> bool:
    """Cost saver: skip multimodal critic only when explicitly opted in.

    Quality-first default: audio/agent pass alone never skips Gemini critic.
    Requires AMP_SKIP_GEMINI_CRITIC=1 AND agent passed AND visual_passed AND
    not needs_visual_regen.
    """
    import os

    if str(os.environ.get("AMP_SKIP_GEMINI_CRITIC") or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False
    if not agent_report or not bool(agent_report.get("passed")):
        return False
    if agent_report.get("needs_visual_regen"):
        return False
    return bool(visual_passed)


def should_force_tts(
    *,
    prefer_agnes_native: bool,
    pre_diagnosis: Optional[Dict[str, Any]],
) -> bool:
    """
    Cost-aware TTS: force clarity when Agnes native is used AND
    (gates already failing OR we always want one clarity pass for documentary).

    Documentary training: one Charon pass is cheaper than Agnes regen + critic loops.
    """
    if not prefer_agnes_native:
        return False
    if not pre_diagnosis:
        return True  # one clarity pass for Agnes-native masters
    if not pre_diagnosis.get("passed", True):
        return True
    # Even if energy gates pass, Agnes often mumbles — still one TTS for pitch match
    return True


def repair_hint_for_hits(hard_hits: List[str]) -> str:
    hits = set(hard_hits or [])
    for fault in FAULT_CATALOG:
        if hits & set(fault.get("detect") or []):
            return str(fault.get("repair") or "")
    return "run_av_self_repair_agent with mux_fit_av_setpts"


# Auto-sync on import (idempotent, cheap)
try:
    sync_history_rules_to_training()
except Exception as exc:  # pragma: no cover
    logger.debug("playbook sync deferred: %s", exc)
