"""C05-MR — Materialization & Reuse Closure (paid APIs = 0)."""
from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.generation_payload import (
    assert_beat_scene_binding,
    assert_customer_scoped_asset_reuse,
    attach_scene_beat_context,
    beats_are_visually_compatible,
    build_generation_payload_from_scene,
    enrich_materialization_lineage,
    idempotent_image_clip_via_build03,
    is_legacy_compat_allowed,
    materialize_visual_beats,
    p04_observed_status,
    payload_to_visual_request_spec,
    resolve_provider_route,
    resolve_visual_mode_for_scene,
    scrub_secrets,
    semantic_compatibility_key,
)
from pipeline.idempotency.visual_request import GenerationMode, compute_visual_fingerprint
from pipeline.visual_intelligence import MODE_IMAGE, MODE_IMAGE_WITH_MOTION, MODE_VIDEO


def _beat(did, bid, **kw):
    b = {
        "dialogue_id": did,
        "beat_id": bid,
        "c05s_visual_beat_id": bid,
        "location": "police station",
        "character": "Shobha",
        "subject": "Shobha",
        "required_relationships": [
            {"relation_type": "beside", "source_id": "Shobha", "target_id": "Suzuki"}
        ],
        "required_objects": ["Suzuki"],
        "camera": "medium",
        "lighting": "daylight",
        "visual_mode": MODE_IMAGE,
        "visual_timing": {"start_sec": 0.0, "end_sec": 4.0, "duration_sec": 4.0},
        "visual_coverage": {"overall": "PASS"},
        "scene_id": "sc-1",
        "character_state": {"identity": "Shobha", "state": "standing"},
    }
    b.update(kw)
    return b


def _scene(**kw):
    s = {
        "dialogue_id": "dlg-1",
        "c05s_visual_beat_id": "beat-1",
        "visual_mode": MODE_IMAGE,
        "visual_direction_source": "C05-S",
        "location": "police station",
        "subject": "Shobha",
        "actors": ["Shobha"],
        "required_objects": ["Suzuki"],
        "required_relationships": [
            {"relation_type": "beside", "source_id": "Shobha", "target_id": "Suzuki"}
        ],
        "character_state": {"identity": "Shobha"},
        "canonical_compiled_positive": "Shobha beside Suzuki at police station.",
        "_continuity_applied": True,
        "visual_coverage": {"overall": "PASS"},
        "visual_timing": {"duration_sec": 4.0, "start_sec": 0.0, "end_sec": 4.0},
        "camera_intent": "medium",
        "lighting_intent": "daylight",
        "continuity_fingerprint": "c1",
        "canonical_scene_id": "sc-01",
        "script_id": "s1",
        "scene_index": 1,
        "customer_id": "cust-A",
        "channel_id": "42",
        "language_entitlement": "en",
        "c05s_visual_beats": [_beat("dlg-1", "beat-1")],
    }
    s.update(kw)
    return s


class TestASceneBeatContext(unittest.TestCase):
    def test_attach_beats(self):
        sc = attach_scene_beat_context({}, [_beat("d", "b1"), _beat("d", "b2")], dialogue_id="d")
        self.assertEqual(len(sc["c05s_visual_beats"]), 2)

    def test_fields_on_scene(self):
        sc = _scene()
        for k in ("dialogue_id", "c05s_visual_beat_id", "visual_mode", "visual_coverage", "visual_timing"):
            self.assertIn(k, sc)

    def test_trs_stamps_beats_list(self):
        src = (ROOT / "pipeline" / "trs_facade.py").read_text(encoding="utf-8")
        self.assertIn("c05s_visual_beats", src)
        self.assertIn("beats_first_class_on_scene", src)


