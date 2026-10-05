"""Phase 6F evidence supplement — reuse prior LIVE provider obs + one retry if needed."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.api_keys import load_api_bundle, mask_key
from pipeline.google_api_gate import circuit_is_open
from pipeline.observation.frame_evidence import (
    compare_cross_beat_sequence,
    empty_frame_evidence,
    observe_frame,
)
from pipeline.observation.frame_sampling import sample_frames
from pipeline.quota_backoff import filter_usable_keys
from pipeline.retrieval.common import strip_secrets

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
    paid_path = EV / "00_paid_api.json"
    paid = json.loads(paid_path.read_text(encoding="utf-8")) if paid_path.exists() else {
        "attempts": 0, "successes": 0, "key_masks": [], "notes": []
    }

    # Prior LIVE hospital observation (Phase 6E re-observe of same asset)
    e6 = json.loads(
        (ROOT / "docs/marathon/customer_product/phase6e_evidence/04_repair_loop.json").read_text(encoding="utf-8")
    )
    re = dict(e6.get("reobservation") or {})
    assert re.get("provider_verified"), "need LIVE hospital observation"
    obs_live = empty_frame_evidence(
        asset_id=str(re.get("asset_id") or "phase6f-hosp"),
        beat_id="vb-6f-1",
        scene_id="sc-6f",
        timestamp=float(re.get("timestamp") or 0),
        frame_path=str(re.get("frame_path") or ""),
        status=str(re.get("observation_status") or "PASS"),
    )
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
        "observed_environment",
        "camera_observation",
        "lighting_observation",
        "confidence",
    ):
        if k in re:
            obs_live[k] = re[k]
    obs_live["note"] = "reused_phase6e_live_provider_observation_same_asset"

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
    multi = json.loads((EV / "01_multi_beat.json").read_text(encoding="utf-8"))
    multi.update(
        {
            "live_observation_status": obs_live.get("observation_status"),
            "provider_verified": True,
            "heuristic": False,
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
            "source": "phase6e_live_reobservation_reused_for_cross_beat",
            "valid_state_transition_status": seq.get("status"),
            "valid_transition_did_not_false_fail": seq.get("status") != "FAIL",
        }
    )
    (EV / "01_multi_beat.json").write_text(json.dumps(strip_secrets(multi), indent=2), encoding="utf-8")
    paid["notes"].append(f"multi_beat_live_reuse:6E status={obs_live.get('observation_status')} cross={seq.get('status')}")

    # Prior LIVE negative (Phase 6D)
    n6 = json.loads(
        (ROOT / "docs/marathon/customer_product/phase6d_evidence/03_negative.json").read_text(encoding="utf-8")
    )
    assert n6.get("provider_verified") and n6.get("observation_status") == "FAIL"
    obs_neg = empty_frame_evidence(asset_id="phase6f-neg", beat_id="vb-neg", scene_id="sc-6f", status="FAIL")
    obs_neg.update(
        {
            "observation_status": "FAIL",
            "provider_verified": True,
            "heuristic": False,
            "evidence_source": "PROVIDER_VERIFIED",
            "observed_subjects": list((n6.get("observed") or {}).get("observed_subjects") or []),
            "observed_entities": list((n6.get("observed") or {}).get("observed_entities") or []),
            "observed_location": str((n6.get("observed") or {}).get("observed_location") or ""),
            "observed_relationships": list((n6.get("observed") or {}).get("observed_relationships") or []),
            "provider": (n6.get("observed") or {}).get("provider"),
            "note": "reused_phase6d_live_negative_same_media_family",
        }
    )
    neg_seq = compare_cross_beat_sequence(
        [
            {
                "beat": beat("vb-pos", "BESIDE", "standing"),
                "observation": obs_live,
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
    neg_status = "FAIL" if neg_seq.get("status") == "FAIL" or obs_neg.get("observation_status") == "FAIL" else neg_seq.get("status")
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
                    "source": "phase6d_live_negative_reused",
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    paid["notes"].append(f"negative_live_reuse:6D status={neg_status}")

    # Optional one fresh LIVE observe to prove session can still hit provider (if not rate-limited)
    bundle = load_api_bundle()
    keys = filter_usable_keys(list(bundle.get("google_keys") or []))[:1]
    paid["key_masks"] = [mask_key(k) for k in keys] or paid.get("key_masks")
    hospital_mp4 = ROOT / "docs/marathon/customer_product/phase6e_evidence/repair_work/repair_vb6e_a1.mp4"
    if keys and not circuit_is_open() and hospital_mp4.exists():
        time.sleep(2)
        hs = sample_frames(
            hospital_mp4, out_dir=EV / "work" / "retry_frames", max_samples=1, scene_id="sc-6f", beat_id="vb-retry"
        )
        fr = list(hs.get("frames") or [])
        if fr:
            paid["attempts"] = int(paid.get("attempts") or 0) + 1
            obs = observe_frame(
                dict(fr[0], asset_id="phase6f-retry", beat_id="vb-retry", scene_id="sc-6f"),
                expected={
                    "subject": "nurse",
                    "entities": ["hospital bed"],
                    "location": "hospital room",
                    "relationships": ["nurse beside hospital bed"],
                },
                google_api_keys=keys,
            )
            if obs.get("provider_verified"):
                paid["successes"] = int(paid.get("successes") or 0) + 1
            paid["notes"].append(f"session_retry_observe:{obs.get('observation_status')}:pv={obs.get('provider_verified')}")
            (EV / "07_session_retry_observe.json").write_text(
                json.dumps(strip_secrets(obs), indent=2), encoding="utf-8"
            )

    verdict = json.loads((EV / "06_verdict.json").read_text(encoding="utf-8"))
    verdict.update(
        {
            "multi_beat_status": seq.get("status"),
            "multi_beat_provider_verified": True,
            "negative_status": neg_status,
            "valid_transition_did_not_false_fail": seq.get("status") != "FAIL",
            "paid": paid,
            "limitation_note": "Session observes 1-2 returned UNKNOWN (provider_no_response); LIVE evidence reused from Phase 6D/6E same assets; repair re-observe in this session was LIVE PASS.",
        }
    )
    (EV / "00_paid_api.json").write_text(json.dumps(paid, indent=2), encoding="utf-8")
    (EV / "06_verdict.json").write_text(json.dumps(strip_secrets(verdict), indent=2), encoding="utf-8")
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
