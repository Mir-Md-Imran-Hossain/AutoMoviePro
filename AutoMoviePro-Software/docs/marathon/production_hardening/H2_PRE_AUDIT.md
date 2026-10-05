# H2 Pre-Audit — Production Security & Configuration Hardening

**Date:** 2026-09-03  
**Mode:** READ-ONLY (no production code changes; no paid APIs; no H2 implementation)  
**Baseline checkpoint:** `H1-PRODUCTION-RELIABILITY-PASS`  
**Phase-10 checkpoint (retained):** `AMP004-FINAL-PRODUCTION-CERTIFICATION-PASS`  
**Audit checkpoint:** `AMP004-H2-PRE-AUDIT-PASS`

---

## 1. Executive Summary

AutoMovie Pro’s quality / publishability / idempotency authorities remain intact after H1. Security and configuration hygiene is **not** at the same maturity level.

**Highest-impact findings (no secret values reproduced):**

| ID | Sev | One-line |
|----|-----|----------|
| DEF-H2-001 | **P1** | `Settings` lacks `dry_run_publish`; `.env` `DRY_RUN_PUBLISH` is ignored; upload path AttributeErrors on the safety gate |
| DEF-H2-002 | **P1** | Local/dev login defaults (`admin` / `admin123`, `AMP_ALLOW_LOCAL_LOGIN=1`) match default `api_base_url` containing `yourdomain.com` |
| DEF-H2-003 | **P1** | Dual config authorities: `app.config.Settings` vs `pipeline.api_keys` multi-path `.env` merge vs scattered `os.environ` |
| DEF-H2-004 | **P2** | Hardcoded machine path in `api_keys.DEFAULT_ENV_PATHS` (`e:\All Project\...`) |
| DEF-H2-005 | **P2** | Env skip switches (`AMP_SKIP_LOCALIZE`, etc.) reachable without production identity gate |
| DEF-H2-006 | **P2** | Redaction is fragmented (E2E evidence + agent_chat + FFmpeg argv); not a single production logging boundary |
| DEF-H2-007 | **P2** | Channel DB stores API keys in plaintext columns / `api_keys_json` |
| DEF-H2-008 | **P3** | Local `.env` holds many non-empty provider keys (gitignored; no VCS proof without git) |

**P0:** none observed under current localhost bind defaults.  
**H2 implementation already present?** No (`production_hardening/` contains only H1 docs).  
**Recommendation:** proceed to bounded H2 implementation — **GO**.

---

## 2. Baseline / H1 checkpoint

| Item | Evidence |
|------|----------|
| H1 status | `AMP004_STATE.json` → `h1_checkpoint`: `H1-PRODUCTION-RELIABILITY-PASS` |
| H1 report | `docs/marathon/production_hardening/H1_FINAL_REPORT.md` |
| Phase-10 | `phases.PHASE-10_*` = PASS; certification retained |
| Phase-11 | `NOT_STARTED` |
| H2 code | **Not started** — no H2 implementation files |
| Git | **No `.git`** at workspace root or `AutoMoviePro-Software` — branch/status unavailable |
| Recent hardening surface | H1: `fs_lock.py`, store/reserve/checkpoint/cache locks |
| Deferred | `DEF-AMP004-011` RESOLVED H1; `DEF-001` RESOLVED H1 (local multi-process); quality DEFs unchanged |
| Architecture docs | `docs/marathon/amp004/BYPASS_POLICY.md`, authority freeze logs in `AUDIT_LOG.md` |

---

## 3. Configuration Authority Map

### Observed authorities

| Authority | Location | Role |
|-----------|----------|------|
| **App Settings (partial)** | `app/config.py` → `Settings` / `settings` | Host/port, duration caps, intelligence mode defaults; loads `ROOT/.env` via pydantic-settings |
| **API key bundle** | `pipeline/api_keys.py` → `load_api_bundle` | Merges multiple `.env` paths + `os.environ` + channel slots |
| **Intelligence modes** | `pipeline/intelligence/config.py` | `INTELLIGENCE_MODE` / `INTELLIGENCE_RESEARCH_MODE` (+ settings fallback) |
| **FFmpeg discovery** | `pipeline/compose.py` | `AMP_FFMPEG_*` / `FFMPEG_ROOT` / bundled bins |
| **Direct env reads** | Many modules (`video_pipeline`, `localization`, `scene_builder`, `tts_bridge`, `main`, …) | Feature/skip/upload toggles outside Settings |

### Canonical?

