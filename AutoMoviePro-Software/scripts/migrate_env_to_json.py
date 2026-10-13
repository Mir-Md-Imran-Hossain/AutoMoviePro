import os
import json
from pathlib import Path

env_file = Path("E:/All Project/AutoMovie_Pro_SAAS_Final_Update/AutoMoviePro-Software/.env")
data_dir = Path("E:/All Project/AutoMovie_Pro_SAAS_Final_Update/AutoMoviePro-Software/app/data/api_matrix")
data_dir.mkdir(parents=True, exist_ok=True)
json_file = data_dir / "api_matrix.json"

env_vars = {}
with open(env_file, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            if "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()

config = {
    "grok_primary_key": env_vars.get("AGENT_GROK_API_KEY_1", ""),
    "grok_fallback_key": env_vars.get("TOPIC_GROK_API_KEY_1", ""),
    "google_media_key": env_vars.get("IMAGE_GOOGLE_API_KEY_1", ""),
    "google_tts_keys": {
        "en": [],
        "bn": [env_vars.get("GOOGLE_API_KEY_BN_PRIMARY", ""), env_vars.get("GOOGLE_API_KEY_BN_SECONDARY", "")],
        "hi": [],
        "ur": [],
        "ta": [env_vars.get("GOOGLE_API_KEY_TA_PRIMARY", ""), env_vars.get("GOOGLE_API_KEY_TA_SECONDARY", "")],
        "ml": [env_vars.get("GOOGLE_API_KEY_ML_PRIMARY", ""), env_vars.get("GOOGLE_API_KEY_ML_SECONDARY", "")]
    },
    "google_pro_key": env_vars.get("GOOGLE_PAID_MASTER_KEY", ""),
    "google_pro_keys_by_lang": {
        "en": "", "bn": "", "hi": "", "ur": "", "ta": "", "ml": ""
    },
    "openrouter_key": env_vars.get("OPENROUTER_API_KEY_1", ""),
    "agnes_key": env_vars.get("AGNES_API_KEY_1", ""),
    "pexels_key": env_vars.get("PEXELS_API_KEY_1", ""),
    "pollinations_key": env_vars.get("POLLINATIONS_API_KEY_1", "")
}

with open(json_file, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)

print(f"Migrated keys to {json_file}")
