#!/usr/bin/env python3
"""RCP-07 — Real Production Certification driver (orchestration only).

Reuses existing customer authorities + C11Runner helpers.
No production code changes. No MOCK/fixture generation path.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"_error": "unreadable", "path": str(path)}


def _probe(path: str) -> Dict[str, Any]:
    p = Path(path) if path else None
    if not p or not p.is_file() or p.stat().st_size < 1000:
        return {"exists": False, "path": path}
    try:
        from pipeline.compose import ffprobe_duration
        from pipeline.idempotency.render_validation import probe_render_metadata

        meta = probe_render_metadata(p)
        return {
            "exists": True,
            "path": str(p),
            "file_size": p.stat().st_size,
            "duration": meta.get("duration_sec") or ffprobe_duration(p),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "has_audio": meta.get("has_audio"),
            "codec": meta.get("codec"),
        }
    except Exception as exc:
        return {"exists": True, "path": str(p), "file_size": p.stat().st_size, "probe_error": str(exc)[:200]}


def collect_work_evidence(work: Path) -> Dict[str, Any]:
    gates = {
        "DURATION_CONTRACT": _read_json(work / "DURATION_CONTRACT.json"),
        "SEMANTIC_COVERAGE_GATE": _read_json(work / "SEMANTIC_COVERAGE_GATE.json"),
        "SEMANTIC_GATE": _read_json(work / "SEMANTIC_GATE.json"),
        "ARTIFACT_GATE": _read_json(work / "ARTIFACT_GATE.json"),
        "AUDIO_DESIGN_GATE": _read_json(work / "AUDIO_DESIGN_GATE.json"),
        "LOCALIZATION_GATE": _read_json(work / "LOCALIZATION_GATE.json"),
        "RENDERING_INTEGRITY_GATE": _read_json(work / "RENDERING_INTEGRITY_GATE.json"),
        "CREATIVE_PRODUCTION_GATE": _read_json(work / "CREATIVE_PRODUCTION_GATE.json"),
        "PUBLISHABILITY_GATE": _read_json(work / "PUBLISHABILITY_GATE.json"),
        "CONTINUITY_STATE": _read_json(work / "CONTINUITY_STATE.json"),
        "VOICE_IDENTITY": None,
    }
    # Voice identity may live on plan / audio gate / scenes
    for cand in (
        work / "VOICE_IDENTITY.json",
        work / "director_plan.json",
        work / "PRODUCTION_PLAN_SNAPSHOT.json",
        work / "immutable_execution_snapshot.json",
    ):
        data = _read_json(cand)
        if not data:
            continue
        if data.get("voice_identity"):
            gates["VOICE_IDENTITY"] = data.get("voice_identity")
            break
        if (data.get("plan") or {}).get("voice_identity"):
            gates["VOICE_IDENTITY"] = (data.get("plan") or {}).get("voice_identity")
            break
        if data.get("audio_plan") and isinstance(data["audio_plan"], dict) and data["audio_plan"].get("voice_identity"):
            gates["VOICE_IDENTITY"] = data["audio_plan"]["voice_identity"]
            break

    # Per-scene / beat evidence
    scenes: List[Dict[str, Any]] = []
    director = _read_json(work / "director_plan.json") or {}
    plan_scenes = director.get("scenes") or []
    clip_hashes: Dict[str, List[str]] = {}
    import hashlib

    for i, sc in enumerate(plan_scenes if isinstance(plan_scenes, list) else []):
        if not isinstance(sc, dict):
            continue
        clip = None
        for pat in (f"scene_{i:02d}.mp4", f"clip_{i:02d}.mp4", f"scene{i}.mp4"):
            c = work / pat
            if c.is_file():
                clip = c
                break
        # glob fallback
        if clip is None:
            matches = sorted(work.glob(f"*scene*{i:02d}*.mp4")) + sorted(work.glob(f"*_{i:02d}.mp4"))
            clip = matches[0] if matches else None
        audio = None
        for ext in (".m4a", ".wav", ".mp3"):
            a = work / f"narration_{i:02d}{ext}"
            if a.is_file():
                audio = a
                break
        h = None
        if clip and clip.is_file():
            h = hashlib.sha256(clip.read_bytes()[: 256 * 1024]).hexdigest()[:16]
            clip_hashes.setdefault(h, []).append(f"scene_{i:02d}")
        sem = _read_json(work / f"SEMANTIC_OBS_{i:02d}.json") or _read_json(work / f"semantic_scene_{i:02d}.json")
        repair = _read_json(work / f"REPAIR_SCENE_{i:02d}.json") or _read_json(work / f"repair_{i:02d}.json")
        ap = sc.get("audio_plan") if isinstance(sc.get("audio_plan"), dict) else {}
        scenes.append(
            {
                "index": i,
                "dialogue_id": sc.get("dialogue_id") or sc.get("c05s_dialogue_id"),
                "beat_id": sc.get("beat_id") or sc.get("c05s_beat_id"),
                "scene_id": sc.get("canonical_scene_id") or sc.get("scene_id") or i,
                "duration_target": sc.get("duration_target_sec") or sc.get("duration"),
                "narration_preview": str(sc.get("narration") or "")[:120],
                "visual_asset": str(clip) if clip else None,
                "audio_asset": str(audio) if audio else None,
                "voice_identity": (sc.get("voice_identity") or {}).get("voice_identity_id")
                if isinstance(sc.get("voice_identity"), dict)
                else (ap.get("metadata") or {}).get("voice_identity_id") or ap.get("voice_profile") or sc.get("voice_profile"),
                "semantic_result": sem,
                "repair_result": repair,
                "clip_hash16": h,
                "camera": sc.get("camera") or (sc.get("continuity_refs") or {}).get("camera_language"),
                "lighting": sc.get("lighting") or (sc.get("continuity_refs") or {}).get("lighting"),
                "location": sc.get("location"),
            }
        )

    reuse = {h: ids for h, ids in clip_hashes.items() if len(ids) > 1}

    # Localization packages
    loc_root = work / "localized" if (work / "localized").is_dir() else work / "languages"
    loc_pkgs: Dict[str, Any] = {}
    if loc_root.is_dir():
        for lang_dir in sorted(p for p in loc_root.iterdir() if p.is_dir()):
            narr = lang_dir / "narration.txt"
            vid = lang_dir / "video.mp4"
            srt = lang_dir / "subtitles.srt"
            text = narr.read_text(encoding="utf-8")[:200] if narr.is_file() else ""
            loc_pkgs[lang_dir.name] = {
                "narration_preview": text,
                "video": _probe(str(vid)) if vid.is_file() else {"exists": False},
                "srt_exists": srt.is_file(),
            }

    # Usage / cost
    usage = _read_json(work / "USAGE_EVENTS.json") or _read_json(work / "idempotency" / "usage.json")
    cost = _read_json(work / "COST_SUMMARY.json") or _read_json(work / "provider_usage.json")

    finals = []
    for name in ("final.mp4", "master.mp4", "output.mp4", "composed.mp4"):
        if (work / name).is_file():
            finals.append(_probe(str(work / name)))
    if not finals:
        for p in sorted(work.glob("*.mp4")):
            if p.stat().st_size > 100_000 and "scene" not in p.name.lower():
                finals.append(_probe(str(p)))
                break

    return {
        "work_dir": str(work),
        "gates": gates,
        "scenes": scenes,
        "clip_reuse_hashes": reuse,
        "localization_packages": loc_pkgs,
        "usage": usage,
        "cost": cost,
        "final_artifacts": finals,
        "collected_at": _now(),
    }


def evaluate_run(evidence: Dict[str, Any], *, video_type: str, contract: Dict[str, Any]) -> Dict[str, Any]:
    """Honest certification verdict — UNKNOWN/fixture never PASS."""
    blocks: List[str] = []
    warnings: List[str] = []
    gates = evidence.get("gates") or {}

    def gstatus(key: str) -> str:
        g = gates.get(key) or {}
        if not g:
            return "ABSENT"
        return str(g.get("verdict") or g.get("status") or "UNKNOWN").upper()

    # Duration
    dc = gates.get("DURATION_CONTRACT") or contract
    target = int((dc or {}).get("target_seconds") or contract.get("target_seconds") or 0)
    max_s = int((dc or {}).get("max_seconds") or contract.get("max_seconds") or 0)
    if video_type.lower().startswith("short"):
        if target != 60 or max_s != 120:
            blocks.append(f"DURATION_CONTRACT_MISMATCH:got_target={target}_max={max_s}_want_60_120")
    else:
        if target != 180 or max_s != 300:
            blocks.append(f"DURATION_CONTRACT_MISMATCH:got_target={target}_max={max_s}_want_180_300")

    finals = evidence.get("final_artifacts") or []
    if not finals or not finals[0].get("exists"):
        blocks.append("FINAL_ARTIFACT_MISSING")
    else:
        dur = float(finals[0].get("duration") or 0)
        if max_s and dur > max_s + 2.5:
            blocks.append(f"DURATION_OVER_MAX:{dur}>{max_s}")
        if target and dur + 15 < target * 0.5:
            warnings.append(f"DURATION_FAR_BELOW_TARGET:{dur}_vs_{target}")

    # Semantic
    sem = gstatus("SEMANTIC_COVERAGE_GATE")
    if sem in ("ABSENT",):
        # try alias
        sem = gstatus("SEMANTIC_GATE")
    if sem == "UNKNOWN":
        blocks.append("SEMANTIC_UNKNOWN_BLOCKS_CERT")
    elif sem == "FAIL":
        blocks.append("SEMANTIC_FAIL")
    elif sem != "PASS":
        blocks.append(f"SEMANTIC_NOT_PASS:{sem}")

    for key, label in (
        ("ARTIFACT_GATE", "ARTIFACT"),
        ("AUDIO_DESIGN_GATE", "AUDIO"),
        ("RENDERING_INTEGRITY_GATE", "RENDER"),
        ("PUBLISHABILITY_GATE", "PUBLISHABILITY"),
    ):
        st = gstatus(key)
        if st == "UNKNOWN":
            blocks.append(f"{label}_UNKNOWN_BLOCKS_CERT")
        elif st in ("FAIL", "BLOCKED", "ABSENT"):
            # localization may be ABSENT if en-only — handled below
            if label == "PUBLISHABILITY":
                pub = gates.get("PUBLISHABILITY_GATE") or {}
                if not pub.get("publishable") and st != "PUBLISHABLE":
                    blocks.append(f"{label}_NOT_PASS:{st}")
            elif st != "PASS" and not (st == "PUBLISHABLE"):
                blocks.append(f"{label}_NOT_PASS:{st}")

    pub = gates.get("PUBLISHABILITY_GATE") or {}
    if pub:
        pv = str(pub.get("verdict") or "").upper()
        if pub.get("publishable") is True or pv == "PUBLISHABLE":
            pass
        else:
            if "PUBLISHABILITY_NOT_PASS" not in " ".join(blocks):
                blocks.append(f"PUBLISHABILITY_NOT_PASS:{pv or pub.get('reason')}")

    # Localization: if packages present, require gate not UNKNOWN; if configured en+bn expect both
    loc_pkgs = evidence.get("localization_packages") or {}
    loc_st = gstatus("LOCALIZATION_GATE")
    if loc_pkgs:
        if loc_st == "UNKNOWN":
            blocks.append("LOCALIZATION_UNKNOWN_BLOCKS_CERT")
        elif loc_st in ("FAIL", "BLOCKED"):
            blocks.append(f"LOCALIZATION_NOT_PASS:{loc_st}")
        # language distinctness
        texts = {k: str(v.get("narration_preview") or "") for k, v in loc_pkgs.items()}
        if "en" in texts and "bn" in texts:
            if texts["en"] and texts["bn"] and texts["en"].strip() == texts["bn"].strip():
                blocks.append("LOCALIZATION_EN_BN_IDENTICAL_TEXT")
    elif loc_st not in ("ABSENT", "UNKNOWN", ""):
        warnings.append(f"localization_gate={loc_st}_but_no_packages_found")

    # Voice
    vi = gates.get("VOICE_IDENTITY")
    scene_voices = {str(s.get("voice_identity") or "") for s in (evidence.get("scenes") or []) if s.get("voice_identity")}
    if not vi and not scene_voices:
        blocks.append("VOICE_IDENTITY_MISSING")
    elif len(scene_voices) > 1:
        blocks.append(f"VOICE_IDENTITY_MISMATCH:{sorted(scene_voices)}")

    # Coverage: every scene should have visual+audio
    scenes = evidence.get("scenes") or []
    if not scenes:
        blocks.append("NO_SCENE_EVIDENCE")
    for s in scenes:
        if not s.get("visual_asset"):
            blocks.append(f"MISSING_VISUAL:scene_{s.get('index')}")
        if not s.get("audio_asset"):
            blocks.append(f"MISSING_AUDIO:scene_{s.get('index')}")

    reuse = evidence.get("clip_reuse_hashes") or {}
    if reuse:
        # Same hash across many scenes is suspicious for dialogue-driven visuals
        for h, ids in reuse.items():
            if len(ids) >= 3:
                blocks.append(f"CLIP_REUSE_SUSPICIOUS:{h}:{','.join(ids)}")
            else:
                warnings.append(f"clip_hash_shared:{h}:{','.join(ids)}")

    # Honest: no false PASS
    if any("UNKNOWN" in b for b in blocks):
        verdict = "BLOCKED"
    elif blocks:
        verdict = "BLOCKED"
    elif warnings:
        verdict = "PASS_WITH_LIMITATION"
    else:
        verdict = "PASS"

    return {
        "verdict": verdict,
        "blocks": list(dict.fromkeys(blocks)),
        "warnings": list(dict.fromkeys(warnings)),
        "target_seconds": target,
        "max_seconds": max_s,
        "final_duration": (finals[0].get("duration") if finals else None),
        "scene_count": len(scenes),
    }


def ensure_channel_en_bn(runner) -> Dict[str, Any]:
    """Prefer channel with en+bn; stamp languages for multilingual check."""
    ch = runner.channel or {}
    # Prefer id 4 if owned
    preferred = runner.store.get_channel(4) or {}
    if str(preferred.get("owner_login_id") or "") == "c11_marathon_customer":
        ch = preferred
    langs = preferred.get("languages_json") if preferred else ch.get("languages_json")
    try:
        parsed = json.loads(langs) if isinstance(langs, str) else (langs or ["en", "bn"])
    except Exception:
        parsed = ["en", "bn"]
    if "en" not in parsed:
        parsed = ["en"] + list(parsed)
    if "bn" not in parsed:
        parsed = list(parsed) + ["bn"]
    runner.store.upsert_channel(
        {
            "id": int(ch["id"]),
            "youtube_name": ch.get("youtube_name") or "C11 Marathon Channel",
            "niche": ch.get("niche") or "space science",
            "niche_id": ch.get("niche_id"),
            "short_upload_time": ch.get("short_upload_time") or "12:00",
            "long_upload_time": ch.get("long_upload_time") or "18:00",
            "lang_code": ch.get("lang_code") or "en",
            "languages_json": json.dumps(["en", "bn"]),
            "owner_login_id": "c11_marathon_customer",
            "enabled": 1,
        }
    )
    runner.channel = runner.store.get_channel(int(ch["id"]))
    return {"channel_id": int(runner.channel["id"]), "languages": ["en", "bn"]}


def run_case(runner, case_id: str, video_type: str) -> Dict[str, Any]:
    from pipeline.duration_budget import resolve_duration_contract

    contract = resolve_duration_contract(video_type)
    print(f"\n=== RCP-07 {case_id} ({video_type}) contract={contract} ===", flush=True)
    t0 = time.monotonic()
    gen = runner._generate_case(case_id, video_type)
    elapsed = time.monotonic() - t0
    job_id = None
    # Extract job id from case result / timeline
    for key in ("job_id",):
        if gen.get(key):
            job_id = gen.get(key)
    # case_results structure may nest
    cr = runner.case_results.get(case_id) or gen
    job_id = job_id or cr.get("job_id")
    if not job_id:
        # scan work dirs by mtime
        from app.config import DATA_DIR

        base = DATA_DIR / "customer_generation_work" / "c11_marathon_customer"
        if base.is_dir():
            jobs = sorted(base.glob("job*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if jobs:
                job_id = int(str(jobs[0].name).replace("job", "") or 0) or None

    from app.config import DATA_DIR

    work = DATA_DIR / "customer_generation_work" / "c11_marathon_customer" / f"job{job_id}" if job_id else None
    evidence = collect_work_evidence(work) if work and work.is_dir() else {"work_dir": None, "gates": {}, "scenes": [], "error": "work_dir_missing"}
    # Classify MOCK/fixture → never PASS
    classification = str(cr.get("classification") or gen.get("classification") or "")
    if classification in ("SYNTHETIC", "MOCK") or "fixture" in classification.lower():
        eval_out = {
            "verdict": "BLOCKED",
            "blocks": [f"MOCK_OR_FIXTURE_NOT_ALLOWED:{classification}"],
            "warnings": [],
            "target_seconds": contract["target_seconds"],
            "max_seconds": contract["max_seconds"],
        }
    elif not cr.get("ok") and str(cr.get("status") or "").upper() in ("FAILED", "BLOCKED"):
        # Still evaluate evidence honestly
        eval_out = evaluate_run(evidence, video_type=video_type, contract=contract)
        if eval_out["verdict"] == "PASS":
            eval_out["verdict"] = "BLOCKED"
            eval_out["blocks"].append(f"GENERATION_STATUS:{cr.get('status')}")
    else:
        eval_out = evaluate_run(evidence, video_type=video_type, contract=contract)

    # Provider failures must not PASS
    if any(x in str(cr) for x in ("PROVIDER_NOT_CONFIGURED", "quota", "billing", "429", "insufficient")):
        eval_out["verdict"] = "BLOCKED"
        eval_out["blocks"].append("PROVIDER_UNAVAILABLE_OR_BILLING")

    out = {
        "case_id": case_id,
        "video_type": video_type,
        "contract": contract,
        "elapsed_sec": round(elapsed, 1),
        "job_id": job_id,
        "generation_result": {
            k: cr.get(k)
            for k in (
                "status",
                "classification",
                "ok",
                "error",
                "upload_status",
                "customer_state",
                "local_path",
                "job_id",
                "approval_status",
                "publish_status",
            )
        },
        "local_path": cr.get("local_path") or ((evidence.get("final_artifacts") or [{}])[0].get("path")),
        "ok": cr.get("status") not in ("FAILED",),
        "status": cr.get("status"),
        "classification": cr.get("classification"),
        "job_id": job_id or cr.get("job_id"),
        "evidence": evidence,
        "evaluation": eval_out,
        "finished_at": _now(),
    }
    # Persist per-case evidence
    out_dir = ROOT / "docs" / "marathon" / "customer_product" / "rcp07_evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{case_id}_{job_id or 'noj'}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"{case_id} verdict={eval_out['verdict']} job={job_id} elapsed={elapsed:.0f}s evidence={path}", flush=True)
    return out


def main() -> int:
    from scripts.c11_real_marathon_runner import C11Runner

    runner = C11Runner()
    print("RCP-07 Phase0 baseline...", flush=True)
    baseline = runner.phase0_baseline()
    agnes = int((baseline.get("provider_inventory") or {}).get("agnes_keys") or 0)
    google = int((baseline.get("provider_inventory") or {}).get("google_keys") or 0)
    print(f"providers google={google} agnes={agnes}", flush=True)
    if agnes <= 0:
        report = {
            "verdict_overall": "BLOCKED",
            "reason": "PROVIDER_NOT_CONFIGURED:AGNES — cannot run live generate_video",
            "short": {"evaluation": {"verdict": "BLOCKED", "blocks": ["PROVIDER_NOT_CONFIGURED:AGNES"]}},
            "long": {"evaluation": {"verdict": "BLOCKED", "blocks": ["PROVIDER_NOT_CONFIGURED:AGNES"]}},
            "baseline": baseline,
            "finished_at": _now(),
        }
        _write_report_stub(report)
        return 2

    print("RCP-07 clean channel...", flush=True)
    runner.phase0_clean_state()
    ensure_channel_en_bn(runner)
    print("RCP-07 create run session...", flush=True)
    runner.phase1_create_run()
    print("RCP-07 unique topic (avoid duplicate-blocked JWST placeholder)...", flush=True)
    from app.customer_trs_workflow import set_manual_topic

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Do NOT append niche name — BUILD-04G duplicate gate falsely matches trailing "space science"
    topic = (
        f"How neutron-star mergers forge gold and platinum visible to X-ray telescopes "
        f"(RCP07 live cert {stamp})"
    )
    sel_out = set_manual_topic("c11_marathon_customer", int(runner.channel["id"]), topic)
    if not sel_out.get("ok"):
        # One more attempt with maximally unique wording
        topic = f"RCP07 live certification topic {stamp}: tidal disruption flares near supermassive black holes"
        sel_out = set_manual_topic("c11_marathon_customer", int(runner.channel["id"]), topic)
    if not sel_out.get("ok"):
        report = {
            "verdict_overall": "BLOCKED",
            "reason": "topic_selection_failed",
            "sel_out": sel_out,
            "finished_at": _now(),
        }
        _write_report_stub(report)
        return 2
    runner.selected_topic = topic
    runner.selected_niche = str((runner.channel or {}).get("niche") or "space science")
    niche = {"ok": True, "topic": topic, "selection_path": "RCP07_MANUAL_UNIQUE", "sel_out": sel_out}

    print(f"TOPIC={runner.selected_topic}", flush=True)

    short_out = run_case(runner, "RCP07-SHORT", "short")
    long_out = run_case(runner, "RCP07-LONG", "long")

    sv = short_out["evaluation"]["verdict"]
    lv = long_out["evaluation"]["verdict"]
    if sv == "PASS" and lv == "PASS":
        overall = "PASS"
    elif "BLOCKED" in (sv, lv):
        overall = "BLOCKED"
    else:
        overall = "PASS_WITH_LIMITATION"

    summary = {
        "contract": "RCP-07",
        "started_at": runner.start_iso,
        "finished_at": _now(),
        "login": "c11_marathon_customer",
        "channel_id": int((runner.channel or {}).get("id") or 0),
        "topic": runner.selected_topic,
        "baseline_providers": baseline.get("provider_inventory"),
        "mock_fixture_used": False,
        "SHORT": {
            "verdict": sv,
            "job_id": short_out.get("job_id"),
            "local_path": short_out.get("local_path"),
            "evaluation": short_out.get("evaluation"),
            "elapsed_sec": short_out.get("elapsed_sec"),
            "evidence_file": f"rcp07_evidence/RCP07-SHORT_{short_out.get('job_id')}.json",
        },
        "LONG": {
            "verdict": lv,
            "job_id": long_out.get("job_id"),
            "local_path": long_out.get("local_path"),
            "evaluation": long_out.get("evaluation"),
            "elapsed_sec": long_out.get("elapsed_sec"),
            "evidence_file": f"rcp07_evidence/RCP07-LONG_{long_out.get('job_id')}.json",
        },
        "overall_verdict": overall,
        "classification_notes": list(runner.classification_notes),
        "paid_metrics": dict(runner.metrics),
    }
    summary_path = ROOT / "docs" / "marathon" / "customer_product" / "rcp07_evidence" / "SUMMARY.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    # Also stash full short/long beside summary for report authoring
    (summary_path.parent / "SHORT_FULL.json").write_text(
        json.dumps(short_out, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (summary_path.parent / "LONG_FULL.json").write_text(
        json.dumps(long_out, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(json.dumps({"overall": overall, "SHORT": sv, "LONG": lv, "summary": str(summary_path)}, indent=2), flush=True)
    return 0 if overall != "BLOCKED" else 1


def _write_report_stub(report: Dict[str, Any]) -> None:
    out = ROOT / "docs" / "marathon" / "customer_product" / "rcp07_evidence" / "SUMMARY.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("RCP07_FATAL", type(exc).__name__, exc, flush=True)
        traceback.print_exc()
        raise
