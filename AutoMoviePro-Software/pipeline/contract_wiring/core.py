"""BUILD-02 contract wiring core — validation gates, logging, stage results."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ValidationError

from domain.enums import ErrorCategory, Verdict
from domain.errors import AppError
from domain.validation import ValidationIssue, ValidationResult

logger = logging.getLogger("pipeline.contract_wiring")

T = TypeVar("T", bound=BaseModel)

CONTRACT_LAYER_VERSION = "build02-1.0.0"


@dataclass
class StageContext:
    job_id: str
    stage: str
    entity_id: Optional[str] = None
    contract_version: str = CONTRACT_LAYER_VERSION


@dataclass
class StageWireResult(Generic[T]):
    stage: str
    context: StageContext
    canonical: Optional[T]
    legacy: Optional[dict[str, Any]]
    input_validation: ValidationResult
    output_validation: ValidationResult
    duration_ms: float = 0.0
    error: Optional[AppError] = None

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and self.canonical is not None
            and self.input_validation.passed
            and self.output_validation.passed
        )

    @classmethod
    def failed(
        cls,
        *,
        stage: str,
        context: StageContext,
        input_validation: ValidationResult,
        output_validation: ValidationResult,
        error: AppError,
        legacy: Optional[dict] = None,
        duration_ms: float = 0.0,
    ) -> "StageWireResult[T]":
        return cls(
            stage=stage,
            context=context,
            canonical=None,
            legacy=legacy,
            input_validation=input_validation,
            output_validation=output_validation,
            duration_ms=duration_ms,
            error=error,
        )


def _issue(rule: str, message: str, *, severity: Verdict = Verdict.FAIL) -> ValidationIssue:
    return ValidationIssue(
        object_type="StageInput",
        rule=rule,
        severity=severity,
        message=message,
    )


def validate_required_dict(data: Any, *, stage: str, required_keys: tuple[str, ...]) -> ValidationResult:
    if not isinstance(data, dict):
        return ValidationResult.fail([_issue("type", f"{stage}: input must be dict")])
    issues = []
    for k in required_keys:
        if k not in data or data[k] in (None, ""):
            issues.append(_issue("required", f"missing required key: {k}"))
    if issues:
        return ValidationResult.fail(issues)
    return ValidationResult.pass_(stage=stage)


def validate_model(model_cls: type[T], data: dict[str, Any], *, stage: str) -> tuple[Optional[T], ValidationResult]:
    try:
        obj = model_cls.model_validate(data)
        return obj, ValidationResult.pass_(stage=stage)
    except ValidationError as exc:
        issues = [
            ValidationIssue(
                object_type=model_cls.__name__,
                field=".".join(str(x) for x in err["loc"]),
                rule="pydantic",
                severity=Verdict.FAIL,
                message=err["msg"],
            )
            for err in exc.errors()
        ]
        return None, ValidationResult.fail(issues, stage=stage)


def validate_instance(obj: BaseModel, *, stage: str) -> ValidationResult:
    try:
        obj.__class__.model_validate(obj.model_dump())
        return ValidationResult.pass_(stage=stage)
    except ValidationError as exc:
        issues = [
            ValidationIssue(
                object_type=obj.__class__.__name__,
                field=".".join(str(x) for x in err["loc"]),
                rule="pydantic",
                severity=Verdict.FAIL,
                message=err["msg"],
            )
            for err in exc.errors()
        ]
        return ValidationResult.fail(issues, stage=stage)


def log_stage(result: StageWireResult[Any]) -> None:
    ctx = result.context
    level = logging.INFO if result.passed else logging.WARNING
    logger.log(
        level,
        "contract_wiring stage=%s job_id=%s entity_id=%s passed=%s duration_ms=%.1f verdict_in=%s verdict_out=%s contract_version=%s",
        result.stage,
        ctx.job_id,
        ctx.entity_id or "-",
        result.passed,
        result.duration_ms,
        result.input_validation.verdict.value,
        result.output_validation.verdict.value,
        ctx.contract_version,
    )
    if result.error:
        logger.warning(
            "contract_wiring error stage=%s category=%s code=%s",
            result.stage,
            result.error.category.value,
            result.error.code,
        )


def run_stage(
    *,
    stage: str,
    job_id: str,
    legacy: dict[str, Any],
    input_validation: ValidationResult,
    build_fn,
    entity_id: Optional[str] = None,
) -> StageWireResult[Any]:
    t0 = time.perf_counter()
    ctx = StageContext(job_id=job_id, stage=stage, entity_id=entity_id)
    if not input_validation.passed:
        out_fail = ValidationResult.fail(
            [_issue("input_gate", "input validation failed — stage not executed")],
            stage=stage,
        )
        err = AppError(
            category=ErrorCategory.VALIDATION_ERROR,
            code="input_validation_failed",
            message=f"{stage} input validation failed",
        )
        result = StageWireResult.failed(
            stage=stage,
            context=ctx,
            input_validation=input_validation,
            output_validation=out_fail,
            error=err,
            legacy=legacy,
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
        log_stage(result)
        return result
    try:
        canonical = build_fn()
        out_val = validate_instance(canonical, stage=stage)
        duration = (time.perf_counter() - t0) * 1000
        result = StageWireResult(
            stage=stage,
            context=ctx,
            canonical=canonical,
            legacy=legacy,
            input_validation=input_validation,
            output_validation=out_val,
            duration_ms=duration,
        )
        if not out_val.passed:
            result.error = AppError(
                category=ErrorCategory.VALIDATION_ERROR,
                code="output_validation_failed",
                message=f"{stage} output validation failed",
            )
        log_stage(result)
        return result
    except Exception as exc:
        duration = (time.perf_counter() - t0) * 1000
        out_fail = ValidationResult.fail(
            [_issue("execution", str(exc)[:300])],
            stage=stage,
        )
        err = AppError.from_exception(exc, category=ErrorCategory.STATE_ERROR, code="stage_execution_failed")
        result = StageWireResult.failed(
            stage=stage,
            context=ctx,
            input_validation=input_validation,
            output_validation=out_fail,
            error=err,
            legacy=legacy,
            duration_ms=duration,
        )
        log_stage(result)
        return result
