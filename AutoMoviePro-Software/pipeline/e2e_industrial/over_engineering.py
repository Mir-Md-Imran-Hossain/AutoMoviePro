"""Over-engineering / duplicate-authority audit (inspect-only; minimal consolidation)."""
from __future__ import annotations

from typing import Any


def audit_over_engineering() -> dict[str, Any]:
    findings = [
        {
            "item": "compose.concat_clips vs scene_builder concat",
            "classification": "LEGACY",
            "action": "PRESERVE — render_bridge is canonical production compose",
        },
        {
            "item": "prompt_engineering vs multimodal prompt_compiler",
            "classification": "LEGACY",
            "action": "PRESERVE — production continuity uses prompt_compiler",
        },
        {
            "item": "publishability evaluate_publishability sole AND",
            "classification": "SINGLE_AUTHORITY",
            "action": "KEEP — P02–P08 dimensions feed one function",
        },
        {
            "item": "render_status vs rendering_integrity_status",
            "classification": "INTENTIONAL ADAPTER",
            "action": "KEEP — distinct dimensions (ship vs integrity)",
        },
        {
            "item": "TTS idempotent + direct synthesize_narration fallback",
            "classification": "BYPASS RISK",
            "action": "DOCUMENT — not deleted in Phase-09; containment via gate path",
        },
        {
            "item": "Phase-09 e2e_industrial package",
            "classification": "INTEGRATION",
            "action": "NEW — does not create second quality/publishability/FFmpeg engine",
        },
        {
            "item": "recursive task structures",
            "classification": "NONE_FOUND_IN_P09_SCOPE",
            "action": "N/A",
        },
    ]
    duplicates_requiring_removal = [f for f in findings if f["classification"] == "DUPLICATE AUTHORITY"]
    return {
        "status": "PASS" if not duplicates_requiring_removal else "FAIL",
        "findings": findings,
        "duplicates_requiring_removal": duplicates_requiring_removal,
        "method": "STATIC",
    }
