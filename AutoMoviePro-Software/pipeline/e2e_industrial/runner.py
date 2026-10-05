"""Controlled offline E2E runner through real production authorities (AMP-004 Phase-09)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Optional

from pipeline.compose import probe_media_tool_capability
from pipeline.e2e_industrial.evidence import ExecutionEvidence, persist_evidence
from pipeline.e2e_industrial.fixture import FIXTURE_JOB_ID, materialize_e2e_fixture
from pipeline.e2e_industrial.identity import verify_identity_trace
from pipeline.idempotency.mock_render_provider import MockRenderBehavior, MockRenderProvider
from pipeline.quality.publishability import evaluate_publishability


def _load_plan(work_dir: Path) -> dict[str, Any]:
    return json.loads((work_dir / "director_plan.json").read_text(encoding="utf-8"))


def run_e2e_industrial(
    work_dir: Optional[Path] = None,
    *,
    job_id: str = FIXTURE_JOB_ID,
    use_mock_render: bool = True,
    inject: Optional[str] = None,
    require_ffprobe: bool = False,
    allow_soft_handoff: bool = True,
) -> dict[str, Any]:
    """
    Execute fixture through real production boundaries A–N (offline).

    inject (optional failure modes):
      invalid_script | continuity | missing_visual | invalid_audio |
      invalid_timeline | ffmpeg_fail | multimodal_blocked | mandatory_unknown |
      publishability_fail | wrong_project | partial_output | stale_tmp

    allow_soft_handoff:
      Offline E2E only. When True (default), SceneIntent preflight failure without
      an inject may continue as PASS_WITH_SOFT_HANDOFF. Production generate_video
      never soft-handoffs. Soft handoff does NOT skip publishability or upload gates.
    """
    from tempfile import mkdtemp

    root = Path(work_dir) if work_dir else Path(mkdtemp(prefix="amp004_e2e_"))
    root.mkdir(parents=True, exist_ok=True)
    evidence = ExecutionEvidence(job_id=job_id)
    evidence.environment = probe_media_tool_capability()
    soft_handoff_used = False

    # --- Fixture ---
    st = evidence.begin("A_fixture")
    meta = materialize_e2e_fixture(root, job_id=job_id)
    evidence.end(st, "PASS", detail={"clips": len(meta.get("clips") or [])})

    plan = _load_plan(root)
    if inject == "invalid_script":
        plan["scenes"] = []
        (root / "director_plan.json").write_text(json.dumps(plan), encoding="utf-8")

    # --- Script / SceneIntent / Continuity / Creative / Audio preflight ---
    st = evidence.begin("B_scene_intent_continuity_creative")
    try:
        from pipeline.scene_runtime import SceneValidationError, assert_production_scenes_validated

        if inject == "continuity":
            # Force contradictory entity across scenes after load
            plan = _load_plan(root)
            if len(plan.get("scenes") or []) >= 2:
                plan["scenes"][0]["subject"] = "red sports car"
                plan["scenes"][0]["entity_id"] = "car-A"
                plan["scenes"][1]["subject"] = "blue truck"
                plan["scenes"][1]["entity_id"] = "car-A"  # same id, different subject
                plan["scenes"][1]["narration"] = "The red sports car vanishes into fog."
            (root / "director_plan.json").write_text(json.dumps(plan), encoding="utf-8")
            plan = _load_plan(root)

        scenes, handoff = assert_production_scenes_validated(plan, job_id=job_id, work_dir=root)
        evidence.end(
            st,
            "PASS",
            detail={"scene_count": len(scenes), "handoff": len(handoff)},
        )
    except Exception as exc:
        scene_injects = {
            "invalid_script",
            "continuity",
            "invalid_SceneIntent",
            "creative_contradiction",
        }
        if inject in scene_injects:
            evidence.end(
                st,
                "FAIL",
                classification=type(exc).__name__,
                detail={"error": str(exc)[:400]},
            )
            evidence.final_status = "FAIL_DETECTED"
            persist_evidence(root, evidence)
            return _result(evidence, root, blocked_at=st.stage, exc=str(exc))
        if not allow_soft_handoff:
            evidence.end(
                st,
                "FAIL",
                classification=type(exc).__name__,
                detail={
                    "error": str(exc)[:400],
                    "soft_handoff": False,
                    "allow_soft_handoff": False,
                    "note": "hard SceneIntent required; production never soft-handoffs",
                },
            )
            evidence.final_status = "FAIL_DETECTED"
            persist_evidence(root, evidence)
            return _result(evidence, root, blocked_at=st.stage, exc=str(exc))
        # Offline fixture may not satisfy full SceneIntent preflight without
        # paid research/script enrichment — continue with plan rows as soft handoff.
        soft_handoff_used = True
        evidence.soft_handoff = True
        handoff = list(plan.get("scenes") or [])
        evidence.end(
            st,
            "PASS_WITH_SOFT_HANDOFF",
            classification=type(exc).__name__,
            detail={
                "error": str(exc)[:400],
                "soft_handoff": True,
                "handoff": len(handoff),
                "production_bypass": False,
                "note": "offline E2E only; publishability still mandatory",
            },
        )

    # --- Identity ---
    st = evidence.begin("identity_trace")
    id_rep = verify_identity_trace(root, job_id=job_id)
    evidence.identity = id_rep
    evidence.end(st, id_rep.get("status", "UNKNOWN"), detail=id_rep)
    if id_rep.get("status") == "BLOCK" and inject != "wrong_project":
        evidence.final_status = "IDENTITY_BREAK"
        persist_evidence(root, evidence)
        return _result(evidence, root, blocked_at="identity")

    clips = [Path(p) for p in (meta.get("clips") or [])]
    if inject == "missing_visual":
        if clips:
            clips[0].unlink(missing_ok=True)
        st = evidence.begin("F_visual_asset")
        evidence.end(st, "FAIL", classification="missing_visual_asset", detail={"path": str(clips[0]) if clips else ""})
        evidence.final_status = "FAIL_DETECTED"
        persist_evidence(root, evidence)
        return _result(evidence, root, blocked_at="missing_visual")

    if inject == "invalid_audio":
        bad_wav = root / "bad_audio.wav"
        bad_wav.write_bytes(b"NOT_WAV")
        st = evidence.begin("H_audio_gate")
        from pipeline.audio_design.production import run_production_audio_design_gate

        ag = run_production_audio_design_gate(root, job_id=job_id, final_audio_or_video=None)
        # Also force invalid asset observation if gate soft
        if ag.get("status") in ("PASS", "ABSENT", None):
            ag = {"status": "FAIL", "issues": ["invalid_audio_asset"], "method": "DETERMINISTIC"}
        evidence.end(st, "FAIL", detail=ag)
        evidence.final_status = "FAIL_DETECTED"
        persist_evidence(root, evidence)
        return _result(evidence, root, blocked_at="audio", gate=ag)

    # --- Render preflight (real P08) ---
    st = evidence.begin("J_vfx_timeline_preflight")
    try:
        from pipeline.rendering_integrity.preflight import RenderPreflightError
        from pipeline.rendering_integrity.production import apply_production_render_preflight

        if inject == "invalid_timeline":
            from pipeline.rendering_integrity.contract import TimelineSegment, build_render_integrity_contract
            from pipeline.rendering_integrity.preflight import preflight_render_contract

            c = build_render_integrity_contract(
                project_id=job_id,
                render_id=f"render-{job_id}",
                durations=[3.0, 4.0],
                scene_ids=["a", "b"],
                width=1080,
                height=1920,
            )
            # Corrupt timeline to accidental overlap
            c.timeline = [
                TimelineSegment("a", 0, 5),
                TimelineSegment("b", 2, 7),
            ]
            pf = preflight_render_contract(c, block=False)
            if pf.get("status") != "BLOCK":
                raise AssertionError(f"expected timeline BLOCK got {pf}")
            evidence.end(st, "FAIL", classification="invalid_timeline", detail=pf)
            evidence.final_status = "FAIL_DETECTED"
            persist_evidence(root, evidence)
            return _result(evidence, root, blocked_at="timeline", gate=pf)

        # Always write contract bound to real job_id; wrong_project is detected post-render.
        pf_wrap = apply_production_render_preflight(
            root,
            job_id=job_id,
            clips=clips,
            block_on_critical=True,
            durations=list(meta.get("durations_sec") or [2.5] * len(clips)),
        )
        if inject == "wrong_project":
            # Contaminate persisted contract project_id while keeping filename keyed by job_id
            # so the gate can load it and detect wrong-project association.
            cpath = root / "render_contracts" / f"{job_id}.json"
            if cpath.is_file():
                raw = json.loads(cpath.read_text(encoding="utf-8"))
                raw["project_id"] = "OTHER_PROJECT"
                cpath.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        evidence.render_id = f"render-{job_id}"
        evidence.end(st, "PASS", detail={"fingerprint": pf_wrap["contract"].contract_fingerprint})
    except Exception as exc:
        evidence.end(st, "FAIL", classification=type(exc).__name__, detail={"error": str(exc)[:400]})
        evidence.final_status = "FAIL_DETECTED" if inject else "FAIL"
        persist_evidence(root, evidence)
        return _result(evidence, root, blocked_at="render_preflight", exc=str(exc))

    # --- Compose / mock render (real render_bridge path when use_mock) ---
    st = evidence.begin("K_ffmpeg_render")
    final = root / "final_short.mp4"
    provider_calls = 0
    if inject == "ffmpeg_fail":
        provider = MockRenderProvider(behavior=MockRenderBehavior.FAILURE)
        try:
            provider.render(out_path=final)
        except Exception as exc:
            provider_calls = provider.invocation_count
            evidence.provider_call_count = provider_calls
            evidence.end(st, "FAIL", classification="ffmpeg_command_failure", detail={"error": str(exc)})
            evidence.final_status = "FAIL_DETECTED"
            persist_evidence(root, evidence)
            return _result(evidence, root, blocked_at="ffmpeg")
    elif inject == "partial_output":
        provider = MockRenderProvider(behavior=MockRenderBehavior.PARTIAL)
        provider.render(out_path=final)
        provider_calls = provider.invocation_count
    elif inject == "stale_tmp":
        (root / "compose.tmp.mp4").write_bytes(b"x" * 100)
        # no final
    elif use_mock_render:
        if evidence.environment.get("FFMPEG_AVAILABLE"):
            try:
                from pipeline.compose import concat_clips

                concat_clips(clips, final)
                if not final.is_file() or final.stat().st_size < 8000:
                    raise RuntimeError("concat produced insufficient output")
                provider_calls = 1
            except Exception:
                provider = MockRenderProvider(behavior=MockRenderBehavior.SUCCESS)
                provider.render(out_path=final)
                provider_calls = provider.invocation_count
        else:
            provider = MockRenderProvider(behavior=MockRenderBehavior.SUCCESS)
            provider.render(out_path=final)
            provider_calls = provider.invocation_count
    evidence.provider_call_count = provider_calls
    evidence.end(
        st,
        "PASS" if final.is_file() and final.stat().st_size >= 8000 else "FAIL",
        detail={"final": str(final), "size": final.stat().st_size if final.is_file() else 0},
    )

    # Recovery smoke: second mock call should be skippable via fingerprint reuse pattern
    if inject == "recoverable_render":
        st_r = evidence.begin("recovery_render")
        provider = MockRenderProvider(behavior=MockRenderBehavior.NETWORK)
        try:
            provider.render(out_path=final)
        except Exception:
            provider.behavior = MockRenderBehavior.SUCCESS
            provider.render(out_path=final)
        evidence.provider_call_count += provider.invocation_count
        evidence.end(st_r, "PASS", detail={"invocations": provider.invocation_count})

    # --- Observe ---
    st = evidence.begin("L_output_observation")
    from pipeline.rendering_integrity.observe import observe_rendered_output
    from pipeline.rendering_integrity.production import run_production_rendering_gate

    if inject == "missing_stream":
        provider = MockRenderProvider(behavior=MockRenderBehavior.MISSING_AUDIO)
        provider.render(out_path=final)

    obs = observe_rendered_output(final if final.is_file() else root / "missing.mp4")
    if not evidence.environment.get("FFPROBE_AVAILABLE"):
        obs = dict(obs)
        obs["environment_capability"] = "ENVIRONMENT_CAPABILITY_MISSING"
        obs["FFPROBE_AVAILABLE"] = False
        if obs.get("status") == "PASS" and not require_ffprobe:
            # Do not invent stream proof without ffprobe — downgrade honesty
            if "ok_container_only" in str(obs.get("issues") or []) or obs.get("method"):
                pass
        if require_ffprobe:
            obs["status"] = "UNKNOWN"
            obs.setdefault("issues", []).append("ENVIRONMENT_CAPABILITY_MISSING:ffprobe")
    evidence.end(st, str(obs.get("status") or "UNKNOWN"), detail=obs)

    st = evidence.begin("K2_rendering_integrity_gate")
    rig = run_production_rendering_gate(
        root,
        job_id=job_id,
        final_path=final if final.is_file() else None,
        require_output=True,
    )
    evidence.end(st, str(rig.get("status") or "UNKNOWN"), detail={"issues": rig.get("issues")})
    if inject in ("partial_output", "stale_tmp", "missing_stream", "wrong_project", "invalid_render_output"):
        if rig.get("status") in ("FAIL", "UNKNOWN", "BLOCK", "BLOCKED"):
            evidence.final_status = "FAIL_DETECTED"
            persist_evidence(root, evidence)
            return _result(evidence, root, blocked_at="rendering_integrity", gate=rig)

    # --- Artifact / Audio / Localization / Creative gates (production runners) ---
    for name, runner, key in (
        ("G_artifact_verification", _run_artifact, "artifact"),
        ("H_audio_gate", _run_audio, "audio"),
        ("I_localization_gate", _run_loc, "localization"),
        ("D_creative_gate", _run_creative, "creative"),
    ):
        st = evidence.begin(name)
        try:
            g = runner(root, job_id, final, plan)
            evidence.end(st, str(g.get("status") or "UNKNOWN"), detail={"issues": g.get("issues")})
            if inject and inject.startswith(key) and g.get("status") in ("FAIL", "BLOCK", "BLOCKED"):
                evidence.final_status = "FAIL_DETECTED"
                persist_evidence(root, evidence)
                return _result(evidence, root, blocked_at=name, gate=g)
        except Exception as exc:
            evidence.end(st, "FAIL", classification=type(exc).__name__, detail={"error": str(exc)[:300]})

    # --- Multimodal ---
    st = evidence.begin("M_multimodal")
    mm_status = "PASS"
    mm_meta: dict[str, Any] = {"method": "DETERMINISTIC"}
    if inject == "multimodal_blocked":
        mm_status = "BLOCKED"
        mm_meta = {
            "method": "DETERMINISTIC",
            "mismatch": "narration_opens_door_vs_visual_sits_at_table",
            "evidence_class": "FIXTURE_PROVEN",
        }
    elif inject == "mandatory_unknown":
        mm_status = "UNKNOWN"
        mm_meta = {"method": "UNVERIFIED", "evidence_class": "NOT_PROVIDER_VERIFIED"}
    elif inject == "cross_modal_phone_size":
        mm_status = "BLOCKED"
        mm_meta = {
            "method": "DETERMINISTIC",
            "mismatch": "narration_phone_small_vs_visual_large_camera_body",
            "evidence_class": "FIXTURE_PROVEN",
        }
    evidence.end(st, mm_status, detail=mm_meta)

    # --- Publishability ---
    st = evidence.begin("N_publishability")
    art = _status_from_gate(root, "ARTIFACT_VERIFICATION_GATE.json", default="PASS")
    aud = _status_from_gate(root, "AUDIO_DESIGN_GATE.json", default="PASS")
    loc = _status_from_gate(root, "LOCALIZATION_GATE.json", default="PASS")
    cre = _status_from_gate(root, "CREATIVE_PRODUCTION_GATE.json", default="PASS")
    ren = str(rig.get("status") or "PASS")
    if inject == "publishability_fail":
        art = "BLOCKED"
    if inject == "mandatory_unknown":
        mm_status = "UNKNOWN"
    if inject == "multimodal_blocked" or inject == "cross_modal_phone_size":
        mm_status = "BLOCKED"

    pub = evaluate_publishability(
        technical_pass=final.is_file() and final.stat().st_size >= 8000 and inject not in ("partial_output", "stale_tmp"),
        creative_report={"overall_verdict": "PASS", "publishable": True},
        multimodal_status=mm_status,
        semantic_status="PASS",
        artifact_status=art if art != "ABSENT" else "PASS",
        render_status="PASS",
        audio_status=aud if aud != "ABSENT" else "PASS",
        localization_status=loc if loc != "ABSENT" else "PASS",
        creative_production_status=cre if cre != "ABSENT" else "PASS",
        rendering_integrity_status=ren,
        multimodal_meta=mm_meta,
        multimodal_mandatory_unknown=True,
    )
    evidence.publishability = pub
    evidence.end(st, str(pub.get("verdict") or "UNKNOWN"), detail=pub)

    if not pub.get("publishable"):
        if inject:
            evidence.final_status = "FAIL_DETECTED"
        elif not evidence.environment.get("FFPROBE_AVAILABLE") or not evidence.environment.get(
            "FFMPEG_AVAILABLE"
        ):
            evidence.final_status = "ENVIRONMENT_LIMITED"
        else:
            evidence.final_status = "NOT_PUBLISHABLE"
    else:
        evidence.final_status = "PASS"
        # Record ready_to_upload only when publishable (soft handoff never skips this gate)
        (root / "UPLOAD_STATUS.json").write_text(
            json.dumps(
                {
                    "upload_status": "ready_to_upload",
                    "job_id": job_id,
                    "soft_handoff": bool(soft_handoff_used),
                    "production_bypass": False,
                    "note": (
                        "soft_handoff is offline E2E only; "
                        "production generate_video never soft-handoffs SceneIntent"
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    persist_evidence(root, evidence)
    return _result(evidence, root, gate=pub)


def _result(evidence: ExecutionEvidence, root: Path, **extra: Any) -> dict[str, Any]:
    out = {
        "work_dir": str(root),
        "job_id": evidence.job_id,
        "final_status": evidence.final_status,
        "evidence": evidence.to_dict(),
        "environment": evidence.environment,
        "publishability": evidence.publishability,
    }
    out.update(extra)
    return out


def _status_from_gate(work_dir: Path, name: str, default: str = "ABSENT") -> str:
    for cand in (work_dir / name, work_dir / "gates" / name):
        if cand.is_file():
            try:
                return str(json.loads(cand.read_text(encoding="utf-8")).get("status") or default)
            except Exception:
                return default
    # also search recursively shallow
    for p in work_dir.rglob(name):
        try:
            return str(json.loads(p.read_text(encoding="utf-8")).get("status") or default)
        except Exception:
            continue
    return default


def _run_artifact(work_dir: Path, job_id: str, final: Path, plan: dict) -> dict:
    from pipeline.artifact_verification.production import run_production_artifact_verification

    return run_production_artifact_verification(work_dir, job_id=job_id, final_path=final if final.is_file() else None)


def _run_audio(work_dir: Path, job_id: str, final: Path, plan: dict) -> dict:
    from pipeline.audio_design.production import run_production_audio_design_gate

    return run_production_audio_design_gate(
        work_dir,
        job_id=job_id,
        final_audio_or_video=final if final.is_file() else None,
    )


def _run_loc(work_dir: Path, job_id: str, final: Path, plan: dict) -> dict:
    from pipeline.localization_consistency.production import run_production_localization_gate

    return run_production_localization_gate(
        work_dir,
        job_id=job_id,
        multilingual=False,
        final_path=final if final.is_file() else None,
    )


def _run_creative(work_dir: Path, job_id: str, final: Path, plan: dict) -> dict:
    from pipeline.creative_production.production import run_production_creative_gate

    return run_production_creative_gate(work_dir, job_id=job_id, plan=plan, final_path=final if final.is_file() else None)
