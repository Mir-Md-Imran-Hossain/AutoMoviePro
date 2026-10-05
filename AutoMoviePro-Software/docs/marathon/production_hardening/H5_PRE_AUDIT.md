# H5 Pre-Audit — Release Packaging & Operational Readiness

**Date:** 2026-09-03  
**Mode:** READ-ONLY (no source/test changes; no installs; no paid APIs; no H5 implementation)  
**Baseline checkpoints:**  
- H1: `H1-PRODUCTION-RELIABILITY-PASS` / `AMP004-H1-PRODUCTION-RELIABILITY-PASS`  
- H2: `AMP004-H2-PRODUCTION-SECURITY-CONFIG-PASS-WITH-LIMITATION`  
- H3: `AMP004-H3-PERFORMANCE-COST-PASS-WITH-LIMITATION`  
- H4: `AMP004-H4-REAL-WORKFLOW-PASS-WITH-LIMITATION`  
- Phase-10: `AMP004-PHASE10-PASS`  
**Audit checkpoint:** `AMP004-H5-PRE-AUDIT-PASS`  
**Paid APIs this audit:** **0**

---

## 1. Executive Summary

AutoMovie Pro’s **evidenced primary deployment model** is a **Windows local process**: `START.bat` → venv → `python -m app.main` (FastAPI/uvicorn) with project-bundled `ffmpeg-8.1.1-full_build` discoverable via `pipeline.compose`. On this host, FFmpeg/ffprobe probe = **AVAILABLE / bundled**. H1–H4 gates (auth fail-closed, AMP_SKIP blocked in PRODUCTION, publishability AND, scheduler no longer forces `ready_to_upload`) remain intact by source inspection.

**No P0/P1 release blockers** for continuing into H5 **implementation** against the source-tree Windows desktop model. Bounded **P2/P3** gaps: PyInstaller dist does **not** ship FFmpeg; dependency ranges without lockfile; no formal app version/build identity; ad-hoc SQLite ALTERs (no Alembic); `/api/status` is process/API readiness, not media-tool readiness; shutdown is PARTIAL; backup/rollback poorly documented; DEF-H2-007 keys-at-rest remains open.

**Recommendation:** `H5_PRE_AUDIT_GO_WITH_LIMITATIONS`.

---

## 2. Baseline

| Item | Evidence |
|------|----------|
| H4 | `H4_FINAL_REPORT.md` — workflow PASS-WITH-LIMITATION; packaging before ready; soft-handoff contained |
| H3 | Retry/TTS/loc reuse; COST_NOT_DETERMINABLE; DEF-H3-008/009/010 open |
| H2 | Settings authority; dry_run default; local login fail-closed; AMP_SKIP blocked; DEF-H2-007 open |
| H1 | `normalize_lock_key` + `exclusive_path_lock` |
| Phase-10 | Bundled FFmpeg discovery; industrial E2E certified on host |
| Deferred carry | DEF-H4-003/004/005; DEF-AMP004-001 VLM/ASR; dual prompt LEGACY |
| Existing release mechanisms | `START.bat`, `installer/automoviepro.spec` + `build_exe.bat`, `INSTALL_GUIDE_BN.md`, `.env.example` |
| Docker/CI | **ABSENT** in repo root (no Dockerfile, no compose, no project `.github` workflows found) |

---

## 3. Release Artifact Inventory

| Item | Class | Notes |
|------|-------|-------|
| `app/`, `pipeline/`, `publishers/`, `hidden_engage/`, `domain/` | REQUIRED | Runtime Python |
| `ui/` (+ static) | REQUIRED | Local UI |
| `requirements.txt` | REQUIRED | Dep install |
| `.env.example` | REQUIRED (template) | Placeholders only |
| `.env` | REQUIRED at runtime / DEVELOPMENT_ONLY in VCS | gitignored |
| `data/` (SQLite etc.) | REQUIRED at runtime | gitignored; created by `init_db` |
| `output/`, work dirs | REQUIRED at runtime | Auto-created / job-local |
| `ffmpeg-8.1.1-full_build/**` | REQUIRED for media (source deploy) | Discovered; **not** in PyInstaller datas |
| `START.bat` | REQUIRED (dev/source start) | Creates venv, pip, playwright |
| `installer/automoviepro.spec`, `build_exe.bat` | OPTIONAL packaging | Incomplete media packaging |
| `scripts/test_*` | TEST_ONLY | Not needed at runtime |
| `docs/` | OPTIONAL / DEVELOPMENT_ONLY | Ops docs partial |
| `venv/` | DEVELOPMENT_ONLY | Local env |
| `pyinstaller` in requirements | DEVELOPMENT_ONLY (listed as runtime dep) | Packaging tool |
| Lockfiles (`poetry.lock` / `requirements.lock`) | MISSING | — |
| `pyproject.toml` / `setup.py` | ABSENT | — |
| Docker images | ABSENT | — |

