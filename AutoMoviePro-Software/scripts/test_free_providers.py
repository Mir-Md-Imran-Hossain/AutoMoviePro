"""Smoke: Groq primary + free-provider chain wiring."""
from __future__ import annotations

from pipeline.api_keys import load_api_bundle
from pipeline.llm_router import chat_text
from pipeline.provider_budget import close_circuit
from pipeline.purpose_caps import capability_summary


def test_bundle_has_new_providers():
    b = load_api_bundle()
    c = b["counts"]
    assert c["groq"] >= 1
    assert c["cerebras"] >= 1
    assert c["freetheai"] >= 1


def test_groq_script_primary():
    for p in ("groq", "cerebras", "openrouter", "huggingface", "freetheai"):
        close_circuit(p)
    hit = chat_text("Reply with exactly: OK", purpose="script", google_api_keys=[])
    assert hit["text"].strip().upper().startswith("OK") or "OK" in hit["text"].upper()
    assert hit["provider"] in (
        "groq",
        "cerebras",
        "openrouter",
        "huggingface",
        "freetheai",
        "google",
    )


def test_capability_matrix():
    caps = capability_summary()["capabilities"]
    assert caps["groq"]["text"] and not caps["groq"]["tts"]
    assert caps["edge_tts"]["tts"] and not caps["edge_tts"]["text"]
    assert caps["freetheai"]["image"]


if __name__ == "__main__":
    test_bundle_has_new_providers()
    test_capability_matrix()
    test_groq_script_primary()
    print("OK free provider wiring")
