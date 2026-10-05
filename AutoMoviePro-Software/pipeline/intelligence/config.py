"""Intelligence layer configuration (BUILD-04G-H)."""
from __future__ import annotations

import os
from enum import Enum


class ResearchMode(str, Enum):
    MOCK = "MOCK"
    LIVE = "LIVE"


class IntelligenceMode(str, Enum):
    PRODUCTION = "PRODUCTION"
    DEVELOPMENT = "DEVELOPMENT"


def get_research_mode() -> ResearchMode:
    try:
        from app.config import settings
        default = getattr(settings, "intelligence_research_mode", "LIVE")
    except Exception:
        default = "LIVE"
    raw = (os.environ.get("INTELLIGENCE_RESEARCH_MODE") or os.environ.get("AUTOMOVIE_RESEARCH_MODE") or default).strip().upper()
    if raw == "MOCK":
        return ResearchMode.MOCK
    return ResearchMode.LIVE


def get_intelligence_mode() -> IntelligenceMode:
    try:
        from app.config import settings
        default = getattr(settings, "intelligence_mode", "PRODUCTION")
    except Exception:
        default = "PRODUCTION"
    raw = (os.environ.get("INTELLIGENCE_MODE") or default).strip().upper()
    if raw == "DEVELOPMENT":
        return IntelligenceMode.DEVELOPMENT
    return IntelligenceMode.PRODUCTION


def allow_mock_research() -> bool:
    return get_research_mode() == ResearchMode.MOCK


def require_fail_closed() -> bool:
    return get_intelligence_mode() == IntelligenceMode.PRODUCTION
