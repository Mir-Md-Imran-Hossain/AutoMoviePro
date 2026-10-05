"""Rebuild marathon progress: keep only true final_passed; retry quota-false-fails."""
import json
import shutil
from datetime import datetime
from pathlib import Path

out = Path("output/marathon_100")
rows = []
p = out / "results.jsonl"
if p.exists():
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

by = {}
for r in rows:
    if "id" in r:
        by[int(r["id"])] = r

keep = []
retry = []
for i, r in sorted(by.items()):
    # Prefer on-disk result.json if present
    rj = out / f"clip_{i:03d}" / "result.json"
    if rj.exists():
        try:
            r = json.loads(rj.read_text(encoding="utf-8"))
        except Exception:
            pass
    outage = (out / f"clip_{i:03d}" / "scene_00_CRITIC_OUTAGE.txt").exists()
    fail_txt = out / f"clip_{i:03d}" / "scene_00_AV_FAIL.txt"
    critique_bad = False
    for c in (out / f"clip_{i:03d}").glob("scene_00_critique_attempt*.json") if (out / f"clip_{i:03d}").exists() else []:
        try:
            d = json.loads(c.read_text(encoding="utf-8"))
            if (d.get("raw") or {}).get("fallback") or "critic_unavailable" in str(d.get("issues")):
                critique_bad = True
        except Exception:
            pass

    if r.get("final_passed") is True and not critique_bad:
        keep.append(i)
    else:
        retry.append(i)
        d = out / f"clip_{i:03d}"
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)

prog = {
    "started_at": datetime.now().isoformat(timespec="seconds"),
    "completed_ids": keep,
    "passed": len(keep),
    "failed": 0,
    "agent_errors": 0,
    "last_id": max(keep) if keep else 0,
    "updated_at": datetime.now().isoformat(timespec="seconds"),
    "note": "retry_after_quota_false_fails",
    "queued_retry": retry,
}
(out / "progress.json").write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(prog, ensure_ascii=False, indent=2))