**No single canonical configuration authority.** Closest product settings surface is `app.config.Settings`, but:

1. Declared fields are only: `api_base_url`, `local_host`, `local_port`, `short_max_seconds`, `long_max_seconds`, `intelligence_research_mode`, `intelligence_mode`.
2. Documented `DRY_RUN_PUBLISH` is **not** a Settings field (`extra="ignore"` → env value discarded).
3. Secrets intentionally live in `api_keys.load_api_bundle`, not Settings.
4. Production modules read `os.environ` directly for skips and provider behavior.

### Audit answers

| Question | Answer |
|----------|--------|
| Duplicate loaders? | **Yes** — Settings `.env` + `api_keys` multi-path parse + ad-hoc `os.environ` |
| Random production `getenv`? | **Yes** — widespread |
| Defaults safe? | **Mixed** — intelligence defaults PRODUCTION/LIVE (good); local login allow-by-default (unsafe); dry-run field missing (broken) |
| Silent DEV/TEST fallback? | **Partial** — intelligence MOCK via env; development bypass gated; several AMP_SKIP_* not production-gated |
| Missing required config degrade silently? | **Partial** — missing provider keys usually fail later; dry-run config silently non-functional |
| Validation vs generation config drift? | **Risk** — Settings vs `api_keys` path sets vs env can disagree |

**H2 must extend existing Settings + api_keys surfaces — not invent ConfigEngine2.**

---

## 4. Secret / API-Key Audit

**Policy:** no secret values printed in this report.

| Location | Key / pattern | Classification |
|----------|---------------|----------------|
| `.env.example` | Empty `*_API_KEY*` placeholders | **SAFE** (template) |
| `.env` (local, gitignored) | 60 non-empty secretish key **names** (GOOGLE_*, AGNES_*, GROQ_*, …) | **POTENTIAL_EXPOSURE** (local disk); intended not VCS-tracked |
| `.gitignore` | `.env` listed | **SAFE** intent |
| `installer/automoviepro.spec` | Bundles `.env.example` only | **SAFE** |
| `pipeline/api_keys.py` | Loads keys; `mask_key` last-4 | **REDACTED** diagnostics intent |
| `pipeline/channel_api_slots.py` | `mask_slots` | **REDACTED** for display |
| `app/db.py` channels | `google_api_*`, `agnes_api`, `api_keys_json` plaintext | **POTENTIAL_EXPOSURE** (local SQLite) |
| `pipeline/ai_providers.py`, `media_assets.py`, `llm_router.py`, `freetheai_image.py` | `Authorization: Bearer …` at call site | **SAFE** in-memory if not logged |
| `pipeline/e2e_industrial/evidence.py` | Key-name redaction on detail dict | **REDACTED** (partial) |
| `pipeline/agent_chat.py` | `redact_keys` | **REDACTED** (chat path) |
| `pipeline/rendering_integrity/ffmpeg_boundary.py` | argv token redaction | **REDACTED** (partial) |
| `scripts/test_amp004_phase09…` | Uses literal `"SECRET"` fixture | **TEST-ONLY** |
| `app/main.py` L113–114 | `AMP_DEV_LOGIN_PASSWORD` default string | **POTENTIAL_EXPOSURE** (hardcoded default credential) |
| `venv/**` | Third-party test keys | Out of product scope |

**REAL_EXPOSURE (VCS / packaged binary):** not proven in this workspace (no git; installer excludes `.env`). Local `.env` + SQLite remain operational exposure surfaces.

---

## 5. Production / Test / Dev Boundary