Do not treat every repo file as release-required.

---

## 4. Reproducible Environment

| Concern | Status | Evidence |
|---------|--------|----------|
| OS | EXPLICIT (Windows) | README, INSTALL_GUIDE_BN (Win 10/11) |
| Python | PARTIAL | Guide: 3.11+; this host 3.12.9; no `python_requires` metadata |
| Pip deps | PARTIAL | `requirements.txt` ranges (`>=`) only |
| Lockfile | MISSING | None found |
| FFmpeg | PARTIAL | Bundled tree + PATH/env; installer omits |
| Playwright Chromium | EXPLICIT in START/build | Browser automation |
| Env vars | PARTIAL | `.env.example` lists many; Settings subset |
| Linux/macOS | NOT_SUPPORTED (as claim) | No evidence of supported non-Windows release |
| Docker | UNSUPPORTED | No files |

---

## 5. Dependency Determinism

| Finding | Detail |
|---------|--------|
| Pins | **Unpinned ranges** (`fastapi>=0.110.0`, etc.) |
| Lock | **None** |
| Drift risk | HIGH across fresh installs over time |
| Runtime vs build | `pyinstaller` listed beside runtime deps |
| Platform | Windows assumed; playwright OS-specific |
| Missing on fresh | Without START.bat/playwright install, browser paths fail; without FFmpeg tree/PATH, media fails at pipeline |

**Classification:** PARTIAL / NON_REPRODUCIBLE for bit-identical environments.

---

## 6. FFmpeg / ffprobe Release Readiness

**Discovery (canonical):** `pipeline/compose.py`  
Order: env bins → `AMP_FFMPEG_ROOT`/`FFMPEG_ROOT` → `_bundled_bin` (`tools/ffmpeg`, `ffmpeg-*/**/bin`) → PATH.  
FFmpeg and ffprobe discovered **independently**.  
`probe_media_tool_capability()` runs `-version` (DETERMINISTIC).

**This host (executed probe):**

| Tool | Available | Source | Path (redacted root) |
|------|-----------|--------|----------------------|
| ffmpeg | True | bundled | `…/ffmpeg-8.1.1-full_build/…/bin/ffmpeg.exe` |
| ffprobe | True | bundled | `…/ffmpeg-8.1.1-full_build/…/bin/ffprobe.exe` |

**PyInstaller:** `binaries=[]`; datas include ui/pipeline/app/…/`.env.example` — **no FFmpeg binaries**. Installer docs mention PATH FFmpeg but do not bundle.

**Startup:** App does **not** refuse to start if FFmpeg missing.  
**Pipeline:** Render/RI/publishability fail-closed when media tools/outputs fail (H4/P08/P10 evidence) — not silent `ready_to_upload`.

**Invariant:** Missing tools do not produce false **upload readiness**; they can produce false **process “ok”** via `/api/status` (see §11).

---

## 7. Configuration Release Audit

| Authority | Role |
|-----------|------|
| `app.config.Settings` | Canonical runtime Settings (H2) |
| `pipeline.api_keys` | Provider keys / redaction |
| `.env` / `.env.example` | Env injection |
| Channel DB fields | Per-channel keys (`api_keys_json`) |

**REQUIRED vs OPTIONAL:** PARTIAL — `.env.example` documents many keys; Settings only models a subset; channel readiness via `evaluate_readiness`.

