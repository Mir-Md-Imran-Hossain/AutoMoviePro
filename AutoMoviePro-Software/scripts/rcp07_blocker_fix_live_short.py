#!/usr/bin/env python3
"""RCP-07 blocker-fix — one REAL SHORT live production (no MOCK/fixtures).

Reuses rcp07_real_certification_run helpers + C11Runner.
Writes evidence under docs/marathon/customer_product/rcp07_blocker_fix_evidence/
"""
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

from scripts.rcp07_real_certification_run import (  # noqa: E402
    _now,
    collect_work_evidence,
    ensure_channel_en_bn,
    evaluate_run,
    run_case,
)


def main() -> int:
    from scripts.c11_real_marathon_runner import C11Runner
    from app.customer_trs_workflow import set_manual_topic
    from pipeline.api_keys import load_api_bundle
    from pipeline.quota_backoff import key_fingerprint

    out_dir = ROOT / "docs" / "marathon" / "customer_product" / "rcp07_blocker_fix_evidence"
    out_dir.mkdir(parents=True, exist_ok=True)

    runner = C11Runner()
    baseline = runner.phase0_baseline()
    google_n = int((baseline.get("provider_inventory") or {}).get("google_keys") or 0)
    agnes_n = int((baseline.get("provider_inventory") or {}).get("agnes_keys") or 0)
    print(f"RCP07-blocker-fix baseline google={google_n} agnes={agnes_n}", flush=True)
    if agnes_n <= 0:
        (out_dir / "SUMMARY.json").write_text(
            json.dumps({"verdict": "BLOCKED", "reason": "AGNES_MISSING"}, indent=2),
            encoding="utf-8",
        )
        return 2

    # Credential inventory (suffix + fingerprint only — no secrets)
    bundle = load_api_bundle()
    gkeys = list(bundle.get("google_keys") or [])
    cred_inv = {
        "google_key_count": len(gkeys),
        "slots": [
            {
                "pool_index": i,
                "suffix": k[-4:],
                "fingerprint12": key_fingerprint(k),
                "length": len(k),
            }
            for i, k in enumerate(gkeys)
        ],
        "unique_fingerprints": len({key_fingerprint(k) for k in gkeys}),
    }
    (out_dir / "GOOGLE_CREDENTIAL_INVENTORY.json").write_text(
        json.dumps(cred_inv, indent=2), encoding="utf-8"
    )
    print(
        f"google_pool unique={cred_inv['unique_fingerprints']}/{cred_inv['google_key_count']}",
        flush=True,
    )

    runner.phase0_clean_state()
    ensure_channel_en_bn(runner)
    runner.phase1_create_run()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    topic = (
        f"How colliding neutron stars forge heavy metals seen by X-ray observatories "
        f"(RCP07 blocker-fix SHORT {stamp})"
    )
    sel = set_manual_topic("c11_marathon_customer", int(runner.channel["id"]), topic)
    if not sel.get("ok"):
        topic = f"RCP07 blocker-fix SHORT {stamp}: magnetar flares and gold forge"
        sel = set_manual_topic("c11_marathon_customer", int(runner.channel["id"]), topic)
    if not sel.get("ok"):
        (out_dir / "SUMMARY.json").write_text(
            json.dumps({"verdict": "BLOCKED", "reason": "topic_failed", "sel": sel}, indent=2),
            encoding="utf-8",
        )
        return 2
    runner.selected_topic = topic
    runner.selected_niche = str((runner.channel or {}).get("niche") or "space science")
    print(f"TOPIC={topic}", flush=True)

    short_out = run_case(runner, "RCP07-BLOCKER-SHORT", "short")
    # Also copy under blocker_fix evidence with richer TTS/remux notes
    job_id = short_out.get("job_id")
    from app.config import DATA_DIR

    work = (
        DATA_DIR / "customer_generation_work" / "c11_marathon_customer" / f"job{job_id}"
        if job_id
        else None
    )
    tts_slots_used = []
    remux_notes = []
    if work and work.is_dir():
        # Scan logs / live activity for slot…XXXX without secrets
        for logp in sorted(work.rglob("*.log")) + sorted(work.glob("*.txt")):
            try:
                text = logp.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for line in text.splitlines():
                if "slot…" in line or "key…" in line or "TTS key" in line:
                    if any(x in line.lower() for x in ("tts", "google", "slot", "key…", "failover")):
                        tts_slots_used.append(line[:240])
                if "remux" in line.lower() or "subtitle" in line.lower() or "localize" in line.lower():
                    if "fail" in line.lower() or "error" in line.lower() or "ok" in line.lower():
                        remux_notes.append(line[:240])
        # SCENE_LOCAL package probe
        sl = work / "SCENE_LOCAL"
        scene_local = {}
        if sl.is_dir():
            for scene_dir in sorted(p for p in sl.iterdir() if p.is_dir()):
                for lang in ("en", "bn"):
                    vid = scene_dir / lang / "video.mp4"
                    narr = scene_dir / lang / "narration.txt"
                    srt = scene_dir / lang / "subtitles.srt"
                    scene_local.setdefault(scene_dir.name, {})[lang] = {
                        "video_exists": vid.is_file() and vid.stat().st_size > 1000,
                        "video_bytes": vid.stat().st_size if vid.is_file() else 0,
                        "narration_exists": narr.is_file(),
                        "srt_exists": srt.is_file(),
                        "srt_name": srt.name if srt.is_file() else None,
                        "has_video_srt_sibling": (scene_dir / lang / "video.srt").is_file(),
                    }
        evidence_extra = {
            "tts_log_lines_sample": tts_slots_used[:40],
            "remux_log_lines_sample": remux_notes[:40],
            "scene_local_packages": scene_local,
            "credential_inventory_file": "GOOGLE_CREDENTIAL_INVENTORY.json",
        }
        (out_dir / f"SHORT_{job_id}_EXTRA.json").write_text(
            json.dumps(evidence_extra, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (out_dir / f"SHORT_{job_id}.json").write_text(
            json.dumps(short_out, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )

    verdict = (short_out.get("evaluation") or {}).get("verdict") or "BLOCKED"
    summary = {
        "contract": "RCP-07-BLOCKER-FIX",
        "finished_at": _now(),
        "login": "c11_marathon_customer",
        "channel_id": int((runner.channel or {}).get("id") or 0),
        "topic": topic,
        "mock_fixture_used": False,
        "deterministic_fixtures": False,
        "google_credential_inventory": cred_inv,
        "SHORT": {
            "verdict": verdict,
            "job_id": job_id,
            "local_path": short_out.get("local_path"),
            "evaluation": short_out.get("evaluation"),
            "elapsed_sec": short_out.get("elapsed_sec"),
            "classification": short_out.get("classification"),
            "status": short_out.get("status"),
        },
        "overall_verdict": verdict,
    }
    (out_dir / "SUMMARY.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(json.dumps({"overall": verdict, "job_id": job_id, "summary": str(out_dir / "SUMMARY.json")}, indent=2), flush=True)
    return 0 if verdict != "BLOCKED" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("RCP07_BLOCKER_FIX_FATAL", type(exc).__name__, exc, flush=True)
        traceback.print_exc()
        raise
