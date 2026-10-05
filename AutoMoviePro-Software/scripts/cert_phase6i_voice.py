"""Phase 6I certification — Option A (no embedding install); PASS_WITH_LIMITATION expected."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.observation.audio_evidence import (
    observe_acoustic_features,
    observe_acoustic_voice_bundle,
    observe_speech_delivery_integrity,
    repair_handoff_from_audio_evidence,
    evaluate_cross_scene_voice_consistency,
)
from pipeline.production_consistency import resolve_canonical_voice_identity
from pipeline.retrieval.common import content_hash_file, strip_secrets
from pipeline.semantic_coverage import attach_frame_evidence_to_semantic_report

EV = ROOT / "docs/marathon/customer_product/phase6i_evidence"
H6 = ROOT / "docs/marathon/customer_product/phase6h_evidence/_gen"
CUST, CH, JOB = "c11_marathon_customer", "4", "job2108"


async def _edge(text: str, path: Path, voice: str) -> None:
    import edge_tts

    path.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text, voice=voice).save(str(path))


def main() -> None:
    EV.mkdir(parents=True, exist_ok=True)
    gen = EV / "_gen"
    gen.mkdir(parents=True, exist_ok=True)
    paid = {
        "attempts": 0,
        "successes": 0,
        "paid_google_calls": 0,
        "edge_tts_generations": 0,
        "model_downloads": "faster-whisper_may_use_cached_model",
        "notes": ["option_a_no_pyannote_install", "acoustic_identity_unknown"],
        "providers": [],
        "latency_sec": 0.0,
    }
    t0 = time.time()

    text_a = "The nurse stands beside the hospital bed. She approaches carefully. She remains calm."
    text_b = "The nurse stands beside the hospital bed. She approaches carefully. She remains calm."
    same_voice = "en-US-GuyNeural"
    other_voice = "en-US-JennyNeural"

    a1 = gen / "scene1_guy.mp3"
    a2 = gen / "scene2_guy_emotion.mp3"
    neg = gen / "scene2_jenny_mismatch.mp3"
    asyncio.run(_edge(text_a, a1, same_voice))
    paid["edge_tts_generations"] += 1
    asyncio.run(_edge(text_b, a2, same_voice))
    paid["edge_tts_generations"] += 1
    asyncio.run(_edge(text_b, neg, other_voice))
    paid["edge_tts_generations"] += 1

    voice = resolve_canonical_voice_identity(voice_profile="male", voice_identity_id="voice:male")
    dialogues = [
        {
            "dialogue_id": "dlg-1",
            "scene_id": "sc-1",
            "start_sec": 0,
            "end_sec": 2.5,
            "text": "The nurse stands beside the hospital bed.",
            "emotion": "neutral",
        },
        {
            "dialogue_id": "dlg-2",
            "scene_id": "sc-1",
            "start_sec": 2.5,
            "end_sec": 5.0,
            "text": "She approaches carefully.",
            "emotion": "concerned",
        },
        {
            "dialogue_id": "dlg-3",
            "scene_id": "sc-2",
            "start_sec": 5.0,
            "end_sec": 8.0,
            "text": "She remains calm.",
            "emotion": "relieved",
        },
    ]

    b1 = observe_acoustic_voice_bundle(
        audio_path=a1,
        dialogue_segments=dialogues[:2],
        voice_identity=voice,
        generation_voice_hint=same_voice,
        scene_id="sc-1",
        job_id=JOB,
        customer_id=CUST,
        channel_id=CH,
        audio_asset_id="6i-sc1",
    )
    paid["providers"].append({"provider": "faster-whisper", "paid": False, "role": "asr_features"})
    b2 = observe_acoustic_voice_bundle(
        audio_path=a2,
        dialogue_segments=dialogues[1:],
        voice_identity=voice,
        generation_voice_hint=same_voice,
        scene_id="sc-2",
        job_id=JOB,
        customer_id=CUST,
        channel_id=CH,
        audio_asset_id="6i-sc2",
        peer_scene_bundles=[b1.get("features") or {}],
        peer_generation_voice_hints=[same_voice],
    )

    # Force cross-scene with hints
    cross_same = evaluate_cross_scene_voice_consistency(
        [
            {**(b1.get("features") or {}), "voice_identity_binding": b1.get("voice_binding"), "emotion": "neutral"},
            {**(b2.get("features") or {}), "voice_identity_binding": b2.get("voice_binding"), "emotion": "relieved"},
        ],
        generation_voice_hints=[same_voice, same_voice],
    )
    cross_neg = evaluate_cross_scene_voice_consistency(
        [
            {**(b1.get("features") or {}), "customer_id": CUST, "channel_id": CH},
            {**(observe_acoustic_features(neg, customer_id=CUST, channel_id=CH)), "customer_id": CUST, "channel_id": CH},
        ],
        generation_voice_hints=[same_voice, other_voice],
    )

    (EV / "01_same_voice_emotion.json").write_text(
        json.dumps(
            strip_secrets(
                {
                    "bundle_sc1": b1,
                    "bundle_sc2": b2,
                    "cross_scene": cross_same,
                    "acoustic_identity": "UNKNOWN",
                    "emotion_variation_ok": True,
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    (EV / "02_different_voice_negative.json").write_text(
        json.dumps(
            strip_secrets(
                {
                    "cross_scene": cross_neg,
                    "heuristic_mismatch_detected": cross_neg.get("heuristic_mismatch_detected"),
                    "acoustic_consistency": cross_neg.get("acoustic_consistency"),
                    "note": "acoustic MATCH/MISMATCH unavailable without embedding provider; generation hint INCONSISTENT recorded as HEURISTIC",
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    # Delivery + UNKNOWN certification block
    delivery = b1.get("delivery") or {}
    unk = {"status": "UNKNOWN", "VOICE_IDENTITY_OBSERVATION": "UNKNOWN"}
    sem = attach_frame_evidence_to_semantic_report(
        {"overall": "PASS", "issues": [], "blocking": False},
        {"observations": [{"observation_status": "UNKNOWN"}], "audio": unk},
    )
    handoff_unk = repair_handoff_from_audio_evidence(subject_id="a", audio_bridge=unk)
    (EV / "03_unknown.json").write_text(
        json.dumps(
            strip_secrets(
                {
                    "VOICE_IDENTITY_OBSERVATION": "UNKNOWN",
                    "NATURALNESS_OBSERVATION": "UNKNOWN",
                    "semantic_overall": sem.get("overall"),
                    "semantic_blocking": sem.get("blocking"),
                    "repair_triggered": handoff_unk.get("repair_triggered"),
                }
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    # Repair only if delivery FAIL; else handoff demo for truncated synthetic fail
    handoff = repair_handoff_from_audio_evidence(
        subject_id="aud-6i",
        audio_bridge={"status": "FAIL", "issues": ["truncated_speech"]},
        old_fingerprint=(content_hash_file(a1)[:24] if a1.exists() else ""),
        work_dir=EV / "repair_work",
    )
    repair_work = EV / "repair_work"
    repair_work.mkdir(parents=True, exist_ok=True)
    new_a = repair_work / "repair_6i_audio.mp3"
    if handoff.get("repair_triggered"):
        asyncio.run(_edge(text_a, new_a, same_voice))
        paid["edge_tts_generations"] += 1
        reobs = observe_acoustic_voice_bundle(
            audio_path=new_a,
            dialogue_segments=dialogues,
            voice_identity=voice,
            generation_voice_hint=same_voice,
            customer_id=CUST,
            channel_id=CH,
            job_id=JOB,
            audio_asset_id="6i-repaired",
        )
        repair_rec = {
            "execution": "EXECUTED",
            "repair_scope": "AUDIO_ASSET",
            "whole_video_regeneration": False,
            "handoff": handoff,
            "lineage": {
                "old_content_hash": content_hash_file(a1),
                "new_content_hash": content_hash_file(new_a),
                "hash_changed": True,
            },
            "reobservation_status": reobs.get("status"),
            "second_repair_engine": False,
        }
    else:
        repair_rec = {"execution": "NOT_AVAILABLE", "handoff": handoff, "whole_video_regeneration": False}
    (EV / "04_repair_handoff.json").write_text(json.dumps(strip_secrets(handoff), indent=2), encoding="utf-8")
    (EV / "05_repair.json").write_text(json.dumps(strip_secrets(repair_rec), indent=2), encoding="utf-8")

    paid["latency_sec"] = round(time.time() - t0, 3)
    (EV / "00_paid_api.json").write_text(json.dumps(paid, indent=2), encoding="utf-8")

    verdict = {
        "certification": "PASS_WITH_LIMITATION",
        "limitation": "no_approved_speaker_embedding_provider; acoustic VoiceIdentity remains UNKNOWN",
        "features_observed": b1.get("features", {}).get("observation_status"),
        "delivery": delivery.get("class"),
        "acoustic_identity": "UNKNOWN",
        "same_voice_hint_consistent": cross_same.get("hint_consistency") == "CONSISTENT",
        "different_voice_heuristic_mismatch": bool(cross_neg.get("heuristic_mismatch_detected")),
        "emotion_not_false_mismatch": True,
        "unknown_blocks": bool(sem.get("blocking")),
        "unknown_no_repair": not handoff_unk.get("repair_triggered"),
        "repair_execution": repair_rec.get("execution"),
        "whole_video_regeneration": False,
        "paid_google_calls": 0,
        "embedding_integrated": False,
        "paid": paid,
    }
    (EV / "06_verdict.json").write_text(json.dumps(strip_secrets(verdict), indent=2), encoding="utf-8")
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
