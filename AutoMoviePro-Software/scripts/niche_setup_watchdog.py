#!/usr/bin/env python3
"""Watchdog: keep niche_setup_marathon.py running until COMPLETE (10-min checks)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CP = ROOT.parent / "docs" / "marathon" / "niche_setup" / "checkpoint.json"
PY = sys.executable
SCRIPT = ROOT / "scripts" / "niche_setup_marathon.py"
INTERVAL = 600


def status() -> dict:
    if not CP.is_file():
        return {}
    try:
        return json.loads(CP.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    os.environ.setdefault("AMP_NICHE_MARATHON_CONTINUE", "1")
    while True:
        st = status()
        if st.get("status") == "COMPLETE" and len(st.get("completed") or []) >= 150:
            print("WATCHDOG: marathon COMPLETE", flush=True)
            return 0
        print(f"WATCHDOG: launching marathon next_id={st.get('next_id')} status={st.get('status')}", flush=True)
        proc = subprocess.run(
            [PY, str(SCRIPT), "--no-llm"],
            cwd=str(ROOT),
            env={**os.environ, "AMP_NICHE_MARATHON_CONTINUE": "1", "PYTHONIOENCODING": "utf-8"},
        )
        st = status()
        print(f"WATCHDOG: exit={proc.returncode} status={st.get('status')} done={len(st.get('completed') or [])}", flush=True)
        if st.get("status") == "COMPLETE" and len(st.get("completed") or []) >= 150:
            return 0
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
