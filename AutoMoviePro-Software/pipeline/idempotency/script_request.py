"""Script generation request identity (BUILD-04C)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from pipeline.idempotency.fingerprint import compute_fingerprint, hash_text


SCRIPT_CONTRACT_VERSION = "1.0.0"
DEFAULT_SCRIPT_PROVIDER = "llm_router"
DEFAULT_SCRIPT_MODEL = "purpose-script"


@dataclass
class ScriptRequestSpec:
    job_id: str
    topic: str
    topic_identity: str
    niche: str
    niche_id: int
    video_type: str
    max_seconds: int
    language: str
    provider: str
    model: str
    research_notes_hash: str = ""
    fact_pack_id: str = ""
    fact_pack_hash: str = ""
    prompt_version: str = ""
    prompt_template_hash: str = ""
    blocked_products: list[str] = field(default_factory=list)
    channel_specials: dict[str, str] = field(default_factory=dict)
    revision_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_inputs(self) -> dict[str, Any]:
        return {
            "topic": self.topic.strip(),
            "topic_identity": self.topic_identity.strip(),
            "niche": self.niche.strip(),
            "niche_id": int(self.niche_id),
            "video_type": self.video_type.strip().lower(),
            "max_seconds": int(self.max_seconds),
            "language": self.language.strip().lower(),
            "research_notes_hash": self.research_notes_hash.strip(),
            "fact_pack_id": self.fact_pack_id.strip(),
            "fact_pack_hash": self.fact_pack_hash.strip(),
            "prompt_version": self.prompt_version.strip(),
            "prompt_template_hash": self.prompt_template_hash.strip(),
            "blocked_products": sorted(p.strip() for p in self.blocked_products if p.strip()),
            "channel_specials": {
                k.strip(): str(v or "").strip()
                for k, v in sorted(self.channel_specials.items())
            },
            "revision_id": self.revision_id.strip(),
            "script_contract_version": SCRIPT_CONTRACT_VERSION,
        }

    def fingerprint(self) -> str:
        return compute_script_fingerprint(self)

    @property
    def entity_id(self) -> str:
        rev = self.revision_id.strip()
        suffix = f"-{rev}" if rev else ""
        tid = self.topic_identity.strip() or hash_text(self.topic.strip())[:12]
        return f"script-{self.niche_id:04d}-{tid[:16]}{suffix}"


def compute_script_fingerprint(spec: ScriptRequestSpec) -> str:
    return compute_fingerprint(
        job_id=spec.job_id,
        stage="script",
        entity_id=spec.entity_id,
        contract_version=SCRIPT_CONTRACT_VERSION,
        provider=spec.provider,
        model=spec.model,
        inputs=spec.normalized_inputs(),
    )


def topic_identity_from_parts(*, topic: str, niche: str, niche_id: int) -> str:
    raw = f"{niche_id}|{niche.strip().lower()}|{topic.strip().lower()}"
    return hash_text(raw)[:24]


def load_fact_pack_identity(work_dir) -> tuple[str, str]:
    """Return (fact_pack_id, fact_pack_hash) from work dir if present."""
    from pathlib import Path
    import json

    work = Path(work_dir)
    fp_path = work / "FACT_PACK.json"
    if fp_path.is_file():
        try:
            data = json.loads(fp_path.read_text(encoding="utf-8"))
            fid = str(data.get("id") or data.get("topic") or "factpack")[:64]
            return fid, hash_text(fp_path.read_text(encoding="utf-8"))[:32]
        except Exception:
            pass
    factpack_dir = work / "factpack"
    if factpack_dir.is_dir():
        files = sorted(factpack_dir.glob("*.json"))
        if files:
            try:
                text = files[0].read_text(encoding="utf-8")
                data = json.loads(text)
                fid = str(data.get("topic") or files[0].stem)[:64]
                return fid, hash_text(text)[:32]
            except Exception:
                pass
    return "", ""


def director_prompt_identity() -> tuple[str, str]:
    """Prompt version + template hash for director script generation."""
    from pipeline.prompt_registry import get_prompt_meta
    from pipeline.niche_director import DIRECTOR_SYSTEM, ELEMENT_GUIDE

    meta = get_prompt_meta("director_system")
    version = str(meta.get("version") or "unknown")
    template_hash = hash_text(DIRECTOR_SYSTEM + ELEMENT_GUIDE)[:32]
    return version, template_hash
