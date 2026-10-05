from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api_client import LicenseClient


def main() -> None:
    offline = LicenseClient("local", "tok")
    assert offline._offline() is True
    assert offline.heartbeat().get("ok") is True
    assert offline.promo_links() == []
    assert offline.sync_job({"title": "x"}).get("offline") is True

    live = LicenseClient("https://automoviepro.com", "abc123")
    assert live._offline() is False
    headers = live._headers()
    assert headers["Authorization"] == "Bearer abc123"
    print("OK license client offline + bearer header")


if __name__ == "__main__":
    main()
