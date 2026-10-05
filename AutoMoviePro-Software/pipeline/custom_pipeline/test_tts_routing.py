"""Unit tests — TTS Engine Allocation Matrix + dual-key quota failover."""

from __future__ import annotations

import os
from unittest import mock

from pipeline.custom_pipeline.tts_routing import (
    ENGINE_CF_AURA,
    ENGINE_CF_MELOTTS,
    ENGINE_EDGE,
    ENGINE_GOOGLE,
    next_google_failover_key,
    normalize_lang_code,
    resolve_dual_google_keys,
    resolve_tts_route,
    routing_config,
    select_google_key_for_lang,
)


def test_routing_config_matrix_voices():
    cfg = routing_config()["tts_routing_config"]["languages"]
    assert cfg["en"]["engine"] == ENGINE_EDGE
    assert cfg["en"]["fallback_engine"] == ENGINE_EDGE
    assert cfg["en"]["voice"] == "en-US-JennyNeural"
    assert cfg["hi"]["engine"] == ENGINE_EDGE
    assert cfg["hi"]["voice"] == "hi-IN-SwaraNeural"
    assert cfg["ur"]["engine"] == ENGINE_EDGE
    assert cfg["ur"]["voice"] == "ur-PK-UzmaNeural"
    assert cfg["bn"]["engine"] == ENGINE_GOOGLE
    assert cfg["bn"]["fallback_voice"] == "bn-BD-NabanitaNeural"
    assert cfg["ta"]["fallback_voice"] == "ta-IN-PallaviNeural"
    assert cfg["ml"]["fallback_voice"] == "ml-IN-SobhanaNeural"


def test_edge_only_langs_never_google():
    # 1. Never Google regardless of Cloudflare credentials
    for lang in ("en", "English", "hi", "Hindi", "ur", "Urdu"):
        d = resolve_tts_route(lang)
        assert d.engine in (ENGINE_EDGE, ENGINE_CF_MELOTTS, ENGINE_CF_AURA), lang
        assert d.engine != ENGINE_GOOGLE, lang
        if d.engine == ENGINE_EDGE:
            assert d.api_key == ""
        else:
            assert d.engine in (ENGINE_CF_MELOTTS, ENGINE_CF_AURA)
            assert bool(d.api_key)

    # 2. When Cloudflare credentials are not provided, English routes directly to Edge-TTS
    with mock.patch("pipeline.custom_pipeline.tts_cloudflare.list_tts_cf_credentials", return_value=[]):
        for lang in ("en", "English", "hi", "Hindi", "ur", "Urdu"):
            d = resolve_tts_route(lang)
            assert d.engine == ENGINE_EDGE, lang
            assert d.api_key == ""
            assert "Neural" in d.voice


def test_normalize_lang_aliases():
    assert normalize_lang_code("Bangla") == "bn"
    assert normalize_lang_code("bengali") == "bn"
    assert normalize_lang_code("Malayalam") == "ml"
    assert normalize_lang_code("EN") == "en"


def test_dual_keys_from_dedicated_env():
    with mock.patch(
        "pipeline.custom_pipeline.tts_routing._env_map",
        return_value={
            "GOOGLE_API_KEY_BN_PRIMARY": "bn_primary_key_AAAA",
            "GOOGLE_API_KEY_BN_SECONDARY": "bn_secondary_key_BBBB",
        },
    ):
        p, s = resolve_dual_google_keys("bn")
    assert p == "bn_primary_key_AAAA"
    assert s == "bn_secondary_key_BBBB"


def test_dual_keys_env_alias(monkeypatch):
    monkeypatch.setenv("ENV_TA_PRIMARY_KEY", "ta_prim_XXXX")
    monkeypatch.setenv("ENV_TA_SECONDARY_KEY", "ta_sec_YYYY")
    # Remove dedicated names if present from real env via patch of _env_map
    with mock.patch(
        "pipeline.custom_pipeline.tts_routing._env_map",
        return_value={
            "ENV_TA_PRIMARY_KEY": "ta_prim_XXXX",
            "ENV_TA_SECONDARY_KEY": "ta_sec_YYYY",
        },
    ):
        p, s = resolve_dual_google_keys("ta")
    assert p == "ta_prim_XXXX"
    assert s == "ta_sec_YYYY"


