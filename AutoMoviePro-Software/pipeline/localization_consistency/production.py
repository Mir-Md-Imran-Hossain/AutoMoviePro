"""Production localization consistency wiring (AMP-004 Phase-06)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.localization_consistency.contract import (
    LocalizationContract,
    build_localization_contract,
    localization_fingerprint,
)
from pipeline.localization_consistency.drift import validate_translation_drift
from pipeline.localization_consistency.gate import persist_localization_contract, persist_localization_gate
from pipeline.localization_consistency.preflight import LocalizationPreflightError, preflight_localization_request
from pipeline.localization_consistency.rtl_font import validate_rtl_and_font
from pipeline.localization_consistency.subtitle_rules import (
    validate_line_breaking,
    validate_reading_speed,
    validate_subtitle_identity,
    validate_subtitle_timing,
)
from pipeline.localization_consistency.text_layout import validate_text_plan, validate_visual_text_consistency

logger = logging.getLogger(__name__)


def validate_localized_pair(
    contract: LocalizationContract,
    localized_text: str,
    *,
    speaker_changed: bool = False,
    emotion_changed: bool = False,
    visual_objects: Optional[list[str]] = None,
) -> dict[str, Any]:
    drift = validate_translation_drift(
        contract, localized_text, speaker_changed=speaker_changed, emotion_changed=emotion_changed
    )
    issues = list(drift.get("issues") or [])
    if contract.text_plan:
        # update subtitle content
        if contract.text_plan.elements:
            contract.text_plan.elements[0].content = localized_text
        tp = validate_text_plan(
            contract.text_plan, max_chars_per_line=int(contract.max_chars_per_line or 42)
        )
        issues.extend(tp.get("issues") or [])
    if visual_objects:
        issues.extend(validate_visual_text_consistency(visual_objects=visual_objects, text_content=localized_text))
    rtl = validate_rtl_and_font(contract.target_language, localized_text)
    # RTL UNKNOWN is recorded; FAIL font hard-blocks
    if rtl.get("status") == "FAIL":
        issues.extend(rtl.get("issues") or ["rtl_font_fail"])
    status = "BLOCK" if issues else "PASS"
    if not issues and rtl.get("status") == "UNKNOWN" and contract.rtl:
        status = "UNKNOWN"
    return {
        "status": status,
        "issues": issues,
        "drift": drift,
        "rtl": rtl,
        "method": "DETERMINISTIC",
        "contract_fingerprint": contract.contract_fingerprint,
    }


def apply_production_localization(
    work_dir: Path,
    *,
    job_id: str,
    scene_id: str,
    dialogue_id: str,
    source_text: str,
    source_language: str,
    target_language: str,
    localized_text: str = "",
    segment_id: str = "",
    revision_id: str = "",
    speaker_id: str = "",
    emotion_intent: str = "",
    visual_objects: Optional[list[str]] = None,
    block_on_critical: bool = True,
    audio_path: Optional[Path] = None,
    planned_subtitle_cues: Optional[list] = None,
) -> dict[str, Any]:
    """Build contract, optional drift validate, persist provenance.

    Optional ``audio_path`` attaches faster-whisper speech-timing observation
    evidence (never treats planned timing as actual PASS).
    """
    work_dir = Path(work_dir)
    pre = preflight_localization_request(
        source_text=source_text,
        source_language=source_language,
        target_language=target_language,
        job_id=job_id,
        scene_id=scene_id,
        dialogue_id=dialogue_id,
        segment_id=segment_id,
        revision_id=revision_id,
        speaker_id=speaker_id,
        block=block_on_critical,
    )
    contract = build_localization_contract(
        job_id=job_id,
        scene_id=scene_id,
        dialogue_id=dialogue_id,
        source_text=source_text,
        source_language=source_language,
        target_language=target_language,
        segment_id=segment_id,
        revision_id=revision_id,
        speaker_id=speaker_id,
        emotion_intent=emotion_intent,
        localized_text=localized_text,
    )
    result: dict[str, Any] = {
        "preflight": pre,
        "contract": contract.to_dict(),
        "contract_fingerprint": contract.contract_fingerprint,
        "_localization_applied": True,
    }
    if localized_text:
        validation = validate_localized_pair(
            contract, localized_text, visual_objects=visual_objects
        )
        result["validation"] = validation
        if validation["status"] == "BLOCK" and block_on_critical:
            raise LocalizationPreflightError(
                f"localization_drift_blocked:{validation['issues'][0]}",
                issues=validation["issues"],
            )
    if audio_path is not None:
        try:
            from pipeline.localization_consistency.subtitle_rules import (
                attach_speech_timing_observation,
            )

            result["speech_timing_evidence"] = attach_speech_timing_observation(
                audio_path=str(audio_path),
                planned_cues=planned_subtitle_cues or [],
                language_hint=target_language or source_language,
            )
        except Exception as exc:
            result["speech_timing_evidence"] = {
                "status": "OBSERVATION_UNAVAILABLE",
                "reason": "attach_failed",
                "detail": str(exc)[:200],
                "planned_as_actual_pass": False,
                "unknown_as_pass": False,
            }
    persist_localization_contract(
        work_dir, result["contract"], key=f"{scene_id}_{dialogue_id}_{target_language}"
    )
    return result


def run_production_localization_gate(
    work_dir: Path,
    *,
    job_id: str = "",
    multilingual: bool = False,
    final_path: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Aggregate localization evidence for publishability.
    Monolingual jobs → ABSENT (non-applicable).
    Multilingual without contracts → UNKNOWN.
    """
    work_dir = Path(work_dir)
    job = job_id or work_dir.name
    contracts_dir = work_dir / "localization_contracts"
    rows: list[dict[str, Any]] = []
    if contracts_dir.is_dir():
        import json

        for p in sorted(contracts_dir.glob("*.json")):
            try:
                rows.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass

    # Also inspect LOCALIZED manifests if present
    loc_root = work_dir / "LOCALIZED"
    has_localized_outputs = loc_root.is_dir() and any(loc_root.rglob("*.srt"))

    if not multilingual and not rows and not has_localized_outputs:
        gate = {
            "status": "ABSENT",
            "verdict": "ABSENT",
            "reason": "localization_not_applicable",
            "job_id": job,
            "authority": "pipeline.localization_consistency",
            "mandatory_unknown": False,
        }
        persist_localization_gate(work_dir, gate)
        return gate

    issues: list[str] = []
    if multilingual and not rows and not has_localized_outputs:
        issues.append("localization_unverified")
        status = "UNKNOWN"
    else:
        status = "PASS"

    # Aggregate per-contract semantic dimensions (PART-5H)
    meaning_statuses: list[str] = []
    name_statuses: list[str] = []
    number_statuses: list[str] = []
    negation_statuses: list[str] = []
    temporal_statuses: list[str] = []
    naturalness_statuses: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        val = row.get("validation") if isinstance(row.get("validation"), dict) else {}
        drift = val.get("drift") if isinstance(val.get("drift"), dict) else row.get("drift") or {}
        if not isinstance(drift, dict):
            drift = {}
        st = str(val.get("status") or drift.get("status") or "").upper()
        iss = list(val.get("issues") or drift.get("issues") or [])
        if st == "BLOCK" or any("entity_missing" in i or "entity_substitution" in i for i in iss):
            name_statuses.append("FAIL")
        elif any("entity" in i for i in iss):
            name_statuses.append("UNKNOWN")
        else:
            name_statuses.append("PASS" if st in ("PASS", "OK", "") else st or "UNKNOWN")
        if any("number_mismatch" in i or "unit_mismatch" in i or "currency_mismatch" in i for i in iss):
            number_statuses.append("FAIL")
        else:
            number_statuses.append("PASS" if st != "BLOCK" else "FAIL")
        if any("negation" in i for i in iss):
            negation_statuses.append("FAIL")
        else:
            negation_statuses.append("PASS")
        if any("temporal" in i for i in iss):
            temporal_statuses.append("FAIL")
        else:
            temporal_statuses.append("PASS")
        if any(
            x in i
            for i in iss
            for x in ("omission", "english_as_localized", "action_omission", "addition_detected")
        ):
            meaning_statuses.append("FAIL")
        elif st == "BLOCK":
            meaning_statuses.append("FAIL")
        else:
            meaning_statuses.append("PASS")
        nat = str(drift.get("semantic_naturalness") or "UNKNOWN")
        naturalness_statuses.append(nat if nat else "UNKNOWN")
        if st == "BLOCK":
            issues.extend(iss or ["localization_block"])
            status = "BLOCKED"

    def _rollup(vals: list[str], *, unknown_ok: bool = False) -> str:
        if not vals:
            return "UNKNOWN" if multilingual else "ABSENT"
        if any(v == "FAIL" for v in vals):
            return "FAIL"
        if all(v == "PASS" for v in vals):
            return "PASS"
        if unknown_ok and any(v == "UNKNOWN" for v in vals):
            return "UNKNOWN"
        return "UNKNOWN" if any(v == "UNKNOWN" for v in vals) else "PASS"

    # Per-language final MP4 uniqueness (PART-5H) — LOCALIZED/{Lang}/video.mp4
    import hashlib

    lang_videos: dict[str, str] = {}
    hash_dupes: list[str] = []
    if loc_root.is_dir():
        for lang_dir in sorted(p for p in loc_root.iterdir() if p.is_dir()):
            mp4 = lang_dir / "video.mp4"
            if not mp4.is_file():
                continue
            lang = lang_dir.name
            try:
                h = hashlib.sha256(mp4.read_bytes()[: 2_000_000]).hexdigest()[:16]
            except Exception:
                h = "unreadable"
            lang_videos[lang] = h
        by_hash: dict[str, list[str]] = {}
        for lang, h in lang_videos.items():
            by_hash.setdefault(h, []).append(lang)
        for h, langs in by_hash.items():
            if h != "unreadable" and len(langs) > 1:
                hash_dupes.append(f"shared:{h}:{'|'.join(sorted(langs))}")
    per_lang_mp4 = "PASS" if lang_videos else ("UNKNOWN" if multilingual else "ABSENT")
    if multilingual and not lang_videos and has_localized_outputs:
        per_lang_mp4 = "UNKNOWN"
        issues.append("per_language_mp4_pending_or_missing")
    no_copy = "FAIL" if hash_dupes else ("PASS" if lang_videos else per_lang_mp4)
    if hash_dupes:
        issues.append("localized_mp4_hash_duplicate:" + ",".join(hash_dupes[:4]))
        status = "BLOCKED"

    # Subtitle artifact observation via Phase-04 style checks
    from pipeline.artifact_verification.verifiers import verify_subtitle_artifact

    for srt in list(work_dir.glob("**/*.srt"))[:24]:
        obs = verify_subtitle_artifact(srt)
        if obs.observation_status.value == "FAIL":
            issues.extend(obs.issues or ["subtitle_fail"])
            status = "BLOCKED"

    if final_path and Path(final_path).is_file():
        # Final composite text verification is structural (subtitle stream optional)
        from pipeline.idempotency.render_validation import probe_render_metadata

        meta = probe_render_metadata(Path(final_path))
        rows.append({"final_composite_observed": True, "has_audio": meta.get("has_audio"), "duration": meta.get("duration_sec")})

    if issues and status != "BLOCKED":
        status = "BLOCKED" if any("fail" in i or "mismatch" in i or "drift" in i for i in issues) else "UNKNOWN"

    from pipeline.localization_consistency.rtl_font import classify_rtl_support

    rtl_ok = bool(classify_rtl_support("ur").get("shaping_guaranteed"))
    gate = {
        "status": status,
        "verdict": status,
        "job_id": job,
        "contract_count": len(
            [
                r
                for r in rows
                if isinstance(r, dict) and (r.get("contract_fingerprint") or r.get("source_text"))
            ]
        ),
        "issues": issues,
        "authority": "pipeline.localization_consistency",
        "semantic_summary": {
            "meaning_preserve": _rollup(meaning_statuses),
            "names_preserve": _rollup(name_statuses),
            "numbers_preserve": _rollup(number_statuses),
            "negation_preserve": _rollup(negation_statuses),
            "tense_temporal_preserve": _rollup(temporal_statuses),
            "naturalness": _rollup(naturalness_statuses, unknown_ok=True),
            "unknown_is_not_pass": True,
            "rtl_shaping_guaranteed": rtl_ok,
            "per_language_mp4": per_lang_mp4,
            "localized_mp4_unique": no_copy,
            "language_video_hashes": lang_videos,
        },
        "provenance_chain": [
            "Script",
            "SceneIntent",
            "LocalizationContract",
            "LocalizedDialogue",
            "AudioPlan",
            "SubtitlePlan",
            "TextPlan",
            "Observation",
            "Publication",
        ],
    }
    persist_localization_gate(work_dir, gate)
    logger.info("localization gate job=%s status=%s contracts=%s", job, status, len(rows))
    return gate
