from __future__ import annotations

"""Smoke-test one Agnes dialogue video clip (no secret printing)."""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from app import db as store
from pipeline.media_assets import generate_agnes_dialogue_clip


def main() -> int:
    store.init_db()
    ch = store.list_channels()[0]
    key = (ch.get("agnes_api") or "").strip()
    if not key:
        print("NO_AGNES_KEY")
        return 2
    out = ROOT / "output" / "_agnes_smoke" / "clip0.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    path = generate_agnes_dialogue_clip(
        api_key=key,
        product_name="OnePlus 13",
        element="design",
        visual_prompt="cinematic orbit around OnePlus 13 circular Hasselblad camera island, studio light",
        narration_hint="ডিজাইন ও ক্যামেরা আইল্যান্ড দেখাই",
        out_path=out,
        size="1080x1920",
        duration_hint=5.0,
        max_poll=24,
    )
    if path and path.exists():
        print("AGNES_OK", path, path.stat().st_size)
        return 0
    print("AGNES_FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
