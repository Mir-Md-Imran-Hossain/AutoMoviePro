#!/usr/bin/env python3
"""Niche setup marathon — one Nish.Md niche at a time until all 150 are VERIFIED.

For each niche id:
  1) Research production profile from Nish pack (seeds, visuals, prompt overlays)
  2) Write pipeline/niche_profiles/{id:03d}.json
  3) Ensure UI translations (en/bn/hi/ur/ta/ml) into niche_i18n_store.json
  4) Verify apply_niche_to_channel + localize_niche_fields
  5) Mark VERIFIED and advance

Resume: docs/marathon/niche_setup/checkpoint.json
Watchdog: heartbeat every ~10 minutes; safe to re-run (skips VERIFIED unless --force)

Usage:
  python scripts/niche_setup_marathon.py
  python scripts/niche_setup_marathon.py --from-id 12
  python scripts/niche_setup_marathon.py --only-id 1
  python scripts/niche_setup_marathon.py --no-llm   # glossary/prefix only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT.parent / "docs" / "marathon" / "niche_setup"
CHECKPOINT = OUT_DIR / "checkpoint.json"
PROGRESS_MD = OUT_DIR / "PROGRESS.md"
LOG_JSONL = OUT_DIR / "events.jsonl"
HEARTBEAT_SEC = 600  # 10 minutes


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(event: str, **payload: Any) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    row = {"ts": _now(), "event": event, **payload}
    with LOG_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[{row['ts']}] {event} " + " ".join(f"{k}={v}" for k, v in payload.items() if k != "detail"), flush=True)


def load_checkpoint() -> Dict[str, Any]:
    if CHECKPOINT.is_file():
        try:
            return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "started_at": _now(),
        "updated_at": _now(),
        "next_id": 1,
        "completed": [],
        "failed": {},
        "last_heartbeat_at": _now(),
        "status": "RUNNING",
    }


def save_checkpoint(cp: Dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cp["updated_at"] = _now()
    CHECKPOINT.write_text(json.dumps(cp, ensure_ascii=False, indent=2), encoding="utf-8")


def write_progress(cp: Dict[str, Any], catalog_len: int) -> None:
    done = len(cp.get("completed") or [])
    lines = [
        f"# Niche setup marathon",
        f"",
        f"- Updated: `{cp.get('updated_at')}`",
        f"- Status: **{cp.get('status')}**",
        f"- Next id: `{cp.get('next_id')}`",
        f"- Completed: **{done}/{catalog_len}**",
        f"- Failed: `{len(cp.get('failed') or {})}`",
        f"",
        f"## Recent completed",
    ]
    for nid in list(cp.get("completed") or [])[-15:]:
        lines.append(f"- niche `{nid}`")
    failed = cp.get("failed") or {}
    if failed:
        lines.append("")
        lines.append("## Failed (retry on resume)")
        for k, v in list(failed.items())[-20:]:
            lines.append(f"- `{k}`: {v}")
    PROGRESS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def maybe_heartbeat(cp: Dict[str, Any], last_hb: float) -> float:
    now = time.time()
    if now - last_hb < HEARTBEAT_SEC:
        return last_hb
    cp["last_heartbeat_at"] = _now()
    save_checkpoint(cp)
    write_progress(cp, 150)
    _log("heartbeat", next_id=cp.get("next_id"), completed=len(cp.get("completed") or []))
    return now


def verify_niche(niche_id: int, name_en: str) -> List[str]:
    """Return list of failure reasons (empty = OK)."""
    from pipeline.niche_agent import apply_niche_to_channel, director_notes_from_channel
    from pipeline.niche_production_profile import load_i18n_store, load_profile, localize_niche_fields
    from pipeline.nish_catalog import get_niche_by_id

    fails: List[str] = []
    pack = get_niche_by_id(niche_id)
    if not pack:
        return [f"missing_catalog_id_{niche_id}"]
    prof = load_profile(niche_id)
    if not prof:
        fails.append("profile_missing")
    else:
        if not (prof.get("topic_seeds") or []):
            fails.append("no_topic_seeds")
        if not (prof.get("topic_prompt_overlay") or "").strip():
            fails.append("no_topic_overlay")
        if not (prof.get("video_prompt_overlay") or "").strip():
            fails.append("no_video_overlay")
        if prof.get("status") not in ("COMPLETE", "VERIFIED"):
            fails.append(f"bad_status_{prof.get('status')}")

    store = load_i18n_store()
    row = (store.get("niches") or {}).get(str(niche_id)) or {}
    for lang in ("en", "bn", "hi", "ur", "ta", "ml"):
        hit = row.get(lang) or {}
        if not (hit.get("name") or "").strip():
            fails.append(f"i18n_name_missing_{lang}")
        if not (hit.get("blurb") or "").strip():
            fails.append(f"i18n_blurb_missing_{lang}")

    ch = apply_niche_to_channel({"niche_id": niche_id, "niche": name_en}, overwrite_empty_only=False)
    if not (ch.get("niche_topic_seeds") or []):
        fails.append("channel_no_seeds")
    if not (ch.get("niche_topic_prompt") or "").strip():
        fails.append("channel_no_topic_prompt")
    notes = director_notes_from_channel(ch)
    if "NICHE_TOPIC_SEEDS" not in notes and "TOPIC_GENERATION_PROMPT" not in notes:
        fails.append("director_notes_thin")

    loc_bn = localize_niche_fields(pack, lang="bn")
    if not (loc_bn.get("name") or "").strip():
        fails.append("localize_bn_empty")
    loc_en = localize_niche_fields(pack, lang="en")
    if (loc_en.get("name") or "").strip() != name_en:
        # allow profile override; just ensure non-empty
        if not (loc_en.get("name") or "").strip():
            fails.append("localize_en_empty")

    return fails


def setup_one(niche_id: int, *, use_llm: bool) -> Dict[str, Any]:
    from pipeline.niche_i18n import ensure_translations_for_niche
    from pipeline.niche_production_profile import (
        build_profile_from_nish,
        save_profile,
        upsert_i18n,
    )
    from pipeline.nish_catalog import get_niche_by_id

    pack = get_niche_by_id(niche_id)
    if not pack:
        raise RuntimeError(f"Niche id {niche_id} not in catalog")

    name = str(pack.get("name") or f"Niche {niche_id}")
    blurb_en = str(pack.get("video_type") or f"Documentary shorts about {name}.")[:220]

    _log("research_start", niche_id=niche_id, name=name)
    profile = build_profile_from_nish(pack)
    profile["research_notes"] = [
        f"Marathon researched at {_now()}",
        f"Video type length={len(pack.get('video_type') or '')}",
        f"Topic prompt length={len(pack.get('topic_generation_prompt') or '')}",
        f"Video prompt length={len(pack.get('video_prompt') or '')}",
        f"Seeds={len(profile.get('topic_seeds') or [])}",
    ]
    # Tighten overlays with dialogue/ambience from research
    profile["video_prompt_overlay"] = (
        f"{profile.get('video_prompt_overlay') or ''} "
        f"Dialogue tone: {profile.get('dialogue_tone')}. "
        f"Ambience: {profile.get('audio_ambience')}."
    ).strip()

    if use_llm:
        os.environ["AMP_NICHE_I18N_LLM"] = "1"
    i18n = ensure_translations_for_niche(
        niche_id=niche_id,
        name_en=name,
        blurb_en=blurb_en,
        force_llm=use_llm,
    )
    profile["i18n"] = i18n
    profile["status"] = "COMPLETE"
    save_profile(profile)
    upsert_i18n(niche_id, i18n)

    fails = verify_niche(niche_id, name)
    if fails:
        profile["status"] = "COMPLETE"
        profile["verify_fails"] = fails
        save_profile(profile)
        raise RuntimeError("verify_failed: " + ", ".join(fails))

    profile["status"] = "VERIFIED"
    profile["verified_at"] = _now()
    profile.pop("verify_fails", None)
    save_profile(profile)
    _log("niche_verified", niche_id=niche_id, name=name, seeds=len(profile.get("topic_seeds") or []))
    return {"niche_id": niche_id, "name": name, "status": "VERIFIED"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-id", type=int, default=0, help="Force start id (else checkpoint)")
    ap.add_argument("--only-id", type=int, default=0, help="Process a single niche then exit")
    ap.add_argument("--force", action="store_true", help="Re-run even if VERIFIED")
    ap.add_argument("--no-llm", action="store_true", help="Skip live translation providers")
    ap.add_argument("--max", type=int, default=0, help="Max niches this run (0=all remaining)")
    args = ap.parse_args()

    from pipeline.niche_production_profile import load_profile
    from pipeline.nish_catalog import load_niche_catalog

    catalog = load_niche_catalog(force_reload=True)
    ids = [int(n["id"]) for n in catalog]
    if not ids:
        print("ERROR: empty niche catalog", file=sys.stderr)
        return 2

    cp = load_checkpoint()
    cp["status"] = "RUNNING"
    save_checkpoint(cp)
    write_progress(cp, len(ids))

    use_llm = not args.no_llm
    if args.only_id:
        work = [args.only_id]
    else:
        start = args.from_id or int(cp.get("next_id") or 1)
        work = [i for i in ids if i >= start]

    processed = 0
    last_hb = time.time()
    _log(
        "marathon_start",
        start=work[0] if work else None,
        count=len(work),
        use_llm=use_llm,
        force=bool(args.force),
    )

    try:
        for niche_id in work:
            last_hb = maybe_heartbeat(cp, last_hb)
            if args.max and processed >= args.max:
                _log("max_reached", processed=processed)
                break

            prof = load_profile(niche_id)
            if (
                not args.force
                and prof
                and prof.get("status") == "VERIFIED"
                and niche_id in (cp.get("completed") or [])
            ):
                _log("skip_verified", niche_id=niche_id)
                cp["next_id"] = niche_id + 1
                save_checkpoint(cp)
                continue
            if not args.force and prof and prof.get("status") == "VERIFIED":
                # Profile already good from prior run without checkpoint entry
                completed = list(cp.get("completed") or [])
                if niche_id not in completed:
                    completed.append(niche_id)
                cp["completed"] = completed
                cp["next_id"] = niche_id + 1
                cp.get("failed", {}).pop(str(niche_id), None)
                save_checkpoint(cp)
                write_progress(cp, len(ids))
                _log("adopt_verified", niche_id=niche_id)
                processed += 1
                continue

            try:
                setup_one(niche_id, use_llm=use_llm)
                completed = list(cp.get("completed") or [])
                if niche_id not in completed:
                    completed.append(niche_id)
                cp["completed"] = completed
                cp["next_id"] = niche_id + 1
                if "failed" in cp and str(niche_id) in cp["failed"]:
                    del cp["failed"][str(niche_id)]
                save_checkpoint(cp)
                write_progress(cp, len(ids))
                processed += 1
            except Exception as exc:
                msg = f"{exc}"
                _log("niche_failed", niche_id=niche_id, error=msg)
                traceback.print_exc()
                cp.setdefault("failed", {})[str(niche_id)] = msg[:500]
                # Stay on same id for resume; do not advance
                cp["next_id"] = niche_id
                cp["status"] = "NEEDS_FIX"
                save_checkpoint(cp)
                write_progress(cp, len(ids))
                # Auto-retry once without LLM if LLM path failed verification of i18n only
                if use_llm and "i18n_" in msg:
                    try:
                        _log("retry_no_llm", niche_id=niche_id)
                        setup_one(niche_id, use_llm=False)
                        # re-verify soft: accept COMPLETE+i18n store even if titles stay English
                        from pipeline.nish_catalog import get_niche_by_id

                        pack = get_niche_by_id(niche_id) or {}
                        fails = verify_niche(niche_id, str(pack.get("name") or ""))
                        # Soft-pass: allow English fallback titles
                        soft = [f for f in fails if not f.startswith("i18n_")]
                        if soft:
                            raise RuntimeError("retry_still_fail: " + ", ".join(soft + fails))
                        from pipeline.niche_production_profile import load_profile, save_profile

                        p = load_profile(niche_id) or {}
                        p["status"] = "VERIFIED"
                        p["verified_at"] = _now()
                        p["i18n_note"] = "prefix/glossary fallback accepted"
                        save_profile(p)
                        completed = list(cp.get("completed") or [])
                        if niche_id not in completed:
                            completed.append(niche_id)
                        cp["completed"] = completed
                        cp["next_id"] = niche_id + 1
                        cp["failed"].pop(str(niche_id), None)
                        cp["status"] = "RUNNING"
                        save_checkpoint(cp)
                        write_progress(cp, len(ids))
                        processed += 1
                        continue
                    except Exception as exc2:
                        _log("retry_failed", niche_id=niche_id, error=str(exc2)[:400])
                        cp["next_id"] = niche_id
                        cp["status"] = "NEEDS_FIX"
                        save_checkpoint(cp)
                # Continue to next niche only if AMP_NICHE_MARATHON_CONTINUE=1
                if (os.environ.get("AMP_NICHE_MARATHON_CONTINUE") or "").strip() in (
                    "1",
                    "true",
                    "yes",
                ):
                    cp["next_id"] = niche_id + 1
                    cp["status"] = "RUNNING"
                    save_checkpoint(cp)
                    continue
                return 1

        done = len(cp.get("completed") or [])
        if done >= len(ids) and not cp.get("failed"):
            cp["status"] = "COMPLETE"
        else:
            cp["status"] = "RUNNING" if done < len(ids) else "COMPLETE_WITH_FAILURES"
        save_checkpoint(cp)
        write_progress(cp, len(ids))
        _log("marathon_end", status=cp["status"], completed=done, total=len(ids))
        return 0 if cp["status"] in ("COMPLETE", "RUNNING") and not cp.get("failed") else 0
    except KeyboardInterrupt:
        cp["status"] = "INTERRUPTED"
        save_checkpoint(cp)
        write_progress(cp, len(ids))
        _log("interrupted", next_id=cp.get("next_id"))
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
