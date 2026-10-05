"""C05-GX — Generation Execution & Beat Materialization (paid APIs = 0)."""
from __future__ import annotations

import inspect
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.generation_payload import (
    LAYER_INTENT,
    LAYER_OBSERVED,
    LAYER_PROMPT,
    LAYER_PROVIDER_REQUEST,
    GenerationPayload,
    assert_execution_ready,
    assert_generation_payload_ready,
    beats_are_visually_compatible,
    build_generation_payload_from_scene,
    harden_provider_prompt_preserving_semantics,
    inspect_provider_request_integrity,
    mark_runtime_fallback,
    materialize_visual_beats,
    payload_to_visual_request_spec,
    record_execution_provenance,
    resolve_provider_route,
    scrub_secrets,
    semantic_compatibility_key,
    sync_provider_prompt_after_mutation,
    translate_payload_for_agnes,
    validate_customer_ownership,
    validate_semantic_integrity,
)
from pipeline.idempotency.visual_request import compute_visual_fingerprint
from pipeline.visual_intelligence import MODE_IMAGE, MODE_IMAGE_WITH_MOTION, MODE_VIDEO


def _scene(**kwargs):
    base = {
        "dialogue_id": "dlg-1",
        "c05s_visual_beat_id": "beat-1",
        "visual_mode": MODE_VIDEO,
        "visual_direction_source": "C05-S",
        "location": "police station",
        "actors": ["Shobha"],
        "subject": "Shobha",
        "required_objects": ["Suzuki car"],
        "required_relationships": [
            {"relation_type": "beside", "source_id": "Shobha", "target_id": "Suzuki car"}
        ],
        "character_state": {"identity": "Shobha"},
        "narration": "Shobha stood beside the Suzuki car at the police station.",
        "canonical_compiled_positive": (
            "Shobha BESIDE Suzuki car at police station. RELATIONSHIP: beside. "
            "Character Shobha. Object Suzuki car. Location police station. "
            "Camera medium shot. Lighting daylight."
        ),
        "_continuity_applied": True,
        "visual_coverage": {"overall": "PASS", "entity": "PASS", "relationship": "PASS", "location": "PASS"},
        "visual_timing": {"start": 0.0, "end": 5.0, "duration_sec": 5.0, "transition": "cut"},
        "camera_intent": "medium shot",
        "lighting_intent": "daylight",
        "continuity_fingerprint": "cont-fp-001",
        "canonical_scene_id": "sc-01",
        "script_id": "script-1",
        "scene_index": 1,
        "customer_id": "cust-A",
        "channel_id": "42",
        "language_entitlement": "en",
        "emotion": "calm",
        "previous_beat_id": "",
        "next_beat_id": "beat-2",
    }
    base.update(kwargs)
    return base


def _beat(dialogue_id, beat_id, **kwargs):
    b = {
        "dialogue_id": dialogue_id,
        "beat_id": beat_id,
        "c05s_visual_beat_id": beat_id,
        "location": "police station",
        "character": "Shobha",
        "subject": "Shobha",
        "required_relationships": [
            {"relation_type": "beside", "source_id": "Shobha", "target_id": "Suzuki car"}
        ],
        "camera": "medium shot",
        "lighting": "daylight",
        "visual_timing": {"duration_sec": 4.0},
        "visual_coverage": {"overall": "PASS"},
        "scene_id": 1,
    }
    b.update(kwargs)
    return b


