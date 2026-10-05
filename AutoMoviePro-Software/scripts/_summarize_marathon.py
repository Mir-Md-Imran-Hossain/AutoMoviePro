import json
from pathlib import Path

rows = []
for line in Path("output/marathon_100/results.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
by = {}
for r in rows:
    if "id" in r:
        by[int(r["id"])] = r
print("unique", len(by))
for i in sorted(by):
    r = by[i]
    if "error" in r:
        print(f"#{i} ERROR {str(r['error'])[:120]}")
    else:
        print(
            f"#{i} score={r.get('agent_score')} pre={r.get('precheck_score')} "
            f"final={r.get('final_passed')} meta={r.get('meta_error')} "
            f"att={r.get('attempts')} {r.get('element')}"
        )
