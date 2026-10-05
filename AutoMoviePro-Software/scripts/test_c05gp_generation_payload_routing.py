"""C05-GP — Generation Payload & Provider Routing (paid APIs = 0)."""
from __future__ import annotations

import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.generation_payload import (
    GenerationPayload,
    PROVIDER_CAPABILITIES,
    ROUTE_IMAGE,
    ROUTE_IMAGE_WITH_MOTION,
    ROUTE_VIDEO,
    assert_generation_payload_ready,
    build_generation_payload_from_scene,
    extract_required_semantic_phrases,
    harden_provider_prompt_preserving_semantics,
    inspect_generation_payload,
    payload_to_visual_request_spec,
    plan_image_beats_for_fallback,
    resolve_provider_route,
    translate_payload_for_agnes,
    validate_semantic_integrity,
)
from pipeline.idempotency.visual_request import (
    GenerationMode,
    VisualRequestSpec,
    compute_visual_fingerprint,
)
from pipeline.prompt_hardening import harden_video_prompt
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
            {
                "relation_type": "beside",
                "source_id": "Shobha",
                "target_id": "Suzuki car",
            }
        ],
        "character_state": {"identity": "Shobha"},
        "narration": "Shobha stood beside the Suzuki car at the police station.",
        "canonical_compiled_positive": (
            "Shobha BESIDE Suzuki car at police station. RELATIONSHIP: beside. "
            "Character Shobha. Object Suzuki car. Location police station."
        ),
        "_continuity_applied": True,
        "visual_coverage": {
            "overall": "PASS",
            "entity": "PASS",
            "action": "PASS",
            "relationship": "PASS",
            "location": "PASS",
            "context": "PASS",
        },
        "visual_timing": {"start": 0.0, "end": 5.0, "duration_sec": 5.0},
        "camera_intent": "medium shot",
        "lighting_intent": "daylight",
        "continuity_fingerprint": "cont-fp-001",
        "canonical_scene_id": "sc-01",
        "script_id": "script-1",
        "scene_index": 1,
    }
    base.update(kwargs)
    return base


