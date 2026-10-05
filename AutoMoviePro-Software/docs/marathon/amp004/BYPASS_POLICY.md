# Bypass Policy (Frozen)

**Production default:** `NO BYPASS`  
**Production code changed:** `false` — policy document only; enforcement = PHASE-02

---

## Allowed bypass classes (explicit only)

| Class | When | Requirements |
|-------|------|--------------|
| `skip_semantic_validation` | Test / controlled offline | mode + reason + audit trail + scope; **production forbidden** |
| Development-only | `IntelligenceMode.DEVELOPMENT` etc. | `allow_development_bypass` + log warning |
| Test-only | Unit/integration fixtures | Explicit test harness markers |
| Admin override | Future ops tool | Authenticated actor + reason + expiration + scope |
| Recovery/resume | Accepted scenes / plan resume | Identity preserved; not a semantic quality waiver |

প্রতিটি bypass-এ থাকতে হবে:

1. **explicit mode**  
2. **reason**  
3. **audit trail**  
4. **scope** (job/scene)  
5. **expiration / containment** (যখন প্রযোজ্য)  

---

## Forbidden

- Silent production skip of mandatory semantic validation  
- multimodal BLOCKED ignore করে publish  
- Heuristic soft-pass-কে PROVIDER_VERIFIED বলে চালানো  
- Cost-saving critic skip = CRITICAL gate waiver  

---

## Existing surfaces (from audit — disposition)

| Surface | Disposition |
|---------|-------------|
| `skip_semantic_validation` metadata | Production-forbid in PHASE-02 + test |
| Heuristic advisory-only | Honest label — not a bypass of identity HARD |
| `allow_development_bypass` | Keep gated |
| `allow_duplicate` | Document; not semantic waiver |
| Playbook skip multimodal critic | Cost control — not CRITICAL waiver |
| Direct Agnes in scene_builder | Already removed — keep green |

---

## Audit trail minimum fields

`timestamp`, `job_id`, `actor`, `bypass_class`, `reason`, `scope`, `expires_at?`
