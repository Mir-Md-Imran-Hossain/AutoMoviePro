#!/usr/bin/env python3
"""RCP-07 next blocker — diagnose Google TTS credentials then REAL SHORT."""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

EVIDENCE = ROOT / "docs" / "marathon" / "customer_product" / "rcp07_next_blocker_evidence"


def main() -> int:
    from pipeline.api_keys import load_api_bundle
    from pipeline.google_api_gate import close_circuit, circuit_is_open
    from pipeline.quota_backoff import reset_quota_state
    from pipeline.tts_credential_diagnostics import (
        clear_tts_ready,
        diagnose_google_tts_credentials,
        google_tts_is_ready,
        readiness_snapshot,
    )
    from scripts.rcp07_real_certification_run import ensure_channel_en_bn, run_case
    from scripts.c11_real_marathon_runner import C11Runner
    from app.customer_trs_workflow import set_manual_topic

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    close_circuit()
    reset_quota_state(keep_per_key=False)
    clear_tts_ready()

    bundle = load_api_bundle()
    keys = list(bundle.get("google_keys") or [])
    print(f"Diagnosing {len(keys)} Google credentials (no secrets)...", flush=True)
    diag = diagnose_google_tts_credentials(keys, out_dir=EVIDENCE)
    print(
        json.dumps(
            {
                "success_count": diag.get("success_count"),
                "google_tts_ready": diag.get("google_tts_ready"),
                "class_counts": diag.get("class_counts"),
                "same_project_evidence": diag.get("same_project_evidence"),
                "success_slots": diag.get("success_slots"),
            },
            indent=2,
        ),
        flush=True,
    )

    runner = C11Runner()
    baseline = runner.phase0_baseline()
    runner.phase0_clean_state()
    ensure_channel_en_bn(runner)
    runner.phase1_create_run()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    topic = (
        f"How colliding neutron stars forge gold seen by X-ray telescopes "
        f"(RCP07 next-blocker SHORT {stamp})"
    )
    sel = set_manual_topic("c11_marathon_customer", int(runner.channel["id"]), topic)
    if not sel.get("ok"):
        topic = f"RCP07 next-blocker SHORT {stamp}: magnetar flares forging heavy metals"
        sel = set_manual_topic("c11_marathon_customer", int(runner.channel["id"]), topic)
    if not sel.get("ok"):
        (EVIDENCE / "SUMMARY.json").write_text(
            json.dumps({"verdict": "BLOCKED", "reason": "topic_failed", "sel": sel}, indent=2),
            encoding="utf-8",
        )
        return 2
    runner.selected_topic = topic
    runner.selected_niche = str((runner.channel or {}).get("niche") or "space science")
    print(f"TOPIC={topic}", flush=True)
    print(f"circuit_open={circuit_is_open()} google_tts_ready={google_tts_is_ready()}", flush=True)

    short_out = run_case(runner, "RCP07-NEXT-SHORT", "short")
    job_id = short_out.get("job_id")
    (EVIDENCE / f"SHORT_{job_id}.json").write_text(
        json.dumps(short_out, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    # Semantic observer evidence from work dir
    from app.config import DATA_DIR

    work = (
        DATA_DIR / "customer_generation_work" / "c11_marathon_customer" / f"job{job_id}"
        if job_id
        else None
    )
    sem_ev = {}
    if work and work.is_dir():
        for name in (
            "SEMANTIC_COVERAGE_GATE.json",
            "SEMANTIC_GATE.json",
            "LOCALIZATION_GATE.json",
            "ARTIFACT_GATE.json",
            "AUDIO_DESIGN_GATE.json",
            "PUBLISHABILITY_GATE.json",
            "RENDERING_INTEGRITY_GATE.json",
            "DURATION_CONTRACT.json",
        ):
            p = work / name
            if p.is_file():
                try:
                    sem_ev[name] = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    sem_ev[name] = {"_error": "unreadable"}
        # scene local packages
        sl = work / "SCENE_LOCAL"
        pkgs = {}
        if sl.is_dir():
            for sd in sorted(p for p in sl.iterdir() if p.is_dir()):
                pkgs[sd.name] = {
                    lang: {
                        "video": (sd / lang / "video.mp4").is_file(),
                        "bytes": (sd / lang / "video.mp4").stat().st_size
                        if (sd / lang / "video.mp4").is_file()
                        else 0,
                    }
                    for lang in ("en", "bn")
                }
        sem_ev["scene_local"] = pkgs
        tts_diag = work / "TTS_ATTEMPT_DIAGNOSTICS.jsonl"
        if tts_diag.is_file():
            sem_ev["tts_attempt_lines"] = tts_diag.read_text(encoding="utf-8", errors="ignore").count("\n")

    verdict = (short_out.get("evaluation") or {}).get("verdict") or "BLOCKED"
    summary = {
        "contract": "RCP-07-NEXT-BLOCKER-FIX",
        "finished_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "topic": topic,
        "mock_fixture_used": False,
        "deterministic_fixtures": False,
        "google_tts_diagnostics_summary": {
            "success_count": diag.get("success_count"),
            "google_tts_ready": diag.get("google_tts_ready"),
            "class_counts": diag.get("class_counts"),
            "same_project_evidence": diag.get("same_project_evidence"),
            "success_slots": diag.get("success_slots"),
            "readiness_snapshot": readiness_snapshot(),
        },
        "circuit_open_at_start_of_short": False,
        "SHORT": {
            "verdict": verdict,
            "job_id": job_id,
            "status": short_out.get("status"),
            "classification": short_out.get("classification"),
            "evaluation": short_out.get("evaluation"),
            "elapsed_sec": short_out.get("elapsed_sec"),
            "local_path": short_out.get("local_path"),
        },
        "work_gates": {
            k: (v.get("verdict") or v.get("status") if isinstance(v, dict) else v)
            for k, v in sem_ev.items()
            if k.endswith(".json")
        },
        "scene_local": sem_ev.get("scene_local"),
        "overall_verdict": verdict,
    }
    (EVIDENCE / "SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (EVIDENCE / "SEMANTIC_AND_GATES.json").write_text(
        json.dumps(sem_ev, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(json.dumps({"overall": verdict, "job_id": job_id, "tts_ready": google_tts_is_ready()}, indent=2), flush=True)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("RCP07_NEXT_BLOCKER_FATAL", type(exc).__name__, exc, flush=True)
        traceback.print_exc()
        raise
