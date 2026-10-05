"""Duration contract authority — Short/Long target vs max (RCP-06B).

Extends existing duration_budget helpers. Not a new engine.
Single place for script / plan / runtime to resolve the same contract.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence


# Agnes reliable spoken window ~7–10s; budget uses 8.5s including ~1s hold.
SECONDS_PER_BEAT = 8.5

# Fallback defaults if Settings unavailable (keep in sync with app.config.Settings)
_DEFAULT_SHORT_TARGET = 60
_DEFAULT_SHORT_MAX = 120
_DEFAULT_LONG_TARGET = 180
_DEFAULT_LONG_MAX = 300

DURATION_CONTRACT_SCHEMA = "amp_duration_contract_v1"
DURATION_RECONCILIATION_SCHEMA = "amp_duration_reconciliation_v1"

# Material under-target threshold (aligns with artifact ~70% truncation suspicion).
# actual/planned must reach at least this fraction of contract target_seconds.
MIN_ACTUAL_FRACTION_OF_TARGET = 0.70


def normalize_video_type(video_type: str | None) -> str:
    raw = str(video_type or "short").strip()
    vt = raw.lower()
    if vt in ("long", "lng") or raw.upper() == "LONG":
        return "long"
    return "short"


def _settings_target_max(video_type: str) -> tuple[int, int]:
    vt = normalize_video_type(video_type)
    try:
        from app.config import settings

        if vt == "long":
            return int(settings.long_target_seconds), int(settings.long_max_seconds)
        return int(settings.short_target_seconds), int(settings.short_max_seconds)
    except Exception:
        if vt == "long":
            return _DEFAULT_LONG_TARGET, _DEFAULT_LONG_MAX
        return _DEFAULT_SHORT_TARGET, _DEFAULT_SHORT_MAX


def resolve_duration_contract(
    video_type: str = "short",
    *,
    max_seconds: Optional[int | float] = None,
    target_seconds: Optional[int | float] = None,
) -> dict[str, Any]:
    """
    Canonical Short/Long duration contract.

    - target_seconds: planning / script packing aim
    - max_seconds: hard runtime ceiling (never silently drop scenes to fit)
    """
    vt = normalize_video_type(video_type)
    t_def, m_def = _settings_target_max(vt)
    target = int(round(float(target_seconds))) if target_seconds is not None else t_def
    maximum = int(round(float(max_seconds))) if max_seconds is not None else m_def
    if target < 1:
        target = t_def
    if maximum < 1:
        maximum = m_def
    if target > maximum:
        target = maximum
    return {
        "schema": DURATION_CONTRACT_SCHEMA,
        "video_type": vt,
        "target_seconds": int(target),
        "max_seconds": int(maximum),
        "authority": "pipeline.duration_budget.resolve_duration_contract",
    }


def planned_scene_count(max_seconds: int, video_type: str = "short") -> int:
    """
    How many dialogue beats the director must write so spoken+visual runtime
    can reach the planning budget.

    Callers should pass contract['target_seconds'] for script planning and
    contract['max_seconds'] only when packing to the hard ceiling.
    """
    n = int(round(float(max_seconds or 0) / SECONDS_PER_BEAT))
    vt = normalize_video_type(video_type)
    if vt == "long":
        return max(14, min(32, n or 14))
    return max(8, min(18, n or 8))


def planned_scene_count_for_contract(contract: Mapping[str, Any]) -> int:
    c = dict(contract or {})
    return planned_scene_count(int(c.get("target_seconds") or 0), str(c.get("video_type") or "short"))


def scene_count_instruction(max_seconds: int, video_type: str = "short") -> str:
    n = planned_scene_count(max_seconds, video_type)
    return (
        f"{n} scenes (HARD: pack spoken runtime toward {max_seconds}s; "
        f"~{SECONDS_PER_BEAT}s per beat including 1s moving hold; "
        "do not write a 4-scene short for a 2-minute budget)"
    )


def validate_timeline_against_contract(
    *,
    dialogue_duration_sec: float,
    visual_duration_sec: float,
    contract: Mapping[str, Any],
) -> list[str]:
    """Planning blocks when timeline cannot fit the hard max (RCP-02 / RCP-06B)."""
    blocks: list[str] = []
    mx = float(contract.get("max_seconds") or 0)
    if mx <= 0:
        return blocks
    dlg = float(dialogue_duration_sec or 0)
    vis = float(visual_duration_sec or 0)
    # Allow small float slack
    if dlg > mx + 0.5:
        blocks.append(
            f"PRODUCTION_INCOMPLETE:dialogue_exceeds_max_duration:dlg={dlg:.2f}:max={mx:.2f}"
        )
    if vis > mx + 0.5:
        blocks.append(
            f"PRODUCTION_INCOMPLETE:visual_exceeds_max_duration:vis={vis:.2f}:max={mx:.2f}"
        )
    return blocks


def min_acceptable_duration_sec(contract: Mapping[str, Any]) -> float:
    """Floor for actual/planned content vs target (not a second contract)."""
    target = float(contract.get("target_seconds") or 0)
    if target <= 0:
        return 0.0
    return float(target) * float(MIN_ACTUAL_FRACTION_OF_TARGET)


def validate_plan_meets_target(
    *,
    dialogue_duration_sec: float,
    visual_duration_sec: float,
    beat_or_scene_count: int,
    contract: Mapping[str, Any],
) -> list[str]:
    """
    Gate A planning actualization: under-target plans cannot be READY_FOR_GENERATION.

    Does not replace validate_timeline_against_contract (max ceiling).
    Does not pad or invent scenes — only blocks incomplete plans.
    """
    blocks: list[str] = []
    target = float(contract.get("target_seconds") or 0)
    if target <= 0:
        return blocks
    dlg = float(dialogue_duration_sec or 0)
    vis = float(visual_duration_sec or 0)
    content = max(dlg, vis)
    min_ok = min_acceptable_duration_sec(contract)
    if content + 0.5 < min_ok:
        blocks.append(
            "PRODUCTION_INCOMPLETE:planned_duration_below_target:"
            f"planned={content:.2f}:min={min_ok:.2f}:target={target:.2f}"
        )
        required_scenes = planned_scene_count_for_contract(contract)
        n = int(beat_or_scene_count or 0)
        if n < required_scenes:
            blocks.append(
                "PRODUCTION_INCOMPLETE:insufficient_scene_budget:"
                f"scenes={n}:required={required_scenes}:target={target:.2f}"
            )
    return blocks


def reconcile_rendered_duration(
    *,
    actual_duration_sec: Optional[float],
    contract: Mapping[str, Any],
    scene_count: Optional[int] = None,
    planned_duration_sec: Optional[float] = None,
) -> dict[str, Any]:
    """
    Gate A final reconciliation — sole duration authority remains resolve_duration_contract.

    planned_duration_sec is recorded for audit only; never treated as actual.
    UNKNOWN duration → status UNKNOWN (never PASS).
    """
    c = resolve_duration_contract(
        str(contract.get("video_type") or "short"),
        max_seconds=contract.get("max_seconds"),
        target_seconds=contract.get("target_seconds"),
    )
    target = float(c["target_seconds"])
    maximum = float(c["max_seconds"])
    min_ok = min_acceptable_duration_sec(c)
    out: dict[str, Any] = {
        "schema": DURATION_RECONCILIATION_SCHEMA,
        "authority": "pipeline.duration_budget.reconcile_rendered_duration",
        "contract": c,
        "planned_duration_sec": planned_duration_sec,
        "planned_is_not_actual": True,
        "actual_duration_sec": actual_duration_sec,
        "scene_count": scene_count,
        "min_acceptable_sec": min_ok,
        "max_seconds": maximum,
        "target_seconds": target,
        "blocks": [],
        "status": "UNKNOWN",
        "allows_completed": False,
        "allows_approved": False,
        "allows_publishable": False,
        "allows_ready_to_upload": False,
    }
    if actual_duration_sec is None:
        out["blocks"] = ["PRODUCTION_INCOMPLETE:duration_observation_absent"]
        out["status"] = "UNKNOWN"
        out["reason"] = "actual_duration_unknown"
        return out
    try:
        actual = float(actual_duration_sec)
    except (TypeError, ValueError):
        out["blocks"] = ["PRODUCTION_INCOMPLETE:duration_observation_invalid"]
        out["status"] = "UNKNOWN"
        out["reason"] = "actual_duration_unknown"
        return out
    if actual <= 0:
        out["blocks"] = ["PRODUCTION_INCOMPLETE:duration_observation_nonpositive"]
        out["status"] = "UNKNOWN"
        out["reason"] = "actual_duration_unknown"
        return out

    out["actual_duration_sec"] = actual
    blocks: list[str] = []
    if actual > maximum + 0.5:
        blocks.append(
            f"PRODUCTION_INCOMPLETE:actual_exceeds_max_duration:actual={actual:.2f}:max={maximum:.2f}"
        )
    if actual + 0.01 < min_ok:
        blocks.append(
            "PRODUCTION_INCOMPLETE:actual_duration_below_target:"
            f"actual={actual:.2f}:min={min_ok:.2f}:target={target:.2f}"
        )
        if scene_count is not None:
            required = planned_scene_count_for_contract(c)
            if int(scene_count) < required:
                blocks.append(
                    "PRODUCTION_INCOMPLETE:insufficient_scene_budget:"
                    f"scenes={int(scene_count)}:required={required}"
                )

    out["blocks"] = blocks
    if blocks:
        out["status"] = "FAIL"
        out["reason"] = blocks[0]
        return out

    out["status"] = "PASS"
    out["reason"] = "actual_duration_meets_contract"
    out["allows_completed"] = True
    out["allows_approved"] = True
    out["allows_publishable"] = True
    out["allows_ready_to_upload"] = True
    return out


def raise_if_rendered_duration_blocks(*, reconciliation: Mapping[str, Any]) -> None:
    """Fail closed before ready_to_upload / COMPLETED."""
    st = str(reconciliation.get("status") or "UNKNOWN").upper()
    if st == "PASS":
        return
    reason = str(reconciliation.get("reason") or (reconciliation.get("blocks") or ["duration_blocked"])[0])
    if st == "UNKNOWN":
        raise RuntimeError(f"duration_reconciliation_unknown:{reason}")
    raise RuntimeError(f"duration_reconciliation_blocked:{reason}")


def load_duration_reconciliation(work_dir: Any) -> Optional[dict[str, Any]]:
    """Load DURATION_RECONCILIATION.json from a job work directory."""
    from pathlib import Path

    path = Path(work_dir) / "DURATION_RECONCILIATION.json"
    if not path.is_file():
        return None
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def write_duration_reconciliation(work_dir: Any, reconciliation: Mapping[str, Any]) -> Any:
    from pathlib import Path
    import json

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    path = work / "DURATION_RECONCILIATION.json"
    path.write_text(json.dumps(dict(reconciliation), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def c11_regression_cases() -> list[dict[str, Any]]:
    """Canonical under-duration regressions from Phase 6K / C11 evidence."""
    return [
        {
            "name": "c11_short_7_2s",
            "video_type": "short",
            "actual_duration_sec": 7.2,
            "expect_status": "FAIL",
            "expect_blocks_substring": "actual_duration_below_target",
        },
        {
            "name": "c11_long_8_85s",
            "video_type": "long",
            "actual_duration_sec": 8.85,
            "expect_status": "FAIL",
            "expect_blocks_substring": "actual_duration_below_target",
        },
    ]


def raise_if_budget_would_drop_scenes(
    *,
    scene_index: int,
    scene_count: int,
    accumulated_sec: float,
    max_seconds: float,
) -> None:
    """
    RCP-06B: replacing silent `break` — if max ceiling is hit with scenes left, fail closed.
    """
    remaining = int(scene_count) - (int(scene_index) + 1)
    if remaining <= 0:
        return
    if float(accumulated_sec) >= float(max_seconds) - 1.0:
        raise RuntimeError(
            "PRODUCTION_INCOMPLETE:duration_budget_exhausted_with_scenes_remaining:"
            f"at_scene={scene_index}:remaining={remaining}:"
            f"total={float(accumulated_sec):.2f}:max={float(max_seconds):.2f}"
        )


def assert_all_planned_scenes_produced(
    *,
    planned_scene_count_n: int,
    produced_scene_count: int,
) -> None:
    """Fail closed when runtime produced fewer scenes than the approved plan."""
    planned = int(planned_scene_count_n)
    produced = int(produced_scene_count)
    if planned > 0 and produced < planned:
        raise RuntimeError(
            "PRODUCTION_INCOMPLETE:duration_budget_dropped_scenes:"
            f"produced={produced}:planned={planned}"
        )


def trim_would_cut_coverage(src_duration_sec: float, max_seconds: float, *, slack_sec: float = 2.5) -> bool:
    """True when a hard `-t max` trim would remove covered dialogue/visual tail."""
    return float(src_duration_sec) > float(max_seconds) + float(slack_sec)


def contract_from_plan(plan: Mapping[str, Any] | None) -> dict[str, Any]:
    """Resolve contract from a director/production plan dict."""
    plan = plan or {}
    embedded = plan.get("duration_contract")
    if isinstance(embedded, dict) and embedded.get("max_seconds"):
        return resolve_duration_contract(
            str(embedded.get("video_type") or plan.get("video_type") or plan.get("format") or "short"),
            max_seconds=embedded.get("max_seconds"),
            target_seconds=embedded.get("target_seconds"),
        )
    vt = plan.get("video_type") or plan.get("format") or plan.get("videoType") or "short"
    return resolve_duration_contract(
        str(vt),
        max_seconds=plan.get("max_seconds"),
        target_seconds=plan.get("target_duration_sec") or plan.get("target_seconds"),
    )