def test_pool_slot_fallback():
    with mock.patch(
        "pipeline.custom_pipeline.tts_routing._env_map",
        return_value={
            "TTS_GOOGLE_API_KEY_1": "k1_aaaa",
            "TTS_GOOGLE_API_KEY_2": "k2_bbbb",
            "TTS_GOOGLE_API_KEY_3": "k3_cccc",
            "TTS_GOOGLE_API_KEY_4": "k4_dddd",
            "TTS_GOOGLE_API_KEY_5": "k5_eeee",
            "TTS_GOOGLE_API_KEY_6": "k6_ffff",
        },
    ):
        bn_p, bn_s = resolve_dual_google_keys("bn")
        ta_p, ta_s = resolve_dual_google_keys("ta")
        ml_p, ml_s = resolve_dual_google_keys("ml")
    assert bn_p == "k1_aaaa" and bn_s == "k2_bbbb"
    assert ta_p == "k3_cccc" and ta_s == "k4_dddd"
    assert ml_p == "k5_eeee" and ml_s == "k6_ffff"


def test_preemptive_switch_at_90pct():
    events = []

    def _sink(evt):
        events.append(evt)

    from pipeline.custom_pipeline import tts_routing as tr

    tr.register_quota_event_sink(_sink)

    with mock.patch(
        "pipeline.custom_pipeline.tts_routing.resolve_dual_google_keys",
        return_value=("prim_key_1111", "sec_key_2222"),
    ), mock.patch(
        "pipeline.custom_pipeline.tts_routing.usage_ratios",
        side_effect=lambda provider, key: {
            "hourly_pct": 0.92 if "prim" in key else 0.10,
            "daily_pct": 0.92 if "prim" in key else 0.10,
            "hourly_used": 0,
            "daily_used": 0,
            "hourly_limit": 20,
            "daily_limit": 60,
            "exhausted": False,
        },
    ), mock.patch(
        "pipeline.custom_pipeline.tts_routing.is_key_usable",
        return_value=True,
    ), mock.patch(
        "pipeline.custom_pipeline.tts_routing.should_rotate",
        side_effect=lambda provider, key: "prim" in key,
    ):
        d = select_google_key_for_lang("bn")

    assert d.engine == ENGINE_GOOGLE
    assert d.key_slot == "secondary"
    assert d.api_key == "sec_key_2222"
    assert any(e.get("event") == "QUOTA_THRESHOLD_WARNING" for e in d.events)


def test_both_keys_exhausted_falls_to_edge():
    with mock.patch(
        "pipeline.custom_pipeline.tts_routing.resolve_dual_google_keys",
        return_value=("prim_key_1111", "sec_key_2222"),
    ), mock.patch(
        "pipeline.custom_pipeline.tts_routing.is_key_usable",
        return_value=False,
    ), mock.patch(
        "pipeline.custom_pipeline.tts_routing.should_rotate",
        return_value=True,
    ), mock.patch(
        "pipeline.custom_pipeline.tts_routing.usage_ratios",
        return_value={
            "hourly_pct": 0.96,
            "daily_pct": 0.96,
            "hourly_used": 20,
            "daily_used": 60,
            "hourly_limit": 20,
            "daily_limit": 60,
            "exhausted": True,
        },
    ):
        d = select_google_key_for_lang("ml")

    assert d.engine == ENGINE_EDGE
    assert d.voice == "ml-IN-SobhanaNeural"
    assert d.reason == "google_dual_key_exhausted"


