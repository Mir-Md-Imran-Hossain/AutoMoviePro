"""Self-upgrade learning bus — record production mistakes → admin inbox → local lessons.

Flow
----
1) Pipeline detects a mistake (e.g. brand UI served from Pexels stock).
2) `record_lesson()` writes:
   - package File/learning_events.jsonl
   - Output/_admin_learning/inbox/{ts}_{id}.json  (admin panel / ops pickup)
   - Output/_admin_learning/lessons.json           (merged rules the pipeline reads)
3) Next runs call `active_lessons()` and apply prompt / routing fixes automatically.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LESSON_BRAND_UI_NO_STOCK = "brand_ui_forbid_stock"
LESSON_AGNES_FREE_NO_CIRCUIT = "agnes_free_403_skip_not_circuit"
LESSON_GOOGLE_429_ROTATE = "google_image_429_rotate_keys"
LESSON_POLLINATIONS_SANITIZE = "pollinations_sanitize_short_prompt"


def _admin_root(output_hint: Optional[Path] = None) -> Path:
    if output_hint is not None:
        base = Path(output_hint)
        if base.name.lower() != "output":
            # package root → climb to Output/
            for p in [base, *base.parents]:
                if p.name == "Output" or (p / "Short").is_dir():
                    return p if p.name == "Output" else p / "Output"
        return base
    return Path("Output")


def admin_learning_dirs(output_root: Optional[Path] = None) -> Dict[str, Path]:
    root = _admin_root(output_root)
    inbox = root / "_admin_learning" / "inbox"
    lessons = root / "_admin_learning"
    inbox.mkdir(parents=True, exist_ok=True)
    lessons.mkdir(parents=True, exist_ok=True)
    return {"root": lessons, "inbox": inbox, "lessons_file": lessons / "lessons.json"}


def record_lesson(
    *,
    kind: str,
    title: str,
    detail: str,
    fix: str,
    package_root: Optional[Path] = None,
    output_root: Optional[Path] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist a mistake+fix so admin + future runs can consume it."""
    event = {
        "id": str(uuid.uuid4())[:12],
        "ts": time.time(),
        "kind": kind,
        "title": title,
        "detail": detail,
        "fix": fix,
        "package_root": str(package_root) if package_root else "",
        "meta": meta or {},
    }
    dirs = admin_learning_dirs(output_root or (Path(package_root).parents[1] if package_root else None))
    # inbox for admin
    inbox_path = dirs["inbox"] / f"{int(event['ts'])}_{event['id']}_{kind}.json"
    inbox_path.write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")

    # merge into lessons.json
    lessons_path = dirs["lessons_file"]
    lessons: Dict[str, Any] = {"version": 1, "items": []}
    if lessons_path.is_file():
        try:
            lessons = json.loads(lessons_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    items: List[Dict[str, Any]] = list(lessons.get("items") or [])
    # upsert by kind
    items = [i for i in items if i.get("kind") != kind]
    items.append(
        {
            "kind": kind,
            "title": title,
            "fix": fix,
            "active": True,
            "updated_ts": event["ts"],
            "last_event_id": event["id"],
        }
    )
    lessons["items"] = items
    lessons["updated_ts"] = event["ts"]
    lessons_path.write_text(json.dumps(lessons, ensure_ascii=False, indent=2), encoding="utf-8")

    # package local log
    if package_root:
        try:
            pkg = Path(package_root)
            log = pkg / "File" / "learning_events.jsonl"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("package learning log failed: %s", exc)

    logger.info("Learning recorded kind=%s → %s", kind, inbox_path.name)
    return event


def active_lessons(output_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = admin_learning_dirs(output_root)["lessons_file"]
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [i for i in (data.get("items") or []) if i.get("active")]
    except Exception:
        return []


def lesson_active(kind: str, output_root: Optional[Path] = None) -> bool:
    return any(i.get("kind") == kind for i in active_lessons(output_root))


def seed_known_lessons_from_live004(output_root: Optional[Path] = None) -> None:
    """One-shot bootstrap from diagnosed live-004 failures (idempotent)."""
    dirs = admin_learning_dirs(output_root)
    marker = dirs["root"] / ".seeded_live004"
    if marker.is_file():
        return
    record_lesson(
        kind=LESSON_BRAND_UI_NO_STOCK,
        title="ChatGPT/product UI shots must not use Pexels/Pixabay stock",
        detail=(
            "Live 004: STOCK_VIDEO product_ui queries returned unrelated laptop B-roll; "
            "VO said Custom Instructions but frame had no ChatGPT UI."
        ),
        fix=(
            "Forbid stock for product_ui/hands_ui; force AI IMAGE/VIDEO; "
            "AV gate regenerates if stock sneaks through."
        ),
        output_root=output_root,
        meta={"source": "live4_pkg004"},
    )
    record_lesson(
        kind=LESSON_AGNES_FREE_NO_CIRCUIT,
        title="Agnes free /image 403 must not open circuit for paid Agnes",
        detail="Live 004: free endpoint 403 opened agnes_image circuit — paid Agnes never tried.",
        fix="Skip free endpoint on 403; only circuit-break on paid auth failures.",
        output_root=output_root,
        meta={"source": "live4_pkg004"},
    )
    record_lesson(
        kind=LESSON_GOOGLE_429_ROTATE,
        title="Google image 429 should rotate keys, not lock all images 30min",
        detail="Live 004: single 429 opened google_image circuit for 1800s.",
        fix="Try next GOOGLE_API_KEY; short soft cooldown; circuit only if all keys dead.",
        output_root=output_root,
        meta={"source": "live4_pkg004"},
    )
    record_lesson(
        kind=LESSON_POLLINATIONS_SANITIZE,
        title="Pollinations fails on huge unicode prompts / enhance=true",
        detail="Live 004: 500 on image.pollinations.ai and 401 on gen.pollinations.ai.",
        fix="ASCII-sanitize, shorten prompt, retry without enhance before giving up.",
        output_root=output_root,
        meta={"source": "live4_pkg004"},
    )
    marker.write_text("ok\n", encoding="utf-8")
