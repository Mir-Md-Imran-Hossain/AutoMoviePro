"""
Staggered trust-browse schedule.

Goal: every clock hour accumulates ≥5 minutes of human-like browsing,
spread in varied patterns so it never looks like a fixed cron bot.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app import db as store

META_KEY_PREFIX = "trust_browse_plan_"


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _make_hour_windows(hour: int) -> List[Dict[str, Any]]:
    """Return 1–3 non-overlapping windows inside `hour` (0–23)."""
    pattern = random.choices(
        ["single", "dual", "triple", "late_long"],
        weights=[35, 35, 20, 10],
        k=1,
    )[0]
    windows: List[Dict[str, Any]] = []

    if pattern == "single":
        duration = random.randint(5, 12)
        start_m = random.randint(2, max(3, 58 - duration))
        windows.append({"start_min": start_m, "duration_min": duration})
    elif pattern == "dual":
        d1 = random.randint(3, 7)
        d2 = random.randint(3, 8)
        # Ensure hour total ≥ 5
        if d1 + d2 < 5:
            d2 = 5 - d1
        gap = random.randint(18, 35)
        start1 = random.randint(1, 20)
        start2 = _clamp(start1 + d1 + gap, start1 + d1 + 8, 55)
        if start2 + d2 > 59:
            d2 = max(2, 59 - start2)
        windows.append({"start_min": start1, "duration_min": d1})
        windows.append({"start_min": start2, "duration_min": max(2, d2)})
    elif pattern == "triple":
        parts = [random.randint(2, 4) for _ in range(3)]
        while sum(parts) < 5:
            parts[random.randint(0, 2)] += 1
        cursor = random.randint(1, 8)
        for d in parts:
            windows.append({"start_min": cursor, "duration_min": d})
            cursor = _clamp(cursor + d + random.randint(8, 16), cursor + d + 5, 55)
            if cursor >= 56:
                break
    else:  # late_long — e.g. every ~50 min feel: long block late in hour
        duration = random.randint(7, 14)
        start_m = random.randint(40, max(41, 58 - duration))
        windows.append({"start_min": start_m, "duration_min": duration})

    # Normalize + tag
    out = []
    for i, w in enumerate(windows):
        out.append(
            {
                "id": f"h{hour:02d}_{i}",
                "hour": hour,
                "start_min": int(w["start_min"]),
                "duration_min": int(w["duration_min"]),
                "done": False,
            }
        )
    return out


ACTIVE_BROWSE_START_HOUR = 8   # 08:00 AM (সকাল ৮টা)
ACTIVE_BROWSE_END_HOUR = 24    # 12:00 AM (রাত ১২টা / midnight)


def is_active_browse_hour(hour: int) -> bool:
    """Returns True only during the allowed 08:00 AM to 12:00 AM (midnight) browsing window."""
    return ACTIVE_BROWSE_START_HOUR <= hour < ACTIVE_BROWSE_END_HOUR


def build_day_plan(day: Optional[date] = None) -> Dict[str, Any]:
    day = day or date.today()
    windows: List[Dict[str, Any]] = []

    # Active human hours: strictly between 08:00 AM and 12:00 AM midnight
    for hour in range(ACTIVE_BROWSE_START_HOUR, ACTIVE_BROWSE_END_HOUR):
        # Realistic human pauses / breaks (e.g. meal time, offline moments)
        if hour in (13, 17, 21) and random.random() < 0.25:
            continue
        windows.extend(_make_hour_windows(hour))

    # Guarantee: for every active hour that has no window, inject a minimal 5-min block
    hours_covered = {w["hour"] for w in windows}
    for hour in range(ACTIVE_BROWSE_START_HOUR, ACTIVE_BROWSE_END_HOUR):
        if hour in hours_covered:
            continue
        start_m = random.randint(5, 45)
        windows.append(
            {
                "id": f"h{hour:02d}_g",
                "hour": hour,
                "start_min": start_m,
                "duration_min": random.randint(5, 8),
                "done": False,
            }
        )

    windows.sort(key=lambda w: (w["hour"], w["start_min"]))
    plan = {
        "date": day.isoformat(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "windows": windows,
        "min_minutes_per_hour": 5,
        "active_range": "08:00-24:00",
    }
    store.set_meta(META_KEY_PREFIX + day.isoformat(), json.dumps(plan, ensure_ascii=False))
    return plan


def get_day_plan(day: Optional[date] = None) -> Dict[str, Any]:
    day = day or date.today()
    raw = store.get_meta(META_KEY_PREFIX + day.isoformat(), "")
    if raw:
        try:
            plan = json.loads(raw)
            if plan.get("date") == day.isoformat() and plan.get("windows"):
                return plan
        except Exception:
            pass
    return build_day_plan(day)


def save_day_plan(plan: Dict[str, Any]) -> None:
    day = plan.get("date") or date.today().isoformat()
    store.set_meta(META_KEY_PREFIX + day, json.dumps(plan, ensure_ascii=False))


def mark_window_done(window_id: str, *, day: Optional[date] = None) -> None:
    plan = get_day_plan(day)
    for w in plan.get("windows") or []:
        if w.get("id") == window_id:
            w["done"] = True
            w["finished_at"] = datetime.now().isoformat(timespec="seconds")
            break
    save_day_plan(plan)


def active_window_now(now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Return the first unfinished window whose time range covers `now`."""
    now = now or datetime.now()
    if not is_active_browse_hour(now.hour):
        return None
    plan = get_day_plan(now.date())
    for w in plan.get("windows") or []:
        if w.get("done"):
            continue
        start = now.replace(hour=int(w["hour"]), minute=int(w["start_min"]), second=0, microsecond=0)
        end = start + timedelta(minutes=int(w["duration_min"]))
        # Allow starting up to 90s late (scheduler jitter)
        if start - timedelta(seconds=90) <= now <= end:
            remaining = max(60, int((end - now).total_seconds()))
            out = dict(w)
            out["remaining_sec"] = remaining
            out["ends_at"] = end.isoformat(timespec="seconds")
            return out
    return None


def plan_summary(day: Optional[date] = None) -> Dict[str, Any]:
    plan = get_day_plan(day)
    wins = plan.get("windows") or []
    done = sum(1 for w in wins if w.get("done"))
    total_min = sum(int(w.get("duration_min") or 0) for w in wins)
    return {
        "date": plan.get("date"),
        "windows": len(wins),
        "done": done,
        "pending": len(wins) - done,
        "planned_minutes": total_min,
        "next": next((w for w in wins if not w.get("done")), None),
    }
