"""Localization preflight — BEFORE translation provider (AMP-004 Phase-06)."""
from __future__ import annotations

from typing import Any, Optional, Sequence

from pipeline.lang_config import TARGET_LANG_CODES
from pipeline.localization_consistency.contract import LocalizationContract, build_localization_contract


class LocalizationPreflightError(ValueError):
    def __init__(self, message: str, *, issues: Optional[list[str]] = None) -> None:
        super().__init__(message)
        self.issues = list(issues or [])


SUPPORTED_LANGS = set(TARGET_LANG_CODES) | {
    "en", "bn", "hi", "ur", "ta", "ml", "ar", "fa", "he", "es", "fr", "de", "pt", "id", "tr", "ru", "ja", "ko", "zh",
}


def preflight_localization_request(
    *,
    source_text: str,
    source_language: str,
    target_language: str,
    job_id: str = "",
    scene_id: str = "",
    dialogue_id: str = "",
    segment_id: str = "",
    revision_id: str = "",
    speaker_id: str = "",
    block: bool = True,
) -> dict[str, Any]:
    """Deterministic validation before expensive translate provider call."""
    issues: list[str] = []
    src = (source_text or "").strip()
    src_lang = (source_language or "").strip().lower()
    tgt = (target_language or "").strip().lower()

    if not src:
        issues.append("missing_source")
    if not tgt:
        issues.append("missing_target")
    if not src_lang:
        issues.append("invalid_language:source_empty")
    if tgt and tgt.split("-")[0] not in {x.split("-")[0] for x in SUPPORTED_LANGS}:
        issues.append(f"invalid_language:{tgt}")
    if src_lang and tgt and src_lang.split("-")[0] == tgt.split("-")[0]:
        # same language — not an error; caller may short-circuit
        pass
    if dialogue_id is not None and str(dialogue_id) != "" and not str(dialogue_id).strip():
        issues.append("invalid_dialogue_identity")
    if scene_id is not None and str(scene_id) != "" and not str(scene_id).strip():
        issues.append("invalid_scene_identity")

    contract = None
    if src and tgt:
        contract = build_localization_contract(
            job_id=job_id,
            scene_id=scene_id or "0",
            dialogue_id=dialogue_id or "dlg",
            source_text=src,
            source_language=src_lang or "en",
            target_language=tgt,
            segment_id=segment_id,
            revision_id=revision_id,
            speaker_id=speaker_id,
        )

    result = {
        "status": "BLOCK" if issues else "PASS",
        "issues": issues,
        "method": "DETERMINISTIC",
        "contract": contract.to_dict() if contract else None,
        "contract_fingerprint": contract.contract_fingerprint if contract else "",
    }
    if block and issues:
        raise LocalizationPreflightError(f"localization_preflight_blocked:{issues[0]}", issues=issues)
    return result
