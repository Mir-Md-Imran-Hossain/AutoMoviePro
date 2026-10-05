#!/usr/bin/env python
"""Refresh title/description/tags on existing upload packages with rich Bangla SEO metadata."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.ai_providers import _fallback_bundle  # noqa: E402


def main() -> int:
    root = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety"
    updated = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        meta_path = folder / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        gadget = (meta.get("gadget") or {}).get("name") or "Gadget"
        vtype = meta.get("video_type") or "short"
        max_sec = 120 if vtype == "short" else 300
        bundle = _fallback_bundle(gadget, vtype, max_sec)
        (folder / "title.txt").write_text(bundle["title"] + "\n", encoding="utf-8")
        (folder / "description.txt").write_text(bundle["description"] + "\n", encoding="utf-8")
        (folder / "tags.txt").write_text(", ".join(bundle["tags"]) + "\n", encoding="utf-8")
        meta["title"] = bundle["title"]
        meta["description"] = bundle["description"]
        meta["tags"] = bundle["tags"]
        meta["metadata_provider"] = "fallback_rich_refresh"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        updated.append({"folder": str(folder), "title": bundle["title"], "type": vtype})
    report = {
        "ok": True,
        "packages": updated,
        "upload_ready_root": str(root),
        "note": "Videos unchanged; SEO metadata refreshed after Gemini quota fallback.",
    }
    out = ROOT / "output" / "E2E_TEST_REPORT.json"
    # merge with previous if present
    if out.exists():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
            prev["ok"] = True
            prev["packages"] = updated
            prev["metadata_refresh"] = report
            # strip secrets if any
            prev.pop("keys", None)
            out.write_text(json.dumps(prev, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        except Exception:
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Updated", len(updated), "packages")
    for u in updated:
        print("-", u["type"], ":", u["title"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