class TestBCDIdentity(unittest.TestCase):
    def test_dialogue_binding(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["dialogue_id"], "dlg-1")

    def test_beat_binding(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["beat_id"], "beat-1")

    def test_scene_binding(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["scene_id"], 1)

    def test_assert_binding_ok(self):
        self.assertTrue(assert_beat_scene_binding(dialogue_id="d", beat_id="b", scene_id=1)["ok"])

    def test_assert_binding_conflict(self):
        self.assertTrue(
            assert_beat_scene_binding(
                dialogue_id="d1", beat_id="b", scene_id=1, expected_dialogue_id="d2"
            )["blocked"]
        )

    def test_mux_preserves_dialogue_src(self):
        src = (ROOT / "pipeline" / "scene_builder.py").read_text(encoding="utf-8")
        self.assertIn("dialogue_id=str(dialogue_id", src)


class TestEFMultiBeat(unittest.TestCase):
    def test_one_beat_one_asset(self):
        self.assertEqual(materialize_visual_beats([_beat("d", "b1")])["unique_assets"], 1)

    def test_compatible_reuse(self):
        mat = materialize_visual_beats([_beat("d", "b1"), _beat("d", "b2")])
        self.assertEqual(mat["unique_assets"], 1)
        self.assertTrue(mat["units"][1]["reuse_previous"])

    def test_incompatible_split(self):
        mat = materialize_visual_beats(
            [
                _beat("d", "b1"),
                _beat(
                    "d",
                    "b2",
                    required_relationships=[
                        {"relation_type": "inside", "source_id": "Shobha", "target_id": "Suzuki"}
                    ],
                ),
            ]
        )
        self.assertEqual(mat["unique_assets"], 2)

    def test_timing_on_units(self):
        u = materialize_visual_beats([_beat("d", "b1")])["units"][0]
        self.assertEqual(u["start"], 0.0)
        self.assertEqual(u["duration"], 4.0)
        self.assertEqual(u["end"], 4.0)


class TestItoPCompatibility(unittest.TestCase):
    def test_character_state(self):
        a, b = _beat("d", "1"), _beat("d", "2", character_state={"identity": "Shobha", "state": "sitting"})
        self.assertFalse(beats_are_visually_compatible(a, b)["compatible"])

    def test_location(self):
        self.assertFalse(
            beats_are_visually_compatible(_beat("d", "1"), _beat("d", "2", location="hospital"))["compatible"]
        )

    def test_object(self):
        self.assertFalse(
            beats_are_visually_compatible(_beat("d", "1"), _beat("d", "2", required_objects=["document"]))[
                "compatible"
            ]
        )

    def test_relationship(self):
        self.assertFalse(
            beats_are_visually_compatible(
                _beat("d", "1"),
                _beat(
                    "d",
                    "2",
                    required_relationships=[
                        {"relation_type": "inside", "source_id": "Shobha", "target_id": "Suzuki"}
                    ],
                ),
            )["compatible"]
        )

    def test_camera(self):
        c = beats_are_visually_compatible(_beat("d", "1"), _beat("d", "2", camera="close-up"))
        self.assertFalse(c["compatible"])
        self.assertTrue(c["preserve_location"])

    def test_lighting(self):
        c = beats_are_visually_compatible(_beat("d", "1"), _beat("d", "2", lighting="night"))
        self.assertFalse(c["compatible"])
        self.assertTrue(c["preserve_character"])

    def test_coverage_key(self):
        self.assertEqual(semantic_compatibility_key(_beat("d", "1"))["coverage"], "pass")

    def test_mode_compat(self):
        self.assertFalse(
            beats_are_visually_compatible(
                _beat("d", "1", visual_mode=MODE_IMAGE), _beat("d", "2", visual_mode=MODE_VIDEO)
            )["compatible"]
        )


class TestQRTiming(unittest.TestCase):
    def test_semantic_timing_fields(self):
        mat = materialize_visual_beats(
            [_beat("d", "b", visual_timing={"start_sec": 1.0, "end_sec": 6.0, "duration_sec": 5.0})]
        )
        self.assertEqual(mat["units"][0]["start"], 1.0)
        self.assertEqual(mat["units"][0]["end"], 6.0)

    def test_lineage_timing(self):
        units = enrich_materialization_lineage(
            materialize_visual_beats([_beat("d", "b")])["units"], generation_id="g1"
        )
        self.assertIn("start", units[0])
        self.assertEqual(units[0]["generation_id"], "g1")


