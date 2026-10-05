# H2 Final Report — Production Security & Configuration Hardening

**Date:** 2026-09-03  
**Final status:** `H2-PRODUCTION-SECURITY-CONFIG-PASS-WITH-LIMITATION`  
**Checkpoint:** `AMP004-H2-PRODUCTION-SECURITY-CONFIG-PASS-WITH-LIMITATION`

---

## 1. Executive Summary

H2 restores canonical configuration for publish safety and closes unsafe default local authentication. `dry_run_publish` is a real `Settings` field (default `true`). Local login is fail-closed in PRODUCTION (no `admin`/`admin123` fallback; no `yourdomain.com` allow). `AMP_SKIP_*` is ignored in PRODUCTION. Secret redaction consolidated under `pipeline.api_keys`. Hardcoded foreign `.env` path removed. Paid APIs = **0**. H1 + Phase-02→10 regressions PASS. Channel-key **at-rest encryption** remains a documented limitation (no KMS invented).

---

## 2. Baseline

| Item | Value |
|------|-------|
| Pre-audit | `AMP004-H2-PRE-AUDIT-PASS` |
| H1 | `H1-PRODUCTION-RELIABILITY-PASS` |
| Phase-10 | `AMP004-FINAL-PRODUCTION-CERTIFICATION-PASS` |
| Git | Unavailable (no `.git`) |

---

## 3. H2 Pre-Audit Reference

`docs/marathon/production_hardening/H2_PRE_AUDIT.md` — GO; findings DEF-H2-001…008.

---

## 4. Implementation Plan

`docs/marathon/production_hardening/H2_IMPLEMENTATION_PLAN.md`

---

## 5. Configuration Authority Changes

**Canonical runtime config:** `app.config.Settings` (+ helpers).  
**Canonical secret loader paths:** `app.config.software_env_paths` → consumed by `pipeline.api_keys`.  
**Not moved into Settings:** provider API keys (remain `load_api_bundle`).

Helpers: `is_production_runtime`, `local_login_permitted`, `amp_skip_active`, `safe_config_diagnostics`, `api_base_allows_local_login`.

---

## 6. dry_run_publish Fix

- Field: `Settings.dry_run_publish: bool = True`
- Loads `DRY_RUN_PUBLISH` from `.env` via pydantic-settings
- Upload path (`publishers/upload_service.py`) uses `settings.dry_run_publish`
- Tests prove env → Settings → dry-run URL vs live mock upload

---

## 7. Authentication Hardening

- `amp_allow_local_login` default **False**
- PRODUCTION: requires allow flag + non-empty `amp_dev_login_id` and `amp_dev_login_password` — **no demo defaults**
- DEVELOPMENT: demo `admin`/`admin123` only when allow flag True
- `app.main.login` uses `local_login_permitted` only (no hardcoded password in login source)

---

## 8. Domain Allowlist Hardening

- Removed `yourdomain.com` auto-allow
- Default bases: local / localhost / offline / 127.0.0.1 / http://localhost
- Optional `AMP_LOCAL_LOGIN_BASES` for explicit extension

---

## 9. Production / Test / Dev Boundary

- `intelligence_mode` PRODUCTION vs DEVELOPMENT gates skip + login credential defaults
- Semantic bypass (Phase-02) unchanged and still fail-closed

---

## 10. AMP_SKIP_* Boundary

- `amp_skip_active(name)` — PRODUCTION always returns False (logs error); DEVELOPMENT honors env
- Wired: `AMP_SKIP_LOCALIZE`, `AMP_SKIP_ASSET_ARCHIVE` in `video_pipeline` / `localization`

---

## 11. Secret / Redaction Hardening

- Extended `pipeline.api_keys`: `redact_sensitive_text`, `redact_mapping`
- `evidence.py` and `agent_chat.redact_keys` consume shared helpers
- Diagnostics: `safe_config_diagnostics` never emits passwords

---

## 12. Channel-Key Handling

- API list path already masks slots / replaces `api_keys_json` with `[encrypted]` label in responses
- **At-rest SQLite plaintext remains** — limitation (no invent KMS in H2)

---

## 13. Filesystem / Path Hardening

- Removed `e:\All Project\AutoMovieProSAAS` from `DEFAULT_ENV_PATHS`
- Optional `AMP_EXTRA_ENV_PATHS` (pathsep-separated)
- H1 `normalize_lock_key` / `exclusive_path_lock` **untouched** (proven by H2 + H1 tests)

---

## 14. Provider Configuration Hardening

- No silent mock introduction; secret paths software-root only
- Missing credentials still fail at provider/session (upload without session fails closed when not dry-run)

---

## 15. Deployment Configuration

| Item | Class |
|------|-------|
| DRY_RUN_PUBLISH | **EXPLICIT** (Settings) |
| AMP_ALLOW_LOCAL_LOGIN + credentials | **EXPLICIT** |
| FFmpeg | EXPLICIT (prior Phase-10) |
| Provider keys | PARTIAL (`.env.example`) |
| Channel key encryption | **IMPLICIT / UNSAFE at rest** (limitation) |

Updated: `.env.example`, `INSTALL_GUIDE_BN.md` tips.

