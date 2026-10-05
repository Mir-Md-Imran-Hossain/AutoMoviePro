"""Resume live test from existing Stage-1 topic_script.json (Stages 2–3)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app.config import software_env_paths
from pipeline.api_keys import merge_env_maps, parse_env_file

maps = [parse_env_file(p) for p in software_env_paths()]
ENV = merge_env_maps(*[m for m in maps if m], {k: v for k, v in os.environ.items() if v})
os.environ["LOCALIZATION_GOOGLE_API_KEY"] = ENV.get("GOOGLE_API_KEY_1", "")
print("Localization key set from GOOGLE_API_KEY_1 for this process only")

import httpx
import pipeline.custom_pipeline.visual_render as vr


def _or_grok(
    prompt,
    *,
    system="",
    api_keys=None,
    models=None,
    json_mode=True,
    temperature=0.7,
    timeout=180.0,
):
    key = ENV.get("OPENROUTER_API_KEY_1", "")
    model_list = list(models) if models else ["x-ai/grok-4.6", "x-ai/grok-4.5", "x-ai/grok-4.3"]
    sys_msg = system or ("Respond with valid JSON only." if json_mode else "You are helpful.")
    last = None
    for model in model_list:
        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": prompt},
                ],
                "temperature": float(temperature),
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            with httpx.Client(timeout=timeout) as client:
                r = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://automoviepro.local",
                        "X-Title": "LiveTest",
                    },
                    json=payload,
                )
            if r.status_code >= 400:
                print("fail", model, r.status_code, r.text[:120])
                last = RuntimeError(r.text[:200])
                continue
            content = (
                r.json().get("choices", [{}])[0].get("message", {}).get("content") or ""
            ).strip()
            if content:
                print("Grok OR OK", model)
                return content
        except Exception as exc:
            last = exc
            print("err", model, exc)
    raise RuntimeError(last)


vr.grok_chat = _or_grok


def preview(obj, n=3500):
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    return text if len(text) <= n else text[:n] + "\n... [truncated]"


def main() -> int:
    from pipeline.custom_pipeline.localization import localize_script
    from pipeline.custom_pipeline.visual_render import plan_visual_renders

    base = ROOT / "Output" / "_live_test_custom_pipeline"
    topic_path = next(p for p in base.rglob("topic_script.json") if p.parent.name == "Shared")
    pkg = topic_path.parent.parent
    payload = json.loads(topic_path.read_text(encoding="utf-8"))
    seo = payload.get("seo_metadata") or {}
    scenes = payload.get("script_scenes") or []

    print("STAGE1 loaded:", topic_path)
    print("topic:", seo.get("selected_topic"))
    print("titles:", seo.get("suggested_titles"))
    print("keywords:", seo.get("seo_keywords"))
    print("scenes:", len(scenes))
    if scenes:
        s0 = scenes[0]
        print(
            "S1:",
            s0.get("shot_duration_seconds"),
            s0.get("emotion_tag"),
            str(s0.get("voiceover_script") or "")[:140],
        )

    print("\n=== STAGE2 English ===")
    en = localize_script(
        payload,
        target_language="English",
        audience_culture="Global English Reader",
        package_root=pkg,
        video_type="short",
        save=True,
    )
    print("saved:", (en.get("save") or {}).get("json_path"))
    en_seo = (en.get("payload") or {}).get("seo_metadata") or {}
    en_scenes = (en.get("payload") or {}).get("script_scenes") or []
    print("EN topic:", en_seo.get("selected_topic"))
    print("EN titles:", en_seo.get("suggested_titles"))
    if en_scenes:
        print(
            "EN S1:",
            en_scenes[0].get("emotion_tag"),
            "|",
            str(en_scenes[0].get("voiceover_script") or "")[:160],
        )

    print("\n=== STAGE2 Hindi ===")
    hi = localize_script(
        payload,
        target_language="Hindi",
        audience_culture="North Indian",
        package_root=pkg,
        video_type="short",
        save=True,
    )
    print("saved:", (hi.get("save") or {}).get("json_path"))
    hi_scenes = (hi.get("payload") or {}).get("script_scenes") or []
    if hi_scenes:
        print(
            "HI S1:",
            hi_scenes[0].get("emotion_tag"),
            "|",
            str(hi_scenes[0].get("voiceover_script") or "")[:160],
        )

    print("\n=== STAGE3 Visual ===")
    vis = plan_visual_renders(payload, video_type="short", package_root=pkg, save=True)
    print("saved:", (vis.get("save") or {}).get("json_path"))
    meta = (vis.get("payload") or {}).get("production_metadata") or {}
    print("meta:", meta)
    for sc in (vis.get("payload") or {}).get("render_scenes") or []:
        md = sc.get("motion_directives") or {}
        vp = str(sc.get("visual_prompt") or "")[:110]
        print(
            f"S{sc.get('shot_number')} {sc.get('render_type')} "
            f"{sc.get('shot_duration_seconds')}s | {vp} | keys={list(md.keys())}"
        )

    report = base / "LIVE_TEST_REPORT.md"
    report.write_text(
        "\n".join(
            [
                "# Custom Pipeline Live Test Report",
                "",
                f"- Package: `{pkg}`",
                f"- Topic JSON: `{topic_path}`",
                "- Grok transport: OpenRouter fallback (x-ai/grok) — XAI_API_KEY was missing",
                "- Localization: GOOGLE_API_KEY_1 as LOCALIZATION_GOOGLE_API_KEY (process only)",
                "",
                "## Stage 1 — Topic / Script",
                "",
                "```json",
                preview(payload, 4500),
                "```",
                "",
                "## Stage 2 — English",
                "",
                "```json",
                preview(en.get("payload"), 3500),
                "```",
                "",
                "## Stage 2b — Hindi",
                "",
                "```json",
                preview(hi.get("payload"), 2500),
                "```",
                "",
                "## Stage 3 — Visual Render Plan",
                "",
                "```json",
                preview(vis.get("payload"), 4500),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("\nREPORT:", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