**Fail-closed preserved (H2):**  
- `dry_run_publish` default True  
- Local login denied in PRODUCTION without explicit allow + credentials  
- `AMP_SKIP_*` blocked when `INTELLIGENCE_MODE=PRODUCTION`  
- No `yourdomain.com` in local-login allowlist  

**Residual:** Settings class default `api_base_url="https://yourdomain.com"` still present (login allowlist does not treat it as local) — documentation/default hygiene P3.

---

## 8. Secret / Credential Audit

| Location | Class | Notes |
|----------|-------|-------|
| `.env` | POTENTIAL_EXPOSURE if packaged | **gitignored**; not in PyInstaller datas |
| `.env.example` | SAFE | Placeholders |
| Channel keys in SQLite | POTENTIAL_EXPOSURE / DEF-H2-007 | Plaintext at rest (known) |
| API responses / evidence | REDACTED | H2 `redact_mapping` / mask |
| Logs | PARTIAL | Redaction on known paths; not audited every logger call this session |
| Release dist datas | SAFE for `.env` | Only `.env.example` listed |
| Test fixtures | TEST_ONLY | Assume no live secrets (not re-scanned for values) |

**Never printed secret values this audit.**  
**DEF-H2-007 remains OPEN** — not closed by H4/H5 pre-audit.

---

## 9. Production / Test / Development Boundary

| Mechanism | Production behavior |
|-----------|---------------------|
| `INTELLIGENCE_MODE=PRODUCTION` | Default Settings |
| `AMP_SKIP_*` | Blocked in PRODUCTION (`amp_skip_active`) |
| Local login | Fail-closed unless explicit |
| `DRY_RUN_PUBLISH` | Default true |
| E2E soft handoff | Offline runner only (`allow_soft_handoff`); not `generate_video` |
| Mock render | E2E/test harness |
| Scheduler ready override | **Removed in H4** |

Import-time: Settings load from `.env`; no automatic mock provider activation found for production generate path in this audit.

---

## 10. Startup Behavior

**Entry:** `START.bat` → `python -m app.main` → `main()` / FastAPI `startup`  
**Startup steps:** `store.init_db()` → optional `seed_channel_from_env()` → `scheduler.start()` → uvicorn on `local_host:local_port` → opens browser.

| Condition | Observed behavior (static) |
|-----------|----------------------------|
| Missing `.env` | Settings defaults apply (dry_run true; PRODUCTION mode) |
| Missing FFmpeg | App still starts; media jobs fail later |
| Missing provider keys | `/api/status` inactive / readiness missing slots |
| DB | Created via `CREATE TABLE IF NOT EXISTS` |
| Invalid config | Pydantic/settings load; not a dedicated boot gate for all required keys |

**Classification:** PARTIAL graceful startup — process-up ≠ media-ready.

---

## 11. Health / Readiness

| Endpoint / signal | Meaning |
|-------------------|---------|
| `/api/status` | Process responds; login; channel API readiness (`evaluate_readiness`); dry_run flag |
| Session health | Publisher session vault check (`/api/channels/{id}/session-health`) |
| K8s-style `/health` `/ready` | **ABSENT** |
| FFmpeg in status | **ABSENT** |

**PROCESS ALIVE** ≠ **READY FOR PRODUCTION MEDIA WORK**. Documented absence of media readiness probe.

---

## 12. Database / Storage

| Store | Init | Notes |
|-------|------|-------|
| SQLite (`data/`, `local.db` present on host) | `init_db()` | Session, channels, jobs, meta, posts, assets… |
| Job work dirs / output | Runtime mkdir | Artifact/checkpoint/idempotency under work |
| GenerationCache / IdempotencyStore / CheckpointStore / reserves | BUILD-03 | H1 locks intact |
| JSON caches | Various under pipeline/data | |

Concurrent startup: SQLite + file locks; H1 normalize_lock_key retained (source).

---

## 13. Migration

| Mechanism | Classification |
|-----------|----------------|
| Alembic / schema_version table | **ABSENT** |
| `CREATE TABLE IF NOT EXISTS` + try/except `ALTER TABLE … ADD COLUMN` | **PARTIAL** (`app/db.py`) |
| Formal upgrade/downgrade | **ABSENT** |

