"""Industrial VFX + FFmpeg + rendering integrity — AMP-004 Phase-08.

Extends BUILD-04D render_bridge / execute_render_request.
Does NOT create a second FFmpeg, quality, continuity, or publishability engine.
"""
from __future__ import annotations

from pipeline.rendering_integrity.contract import (
    RenderIntegrityContract,
    build_render_integrity_contract,
    render_contract_fingerprint,
)
from pipeline.rendering_integrity.gate import (
    RENDERING_INTEGRITY_GATE_FILE,
    load_rendering_integrity_gate,
)
from pipeline.rendering_integrity.preflight import RenderPreflightError, preflight_render_contract
from pipeline.rendering_integrity.production import (
    apply_production_render_preflight,
    run_production_rendering_gate,
)

__all__ = [
    "RenderIntegrityContract",
    "build_render_integrity_contract",
    "render_contract_fingerprint",
    "RenderPreflightError",
    "preflight_render_contract",
    "apply_production_render_preflight",
    "run_production_rendering_gate",
    "RENDERING_INTEGRITY_GATE_FILE",
    "load_rendering_integrity_gate",
]
