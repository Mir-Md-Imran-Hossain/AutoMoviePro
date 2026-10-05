"""
E2E UI Automation Engine (Camoufox / Playwright).

Classes:
  - BrowserEngine
  - HumanInteractionManager
  - WorkflowTaskRunner
  - AlertHandler

Hooks existing publishers.captcha_alerts + session_vault when available.
"""
from __future__ import annotations

from pipeline.e2e_ui.alert_handler import AlertHandler, ChallengePaused
from pipeline.e2e_ui.browser_engine import BrowserEngine, BrowserSession
from pipeline.e2e_ui.human_input import HumanInteractionManager
from pipeline.e2e_ui.workflows import WorkflowTaskRunner, WorkflowResult

__all__ = [
    "AlertHandler",
    "BrowserEngine",
    "BrowserSession",
    "ChallengePaused",
    "HumanInteractionManager",
    "WorkflowResult",
    "WorkflowTaskRunner",
]