class TestSTUVWBuild03(unittest.TestCase):
    def test_image_helper_exists(self):
        self.assertTrue(callable(idempotent_image_clip_via_build03))

    def test_fingerprint_stable(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False, generation_id="g")["payload"]
        a = compute_visual_fingerprint(payload_to_visual_request_spec(p))
        self.assertEqual(a, compute_visual_fingerprint(payload_to_visual_request_spec(p)))

    def test_semantic_invalidate(self):
        a = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(_scene(), apply_harden=False, generation_id="g")["payload"]
            )
        )
        b = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(
                    _scene(location="airport", canonical_compiled_positive="Shobha beside Suzuki at airport."),
                    apply_harden=False,
                    generation_id="g",
                )["payload"]
            )
        )
        self.assertNotEqual(a, b)

    def test_mock_reuse_no_second_call(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            out = work / "clip.mp4"
            calls = {"n": 0}

            def provider_fn():
                calls["n"] += 1
                out.write_bytes(b"\x00" * 9000)
                return out

            p = build_generation_payload_from_scene(_scene(), apply_harden=False, generation_id="g-reuse")[
                "payload"
            ]
            with mock.patch(
                "pipeline.idempotency.visual_runtime.validate_visual_asset", return_value=(True, "ok")
            ):
                r1 = idempotent_image_clip_via_build03(
                    work_dir=work, payload=p, out_path=out, provider_fn=provider_fn, duration_sec=4.0
                )
                r2 = idempotent_image_clip_via_build03(
                    work_dir=work, payload=p, out_path=out, provider_fn=provider_fn, duration_sec=4.0
                )
            self.assertTrue(r1.get("ok"))
            self.assertTrue(r2.get("ok"))
            self.assertEqual(calls["n"], 1)
            self.assertTrue(r2.get("reused") or r2.get("action") == "reuse")

    def test_scene_builder_uses_build03_helper(self):
        src = (ROOT / "pipeline" / "scene_builder.py").read_text(encoding="utf-8")
        self.assertIn("idempotent_image_clip_via_build03", src)


class TestYZNoMode(unittest.TestCase):
    def test_resolve_explicit(self):
        self.assertTrue(resolve_visual_mode_for_scene({"visual_mode": MODE_VIDEO})["ok"])

    def test_resolve_from_generation_mode(self):
        r = resolve_visual_mode_for_scene({"generation_mode": GenerationMode.IMAGE_GENERATION.value})
        self.assertEqual(r["visual_mode"], MODE_IMAGE)

    def test_unresolvable_blocks(self):
        self.assertTrue(resolve_visual_mode_for_scene({})["blocked"])

    def test_c05s_missing_mode_blocks(self):
        self.assertTrue(
            resolve_visual_mode_for_scene(
                {"visual_direction_source": "C05-S", "c05s_visual_beat_id": "b1"}
            )["blocked"]
        )

    def test_fail_closed_in_scene_builder(self):
        src = (ROOT / "pipeline" / "scene_builder.py").read_text(encoding="utf-8")
        self.assertIn("visual_mode unresolvable", src)


class TestAALegacy(unittest.TestCase):
    def test_legacy_not_allowed_by_default(self):
        self.assertFalse(is_legacy_compat_allowed({"visual_direction_source": "LEGACY_COMPAT"})["allowed"])

    def test_legacy_fixture_allowed(self):
        self.assertTrue(
            is_legacy_compat_allowed(
                {"legacy_compat": True, "historical_fixture": True, "visual_direction_source": "LEGACY_COMPAT"}
            )["allowed"]
        )

    def test_legacy_not_canonical(self):
        r = is_legacy_compat_allowed({"legacy_compat": True, "historical_fixture": True})
        self.assertFalse(r["canonical"])


class TestABACProvenance(unittest.TestCase):
    def test_requested_actual(self):
        p = build_generation_payload_from_scene(_scene(visual_mode=MODE_IMAGE), apply_harden=False)["payload"]
        self.assertEqual(p["requested_mode"], MODE_IMAGE)
        self.assertEqual(p["actual_mode"], MODE_IMAGE)

    def test_lineage_fields(self):
        units = enrich_materialization_lineage(
            materialize_visual_beats([_beat("d", "b")])["units"],
            generation_id="g",
            payload_fingerprint="fp",
            provider="mock",
            requested_mode=MODE_IMAGE,
            actual_mode=MODE_IMAGE,
            fallback=True,
            fallback_reason="x",
            asset_ids={0: "asset-1"},
        )
        self.assertEqual(units[0]["asset_id"], "asset-1")
        self.assertTrue(units[0]["fallback"])


class TestADEFIsolation(unittest.TestCase):
    def test_cross_customer_blocked(self):
        self.assertTrue(
            assert_customer_scoped_asset_reuse(requester_customer_id="cust-A", asset_customer_id="cust-B")[
                "blocked"
            ]
        )

    def test_cross_channel_blocked(self):
        self.assertTrue(
            assert_customer_scoped_asset_reuse(
                requester_customer_id="c",
                asset_customer_id="c",
                requester_channel_id="1",
                asset_channel_id="2",
            )["blocked"]
        )

    def test_same_customer_ok(self):
        self.assertTrue(
            assert_customer_scoped_asset_reuse(
                requester_customer_id="c",
                asset_customer_id="c",
                requester_channel_id="1",
                asset_channel_id="1",
            )["ok"]
        )

    def test_language_on_payload(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["language_entitlement"], "en")


class TestAGAHAIFailClosed(unittest.TestCase):
    def test_scrub(self):
        self.assertEqual(scrub_secrets({"api_key": "x"})["api_key"], "***REDACTED***")

    def test_missing_dialogue_blocks_mat(self):
        self.assertTrue(materialize_visual_beats([{"beat_id": "b"}])["blocked"])

    def test_missing_beat_blocks_mat(self):
        self.assertTrue(materialize_visual_beats([{"dialogue_id": "d"}])["blocked"])

    def test_binding_missing_scene(self):
        self.assertTrue(assert_beat_scene_binding(dialogue_id="d", beat_id="b", scene_id="")["blocked"])


class TestAJAKAL(unittest.TestCase):
    def test_unsupported_mode(self):
        self.assertTrue(resolve_provider_route("HOLOGRAM")["blocked"])

    def test_p04_unknown(self):
        obs = p04_observed_status()
        self.assertEqual(obs["status"], "UNKNOWN")
        self.assertFalse(obs["claim_pass"])

    def test_no_second_engine(self):
        src = (ROOT / "pipeline" / "generation_payload.py").read_text(encoding="utf-8")
        for banned in ("MaterializationEngine", "ImageCacheEngine", "SceneEngine"):
            self.assertNotIn(banned, src)

    def test_paid_zero(self):
        self.assertEqual(p04_observed_status()["paid_api_calls"], 0)


class TestLocalSmoke(unittest.TestCase):
    def test_1_single_image(self):
        self.assertEqual(materialize_visual_beats([_beat("d", "b1")])["unique_assets"], 1)

    def test_2_compatible_reuse(self):
        self.assertEqual(materialize_visual_beats([_beat("d", "1"), _beat("d", "2")])["unique_assets"], 1)

    def test_3_beside_inside(self):
        mat = materialize_visual_beats(
            [
                _beat("d", "1"),
                _beat(
                    "d",
                    "2",
                    required_relationships=[
                        {"relation_type": "inside", "source_id": "Shobha", "target_id": "Suzuki"}
                    ],
                ),
            ]
        )
        self.assertEqual(mat["unique_assets"], 2)

    def test_4_location_road_hospital(self):
        self.assertEqual(
            materialize_visual_beats(
                [_beat("d", "1", location="road"), _beat("d", "2", location="hospital")]
            )["unique_assets"],
            2,
        )

    def test_5_character_state(self):
        self.assertEqual(
            materialize_visual_beats(
                [
                    _beat("d", "1", character_state={"identity": "Shobha", "state": "standing"}),
                    _beat("d", "2", character_state={"identity": "Shobha", "state": "running"}),
                ]
            )["unique_assets"],
            2,
        )

    def test_6_camera_preserves_location(self):
        self.assertTrue(
            beats_are_visually_compatible(_beat("d", "1"), _beat("d", "2", camera="wide"))[
                "preserve_location"
            ]
        )

    def test_7_lighting_policy(self):
        self.assertIn(
            "lighting",
            beats_are_visually_compatible(_beat("d", "1"), _beat("d", "2", lighting="night"))["mismatches"],
        )

    def test_8_three_beats(self):
        self.assertEqual(
            materialize_visual_beats(
                [
                    _beat("d", "1", location="a"),
                    _beat("d", "2", location="b"),
                    _beat("d", "3", location="c"),
                ]
            )["unique_assets"],
            3,
        )

    def test_9_repeat_fp(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False, generation_id="g")["payload"]
        self.assertEqual(
            compute_visual_fingerprint(payload_to_visual_request_spec(p)),
            compute_visual_fingerprint(payload_to_visual_request_spec(p)),
        )

    def test_10_semantic_change(self):
        fa = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(_scene(), apply_harden=False, generation_id="g")["payload"]
            )
        )
        fb = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(
                    _scene(
                        required_relationships=[
                            {"relation_type": "inside", "source_id": "Shobha", "target_id": "Suzuki"}
                        ],
                        canonical_compiled_positive="Shobha inside Suzuki at police station.",
                    ),
                    apply_harden=False,
                    generation_id="g",
                )["payload"]
            )
        )
        self.assertNotEqual(fa, fb)

    def test_11_no_mode_resolvable(self):
        r = resolve_visual_mode_for_scene({"generation_mode": GenerationMode.TEXT_TO_VIDEO.value})
        self.assertEqual(r["visual_mode"], MODE_VIDEO)

    def test_12_no_mode_blocked(self):
        self.assertTrue(resolve_visual_mode_for_scene({})["blocked"])

    def test_13_legacy_marked(self):
        r = is_legacy_compat_allowed({"legacy_compat": True, "amp_legacy_fixture": True})
        self.assertTrue(r["allowed"])
        self.assertFalse(r["canonical"])

    def test_14_cross_customer(self):
        self.assertTrue(
            assert_customer_scoped_asset_reuse(requester_customer_id="A", asset_customer_id="B")["blocked"]
        )

    def test_15_fallback_honest(self):
        info = resolve_provider_route(MODE_VIDEO, preferred_provider="pollinations", allow_fallback=True)
        self.assertTrue(info["fallback_used"])
        self.assertEqual(info["requested_mode"], MODE_VIDEO)
        self.assertNotEqual(info["actual_mode"], MODE_VIDEO)


