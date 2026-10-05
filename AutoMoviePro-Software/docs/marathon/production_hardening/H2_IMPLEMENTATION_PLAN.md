# H2 Implementation Plan — Production Security & Configuration Hardening

**Baseline:** `AMP004-H2-PRE-AUDIT-PASS`  
**Date:** 2026-09-03  
**Authority rule:** Extend `app.config.Settings` + `pipeline.api_keys` — no ConfigEngine2 / SecretManager2.

---

## Findings → fixes

| Finding | Authority | Root cause | Minimal fix |
|---------|-----------|------------|-------------|
| DEF-H2-001 | `app.config.Settings` | `dry_run_publish` missing; pydantic `extra=ignore` drops `DRY_RUN_PUBLISH` | Add `dry_run_publish: bool = True` |
| DEF-H2-002 | `app.main.login` + Settings | Hardcoded `admin`/`admin123`; `AMP_ALLOW_LOCAL_LOGIN` default `1`; `yourdomain.com` allow | Fail-closed local login via Settings; no prod defaults; remove yourdomain allow |
| DEF-H2-003 | Settings + helpers | Ad-hoc `os.environ` for safety flags | Safety flags on Settings; helpers `local_login_allowed`, `amp_skip_active` |
| DEF-H2-004 | `pipeline.api_keys` | Hardcoded `e:\All Project\...` | `DEFAULT_ENV_PATHS` = software-root `.env` only (+ optional env `AMP_EXTRA_ENV_PATHS`) |
| DEF-H2-005 | `video_pipeline` / localization | `AMP_SKIP_*` unchecked in PRODUCTION | `amp_skip_active()` returns False in PRODUCTION |
| DEF-H2-006 | `api_keys` + callers | Fragmented redact | Extend `api_keys` with `redact_sensitive_text` / `redact_mapping`; wire evidence |
| DEF-H2-007 | Channel DB | Plaintext at rest | **Limitation** — no crypto platform; redact API/diagnostics only |
| DEF-H2-009 | Critic skip | Cost policy | Out of H2 (not config/auth); document only |

---

## Security invariants

- S1–S3: Production never uses demo credentials / silent local auth  
- S4: `settings.dry_run_publish` == env == upload behavior  
- S5–S7: `AMP_SKIP_*` cannot disable gates in PRODUCTION  
- S8–S9: Redaction via extended `api_keys` helpers  
- S14–S15: H1 locks untouched; no second authorities  

---

## Files to change

- `app/config.py` — fields + helpers  
- `app/main.py` — login / local-approve use helpers  
- `pipeline/api_keys.py` — paths + redaction helpers  
- `pipeline/e2e_industrial/evidence.py` — use shared redact  
- `pipeline/video_pipeline.py` — `amp_skip_active` for localize/archive  
- `pipeline/localization.py` — archive skip via helper if present  
- `scripts/test_amp004_h2_security_config.py` — NEW  
- Docs: plan, final report, deferred, state, audit log  
- `.env.example` — document new defaults (no secrets)

## Tests

- H2 focused suite (config, auth, skip, redact, dry-run path)  
- Regression: H1, BUILD-03/04A/G subset, Phase-02→10  

## Out of scope

- H3, Phase-11, encrypt-at-rest KMS, new quality engines, H1 lock redesign  

## Rollback

- Revert Settings fields + login helpers; restore previous defaults only in DEVELOPMENT docs  

## Paid APIs

- 0 (mocks/fixtures only)
