# Live production marathon — progress

## Verdict so far
Part-by-part **Topic + Script** live audits are **PASS**. Full six-language production job is still in fix→re-run loop.

## Live evidence
| Run | Result |
|-----|--------|
| `live_part_audit_20260910T035055Z_9c14ca` | Part A+B **PASS** (SEO topic, niche, dup, 7–9s dialogue, continuity) |
| job2313 | semantic/duration/loc/ASR PASS; blocked scene_boundary+audience |
| job2315 | boundary+emotion PASS; blocked visual_repetition (same subject) |
| job2317 | semantic FAIL (false `lunar rover` subject) |
| job2318 | AV hard-fail on year-SKU / static_photo hallucinations |
| Current | restart after documentary AV soften + spectrometer subject fix |

## Code fixes this session
- Topic discovery SEO banks; niche synonym SEO; 7–9s dialogue enforce
- Edge-TTS prefer; translate HF-first; groq circuit not for payload-too-large
- Location continuity; emotion arc; static_hold 10.5s
- Spectrometer ≠ rover remap; year SKU / static_photo documentary soften

## How to watch
`docs/marathon/runs/LIVE_MARATHON_CONSOLE.log` → look for `FINAL_VERDICT=`