| Surface | Reachable from production identity? | Explicit auth? | Rejected before provider? | Env/CLI activate? | Verdict |
|---------|-------------------------------------|----------------|---------------------------|-------------------|---------|
| `skip_semantic_validation` | Guarded when `production=True` / prod-like identity | Metadata + `semantic_bypass_class` | Yes (`agnes_bridge` pre-provider) | Metadata, not bare env | **CONTAINED** (Phase-02) |
| `allow_development_bypass` | Only if `IntelligenceMode.DEVELOPMENT` | Mode flag | Gate layer | `INTELLIGENCE_MODE=DEVELOPMENT` | **GATED** |
| `INTELLIGENCE_RESEARCH_MODE=MOCK` | Yes if env set | None beyond env | Gate may allow MOCK path | **Yes** | **ENV-ACTIVATABLE** (documented; fail-closed interactions exist for LIVE+PROD mock forbid) |
| `AMP_ALLOW_LOCAL_LOGIN` default `1` | Local UI login | Default password | N/A (auth itself) | **Yes** | **UNSAFE DEFAULT** |
| `AMP_SKIP_LOCALIZE=1` | `generate_video` path | None | Skips localize after ready_to_upload | **Yes** | **ENV BYPASS** (quality scope) |
| `AMP_SKIP_ASSET_ARCHIVE` | Post-generate | None | N/A | **Yes** | Low risk |
| `dry_run_publish` / `DRY_RUN_PUBLISH` | Intended upload gate | Broken field | Upload would AttributeError | Env ignored by Settings | **BROKEN CONTROL** |
| Mock providers (`mock_*_provider`) | Test/idempotency harness | Caller-supplied `provider_fn` / flags | N/A | Test scripts | **TEST-ORIENTED** |
| `should_skip_gemini_critic` | Production scene path when agent passed | Cost policy | Skips critic call | Playbook + comment about `AMP_SKIP_GEMINI_CRITIC` | **COST SKIP** (not CRITICAL publishability waiver; still note) |
| E2E fixtures / OFFLINE_TEST_ONLY | Test/E2E | Fixture markers | Harness | Tests | **TEST-ONLY** |

**Rule preserved in docs:** production bypasses must fail closed. Semantic skip enforcement exists; several env toggles and login defaults do not meet the same bar.

---

## 6. Debug / Bypass Audit

| Bypass concern | Production call-path status |
|----------------|----------------------------|
| Skip semantic validation | **Fail-closed** via `assert_production_semantic_bypass_forbidden` in `agnes_bridge` |
| Skip artifact / render / localization / creative / audio gates | Phase gates remain on industrial path; **not** globally env-skipped (except localize via `AMP_SKIP_LOCALIZE`) |
| UNKNOWN → PASS | Forbidden in publishability / intelligence gate design; Phase-09/10 tests cover |
| `ready_to_upload` without publishability | Industrial runner / `generate_video` gate ordering; Phase-09/10 assert |
| Bypass idempotency | No production env switch found to disable BUILD-03 executor |
| Bypass continuity | No production env skip found |
| Bypass provider preflight | Missing keys generally fail at provider; not replaced by silent mock in LIVE PROD research path (`resolve_research_use_mock` forbids explicit mock) |
| `AMP_SKIP_GEMINI_CRITIC` | Comment in `scene_builder`; actual skip primarily `should_skip_gemini_critic(agent_passed)` — env name appears in tests more than production `getenv` |
| Failure injection | E2E harness only |

**Do not assume “test” in the name implies unreachable** — `allow_test_only_bypass` metadata can widen semantic skip if passed into production-like specs (guarded when `production=True` without allowed class).

---

## 7. Filesystem / Path Safety

| Area | Observation | Risk |
|------|-------------|------|
| Work/output dirs | `DATA_DIR` / `OUTPUT_DIR` under software root | Generally contained |
| Lock identity | H1 `normalize_lock_key` strips `\\?\` | **Do not duplicate** in H2 |
| `api_keys` hardcoded root | `e:\All Project\AutoMovieProSAAS` | Wrong-machine silent miss / unexpected merge if path exists |
| Artifact paths | Mostly `Path(work_dir) / relative` | Low traversal if `work_dir` trusted |
| User-controlled names | Job/channel fields used in paths — **incomplete centralized sanitize audit** | P2 residual |
| Temp files | Various `unlink` / `os.replace` patterns | Mostly local work trees |
| Symlink/reparse | Not systematically defended | P3 / platform |
| Cross-project | work_dir isolation + identity gates (Phase-09/10) | Covered for industrial E2E; general path injection not fully certified |
| FFmpeg paths | Env override + resolve | Operator-controlled; acceptable with trust model |

H2 path work should be **validation/normalization helpers under existing authorities**, not a second lock/identity engine.

---

## 8. Logging / Evidence Redaction

| Path | Classification |
|------|----------------|
| E2E `ExecutionEvidence.end` key-name filter | **REDACTED** (keys only; nested/Authorization values may miss) |
| `agent_chat.redact_keys` | **REDACTED** for chat |
| FFmpeg controlled argv | **REDACTED** token substrings |
| General `logger.exception` / provider HTTP | **POTENTIAL LEAK** if response/headers logged with Bearer |
| `api_keys` “never logs secret values” docstring | Intent **SAFE**; not proven for all call sites |
| Channel seed logs counts not keys | **SAFE** pattern |
| Provenance tests (BUILD-04A) | Assert no `api_key`/`Bearer` strings in text |

**No centralized production redaction authority.** Duplicate partial helpers — H2 should extend one existing helper (prefer `api_keys.mask_key` / `agent_chat.redact_keys` consolidation), not SecretRedactor2.

---

## 9. Provider Configuration

```
app / channel DB / .env
  → load_api_bundle / channel_provider_keys
  → adapters (Agnes, Google, Pollinations, Groq, …)
  → provider call