def test_429_catch_block_secondary_then_edge():
    from pipeline.custom_pipeline.tts_routing import TtsRouteDecision

    decision = TtsRouteDecision(
        lang="bn",
        engine=ENGINE_GOOGLE,
        api_key="prim_key_1111",
        key_slot="primary",
        secondary_key="sec_key_2222",
        fallback_voice="bn-BD-NabanitaNeural",
    )
    with mock.patch(
        "pipeline.custom_pipeline.tts_routing.is_key_usable",
        return_value=True,
    ), mock.patch(
        "pipeline.custom_pipeline.tts_routing.select_google_key_for_lang",
        return_value=TtsRouteDecision(
            lang="bn",
            engine=ENGINE_GOOGLE,
            api_key="sec_key_2222",
            key_slot="secondary",
            reason="forced_secondary",
            fallback_voice="bn-BD-NabanitaNeural",
        ),
    ):
        nxt = next_google_failover_key(decision)
    assert nxt is not None
    assert nxt.key_slot == "secondary"
    assert nxt.api_key == "sec_key_2222"

    # Secondary already in use → Edge
    decision2 = TtsRouteDecision(
        lang="bn",
        engine=ENGINE_GOOGLE,
        api_key="sec_key_2222",
        key_slot="secondary",
        secondary_key="",
        fallback_voice="bn-BD-NabanitaNeural",
    )
    with mock.patch(
        "pipeline.custom_pipeline.tts_routing.is_key_usable",
        return_value=False,
    ):
        edge = next_google_failover_key(decision2)
    assert edge.engine == ENGINE_EDGE
    assert edge.voice == "bn-BD-NabanitaNeural"


def test_failover_to_pool_key_when_dual_keys_fail():
    from pipeline.custom_pipeline.tts_routing import TtsRouteDecision

    decision = TtsRouteDecision(
        lang="bn",
        engine=ENGINE_GOOGLE,
        api_key="sec_key_2222",
        key_slot="secondary",
        secondary_key="",
        fallback_voice="bn-BD-NabanitaNeural",
    )
    with mock.patch(
        "pipeline.custom_pipeline.tts_routing._collect_pool",
        return_value=["pool_key_healthy_9999"],
    ), mock.patch(
        "pipeline.custom_pipeline.tts_routing.is_key_usable",
        side_effect=lambda prov, k: k == "pool_key_healthy_9999",
    ), mock.patch(
        "pipeline.custom_pipeline.tts_routing._max_quota_pct",
        return_value=10.0,
    ):
        nxt = next_google_failover_key(decision)
    assert nxt is not None
    assert nxt.engine == ENGINE_GOOGLE
    assert nxt.key_slot == "pool"
    assert nxt.api_key == "pool_key_healthy_9999"


def test_client_routes_english_to_edge(tmp_path, monkeypatch):
    """synthesize_shot_audio for English must call Edge when CF credentials are unconfigured, never Google REST."""
    monkeypatch.setenv("AMP_TTS_CALL_GAP_SEC", "0")
    out = tmp_path / "S01_EN.m4a"
    calls = {"edge": 0, "google": 0}

    def _fake_edge(text, out_path, **kwargs):
        calls["edge"] += 1
        p = out_path.with_suffix(".m4a")
        p.write_bytes(b"x" * 500)
        return p

    def _fake_rest(*a, **k):
        calls["google"] += 1
        raise AssertionError("Google TTS must not be called for English")

    with mock.patch(
        "pipeline.custom_pipeline.tts_cloudflare.list_tts_cf_credentials",
        return_value=[],
    ), mock.patch(
        "pipeline.edge_tts_fallback.synthesize_edge_tts",
        side_effect=_fake_edge,
    ), mock.patch(
        "pipeline.custom_pipeline.tts_client._tts_via_rest",
        side_effect=_fake_rest,
    ):
        from pipeline.custom_pipeline.tts_client import synthesize_shot_audio

        result = synthesize_shot_audio(
            "Hello world from the routing test.",
            out,
            language="English",
            language_code="en",
        )
    assert calls["edge"] == 1
    assert calls["google"] == 0
    assert result.exists()


