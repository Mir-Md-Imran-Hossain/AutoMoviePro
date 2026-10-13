import os
import httpx
import dotenv
dotenv.load_dotenv()

from pipeline.custom_pipeline.session_keys import list_localization_keys

keys = list_localization_keys()
print(f"Total Google keys found: {len(keys)}")

test_prompt = '{"test": "hello"}'
for k in keys[:3]:
    for model in ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "Generate a json with keys 'topic' and 'hook' for a robotics short."}]}],
            "generationConfig": {
                "temperature": 0.7,
                "responseMimeType": "application/json"
            }
        }
        try:
            r = httpx.post(url, headers={"x-goog-api-key": k, "Content-Type": "application/json"}, json=payload, timeout=15)
            if r.status_code == 200:
                print(f"SUCCESS: model={model} key=...{k[-4:]}")
                data = r.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                print(f"Sample response: {text[:150]}")
                break
            else:
                print(f"FAILED: model={model} key=...{k[-4:]} code={r.status_code} body={r.text[:100]}")
        except Exception as e:
            print(f"EXC: {model} {e}")
    else:
        continue
    break
