"""Normalized application error taxonomy."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from domain.common import ContractBase
from domain.enums import ErrorCategory


class AppError(ContractBase):
    schema_version: str = "1.0.0"
    category: ErrorCategory
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    cause_type: Optional[str] = None

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        *,
        category: ErrorCategory = ErrorCategory.UNKNOWN_ERROR,
        code: str = "unexpected",
        retryable: bool = False,
    ) -> "AppError":
        return cls(
            category=category,
            code=code,
            message=str(exc)[:500],
            retryable=retryable,
            cause_type=type(exc).__name__,
        )
