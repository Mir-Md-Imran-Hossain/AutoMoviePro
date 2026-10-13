import os
import sys
sys.path.insert(0, ".")
import httpx
import dotenv
dotenv.load_dotenv()

from pipeline.custom_pipeline.session_keys import list_localization_keys

keys = list_localization_keys()
print(f"Total Google keys found: {len(keys)}")

active_keys = []
models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"]

for idx, k in enumerate(keys):
    worked = False
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "Reply JSON: {\"ok\": true}"}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        try:
            r = httpx.post(url, headers={"x-goog-api-key": k, "Content-Type": "application/json"}, json=payload, timeout=8)
            if r.status_code == 200:
                print(f"Key #{idx+1} (...{k[-4:]}) WORKS with {m}")
                active_keys.append((k, m))
                worked = True
                break
        except Exception:
            pass
    if not worked:
        print(f"Key #{idx+1} (...{k[-4:]}) INACTIVE / 404")

print(f"\nTotal working keys: {len(active_keys)} out of {len(keys)}")
