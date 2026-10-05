"""Live end-to-end smoke test for custom_pipeline Stages 1–3.

Uses:
  - OpenRouter x-ai/grok-* when XAI_API_KEY is missing (test fallback)
  - GOOGLE_API_KEY_1 as LOCALIZATION_GOOGLE_API_KEY for this process only
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Windows consoles often default to cp1252 — force UTF-8 for Bangla output
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


from pipeline.api_keys import merge_env_maps, parse_env_file
from app.config import software_env_paths

maps = [parse_env_file(p) for p in software_env_paths()]
ENV = merge_env_maps(*[m for m in maps if m], {k: v for k, v in os.environ.items() if v})

# --- dedicated localization key for THIS process only ---
if not (ENV.get("LOCALIZATION_GOOGLE_API_KEY") or ENV.get("GOOGLE_LOCALIZE_API_KEY")):
    g1 = (ENV.get("GOOGLE_API_KEY_1") or "").strip()
    if not g1:
        raise SystemExit("No GOOGLE_API_KEY_1 to use as temporary localization key")
    os.environ["LOCALIZATION_GOOGLE_API_KEY"] = g1
    print("NOTE: using GOOGLE_API_KEY_1 as LOCALIZATION_GOOGLE_API_KEY for this test only")

# --- Grok via OpenRouter if no XAI key ---
from pipeline.custom_pipeline import grok_client

_orig_grok = grok_client.grok_chat
_xai = grok_client.resolve_xai_keys()


def _openrouter_grok_chat(
    prompt: str,
    *,
    system: str = "",
    api_keys=None,
    models=None,
    json_mode: bool = True,
    temperature: float = 0.7,
    timeout: float = 180.0,
) -> str:
    import httpx

    key = (ENV.get("OPENROUTER_API_KEY_1") or "").strip()
    if not key:
        raise RuntimeError("No OPENROUTER_API_KEY_1 for Grok fallback")
    model_list = list(models) if models else [
        "x-ai/grok-4.6",
        "x-ai/grok-4.5",
        "x-ai/grok-4.3",
    ]
    sys_msg = system or (
        "You are a helpful assistant. "
        + ("Respond with valid JSON only." if json_mode else "")
    )
    last_err = None
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
                        "X-Title": "AutoMoviePro Live Test",
                    },
                    json=payload,
                )
            if r.status_code >= 400:
                last_err = RuntimeError(f"{model} {r.status_code}: {r.text[:240]}")
                print("OR fail", model, r.status_code, r.text[:120])
                continue
            content = (
                r.json().get("choices", [{}])[0].get("message", {}).get("content") or ""
            ).strip()
            if content:
                print(f"Grok via OpenRouter OK model={model}")
                return content
        except Exception as exc:
            last_err = exc
            print("OR error", model, exc)
    raise RuntimeError(f"OpenRouter Grok failed: {last_err}")


if not _xai:
    print("NOTE: XAI_API_KEY missing — Stage 1/3 use OpenRouter Grok models for this test")
    grok_client.grok_chat = _openrouter_grok_chat
    import pipeline.custom_pipeline.topic_research as tr
    import pipeline.custom_pipeline.visual_render as vr

    tr.grok_chat = _openrouter_grok_chat
    vr.grok_chat = _openrouter_grok_chat
else:
    print("Using native XAI Grok keys:", len(_xai))


def _preview(obj, limit=1800):
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if len(text) > limit:
        return text[:limit] + "\n… [truncated]"
    return text


def main() -> int:
    from pipeline.custom_pipeline.topic_research import run_topic_research
    from pipeline.custom_pipeline.localization import localize_script, localize_to_languages
    from pipeline.custom_pipeline.visual_render import plan_visual_renders

    out_dir = ROOT / "Output" / "_live_test_custom_pipeline"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "LIVE_TEST_REPORT.md"

    print("\n=== STAGE 1: Topic Research (Grok) ===")
    stage1 = run_topic_research(
        niche="AI Tech Facts",
        video_type="short",
        audience="তরুণ প্রজন্ম",
        output_root=out_dir,
        save=True,
        temperature=0.6,
    )
    pkg = Path((stage1.get("save") or {}).get("package_root") or "")
    topic_json = Path((stage1.get("save") or {}).get("json_path") or "")
    print("Saved:", topic_json)
    seo = (stage1.get("payload") or {}).get("seo_metadata") or {}
    scenes = (stage1.get("payload") or {}).get("script_scenes") or []
    print("Topic:", seo.get("selected_topic"))
    print("Titles:", seo.get("suggested_titles"))
    print("Keywords:", seo.get("seo_keywords"))
    print("Scenes:", len(scenes))
    if scenes:
        s0 = scenes[0]
        print(
            "Shot1 duration/emotion/VO:",
            s0.get("shot_duration_seconds"),
            "|",
            s0.get("emotion_tag"),
            "|",
            str(s0.get("voiceover_script") or "")[:120],
        )

    print("\n=== STAGE 2: Localization (Google dedicated) — English ===")
    stage2_en = localize_script(
        stage1["payload"],
        target_language="English",
        audience_culture="Global English Reader",
        package_root=pkg if pkg.exists() else None,
        output_root=out_dir,
        video_type="short",
        save=True,
    )
    print("Saved:", (stage2_en.get("save") or {}).get("json_path"))
    en_seo = (stage2_en.get("payload") or {}).get("seo_metadata") or {}
    en_scenes = (stage2_en.get("payload") or {}).get("script_scenes") or []
    print("EN Topic:", en_seo.get("selected_topic"))
    print("EN Titles:", en_seo.get("suggested_titles"))
    if en_scenes:
        print(
            "EN Shot1 emotion/VO:",
            en_scenes[0].get("emotion_tag"),
            "|",
            str(en_scenes[0].get("voiceover_script") or "")[:140],
        )

    print("\n=== STAGE 2b: Localization — Hindi (sample) ===")
    stage2_hi = localize_script(
        stage1["payload"],
        target_language="Hindi",
        audience_culture="North Indian",
        package_root=pkg if pkg.exists() else None,
        output_root=out_dir,
        video_type="short",
        save=True,
    )
    print("Saved:", (stage2_hi.get("save") or {}).get("json_path"))
    hi_scenes = (stage2_hi.get("payload") or {}).get("script_scenes") or []
    if hi_scenes:
        print(
            "HI Shot1 emotion/VO:",
            hi_scenes[0].get("emotion_tag"),
            "|",
            str(hi_scenes[0].get("voiceover_script") or "")[:140],
        )

    print("\n=== STAGE 3: Visual Render Plan (Grok IMAGE vs VIDEO) ===")
    stage3 = plan_visual_renders(
        stage1["payload"],
        video_type="short",
        package_root=pkg if pkg.exists() else None,
        output_root=out_dir,
        save=True,
    )
    print("Saved:", (stage3.get("save") or {}).get("json_path"))
    meta = (stage3.get("payload") or {}).get("production_metadata") or {}
    renders = (stage3.get("payload") or {}).get("render_scenes") or []
    print("Meta:", meta)
    for sc in renders[:5]:
        md = sc.get("motion_directives") or {}
        print(
            f"  S{sc.get('shot_number')} {sc.get('render_type')} "
            f"{sc.get('shot_duration_seconds')}s | "
            f"prompt={str(sc.get('visual_prompt') or '')[:90]}… | "
            f"motion={list(md.keys())}"
        )

    # Write markdown report
    lines = [
        "# Custom Pipeline Live Test Report",
        "",
        f"- Package: `{pkg}`",
        f"- Topic JSON: `{topic_json}`",
        f"- Grok transport: `{'native XAI' if _xai else 'OpenRouter fallback (x-ai/grok)'}`",
        f"- Localization key: `LOCALIZATION_GOOGLE_API_KEY (process)`",
        "",
        "## Stage 1 — Topic / Titles / Tags / Script",
        "",
        "```json",
        _preview(stage1.get("payload"), 4000),
        "```",
        "",
        "## Stage 2 — English Localized Script",
        "",
        "```json",
        _preview(stage2_en.get("payload"), 3500),
        "```",
        "",
        "## Stage 2b — Hindi Localized Script (sample)",
        "",
        "```json",
        _preview(stage2_hi.get("payload"), 2500),
        "```",
        "",
        "## Stage 3 — Visual Render Plan (IMAGE vs VIDEO)",
        "",
        "```json",
        _preview(stage3.get("payload"), 4000),
        "```",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\nREPORT:", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