**NOT_REQUIRED_WITH_EVIDENCE?** No — ad-hoc ALTERs are acceptable for single-desktop SQLite **only with** documented compatibility; multi-version field upgrades remain a **release risk** (P2).

---

## 14. Filesystem / Permissions

- `DATA_DIR`, `OUTPUT_DIR`, `ASSETS_DIR` auto-`mkdir` in config.  
- Work/export/localize dirs created in pipeline.  
- Windows paths; H1 extended-path normalization for locks.  
- `.gitignore` excludes `data/`, `output/`, `.env`, `dist/`, `build/`, media, logs.  
- Disk exhaustion: **UNSPECIFIED** (no dedicated handler found).  
- Destructive tests: not run.

---

## 15. Logging / Diagnostics

- Uvicorn `log_level=info`; pipeline loggers.  
- E2E evidence / H3 usage ledger carry job/operation/latency fields when used.  
- H2 redaction on evidence paths.  
- Operator diagnosis of failed generate: logs + gate JSON under work dirs — **PARTIAL** without a single ops runbook.

---

## 16. Error Handling / Fail-Closed

| Area | Behavior |
|------|----------|
| Publishability | AND gates; UNKNOWN ≠ PASS (H4/P02) |
| Multilingual packaging | Fail-closed before ready (H4) |
| AMP_SKIP in PRODUCTION | Blocked |
| Auth demo fallback | Blocked in PRODUCTION |
| Missing FFmpeg at boot | Not fail-closed at process level |
| Provider unavailable | Runtime errors / circuit (H3) — not boot-block |

---

## 17. Graceful Shutdown

| Mechanism | Evidence |
|-----------|----------|
| FastAPI `on_event("shutdown")` | `scheduler.stop()` |
| `SchedulerService.stop` | `shutdown(wait=False)` |
| SIGTERM/SIGINT handlers | Not app-specific beyond uvicorn |
| In-flight generate / FFmpeg child drain | **Not evidenced** |
| Lock release | OS/handle close (H1 note) |

**Classification:** PARTIAL.

---

## 18. Crash / Restart

Cross-check H4/BUILD-03: checkpoint/idempotency **SAFE_TO_RESUME** for completed fingerprints; stale locks reclaimable per H1; partial artifacts fail publishability.  
Live mid-provider crash: PARTIAL/UNKNOWN without paid run.  
**Classification:** PARTIAL / RECOVERABLE for local idempotent stages.

---

## 19. Backup / Restore

Persistent: SQLite DB, `.env`, channel sessions, job outputs, work manifests, checkpoints.  
Documented backup procedure: **ABSENT / NOT_DOCUMENTED**.  
**Classification:** PARTIAL (files exist; ops procedure missing).

---

## 20. Rollback

| Factor | Status |
|--------|--------|
| App version / build id | MISSING (no release version authority found) |
| Git commit in binary | Not packaged |
| Schema downgrade | UNSUPPORTED |
| Cache compatibility | Fingerprint-based; version-agnostic |

**Classification:** PARTIAL / UNKNOWN — replace source tree + keep/restore `data/` is operator improvisation.

---

## 21. Version / Build Identity

No canonical `APP_VERSION` / build / commit stamped into `/api/status` or package metadata found.  
Contract versions exist inside quality/intelligence modules (not product release version).  
**Classification:** ABSENT for release identity.

---

## 22. Release Reproducibility

| Factor | Result |
|--------|--------|
| Dep pins | Ranges → NON_REPRODUCIBLE bit-identical |
| Bundled FFmpeg tree | Same tree → equivalent media tools if shipped |
| Timestamps in export packages | Non-deterministic folder names (`package_export`) |
| External downloads at START | pip + playwright |

**Classification:** PARTIAL.

---

## 23. Package Export

**Authority:** `pipeline.package_export.export_upload_package` (sole; used from `generate_video`).  
Contents: `video.mp4`, title/description/tags, thumbnail, `meta.json`, README.  
`meta.upload_ready: True` is **package-folder semantics**, not publishability authority (publishability remains sole upload readiness for jobs).  
Localized remux packages: separate `LOCALIZED/` path (H4).  
Checksums: **not** in export.  
No second export engine required.

