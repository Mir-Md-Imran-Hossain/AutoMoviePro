import os
import sys
sys.path.insert(0, ".")
os.environ.setdefault("USE_GEMINI_RESEARCH", "1")
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pipeline.custom_pipeline.topic_research import run_topic_research
from pipeline.custom_pipeline.script_quality_gate import evaluate_script_quality

target_niches = [
    "Human Brain, Biology & Medicine (মানবদেহ ও মস্তিষ্ক বিজ্ঞান)",
    "Psychology & Human Behavior (মানব মনস্তত্ত্ব ও আচরণ)",
    "Extreme Engineering & Megaprojects (মেগাপ্রজেক্ট ও স্থাপত্য)",
]

for n in target_niches:
    print(f"\n--- Testing: {n} ---", flush=True)
    res = run_topic_research(niche=n, video_type="short", save=False)
    p = res.get("payload", {})
    topic = p.get("seo_metadata", {}).get("selected_topic")
    q = evaluate_script_quality(p, video_type="short")
    print(f"Topic: {topic}", flush=True)
    print(f"Score: {q.get('score')} | OK: {q.get('ok')}", flush=True)
    print(f"Issues: {q.get('issues')}", flush=True)
    scenes = p.get("script_scenes", [])
    if scenes:
        print(f"Hook: {scenes[0].get('voiceover_script')[:90]}...", flush=True)
