"""Burn-guard: Google key spray must be impossible."""
from __future__ import annotations

from pipeline.google_api_gate import (
    HARD_MAX_KEYS,
    GoogleCircuitOpen,
    close_circuit,
    max_keys_for,
    open_circuit,
    select_keys,
    status_snapshot,
)
from pipeline.llm_router import prefer_openrouter


def test_select_keys_never_returns_full_vault():
    close_circuit()
    vault = [f"key-{i:02d}-xxxxxxxx" for i in range(18)]
    chosen = select_keys(vault, purpose="text")
    assert 1 <= len(chosen) <= HARD_MAX_KEYS
    assert len(chosen) <= max_keys_for("text")
    assert len(chosen) < len(vault)


def test_circuit_blocks_select():
    open_circuit("unit_test")
    try:
        select_keys(["k1", "k2", "k3"], purpose="text")
        raise AssertionError("expected GoogleCircuitOpen")
    except GoogleCircuitOpen:
        pass
    finally:
        # leave circuit open for production safety after this suite's OR tests;
        # reopen closed for other unit asserts then re-open burn state
        close_circuit()


def test_prefer_openrouter_default():
    assert prefer_openrouter() is True


def test_status_snapshot_shape():
    snap = status_snapshot()
    assert "circuit_open" in snap
    assert "hourly_budget" in snap
    assert snap["max_keys_text"] <= HARD_MAX_KEYS


def test_tts_allows_two_keys_cap():
    assert max_keys_for("tts") <= HARD_MAX_KEYS
    assert max_keys_for("text") == 1


if __name__ == "__main__":
    test_select_keys_never_returns_full_vault()
    test_circuit_blocks_select()
    test_prefer_openrouter_default()
    test_status_snapshot_shape()
    test_tts_allows_two_keys_cap()
    open_circuit("post_test_keep_or_mode")
    print("OK burn guard tests")