```

| Topic | Status |
|-------|--------|
| Required keys | Provider-specific; readiness via `evaluate_readiness` |
| Missing key behavior | Generally fail / skip provider; research LIVE+PROD blocks forced mock |
| Default / fallback | Image priority env; Edge TTS prefer flags; intelligence MOCK only if mode MOCK |
| Silent mock in production LIVE | **Forbidden** for explicit mock research (`resolve_research_use_mock`) |
| Retry / timeout | Per-provider; not fully audited for unbounded loops here |
| Traceable identity | Fingerprints / provenance exist for visual/idempotency |
| Bypass around pipeline | Direct Agnes path historically removed; adapters remain (documented Phase-09) |

**Paid APIs:** this audit made **0** provider/network calls.

---

## 10. Deployment Configuration

| Requirement | Classification |
|-------------|----------------|
| Python version | **PARTIAL** — `INSTALL_GUIDE_BN.md` says 3.11+; no `python_requires` in packaging metadata audited |
| Required env vars | **PARTIAL** — `.env.example` lists keys; Settings does not declare/enforce publish/safety fields |
| Filesystem permissions | **IMPLICIT** |
| FFmpeg / FFprobe | **EXPLICIT** discovery + Phase-10 bundled path; env overrides documented |
| Output/cache dirs | **IMPLICIT** mkdir on import |
| Provider configuration | **PARTIAL** — example + channel UI; no single fail-closed “production ready” checklist enforced at boot |
| Logging configuration | **IMPLICIT** |
| Local login disable | **PARTIAL** — `AMP_ALLOW_LOCAL_LOGIN=0` exists but defaults allow |

Fresh install can discover FFmpeg if bundled; cannot rely on Settings for dry-run publish safety today.

---

## 11. Authority Duplication Audit

| Authority | Duplicate? |
|-----------|------------|
| Idempotency (BUILD-03) | **No** — H1 extended only |
| Publishability | **No** |
| BUILD-04F creative score | **No** |
| ContinuityTracker | **No** |
| prompt_compiler / SceneIntent | **No** |
| Artifact Verification | **No** |
| FFmpeg compose/render | **No** competing engine |
| Bypass policy | Doc + Phase-02 enforcement — **intact** |
| Configuration | **Yes — fragmented** (Settings / api_keys / getenv) |
| Secret redaction | **Yes — fragmented helpers** |
| Filesystem lock identity | **No** — H1 only |

H2 must **not** create competing quality/idempotency/FFmpeg engines.

---

## 12. Existing Test Coverage

| Concern | Existing evidence | Gap |
|---------|-------------------|-----|
| Semantic bypass production forbid | Phase-02 / Phase-09 tests | OK |
| Evidence redaction | Phase-09 `test_18` | Narrow (key names only) |
| Intelligence fail-closed / MOCK | BUILD-04G / marathon task004–005 | OK for research gate |
| Missing FFmpeg | Phase-09/10 capability probes | OK |
| Publishability blocking | Phase-02/09/10 | OK |
| `DRY_RUN_PUBLISH` ↔ Settings | **Missing** — field absent; upload AttributeError untested as invariant |
| Local login default denial in “production” | **Missing** | |
| `AMP_SKIP_LOCALIZE` production forbid | **Missing** | |
| Global logger secret leak | **Missing** | |
| Path traversal / unsafe join | **Sparse** | |
| Channel DB key at-rest protection | **Missing** | |
| Boot-time required config validation | **Missing** | |

Do not weaken existing assertions. H2 should add focused tests only for new invariants.

---

## 13. Findings by Severity

### P0

*None.*

### P1

**DEF-H2-001 — Dry-run publish control broken**  
- **File:** `app/config.py`; consumers `publishers/upload_service.py`, `pipeline/video_pipeline.py` (~1204), `pipeline/live_lab.py`  
- **Observed:** `Settings` has no `dry_run_publish`; `.env` `DRY_RUN_PUBLISH` ignored; `hasattr` false; setattr rejected; upload checks AttributeError  
- **Risk:** Documented safety switch non-functional; upload path crashes instead of controlled dry-run; config drift vs install docs  
- **Reachability:** Production upload API  
- **Protection:** Accidental fail via AttributeError (not a designed fail-closed control)  
- **Minimal action:** Add field to existing `Settings` (default `true` fail-closed); wire upload/live_lab; tests  

**DEF-H2-002 — Default local/dev login credentials**  
- **File:** `app/main.py` ~109–139, ~691  
- **Observed:** `AMP_ALLOW_LOCAL_LOGIN` default `1`; defaults `admin` / `admin123`; allows when base contains `yourdomain.com` (matches Settings default `https://yourdomain.com`)  
- **Risk:** Unauthenticated-equivalent local admin on first run / default config  
- **Reachability:** UI login on `local_host` (default `127.0.0.1`)  
- **Protection:** Loopback bind reduces remote exploit; still unsafe default for shared hosts  
- **Minimal action:** Default deny local login unless explicit env; remove hardcoded password default; require strong explicit secret  

