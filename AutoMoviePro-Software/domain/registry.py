"""Canonical contract registry metadata (BUILD-01)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Type

from pydantic import BaseModel

from domain.channel import Channel, Session
from domain.engagement import Comment, EngagementAction, Message, Reply
from domain.errors import AppError
from domain.execution import Checkpoint, Job, JobAttempt
from domain.fact_pack import FactPack
from domain.localization import Localization
from domain.media import MediaAsset
from domain.publication import Publication, UploadJob, VideoMetadata
from domain.render import RenderArtifact, RenderJob, RenderManifest
from domain.research import TopicResearch
from domain.scene import Scene, VisualPlan, AudioPlan, SubtitlePlan
from domain.script import Script, Dialogue
from domain.topic import Topic
from domain.validation import ValidationResult


@dataclass(frozen=True)
class ContractSpec:
    name: str
    version: str
    model: Type[BaseModel]
    module: str
    status: str  # REQUIRED_NOW | EXISTING | FUTURE | DERIVED
    producers: tuple[str, ...]
    consumers: tuple[str, ...]


CONTRACT_REGISTRY: tuple[ContractSpec, ...] = (
    ContractSpec("Topic", "1.0.0", Topic, "domain.topic", "REQUIRED_NOW",
                 ("pipeline.niche_director", "pipeline.topic_scoring"),
                 ("pipeline.video_pipeline", "domain.adapters")),
    ContractSpec("TopicResearch", "1.0.0", TopicResearch, "domain.research", "FUTURE",
                 ("pipeline.trending_search",), ("domain.fact_pack",)),
    ContractSpec("FactPack", "1.0.0", FactPack, "domain.fact_pack", "REQUIRED_NOW",
                 ("pipeline.fact_pack",), ("pipeline.prompt_engineering", "domain.adapters")),
    ContractSpec("Script", "1.0.0", Script, "domain.script", "REQUIRED_NOW",
                 ("pipeline.niche_director",), ("pipeline.scene_builder",)),
    ContractSpec("Scene", "1.0.0", Scene, "domain.scene", "REQUIRED_NOW",
                 ("pipeline.scene_contract",), ("pipeline.scene_builder", "pipeline.media_assets")),
    ContractSpec("VisualPlan", "1.0.0", VisualPlan, "domain.scene", "REQUIRED_NOW",
                 ("pipeline.scene_contract",), ("pipeline.media_assets",)),
    ContractSpec("AudioPlan", "1.0.0", AudioPlan, "domain.scene", "REQUIRED_NOW",
                 ("pipeline.tts_google",), ("pipeline.compose",)),
    ContractSpec("SubtitlePlan", "1.0.0", SubtitlePlan, "domain.scene", "REQUIRED_NOW",
                 ("pipeline.subtitle_align",), ("pipeline.compose",)),
    ContractSpec("MediaAsset", "1.0.0", MediaAsset, "domain.media", "REQUIRED_NOW",
                 ("pipeline.media_assets",), ("pipeline.compose", "pipeline.asset_vault")),
    ContractSpec("Localization", "1.0.0", Localization, "domain.localization", "EXISTING",
                 ("pipeline.localization",), ("pipeline.master_lang",)),
    ContractSpec("Job", "1.0.0", Job, "domain.execution", "REQUIRED_NOW",
                 ("pipeline.job_fsm", "app.db"), ("pipeline.orchestrator", "pipeline.live_lab")),
    ContractSpec("Checkpoint", "1.0.0", Checkpoint, "domain.execution", "REQUIRED_NOW",
                 ("pipeline.generation_cache", "pipeline.resume_guard"), ("pipeline.orchestrator",)),
    ContractSpec("ValidationResult", "1.0.0", ValidationResult, "domain.validation", "REQUIRED_NOW",
                 ("pipeline.scene_contract", "pipeline.av_quality_gates"), ("domain.adapters",)),
    ContractSpec("UploadJob", "1.0.0", UploadJob, "domain.publication", "EXISTING",
                 ("publishers.upload_service",), ("publishers.human_browser",)),
    ContractSpec("Publication", "1.0.0", Publication, "domain.publication", "FUTURE",
                 ("publishers.upload_service",), ("app.db",)),
    ContractSpec("Channel", "1.0.0", Channel, "domain.channel", "EXISTING",
                 ("app.db",), ("app.main", "pipeline.video_pipeline")),
    ContractSpec("Session", "1.0.0", Session, "domain.channel", "EXISTING",
                 ("app.db",), ("app.main",)),
    ContractSpec("VideoMetadata", "1.0.0", VideoMetadata, "domain.publication", "EXISTING",
                 ("publishers.upload_meta",), ("publishers.upload_service",)),
    ContractSpec("Dialogue", "1.0.0", Dialogue, "domain.script", "REQUIRED_NOW",
                 ("pipeline.niche_director",), ("domain.scene",)),
    ContractSpec("JobAttempt", "1.0.0", JobAttempt, "domain.execution", "EXISTING",
                 ("pipeline.job_fsm",), ("pipeline.orchestrator",)),
    ContractSpec("AppError", "1.0.0", AppError, "domain.errors", "REQUIRED_NOW",
                 ("pipeline.orchestrator", "pipeline.contract_wiring"), ("domain.execution",)),
    ContractSpec("EngagementAction", "1.0.0", EngagementAction, "domain.engagement", "EXISTING",
                 ("pipeline.contract_wiring",), ("publishers.human_browser",)),
    ContractSpec("Comment", "1.0.0", Comment, "domain.engagement", "EXISTING",
                 ("pipeline.contract_wiring",), ("publishers.human_browser",)),
    ContractSpec("Reply", "1.0.0", Reply, "domain.engagement", "EXISTING",
                 ("pipeline.contract_wiring",), ("publishers.human_browser",)),
    ContractSpec("Message", "1.0.0", Message, "domain.engagement", "EXISTING",
                 ("pipeline.contract_wiring",), ("publishers.human_browser",)),
    ContractSpec("RenderArtifact", "1.0.0", RenderArtifact, "domain.render", "EXISTING",
                 ("pipeline.compose",), ("domain.render",)),
    ContractSpec("RenderManifest", "1.0.0", RenderManifest, "domain.render", "EXISTING",
                 ("pipeline.compose",), ("domain.render",)),
    ContractSpec("RenderJob", "1.0.0", RenderJob, "domain.render", "EXISTING",
                 ("pipeline.compose",), ("pipeline.orchestrator",)),
)


def get_contract_spec(name: str) -> ContractSpec | None:
    for spec in CONTRACT_REGISTRY:
        if spec.name == name:
            return spec
    return None


def registry_model_names() -> list[str]:
    return [spec.name for spec in CONTRACT_REGISTRY]


def all_contract_models() -> list[Type[BaseModel]]:
    return [spec.model for spec in CONTRACT_REGISTRY]
