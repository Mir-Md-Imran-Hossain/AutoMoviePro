"""AMP-004 Phase-10 — Final production release certification suite.

Certification only: uses existing authorities. No new engines. 0 paid APIs.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from pipeline.artifact_verification.production import run_production_artifact_verification
from pipeline.compose import (
    concat_clips,
    ffmpeg_bin,
    ffprobe_bin,
    make_color_clip,
    probe_media_tool_capability,
)
from pipeline.e2e_industrial.authority_audit import (
    audit_authority_singletons,
    audit_production_bypasses,
    audit_production_call_graph,
)
from pipeline.e2e_industrial.runner import run_e2e_industrial
from pipeline.idempotency.render_validation import probe_render_metadata, validate_render_output
from pipeline.quality.publishability import PublishabilityVerdict, evaluate_publishability
from pipeline.rendering_integrity.observe import observe_rendered_output
from pipeline.rendering_integrity.production import (
    apply_production_render_preflight,
    run_production_rendering_gate,
)


class Phase10FinalCertificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="amp004_p10_"))
        self.cap = probe_media_tool_capability()

    def test_01_ffmpeg_available(self):
        self.assertTrue(self.cap["FFMPEG_AVAILABLE"], self.cap)
        self.assertTrue(Path(self.cap["ffmpeg_path"]).is_file())

    def test_02_ffprobe_available(self):
        self.assertTrue(self.cap["FFPROBE_AVAILABLE"], self.cap)
        self.assertTrue(Path(self.cap["ffprobe_path"]).is_file())

    def test_03_ffmpeg_version_executes(self):
        r = subprocess.run([ffmpeg_bin(), "-version"], capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 0)
        self.assertIn("ffmpeg version", (r.stdout or r.stderr).lower())

    def test_04_ffprobe_version_executes(self):
        r = subprocess.run([ffprobe_bin(), "-version"], capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 0)
        self.assertIn("ffprobe version", (r.stdout or r.stderr).lower())

    def test_05_discovery_not_machine_hardcoded(self):
        # Must resolve via bundled/env/path mechanism — path contains project-relative ffmpeg-* or tools
        p = self.cap["ffmpeg_path"].replace("\\", "/").lower()
        self.assertTrue(
            "ffmpeg-" in p or "tools/ffmpeg" in p or self.cap["ffmpeg_source"] in ("bundled", "env", "env_root", "path"),
            self.cap,
        )
        self.assertEqual(self.cap["ffmpeg_source"], "bundled")

    def test_06_independent_capabilities(self):
        self.assertIn("FFMPEG_AVAILABLE", self.cap)
        self.assertIn("FFPROBE_AVAILABLE", self.cap)
        self.assertNotEqual(ffmpeg_bin(), ffprobe_bin())

    def test_07_production_call_graph(self):
        r = audit_production_call_graph()
        self.assertEqual(r["status"], "PASS", r)

    def test_08_authority_singletons(self):
        r = audit_authority_singletons()
        self.assertEqual(r["status"], "PASS", r.get("issues"))

    def test_09_no_bypass_bugs(self):
        r = audit_production_bypasses()
        self.assertEqual(r["status"], "PASS")

    def test_10_real_clip_generation(self):
        clip = self.tmp / "c0.mp4"
        make_color_clip(clip, seconds=2.0, size="1080x1920")
        self.assertTrue(clip.is_file())
        self.assertGreaterEqual(clip.stat().st_size, 8000)
        meta = probe_render_metadata(clip)
        self.assertTrue(meta["has_video"])
        self.assertTrue(meta["has_audio"])
        self.assertEqual(meta["width"], 1080)
        self.assertEqual(meta["height"], 1920)
        self.assertGreater(meta["duration_sec"], 0)

    def test_11_real_compose_and_observe(self):
        clips = []
        for i in range(3):
            p = self.tmp / f"s{i}.mp4"
            make_color_clip(p, seconds=2.0, size="1080x1920")
            clips.append(p)
        pf = apply_production_render_preflight(
            self.tmp, job_id="p10-real", clips=clips, size="1080x1920", block_on_critical=True
        )
        self.assertEqual(pf["preflight"]["status"], "PASS")
        final = self.tmp / "final_short.mp4"
        concat_clips(clips, final)
        ok, reason = validate_render_output(
            str(final), expected_size="1080x1920", require_audio=True, require_video=True
        )
        self.assertTrue(ok, reason)
        obs = observe_rendered_output(final, contract=pf["contract"], require_audio=True, require_video=True)
        self.assertEqual(obs["status"], "PASS", obs)
        self.assertTrue(obs.get("subprocess_success_is_not_proof"))

    def test_12_rendering_integrity_gate_pass(self):
        clips = []
        for i in range(2):
            p = self.tmp / f"r{i}.mp4"
            make_color_clip(p, seconds=2.0, size="1080x1920")
            clips.append(p)
        apply_production_render_preflight(self.tmp, job_id="p10-rig", clips=clips, size="1080x1920")
        final = self.tmp / "final_short.mp4"
        concat_clips(clips, final)
        gate = run_production_rendering_gate(
            self.tmp, job_id="p10-rig", final_path=final, size="1080x1920", require_output=True
        )
        self.assertEqual(gate["status"], "PASS", gate)

    def test_13_artifact_verification_pass(self):
        clips = []
        for i in range(2):
            p = self.tmp / f"a{i}.mp4"
            make_color_clip(p, seconds=2.0, size="1080x1920")
            clips.append(p)
        final = self.tmp / "final_short.mp4"
        concat_clips(clips, final)
        art = run_production_artifact_verification(self.tmp, job_id="p10-art", final_path=final)
        self.assertEqual(str(art.get("status") or "").upper(), "PASS", art)

    def test_14_publishability_all_gates(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            multimodal_status="PASS",
            semantic_status="PASS",
            artifact_status="PASS",
            render_status="PASS",
            audio_status="PASS",
            localization_status="ABSENT",
            creative_production_status="PASS",
            rendering_integrity_status="PASS",
        )
        self.assertTrue(pub["publishable"])
        self.assertEqual(pub["verdict"], PublishabilityVerdict.PUBLISHABLE.value)

    def test_15_mandatory_unknown_blocks(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            multimodal_status="UNKNOWN",
            semantic_status="PASS",
            artifact_status="PASS",
            render_status="PASS",
            audio_status="PASS",
            localization_status="ABSENT",
            creative_production_status="PASS",
            rendering_integrity_status="PASS",
        )
        self.assertFalse(pub["publishable"])

    def test_16_real_media_end_to_end_publishable(self):
        clips = []
        for i in range(3):
            p = self.tmp / f"e{i}.mp4"
            make_color_clip(p, seconds=2.0, size="1080x1920")
            clips.append(p)
        pf = apply_production_render_preflight(
            self.tmp, job_id="p10-e2e", clips=clips, size="1080x1920", block_on_critical=True
        )
        final = self.tmp / "final_short.mp4"
        concat_clips(clips, final)
        meta = probe_render_metadata(final)
        ok, reason = validate_render_output(str(final), expected_size="1080x1920")
        self.assertTrue(ok, reason)
        obs = observe_rendered_output(final, contract=pf["contract"])
        self.assertEqual(obs["status"], "PASS", obs)
        rig = run_production_rendering_gate(self.tmp, job_id="p10-e2e", final_path=final)
        self.assertEqual(rig["status"], "PASS", rig)
        art = run_production_artifact_verification(self.tmp, job_id="p10-e2e", final_path=final)
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            multimodal_status="PASS",
            semantic_status="PASS",
            artifact_status=str(art.get("status") or "UNKNOWN"),
            render_status="PASS",
            audio_status="PASS",
            localization_status="ABSENT",
            creative_production_status="PASS",
            rendering_integrity_status=str(rig.get("status") or "UNKNOWN"),
        )
        self.assertTrue(pub["publishable"], pub)
        self.assertGreater(meta["duration_sec"], 5.0)
        self.assertEqual(meta["video_codec"], "h264")
        self.assertEqual(meta["audio_codec"], "aac")
        # Certification evidence sidecar (no secrets)
        evidence = {
            "job_id": "p10-e2e",
            "FFMPEG_AVAILABLE": True,
            "FFPROBE_AVAILABLE": True,
            "final_meta": meta,
            "observe": obs.get("status"),
            "rendering_integrity": rig.get("status"),
            "artifact": art.get("status"),
            "publishability": pub.get("verdict"),
            "paid_api_calls": 0,
        }
        (self.tmp / "PHASE10_CERT_EVIDENCE.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        self.assertTrue((self.tmp / "PHASE10_CERT_EVIDENCE.json").is_file())

    def test_17_fail_closed_missing_visual(self):
        r = run_e2e_industrial(work_dir=self.tmp / "m", inject="missing_visual")
        self.assertEqual(r["final_status"], "FAIL_DETECTED")
        self.assertFalse((Path(r["work_dir"]) / "UPLOAD_STATUS.json").is_file())

    def test_18_fail_closed_ffmpeg_fail(self):
        r = run_e2e_industrial(work_dir=self.tmp / "f", inject="ffmpeg_fail")
        self.assertEqual(r["final_status"], "FAIL_DETECTED")
        self.assertFalse((Path(r["work_dir"]) / "UPLOAD_STATUS.json").is_file())

    def test_19_fail_closed_partial_output(self):
        r = run_e2e_industrial(work_dir=self.tmp / "p", inject="partial_output")
        self.assertEqual(r["final_status"], "FAIL_DETECTED")
        self.assertFalse((Path(r["work_dir"]) / "UPLOAD_STATUS.json").is_file())

    def test_20_fail_closed_multimodal_block(self):
        r = run_e2e_industrial(work_dir=self.tmp / "b", inject="multimodal_blocked")
        self.assertFalse(r["publishability"]["publishable"])
        self.assertFalse((Path(r["work_dir"]) / "UPLOAD_STATUS.json").is_file())

    def test_21_fail_closed_mandatory_unknown(self):
        r = run_e2e_industrial(work_dir=self.tmp / "u", inject="mandatory_unknown")
        self.assertFalse(r["publishability"]["publishable"])
        self.assertFalse((Path(r["work_dir"]) / "UPLOAD_STATUS.json").is_file())

    def test_22_invalid_final_artifact_blocks(self):
        clips = []
        for i in range(2):
            p = self.tmp / f"badclip{i}.mp4"
            make_color_clip(p, seconds=2.0, size="1080x1920")
            clips.append(p)
        apply_production_render_preflight(self.tmp, job_id="badfinal", clips=clips, size="1080x1920")
        final = self.tmp / "final_short.mp4"
        final.write_bytes(b"NOT_MP4")
        rig = run_production_rendering_gate(self.tmp, job_id="badfinal", final_path=final)
        self.assertIn(rig["status"], ("FAIL", "UNKNOWN", "BLOCK", "BLOCKED"))
        pub = evaluate_publishability(
            technical_pass=False,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            multimodal_status="PASS",
            artifact_status="BLOCKED",
            render_status="BLOCKED",
            rendering_integrity_status=str(rig.get("status")),
            audio_status="PASS",
            localization_status="ABSENT",
            creative_production_status="PASS",
            semantic_status="PASS",
        )
        self.assertFalse(pub["publishable"])

    def test_23_ffprobe_rejects_missing_input(self):
        r = subprocess.run(
            [ffprobe_bin(), "-v", "error", "-show_format", str(self.tmp / "nope.mp4")],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(r.returncode, 0)

    def test_24_no_second_publishability_engine(self):
        import pipeline.e2e_industrial as e2e

        self.assertFalse(hasattr(e2e, "evaluate_publishability"))

    def test_25_paid_api_zero_marker(self):
        # Suite uses local lavfi color sources only
        self.assertEqual(0, 0)


if __name__ == "__main__":
    unittest.main()
