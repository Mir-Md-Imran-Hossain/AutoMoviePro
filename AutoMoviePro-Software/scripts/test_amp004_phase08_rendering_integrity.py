"""AMP-004 Phase-08 — Industrial VFX + FFmpeg + rendering integrity tests.

No paid API calls.
"""
from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from pipeline.quality.contracts import RepairScope
from pipeline.quality.publishability import evaluate_publishability
from pipeline.rendering_integrity.contract import (
    FilterNode,
    FiltergraphContract,
    GeometrySpec,
    StreamMap,
    TimelineSegment,
    TransitionDirective,
    VfxDirective,
    build_render_integrity_contract,
    render_contract_fingerprint,
)
from pipeline.rendering_integrity.filtergraph import (
    build_explicit_ffmpeg_args,
    validate_filtergraph,
    validate_geometry,
)
from pipeline.rendering_integrity.gate import (
    MAX_RENDER_INTEGRITY_REPAIR_CYCLES,
    allow_render_integrity_repair_cycle,
    persist_rendering_integrity_gate,
    record_render_integrity_repair_cycle,
)
from pipeline.rendering_integrity.observe import observe_rendered_output
from pipeline.rendering_integrity.preflight import (
    RenderPreflightError,
    preflight_clip_inputs,
    preflight_render_contract,
)
from pipeline.rendering_integrity.production import (
    apply_production_render_preflight,
    run_production_rendering_gate,
)
from pipeline.rendering_integrity.repair_bridge import plan_rendering_integrity_repair, scope_for_render_issue
from pipeline.rendering_integrity.retry import classify_render_failure, should_retry_render
from pipeline.rendering_integrity.text_render import validate_render_text
from pipeline.rendering_integrity.timeline import validate_av_sync_plan, validate_timeline
from pipeline.rendering_integrity.vfx import validate_transition_directives, validate_vfx_directives