---

## 24. Release Package Content Safety

| Exclusion | Mechanism |
|-----------|-----------|
| `.env` | EXPLICIT gitignore; not in spec datas |
| `data/` | EXPLICIT gitignore |
| `output/`, logs, mp4 | EXPLICIT gitignore |
| Secrets in `.env.example` | SAFE placeholders |
| PyInstaller | PARTIAL — includes full `pipeline/` (code only); risk if local secrets copied manually into tree |
| Customer artifacts in dist | MISSING automated scrub beyond gitignore |

---

## 25. Operational Documentation

| Topic | Status |
|-------|--------|
| Install / start | PARTIAL — README + INSTALL_GUIDE_BN |
| Config / dry_run / local login | PARTIAL — guide + `.env.example` |
| FFmpeg | PARTIAL — PATH tip; bundled discovery underexplained for exe |
| Health/readiness | ABSENT |
| Backup/restore/rollback | ABSENT |
| Troubleshooting gates | ABSENT as ops runbook (marathon docs exist for engineers) |
| Release procedure | PARTIAL — pyinstaller steps only |

---

## 26. Deployment Model

| Model | Classification |
|-------|----------------|
| Windows local process (START.bat / uvicorn) | **SUPPORTED** (primary evidence) |
| PyInstaller Windows folder exe | **PARTIAL** (builds; media binaries not included) |
| Windows service | UNKNOWN / UNSUPPORTED (no service wrapper found) |
| Linux service / Docker / k8s | **UNSUPPORTED** (no evidence) |
| Hybrid web UI + background scheduler | **SUPPORTED** (in-process APScheduler) |
| Separate worker fleet | **UNSUPPORTED** as certified |

---

## 27. Scheduler / Worker Operations

- Started on app startup; stopped on shutdown (`wait=False`).  
- Jobs: heartbeat, timed upload, idle pregenerate, comments, captcha, etc.  
- **H4:** `_pregenerate_one` does **not** force `upload_status="ready_to_upload"`; trusts `generate_video`.  
- Duplicate workers: single in-process scheduler; multi-process same DB not certified (H1 historical note).  
- Publishability not bypassed by scheduler (source).

---

## 28. Resource Limits

| Limit | Status |
|-------|--------|
| Concurrent jobs | UNSPECIFIED (idle pregen one-at-a-time flag exists) |
| Scene/duration | Settings short/long max seconds |
| Retries | H3 bounded |
| Disk/memory/CPU | UNSPECIFIED |
| Worker count | Single process |

---

## 29. Security Release Gate

| Check | Result |
|-------|--------|
| Production auth bypass | Mitigated (H2) |
| AMP_SKIP in PRODUCTION | Blocked |
| Secret in release datas | `.env` excluded |
| Unsafe upload readiness | Scheduler fixed (H4); publishability AND |
| Cross-project contamination | work_dir isolation (H4 partial batch) |
| Unbounded retry | H3 bounds |
| DEF-H2-007 keys at rest | **OPEN limitation** |

---

## 30. Performance / Cost Release Gate

H3 retained: bounded retry, idempotent reuse, TTS/loc/render reuse patterns, usage ledger, COST_NOT_DETERMINABLE.  
This audit paid APIs = **0**.

---

## 31. Release Smoke Test Audit

| Existing | Role |
|----------|------|
| Phase-09/10 E2E | Offline/industrial workflow gates |
| H4 focused suite | Workflow + ready writers |
| H1–H3 suites | Reliability/security/cost |

**Dedicated release smoke** (boot → config → storage → FFmpeg probe → status → offline package export): **ABSENT** as a named release gate.  
**Need for H5:** recommend minimal offline smoke — **do not implement in pre-audit**.

---

## 32. Operational Failure Matrix