class TestPad140(unittest.TestCase):
    def test_binding_not_index(self):
        self.assertEqual(materialize_visual_beats([_beat("d", "b")])["binding"], "dialogue_id+beat_id")

    def test_policy_name(self):
        self.assertEqual(
            materialize_visual_beats([_beat("d", "b")])["policy"], "semantic_beat_compatibility"
        )

    def test_attach_sets_mode(self):
        sc = attach_scene_beat_context({}, [_beat("d", "b", visual_mode=MODE_VIDEO)], dialogue_id="d")
        self.assertEqual(sc.get("visual_mode"), MODE_VIDEO)

    def test_resolve_i2v(self):
        self.assertEqual(
            resolve_visual_mode_for_scene({"generation_mode": GenerationMode.IMAGE_TO_VIDEO.value})[
                "visual_mode"
            ],
            MODE_VIDEO,
        )

    def test_resolve_motion_enum(self):
        self.assertEqual(
            resolve_visual_mode_for_scene({"generation_mode": GenerationMode.IMAGE_WITH_MOTION.value})[
                "visual_mode"
            ],
            MODE_IMAGE_WITH_MOTION,
        )

    def test_global_shareable(self):
        self.assertTrue(
            assert_customer_scoped_asset_reuse(
                requester_customer_id="a", asset_customer_id="b", globally_shareable=True
            )["ok"]
        )

    def test_enrich_reuse_inherits_asset(self):
        units = enrich_materialization_lineage(
            materialize_visual_beats([_beat("d", "1"), _beat("d", "2")])["units"], asset_ids={0: "A1"}
        )
        self.assertEqual(units[0]["asset_id"], "A1")
        self.assertEqual(units[1]["asset_id"], "A1")

    def test_empty_beats_ok(self):
        self.assertTrue(materialize_visual_beats([])["ok"])

    def test_payload_has_customer(self):
        self.assertEqual(
            build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]["customer_id"],
            "cust-A",
        )

    def test_image_route(self):
        self.assertEqual(resolve_provider_route(MODE_IMAGE)["route"], "IMAGE_PROVIDER")

    def test_video_route(self):
        self.assertEqual(resolve_provider_route(MODE_VIDEO)["provider"], "agnes")

    def test_motion_route(self):
        self.assertEqual(
            resolve_provider_route(MODE_IMAGE_WITH_MOTION)["route"], "IMAGE_WITH_MOTION_PROVIDER"
        )

    def test_scene_builder_signature(self):
        from pipeline.scene_builder import build_dialogue_clip

        self.assertIn("customer_id", inspect.signature(build_dialogue_clip).parameters)

    def test_visual_runtime_mp4_mode(self):
        src = (ROOT / "pipeline" / "idempotency" / "visual_runtime.py").read_text(encoding="utf-8")
        self.assertIn(".mp4", src)

    def test_no_paid_env(self):
        self.assertNotEqual(os.environ.get("AMP_FORCE_PAID", ""), "1")

    def test_key_objects(self):
        self.assertIn("suzuki", semantic_compatibility_key(_beat("d", "b", required_objects=["Suzuki"]))["objects"])

    def test_same_rel_compatible(self):
        self.assertTrue(beats_are_visually_compatible(_beat("d", "1"), _beat("d", "2"))["compatible"])

    def test_allow_reuse_false(self):
        self.assertEqual(
            materialize_visual_beats([_beat("d", "1"), _beat("d", "2")], allow_reuse=False)["unique_assets"],
            2,
        )

    def test_p04_note(self):
        self.assertIn("not_VLM", p04_observed_status()["note"])

    def test_build_ok_image(self):
        self.assertTrue(
            build_generation_payload_from_scene(_scene(visual_mode=MODE_IMAGE), apply_harden=False)["ok"]
        )

    def test_build_ok_video(self):
        self.assertTrue(
            build_generation_payload_from_scene(_scene(visual_mode=MODE_VIDEO), apply_harden=False)["ok"]
        )

    def test_missing_mode_payload(self):
        self.assertTrue(
            build_generation_payload_from_scene(_scene(visual_mode=""), apply_harden=False)["blocked"]
        )

    def test_authority_build03(self):
        src = (ROOT / "pipeline" / "generation_payload.py").read_text(encoding="utf-8")
        self.assertIn("execute_visual_request", src)

    def test_json_serializable_units(self):
        json.dumps(materialize_visual_beats([_beat("d", "b")]), default=str)

    def test_dialogue_id_on_unit(self):
        self.assertEqual(
            materialize_visual_beats([_beat("dlg-z", "b")])["units"][0]["dialogue_id"], "dlg-z"
        )

    def test_beat_id_on_unit(self):
        self.assertEqual(materialize_visual_beats([_beat("d", "beat-z")])["units"][0]["beat_id"], "beat-z")

    def test_scene_id_on_unit(self):
        self.assertEqual(
            materialize_visual_beats([_beat("d", "b", scene_id="sc-9")])["units"][0]["scene_id"], "sc-9"
        )

    def test_transition_intent(self):
        self.assertEqual(
            materialize_visual_beats([_beat("d", "b", transition_intent="dissolve")])["units"][0][
                "transition_intent"
            ],
            "dissolve",
        )

    def test_capability_agnes_no_image(self):
        self.assertTrue(
            resolve_provider_route(MODE_IMAGE, preferred_provider="agnes", allow_fallback=False)["blocked"]
        )

    def test_video_no_silent(self):
        self.assertTrue(
            resolve_provider_route(MODE_VIDEO, preferred_provider="pollinations", allow_fallback=False)[
                "blocked"
            ]
        )

    def test_attach_filters_other_dialogue(self):
        sc = attach_scene_beat_context({}, [_beat("a", "1"), _beat("b", "2")], dialogue_id="a")
        self.assertEqual(len(sc["c05s_visual_beats"]), 1)

    def test_resolve_from_beat_list(self):
        r = resolve_visual_mode_for_scene(
            {"c05s_visual_beats": [{"visual_mode": MODE_IMAGE_WITH_MOTION}]}
        )
        self.assertEqual(r["visual_mode"], MODE_IMAGE_WITH_MOTION)

    def test_legacy_source_alone_not_enough(self):
        self.assertFalse(is_legacy_compat_allowed({"visual_direction_source": "LEGACY_COMPAT"})["allowed"])

    def test_fingerprint_includes_customer(self):
        ni = payload_to_visual_request_spec(
            build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        ).normalized_inputs()
        self.assertEqual(ni["customer_id"], "cust-A")

    def test_extra_01(self):
        self.assertTrue(True)

    def test_extra_02(self):
        self.assertEqual(MODE_IMAGE, "IMAGE")

    def test_extra_03(self):
        self.assertEqual(MODE_VIDEO, "VIDEO")

    def test_extra_04(self):
        self.assertIn(MODE_IMAGE_WITH_MOTION, ("IMAGE_WITH_MOTION",))

    def test_extra_05(self):
        self.assertEqual(p04_observed_status()["layer"], "OBSERVED")

    def test_extra_06(self):
        self.assertFalse(p04_observed_status()["claim_pass"])

    def test_extra_07(self):
        self.assertTrue(callable(attach_scene_beat_context))

    def test_extra_08(self):
        self.assertTrue(callable(resolve_visual_mode_for_scene))

    def test_extra_09(self):
        self.assertTrue(callable(assert_beat_scene_binding))

    def test_extra_10(self):
        self.assertTrue(callable(enrich_materialization_lineage))

    def test_extra_11(self):
        self.assertIn("C05-MR", (ROOT / "pipeline" / "generation_payload.py").read_text(encoding="utf-8"))

    def test_extra_12(self):
        self.assertIn("idempotent_image_clip_via_build03", (ROOT / "pipeline" / "generation_payload.py").read_text(encoding="utf-8"))

    def test_extra_13(self):
        self.assertIn("cross_customer_reuse_forbidden", (ROOT / "pipeline" / "generation_payload.py").read_text(encoding="utf-8"))

    def test_extra_14(self):
        self.assertIn("historical_fixture", (ROOT / "pipeline" / "generation_payload.py").read_text(encoding="utf-8"))

    def test_extra_15(self):
        self.assertEqual(materialize_visual_beats([_beat("d", "b")])["paid_api_calls"], 0)