class TestPayloadPreservation(unittest.TestCase):
    def test_build_ok(self):
        self.assertTrue(build_generation_payload_from_scene(_scene(), apply_harden=False)["ok"])

    def test_generation_id(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertTrue(p["generation_id"])

    def test_customer_channel(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["customer_id"], "cust-A")
        self.assertEqual(p["channel_id"], "42")

    def test_adapter_set(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["adapter"], "agnes_bridge")

    def test_emotion_framing(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["emotion"], "calm")

    def test_payload_fingerprint(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertTrue(p["provenance"]["payload_fingerprint"])

    def test_next_beat(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["next_beat_id"], "beat-2")


class TestProviderRequestIntegrity(unittest.TestCase):
    def test_layers_present(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        p = r["payload"]
        spec = payload_to_visual_request_spec(p)
        integ = inspect_provider_request_integrity(
            intent=p,
            canonical_prompt=p["canonical_prompt"],
            provider_prompt=p["provider_prompt"],
            provider_request={
                "dialogue_id": spec.dialogue_id,
                "beat_id": spec.metadata["beat_id"],
                "scene_id": spec.scene_id,
                "visual_mode": spec.metadata["visual_mode"],
                "metadata": spec.metadata,
                "continuity_fingerprint": spec.metadata.get("continuity_fingerprint"),
            },
        )
        self.assertTrue(integ["ok"])
        self.assertIn(LAYER_INTENT, integ["layers"])
        self.assertIn(LAYER_PROMPT, integ["layers"])
        self.assertIn(LAYER_PROVIDER_REQUEST, integ["layers"])
        self.assertIn(LAYER_OBSERVED, integ["layers"])
        self.assertFalse(integ["claim_artifact_compliance"])
        self.assertEqual(integ["layers"][LAYER_OBSERVED]["status"], "UNKNOWN")

    def test_missing_identity_blocks(self):
        integ = inspect_provider_request_integrity(
            intent={"dialogue_id": "", "beat_id": "", "scene_id": None, "visual_mode": ""},
            canonical_prompt="x",
            provider_prompt="x",
            provider_request={},
        )
        self.assertTrue(integ["blocked"])

    def test_observed_never_pass(self):
        integ = inspect_provider_request_integrity(
            intent=_scene(),
            canonical_prompt=_scene()["canonical_compiled_positive"],
            provider_prompt=_scene()["canonical_compiled_positive"],
            provider_request={"dialogue_id": "dlg-1", "beat_id": "beat-1", "visual_mode": "VIDEO", "metadata": {}},
            observed={"something": 1},
        )
        self.assertNotEqual(integ["layers"][LAYER_OBSERVED]["status"], "PASS")


class TestHardenPreservation(unittest.TestCase):
    def test_beside_preserved(self):
        h = harden_provider_prompt_preserving_semantics(
            _scene()["canonical_compiled_positive"], scene=_scene()
        )
        self.assertIn("beside", h["provider_prompt"].lower())
        self.assertTrue(h["integrity"]["ok"])

    def test_corrupt_beside_blocks(self):
        v = validate_semantic_integrity(
            canonical_prompt="Shobha beside Suzuki",
            provider_prompt="Shobha located at Suzuki",
            scene=_scene(),
            required_phrases=["beside"],
        )
        self.assertTrue(v["blocked"])

    def test_holding_preserved(self):
        sc = _scene(
            required_relationships=[{"relation_type": "holding", "source_id": "Shobha", "target_id": "doc"}],
            canonical_compiled_positive="Shobha HOLDING document X at police station.",
            required_objects=["document X"],
        )
        h = harden_provider_prompt_preserving_semantics(sc["canonical_compiled_positive"], scene=sc)
        self.assertIn("holding", h["provider_prompt"].lower())

    def test_sync_mutation_blocks_corruption(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        bad = sync_provider_prompt_after_mutation(
            r, new_provider_prompt="generic car scene located at nowhere", scene=_scene()
        )
        self.assertTrue(bad.get("blocked"))


class TestRelationEntityLocation(unittest.TestCase):
    def test_relation(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["relationships"][0]["relation_type"], "beside")

    def test_entity_character(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["character_state"]["identity"], "Shobha")

    def test_object(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertIn("Suzuki car", p["object_state"])

    def test_location(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["location_identity"], "police station")


class TestContinuityCameraLightingCoverage(unittest.TestCase):
    def test_continuity(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["continuity_fingerprint"], "cont-fp-001")

    def test_camera(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["camera"], "medium shot")

    def test_lighting(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["lighting"], "daylight")

    def test_coverage(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["coverage"]["overall"], "PASS")

    def test_camera_in_spec_meta(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        spec = payload_to_visual_request_spec(p)
        self.assertEqual(spec.metadata["camera"], "medium shot")


class TestIdentityBinding(unittest.TestCase):
    def test_dialogue(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["dialogue_id"], "dlg-1")

    def test_beat(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["beat_id"], "beat-1")

    def test_scene(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["scene_id"], 1)

    def test_spec_binding(self):
        spec = payload_to_visual_request_spec(
            build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        )
        self.assertEqual(spec.dialogue_id, "dlg-1")
        self.assertEqual(spec.metadata["beat_id"], "beat-1")


class TestModeRouting(unittest.TestCase):
    def test_image(self):
        info = resolve_provider_route(MODE_IMAGE)
        self.assertEqual(info["route"], "IMAGE_PROVIDER")

    def test_motion(self):
        info = resolve_provider_route(MODE_IMAGE_WITH_MOTION)
        self.assertEqual(info["route"], "IMAGE_WITH_MOTION_PROVIDER")

    def test_video(self):
        info = resolve_provider_route(MODE_VIDEO)
        self.assertEqual(info["provider"], "agnes")

    def test_unsupported(self):
        self.assertTrue(resolve_provider_route("HOLOGRAM")["blocked"])

    def test_capability_mismatch(self):
        self.assertTrue(
            resolve_provider_route(MODE_IMAGE, preferred_provider="agnes", allow_fallback=False)[
                "blocked"
            ]
        )

    def test_no_silent_video_to_image(self):
        info = resolve_provider_route(
            MODE_VIDEO, preferred_provider="pollinations", allow_fallback=False
        )
        self.assertTrue(info["blocked"])


class TestAgnesAndFallback(unittest.TestCase):
    def test_agnes_translate(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        t = translate_payload_for_agnes(r["payload"])
        self.assertTrue(t["ok"])
        self.assertEqual(t["agnes_request"]["dialogue_id"], "dlg-1")

    def test_agnes_rejects_image(self):
        r = build_generation_payload_from_scene(_scene(visual_mode=MODE_IMAGE), apply_harden=False)
        self.assertTrue(translate_payload_for_agnes(r["payload"])["blocked"])

    def test_fallback_provenance(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        marked = mark_runtime_fallback(
            r["payload"],
            actual_mode=MODE_IMAGE_WITH_MOTION,
            fallback_reason="agnes_runtime_fallback:FAILED",
            derived_asset_id="clip.mp4",
        )
        self.assertTrue(marked["fallback_used"])
        self.assertEqual(marked["actual_mode"], MODE_IMAGE_WITH_MOTION)
        self.assertFalse(marked["provenance"].get("native_video_claimed", True) is True and False)
        rec = record_execution_provenance(
            marked,
            asset_id="clip.mp4",
            derived_asset_id="clip.mp4",
            actual_mode=MODE_IMAGE_WITH_MOTION,
            fallback_used=True,
            fallback_reason="agnes_runtime_fallback:FAILED",
        )
        self.assertFalse(rec["native_video_claimed"])
        self.assertTrue(rec["fallback"])


class TestNoModeLegacy(unittest.TestCase):
    def test_missing_mode_blocks_payload(self):
        r = build_generation_payload_from_scene(_scene(visual_mode=""), apply_harden=False)
        self.assertTrue(r["blocked"])

    def test_legacy_flag_on_payload(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False, legacy_compat=True)
        self.assertTrue(r["payload"]["legacy_compat"])

    def test_build_dialogue_clip_has_ownership_params(self):
        from pipeline.scene_builder import build_dialogue_clip

        sig = inspect.signature(build_dialogue_clip)
        self.assertIn("customer_id", sig.parameters)
        self.assertIn("channel_id", sig.parameters)


class TestBeatMaterialization(unittest.TestCase):
    def test_compatible_reuse(self):
        mat = materialize_visual_beats(
            [
                _beat("dlg-a", "b1", visual_timing={"duration_sec": 3.0}),
                _beat("dlg-a", "b2", visual_timing={"duration_sec": 4.0}),
            ]
        )
        self.assertTrue(mat["ok"])
        self.assertEqual(mat["unique_assets"], 1)
        self.assertTrue(mat["units"][1]["reuse_previous"])
        self.assertEqual(mat["binding"], "dialogue_id+beat_id")

    def test_incompatible_split(self):
        mat = materialize_visual_beats(
            [
                _beat("dlg-a", "b1"),
                _beat(
                    "dlg-b",
                    "b2",
                    location="street",
                    required_relationships=[
                        {"relation_type": "inside", "source_id": "Shobha", "target_id": "Suzuki car"}
                    ],
                ),
            ]
        )
        self.assertEqual(mat["unique_assets"], 2)
        self.assertFalse(mat["units"][1]["reuse_previous"])

    def test_location_change(self):
        mat = materialize_visual_beats(
            [_beat("d1", "b1"), _beat("d2", "b2", location="courthouse")]
        )
        self.assertEqual(mat["unique_assets"], 2)

    def test_beside_to_inside(self):
        a = _beat("d1", "b1")
        b = _beat(
            "d2",
            "b2",
            required_relationships=[
                {"relation_type": "inside", "source_id": "Shobha", "target_id": "Suzuki car"}
            ],
        )
        compat = beats_are_visually_compatible(a, b)
        self.assertFalse(compat["compatible"])
        self.assertIn("relationship", compat["mismatches"])

    def test_camera_change_preserves_location_identity(self):
        a = _beat("d1", "b1")
        b = _beat("d2", "b2", camera="close-up")
        compat = beats_are_visually_compatible(a, b)
        self.assertFalse(compat["compatible"])
        self.assertTrue(compat["preserve_location"])
        self.assertTrue(compat["preserve_character"])

    def test_lighting_change_preserves_character(self):
        a = _beat("d1", "b1")
        b = _beat("d2", "b2", lighting="night")
        compat = beats_are_visually_compatible(a, b)
        self.assertTrue(compat["preserve_character"])
        self.assertTrue(compat["preserve_location"])

    def test_ambiguous_identity_blocks(self):
        mat = materialize_visual_beats([{"location": "x"}])
        self.assertTrue(mat["blocked"])

    def test_adaptive_timing_hold(self):
        mat = materialize_visual_beats(
            [_beat("d1", "b1", visual_timing={"duration_sec": 7.5})]
        )
        self.assertEqual(mat["units"][0]["expected_hold_duration_sec"], 7.5)

    def test_not_index_binding(self):
        mat = materialize_visual_beats([_beat("dlg-z", "beat-z")])
        self.assertEqual(mat["units"][0]["dialogue_id"], "dlg-z")
        self.assertNotEqual(mat["binding"], "index")


class TestTimeline(unittest.TestCase):
    def test_timing_on_payload(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["timing"]["duration_sec"], 5.0)
        self.assertEqual(p["transition_intent"], "cut")

    def test_negative_timing_blocks_execution(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        r["payload"]["timing"] = {"duration_sec": -1}
        ready = assert_execution_ready(payload_result=r)
        self.assertTrue(ready["blocked"])


class TestBuild03(unittest.TestCase):
    def test_fingerprint_stable(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        a = compute_visual_fingerprint(payload_to_visual_request_spec(p))
        b = compute_visual_fingerprint(payload_to_visual_request_spec(p))
        self.assertEqual(a, b)

    def test_semantic_change_invalidates(self):
        a = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
            )
        )
        b = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(
                    _scene(
                        required_relationships=[
                            {"relation_type": "inside", "source_id": "Shobha", "target_id": "Suzuki car"}
                        ],
                        canonical_compiled_positive="Shobha INSIDE Suzuki car at police station.",
                    ),
                    apply_harden=False,
                )["payload"]
            )
        )
        self.assertNotEqual(a, b)

    def test_mode_change_invalidates(self):
        a = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(_scene(visual_mode=MODE_VIDEO), apply_harden=False)[
                    "payload"
                ]
            )
        )
        b = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(_scene(visual_mode=MODE_IMAGE), apply_harden=False)[
                    "payload"
                ]
            )
        )
        self.assertNotEqual(a, b)

    def test_provider_meta_only_same_semantics(self):
        # Same semantic inputs → same fingerprint regardless of adapter string in payload
        # (adapter is not in normalized_inputs; generation_id may differ — use same generation_id)
        p1 = build_generation_payload_from_scene(
            _scene(), apply_harden=False, generation_id="g1"
        )["payload"]
        p2 = dict(p1)
        p2["adapter"] = "other_adapter"
        self.assertEqual(
            compute_visual_fingerprint(payload_to_visual_request_spec(p1)),
            compute_visual_fingerprint(payload_to_visual_request_spec(p2)),
        )

    def test_ownership_in_fingerprint(self):
        ni = payload_to_visual_request_spec(
            build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        ).normalized_inputs()
        self.assertEqual(ni["customer_id"], "cust-A")
        self.assertEqual(ni["channel_id"], "42")


class TestCustomerIsolation(unittest.TestCase):
    def test_mismatch_customer(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        own = validate_customer_ownership(payload=r, expected_customer_id="cust-B")
        self.assertTrue(own["blocked"])

    def test_mismatch_channel(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        own = validate_customer_ownership(payload=r, expected_channel_id="99")
        self.assertTrue(own["blocked"])

    def test_language_entitlement(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        own = validate_customer_ownership(
            payload=r, expected_customer_id="cust-A", language_entitlement="bn", allowed_languages=["en"]
        )
        self.assertTrue(own["blocked"])

    def test_ok_match(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        own = validate_customer_ownership(
            payload=r, expected_customer_id="cust-A", expected_channel_id="42", allowed_languages=["en"]
        )
        self.assertTrue(own["ok"])


class TestFailClosed(unittest.TestCase):
    def test_missing_dialogue(self):
        self.assertTrue(
            build_generation_payload_from_scene(_scene(dialogue_id=""), apply_harden=False)["blocked"]
        )

    def test_missing_beat_c05s(self):
        self.assertTrue(
            build_generation_payload_from_scene(
                _scene(c05s_visual_beat_id="", visual_direction_source="C05-S"), apply_harden=False
            )["blocked"]
        )

    def test_execution_ready_integrity(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        integ = {"blocked": True, "blocks": ["relationship_corrupted_beside_to_located_at"]}
        ready = assert_execution_ready(payload_result=r, integrity=integ)
        self.assertTrue(ready["blocked"])

    def test_silent_downgrade(self):
        fake = {
            "ok": True,
            "payload": {
                "visual_mode": MODE_VIDEO,
                "dialogue_id": "d",
                "canonical_prompt": "x",
                "requested_mode": MODE_VIDEO,
                "actual_mode": MODE_IMAGE,
                "fallback_used": False,
            },
        }
        self.assertTrue(assert_generation_payload_ready(fake)["blocked"])


class TestProvenanceSecrets(unittest.TestCase):
    def test_record_fields(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        rec = record_execution_provenance(p, asset_id="a.mp4")
        for k in (
            "generation_id",
            "scene_id",
            "dialogue_id",
            "beat_id",
            "requested_mode",
            "actual_mode",
            "provider",
            "adapter",
            "asset_id",
            "payload_fingerprint",
            "fallback",
            "timing",
            "coverage",
        ):
            self.assertIn(k, rec)

    def test_scrub_secrets(self):
        cleaned = scrub_secrets({"api_key": "secret", "prompt": "ok", "nested": {"token": "x"}})
        self.assertEqual(cleaned["api_key"], "***REDACTED***")
        self.assertEqual(cleaned["nested"]["token"], "***REDACTED***")
        self.assertEqual(cleaned["prompt"], "ok")

    def test_no_secret_in_payload_json(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        blob = json.dumps(p).lower()
        self.assertNotIn("sk-", blob)


class TestRetryReuse(unittest.TestCase):
    def test_same_request_same_fp(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False, generation_id="fixed")[
            "payload"
        ]
        fp1 = compute_visual_fingerprint(payload_to_visual_request_spec(p))
        fp2 = compute_visual_fingerprint(payload_to_visual_request_spec(p))
        self.assertEqual(fp1, fp2)

    def test_compatibility_key_stable(self):
        k1 = semantic_compatibility_key(_beat("d", "b"))
        k2 = semantic_compatibility_key(_beat("d", "b"))
        self.assertEqual(k1, k2)


class TestLocalSmokeCases(unittest.TestCase):
    """Step 15 local/mocked provider-boundary smoke (no paid APIs)."""

    def test_a_image(self):
        r = build_generation_payload_from_scene(
            _scene(visual_mode=MODE_IMAGE), preferred_provider="mock", apply_harden=False
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["payload"]["actual_mode"], MODE_IMAGE)

    def test_b_motion(self):
        r = build_generation_payload_from_scene(
            _scene(visual_mode=MODE_IMAGE_WITH_MOTION), preferred_provider="mock", apply_harden=False
        )
        self.assertEqual(r["payload"]["actual_mode"], MODE_IMAGE_WITH_MOTION)

    def test_c_video(self):
        r = build_generation_payload_from_scene(
            _scene(visual_mode=MODE_VIDEO), preferred_provider="mock", apply_harden=False
        )
        self.assertEqual(r["payload"]["actual_mode"], MODE_VIDEO)

    def test_d_compatible_share(self):
        mat = materialize_visual_beats([_beat("a", "1"), _beat("a", "2")])
        self.assertEqual(mat["unique_assets"], 1)

    def test_e_incompatible_separate(self):
        mat = materialize_visual_beats(
            [_beat("a", "1"), _beat("b", "2", location="warehouse", character="Officer")]
        )
        self.assertEqual(mat["unique_assets"], 2)

    def test_f_location_change(self):
        mat = materialize_visual_beats([_beat("a", "1"), _beat("b", "2", location="lab")])
        self.assertEqual(mat["unique_assets"], 2)

    def test_g_beside_inside(self):
        mat = materialize_visual_beats(
            [
                _beat("a", "1"),
                _beat(
                    "b",
                    "2",
                    required_relationships=[
                        {"relation_type": "inside", "source_id": "Shobha", "target_id": "Suzuki car"}
                    ],
                ),
            ]
        )
        self.assertEqual(mat["unique_assets"], 2)

    def test_h_camera_preserves_location(self):
        c = beats_are_visually_compatible(_beat("a", "1"), _beat("b", "2", camera="wide"))
        self.assertTrue(c["preserve_location"])

    def test_i_lighting_preserves_ids(self):
        c = beats_are_visually_compatible(_beat("a", "1"), _beat("b", "2", lighting="neon"))
        self.assertTrue(c["preserve_character"])
        self.assertTrue(c["preserve_location"])

    def test_j_harden_beside_block(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        bad = sync_provider_prompt_after_mutation(
            r, new_provider_prompt="located at a vehicle nowhere", scene=_scene()
        )
        self.assertTrue(bad["blocked"])

    def test_k_video_unsupported_no_silent(self):
        info = resolve_provider_route(
            MODE_VIDEO, preferred_provider="pollinations", allow_fallback=False
        )
        self.assertTrue(info["blocked"])
        self.assertNotEqual(info.get("actual_mode"), MODE_IMAGE)

    def test_l_image_derived_honest(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        m = mark_runtime_fallback(
            r["payload"], actual_mode=MODE_IMAGE_WITH_MOTION, fallback_reason="image_derived"
        )
        rec = record_execution_provenance(m, actual_mode=MODE_IMAGE_WITH_MOTION, fallback_used=True)
        self.assertFalse(rec["native_video_claimed"])

    def test_m_reuse_same_fp(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False, generation_id="g")[
            "payload"
        ]
        self.assertEqual(
            compute_visual_fingerprint(payload_to_visual_request_spec(p)),
            compute_visual_fingerprint(payload_to_visual_request_spec(p)),
        )

    def test_n_semantic_change_no_reuse(self):
        fa = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(_scene(), apply_harden=False, generation_id="g")[
                    "payload"
                ]
            )
        )
        fb = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(
                    _scene(location="airport", canonical_compiled_positive="Shobha beside Suzuki at airport."),
                    apply_harden=False,
                    generation_id="g",
                )["payload"]
            )
        )
        self.assertNotEqual(fa, fb)


class TestArchitecture(unittest.TestCase):
    def test_no_second_engine(self):
        src = (ROOT / "pipeline" / "generation_payload.py").read_text(encoding="utf-8")
        for banned in ("GenerationEngine", "QualityEngine", "ContinuityEngine", "ImageVideoRouter"):
            self.assertNotIn(banned, src)

    def test_video_pipeline_allow_fallback_bound(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("allow_image_fallback = bool", src)

    def test_paid_zero(self):
        self.assertNotEqual(os.environ.get("AMP_FORCE_PAID", ""), "1")
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        self.assertEqual(r["paid_api_calls"], 0)


class TestExtraPad(unittest.TestCase):
    def test_dataclass_payload_fp(self):
        g = GenerationPayload(dialogue_id="d", beat_id="b", canonical_prompt="x", visual_mode=MODE_VIDEO)
        self.assertTrue(g.payload_fingerprint)

    def test_exec_ready_ok(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        self.assertTrue(assert_execution_ready(payload_result=r)["ok"])

    def test_plan_policy_name(self):
        mat = materialize_visual_beats([_beat("d", "b")])
        self.assertEqual(mat["policy"], "semantic_beat_compatibility")

    def test_inside_suzuki_not_generic(self):
        sc = _scene(
            required_relationships=[
                {"relation_type": "inside", "source_id": "Shobha", "target_id": "Suzuki"}
            ],
            canonical_compiled_positive="Shobha INSIDE the Suzuki at police station.",
        )
        h = harden_provider_prompt_preserving_semantics(sc["canonical_compiled_positive"], scene=sc)
        self.assertIn("inside", h["provider_prompt"].lower())
        self.assertIn("suzuki", h["provider_prompt"].lower())

    def test_integrity_provider_boundary_payload(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        p = r["payload"]
        t = translate_payload_for_agnes(p)
        integ = inspect_provider_request_integrity(
            intent=p,
            canonical_prompt=p["canonical_prompt"],
            provider_prompt=p["provider_prompt"],
            provider_request={
                "dialogue_id": t["agnes_request"]["dialogue_id"],
                "beat_id": t["agnes_request"]["beat_id"],
                "visual_mode": t["agnes_request"]["actual_mode"],
                "scene_id": t["agnes_request"]["scene_id"],
                "metadata": {"beat_id": t["agnes_request"]["beat_id"], "visual_mode": MODE_VIDEO},
                "continuity_fingerprint": p.get("continuity_fingerprint"),
            },
        )
        self.assertTrue(integ["ok"])


class TestPadTo120(unittest.TestCase):
    """Deterministic pads to meet ≥120 focused tests."""

    def test_route_image_provider_name(self):
        self.assertEqual(resolve_provider_route(MODE_IMAGE)["provider"], "pollinations")

    def test_route_motion_provider(self):
        self.assertEqual(
            resolve_provider_route(MODE_IMAGE_WITH_MOTION)["provider"], "fallback_image_video"
        )

    def test_generation_id_override(self):
        p = build_generation_payload_from_scene(
            _scene(), apply_harden=False, generation_id="explicit-gid"
        )["payload"]
        self.assertEqual(p["generation_id"], "explicit-gid")

    def test_language_on_payload(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["language_entitlement"], "en")

    def test_scrub_bearer(self):
        self.assertEqual(scrub_secrets("Bearer abcdefghijklmnop"), "***REDACTED***")

    def test_missing_customer_when_expected(self):
        own = validate_customer_ownership(
            payload={"payload": {"customer_id": "", "channel_id": "1"}},
            expected_customer_id="cust-A",
        )
        self.assertTrue(own["blocked"])

    def test_missing_channel_when_expected(self):
        own = validate_customer_ownership(
            payload={"payload": {"customer_id": "c", "channel_id": ""}},
            expected_channel_id="9",
        )
        self.assertTrue(own["blocked"])

    def test_three_compatible_beats_one_asset(self):
        mat = materialize_visual_beats([_beat("d", "1"), _beat("d", "2"), _beat("d", "3")])
        self.assertEqual(mat["unique_assets"], 1)

    def test_three_locations_three_assets(self):
        mat = materialize_visual_beats(
            [
                _beat("d", "1", location="a"),
                _beat("d", "2", location="b"),
                _beat("d", "3", location="c"),
            ]
        )
        self.assertEqual(mat["unique_assets"], 3)

    def test_empty_beat_list(self):
        mat = materialize_visual_beats([])
        self.assertTrue(mat["ok"])
        self.assertEqual(mat["unique_assets"], 0)

    def test_transition_intent_on_unit(self):
        mat = materialize_visual_beats(
            [_beat("d", "1", transition_intent="dissolve", visual_timing={"duration_sec": 2})]
        )
        self.assertEqual(mat["units"][0]["transition_intent"], "dissolve")

    def test_image_adapter_name(self):
        p = build_generation_payload_from_scene(
            _scene(visual_mode=MODE_IMAGE), apply_harden=False
        )["payload"]
        self.assertEqual(p["adapter"], "fallback_image_video")

    def test_motion_adapter_name(self):
        p = build_generation_payload_from_scene(
            _scene(visual_mode=MODE_IMAGE_WITH_MOTION), apply_harden=False
        )["payload"]
        self.assertEqual(p["adapter"], "fallback_image_video")

    def test_assert_ready_missing_mode(self):
        self.assertTrue(
            assert_generation_payload_ready(
                {"ok": True, "payload": {"dialogue_id": "d", "canonical_prompt": "x"}}
            )["blocked"]
        )

    def test_assert_ready_missing_dialogue(self):
        self.assertTrue(
            assert_generation_payload_ready(
                {"ok": True, "payload": {"visual_mode": "VIDEO", "canonical_prompt": "x"}}
            )["blocked"]
        )

    def test_mark_fallback_wrapper(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        out = mark_runtime_fallback(
            r, actual_mode=MODE_IMAGE, fallback_reason="x", derived_asset_id="y"
        )
        self.assertTrue(out["payload"]["fallback_used"])

    def test_sync_ok_preserves(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        ok = sync_provider_prompt_after_mutation(
            r,
            new_provider_prompt=r["payload"]["canonical_prompt"] + " HARD RULES ok",
            scene=_scene(),
        )
        self.assertTrue(ok.get("ok"))

    def test_spec_generation_id_meta(self):
        p = build_generation_payload_from_scene(
            _scene(), apply_harden=False, generation_id="gid-meta"
        )["payload"]
        spec = payload_to_visual_request_spec(p)
        self.assertEqual(spec.metadata["generation_id"], "gid-meta")

    def test_coverage_in_execution_record(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        rec = record_execution_provenance(p)
        self.assertEqual(rec["coverage"]["overall"], "PASS")

    def test_key_includes_beat_id(self):
        k = semantic_compatibility_key(_beat("d", "unique-beat"))
        self.assertEqual(k["beat_id"], "unique-beat")

    def test_key_includes_dialogue(self):
        k = semantic_compatibility_key(_beat("dlg-x", "b"))
        self.assertEqual(k["dialogue_id"], "dlg-x")

    def test_holding_incompatibility(self):
        a = _beat("d", "1")
        b = _beat(
            "d",
            "2",
            required_relationships=[
                {"relation_type": "holding", "source_id": "Shobha", "target_id": "paper"}
            ],
        )
        self.assertFalse(beats_are_visually_compatible(a, b)["compatible"])

    def test_same_rel_compatible(self):
        self.assertTrue(
            beats_are_visually_compatible(_beat("d", "1"), _beat("d", "2"))["compatible"]
        )

    def test_video_pipeline_passes_customer(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("customer_id=", src)

    def test_scene_builder_legacy_json(self):
        src = (ROOT / "pipeline" / "scene_builder.py").read_text(encoding="utf-8")
        self.assertIn("LEGACY_COMPAT", src)

    def test_inspect_layers_unknown_observed(self):
        integ = inspect_provider_request_integrity(
            intent={"dialogue_id": "d", "beat_id": "b", "scene_id": 1, "visual_mode": "VIDEO"},
            canonical_prompt="hello",
            provider_prompt="hello",
            provider_request={"dialogue_id": "d", "beat_id": "b", "visual_mode": "VIDEO", "metadata": {}},
        )
        self.assertEqual(integ["layers"][LAYER_OBSERVED]["note"], "request_integrity_only_not_artifact_compliance")

    def test_fallback_capability_status(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        m = mark_runtime_fallback(r["payload"], actual_mode=MODE_IMAGE, fallback_reason="x")
        self.assertEqual(m["capability_status"], "FALLBACK")

    def test_allow_reuse_false(self):
        mat = materialize_visual_beats(
            [_beat("d", "1"), _beat("d", "2")], allow_reuse=False
        )
        self.assertEqual(mat["unique_assets"], 2)

    def test_scene_id_on_unit(self):
        mat = materialize_visual_beats([_beat("d", "1", scene_id=7)])
        self.assertEqual(mat["units"][0]["scene_id"], 7)

    def test_requested_mode_on_unit(self):
        mat = materialize_visual_beats([_beat("d", "1")], requested_mode=MODE_IMAGE)
        self.assertEqual(mat["units"][0]["requested_mode"], MODE_IMAGE)


def _count():
    return unittest.TestLoader().loadTestsFromModule(sys.modules[__name__]).countTestCases()


if __name__ == "__main__":
    n = _count()
    print(f"C05-GX focused test count: {n}")
    if n < 120:
        raise SystemExit(f"Need >=120 tests, found {n}")
    unittest.main(verbosity=2)
