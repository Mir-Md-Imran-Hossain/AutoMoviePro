#!/usr/bin/env python3
"""AMP-001 — Run all marathon and regression test suites."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUITES = [
    "scripts/test_build_00r_imports.py",
    "scripts/test_build01_contracts.py",
    "scripts/test_build02_wiring.py",
    "scripts/test_build03_idempotency.py",
    "scripts/test_build04g_topic_research.py",
    "scripts/test_build04g_hardening.py",
    "scripts/test_build04g_h1_idempotency_concurrency.py",
    "scripts/test_marathon_task002_reserve_atomicity.py",
    "scripts/test_marathon_task003_long_short_isolation.py",
    "scripts/test_marathon_task004_fail_closed_gate.py",
    "scripts/test_marathon_task005_research_provider_boundary.py",
    "scripts/test_marathon_tasks_006_020.py",
]


def main() -> int:
    failed: list[str] = []
    for script in SUITES:
        print(f"\n=== {script} ===")
        r = subprocess.run([sys.executable, script], cwd=ROOT)
        if r.returncode != 0:
            failed.append(script)
    print("\n" + "=" * 60)
    if failed:
        print(f"FAILED ({len(failed)}): " + ", ".join(failed))
        return 1
    print(f"ALL {len(SUITES)} SUITES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