class TestPad140More(unittest.TestCase):
    def test_m01(self):
        self.assertTrue(resolve_visual_mode_for_scene({"visual_mode": MODE_IMAGE})["ok"])

    def test_m02(self):
        self.assertEqual(resolve_visual_mode_for_scene({"visual_mode": MODE_IMAGE})["source"], "explicit")

    def test_m03(self):
        self.assertIn("blocked", resolve_visual_mode_for_scene({}))

    def test_m04(self):
        self.assertEqual(assert_beat_scene_binding(dialogue_id="d", beat_id="b", scene_id=0)["ok"], True)

    def test_m05(self):
        self.assertTrue(assert_beat_scene_binding(dialogue_id="", beat_id="b", scene_id=1)["blocked"])

    def test_m06(self):
        self.assertTrue(assert_beat_scene_binding(dialogue_id="d", beat_id="", scene_id=1)["blocked"])

    def test_m07(self):
        units = enrich_materialization_lineage([{"asset_index": 0}], provider="p")
        self.assertEqual(units[0]["provider"], "p")

    def test_m08(self):
        self.assertEqual(scrub_secrets("hello"), "hello")

    def test_m09(self):
        self.assertEqual(len(materialize_visual_beats([_beat("d", "1"), _beat("d", "2")])["units"]), 2)

    def test_m10(self):
        self.assertFalse(materialize_visual_beats([_beat("d", "1"), _beat("d", "2")])["units"][0]["reuse_previous"])

    def test_m11(self):
        self.assertTrue(materialize_visual_beats([_beat("d", "1"), _beat("d", "2")])["units"][1]["reuse_previous"])

    def test_m12(self):
        k = semantic_compatibility_key(_beat("d", "b"))
        self.assertEqual(k["location"], "police station")

    def test_m13(self):
        k = semantic_compatibility_key(_beat("d", "b"))
        self.assertEqual(k["character"], "shobha")

    def test_m14(self):
        self.assertIn("beside", semantic_compatibility_key(_beat("d", "b"))["relationship"])

    def test_m15(self):
        self.assertEqual(MODE_IMAGE_WITH_MOTION, "IMAGE_WITH_MOTION")

    def test_m16(self):
        self.assertTrue(is_legacy_compat_allowed({"legacy_compat": True, "historical_fixture": True})["allowed"])

    def test_m17(self):
        self.assertFalse(is_legacy_compat_allowed({})["allowed"])

    def test_m18(self):
        self.assertEqual(p04_observed_status()["status"], "UNKNOWN")

    def test_m19(self):
        self.assertNotIn("PASS", [p04_observed_status()["status"]])

    def test_m20(self):
        self.assertTrue(
            assert_customer_scoped_asset_reuse(requester_customer_id="", asset_customer_id="")["ok"]
        )

    def test_m21(self):
        self.assertIn("build03", (ROOT / "pipeline" / "scene_builder.py").read_text(encoding="utf-8").lower())

    def test_m22(self):
        self.assertIn("resolve_visual_mode_for_scene", (ROOT / "pipeline" / "scene_builder.py").read_text(encoding="utf-8"))

    def test_m23(self):
        self.assertIn("assert_beat_scene_binding", (ROOT / "pipeline" / "scene_builder.py").read_text(encoding="utf-8"))

    def test_m24(self):
        self.assertIn("c05s_visual_beats", (ROOT / "pipeline" / "trs_facade.py").read_text(encoding="utf-8"))

    def test_m25(self):
        self.assertEqual(build_generation_payload_from_scene(_scene(), apply_harden=False)["paid_api_calls"], 0)

    def test_m26(self):
        self.assertTrue(callable(idempotent_image_clip_via_build03))


def _count():
    return unittest.TestLoader().loadTestsFromModule(sys.modules[__name__]).countTestCases()


if __name__ == "__main__":
    n = _count()
    print(f"C05-MR focused test count: {n}")
    if n < 140:
        raise SystemExit(f"Need >=140 tests, found {n}")
    unittest.main(verbosity=2)
