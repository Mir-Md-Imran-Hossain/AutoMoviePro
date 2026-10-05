"""High-level orchestrator + CLI entry for E2E UI automation."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.e2e_ui.alert_handler import AlertHandler
from pipeline.e2e_ui.browser_engine import BrowserEngine
from pipeline.e2e_ui.human_input import HumanInteractionManager
from pipeline.e2e_ui.workflows import WorkflowResult, WorkflowTaskRunner

logger = logging.getLogger(__name__)


def run_e2e_session(
    *,
    platform: str = "youtube",
    start_url: str = "",
    query: str = "",
    subscribe: bool = False,
    like: bool = False,
    comment: str = "",
    watch_seconds: float = 20.0,
    headless: Optional[bool] = None,
    user_data_dir: str = "",
    tasks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Launch browser, run selected tasks, persist session, return summary dict.
    Safe to call from FastAPI / scheduler / scripts.
    """
    wanted = [t.lower() for t in (tasks or ["a", "b", "c"])]
    engine = BrowserEngine(
        platform=platform,
        user_data_dir=user_data_dir,
        headless=headless,
        humanize=True,
    )
    results: List[WorkflowResult] = []
    engine_name = "unknown"
    with engine.session() as sess:
        engine_name = sess.engine
        human = HumanInteractionManager(sess.page)
        alerts = AlertHandler(sess.page, platform=platform)
        alerts.start_watchdog()
        runner = WorkflowTaskRunner(
            sess.page,
            platform=platform,
            human=human,
            alerts=alerts,
        )
        try:
            if "a" in wanted or "discovery" in wanted:
                results.append(
                    runner.task_content_discovery(
                        query=query or "documentary",
                        start_url=start_url
                        or (
                            "https://www.youtube.com/"
                            if "you" in platform.lower()
                            else "https://www.facebook.com/"
                        ),
                        watch_seconds=watch_seconds,
                    )
                )
            if "b" in wanted or "engage" in wanted:
                results.append(
                    runner.task_engagement(
                        subscribe=subscribe,
                        like=like,
                        comment=comment,
                    )
                )
            if "c" in wanted or "inbox" in wanted:
                results.append(runner.task_inbox_notifications())
        finally:
            alerts.stop_watchdog()
            sess.save_storage_state()

    summary = {
        "ok": all(r.ok for r in results) if results else False,
        "platform": platform,
        "engine": engine_name,
        "profile": engine.user_data_dir,
        "results": [
            {"ok": r.ok, "task": r.task, "detail": r.detail, "data": r.data} for r in results
        ],
    }
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description="AutoMovie Pro E2E UI Automation Engine")
    ap.add_argument("--platform", default="youtube", choices=["youtube", "facebook"])
    ap.add_argument("--url", default="", help="Start URL override")
    ap.add_argument("--query", default="space science documentary")
    ap.add_argument("--subscribe", action="store_true")
    ap.add_argument("--like", action="store_true")
    ap.add_argument("--comment", default="")
    ap.add_argument("--watch", type=float, default=20.0)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--profile", default="", help="Persistent user_data_dir")
    ap.add_argument(
        "--tasks",
        default="a,b,c",
        help="Comma list: a/discovery, b/engage, c/inbox",
    )
    ap.add_argument("--out", default="", help="Write JSON summary path")
    args = ap.parse_args(argv)

    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    summary = run_e2e_session(
        platform=args.platform,
        start_url=args.url,
        query=args.query,
        subscribe=args.subscribe,
        like=args.like,
        comment=args.comment,
        watch_seconds=args.watch,
        headless=True if args.headless else None,
        user_data_dir=args.profile,
        tasks=tasks,
    )
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    # Allow `python -m pipeline.e2e_ui.runner`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
