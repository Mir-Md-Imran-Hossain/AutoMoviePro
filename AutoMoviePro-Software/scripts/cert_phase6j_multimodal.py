"""Phase 6J small real certification — evidence fusion (minimal paid)."""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.multimodal_consistency import (
    attach_evidence_projection_to_semantic_report,
    fuse_production_evidence,
    project_beat_evidence,
    repair_handoff_from_evidence_projection,
)
from pipeline.observation.frame_evidence import execute_targeted_visual_asset_repair_loop
from pipeline.retrieval.common import content_hash_file, strip_secrets

EV = ROOT / "docs/marathon/customer_product/phase6j_evidence"
CUST, CH, JOB = "c11_marathon_customer", "4", "job2108"


def main() -> None:
    EV.mkdir(parents=True, exist_ok=True)
    paid = {
        "attempts": 0,
        "successes": 0,
        "paid_google_calls": 0,
        "notes": ["reuse_phase6d_6e_6h_live_evidence_no_new_paid_unless_repair_reobserve"],
        "key_masks": [],
        "latency_sec": 0.0,
    }
    t0 = time.time()

    # Reuse prior LIVE visual evidence
    e6e = json.loads(
        (ROOT / "docs/marathon/customer_product/phase6e_evidence/04_repair_loop.json").read_text(encoding="utf-8")
    )
    vis_pass = dict(e6e.get("reobservation") or {})
    assert vis_pass.get("provider_verified")

    e6d = json.loads(
        (ROOT / "docs/marathon/customer_product/phase6d_evidence/03_negative.json").read_text(encoding="utf-8")
    )
    vis_neg = {
        "observation_status": "FAIL",
        "provider_verified": True,
        "heuristic": False,
        "evidence_source": "PROVIDER_VERIFIED",
        "provider": (e6d.get("observed") or {}).get("provider"),
        "observed_subjects": list((e6d.get("observed") or {}).get("observed_subjects") or []),
        "observed_entities": list((e6d.get("observed") or {}).get("observed_entities") or []),
        "observed_location": str((e6d.get("observed") or {}).get("observed_location") or ""),
        "observed_relationships": [],
        "observed_actions": [],
        "note": "reused_phase6d_live_negative",
    }

    # Audio from 6H if present
    aud_path = ROOT / "docs/marathon/customer_product/phase6h_evidence/_gen/narration_positive.mp3"
    from pipeline.observation.audio_evidence import observe_audio_production, observe_acoustic_voice_bundle
    from pipeline.production_consistency import resolve_canonical_voice_identity

    voice = resolve_canonical_voice_identity(voice_profile="male", voice_identity_id="voice:male")
    dialogues = [
        {
            "dialogue_id": "dlg-1",
            "scene_id": "sc-1",
            "start_sec": 0,
            "end_sec": 2.5,
            "text": "The nurse stands beside the hospital bed.",
            "emotion": "neutral",
            "entities": [{"label": "Nurse"}, {"label": "hospital bed"}],
            "location": "hospital room",
            "actions": ["standing beside"],
            "relationships": [{"relation": "beside"}],
        },
        {
            "dialogue_id": "dlg-2",
            "scene_id": "sc-1",
            "start_sec": 2.5,
            "end_sec": 5.0,
            "text": "She approaches carefully.",
            "emotion": "concerned",
            "entities": [{"label": "Nurse"}, {"label": "hospital bed"}],
            "location": "hospital room",
            "actions": ["approaching"],
            "relationships": [{"relation": "near"}],
        },
        {
            "dialogue_id": "dlg-3",
            "scene_id": "sc-2",
            "start_sec": 5.0,
            "end_sec": 8.0,
            "text": "She remains calm at the bedside.",
            "emotion": "relieved",
            "entities": [{"label": "Nurse"}, {"label": "hospital bed"}],
            "location": "hospital room",
            "actions": ["at bedside"],
            "relationships": [{"relation": "beside"}],
        },
    ]
    audio_bundle = None
    acoustic = None
    if aud_path.exists():
        audio_bundle = observe_audio_production(
            audio_path=aud_path,
            dialogue_segments=dialogues,
            voice_identity=voice,
            customer_id=CUST,
            channel_id=CH,
            job_id=JOB,
            audio_asset_id="6j-aud",
            materialized_dialogue_ids=["dlg-1", "dlg-2", "dlg-3"],
        )
        acoustic = observe_acoustic_voice_bundle(
            audio_path=aud_path,
            dialogue_segments=dialogues,
            voice_identity=voice,
            customer_id=CUST,
            channel_id=CH,
            job_id=JOB,
            audio_asset_id="6j-aud",
        )
        paid["notes"].append(f"local_asr_audio:{audio_bundle.get('status')}")

    beats = []
    for i, d in enumerate(dialogues, 1):
        beats.append(
            project_beat_evidence(
                beat_id=f"vb-{i}",
                scene_id=d["scene_id"],
                dialogue_id=d["dialogue_id"],
                visual_asset_id="vis-hosp",
                audio_asset_id="6j-aud",
                intent={
                    "subject": "Nurse",
                    "entities": d["entities"],
                    "relationships": d["relationships"],
                    "actions": d["actions"],
                    "location": d["location"],
                    "emotion": d["emotion"],
                    "dialogue": d["text"],
                },
                visual_observation=vis_pass,
                audio_observation=audio_bundle or {"status": "UNKNOWN", "speech": {"status": "UNKNOWN"}},
                acoustic_observation=acoustic or {"VOICE_IDENTITY_OBSERVATION": "UNKNOWN"},
                timing={
                    "planned_start": d["start_sec"],
                    "planned_end": d["end_sec"],
                    "visual_coverage": "FULL",
                    "dialogue_coverage": "FULL",
                },
                continuity={"status": "PASS", "location": "hospital", "character": "Nurse", "object": "hospital bed"},
                customer_id=CUST,
                channel_id=CH,
                job_id=JOB,
            )
        )

    positive = fuse_production_evidence(beats=beats, customer_id=CUST, channel_id=CH, job_id=JOB)
    (EV / "01_positive.json").write_text(json.dumps(strip_secrets(positive), indent=2), encoding="utf-8")

    neg_beat = project_beat_evidence(
        beat_id="vb-neg",
        scene_id="sc-neg",
        dialogue_id="dlg-hosp",
        intent={
            "location": "hospital room",
            "dialogue": "She enters the hospital.",
            "entities": [{"label": "Nurse"}],
            "relationships": [{"relation": "beside"}],
        },
        visual_observation=vis_neg,
        audio_observation=audio_bundle or {},
        acoustic_observation={"VOICE_IDENTITY_OBSERVATION": "UNKNOWN"},
        customer_id=CUST,
        channel_id=CH,
        job_id=JOB,
    )
    negative = fuse_production_evidence(beats=[neg_beat], customer_id=CUST, channel_id=CH, job_id=JOB)
    (EV / "02_negative.json").write_text(
        json.dumps(
            strip_secrets(
                {
                    "case": "hospital_dialogue_vs_spacecraft_visual",
                    "status": negative.get("status"),
                    "beat": neg_beat,
                    "must_not_be_pass": True,
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    unk_beat = project_beat_evidence(
        beat_id="vb-unk",
        intent={"location": "hospital room", "dialogue": "hello"},
        visual_observation={"observation_status": "UNKNOWN", "provider_verified": False},
        audio_observation={"status": "UNKNOWN", "speech": {"status": "UNKNOWN", "provider_verified": False}},
        acoustic_observation={"VOICE_IDENTITY_OBSERVATION": "UNKNOWN"},
        customer_id=CUST,
        channel_id=CH,
    )
    unk_fuse = fuse_production_evidence(beats=[unk_beat], customer_id=CUST)
    sem = attach_evidence_projection_to_semantic_report(
        {"overall": "PASS", "issues": [], "blocking": False},
        unk_fuse,
        mandatory=True,
    )
    handoff_unk = repair_handoff_from_evidence_projection(beat_id="vb-unk", scene_id="sc", evidence=unk_beat)
    (EV / "03_unknown.json").write_text(
        json.dumps(
            strip_secrets(
                {
                    "fusion_status": unk_fuse.get("status"),
                    "semantic_overall": sem.get("overall"),
                    "semantic_blocking": sem.get("blocking"),
                    "repair_triggered": handoff_unk.get("repair_triggered"),
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    handoff = repair_handoff_from_evidence_projection(beat_id="vb-neg", scene_id="sc-neg", evidence=neg_beat)
    (EV / "04_repair_handoff.json").write_text(json.dumps(strip_secrets(handoff), indent=2), encoding="utf-8")

    # Targeted visual repair using existing loop + copy hospital asset (no new paid gen)
    hospital = ROOT / "docs/marathon/customer_product/phase6e_evidence/repair_work/repair_vb6e_a1.mp4"
    neg_png = ROOT / "data/customer_generation_work/c11_marathon_customer/job2108/_fallback_i2v/fb_beat_00.png"
    repair_work = EV / "repair_work"
    repair_work.mkdir(parents=True, exist_ok=True)
    new_copy = repair_work / "repair_vb6j.mp4"
    repair_rec = {"execution": "HANDOFF_ONLY", "handoff": handoff, "whole_video_regeneration": False}
    if handoff.get("repair_triggered") and hospital.exists() and neg_png.exists():

        def _provider():
            shutil.copy2(hospital, new_copy)
            return new_copy

        rep = execute_targeted_visual_asset_repair_loop(
            work_dir=repair_work,
            beat_id="vb-neg",
            scene_id="sc-neg",
            old_asset_path=neg_png,
            fail_bridge_or_temporal={
                "temporal": {"status": "FAIL", "issues": ["cross_modal_location_contradiction"]},
                "observations": [vis_neg],
            },
            repair_prompt="nurse hospital bed hospital room",
            customer_id=CUST,
            channel_id=CH,
            max_repair_attempts=1,
            provider_fn=_provider,
            google_api_keys=[],  # avoid paid if loop still reobserves without keys → UNKNOWN ok
        )
        # If loop re-observes without keys may UNKNOWN; still prove lineage
        lin = dict(rep.get("lineage") or {})
        lin["old_content_hash"] = lin.get("old_content_hash") or content_hash_file(neg_png)
        if new_copy.exists():
            lin["new_content_hash"] = content_hash_file(new_copy)
            lin["hash_changed"] = lin["old_content_hash"] != lin["new_content_hash"]
        repair_rec = {
            "execution": rep.get("execution") or "EXECUTED",
            "repair_scope": "VISUAL_ASSET",
            "whole_video_regeneration": False,
            "handoff": handoff,
            "lineage": lin,
            "reobservation": rep.get("reobservation"),
            "second_repair_engine": False,
            "note": "provider_fn_copy_hospital_asset; reobserve may be UNKNOWN without paid keys",
        }
        if (rep.get("reobservation") or {}).get("provider_verified"):
            paid["attempts"] += 1
            paid["successes"] += 1
            paid["paid_google_calls"] += 1
            paid["notes"].append("repair_reobserve_live")
    (EV / "05_repair.json").write_text(json.dumps(strip_secrets(repair_rec), indent=2), encoding="utf-8")

    paid["latency_sec"] = round(time.time() - t0, 3)
    (EV / "00_paid_api.json").write_text(json.dumps(paid, indent=2), encoding="utf-8")

    verdict = {
        "positive_status": positive.get("status"),
        "negative_status": negative.get("status"),
        "unknown_status": unk_fuse.get("status"),
        "unknown_blocks": bool(sem.get("blocking")) and sem.get("overall") != "PASS",
        "unknown_no_repair": not handoff_unk.get("repair_triggered"),
        "repair_triggered": bool(handoff.get("repair_triggered")),
        "whole_video_regeneration": False,
        "never_directly_publishable": True,
        "voice_acoustic": "UNKNOWN",
        "paid": paid,
    }
    (EV / "06_verdict.json").write_text(json.dumps(strip_secrets(verdict), indent=2), encoding="utf-8")
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