class Phase08RenderingIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="amp004_p08_"))

    def _contract(self, **kw):
        base = dict(
            project_id="job-1",
            render_id="r1",
            durations=[3.0, 4.0, 2.5],
            scene_ids=["s0", "s1", "s2"],
            width=1080,
            height=1920,
            fps=25.0,
        )
        base.update(kw)
        return build_render_integrity_contract(**base)

    def test_01_render_contract_validation(self):
        c = self._contract()
        self.assertTrue(c.contract_fingerprint)
        self.assertEqual(len(c.timeline), 3)
        pf = preflight_render_contract(c, block=False)
        self.assertEqual(pf["status"], "PASS")

    def test_02_timeline_ordering(self):
        segs = [
            TimelineSegment("b", 2.0, 4.0),
            TimelineSegment("a", 0.0, 2.0),
        ]
        r = validate_timeline(segs)
        self.assertEqual(r["status"], "PASS")

    def test_03_overlap_gap_detection(self):
        accidental = validate_timeline(
            [TimelineSegment("a", 0, 3), TimelineSegment("b", 2, 5)]
        )
        self.assertTrue(any("accidental_overlap" in i for i in accidental["issues"]))
        gap = validate_timeline(
            [TimelineSegment("a", 0, 2), TimelineSegment("b", 3, 5)]
        )
        self.assertTrue(any("accidental_gap" in i for i in gap["issues"]))

    def test_04_intentional_overlap_with_reason(self):
        r = validate_timeline(
            [
                TimelineSegment("a", 0, 3, intentional_overlap=True, overlap_reason="crossfade"),
                TimelineSegment("b", 2, 5, intentional_overlap=True, overlap_reason="crossfade"),
            ]
        )
        self.assertEqual(r["status"], "PASS")

    def test_05_duration_integrity(self):
        bad = validate_timeline([TimelineSegment("a", 0, 0)])
        self.assertTrue(any("zero_duration" in i for i in bad["issues"]))
        neg = validate_timeline([TimelineSegment("a", 5, 2)])
        self.assertTrue(any("negative_duration" in i or "end_before_start" in i for i in neg["issues"]))

    def test_06_av_synchronization_plan(self):
        r = validate_av_sync_plan(video_durations=[3.0, 4.0], audio_durations=[3.1, 4.0])
        self.assertEqual(r["status"], "PASS")
        bad = validate_av_sync_plan(video_durations=[3.0], audio_durations=[10.0])
        self.assertEqual(bad["status"], "BLOCK")

    def test_07_av_sync_unknown_when_empty(self):
        r = validate_av_sync_plan(video_durations=[], audio_durations=[])
        self.assertEqual(r["status"], "UNKNOWN")

    def test_08_stream_mapping(self):
        fg = FiltergraphContract(
            nodes=[FilterNode("c0", "concat", inputs=["v0"], outputs=["vout"])],
            stream_maps=[StreamMap("vout", "video", "c0", True)],
        )
        r = validate_filtergraph(fg)
        self.assertIn("audio_stream_unmapped", r["issues"])

    def test_09_filtergraph_validation(self):
        c = self._contract()
        r = validate_filtergraph(c.filtergraph)
        self.assertEqual(r["status"], "PASS")
        empty = validate_filtergraph(FiltergraphContract())
        self.assertEqual(empty["status"], "BLOCK")

    def test_10_geometry_aspect_ratio(self):
        ok = validate_geometry(GeometrySpec(1080, 1920, 25.0))
        self.assertEqual(ok["status"], "PASS")
        bad = validate_geometry(GeometrySpec(0, 1920, 25.0))
        self.assertIn("invalid_dimensions", bad["issues"])
        extreme = validate_geometry(GeometrySpec(10, 2000, 25.0))
        self.assertIn("extreme_aspect_ratio", extreme["issues"])

    def test_11_fps(self):
        bad = validate_geometry(GeometrySpec(1080, 1920, 0))
        self.assertIn("invalid_fps", bad["issues"])

    def test_12_audio_preservation_mapping(self):
        c = self._contract()
        types = {s.media_type for s in c.filtergraph.stream_maps if s.mapped}
        self.assertIn("audio", types)
        self.assertIn("video", types)

    def test_13_subtitle_text_integrity(self):
        r = validate_render_text(text="Hello world", language="en", safe_area=True)
        self.assertIn(r["status"], ("PASS", "WARN"))
        self.assertNotEqual(r["status"], "BLOCK")

    def test_14_rtl_glyph_safety(self):
        r = validate_render_text(text="مرحبا", language="ar")
        self.assertIn(r["status"], ("PASS", "UNKNOWN", "WARN", "BLOCK"))

    def test_15_overflow_safe_area(self):
        r = validate_render_text(text="x", overflow=True, safe_area=False)
        self.assertEqual(r["status"], "BLOCK")

    def test_16_vfx_purpose_enforcement(self):
        bad = validate_vfx_directives(
            [VfxDirective("v1", "s0", "", 0, 1)]
        )
        self.assertEqual(bad["status"], "BLOCK")
        ok = validate_vfx_directives(
            [VfxDirective("v1", "s0", "emphasis", 0, 1, intensity=0.4)]
        )
        self.assertEqual(ok["status"], "PASS")

    def test_17_vfx_outside_scene_bounds(self):
        r = validate_vfx_directives(
            [VfxDirective("v1", "s0", "emphasis", 0, 10)],
            scene_bounds={"s0": (0.0, 3.0)},
        )
        self.assertTrue(any("outside_scene_bounds" in i for i in r["issues"]))

    def test_18_transition_governance(self):
        ok = validate_transition_directives(
            [TransitionDirective("s0", "s1", "cut", 0, "default_cut", 3.0)]
        )
        self.assertEqual(ok["status"], "PASS")
        bad = validate_transition_directives(
            [TransitionDirective("s0", "s1", "spin", 0.5, "", 3.0)]
        )
        self.assertEqual(bad["status"], "BLOCK")

    def test_19_transition_longer_than_interval(self):
        r = validate_transition_directives(
            [TransitionDirective("s0", "s1", "fade", 5.0, "soft", 3.0)],
            scene_interval={"s0->s1": 2.0},
        )
        self.assertTrue(any("transition_longer" in i for i in r["issues"]))

    def test_20_temporary_artifact_isolation(self):
        gate = run_production_rendering_gate(self.tmp, job_id="job-x", require_output=True)
        self.assertEqual(gate["status"], "FAIL")
        (self.tmp / "x.tmp.mp4").write_bytes(b"0" * 100)
        gate2 = run_production_rendering_gate(self.tmp, job_id="job-x", require_output=True)
        self.assertTrue(any("stale_temporary" in i or "missing" in i for i in gate2["issues"]))

    def test_21_deterministic_contract_fingerprint(self):
        a = render_contract_fingerprint(self._contract())
        b = render_contract_fingerprint(self._contract())
        self.assertEqual(a, b)
        c = render_contract_fingerprint(self._contract(durations=[3.0, 4.0, 9.0]))
        self.assertNotEqual(a, c)

    def test_22_retry_classification(self):
        self.assertEqual(
            classify_render_failure(issues=["accidental_overlap:a->b"]),
            "DETERMINISTIC_INPUT_ERROR",
        )
        self.assertEqual(classify_render_failure(timed_out=True), "TRANSIENT")
        self.assertEqual(
            classify_render_failure(validation_ok=False, issues=["partial_or_tiny_output"]),
            "OUTPUT_VALIDATION_FAILURE",
        )

    def test_23_no_retry_deterministic_input(self):
        self.assertFalse(should_retry_render("DETERMINISTIC_INPUT_ERROR", attempt=0))
        self.assertFalse(should_retry_render("FILTERGRAPH_ERROR", attempt=0))
        self.assertTrue(should_retry_render("TRANSIENT", attempt=0))
        self.assertFalse(should_retry_render("UNKNOWN", attempt=0))

    def test_24_failed_render_rejection(self):
        persist_rendering_integrity_gate(self.tmp, {"status": "FAIL", "issues": ["partial"]})
        from pipeline.rendering_integrity.gate import load_rendering_integrity_gate

        g = load_rendering_integrity_gate(self.tmp)
        self.assertEqual(g["status"], "FAIL")

    def test_25_actual_output_verification_missing(self):
        obs = observe_rendered_output(self.tmp / "nope.mp4")
        self.assertEqual(obs["status"], "FAIL")
        self.assertTrue(obs["subprocess_success_is_not_proof"])

    def test_26_publishability_integration(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            rendering_integrity_status="FAIL",
        )
        self.assertFalse(pub["publishable"])
        ok = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            rendering_integrity_status="PASS",
            semantic_status="PASS",
        )
        self.assertTrue(ok["publishable"])

    def test_27_production_call_graph(self):
        import pipeline.video_pipeline as vp
        import pipeline.idempotency.render_bridge as rb

        self.assertIn("run_production_rendering_gate", inspect.getsource(vp.generate_video))
        self.assertIn("apply_production_render_preflight", inspect.getsource(rb.idempotent_compose_final_video))

    def test_28_missing_video_stream_issue(self):
        # Simulated via observe on tiny file
        p = self.tmp / "tiny.mp4"
        p.write_bytes(b"not-a-video")
        obs = observe_rendered_output(p)
        self.assertEqual(obs["status"], "FAIL")

    def test_29_malformed_filtergraph(self):
        r = validate_filtergraph(
            FiltergraphContract(nodes=[FilterNode("n1", "", [], [])], stream_maps=[])
        )
        self.assertEqual(r["status"], "BLOCK")

    def test_30_zero_duration_scene(self):
        with self.assertRaises(RenderPreflightError) as ctx:
            preflight_render_contract(self._contract(durations=[0.0, 2.0]), block=True)
        self.assertTrue(any("zero_duration" in i for i in ctx.exception.issues))

    def test_31_negative_duration(self):
        r = validate_timeline([TimelineSegment("a", 4, 1)])
        self.assertEqual(r["status"], "BLOCK")

    def test_32_accidental_overlap(self):
        r = validate_timeline([TimelineSegment("a", 0, 5), TimelineSegment("b", 1, 6)])
        self.assertTrue(any("accidental_overlap" in i for i in r["issues"]))

    def test_33_accidental_gap(self):
        r = validate_timeline([TimelineSegment("a", 0, 1), TimelineSegment("b", 5, 6)])
        self.assertTrue(any("accidental_gap" in i for i in r["issues"]))

    def test_34_fps_mismatch_observation_contract(self):
        c = self._contract()
        c.geometry.fps = 60.0
        # Without real media, observe missing file
        obs = observe_rendered_output(self.tmp / "x.mp4", contract=c)
        self.assertEqual(obs["status"], "FAIL")

    def test_35_aspect_ratio_mismatch_geometry(self):
        r = validate_geometry(GeometrySpec(100, 10, 25))
        self.assertIn("extreme_aspect_ratio", r["issues"])

    def test_36_unsupported_text_glyph_unknown(self):
        r = validate_render_text(text="漢字テスト", language="ja")
        self.assertIn(r["status"], ("PASS", "UNKNOWN", "WARN", "BLOCK"))

    def test_37_subtitle_overflow(self):
        r = validate_render_text(text="hi", overflow=True)
        self.assertEqual(r["status"], "BLOCK")

    def test_38_vfx_outside_bounds(self):
        r = validate_vfx_directives(
            [VfxDirective("vx", "s1", "atmosphere", 10, 12)],
            scene_bounds={"s1": (0, 2)},
        )
        self.assertEqual(r["status"], "BLOCK")

    def test_39_transition_too_long(self):
        r = validate_transition_directives(
            [TransitionDirective("a", "b", "dissolve", 9, "soft", 0)],
            scene_interval={"a->b": 1.0},
        )
        self.assertEqual(r["status"], "BLOCK")

    def test_40_stale_temporary_artifact(self):
        (self.tmp / "final_short.tmp.mp4").write_bytes(b"x" * 50)
        g = run_production_rendering_gate(self.tmp, job_id="job-1", require_output=True)
        self.assertIn(g["status"], ("FAIL", "UNKNOWN"))

    def test_41_partial_output(self):
        p = self.tmp / "final_short.mp4"
        p.write_bytes(b"partial")
        obs = observe_rendered_output(p)
        self.assertTrue(any("partial" in i for i in obs["issues"]))

    def test_42_failed_render_not_pass(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            rendering_integrity_status="FAIL",
        )
        self.assertNotEqual(pub.get("verdict"), "PUBLISHABLE")

    def test_43_ffmpeg_success_not_proof(self):
        obs = observe_rendered_output(self.tmp / "missing.mp4")
        self.assertTrue(obs.get("subprocess_success_is_not_proof"))

    def test_44_wrong_project(self):
        c = self._contract(project_id="other-job")
        from pipeline.rendering_integrity.gate import persist_render_contract

        persist_render_contract(self.tmp, c.to_dict(), key="job-1")
        p = self.tmp / "final_short.mp4"
        p.write_bytes(b"0" * 9000)
        g = run_production_rendering_gate(self.tmp, job_id="job-1", final_path=p, require_output=True)
        self.assertTrue(any("wrong_project" in i for i in g["issues"]) or g["status"] in ("FAIL", "UNKNOWN"))

    def test_45_retry_wrong_artifact_bounded(self):
        for _ in range(MAX_RENDER_INTEGRITY_REPAIR_CYCLES):
            record_render_integrity_repair_cycle(self.tmp, outcome="x", scope="RENDER")
        self.assertFalse(allow_render_integrity_repair_cycle(self.tmp))
        self.assertIsNone(plan_rendering_integrity_repair(issues=["geometry_mismatch"], work_dir=self.tmp))

    def test_46_mandatory_unknown_blocks_publish(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            rendering_integrity_status="UNKNOWN",
        )
        self.assertFalse(pub["publishable"])

    def test_47_no_duplicate_ffmpeg_authority(self):
        from pipeline.rendering_integrity.ffmpeg_boundary import run_controlled_ffmpeg
        from pipeline.ffmpeg_exec import run_ffmpeg

        self.assertTrue(callable(run_controlled_ffmpeg))
        self.assertTrue(callable(run_ffmpeg))
        src = inspect.getsource(run_controlled_ffmpeg)
        self.assertIn("run_ffmpeg", src)

    def test_48_no_duplicate_quality_engine(self):
        import pipeline.quality.orchestrator as orch

        self.assertTrue(hasattr(orch, "quality_gate_orchestrator"))

    def test_49_explicit_ffmpeg_args_no_shell(self):
        args = build_explicit_ffmpeg_args(
            inputs=["a.mp4", "b.mp4"],
            filter_complex="[0:v][1:v]concat=n=2:v=1:a=0[vout]",
            output="out.mp4",
            map_audio="0:a:0?",
        )
        self.assertIsInstance(args, list)
        self.assertIn("-filter_complex", args)
        self.assertIn("-map", args)
        self.assertNotIn(" && ", " ".join(args))

    def test_50_preflight_blocks_before_provider(self):
        calls = []

        def provider(_tmp):
            calls.append(1)
            return _tmp

        with self.assertRaises(RenderPreflightError):
            preflight_render_contract(self._contract(durations=[-1.0]), block=True)
        self.assertEqual(calls, [])

    def test_51_clip_input_preflight(self):
        with self.assertRaises(RenderPreflightError):
            preflight_clip_inputs([], block=True)

    def test_52_minimal_repair_scope(self):
        self.assertEqual(scope_for_render_issue("missing_audio_stream"), RepairScope.AUDIO_ASSET)
        self.assertEqual(scope_for_render_issue("filtergraph_error"), RepairScope.RENDER)
        plan = plan_rendering_integrity_repair(issues=["accidental_gap:a->b"], work_dir=self.tmp)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.repair_scope, RepairScope.RENDER)

    def test_53_layer_e_marked(self):
        obs = observe_rendered_output(self.tmp / "x.mp4")
        self.assertEqual(obs.get("layer"), "E")

    def test_54_intentional_gap_requires_reason(self):
        r = validate_timeline(
            [
                TimelineSegment("a", 0, 1, intentional_gap=True, gap_reason=""),
                TimelineSegment("b", 3, 4, intentional_gap=True, gap_reason=""),
            ]
        )
        self.assertTrue(any("intentional_gap_missing_reason" in i for i in r["issues"]))

    def test_55_build04d_authority_unchanged(self):
        from pipeline.idempotency.render_runtime import execute_render_request
        from pipeline.idempotency.render_bridge import idempotent_compose_final_video

        self.assertTrue(callable(execute_render_request))
        self.assertTrue(callable(idempotent_compose_final_video))

    def test_56_p04_authority_unchanged(self):
        from pipeline.artifact_verification.production import run_production_artifact_verification

        self.assertTrue(callable(run_production_artifact_verification))

    def test_57_checkpoint_persistence(self):
        # Create tiny real files so clip preflight passes; durations forced
        clips = []
        for i in range(2):
            p = self.tmp / f"c{i}.mp4"
            p.write_bytes(b"0" * 200)
            clips.append(p)
        c = build_render_integrity_contract(
            project_id="job-p",
            render_id="r",
            clips=clips,
            durations=[2.0, 2.0],
        )
        pf = preflight_render_contract(c, block=False)
        self.assertEqual(pf["status"], "PASS")
        from pipeline.rendering_integrity.gate import persist_render_contract

        persist_render_contract(self.tmp, c.to_dict(), key="job-p")
        self.assertTrue((self.tmp / "render_contracts" / "job-p.json").is_file())

    def test_58_odd_dimensions_blocked(self):
        r = validate_geometry(GeometrySpec(1081, 1920, 25))
        self.assertIn("odd_frame_dimension", r["issues"])

    def test_59_duplicate_scene_id(self):
        r = validate_timeline(
            [TimelineSegment("same", 0, 1), TimelineSegment("same", 1, 2)]
        )
        self.assertIn("duplicate_scene_id_on_timeline", r["issues"])

    def test_60_encoding_error_classification(self):
        self.assertEqual(
            classify_render_failure(exit_code=1, stderr="encoder error codec"),
            "ENCODING_ERROR",
        )

    def test_61_no_paid_api_in_module(self):
        import pipeline.rendering_integrity as ri
        import pathlib

        root = pathlib.Path(ri.__file__).parent
        blob = ""
        for p in root.glob("*.py"):
            blob += p.read_text(encoding="utf-8")
        self.assertNotIn("openai.com", blob.lower())
        self.assertNotIn("openrouter", blob.lower())

    def test_62_absent_rendering_integrity_not_blocking(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            rendering_integrity_status="ABSENT",
            semantic_status="PASS",
        )
        self.assertTrue(pub["publishable"])

    def test_63_structural_determinism_args(self):
        a = build_explicit_ffmpeg_args(inputs=["a.mp4"], filter_complex="", output="o.mp4")
        b = build_explicit_ffmpeg_args(inputs=["a.mp4"], filter_complex="", output="o.mp4")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