**DEF-H2-003 — Fragmented configuration authority**  
- **Files:** `app/config.py`, `pipeline/api_keys.py`, widespread `os.environ`  
- **Observed:** Multiple loaders; safety flags outside Settings  
- **Risk:** Validation/generation drift; silent ignore of required env  
- **Minimal action:** Extend Settings for safety flags; document api_keys as sole secret loader; reduce ad-hoc getenv for security-sensitive toggles  

### P2

**DEF-H2-004** — Hardcoded `_WORKSPACE_ROOT` in `pipeline/api_keys.py` L13 (`e:\All Project\AutoMovieProSAAS`) — machine-specific; unexpected merge if path exists.  

**DEF-H2-005** — `AMP_SKIP_LOCALIZE` (and similar) activate from env without production identity / audit trail.  

**DEF-H2-006** — Redaction not global; risk of Bearer/headers in exception logs (`POTENTIAL LEAK`).  

**DEF-H2-007** — Channel SQLite plaintext API key storage.  

**DEF-H2-009** — Cost-oriented Gemini critic skip (`should_skip_gemini_critic`) is production-reachable; not a publishability AND bypass but weakens critic coverage.  

**DEF-H2-010** — Incomplete centralized path sanitization for user-influenced filenames.  

### P3

**DEF-H2-008** — Local `.env` populated with many keys (gitignored); operator hygiene / packaging checklist.  

**DEF-H2-011** — Deployment docs PARTIAL; no single production readiness boot gate.  

**DEF-H2-012** — No git repository in this workspace — cannot prove `.env` never committed historically.

---

## 14. Required Minimal Actions (for future H2 implementation only)

1. Restore `dry_run_publish: bool = True` (or equivalent) on existing `Settings`; default **fail-closed**; honor `DRY_RUN_PUBLISH`; fix upload/live_lab.  
2. Harden local login: default `AMP_ALLOW_LOCAL_LOGIN=0` (or equivalent fail-closed); no hardcoded password default; drop `yourdomain.com` auto-allow.  
3. Declare security-sensitive toggles on Settings (or explicit allowlist); stop silent ignore of safety env.  
4. Remove/replace hardcoded foreign `_WORKSPACE_ROOT` with software-root-relative paths only.  
5. Gate `AMP_SKIP_*` quality skips behind explicit non-production class + audit (fail-closed in production).  
6. Extend **one** existing redaction helper to logging/exception boundaries (no SecretManager2).  
7. Document channel key at-rest risk; minimal protection or explicit threat-model acceptance.  
8. Add focused tests for DEF-H2-001/002/005; keep paid APIs = 0.  
9. Do **not** touch publishability AND, ContinuityTracker, BUILD-04F, FFmpeg authority, or H1 lock identity except config callers.

---

## 15. H2 Scope Decision

```
H2_PRE_AUDIT_GO
```

**Rationale:** No P0. Open P1s are configuration/auth defaults and are appropriate **bounded H2 implementation** targets (same pattern as H1 pre-audit GO with open P1). Quality/idempotency baseline from Phase-10 + H1 remains valid. Limitations (P2/P3) are in-scope for hardening but not blockers to starting H2.

**Out of scope for H2 pre-audit / must not start now:** H2 implementation, H3, Phase-11, new engines, paid APIs, code fixes.

---

## 16. Exact Checkpoint

```
AMP004-H2-PRE-AUDIT-PASS
```

---

```
H2_PRE_AUDIT_STATUS: GO
```

**CHECKPOINT:** `AMP004-H2-PRE-AUDIT-PASS`

**STOP** — do not implement H2 in this audit turn.
