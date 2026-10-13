"""Runtime guard to prevent use_mock=True in customer production environment."""
from __future__ import annotations

import os


def is_customer_production_runtime() -> bool:
    """Checks if running in customer production environment."""
    if os.getenv("AUTOMOVIE_PRODUCTION", "").strip().lower() in ("1", "true", "yes"):
        return True
    if os.getenv("AUTOMOVIE_CUSTOMER_PROD", "").strip().lower() in ("1", "true", "yes"):
        return True
    if os.getenv("AUTOMOVIE_ENV", "").strip().lower() == "production":
        return True
    return False


def assert_no_mock_in_production(use_mock: bool = False, stage: str = "idempotency") -> None:
    """Strictly prevents use_mock=True when executing in customer production environment."""
    if not use_mock:
        return
    if is_customer_production_runtime():
        raise RuntimeError(
            f"PRODUCTION_INTEGRITY_VIOLATION: use_mock=True is strictly prohibited in customer production environment (stage: {stage})."
        )
