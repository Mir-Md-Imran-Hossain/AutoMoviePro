"""AMP-004 Phase-09 — Industrial E2E QA package (integration only)."""
from __future__ import annotations

from pipeline.e2e_industrial.authority_audit import (
    audit_authority_singletons,
    audit_production_bypasses,
    audit_production_call_graph,
)
from pipeline.e2e_industrial.fixture import FIXTURE_JOB_ID, build_e2e_director_plan, materialize_e2e_fixture
from pipeline.e2e_industrial.media_tools import discover_media_tools, observe_final_media
from pipeline.e2e_industrial.runner import run_e2e_industrial

__all__ = [
    "FIXTURE_JOB_ID",
    "audit_authority_singletons",
    "audit_production_bypasses",
    "audit_production_call_graph",
    "build_e2e_director_plan",
    "discover_media_tools",
    "materialize_e2e_fixture",
    "observe_final_media",
    "run_e2e_industrial",
]
