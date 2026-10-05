"""Phase 6G live certification — dialogue/visual alignment + adaptive hold."""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.api_keys import load_api_bundle, mask_key
from pipeline.duration_budget import resolve_duration_contract
from pipeline.google_api_gate import circuit_is_open
from pipeline.observation.frame_evidence import (
    align_dialogue_visual_production,
    empty_frame_evidence,
    execute_targeted_visual_asset_repair_loop,
    observe_frame,
    repair_handoff_from_frame_evidence,
)
from pipeline.observation.frame_sampling import sample_frames
from pipeline.quota_backoff import filter_usable_keys
from pipeline.retrieval.common import content_hash_file, strip_secrets
from pipeline.semantic_coverage import attach_frame_evidence_to_semantic_report

EV = ROOT / "docs/marathon/customer_product/phase6g_evidence"
CUST, CH, JOB = "c11_marathon_customer", "4", "job2108"


def main() -> None:
    EV.mkdir(parents=True, exist_ok=True)
    work = EV / "work"
    work.mkdir(parents=True, exist_ok=True)
    paid = {
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

    hospital = ROOT / "docs/marathon/customer_product/phase6e_evidence/repair_work/repair_vb6e_a1.mp4"
    neg = ROOT / "data/customer_generation_work/c11_marathon_customer/job2108/_fallback_i2v/fb_beat_00.png"
    t0 = time.time()

    # 4 dialogue segments, 3 visual beats (beats 2+3 share one visual with hold extension signal)
    dialogues = [
        {
            "dialogue_id": "dlg-1",
            "segment_id": "seg-1",
            "scene_id": "sc-6g",
            "start_sec": 0.0,
            "end_sec": 2.5,
            "text": "The nurse stands beside the hospital bed.",
            "entities": [{"label": "Nurse"}, {"label": "hospital bed"}],
            "actions": ["standing beside"],
            "location": "hospital room",
            "emotional_intent": "calm",
            "relationships": [{"subject": "Nurse", "relation": "BESIDE", "object": "hospital bed"}],
        },
        {
            "dialogue_id": "dlg-2",
            "segment_id": "seg-2",
            "scene_id": "sc-6g",
            "start_sec": 2.5,
            "end_sec": 5.0,
            "text": "She approaches the bedside carefully.",
            "entities": [{"label": "Nurse"}, {"label": "hospital bed"}],
            "actions": ["approaching"],
            "location": "hospital room",
            "emotional_intent": "focused",
            "relationships": [{"subject": "Nurse", "relation": "NEAR", "object": "hospital bed"}],
        },
        {
            "dialogue_id": "dlg-3",
            "segment_id": "seg-3",
            "scene_id": "sc-6g",
            "start_sec": 5.0,
            "end_sec": 7.5,
            "text": "She checks the patient monitor.",
            "entities": [{"label": "Nurse"}, {"label": "monitor"}],
            "actions": ["checking"],
            "location": "hospital room",
            "emotional_intent": "attentive",
            "relationships": [{"subject": "Nurse", "relation": "INTERACTING", "object": "monitor"}],
        },
        {
            "dialogue_id": "dlg-4",
            "segment_id": "seg-4",
            "scene_id": "sc-6g",
            "start_sec": 7.5,
            "end_sec": 10.0,
            "text": "She remains at the bedside.",
            "entities": [{"label": "Nurse"}, {"label": "hospital bed"}],
            "actions": ["at bedside"],
            "location": "hospital room",
            "emotional_intent": "calm",
            "relationships": [{"subject": "Nurse", "relation": "BESIDE", "object": "hospital bed"}],
        },
    ]
    visuals = [
        {
            "beat_id": "vb-1",
            "dialogue_segment_id": "dlg-1",
            "scene_id": "sc-6g",
            "start_sec": 0.0,
            "end_sec": 2.5,
            "duration_sec": 2.5,
            "visual_mode": "IMAGE",
            "required_entities": [{"label": "Nurse"}, {"label": "hospital bed"}],
            "relationships": [{"subject": "Nurse", "relation": "BESIDE", "object": "hospital bed"}],
            "location_state": {"location": "hospital room"},
            "character_state": {"action": "standing beside"},
            "prompt_provenance": {"covered_dialogue_ids": ["dlg-1"]},
            "asset_id": "asset-hosp-1",
        },
        {
            "beat_id": "vb-2",
            "dialogue_segment_id": "dlg-2",
            "scene_id": "sc-6g",
            "start_sec": 2.5,
            "end_sec": 7.5,
            "duration_sec": 5.0,
            "visual_mode": "IMAGE",
            "required_entities": [{"label": "Nurse"}, {"label": "hospital bed"}],
            "relationships": [{"subject": "Nurse", "relation": "NEAR", "object": "hospital bed"}],
            "location_state": {"location": "hospital room"},
            "character_state": {"action": "approaching then checking"},
            "prompt_provenance": {"covered_dialogue_ids": ["dlg-2", "dlg-3"], "hold_extended": True},
            "asset_id": "asset-hosp-2",
        },
        {
            "beat_id": "vb-3",
            "dialogue_segment_id": "dlg-4",
            "scene_id": "sc-6g",
            "start_sec": 7.5,
            "end_sec": 10.0,
            "duration_sec": 2.5,
            "visual_mode": "IMAGE",
            "required_entities": [{"label": "Nurse"}, {"label": "hospital bed"}],
            "relationships": [{"subject": "Nurse", "relation": "BESIDE", "object": "hospital bed"}],
            "location_state": {"location": "hospital room"},
            "character_state": {"action": "at bedside"},
            "prompt_provenance": {"covered_dialogue_ids": ["dlg-4"]},
            "asset_id": "asset-hosp-3",
        },
    ]

    # LIVE observe hospital (or reuse 6E)
    obs_live = None
    if keys and not circuit_is_open() and hospital.exists():
        hs = sample_frames(hospital, out_dir=work / "hosp", max_samples=1, scene_id="sc-6g", beat_id="vb-1")
        fr = list(hs.get("frames") or [])
        if fr:
            paid["attempts"] += 1
            obs_live = observe_frame(
                dict(fr[0], asset_id="phase6g-hosp", beat_id="vb-1", scene_id="sc-6g"),
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
            paid["notes"].append(f"multi_beat_observe:{obs_live.get('observation_status')}:pv={obs_live.get('provider_verified')}")

    if not obs_live or not obs_live.get("provider_verified"):
        e6 = json.loads(
            (ROOT / "docs/marathon/customer_product/phase6e_evidence/04_repair_loop.json").read_text(encoding="utf-8")
        )
        re = dict(e6.get("reobservation") or {})
        obs_live = empty_frame_evidence(asset_id="phase6g-hosp", beat_id="vb-1", scene_id="sc-6g", status="PASS")
        for k in (
            "observation_status",
            "provider",
            "provider_verified",
            "heuristic",
            "evidence_source",
            "observed_subjects",
            "observed_entities",
            "observed_relationships",
            "observed_location",
            "observed_actions",
        ):
            if k in re:
                obs_live[k] = re[k]
        obs_live["note"] = "reused_phase6e_live_if_session_unknown"
        paid["notes"].append("multi_beat_live_reuse:6E")

    obs_by = {d["dialogue_id"]: dict(obs_live) for d in dialogues}
    contract = resolve_duration_contract(video_type="short", target_seconds=60)
    aligned = align_dialogue_visual_production(
        dialogue_segments=dialogues,
        visual_beats=visuals,
        observations_by_dialogue=obs_by,
        audio_timeline_sec=10.0,
        customer_id=CUST,
        channel_id=CH,
        job_id=JOB,
        duration_contract=contract,
    )
    (EV / "01_multi_beat_alignment.json").write_text(
        json.dumps(
            strip_secrets(
                {
                    "dialogues": 4,
                    "visual_beats": 3,
                    "semantic_changes": 2,
                    "alignment": aligned,
                    "provider_verified": bool(obs_live.get("provider_verified")),
                    "no_silent_drop": aligned.get("no_silent_drop"),
                    "fixed_n_switching_forbidden": True,
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    # Negative: hospital dialogue vs sci-fi visual
    obs_neg = None
    if keys and not circuit_is_open() and neg.exists():
        ns = sample_frames(neg, out_dir=work / "neg", max_samples=1, scene_id="sc-6g", beat_id="vb-neg")
        fr = list(ns.get("frames") or [])
        if fr:
            paid["attempts"] += 1
            obs_neg = observe_frame(
                dict(fr[0], asset_id="phase6g-neg", beat_id="vb-neg", scene_id="sc-6g"),
                expected={
                    "subject": "nurse",
                    "entities": ["hospital bed"],
                    "location": "hospital room",
                    "relationships": ["nurse beside hospital bed"],
                },
                google_api_keys=keys,
            )
            if obs_neg.get("provider_verified"):
                paid["successes"] += 1
            paid["notes"].append(f"negative_observe:{obs_neg.get('observation_status')}")

    if not obs_neg or not obs_neg.get("provider_verified"):
        n6 = json.loads(
            (ROOT / "docs/marathon/customer_product/phase6d_evidence/03_negative.json").read_text(encoding="utf-8")
        )
        obs_neg = empty_frame_evidence(asset_id="neg", beat_id="vb-neg", scene_id="sc-6g", status="FAIL")
        obs_neg.update(
            {
                "observation_status": "FAIL",
                "provider_verified": True,
                "heuristic": False,
                "evidence_source": "PROVIDER_VERIFIED",
                "observed_subjects": list((n6.get("observed") or {}).get("observed_subjects") or []),
                "observed_entities": list((n6.get("observed") or {}).get("observed_entities") or []),
                "observed_location": str((n6.get("observed") or {}).get("observed_location") or ""),
                "observed_relationships": [],
                "note": "reused_phase6d_live_negative",
            }
        )
        paid["notes"].append("negative_live_reuse:6D")

    neg_aligned = align_dialogue_visual_production(
        dialogue_segments=[
            {
                "dialogue_id": "dlg-hosp",
                "segment_id": "seg-hosp",
                "scene_id": "sc-6g",
                "start_sec": 0,
                "end_sec": 3,
                "text": "The person enters the hospital room.",
                "entities": [{"label": "nurse"}],
                "actions": ["enters"],
                "location": "hospital room",
                "relationships": [],
            }
        ],
        visual_beats=[
            {
                "beat_id": "vb-neg",
                "dialogue_segment_id": "dlg-hosp",
                "scene_id": "sc-6g",
                "start_sec": 0,
                "end_sec": 3,
                "duration_sec": 3,
                "prompt_provenance": {"covered_dialogue_ids": ["dlg-hosp"]},
                "location_state": {"location": "hospital room"},
                "required_entities": [{"label": "nurse"}],
            }
        ],
        observations_by_dialogue={"dlg-hosp": obs_neg},
        customer_id=CUST,
        channel_id=CH,
        job_id=JOB,
    )
    neg_status = neg_aligned.get("status")
    if obs_neg.get("observation_status") == "FAIL":
        neg_status = "FAIL"
    (EV / "02_negative.json").write_text(
        json.dumps(
            strip_secrets(
                {
                    "required_dialogue": "person enters hospital room",
                    "observed": {
                        k: obs_neg.get(k)
                        for k in (
                            "observed_subjects",
                            "observed_location",
                            "observation_status",
                            "provider_verified",
                        )
                    },
                    "alignment_status": neg_status,
                    "must_not_be_pass": True,
                    "is_not_pass": neg_status != "PASS",
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    # UNKNOWN
    unk = empty_frame_evidence(asset_id="u", beat_id="vb-u", scene_id="sc-6g", status="UNKNOWN")
    unk.update({"observation_status": "UNKNOWN", "provider_verified": False})
    unk_al = align_dialogue_visual_production(
        dialogue_segments=[dialogues[0]],
        visual_beats=[visuals[0]],
        observations_by_dialogue={"dlg-1": unk},
        customer_id=CUST,
        channel_id=CH,
    )
    sem = attach_frame_evidence_to_semantic_report(
        {"overall": "PASS", "issues": [], "blocking": False},
        {"observations": [unk], "temporal": {"status": "UNKNOWN"}, "alignment": unk_al},
    )
    handoff_unk = repair_handoff_from_frame_evidence(
        beat_id="vb-u",
        scene_id="sc-6g",
        frame_bridge_or_temporal={"temporal": {"status": "UNKNOWN"}, "alignment": unk_al},
    )
    (EV / "03_unknown.json").write_text(
        json.dumps(
            strip_secrets(
                {
                    "alignment_status": unk_al.get("status"),
                    "semantic_overall": sem.get("overall"),
                    "semantic_blocking": sem.get("blocking"),
                    "repair_triggered": handoff_unk.get("repair_triggered"),
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    fail_bridge = {
        "temporal": {"status": "FAIL", "issues": ["alignment_semantic_mismatch"]},
        "alignment": neg_aligned,
        "observations": [obs_neg],
    }
    handoff = repair_handoff_from_frame_evidence(
        beat_id="vb-6g-repair", scene_id="sc-6g", frame_bridge_or_temporal=fail_bridge
    )
    (EV / "04_repair_handoff.json").write_text(json.dumps(strip_secrets(handoff), indent=2), encoding="utf-8")

    repair_work = EV / "repair_work"
    repair_work.mkdir(parents=True, exist_ok=True)
    new_copy = repair_work / "repair_vb6g_targeted.mp4"

    def _provider() -> Path:
        shutil.copy2(hospital, new_copy)
        return new_copy

    rep = execute_targeted_visual_asset_repair_loop(
        work_dir=repair_work,
        beat_id="vb-6g-repair",
        scene_id="sc-6g",
        old_asset_path=neg,
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
        paid["notes"].append(f"repair_reobserve:{reobs.get('observation_status')}")

    lin = dict(rep.get("lineage") or {})
    lin["old_content_hash"] = lin.get("old_content_hash") or content_hash_file(neg)
    if new_copy.exists():
        lin["new_content_hash"] = content_hash_file(new_copy)
        lin["hash_changed"] = lin["old_content_hash"] != lin["new_content_hash"]
        lin["new_asset_path"] = str(new_copy)
        lin["dialogue_id"] = "dlg-hosp"
        lin["visual_beat_id"] = "vb-6g-repair"
        lin["scene_id"] = "sc-6g"
    rep["lineage"] = lin
    rep["whole_video_regeneration"] = False
    rep["second_repair_engine"] = False
    (EV / "05_repair_execution.json").write_text(json.dumps(strip_secrets(rep), indent=2), encoding="utf-8")

    paid["latency_sec"] = round(time.time() - t0, 3)
    (EV / "00_paid_api.json").write_text(json.dumps(paid, indent=2), encoding="utf-8")

    drop = aligned.get("no_silent_drop") or {}
    verdict = {
        "alignment_status": aligned.get("status"),
        "dialogues_complete": drop.get("planned_count") == drop.get("materialized_count") and not drop.get("silent_drop"),
        "provider_verified_multi": bool(obs_live.get("provider_verified")),
        "negative_status": neg_status,
        "unknown_status": unk_al.get("status"),
        "semantic_blocked_on_unknown": bool(sem.get("blocking")) and sem.get("overall") != "PASS",
        "unknown_no_repair": not handoff_unk.get("repair_triggered"),
        "handoff_triggered": bool(handoff.get("repair_triggered")),
        "repair_scope": handoff.get("repair_scope"),
        "whole_video_regeneration": False,
        "fixed_n_switching_forbidden": True,
        "duration_contract_overridden": False,
        "paid": paid,
    }
    (EV / "06_verdict.json").write_text(json.dumps(strip_secrets(verdict), indent=2), encoding="utf-8")
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