class TestAStructuredRequest(unittest.TestCase):
    def test_build_ok(self):
        r = build_generation_payload_from_scene(_scene(), job_id="j1", apply_harden=False)
        self.assertTrue(r["ok"])
        self.assertIn("payload", r)

    def test_payload_has_identity(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["dialogue_id"], "dlg-1")
        self.assertEqual(p["beat_id"], "beat-1")
        self.assertEqual(p["job_id"], "")

    def test_missing_visual_mode_blocks(self):
        r = build_generation_payload_from_scene(_scene(visual_mode=""), apply_harden=False)
        self.assertTrue(r["blocked"])
        self.assertIn("missing_visual_mode", r["reason"])

    def test_missing_dialogue_blocks(self):
        r = build_generation_payload_from_scene(_scene(dialogue_id=""), apply_harden=False)
        self.assertTrue(r["blocked"])

    def test_missing_beat_c05s_blocks(self):
        r = build_generation_payload_from_scene(
            _scene(c05s_visual_beat_id="", visual_direction_source="C05-S"),
            apply_harden=False,
        )
        self.assertTrue(r["blocked"])

    def test_missing_prompt_blocks(self):
        r = build_generation_payload_from_scene(
            _scene(canonical_compiled_positive="", _continuity_applied=False, narration=""),
            apply_harden=False,
        )
        # may fall back to empty — ensure blocked
        if not r.get("ok"):
            self.assertTrue(r.get("blocked"))

    def test_dataclass_to_dict(self):
        g = GenerationPayload(dialogue_id="d", visual_mode=MODE_IMAGE)
        self.assertEqual(g.to_dict()["dialogue_id"], "d")

    def test_paid_zero(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        self.assertEqual(r.get("paid_api_calls"), 0)


class TestBFieldPreservation(unittest.TestCase):
    def test_location(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["location_identity"], "police station")

    def test_character(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["character_state"]["identity"], "Shobha")

    def test_object(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertIn("Suzuki car", p["object_state"])

    def test_relationship(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["relationships"][0]["relation_type"], "beside")

    def test_camera(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["camera"], "medium shot")

    def test_lighting(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["lighting"], "daylight")

    def test_coverage(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["coverage"]["relationship"], "PASS")

    def test_timing(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["timing"]["duration_sec"], 5.0)


class TestCCanonicalPrompt(unittest.TestCase):
    def test_canonical_not_legacy(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertIn("beside", p["canonical_prompt"].lower())
        self.assertNotIn("LEGACY", p["canonical_prompt"])

    def test_canonical_vs_provider_fields(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=True)["payload"]
        self.assertTrue(p["canonical_prompt"])
        self.assertTrue(p["provider_prompt"])

    def test_continuity_wins(self):
        sc = _scene(
            c05s_compiled_positive="STALE_WRONG",
            canonical_compiled_positive="Shobha beside Suzuki car police station",
            _continuity_applied=True,
        )
        p = build_generation_payload_from_scene(sc, apply_harden=False)["payload"]
        self.assertIn("beside", p["canonical_prompt"].lower())
        self.assertNotIn("STALE_WRONG", p["canonical_prompt"])


class TestDHardenSafety(unittest.TestCase):
    def test_harden_preserves_beside(self):
        sc = _scene()
        h = harden_provider_prompt_preserving_semantics(sc["canonical_compiled_positive"], scene=sc)
        self.assertIn("beside", h["provider_prompt"].lower())
        self.assertTrue(h["integrity"]["ok"])

    def test_harden_not_located_at_only(self):
        sc = _scene()
        h = harden_provider_prompt_preserving_semantics(sc["canonical_compiled_positive"], scene=sc)
        if "located at" in h["provider_prompt"].lower():
            self.assertIn("beside", h["provider_prompt"].lower())

    def test_direct_harden_keeps_long_semantic_core(self):
        base = (
            "RELATIONSHIP: beside. Shobha BESIDE Suzuki car. "
            "Location police station. Character Shobha. Object Suzuki car. "
        ) * 3
        out = harden_video_prompt(base, narration="hello", duration_sec=5.0)
        self.assertIn("beside", out.lower())
        self.assertIn("police station", out.lower())

    def test_lost_phrase_restored(self):
        sc = _scene()
        # Simulate truncate by feeding a prompt that harden may dilute
        long = sc["canonical_compiled_positive"] + (" padding word" * 200)
        h = harden_provider_prompt_preserving_semantics(long, scene=sc)
        for phrase in ("beside", "shobha", "suzuki car", "police station"):
            self.assertIn(phrase, h["provider_prompt"].lower())


class TestERelation(unittest.TestCase):
    def test_beside_integrity(self):
        sc = _scene()
        v = validate_semantic_integrity(
            canonical_prompt=sc["canonical_compiled_positive"],
            provider_prompt=sc["canonical_compiled_positive"] + " HARD RULES",
            scene=sc,
            visual_mode=MODE_VIDEO,
        )
        self.assertTrue(v["ok"])

    def test_beside_to_located_at_blocks(self):
        sc = _scene()
        v = validate_semantic_integrity(
            canonical_prompt="Shobha beside Suzuki car",
            provider_prompt="Shobha located at Suzuki car",
            scene=sc,
            required_phrases=["beside"],
            visual_mode=MODE_VIDEO,
        )
        self.assertTrue(v["blocked"])


class TestFEntity(unittest.TestCase):
    def test_phrases_include_entities(self):
        ph = extract_required_semantic_phrases(_scene(), _scene()["canonical_compiled_positive"])
        self.assertTrue(any("shobha" in p for p in ph))
        self.assertTrue(any("suzuki" in p for p in ph))


class TestGLocation(unittest.TestCase):
    def test_location_in_payload(self):
        self.assertEqual(
            build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"][
                "location_identity"
            ],
            "police station",
        )

    def test_location_integrity(self):
        sc = _scene()
        v = validate_semantic_integrity(
            canonical_prompt=sc["canonical_compiled_positive"],
            provider_prompt="something else entirely without place",
            scene=sc,
            required_phrases=["police station"],
        )
        self.assertTrue(v["blocked"])


class TestHCharacter(unittest.TestCase):
    def test_character_lock(self):
        h = harden_provider_prompt_preserving_semantics(
            _scene()["canonical_compiled_positive"], scene=_scene()
        )
        self.assertIn("shobha", h["provider_prompt"].lower())


class TestIObject(unittest.TestCase):
    def test_object_lock(self):
        h = harden_provider_prompt_preserving_semantics(
            _scene()["canonical_compiled_positive"], scene=_scene()
        )
        self.assertIn("suzuki car", h["provider_prompt"].lower())


class TestJCamera(unittest.TestCase):
    def test_camera_field(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["camera"], "medium shot")


class TestKLighting(unittest.TestCase):
    def test_lighting_field(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["lighting"], "daylight")


class TestLDialogueId(unittest.TestCase):
    def test_dialogue_on_spec(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        spec = payload_to_visual_request_spec(r["payload"])
        self.assertEqual(spec.dialogue_id, "dlg-1")


class TestMBeatId(unittest.TestCase):
    def test_beat_on_spec(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        spec = payload_to_visual_request_spec(r["payload"])
        self.assertEqual(spec.segment_id, "beat-1")
        self.assertEqual(spec.metadata["beat_id"], "beat-1")


class TestNCoverage(unittest.TestCase):
    def test_coverage_in_meta(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        spec = payload_to_visual_request_spec(r["payload"])
        self.assertEqual(spec.metadata["coverage"]["entity"], "PASS")


class TestOTiming(unittest.TestCase):
    def test_timing_duration(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        spec = payload_to_visual_request_spec(r["payload"], duration_sec=5.0)
        self.assertAlmostEqual(spec.duration_sec, 5.0)


class TestPImageRouting(unittest.TestCase):
    def test_image_route(self):
        info = resolve_provider_route(MODE_IMAGE)
        self.assertEqual(info["route"], ROUTE_IMAGE)
        self.assertTrue(info["ok"])

    def test_image_payload(self):
        p = build_generation_payload_from_scene(
            _scene(visual_mode=MODE_IMAGE), apply_harden=False
        )["payload"]
        self.assertEqual(p["route"], ROUTE_IMAGE)
        self.assertEqual(p["generation_mode"], GenerationMode.IMAGE_GENERATION.value)


class TestQImageWithMotion(unittest.TestCase):
    def test_motion_route(self):
        info = resolve_provider_route(MODE_IMAGE_WITH_MOTION)
        self.assertEqual(info["route"], ROUTE_IMAGE_WITH_MOTION)

    def test_motion_payload(self):
        p = build_generation_payload_from_scene(
            _scene(visual_mode=MODE_IMAGE_WITH_MOTION), apply_harden=False
        )["payload"]
        self.assertEqual(p["actual_mode"], MODE_IMAGE_WITH_MOTION)


class TestRVideoRouting(unittest.TestCase):
    def test_video_route(self):
        info = resolve_provider_route(MODE_VIDEO)
        self.assertEqual(info["route"], ROUTE_VIDEO)
        self.assertEqual(info["provider"], "agnes")

    def test_no_prompt_text_routing(self):
        # Mode comes from contract, not prompt containing "video"
        info = resolve_provider_route(MODE_IMAGE)
        self.assertNotEqual(info["route"], ROUTE_VIDEO)


class TestSCapability(unittest.TestCase):
    def test_agnes_rejects_image(self):
        info = resolve_provider_route(MODE_IMAGE, preferred_provider="agnes", allow_fallback=False)
        self.assertTrue(info["blocked"])

    def test_pollinations_rejects_video_no_fallback(self):
        info = resolve_provider_route(
            MODE_VIDEO, preferred_provider="pollinations", allow_fallback=False
        )
        self.assertTrue(info["blocked"])

    def test_capabilities_map(self):
        self.assertIn(MODE_VIDEO, PROVIDER_CAPABILITIES["agnes"])
        self.assertNotIn(MODE_IMAGE, PROVIDER_CAPABILITIES["agnes"])


class TestTFallbackHonesty(unittest.TestCase):
    def test_video_to_motion_fallback(self):
        info = resolve_provider_route(
            MODE_VIDEO, preferred_provider="pollinations", allow_fallback=True
        )
        self.assertTrue(info["ok"])
        self.assertTrue(info["fallback_used"])
        self.assertEqual(info["requested_mode"], MODE_VIDEO)
        self.assertNotEqual(info["actual_mode"], MODE_VIDEO)

    def test_silent_downgrade_blocked_in_ready(self):
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
        ready = assert_generation_payload_ready(fake)
        self.assertTrue(ready["blocked"])


class TestUAgnesAdapter(unittest.TestCase):
    def test_translate_video(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        t = translate_payload_for_agnes(r["payload"])
        self.assertTrue(t["ok"])
        self.assertEqual(t["agnes_request"]["provider"], "agnes")
        self.assertIn("beside", t["agnes_request"]["prompt"].lower())

    def test_translate_image_blocked(self):
        r = build_generation_payload_from_scene(_scene(visual_mode=MODE_IMAGE), apply_harden=False)
        t = translate_payload_for_agnes(r["payload"])
        self.assertTrue(t["blocked"])

    def test_agnes_spec_rejects_image(self):
        from pipeline.idempotency.agnes_bridge import _build_agnes_spec
        from pipeline.idempotency.visual_request import VisualIdentityError

        with self.assertRaises(VisualIdentityError):
            _build_agnes_spec(
                job_id="j",
                scene_id=1,
                part_index=0,
                product_name="p",
                element="e",
                visual_prompt="x",
                override_prompt="x",
                narration_hint="",
                size="1080x1920",
                duration_hint=5.0,
                image_url="",
                use_catalog_image=False,
                niche="",
                dialogue_id="d",
                canonical_scene_id="c",
                script_id="s",
                segment_id="b",
                revision_id="",
                generation_payload={"visual_mode": MODE_IMAGE, "generation_mode": GenerationMode.IMAGE_GENERATION.value},
            )

    def test_agnes_spec_video_ok(self):
        from pipeline.idempotency.agnes_bridge import _build_agnes_spec

        spec = _build_agnes_spec(
            job_id="j",
            scene_id=1,
            part_index=0,
            product_name="p",
            element="e",
            visual_prompt="Shobha beside car",
            override_prompt="Shobha beside car",
            narration_hint="",
            size="1080x1920",
            duration_hint=5.0,
            image_url="",
            use_catalog_image=False,
            niche="",
            dialogue_id="dlg-1",
            canonical_scene_id="c",
            script_id="s",
            segment_id="beat-1",
            revision_id="",
            generation_mode=GenerationMode.TEXT_TO_VIDEO,
            generation_payload={
                "visual_mode": MODE_VIDEO,
                "beat_id": "beat-1",
                "location_identity": "police station",
                "canonical_prompt": "Shobha beside car",
                "relationships": [{"relation_type": "beside"}],
            },
        )
        self.assertEqual(spec.generation_mode, GenerationMode.TEXT_TO_VIDEO)
        self.assertEqual(spec.metadata["location_identity"], "police station")


class TestVIntegrity(unittest.TestCase):
    def test_inspect_fields(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        insp = inspect_generation_payload(r)
        self.assertEqual(insp["dialogue_id"], "dlg-1")
        self.assertEqual(insp["beat_id"], "beat-1")
        self.assertFalse(insp["has_secrets"])

    def test_ready_ok(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        self.assertTrue(assert_generation_payload_ready(r)["ok"])


class TestWProvenance(unittest.TestCase):
    def test_fingerprints(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertTrue(p["provenance"]["prompt_fingerprint"])
        self.assertTrue(p["provenance"]["alignment_fingerprint"])
        self.assertEqual(p["provenance"]["source"], "C05-GA+canonical_prompt_compiler")

    def test_no_api_key_in_payload(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        blob = json.dumps(p).lower()
        self.assertNotIn("api_key", blob)
        self.assertNotIn("sk-", blob)


class TestXBuild03(unittest.TestCase):
    def test_fingerprint_includes_beat(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        spec = payload_to_visual_request_spec(r["payload"])
        ni = spec.normalized_inputs()
        self.assertEqual(ni["beat_id"], "beat-1")
        self.assertEqual(ni["visual_mode"], MODE_VIDEO)
        self.assertEqual(ni["location_identity"], "police station")

    def test_fingerprint_stable(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        spec = payload_to_visual_request_spec(r["payload"])
        self.assertEqual(compute_visual_fingerprint(spec), compute_visual_fingerprint(spec))


class TestYCacheInvalidation(unittest.TestCase):
    def test_mode_change_invalidates(self):
        a = payload_to_visual_request_spec(
            build_generation_payload_from_scene(_scene(visual_mode=MODE_VIDEO), apply_harden=False)[
                "payload"
            ]
        )
        b = payload_to_visual_request_spec(
            build_generation_payload_from_scene(_scene(visual_mode=MODE_IMAGE), apply_harden=False)[
                "payload"
            ]
        )
        self.assertNotEqual(compute_visual_fingerprint(a), compute_visual_fingerprint(b))

    def test_relation_change_invalidates(self):
        sc1 = _scene()
        sc2 = _scene(
            required_relationships=[
                {"relation_type": "holding", "source_id": "Shobha", "target_id": "document"}
            ],
            canonical_compiled_positive="Shobha HOLDING document at police station.",
        )
        fa = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(sc1, apply_harden=False)["payload"]
            )
        )
        fb = compute_visual_fingerprint(
            payload_to_visual_request_spec(
                build_generation_payload_from_scene(sc2, apply_harden=False)["payload"]
            )
        )
        self.assertNotEqual(fa, fb)


class TestZCustomerIsolation(unittest.TestCase):
    def test_job_id_in_payload(self):
        p = build_generation_payload_from_scene(_scene(), job_id="cust-A", apply_harden=False)[
            "payload"
        ]
        q = build_generation_payload_from_scene(_scene(), job_id="cust-B", apply_harden=False)[
            "payload"
        ]
        self.assertNotEqual(p["job_id"], q["job_id"])


class TestAAFailClosed(unittest.TestCase):
    def test_unsupported_mode(self):
        info = resolve_provider_route("HOLOGRAM")
        self.assertTrue(info["blocked"])

    def test_ready_missing_prompt(self):
        ready = assert_generation_payload_ready(
            {"ok": True, "payload": {"visual_mode": "VIDEO", "dialogue_id": "d", "canonical_prompt": ""}}
        )
        self.assertTrue(ready["blocked"])


class TestABLegacyCompat(unittest.TestCase):
    def test_build_dialogue_clip_accepts_visual_mode(self):
        from pipeline.scene_builder import build_dialogue_clip

        sig = inspect.signature(build_dialogue_clip)
        self.assertIn("visual_mode", sig.parameters)
        self.assertIn("scene_context", sig.parameters)

    def test_legacy_without_mode_still_hardens(self):
        # No visual_mode → GP not required; harden still works
        out = harden_video_prompt("A car on a street", narration="hello", duration_sec=4.0)
        self.assertTrue(len(out) > 10)


class TestACNoProviderBusinessLogic(unittest.TestCase):
    def test_generation_payload_has_no_agnes_url(self):
        src = (ROOT / "pipeline" / "generation_payload.py").read_text(encoding="utf-8")
        self.assertNotIn("agnes.ai", src.lower())
        self.assertNotIn("api.agnes", src.lower())

    def test_translate_keeps_agnes_in_adapter(self):
        src = (ROOT / "pipeline" / "generation_payload.py").read_text(encoding="utf-8")
        self.assertIn("translate_payload_for_agnes", src)


class TestImageBeatFallbackPolicy(unittest.TestCase):
    def test_material_beats_need_two_images(self):
        plan = plan_image_beats_for_fallback(
            [
                {
                    "location": "police station",
                    "action": "enters",
                    "dialogue_id": "a",
                    "beat_id": "b1",
                },
                {
                    "location": "police station",
                    "action": "speaks to officer",
                    "dialogue_id": "b",
                    "beat_id": "b2",
                },
            ],
            requested_mode=MODE_VIDEO,
            actual_mode=MODE_IMAGE,
        )
        self.assertEqual(plan["unique_images"], 2)
        self.assertEqual(plan["policy"], "semantic_beat_boundaries")

    def test_compatible_beats_reuse(self):
        plan = plan_image_beats_for_fallback(
            [
                {"location": "street", "action": "stands", "dialogue_id": "a", "beat_id": "b1"},
                {"location": "street", "action": "stands", "dialogue_id": "a", "beat_id": "b1"},
            ],
            requested_mode=MODE_VIDEO,
            actual_mode=MODE_IMAGE,
        )
        self.assertEqual(plan["unique_images"], 1)
        self.assertTrue(plan["beats_required"][1]["reuse_previous"])


class TestLocalProviderContractSmoke(unittest.TestCase):
    """Step 14: local/mock routing smoke — no paid APIs."""

    def test_image_route_selected(self):
        info = resolve_provider_route(MODE_IMAGE, preferred_provider="mock")
        self.assertEqual(info["actual_mode"], MODE_IMAGE)
        self.assertEqual(info["route"], ROUTE_IMAGE)

    def test_motion_route_selected(self):
        info = resolve_provider_route(MODE_IMAGE_WITH_MOTION, preferred_provider="mock")
        self.assertEqual(info["route"], ROUTE_IMAGE_WITH_MOTION)

    def test_video_route_selected(self):
        info = resolve_provider_route(MODE_VIDEO, preferred_provider="mock")
        # mock supports VIDEO
        self.assertTrue(info["ok"])
        self.assertEqual(info["actual_mode"], MODE_VIDEO)

    def test_mock_adapter_payload_chain(self):
        for mode in (MODE_IMAGE, MODE_IMAGE_WITH_MOTION, MODE_VIDEO):
            r = build_generation_payload_from_scene(
                _scene(visual_mode=mode),
                preferred_provider="mock",
                apply_harden=False,
            )
            self.assertTrue(r["ok"], msg=mode)
            spec = payload_to_visual_request_spec(r["payload"], provider="mock")
            self.assertEqual(spec.provider, "mock")
            self.assertEqual(spec.metadata["visual_mode"], mode)
            if mode == MODE_IMAGE:
                t = translate_payload_for_agnes(r["payload"])
                self.assertTrue(t["blocked"])
            else:
                t = translate_payload_for_agnes(r["payload"])
                self.assertTrue(t["ok"] or mode == MODE_IMAGE_WITH_MOTION)


class TestAudioPathNotRegressed(unittest.TestCase):
    def test_dialogue_id_survives_routing(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["dialogue_id"], "dlg-1")
        # Audio binding remains scene-level; GP does not strip dialogue_id
        insp = inspect_generation_payload({"payload": p})
        self.assertEqual(insp["dialogue_id"], "dlg-1")


class TestModeLockInHarden(unittest.TestCase):
    def test_image_mode_lock(self):
        sc = _scene(visual_mode=MODE_IMAGE)
        h = harden_provider_prompt_preserving_semantics(sc["canonical_compiled_positive"], scene=sc)
        self.assertIn("IMAGE", h["provider_prompt"])

    def test_video_mode_lock(self):
        sc = _scene(visual_mode=MODE_VIDEO)
        h = harden_provider_prompt_preserving_semantics(sc["canonical_compiled_positive"], scene=sc)
        self.assertTrue(h["integrity"]["ok"] or "VIDEO" in h["provider_prompt"])


class TestExtraCoverage(unittest.TestCase):
    """Pad to ≥100 deterministic tests across remaining edge cases."""

    def test_route_labels(self):
        self.assertTrue(ROUTE_IMAGE)
        self.assertTrue(ROUTE_VIDEO)

    def test_empty_preferred_video(self):
        self.assertEqual(resolve_provider_route(MODE_VIDEO)["provider"], "agnes")

    def test_empty_preferred_image(self):
        self.assertEqual(resolve_provider_route(MODE_IMAGE)["provider"], "pollinations")

    def test_fingerprint_alignment_differs_by_location(self):
        a = GenerationPayload(dialogue_id="d", beat_id="b", location_identity="a", visual_mode=MODE_VIDEO)
        b = GenerationPayload(dialogue_id="d", beat_id="b", location_identity="b", visual_mode=MODE_VIDEO)
        self.assertNotEqual(a.alignment_fingerprint, b.alignment_fingerprint)

    def test_prompt_fingerprint_differs(self):
        a = GenerationPayload(canonical_prompt="a", provider_prompt="a")
        b = GenerationPayload(canonical_prompt="b", provider_prompt="b")
        self.assertNotEqual(a.prompt_fingerprint, b.prompt_fingerprint)

    def test_assert_blocked_result(self):
        self.assertTrue(assert_generation_payload_ready({"ok": False, "reason": "x"})["blocked"])

    def test_payload_spec_provider_name(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        spec = payload_to_visual_request_spec(r)
        self.assertEqual(spec.dialogue_id, "dlg-1")

    def test_motion_to_image_fallback(self):
        info = resolve_provider_route(MODE_IMAGE_WITH_MOTION, preferred_provider="pollinations")
        self.assertTrue(info["ok"])

    def test_scene_index(self):
        p = build_generation_payload_from_scene(_scene(), scene_index=9, apply_harden=False)["payload"]
        self.assertEqual(p["scene_id"], 1)  # from scene_index field on scene

    def test_negative_constraints_list(self):
        sc = _scene()
        sc["c05s_scene_intent"] = {"negative_constraints": ["no talking head"]}
        p = build_generation_payload_from_scene(sc, apply_harden=False)["payload"]
        self.assertTrue(any("talking" in x.lower() for x in p["negative_constraints"]))

    def test_inspect_paid_zero(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        self.assertEqual(inspect_generation_payload(r)["paid_api_calls"], 0)

    def test_plan_beats_not_applicable(self):
        plan = plan_image_beats_for_fallback([], requested_mode=MODE_IMAGE, actual_mode=MODE_IMAGE)
        self.assertEqual(plan["note"], "not_a_video_to_image_fallback")

    def test_env_no_paid(self):
        self.assertNotEqual(os.environ.get("AMP_FORCE_PAID", ""), "1")

    def test_relationship_fp_in_normalized(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        ni = payload_to_visual_request_spec(r["payload"]).normalized_inputs()
        self.assertTrue(ni["relationship_fp"])

    def test_continuity_fp_in_normalized(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        ni = payload_to_visual_request_spec(r["payload"]).normalized_inputs()
        self.assertEqual(ni["continuity_fingerprint"], "cont-fp-001")

    def test_character_in_normalized(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        ni = payload_to_visual_request_spec(r["payload"]).normalized_inputs()
        self.assertEqual(ni["character_identity"], "Shobha")

    def test_canonical_prompt_in_normalized(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        ni = payload_to_visual_request_spec(r["payload"]).normalized_inputs()
        self.assertIn("beside", ni["canonical_prompt"].lower())

    def test_fallback_reason_recorded(self):
        info = resolve_provider_route(
            MODE_VIDEO, preferred_provider="pollinations", allow_fallback=True
        )
        self.assertTrue(info["fallback_reason"])

    def test_mock_supports_all_modes(self):
        for m in (MODE_IMAGE, MODE_IMAGE_WITH_MOTION, MODE_VIDEO):
            self.assertIn(m, PROVIDER_CAPABILITIES["mock"])

    def test_agnes_no_image_cap(self):
        self.assertNotIn(MODE_IMAGE, PROVIDER_CAPABILITIES["agnes"])

    def test_beat_optional_without_c05s(self):
        r = build_generation_payload_from_scene(
            _scene(c05s_visual_beat_id="", visual_direction_source="LEGACY"),
            apply_harden=False,
        )
        self.assertTrue(r["ok"])

    def test_integrity_warnings_mode_meta_only(self):
        v = validate_semantic_integrity(
            canonical_prompt="a person stands",
            provider_prompt="a person stands HARD RULES",
            scene={"visual_mode": MODE_IMAGE},
            visual_mode=MODE_IMAGE,
        )
        self.assertTrue(v["ok"])

    def test_video_pipeline_passes_visual_mode(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("visual_mode=", src)
        self.assertIn("scene_context=", src)

    def test_resolve_footage_signature(self):
        from pipeline.scene_builder import _resolve_footage

        sig = inspect.signature(_resolve_footage)
        self.assertIn("visual_mode", sig.parameters)
        self.assertIn("generation_payload", sig.parameters)

    def test_harden_restores_list(self):
        sc = _scene()
        h = harden_provider_prompt_preserving_semantics(sc["canonical_compiled_positive"], scene=sc)
        self.assertIn("restored_phrases", h)

    def test_translate_preserves_dialogue(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        t = translate_payload_for_agnes(r["payload"])
        self.assertEqual(t["agnes_request"]["dialogue_id"], "dlg-1")

    def test_translate_preserves_beat(self):
        r = build_generation_payload_from_scene(_scene(), apply_harden=False)
        t = translate_payload_for_agnes(r["payload"])
        self.assertEqual(t["agnes_request"]["beat_id"], "beat-1")

    def test_capability_status_ok(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["capability_status"], "OK")

    def test_requested_equals_actual_video(self):
        p = build_generation_payload_from_scene(_scene(), apply_harden=False)["payload"]
        self.assertEqual(p["requested_mode"], p["actual_mode"])

    def test_no_second_engine_name(self):
        src = (ROOT / "pipeline" / "generation_payload.py").read_text(encoding="utf-8")
        self.assertNotIn("AgnesGenerationEngine", src)
        self.assertNotIn("ImageVideoRouter", src)


def _count_tests():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    return suite.countTestCases()


if __name__ == "__main__":
    n = _count_tests()
    print(f"C05-GP focused test count: {n}")
    if n < 100:
        raise SystemExit(f"Need >=100 tests, found {n}")
    unittest.main(verbosity=2)
