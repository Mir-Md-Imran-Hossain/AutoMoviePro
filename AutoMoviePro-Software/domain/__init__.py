"""AutoMovie Pro canonical domain & data contracts (BUILD-01)."""
from domain.adapters import (
    checkpoint_from_meta,
    fact_pack_from_legacy,
    job_from_fsm_dict,
    scene_from_legacy_contract,
    script_from_plan,
    topic_from_plan,
    validation_from_preflight,
)
from domain.channel import Channel, Session
from domain.common import ContractBase, ExternalRef, TimestampedContract, new_id
from domain.enums import (
    AssetType,
    ErrorCategory,
    EvidenceStatus,
    JobState,
    LifecycleStatus,
    ResearchStatus,
    Verdict,
)
from domain.errors import AppError
from domain.execution import Checkpoint, Job, JobAttempt
from domain.fact_pack import FactClaim, FactPack
from domain.localization import Localization, LocalizedDialogue, VoiceProfile
from domain.media import AudioAsset, ImageAsset, MediaAsset, Provenance, VideoAsset, VisualAsset
from domain.publication import Publication, PublicationTarget, UploadJob, VideoMetadata
from domain.registry import CONTRACT_REGISTRY, ContractSpec, get_contract_spec, registry_model_names
from domain.research import ResearchEvidence, TopicResearch
from domain.scene import AudioPlan, Scene, ShotPlan, SubtitleCue, SubtitlePlan, VisualEvidence, VisualPlan
from domain.script import Dialogue, Script, ScriptSection
from domain.topic import Topic
from domain.validation import ValidationIssue, ValidationResult

__all__ = [
    "CONTRACT_REGISTRY",
    "ContractSpec",
    "get_contract_spec",
    "registry_model_names",
    "ContractBase",
    "TimestampedContract",
    "ExternalRef",
    "new_id",
    "Topic",
    "TopicResearch",
    "ResearchEvidence",
    "FactPack",
    "FactClaim",
    "Script",
    "ScriptSection",
    "Dialogue",
    "Scene",
    "VisualPlan",
    "AudioPlan",
    "SubtitlePlan",
    "SubtitleCue",
    "VisualEvidence",
    "ShotPlan",
    "MediaAsset",
    "VisualAsset",
    "AudioAsset",
    "VideoAsset",
    "ImageAsset",
    "Provenance",
    "Localization",
    "LocalizedDialogue",
    "VoiceProfile",
    "Job",
    "JobAttempt",
    "Checkpoint",
    "UploadJob",
    "Publication",
    "PublicationTarget",
    "VideoMetadata",
    "Channel",
    "Session",
    "ValidationResult",
    "ValidationIssue",
    "AppError",
    "Verdict",
    "JobState",
    "LifecycleStatus",
    "EvidenceStatus",
    "ResearchStatus",
    "AssetType",
    "ErrorCategory",
    "topic_from_plan",
    "fact_pack_from_legacy",
    "scene_from_legacy_contract",
    "script_from_plan",
    "validation_from_preflight",
    "job_from_fsm_dict",
    "checkpoint_from_meta",
]
