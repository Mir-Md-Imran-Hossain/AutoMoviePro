import json
from pathlib import Path

cache_file = Path("pipeline/nish_catalog_cache.json")
data = json.loads(cache_file.read_text(encoding="utf-8"))
niches = data.get("niches", [])

out_lines = ["# AutoMovie Pro — Niche Catalog\n\n"]
for n in niches:
    out_lines.append(f"### {n['id']}. {n['name']}\n")
    out_lines.append(f"- **Slug:** {n.get('slug', '')}\n")
    out_lines.append(f"- **Style Family:** {n.get('style_family', '')}\n")
    out_lines.append(f"- **Video Type:** {n.get('video_type', '')}\n")
    out_lines.append(f"- **Topic Generation Prompt:** {n.get('topic_generation_prompt', '')}\n")
    out_lines.append(f"- **Video Prompt:** {n.get('video_prompt', '')}\n\n---\n\n")

content = "".join(out_lines)
Path("..", "Nish.Md").write_text(content, encoding="utf-8")
Path("Nish.Md").write_text(content, encoding="utf-8")
print(f"Nish.Md successfully created with {len(niches)} niches!")
