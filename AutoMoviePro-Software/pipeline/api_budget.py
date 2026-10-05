"""Per-job API budget counters — fail-closed when exceeded."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_BUDGET = {
    "max_generation_calls": 40,
    "max_image_calls": 40,
    "max_video_calls": 24,
    "max_tts_calls": 40,
    "max_critic_calls": 40,
    "max_repairs": 20,
    "max_cost": 0.0,  # 0 = unused
    "max_runtime_sec": 7200,
}


class ApiBudget:
    def __init__(self, work_dir: Path, limits: Optional[Dict[str, Any]] = None):
        self.work = Path(work_dir)
        self.path = self.work / "API_BUDGET.json"
        self.limits = {**DEFAULT_BUDGET, **(limits or {})}
        self.used = {
            "generation_calls": 0,
            "image_calls": 0,
            "video_calls": 0,
            "tts_calls": 0,
            "critic_calls": 0,
            "repairs": 0,
            "cost": 0.0,
            "runtime_sec": 0.0,
        }
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.limits.update(data.get("limits") or {})
                self.used.update(data.get("used") or {})
            except Exception:
                pass

    def _save(self) -> None:
        self.work.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"limits": self.limits, "used": self.used}, indent=2),
            encoding="utf-8",
        )

    def remaining(self, kind: str) -> int:
        key = f"{kind}_calls" if not kind.endswith("s") and kind != "repairs" else (
            "repairs" if kind == "repairs" else f"{kind}" if kind.endswith("s") else f"{kind}_calls"
        )
        # normalize
        mapping = {
            "generation": "generation_calls",
            "image": "image_calls",
            "video": "video_calls",
            "tts": "tts_calls",
            "critic": "critic_calls",
            "repair": "repairs",
            "repairs": "repairs",
        }
        used_key = mapping.get(kind, key)
        lim_key = {
            "generation_calls": "max_generation_calls",
            "image_calls": "max_image_calls",
            "video_calls": "max_video_calls",
            "tts_calls": "max_tts_calls",
            "critic_calls": "max_critic_calls",
            "repairs": "max_repairs",
        }[used_key]
        return int(self.limits.get(lim_key) or 0) - int(self.used.get(used_key) or 0)

    def allow(self, kind: str) -> bool:
        return self.remaining(kind) > 0

    def consume(self, kind: str, n: int = 1, *, cost: float = 0.0) -> Dict[str, Any]:
        mapping = {
            "generation": "generation_calls",
            "image": "image_calls",
            "video": "video_calls",
            "tts": "tts_calls",
            "critic": "critic_calls",
            "repair": "repairs",
            "repairs": "repairs",
        }
        used_key = mapping[kind]
        if not self.allow(kind):
            return {"ok": False, "reason": f"budget_exceeded:{kind}", "used": dict(self.used)}
        self.used[used_key] = int(self.used.get(used_key) or 0) + int(n)
        self.used["cost"] = float(self.used.get("cost") or 0.0) + float(cost)
        self._save()
        return {"ok": True, "used": dict(self.used), "remaining": self.remaining(kind)}

    def snapshot(self) -> Dict[str, Any]:
        return {"limits": dict(self.limits), "used": dict(self.used)}
