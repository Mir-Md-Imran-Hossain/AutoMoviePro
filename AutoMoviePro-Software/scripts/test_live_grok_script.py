import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pipeline.custom_pipeline.topic_research import run_topic_research

def test_single():
    niche = sys.argv[1] if len(sys.argv) > 1 else "Science & Technology"
    print(f"Testing script generation for niche: {niche}...")
    res = run_topic_research(niche=niche, video_type="short", save=False)
    p = res["payload"]
    seo = p.get("seo_metadata", {})
    q = res.get("script_quality", {})
    
    print("=" * 60)
    print("TOPIC:", seo.get("selected_topic"))
    print("TITLES:", seo.get("suggested_titles"))
    print("QUALITY SCORE:", q.get("score"))
    print("QUALITY OK:", q.get("ok"))
    print("BREAKDOWN:", json.dumps(q.get("breakdown", {}), indent=2))
    print("ISSUES:", q.get("issues", []))
    print("=" * 60)
    print("SCENES:")
    for s in p.get("script_scenes", []):
        print(f"Shot {s.get('shot_number')} [{s.get('shot_duration_seconds')}s] ({s.get('emotion_tag')}):")
        print(f"  VO: {s.get('voiceover_script')}")
        print(f"  VISUAL: {s.get('visual_prompt')[:100]}...")
        print()

    out_file = ROOT / "Output" / "test_script_sample.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved payload to: {out_file}")

if __name__ == "__main__":
    test_single()
