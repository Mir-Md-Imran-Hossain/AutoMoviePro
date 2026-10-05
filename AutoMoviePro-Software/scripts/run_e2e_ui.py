#!/usr/bin/env python3
"""CLI wrapper: python scripts/run_e2e_ui.py --platform youtube --query '...' --tasks a"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.e2e_ui.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