def test_client_routes_english_to_cloudflare_when_configured(tmp_path, monkeypatch):
    """synthesize_shot_audio for English routes to Cloudflare when configured."""
    monkeypatch.setenv("AMP_TTS_CALL_GAP_SEC", "0")
    out = tmp_path / "S01_EN_CF.m4a"
    calls = {"cf": 0, "google": 0}

    def _fake_cf(text, out_path, **kwargs):
        calls["cf"] += 1
        p = out_path.with_suffix(".m4a")
        p.write_bytes(b"x" * 500)
        return p

    def _fake_rest(*a, **k):
        calls["google"] += 1
        raise AssertionError("Google TTS must not be called for English")

    dummy_cf = [("tok456", "acc123", "primary")]

    with mock.patch(
        "pipeline.custom_pipeline.tts_cloudflare.list_tts_cf_credentials",
        return_value=dummy_cf,
    ), mock.patch(
        "pipeline.custom_pipeline.tts_cloudflare.synthesize_melotts",
        side_effect=_fake_cf,
    ), mock.patch(
        "pipeline.custom_pipeline.tts_client._tts_via_rest",
        side_effect=_fake_rest,
    ):
        from pipeline.custom_pipeline.tts_client import synthesize_shot_audio

        result = synthesize_shot_audio(
            "Hello world Cloudflare MeloTTS test.",
            out,
            language="English",
            language_code="en",
        )
    assert calls["cf"] == 1
    assert calls["google"] == 0
    assert result.exists()


def test_client_routes_english_cloudflare_failure_falls_back_to_edge(tmp_path, monkeypatch):
    """When Cloudflare synthesis fails, fallback to Edge-TTS is triggered without calling Google."""
    monkeypatch.setenv("AMP_TTS_CALL_GAP_SEC", "0")
    out = tmp_path / "S01_EN_FAIL.m4a"
    calls = {"cf": 0, "edge": 0, "google": 0}

    def _fake_cf(text, out_path, **kwargs):
        calls["cf"] += 1
        raise RuntimeError("Cloudflare 500 internal error")

    def _fake_edge(text, out_path, **kwargs):
        calls["edge"] += 1
        p = out_path.with_suffix(".m4a")
        p.write_bytes(b"x" * 500)
        return p

    def _fake_rest(*a, **k):
        calls["google"] += 1
        raise AssertionError("Google TTS must not be called for English")

    dummy_cf = [("tok456", "acc123", "primary")]

    with mock.patch(
        "pipeline.custom_pipeline.tts_cloudflare.list_tts_cf_credentials",
        return_value=dummy_cf,
    ), mock.patch(
        "pipeline.custom_pipeline.tts_cloudflare.synthesize_melotts",
        side_effect=_fake_cf,
    ), mock.patch(
        "pipeline.edge_tts_fallback.synthesize_edge_tts",
        side_effect=_fake_edge,
    ), mock.patch(
        "pipeline.custom_pipeline.tts_client._tts_via_rest",
        side_effect=_fake_rest,
    ):
        from pipeline.custom_pipeline.tts_client import synthesize_shot_audio

        result = synthesize_shot_audio(
            "Hello world Cloudflare fallback test.",
            out,
            language="English",
            language_code="en",
        )
    assert calls["cf"] == 1
    assert calls["edge"] == 1
    assert calls["google"] == 0
    assert result.exists()


def test_audio_localization_engine_english_never_calls_google(tmp_path):
    """AudioLocalizationEngine in 'auto' mode must route en/hi/ur to Edge-TTS, never Google."""
    from pipeline.audio_localization_engine import AudioLocalizationEngine

    engine = AudioLocalizationEngine(audio_dir=tmp_path)
    calls = {"google": 0, "edge": 0}

    def _fake_google(*args, **kwargs):
        calls["google"] += 1
        raise AssertionError("Google TTS must NEVER be called for Edge-only languages in auto mode!")

    def _fake_edge(*args, **kwargs):
        calls["edge"] += 1
        out = kwargs.get("out_path")
        out.write_bytes(b"\xff\xfb\x90\x44" + b"\x00" * 2000)
        return out

    with mock.patch("pipeline.tts_google.synthesize_narration", side_effect=_fake_google), \
         mock.patch("pipeline.edge_tts_fallback.synthesize_edge_tts", side_effect=_fake_edge):
        for lang in ("en", "hi", "ur"):
            res = engine.synthesize_speech(
                scene_index=1,
                text="Never call Google TTS for Edge-only languages.",
                target_lang=lang,
                provider="auto",
            )
            assert res.passed_qa

    assert calls["google"] == 0
    assert calls["edge"] == 3



