"""Deterministic mix hierarchy + ducking policy (AMP-004 Phase-05).

Does not rewrite FFmpeg architecture — produces filter recipes for existing tools.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MixPolicy:
    """Canonical audio hierarchy: Dialogue > narrative SFX > ambience > music."""

    policy_id: str = "dialogue_primary_v1"
    priority: dict[str, int] = field(
        default_factory=lambda: {"dialogue": 1, "sfx": 2, "ambience": 3, "music": 4}
    )
    dialogue_target_peak: float = 0.89  # ~ -1 dBFS headroom (not broadcast LUFS claim)
    duck_music_db: float = -16.0  # -14dB to -18dB sidechain ducking under dialogue
    duck_ambience_db: float = -10.0
    duck_sfx_db: float = -3.0
    attack_ms: int = 150
    release_ms: int = 400

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "priority": dict(self.priority),
            "dialogue_target_peak": self.dialogue_target_peak,
            "duck_music_db": self.duck_music_db,
            "duck_ambience_db": self.duck_ambience_db,
            "duck_sfx_db": self.duck_sfx_db,
            "attack_ms": self.attack_ms,
            "release_ms": self.release_ms,
            "broadcast_lufs_claimed": False,
            "note": "Peak/hierarchy policy — not claiming calibrated LUFS broadcast compliance",
        }


def default_mix_policy() -> MixPolicy:
    return MixPolicy()


def ducking_gain_db(layer: str, *, dialogue_active: bool, policy: MixPolicy | None = None) -> float:
    """Deterministic supporting-layer attenuation while dialogue is active."""
    policy = policy or default_mix_policy()
    if not dialogue_active or layer == "dialogue":
        return 0.0
    if layer == "music":
        return float(policy.duck_music_db)
    if layer == "ambience":
        return float(policy.duck_ambience_db)
    if layer == "sfx":
        return float(policy.duck_sfx_db)
    return -6.0


def validate_music_vs_dialogue_priority(music: dict[str, Any] | None, mix_priority: dict[str, int]) -> list[str]:
    """Block music competing with dialogue unless explicitly intended."""
    issues: list[str] = []
    if not music:
        return issues
    mpri = int(music.get("priority") or mix_priority.get("music") or 4)
    dpri = int(mix_priority.get("dialogue") or 1)
    if mpri <= dpri and str(music.get("ducking") or "") not in ("under_dialogue", "explicit_equal_ok"):
        issues.append("music_priority_competes_with_dialogue")
    energy = float(music.get("energy") or 0)
    if energy >= 0.85 and str(music.get("ducking") or "") != "explicit_equal_ok":
        issues.append("music_energy_masks_dialogue_risk")
    return issues


def ffmpeg_duck_filter_hint(policy: MixPolicy | None = None) -> str:
    """Documentation/recipe string for existing FFmpeg sidechaincompress usage — not a rewrite."""
    policy = policy or default_mix_policy()
    return (
        f"sidechaincompress=threshold=0.02:ratio=6:attack={policy.attack_ms}:"
        f"release={policy.release_ms}:level_sc=1"
    )
