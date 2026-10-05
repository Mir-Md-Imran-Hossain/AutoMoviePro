"""Canonical localization + TextPlan contracts (AMP-004 Phase-06)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from domain.scene_intent import LocalizationIntent, SceneIntent


RTL_LANGS = frozenset({"ar", "ur", "fa", "he", "ps", "yi"})

TEXT_TYPES = (
    "TITLE",
    "HEADING",
    "CAPTION",
    "LOWER_THIRD",
    "LABEL",
    "CALLOUT",
    "STATISTIC",
    "QUOTE",
    "CTA",
    "WATERMARK",
    "SUBTITLE",
)


@dataclass
class TextElement:
    text_id: str
    scene_id: str
    language: str
    content: str
    purpose: str = "CAPTION"
    timing_start: float = 0.0
    timing_end: float = 0.0
    position: str = "bottom_center"
    safe_area: bool = True
    style: str = "default"
    priority: int = 2
    effect: str = "none"  # none|fade|slide|scale|highlight
    max_width_pct: float = 0.9
    max_height_pct: float = 0.25

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TextPlan:
    scene_id: str
    language: str
    elements: list[TextElement] = field(default_factory=list)
    effect_policy: str = "purposeful_v1"
    revision_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "language": self.language,
            "elements": [e.to_dict() for e in self.elements],
            "effect_policy": self.effect_policy,
            "revision_id": self.revision_id,
        }


@dataclass
class LocalizationContract:
    """Traceable localization binding — SceneIntent remains semantic source."""

    job_id: str
    scene_id: str
    dialogue_id: str
    segment_id: str = ""
    revision_id: str = ""
    source_language: str = "en"
    target_language: str = ""
    source_text: str = ""
    localized_text: str = ""
    speaker_id: str = ""
    entity_bindings: list[str] = field(default_factory=list)
    fact_bindings: list[dict[str, Any]] = field(default_factory=list)
    emotion_intent: str = ""
    emotion_intensity: float = 0.5
    action_events: list[str] = field(default_factory=list)
    rtl: bool = False
    numeral_policy: str = "preserve_source_digits"
    unit_policy: str = "preserve_source_units"
    currency_policy: str = "preserve_source_currency"
    name_policy: str = "preserve_latin_proper_nouns"
    reading_speed_cps: float = 17.0
    max_chars_per_line: int = 42
    max_lines: int = 2
    audio_fingerprint: str = ""
    contract_fingerprint: str = ""
    text_plan: Optional[TextPlan] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.text_plan:
            d["text_plan"] = self.text_plan.to_dict()
        return d

    def to_localization_intent(self) -> LocalizationIntent:
        return LocalizationIntent(
            source_language=self.source_language,
            target_language=self.target_language,
            preserve_events=True,
            semantic_events=list(self.action_events),
            entity_bindings=list(self.entity_bindings),
            fact_bindings=list(self.fact_bindings),
            speaker_id=self.speaker_id,
            emotion_intent=self.emotion_intent,
            emotion_intensity=self.emotion_intensity,
            rtl=self.rtl,
            numeral_policy=self.numeral_policy,
            unit_policy=self.unit_policy,
            currency_policy=self.currency_policy,
            name_policy=self.name_policy,
            reading_speed_cps=self.reading_speed_cps,
            max_chars_per_line=self.max_chars_per_line,
            max_lines=self.max_lines,
            revision_id=self.revision_id,
            job_id=self.job_id,
            scene_id=self.scene_id,
            dialogue_id=self.dialogue_id,
            segment_id=self.segment_id,
        )


def localization_fingerprint(contract: LocalizationContract | dict[str, Any]) -> str:
    data = contract.to_dict() if isinstance(contract, LocalizationContract) else dict(contract)
    keys = (
        "job_id",
        "scene_id",
        "dialogue_id",
        "segment_id",
        "revision_id",
        "source_language",
        "target_language",
        "source_text",
        "entity_bindings",
        "fact_bindings",
        "emotion_intent",
        "speaker_id",
        "numeral_policy",
        "unit_policy",
        "name_policy",
    )
    payload = {k: data.get(k) for k in keys}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_PROPER = re.compile(
    r"\b(iPhone|iPad|Pixel|Galaxy|Samsung|Apple|Google|Chernobyl|NASA|USB|OLED|HDR|"
    r"Android|Windows|Linux|ChatGPT|OpenAI|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b"
)
_NUMBER = re.compile(r"(?<![A-Za-z])(\d+(?:[.,]\d+)?)\s*(%|kg|km|m|cm|mm|ft|in|lb|usd|USD|\$|€|£|¥)?", re.I)
_DEVICE_FEATURE = re.compile(
    r"\b(iphone|pixel|galaxy|smartphone|phone)\s+(camera|lens|sensor|display|battery)\b",
    re.I,
)


def extract_entity_bindings(text: str) -> list[str]:
    found = _PROPER.findall(text or "")
    # also device+feature as atomic binding
    for m in _DEVICE_FEATURE.finditer(text or ""):
        found.append(m.group(0))
    out: list[str] = []
    seen: set[str] = set()
    for f in found:
        key = f.strip()
        if key and key.lower() not in seen:
            seen.add(key.lower())
            out.append(key)
    return out


def extract_fact_bindings(text: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for m in _NUMBER.finditer(text or ""):
        facts.append(
            {
                "value": m.group(1),
                "unit": (m.group(2) or "").strip(),
                "span": m.group(0).strip(),
                "policy": "preserve_unless_explicit_conversion",
            }
        )
    return facts


def build_localization_contract(
    *,
    job_id: str,
    scene_id: str,
    dialogue_id: str,
    source_text: str,
    source_language: str = "en",
    target_language: str,
    segment_id: str = "",
    revision_id: str = "",
    speaker_id: str = "",
    emotion_intent: str = "",
    emotion_intensity: float = 0.5,
    intent: Optional[SceneIntent] = None,
    localized_text: str = "",
) -> LocalizationContract:
    src = (source_text or "").strip()
    tgt_lang = (target_language or "").lower().strip()
    entities = extract_entity_bindings(src)
    facts = extract_fact_bindings(src)
    actions: list[str] = []
    if intent is not None:
        from pipeline.multimodal_consistency.localization_semantic import extract_semantic_events

        actions = extract_semantic_events(intent.summary or src)
        if intent.entities:
            for e in intent.entities:
                if e.label and e.label not in entities:
                    entities.append(e.label)
        speaker_id = speaker_id or (intent.actors[0] if intent.actors else "")
        emotion_intent = emotion_intent or intent.emotional_intent
        scene_id = intent.scene_id or scene_id
        dialogue_id = intent.dialogue_id or dialogue_id
        revision_id = revision_id or intent.revision_id

    # Language-family reading defaults
    cps = 17.0
    max_cpl = 42
    if tgt_lang in ("zh", "ja", "ko"):
        cps = 12.0
        max_cpl = 20
    elif tgt_lang in RTL_LANGS:
        cps = 15.0
        max_cpl = 40

    text_plan = TextPlan(
        scene_id=scene_id,
        language=tgt_lang or source_language,
        elements=[
            TextElement(
                text_id=f"sub-{dialogue_id}",
                scene_id=scene_id,
                language=tgt_lang or source_language,
                content=localized_text or src,
                purpose="SUBTITLE",
                effect="none",
                priority=1,
            )
        ],
        revision_id=revision_id,
    )

    contract = LocalizationContract(
        job_id=job_id,
        scene_id=scene_id,
        dialogue_id=dialogue_id,
        segment_id=segment_id,
        revision_id=revision_id,
        source_language=source_language,
        target_language=tgt_lang,
        source_text=src,
        localized_text=localized_text,
        speaker_id=speaker_id,
        entity_bindings=entities,
        fact_bindings=facts,
        emotion_intent=emotion_intent,
        emotion_intensity=emotion_intensity,
        action_events=actions,
        rtl=tgt_lang in RTL_LANGS,
        reading_speed_cps=cps,
        max_chars_per_line=max_cpl,
        text_plan=text_plan,
    )
    contract.contract_fingerprint = localization_fingerprint(contract)
    return contract
