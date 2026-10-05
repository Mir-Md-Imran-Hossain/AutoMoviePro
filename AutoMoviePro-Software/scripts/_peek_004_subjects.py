import json
from pathlib import Path

pkgs = list(Path("Output/Short").glob("004_*"))
if not pkgs:
    raise SystemExit("no 004 package")
p = pkgs[0]
print("PKG", p)
d = json.loads((p / "File" / "topic_script.json").read_text(encoding="utf-8"))
print("topic", (d.get("seo_metadata") or {}).get("selected_topic"))
for sc in d.get("script_scenes") or []:
    n = sc.get("shot_number")
    subj = sc.get("visual_subject")
    char = (sc.get("character_details") or "")[:50]
    vo = (sc.get("voiceover_script") or "")[:80]
    print(f"S{int(n):02d} subj={subj!r} char={char!r}")
    print(f"     vo={vo!r}")
