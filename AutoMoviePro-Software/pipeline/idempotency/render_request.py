"""Render request identity (BUILD-04D)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pipeline.idempotency.fingerprint import compute_fingerprint
from pipeline.idempotency.render_manifest import RenderAssemblyManifest


RENDER_CONTRACT_VERSION = "1.0.0"
DEFAULT_RENDER_PROVIDER = "ffmpeg"
DEFAULT_RENDER_MODEL = "compose-v1"


@dataclass
class RenderRequestSpec:
    job_id: str
    manifest: RenderAssemblyManifest
    provider: str = DEFAULT_RENDER_PROVIDER
    model: str = DEFAULT_RENDER_MODEL
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_inputs(self) -> dict[str, Any]:
        return {
            **self.manifest.normalized(),
            "provider": self.provider.strip().lower(),
            "model": self.model.strip().lower(),
            "render_contract_version": RENDER_CONTRACT_VERSION,
        }

    def fingerprint(self) -> str:
        return compute_render_fingerprint(self)

    @property
    def entity_id(self) -> str:
        return f"render-{self.job_id}"


def compute_render_fingerprint(spec: RenderRequestSpec) -> str:
    return compute_fingerprint(
        job_id=spec.job_id,
        stage="render",
        entity_id=spec.entity_id,
        contract_version=RENDER_CONTRACT_VERSION,
        provider=spec.provider,
        model=spec.model,
        inputs=spec.normalized_inputs(),
    )