---

## 16. Authority Duplication Audit

| Authority | Status |
|-----------|--------|
| Settings | Single extended |
| api_keys redaction | Single extended |
| Idempotency / publishability / FFmpeg / Continuity / 04F | Unchanged |
| H1 fs_lock | Unchanged |

No ConfigEngine2 / SecretManager2.

---

## 17. Security Invariants

| ID | Result |
|----|--------|
| S1–S3 auth fail-closed | **PASS** (tests 10–16) |
| S4 dry_run canonical | **PASS** (tests 01–03) |
| S5–S7 AMP_SKIP / gates | **PASS** (tests 20–21; Phase-02→10) |
| S8–S9 redaction | **PASS** (tests 30–32; P09 evidence) |
| S10–S12 provider | **PASS** with existing fail paths |
| S13 path isolation | Prior Phase-09/10; H2 no regression |
| S14 H1 locks | **PASS** (H1 9/9 + test_42) |
| S15 no second authority | **PASS** |

---

## 18. Tests Executed

| Command | Result |
|---------|--------|
| `python -m unittest scripts.test_amp004_h2_security_config -v` | **20/20 PASS** |
| `python -m unittest scripts.test_amp004_h1_reliability` | **9/9 PASS** |
| `python -m unittest` BUILD-03 + AMP-003 T003/concurrency + 04G-H1 + reserve + 04A + 04G harden | **82 PASS** |
| `python -m unittest` Phase-02→10 | **398 PASS** |
| `…Phase09E2EIndustrialQATests.test_18_evidence_redacts_secrets` | **PASS** |
| `python scripts/test_live_lab.py` | **22 passed** |
| `python scripts/test_features_5_12.py` | **FAIL** one pre-existing resume-folder assert (`test_find_resumable_prefers_folder_with_accepted_clips`) — unrelated to H2 config/auth; dry_run assert still valid |

SKIP: none intentional.

---

## 19. Regression Results

- H1 reliability: PASS  
- BUILD-03/04A/G subset: PASS (82)  
- Phase-02→10: PASS (398)  
- No assertions weakened  

---

## 20. Paid API Usage

**0**

---

## 21. Remaining Limitations

1. **DEF-H2-007:** Channel API keys remain plaintext in local SQLite — no encrypt-at-rest platform in H2.  
2. **DEF-H2-009:** Cost-oriented Gemini critic skip unchanged (not a config/auth bypass of publishability AND).  
3. Logging of arbitrary exception strings outside redacted paths may still leak if callers embed raw keys (mitigated for evidence/chat/argv patterns).  
4. Operator `.env` may set `DRY_RUN_PUBLISH=false` — intentional live publish when configured; default code remains dry-run.  

---

## 22. Findings Closed

| ID | Status |
|----|--------|
| DEF-H2-001 dry_run | **CLOSED** |
| DEF-H2-002 default login | **CLOSED** |
| DEF-H2-003 config fragmentation (safety flags) | **CLOSED** (bounded) |
| DEF-H2-004 hardcoded path | **CLOSED** |
| DEF-H2-005 AMP_SKIP | **CLOSED** |
| DEF-H2-006 redaction | **CLOSED** (bounded consolidation) |

---

## 23. Findings Deferred

| ID | Note |
|----|------|
| DEF-H2-007 | At-rest encryption — future |
| DEF-H2-008 | Local `.env` hygiene / git history — ops |
| DEF-H2-009 | Critic cost skip — quality/cost policy |
| DEF-H2-010 | Broader path traversal suite — future |

---

## 24. Final Scope Decision

```
H2-PRODUCTION-SECURITY-CONFIG-PASS-WITH-LIMITATION
```

Limitations are P2/P3 at-rest and non-config quality skips — required security invariants for H2 config/auth/skip/redaction/dry-run are proven.

---

## 25. Exact Checkpoint

```
AMP004-H2-PRODUCTION-SECURITY-CONFIG-PASS-WITH-LIMITATION
```

### Changed files (reason / authority / impact)

| Path | Reason | Authority | Impact |
|------|--------|-----------|--------|
| `app/config.py` | Settings fields + helpers | Config | dry_run, login, skip |
| `app/main.py` | Login / local-approve | Auth via Settings | Fail-closed local login |
| `pipeline/api_keys.py` | Paths + redact helpers | Secret load/redact | No hardcoded root; shared redact |
| `pipeline/video_pipeline.py` | amp_skip_active | Config gate | Skip blocked in PRODUCTION |
| `pipeline/localization.py` | amp_skip_active | Config gate | Same |
| `pipeline/e2e_industrial/evidence.py` | Shared redact | api_keys | Consistent redaction |
| `pipeline/agent_chat.py` | Delegate redact_keys | api_keys | Single text redactor |
| `.env.example` | Document flags | Docs | Operator clarity |
| `INSTALL_GUIDE_BN.md` | Local login tips | Docs | Deploy clarity |
| `scripts/test_amp004_h2_security_config.py` | NEW tests | — | Prove invariants |
| `docs/marathon/production_hardening/H2_*.md` | Plan + report | — | Audit trail |

**STOP** — do not start H3 / Phase-11.
