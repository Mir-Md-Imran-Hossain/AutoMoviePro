"""Smoke: image provider chain + Goblin wiring (no live Goblin browser call)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_image_chain_orders():
    from pipeline.purpose_caps import image_provider_chain

    os.environ["GOBLIN_ENABLED"] = "true"
    os.environ["GOBLIN_PRIMARY"] = "false"
    os.environ["IMAGE_PROVIDER_PRIORITY"] = "pollinations,freetheai,goblin,google"
    chain = image_provider_chain()
    assert chain[0] == "pollinations"
    assert "goblin" in chain

    os.environ["GOBLIN_PRIMARY"] = "true"
    chain = image_provider_chain()
    assert chain[0] == "goblin"

    os.environ["GOBLIN_ENABLED"] = "false"
    chain = image_provider_chain()
    assert "goblin" not in chain


def test_ai_still_skips_failed_goblin():
    from pipeline import media_assets as m

    os.environ["GOBLIN_ENABLED"] = "true"
    os.environ["GOBLIN_PRIMARY"] = "false"
    os.environ["IMAGE_PROVIDER_PRIORITY"] = "goblin,pollinations"
    out = ROOT / "output" / "_test_goblin_chain.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    def boom(*_a, **_k):
        raise RuntimeError("goblin boom")

    def ok_poll(prompt, out_path, **_kw):
        out_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 5000)
        return out_path

    with patch("pipeline.goblin_image.goblin_generate_image", side_effect=boom), patch.object(
        m, "_pollinations_image", side_effect=ok_poll
    ):
        p = m._ai_still_via_chain("test", out, width=512, height=512)
    assert p.exists() and p.stat().st_size > 1000


if __name__ == "__main__":
    test_image_chain_orders()
    test_ai_still_skips_failed_goblin()
    print("OK goblin image chain tests")
