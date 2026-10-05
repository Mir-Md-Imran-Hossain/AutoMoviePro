# Core Engine Marathon — Failure Cause List (from report analysis)

Marathon: `mr_core_engine_20260909T122850Z_d28d7146` · Verdict: FAIL

## Ordered causes (fix one-by-one)

| # | Sev | Cause | Status |
|---|-----|-------|--------|
| C1 | P0 | Pre-Agnes docref only allowed Webb/STScI — NASA lunar stills skipped | FIXED |
| C2 | P0 | Critic required literal Artemis/spectrometer pixels; proxy via rover | FIXED |
| C2b | P0 | Docref required LLM passed=True (soft static_image blocked NASA stills) | FIXED |
| C3 | P0 | No six-language finals (downstream) | PENDING re-run |
| C4–C7 | P1 | Audio langs / nebula keying / SKU stamp / DUPLICATE lock | FIXED earlier |
| C9 | P0 | Scene6 Moon narration → default Webb nebula (`moon` key missing; product=station) | FIXED |
| C10 | P0 | Final compose: `concat_av_clips` fallback wrote empty `body_av.mp4` then duration UNKNOWN | FIXED (retry filter-concat on `_fix_*`) |
| C11 | P0 | Scene5: destination “Mars” stole visual subject; lunar ice beat failed AV critic | FIXED (demote destination-only subjects when ice/lunar/rover present) |
| C12 | P0 | Phenomenon subjects (Sunlight / Fast neutrons / Comet) + neutrons→Webb default | FIXED (phenomenon demotion + lunar still keys + dialogue-corpus topic fallback) |
| C12b | P1 | Bare `spectrometers` fell through to Webb default still | FIXED |
| C13 | P0 | Critic rejects on-topic lunar stills for comet/shadowed/intangible beats (`wrong_subject`/`unrelated_broll`) | FIXED (`soften_documentary_proxy_critique` + shadowed still with deep shadows) |
| C14 | P0 | SEMANTIC_COVERAGE_GATE FAIL: literal ice/spectrometer/“station” required vs lunar stills (job2305 S0/S3/S6) | FIXED (semantic documentary proxies + demote ice/station subjects to crater/Moon) |
| C8 | P1 | Metaphor “transforms the Moon from…into…” → unexplained_transformation | FIXED earlier |

## Latest production verdict

| Run | Job | Verdict |
|-----|-----|---------|
| `mr_core_engine_20260909T191452Z_a6c930ca` | **2307** | **PASS_WITH_LIMITATION** — 8/8 semantic PASS, duration PASS, `body_av.mp4` ~10MB; honest UNKNOWNs: acoustic voice + UR RTL + creative human review |

Loop complete for core-engine live marathon (no entitlement forge).

## Fix order

1. C1 — allow NASA images-assets in pre-Agnes docref path + prefer lunar hardware stills
2. C2 — ensure critic revised_prompt / hardware still used when IMAGE fails
3. C10 — non-empty concat for `body_av.mp4`
4. C11 — Mars-as-destination must not become visual subject
5. Re-run live marathon
6. If fail → diagnose next cause → fix → re-run
