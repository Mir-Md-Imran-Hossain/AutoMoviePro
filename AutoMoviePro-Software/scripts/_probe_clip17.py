from __future__ import annotations

import json
from pathlib import Path

from pipeline.av_quality_gates import (
    detect_av_length_match,
    detect_dialogue_cutoff,
    detect_duration_window,
    detect_tail_hold,
)
from pipeline.compose import ffprobe_duration

work = Path(r"output/Chernobyl_30_TrainCompare/clip_17")
narr = ""
for p in [work / "narration_en.txt", work / "narration_en_raw.txt"]:
    if p.exists():
        narr = p.read_text(encoding="utf-8").strip()
        print("NARR:", narr)
        print("spoken_words:", len(narr.split()))
        break

for c in sorted(work.glob("*.mp4")):
    vd = ffprobe_duration(c)
    print(f"\n=== {c.name} dur={vd:.2f}s size={c.stat().st_size} ===")
    cut = detect_dialogue_cutoff(c, narration_text=narr, lang="en")
    hold = detect_tail_hold(c)
    print("cutoff_passed:", cut.get("passed"), "issues:", cut.get("issues"))
    for k in ("end_rms", "spoken_est", "silence_tail_sec", "detail"):
        if k in cut:
            print(f"  {k}={cut.get(k)}")
    print("hold_passed:", hold.get("passed"), "issues:", hold.get("issues"))
    print("dur_win:", detect_duration_window(c, label=c.stem))
    print("av:", detect_av_length_match(c, None))

for j in sorted(work.glob("scene_00_critique*.json")):
    d = json.loads(j.read_text(encoding="utf-8"))
    print(
        f"\nCRITIQUE {j.name}: score={d.get('match_score')} passed={d.get('passed')} "
        f"critical={d.get('critical_issues')} issues={d.get('issues')}"
    )

for name in (
    "scene_00_prior_issues.json",
    "scene_00_AV_FAIL.txt",
    "scene_00_USED_IMAGE_FALLBACK.txt",
    "scene_00_source.txt",
):
    p = work / name
    if p.exists():
        print(f"\nFILE {name}:\n{p.read_text(encoding='utf-8')[:500]}")
