import os
import sys
import json
import time
sys.path.insert(0, ".")
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import dotenv
import httpx
dotenv.load_dotenv()

from pipeline.custom_pipeline.session_keys import list_localization_keys
from pipeline.custom_pipeline.prompts import build_topic_research_prompt, SYSTEM_JSON_ONLY
from pipeline.custom_pipeline.topic_research import normalize_payload, parse_grok_json
from pipeline.custom_pipeline.script_quality_gate import evaluate_script_quality

keys = list_localization_keys()
active_key = [k for k in keys if k.endswith("GnmI")][0]

niche = "Deep Ocean Exploration & Marine Mysteries (গভীর সমুদ্র ও রহস্য)"
prompt = build_topic_research_prompt(
    niche=niche,
    video_type="short",
    audience="General Audience / Curious Viewers",
)

url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
payload = {
    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
    "systemInstruction": {"parts": [{"text": SYSTEM_JSON_ONLY}]},
    "generationConfig": {
        "temperature": 0.7,
        "responseMimeType": "application/json"
    }
}

t0 = time.time()
r = httpx.post(url, headers={"x-goog-api-key": active_key, "Content-Type": "application/json"}, json=payload, timeout=60)
elapsed = round(time.time() - t0, 2)
print(f"Status: {r.status_code} in {elapsed}s")

if r.status_code == 200:
    data = r.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = parse_grok_json(text)
    norm = normalize_payload(parsed, video_type="short")
    quality = evaluate_script_quality(norm, video_type="short")
    with open("Output/gemini_ocean_sample.json", "w", encoding="utf-8") as f:
        json.dump(norm, f, ensure_ascii=False, indent=2)
    print(f"Selected Topic: {norm.get('seo_metadata', {}).get('selected_topic')}")
    print(f"Quality Score: {quality.get('score')} | OK: {quality.get('ok')}")
    print(f"Issues: {quality.get('issues')}")
    scenes = norm.get("script_scenes", [])
    print(f"\n--- Shot 1 Hook ---")
    print(scenes[0].get("voiceover_script") if scenes else "No scenes")
    print(f"\n--- Shot 2 Visual Metaphor ---")
    print(scenes[1].get("voiceover_script") if len(scenes) > 1 else "")
    print(f"\n--- Shot 5 Mid-roll Hook ---")
    print(scenes[4].get("voiceover_script") if len(scenes) > 4 else "")
else:
    print(r.text)
