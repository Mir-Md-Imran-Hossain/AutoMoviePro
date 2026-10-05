"""One-shot repair for clip_17 dialogue cutoff using TTS over Agnes picture."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.api_keys import load_api_keys
from pipeline.av_quality_gates import detect_dialogue_cutoff, detect_tail_hold
from pipeline.scene_builder import _repair_cutoff_with_complete_tts

work = ROOT / "output" / "Chernobyl_30_TrainCompare" / "clip_17"
src = work / "agnes_00_metaphor.mp4"
dest = work / "scene_00_metaphor.mp4"
narr = (work / "narration_en.txt").read_text(encoding="utf-8").strip()
keys = load_api_keys().get("google") or []
print("keys", len(keys), "src", src.exists(), "narr", narr[:80])
out = _repair_cutoff_with_complete_tts(
    video_src=src,
    dest=dest,
    narration=narr,
    google_api_keys=keys,
    size="1080x1920",
    work=work,
    idx=0,
)
print("out", out)
if out and out.exists():
    print("cutoff", detect_dialogue_cutoff(out, narration_text=narr, lang="en"))
    print("hold", detect_tail_hold(out))