| Failure | Detection | Startup/Runtime | Fail-Closed | Recovery | Evidence |
|---------|-----------|-----------------|-------------|----------|----------|
| Missing config | Defaults / readiness missing | Starts; generate may fail | PARTIAL | Set `.env`/channel | Settings, readiness |
| Invalid config | Settings/parse | Varies | PARTIAL | Fix env | pydantic-settings |
| Missing FFmpeg | probe / render fail | Starts anyway | Pipeline yes; boot no | Install/bundle | compose probe |
| Missing ffprobe | probe / AV/RI | Starts anyway | Pipeline yes | Same | compose |
| Missing storage dir | mkdir | Auto-create | Soft | Permissions | config mkdir |
| Permission denied | OS errors | Runtime fail | Yes (ops) | Fix ACLs | expected |
| Corrupt state | validate/reuse fail | Job fail | Yes | Rebuild fingerprint | BUILD-03 |
| Provider unavailable | Runtime/circuit | Job fail | Yes | Retry policy H3 | H3 |
| Render failure | RI/ffmpeg | No ready | Yes | Repair/retry | H4/P08 |
| Verification failure | AV gate | No ready | Yes | — | P04/H4 |
| Publishability failure | evaluate_publishability | No ready | Yes | — | H4 |
| Process restart | — | Resume partial | PARTIAL | Checkpoint | BUILD-03/H4 |
| Stale lock | H1 reclaim | Continue | Safe reclaim | H1 | H1 report |
| Disk exhaustion | UNSPECIFIED | UNKNOWN | UNKNOWN | Ops | no handler found |

---

## 33. Release Readiness Matrix

| Area | Status | Evidence | Risk | Required Action |
|------|--------|----------|------|-----------------|
| Source package | PASS | Tree + START.bat | Low | Keep primary path |
| Dependencies | PARTIAL | Unpinned reqs | Drift | Pin/lock in H5 |
| Runtime | PASS (Win) | Host 3.12 | Medium | Document 3.11+ |
| Configuration | PARTIAL | Settings + example | Medium | Boot checklist |
| Secrets | PARTIAL | H2 + DEF-H2-007 | Medium | At-rest plan later |
| FFmpeg (source) | PASS | Probe bundled | Low | Document ship tree |
| FFmpeg (exe) | FAIL/PARTIAL | Spec omits bins | High for exe | Bundle or sidecar |
| ffprobe | Same as FFmpeg | — | — | — |
| Storage | PASS | init_db/mkdir | Low | — |
| Database | PARTIAL | Ad-hoc ALTER | Medium | Document/version |
| Filesystem | PASS | Paths/gitignore | Low | — |
| Startup | PARTIAL | No media boot gate | Medium | Optional probe |
| Health | PARTIAL | /api/status only | Medium | Media readiness field |
| Shutdown | PARTIAL | wait=False | Medium | Document |
| Crash recovery | PARTIAL | BUILD-03 | Medium | Ops note |
| Backup | NOT_DOCUMENTED | Files exist | Medium | Document copy of data+env |
| Rollback | PARTIAL | No version | Medium | Stamp version |
| Versioning | ABSENT | — | Medium | Add identity |
| Package export | PASS | package_export | Low | — |
| Release artifact | PARTIAL | Installer incomplete | High for exe | H5 packaging |
| Documentation | PARTIAL | BN guide | Medium | Expand |
| Scheduler | PASS | H4 fix | Low | — |
| Workers | PARTIAL | In-process only | Low | — |
| Security | PASS-WITH-LIMIT | H2 | DEF-H2-007 | — |
| Cost/performance | PASS-WITH-LIMIT | H3 | Deferred skips | — |

---

## 34. Findings by Severity

### P0
None.

### P1
None (for primary Windows source+venv+bundled FFmpeg model).

### P2

