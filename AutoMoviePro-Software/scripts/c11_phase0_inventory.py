"""C11 Phase 0 helper — provider inventory without printing secrets."""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def presence(name: str) -> dict:
    v = (os.environ.get(name) or "").strip()
    return {
        "name": name,
        "status": "SET" if v else "EMPTY",
        "length": len(v) if v else 0,
    }


def main() -> None:
    from app.config import DATA_DIR, safe_config_diagnostics
    from app.release_identity import RELEASE_VERSION, get_release_identity
    from pipeline.compose import probe_media_tool_capability, media_tool_versions
    from pipeline.api_keys import collect_all_keys

    keys = collect_all_keys()
    summary = {}
    if isinstance(keys, dict):
        for k, v in keys.items():
            if isinstance(v, (list, tuple)):
                summary[k] = {"count": len([x for x in v if x]), "kind": "list"}
            elif isinstance(v, dict):
                summary[k] = {"count": len(v), "kind": "dict"}
            elif v:
                summary[k] = {"present": True, "kind": type(v).__name__}
            else:
                summary[k] = {"present": False}

    interesting = [
        "GOOGLE_API_KEY",
        "GOOGLE_API_KEY_1",
        "GEMINI_API_KEY",
        "AGNES_API_KEY",
        "AGNES_API_KEY_1",
        "AGNES_API_BASE_URL",
        "YOUTUBE_API_KEY",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "OPENAI_API_KEY",
        "EDGE_TTS",
    ]
    env_presence = [presence(n) for n in interesting]
    # also numbered google/agnes
    for i in range(1, 6):
        env_presence.append(presence(f"GOOGLE_API_KEY_{i}"))
        env_presence.append(presence(f"AGNES_API_KEY_{i}"))

    out = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "release_version": RELEASE_VERSION,
        "release_identity": get_release_identity(include_media=True),
        "media": probe_media_tool_capability(),
        "media_versions": media_tool_versions(),
        "data_dir": str(DATA_DIR),
        "disk_free_gb": round(shutil.disk_usage(str(ROOT)).free / 1e9, 2),
        "utc_now": datetime.now(timezone.utc).isoformat(),
        "env_presence": env_presence,
        "api_keys_summary": summary,
        "safe_config": {
            k: v
            for k, v in (safe_config_diagnostics() or {}).items()
            if not any(x in str(k).lower() for x in ("password", "secret", "token", "key_value"))
        },
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
