# Bypass Audit — AMP-004

**Production code changed:** `false`

---

## Verified bypass / skip surfaces

| Surface | Location | Risk | Disposition |
|---------|----------|------|-------------|
| `skip_semantic_validation` metadata | `agnes_bridge` | Semantic skip | DOCUMENT — production must not set |
| Heuristic semantic advisory-only | agnes_bridge / C3 | Soft pass without vision | HONEST — not false PASS claim |
| `allow_development_bypass` | intelligence gate | Dev only | KEEP gated |
| `allow_duplicate` | generate_video | Skip dup/intel paths | DOCUMENT |
| Plan resume / accepted scenes | resume_guard | Skip rebuild | KEEP with identity |
| Agent playbook skip multimodal critic | agent_playbook | Cost skip | DOCUMENT — not CRITICAL waiver |
| Image/fallback paths | scene_builder / fallback | Was bypass risk | C3 fallback semantic required; full C-4 deferred |
| Direct Agnes in scene_builder | — | **Removed** C2-E | KEEP audit green |
| `generate_agnes_dialogue_clip` | media_assets | Only via bridge provider_fn | OK BRIDGE_INTERNAL |

---

## Domain bypass summary

| Domain | Can production bypass? |
|--------|------------------------|
| Intelligence | Only allow_duplicate / resume edge |
| Scene contract | Fail-closed in prod path |
| Visual identity | Hard block |
| Multimodal full | Partial (heuristic) |
| 04F creative | Fail-closed at end |
| SFX/Music | N/A (absent) |
| Layer-D vision | Effectively “bypassed” by absence |

---

## P0 bypass-related gaps

1. Layer-D absence ⇒ semantic “pass” can be optimistic under heuristic  
2. Multimodal BLOCKED not always wired into publishability AND  
3. Metadata skip flags must be production-forbidden (policy/test)
