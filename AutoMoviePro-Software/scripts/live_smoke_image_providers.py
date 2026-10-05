"""Live smoke: Workers AI + dedicated Google image keys.

Usage (from AutoMoviePro-Software):
  python scripts/live_smoke_image_providers.py
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)
    os.environ["AMP_MEDIA_CALL_GAP_SEC"] = "0"

    from pipeline.custom_pipeline.media_call_guard import (
        _circuit_open_until,
        _created,
        _persist,
        reset_runtime_state,
    )
    from pipeline.custom_pipeline.media_providers import image_google, image_workers_ai
    from pipeline.dedicated_api_registry import list_image_google_keys, list_workers_ai_credentials

    reset_runtime_state(reload=False)
    _circuit_open_until.clear()
    _created.clear()
    _persist()

    out = ROOT / "Output" / "_live_smoke_image"
    out.mkdir(parents=True, exist_ok=True)
    prompt = (
        "Photoreal ChatGPT Custom Instructions settings panel on a laptop screen, "
        "Save button visible, dark UI, no human face"
    )

    print("WorkersAI pairs:", len(list_workers_ai_credentials()))
    print("IMAGE_GOOGLE keys:", [k[-4:] for k in list_image_google_keys()])

    w_path = out / "workers_ai_smoke.png"
    w = image_workers_ai(prompt, w_path, w=768, h=1024, seed=42)
    print(
        "WORKERS_AI:",
        "OK" if w and Path(w).is_file() else "FAIL",
        Path(w).stat().st_size if w and Path(w).is_file() else 0,
    )

    g_path = out / "google_image_smoke.png"
    g = image_google(prompt, g_path, w=768, h=1024)
    print(
        "GOOGLE_IMAGE:",
        "OK" if g and Path(g).is_file() else "FAIL",
        Path(g).stat().st_size if g and Path(g).is_file() else 0,
    )

    ok_w = bool(w and Path(w).is_file() and Path(w).stat().st_size > 2000)
    # Google may be quota-exhausted across the pool — still exit 0 if Workers works
    # Exit 2 only if Workers fails (critical Pollinations fallback)
    if not ok_w:
        return 2
    if not (g and Path(g).is_file()):
        print(
            "NOTE: Google image keys all 429/403 — add fresh AI Studio keys to "
            "IMAGE_GOOGLE_API_KEY_1/2. Chain falls through to Agnes/Pollinations/Workers AI."
        )
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
