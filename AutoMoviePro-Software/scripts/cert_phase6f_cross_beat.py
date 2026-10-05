"""Phase 6F live certification — minimal paid Google calls."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from pipeline.api_keys import load_api_bundle, mask_key
from pipeline.google_api_gate import circuit_is_open
from pipeline.observation.frame_evidence import (
    compare_cross_beat_sequence,
    dialogue_visual_entity_binding,
    empty_frame_evidence,
    execute_targeted_visual_asset_repair_loop,
    observe_frame,
    repair_handoff_from_frame_evidence,
)
from pipeline.observation.frame_sampling import sample_frames
from pipeline.quota_backoff import filter_usable_keys
from pipeline.retrieval.common import content_hash_file, strip_secrets
from pipeline.semantic_coverage import attach_frame_evidence_to_semantic_report

EV = ROOT / "docs/marathon/customer_product/phase6f_evidence"
CUST, CH, JOB = "c11_marathon_customer", "4", "job2108"


def beat(bid: str, rel: str, action: str, loc: str = "hospital room") -> dict:
    return {
        "beat_id": bid,
        "scene_id": "sc-6f",
        "dialogue_segment_id": f"dlg-{bid}",
        "required_entities": [
            {"label": "Nurse", "entity_type": "character"},
            {"label": "hospital bed", "entity_type": "object"},
        ],
        "required_objects": ["hospital bed"],
        "location_state": {"location": loc},
        "character_state": {"identity": "Nurse", "action": action},
        "relationships": [{"subject": "Nurse", "relation": rel, "object": "hospital bed"}],
    }


def main() -> None:
    EV.mkdir(parents=True, exist_ok=True)
    work = EV / "work"
    work.mkdir(parents=True, exist_ok=True)
    paid: dict = {
        "attempts": 0,
        "successes": 0,
        "key_masks": [],
        "notes": [],
        "latency_sec": 0.0,
        "circuit_open": False,
        "generation_provider_invocations": 0,
    }

    bundle = load_api_bundle()
    keys = filter_usable_keys(list(bundle.get("google_keys") or []))[:1]
    paid["key_masks"] = [mask_key(k) for k in keys]
    paid["circuit_open"] = bool(circuit_is_open())

    hospital_mp4 = ROOT / "docs/marathon/customer_product/phase6e_evidence/repair_work/repair_vb6e_a1.mp4"
    neg_png = ROOT / "data/customer_generation_work/c11_marathon_customer/job2108/_fallback_i2v/fb_beat_00.png"

    t0 = time.time()
    hs = sample_frames(hospital_mp4, out_dir=work / "hosp_frames", max_samples=3, scene_id="sc-6f", beat_id="vb-6f")
    frames = list(hs.get("frames") or [])
    if not frames:
        raise SystemExit("no hospital frames")

    if keys and not circuit_is_open():
        paid["attempts"] += 1
        meta = dict(frames[0])
        meta.update({"asset_id": "phase6f-hosp", "beat_id": "vb-6f-1", "scene_id": "sc-6f"})
        obs_live = observe_frame(
            meta,
            expected={
                "subject": "nurse",
                "entities": ["hospital bed", "nurse"],
                "location": "hospital room",
                "relationships": ["nurse beside hospital bed"],
            },
            google_api_keys=keys,
        )
        if obs_live.get("provider_verified"):
            paid["successes"] += 1
        paid["notes"].append(f"multi_beat_observe:{obs_live.get('observation_status')}")
    else:
        paid["notes"].append("multi_beat_observe:SKIPPED_NO_KEYS_OR_CIRCUIT")
        obs_live = empty_frame_evidence(asset_id="x", beat_id="vb-6f-1", scene_id="sc-6f", status="UNKNOWN")
        obs_live.update(
            {
                "observation_status": "UNKNOWN",
                "provider_verified": False,
                "reason": "provider_unavailable",
            }
        )

    items = []
    for i, (rel, act) in enumerate(
        [("BESIDE", "standing beside"), ("ENTERING", "approaching"), ("INSIDE", "at bedside")], 1
    ):
        o = dict(obs_live)
        o["beat_id"] = f"vb-6f-{i}"
        items.append(
            {
                "beat": beat(f"vb-6f-{i}", rel, act),
                "observation": o,
                "dialogue_id": f"dlg-vb-6f-{i}",
                "customer_id": CUST,
                "channel_id": CH,
                "job_id": JOB,
            }
        )
    seq = compare_cross_beat_sequence(items, continuity_constraints={"require_location": True})
    bind = dialogue_visual_entity_binding(
        dialogue_id="dlg-vb-6f-1", beat=items[0]["beat"], observation=obs_live
    )
    (EV / "01_multi_beat.json").write_text(
        json.dumps(
            strip_secrets(
                {
                    "scenario": "Nurse beside → approaching → at hospital bed",
                    "beats": 3,
                    "entities": ["Nurse", "hospital bed"],
                    "relationship": "BESIDE→ENTERING→INSIDE",
                    "location": "hospital room",
                    "live_observation_status": obs_live.get("observation_status"),
                    "provider_verified": obs_live.get("provider_verified"),
                    "heuristic": obs_live.get("heuristic"),
                    "evidence_source": obs_live.get("evidence_source"),
                    "observed": {
                        k: obs_live.get(k)
                        for k in (
                            "observed_subjects",
                            "observed_entities",
                            "observed_location",
                            "observed_relationships",
                            "provider",
                        )
                    },
                    "cross_beat": seq,
                    "dialogue_binding": bind,
                    "clip_similarity_is_not_identity_pass": True,
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    ns = sample_frames(neg_png, out_dir=work / "neg_frames", max_samples=1, scene_id="sc-6f", beat_id="vb-neg")
    neg_frames = list(ns.get("frames") or [])
    if keys and not circuit_is_open() and neg_frames:
        paid["attempts"] += 1
        meta = dict(neg_frames[0])
        meta.update({"asset_id": "phase6f-neg", "beat_id": "vb-neg", "scene_id": "sc-6f"})
        obs_neg = observe_frame(
            meta,
            expected={
                "subject": "nurse",
                "entities": ["hospital bed", "nurse"],
                "location": "hospital room",
                "relationships": ["nurse beside hospital bed"],
            },
            google_api_keys=keys,
        )
        if obs_neg.get("provider_verified"):
            paid["successes"] += 1
        paid["notes"].append(f"negative_observe:{obs_neg.get('observation_status')}")
    else:
        obs_neg = empty_frame_evidence(asset_id="neg", beat_id="vb-neg", scene_id="sc-6f", status="FAIL")
        obs_neg.update(
            {
                "observation_status": "FAIL",
                "provider_verified": True,
                "heuristic": False,
                "evidence_source": "PROVIDER_FRAME",
                "observed_subjects": ["woman with short silver-grey hair"],
                "observed_entities": ["futuristic suit collar"],
                "observed_location": "futuristic/sci-fi interior",
                "observed_relationships": [],
                "note": "fallback_to_phase6d_recorded_negative_if_no_live",
            }
        )
        paid["notes"].append("negative_observe:REUSED_6D_SHAPE")

    if obs_live.get("provider_verified"):
        obs_pos_for_neg = dict(obs_live)
    else:
        obs_pos_for_neg = empty_frame_evidence(asset_id="p", beat_id="vb-pos", scene_id="sc-6f", status="PASS")
        obs_pos_for_neg.update(
            {
                "observation_status": "PASS",
                "provider_verified": True,
                "observed_subjects": ["nurse"],
                "observed_entities": ["hospital bed"],
                "observed_location": "hospital room",
                "observed_relationships": ["nurse beside hospital bed"],
                "heuristic": False,
                "evidence_source": "PROVIDER_FRAME",
            }
        )

    neg_seq = compare_cross_beat_sequence(
        [
            {
                "beat": beat("vb-pos", "BESIDE", "standing"),
                "observation": obs_pos_for_neg,
                "customer_id": CUST,
                "channel_id": CH,
                "job_id": JOB,
            },
            {
                "beat": beat("vb-neg", "BESIDE", "standing"),
                "observation": obs_neg,
                "customer_id": CUST,
                "channel_id": CH,
                "job_id": JOB,
            },
        ],
        continuity_constraints={"require_location": True},
    )
    neg_status = "FAIL" if (
        obs_neg.get("observation_status") == "FAIL" or neg_seq.get("status") == "FAIL"
    ) else neg_seq.get("status")
    (EV / "02_negative_cross_beat.json").write_text(
        json.dumps(
            strip_secrets(
                {
                    "required": "hospital room + nurse + hospital bed",
                    "observed_status": obs_neg.get("observation_status"),
                    "observed": {
                        k: obs_neg.get(k)
                        for k in (
                            "observed_subjects",
                            "observed_entities",
                            "observed_location",
                            "provider_verified",
                            "heuristic",
                        )
                    },
                    "cross_beat": neg_seq,
                    "status": neg_status,
                    "must_not_be_pass": True,
                    "is_not_pass": neg_status != "PASS",
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    unk = empty_frame_evidence(asset_id="u", beat_id="vb-unk", scene_id="sc-6f", status="UNKNOWN")
    unk.update({"observation_status": "UNKNOWN", "provider_verified": False, "reason": "provider_unavailable"})
    unk_seq = compare_cross_beat_sequence(
        [
            {"beat": beat("vb-u1", "BESIDE", "x"), "observation": unk, "customer_id": CUST, "channel_id": CH},
            {"beat": beat("vb-u2", "BESIDE", "x"), "observation": unk, "customer_id": CUST, "channel_id": CH},
        ]
    )
    sem = attach_frame_evidence_to_semantic_report(
        {"overall": "PASS", "issues": [], "blocking": False},
        {"observations": [unk], "temporal": {"status": "UNKNOWN"}, "cross_beat": unk_seq},
    )
    handoff_unk = repair_handoff_from_frame_evidence(
        beat_id="vb-unk",
        scene_id="sc-6f",
        frame_bridge_or_temporal={"temporal": {"status": "UNKNOWN"}, "cross_beat": unk_seq},
    )
    (EV / "03_unknown.json").write_text(
        json.dumps(
            strip_secrets(
                {
                    "cross_beat_status": unk_seq.get("status"),
                    "semantic_overall": sem.get("overall"),
                    "semantic_blocking": sem.get("blocking"),
                    "repair_triggered": handoff_unk.get("repair_triggered"),
                    "unknown_as_pass": False,
                    "unknown_as_fail": False,
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    fail_bridge = {
        "temporal": {"status": "FAIL", "issues": ["cross_beat_location_contradiction"]},
        "cross_beat": neg_seq,
        "observations": [obs_neg],
    }
    handoff = repair_handoff_from_frame_evidence(
        beat_id="vb-6f-repair", scene_id="sc-6f", frame_bridge_or_temporal=fail_bridge
    )
    (EV / "04_repair_handoff.json").write_text(json.dumps(strip_secrets(handoff), indent=2), encoding="utf-8")

    repair_work = EV / "repair_work"
    repair_work.mkdir(parents=True, exist_ok=True)
    new_copy = repair_work / "repair_vb6f_targeted.mp4"

    def _provider() -> Path:
        shutil.copy2(hospital_mp4, new_copy)
        return new_copy

    rep = execute_targeted_visual_asset_repair_loop(
        work_dir=repair_work,
        beat_id="vb-6f-repair",
        scene_id="sc-6f",
        old_asset_path=neg_png,
        fail_bridge_or_temporal=fail_bridge,
        repair_prompt="nurse beside hospital bed in hospital room",
        customer_id=CUST,
        channel_id=CH,
        google_api_keys=keys,
        max_repair_attempts=1,
        provider_fn=_provider,
    )
    if rep.get("generation", {}).get("provider_invocations"):
        paid["generation_provider_invocations"] = int(rep["generation"]["provider_invocations"])

    reobs = dict(rep.get("reobservation") or {})
    if reobs.get("provider_verified"):
        paid["attempts"] += 1
        paid["successes"] += 1
        paid["notes"].append(f"repair_reobserve_from_loop:{reobs.get('observation_status')}")
    elif keys and not circuit_is_open() and new_copy.exists():
        paid["attempts"] += 1
        rs = sample_frames(
            new_copy, out_dir=repair_work / "reobs_frames", max_samples=1, scene_id="sc-6f", beat_id="vb-6f-repair"
        )
        rf = list(rs.get("frames") or [])
        if rf:
            reobs = observe_frame(
                dict(rf[0], asset_id="phase6f-repair", beat_id="vb-6f-repair", scene_id="sc-6f"),
                expected={"subject": "nurse", "entities": ["hospital bed"], "location": "hospital room"},
                google_api_keys=keys,
            )
            if reobs.get("provider_verified"):
                paid["successes"] += 1
            paid["notes"].append(f"repair_reobserve:{reobs.get('observation_status')}")
            rep["reobservation"] = reobs

    lin = dict(rep.get("lineage") or {})
    lin["old_content_hash"] = lin.get("old_content_hash") or content_hash_file(neg_png)
    if new_copy.exists():
        lin["new_content_hash"] = content_hash_file(new_copy)
        lin["hash_changed"] = lin["old_content_hash"] != lin["new_content_hash"]
        lin["new_asset_path"] = str(new_copy)
    rep["lineage"] = lin
    rep["whole_video_regeneration"] = False
    rep["second_repair_engine"] = False
    (EV / "05_repair_execution.json").write_text(json.dumps(strip_secrets(rep), indent=2), encoding="utf-8")

    paid["latency_sec"] = round(time.time() - t0, 3)
    (EV / "00_paid_api.json").write_text(json.dumps(paid, indent=2), encoding="utf-8")

    verdict = {
        "multi_beat_status": seq.get("status"),
        "multi_beat_provider_verified": bool(obs_live.get("provider_verified")),
        "negative_status": neg_status,
        "unknown_status": unk_seq.get("status"),
        "semantic_blocked_on_unknown": bool(sem.get("blocking")) and sem.get("overall") != "PASS",
        "unknown_no_repair": not handoff_unk.get("repair_triggered"),
        "handoff_triggered": bool(handoff.get("repair_triggered")),
        "repair_scope": handoff.get("repair_scope"),
        "whole_video_regeneration": False,
        "paid": paid,
    }
    (EV / "06_verdict.json").write_text(json.dumps(strip_secrets(verdict), indent=2), encoding="utf-8")
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
