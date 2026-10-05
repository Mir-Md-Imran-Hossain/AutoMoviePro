#!/usr/bin/env python3
"""Ensure history playbook syncs into training rules (quality-first critic policy)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.agent_playbook import (  # noqa: E402
    FAULT_CATALOG,
    HISTORY_TRAINING_RULES,
    should_skip_gemini_critic,
    sync_history_rules_to_training,
)
from pipeline.av_sync_critic import load_training_rules  # noqa: E402


def main() -> int:
    sync_history_rules_to_training()
    rules = load_training_rules()
    joined = "\n".join(rules).lower()
    assert "setpts" in joined, "missing setpts rule"
    assert "soft-accept" in joined or "429" in joined, "missing critic-outage rule"
    assert "black" in joined, "missing black-tail rule"
    assert "api budget" in joined or "max 1 agnes" in joined, "missing API budget rule"
    assert "english master" in joined or "bcp-47" in joined, "missing English-master rule"
    assert "wrong_subject" in joined or "visual ≠ audio" in joined or "visual != audio" in joined
    assert "charon" in joined, "missing Charon voice rule"
    assert "skip multimodal critic when self-repair already passed" not in joined
    # obsolete freeze-clone instruction scrubbed
    assert "tpad clone only after content" not in joined

    ids = {f["id"] for f in FAULT_CATALOG}
    for fid in (
        "english_master_drift",
        "voice_identity_drift",
        "english_burnin_on_master",
        "keyword_preflight_skip",
        "stale_resume_clip",
        "hard_trim_last_word",
        "audio_pass_skips_visual",
        "too_few_beats_for_budget",
        "missing_localize_package",
    ):
        assert fid in ids, fid

    # Quality-first: audio pass alone never skips Gemini critic
    prev = os.environ.pop("AMP_SKIP_GEMINI_CRITIC", None)
    try:
        assert not should_skip_gemini_critic({"passed": True})
        assert not should_skip_gemini_critic({"passed": True}, visual_passed=True)
        assert not should_skip_gemini_critic({"passed": False})
        os.environ["AMP_SKIP_GEMINI_CRITIC"] = "1"
        assert should_skip_gemini_critic({"passed": True}, visual_passed=True)
        assert not should_skip_gemini_critic({"passed": True}, visual_passed=False)
        assert not should_skip_gemini_critic(
            {"passed": True, "needs_visual_regen": True}, visual_passed=True
        )
    finally:
        if prev is None:
            os.environ.pop("AMP_SKIP_GEMINI_CRITIC", None)
        else:
            os.environ["AMP_SKIP_GEMINI_CRITIC"] = prev

    assert len(FAULT_CATALOG) >= 18
    assert len(HISTORY_TRAINING_RULES) >= 20
    print(f"OK playbook faults={len(FAULT_CATALOG)} rules_on_disk={len(rules)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