| ID | Area | Location | Behavior | Trigger | Reachability | Evidence | Protection | Impact | Minimal future action |
|----|------|----------|----------|---------|--------------|----------|------------|--------|----------------------|
| DEF-H5-001 | FFmpeg packaging | `installer/automoviepro.spec` | Exe dist has no FFmpeg/ffprobe | Build exe-only | Production if shipping installer | Spec `binaries=[]`, no ffmpeg datas; INSTALL guide PATH tip | Source tree bundled works | Media fail on clean exe install | Bundle binaries or mandatory sidecar + smoke |
| DEF-H5-002 | Health/readiness | `app/main.py` `/api/status` | ok without media tools | Missing FFmpeg | Ops false “healthy” | Source; probe independent | Pipeline fail-closed | Ops misread readiness | Add media capability to status/smoke |
| DEF-H5-003 | Dependencies | `requirements.txt` | Unpinned; no lock; pyinstaller mixed | Fresh pip | All installs | File inspect | None | Drift/break | Pin + lock; split dev deps |
| DEF-H5-004 | Migrations | `app/db.py` | Ad-hoc ALTER only | Schema evolve | Upgrades | Source | IF NOT EXISTS | Upgrade ambiguity | Document schema rev or light version |
| DEF-H5-005 | Version identity | app package | No release version in status | Support/rollback | Ops | Grep | — | Cannot identify build | Expose version/commit |
| DEF-H5-006 | Shutdown | `scheduler_service.stop` | `wait=False` | Process stop | Production | Source | uvicorn stop | In-flight cut | Document; optional wait |
| DEF-H5-007 | Backup/rollback | docs | Not documented | Disaster | Ops | Doc audit | gitignore separates data | Data loss risk | Write backup/restore note |
| DEF-H2-007 | Secrets | SQLite channels | Keys plaintext at rest | DB copy | Production | H2 | API mask | Disclosure if DB stolen | Encrypt/KMS later |

### P3

| ID | Area | Notes |
|----|------|-------|
| DEF-H5-008 | Docs | README minimal; no health/backup runbook |
| DEF-H5-009 | Defaults | Settings `api_base_url` placeholder `yourdomain.com` (login allowlist safe) |
| DEF-H5-010 | Resources | Disk/CPU/concurrency UNSPECIFIED |
| DEF-H5-011 | Export | No checksums in upload package |
| DEF-H5-012 | Platform | No Linux/macOS/Docker support claim possible |

**Carry-forward:** DEF-H3-008/009/010; DEF-H4-003/004/005; DEF-AMP004-001.

**Counts:** P0: 0 · P1: 0 · P2: 8 (incl. DEF-H2-007) · P3: 5  

---

## 35. Authority Duplication Audit

No new configuration, redaction, deployment, storage, migration, health, packaging, export, scheduler, publishability, FFmpeg, or idempotency engines introduced or required by this pre-audit.  
Use existing: Settings, api_keys redaction, compose FFmpeg discovery, package_export, SchedulerService, publishability, BUILD-03, H1 locks.

---

## 36. Known Limitations

- Primary certified deploy = Windows source/venv + bundled FFmpeg tree — not cross-platform SaaS containers.  
- PyInstaller release incomplete for media.  
- No lockfile / unpinned deps.  
- No product version stamp.  
- Ad-hoc SQLite migrations.  
- `/api/status` ≠ media readiness.  
- Shutdown PARTIAL; backup/rollback undocumented.  
- DEF-H2-007 plaintext channel keys.  
- H3/H4 deferred semantic/scale limitations remain.

---

## 37. Required Minimal Actions (H5 implementation — future only)

1. Define **release bill of materials**: source vs exe; require FFmpeg sidecars or bundle into installer.  
2. Add **offline release smoke**: boot → Settings → DB init → `probe_media_tool_capability` → fail clearly if media tools absent (status field).  
3. Pin/lock dependencies; split packaging deps from runtime.  
4. Expose **version/build identity** on `/api/status`.  
5. Document backup (`data/`, `.env`, sessions) and rollback.  
6. Do **not** create second engines; do **not** weaken H2/H3/H4 gates.  
7. Leave DEF-H2-007 as known limitation unless explicitly in H5 scope with existing crypto patterns.

---

## 38. H5 Scope Decision

```
H5_PRE_AUDIT_GO_WITH_LIMITATIONS
```

**Rationale:** No P0/P1 against the evidenced Windows source+bundled-FFmpeg operational model; pipeline upload readiness remains fail-closed; bounded packaging/ops/docs/dependency limitations must be addressed in H5 implementation without claiming Docker/Linux readiness.

---

## 39. Exact Checkpoint

```
AMP004-H5-PRE-AUDIT-PASS
```

**STOP.** Do not implement H5, modify source/tests, install packages, call paid APIs, start H6, or start Phase-11.
