"""Validation result contracts."""
from __future__ import annotations

from typing import Any, Optional, Type

from pydantic import BaseModel, Field

from domain.common import ContractBase, SchemaVersionMismatchError, schema_versions_compatible
from domain.enums import Verdict


class ValidationIssue(ContractBase):
    schema_version: str = "1.0.0"
    object_type: str
    object_id: Optional[str] = None
    field: Optional[str] = None
    rule: str
    severity: Verdict = Verdict.FAIL
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(ContractBase):
    schema_version: str = "1.0.0"
    verdict: Verdict
    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def pass_(cls, **context: Any) -> "ValidationResult":
        return cls(verdict=Verdict.PASS, passed=True, context=dict(context))

    @classmethod
    def fail(cls, issues: list[ValidationIssue], **context: Any) -> "ValidationResult":
        return cls(
            verdict=Verdict.FAIL,
            passed=False,
            issues=issues,
            context=dict(context),
        )


def expected_schema_version(model: Type[BaseModel]) -> str:
    field = model.model_fields.get("schema_version")
    default = getattr(field, "default", None) if field else None
    return str(default or "1.0.0")


def validate_contract_version(model: Type[BaseModel], data: dict[str, Any]) -> tuple[bool, Optional[str]]:
    stored = str(data.get("schema_version") or expected_schema_version(model))
    expected = expected_schema_version(model)
    if schema_versions_compatible(stored, expected):
        return True, None
    return False, f"schema_version mismatch: stored={stored!r} expected major={expected!r}"


def deserialize_contract(model: Type[BaseModel], data: dict[str, Any]) -> BaseModel:
    ok, reason = validate_contract_version(model, data)
    if not ok:
        raise SchemaVersionMismatchError(
            str(data.get("schema_version") or ""),
            expected_schema_version(model),
            model.__name__,
        )
    return model.model_validate(data)
