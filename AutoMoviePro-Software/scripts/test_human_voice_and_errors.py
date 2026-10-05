"""
Human voice + browser humanize + error notebook — double cross-check tests.

Run: venv\\Scripts\\python.exe scripts\\test_human_voice_and_errors.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.content_humanizer import (  # noqa: E402
    audit_plan_human_voice,
    find_ai_tells,
    humanize_plan,
    score_human_text,
)
from pipeline.error_notebook import note_error, summarize_open_notes  # noqa: E402
from pipeline.prompt_engineering import HUMAN_VOICE_CONTRACT, system_for_purpose  # noqa: E402
from app import db as store  # noqa: E402

failed = 0
passed = 0


def expect(cond: bool, msg: str) -> None:
    global failed, passed
    if cond:
        passed += 1
        print(f"OK  {msg}")
    else:
        failed += 1
        print(f"FAIL {msg}")


def round_prompts() -> None:
    print("\n=== Round 1A: prompts carry human-voice contract ===")
    expect("HUMAN VOICE" in HUMAN_VOICE_CONTRACT or "human" in HUMAN_VOICE_CONTRACT.lower(), "contract defined")
    sys_p = system_for_purpose("director", json_mode=True)
    expect("HUMAN VOICE" in sys_p or "delve" in sys_p.lower() or "human" in sys_p.lower(), "director system humanized")
    expect("JSON" in sys_p, "json mode still on")


def round_humanizer() -> None:
    print("\n=== Round 1B: AI-tell detection + rewrite ===")
    robotic = (
        "In today's digital landscape, we delve into the Pixel 9a — "
        "a game-changer that will seamlessly unlock your potential. "
        "Furthermore, it is important to note the comprehensive guide below."
    )
    tells = find_ai_tells(robotic)
    expect(len(tells) >= 4, f"many AI tells detected ({len(tells)})")
    sc = score_human_text(robotic, field="description")
    expect(sc["score"] < 70, f"robotic score low ({sc['score']})")

    plan = {
        "topic": "Pixel 9a",
        "title": "The Ultimate Comprehensive Guide to Pixel 9a!",
        "description": robotic,
        "scenes": [
            {"narration": "Moreover, we delve into battery life on the Pixel 9a today."},
            {"narration": "Pixel 9a lasts all day — camera stays sharp after dark."},
        ],
    }
    before = audit_plan_human_voice(plan)
    expect(before["needs_rewrite"] is True, "audit flags rewrite")
    hum = humanize_plan(plan, use_llm=False, work_dir=None)
    after = hum["audit_after"]
    expect("delve" not in str(hum["plan"].get("description") or "").lower(), "delve stripped")
    expect(after["avg_score"] >= before["avg_score"], "score improved or equal after humanize")
    expect(hum.get("rewrites") is not None, "rewrites list present")

    print("\n=== Round 1C: human sample passes ===")
    human = {
        "topic": "Pixel 9a",
        "title": "Pixel 9a overnight — battery that actually lasts",
        "description": "Tried the Pixel 9a for a week. Night shots hold up. Link in description.\n\n#Pixel9a #Android",
        "scenes": [
            {"narration": "Pixel 9a still looks sharp after a full workday on one charge."},
        ],
    }
    ok = audit_plan_human_voice(human)
    expect(ok["ok"] is True or ok["avg_score"] >= 72, f"human sample ok avg={ok['avg_score']}")


def round_browser() -> None:
    print("\n=== Round 2A: browser human helpers ===")
    from publishers import human_browser, youtube_uploader, facebook_uploader

    expect(hasattr(human_browser, "upload_ritual"), "upload_ritual exists")
    expect(hasattr(human_browser, "wait_human"), "wait_human exists")
    expect("prefer_type" in human_browser.human_paste_text.__code__.co_varnames, "prefer_type on paste")
    src = Path(youtube_uploader.__file__).read_text(encoding="utf-8")
    expect("upload_ritual" in src, "YT calls upload ritual")
    fbs = Path(facebook_uploader.__file__).read_text(encoding="utf-8")
    expect("upload_ritual" in fbs, "FB calls upload ritual")


def round_errors() -> None:
    print("\n=== Round 2B: error notebook ===")
    store.init_db()
    id1 = note_error(
        subsystem="test",
        fault_code="unit_glitch",
        message="tiny selector miss #1",
        severity="warn",
        channel_id=1,
    )
    expect(id1 > 0, "first note id")
    id2 = note_error(
        subsystem="test",
        fault_code="unit_glitch",
        message="tiny selector miss #1",
        severity="warn",
        channel_id=1,
    )
    expect(id1 == id2, "same fingerprint bumps same note")
    rows = store.list_error_notes(status="open", subsystem="test", limit=10)
    expect(any(int(r.get("count") or 0) >= 2 for r in rows), "count bumped")
    summ = summarize_open_notes(20)
    expect(summ.get("ok") is True, "summary ok")
    store.resolve_error_note(id1, owner_note="fixed in test")
    open_rows = store.list_error_notes(status="open", subsystem="test", limit=20)
    expect(all(int(r["id"]) != id1 for r in open_rows), "resolved leaves open list")


def main() -> int:
    round_prompts()
    round_humanizer()
    round_browser()
    round_errors()
    # Second full cross-check cycle
    print("\n======== RE-ANALYSIS CYCLE 2 ========")
    round_prompts()
    round_humanizer()
    round_browser()
    round_errors()
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
