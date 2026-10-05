# H5 Implementation Discovery (Step 0 — read-only)

**Date:** 2026-09-03  
**Baseline:** `AMP004-H5-PRE-AUDIT-PASS` / `GO_WITH_LIMITATIONS`  
**Mode:** Discovery only — no source changes in this step.

---

## Canonical authorities (discovered)

| Concern | Authority | Location | Status |
|---------|-----------|----------|--------|
| Configuration | `Settings` + helpers | `app/config.py` | EXISTS — extend |
| Secret redaction | `redact_mapping` / mask | `pipeline/api_keys.py` | EXISTS — reuse |
| FFmpeg discovery | `ffmpeg_bin`, `_bundled_bin` | `pipeline/compose.py` | EXISTS — preserve |
| ffprobe discovery | `ffprobe_bin` | `pipeline/compose.py` | EXISTS — preserve |
| Media capability probe | `probe_media_tool_capability` | `pipeline/compose.py` | EXISTS — extend versions only if needed |
| App health / status | `/api/status` | `app/main.py` | EXISTS — process + API readiness; **not** media |
| Channel API readiness | `evaluate_readiness` | `pipeline/channel_api_slots.py` | EXISTS — leave |
| Package export | `export_upload_package` | `pipeline/package_export.py` | EXISTS — optional identity attachment |
| Startup | `_startup` / `main()` | `app/main.py` | EXISTS — extend minimally |
| Shutdown | `_shutdown` → `scheduler.stop` | `app/main.py`, `scheduler_service.py` | EXISTS — PARTIAL (`wait=False`) |
| Scheduler | `SchedulerService` | `app/scheduler_service.py` | EXISTS — protect (H4 ready fix) |
| Storage / DB | `init_db` | `app/db.py` | EXISTS — no destructive migrate |
| Logging | stdlib / uvicorn | various | EXISTS |
| Release / build metadata | — | — | **ABSENT** |
| Backup / restore | — | — | **ABSENT** |
| Release manifest | — | — | **ABSENT** |
| Dependency lock | `requirements.txt` ranges only | root | **PARTIAL** |
| PyInstaller | `installer/automoviepro.spec` | installer | EXISTS — FFmpeg omitted |
| Launcher | `START.bat` | root | EXISTS |

---

## Existing behavior (summary)

1. **START.bat** creates venv, installs requirements, runs `python -m app.main`.  
2. **Startup** initializes SQLite, seeds channel from env, starts APScheduler.  
3. **`/api/status`** returns login + channel API readiness + `dry_run_publish` — does not probe FFmpeg.  
4. **Media tools** discovered project-relatively; Phase-10 proven bundled 8.1.1.  
5. **Publishability** remains sole upload readiness (out of H5 scope to change).  
6. **DEF-H2-007** channel keys plaintext in SQLite — outside encrypt-at-rest; carry forward.

---

## H5 gaps → minimal extension points

| Gap | Extension point | Avoid |
|-----|-----------------|-------|
| No release identity | NEW `app/release_identity.py` (single) + wire into config diagnostics / status / manifest | Second version in multiple files |
| Unpinned deps | Pin `requirements.txt`; split `requirements-dev.txt` | New package manager |
| PyInstaller omits FFmpeg | Extend `.spec` datas + frozen-aware root in `compose._project_root` | Second FFmpeg manager |
| Status ≠ media | NEW `/api/media-capability` + `/api/health`; enrich status with `release` only | Overloading status as media-ready |
| Config validation | Extend `app/config.py` (`validate_production_operational` / diagnostics) | Second Settings |
| Backup/restore | NEW `app/ops_backup.py` + docs | Auto-rollback framework |
| Manifest | NEW `release/` generator using release_identity | Duplicate export engine |
| Smoke tests | NEW `scripts/test_amp004_h5_release.py` | Replacing AMP-004 suites |

---

## Duplicate-authority risks

- Do not add alternate `ffmpeg_bin` / probe.  
- Do not add second scheduler or publishability.  
- Do not invent Docker/Linux as supported.  
- Do not create parallel version constants in package_export and main independently — import one module.

---

## Files intended to change / add

**Modify:** `pipeline/compose.py` (frozen root only), `app/config.py`, `app/main.py`, `installer/automoviepro.spec`, `requirements.txt`, `START.bat` (optional pin note), `package_export.py` (optional safe identity in meta), `.env.example` (ops notes), `INSTALL_GUIDE_BN.md` / README ops, `DEFERRED_ISSUES.md`, `AMP004_STATE.json`, `AUDIT_LOG.md`

**Add:** `app/release_identity.py`, `app/ops_backup.py`, `app/ops_release.py` (manifest/validate), `requirements-dev.txt`, `release/README.md`, `docs/.../H5_IMPLEMENTATION_DISCOVERY.md` (this), `docs/.../H5_IMPLEMENTATION_REPORT.md`, `docs/.../H5_OPERATIONS.md`, `scripts/test_amp004_h5_release.py`, `scripts/generate_release_manifest.py`

---

## Files explicitly protected

- `pipeline/quality/publishability.py`  
- Idempotency / ContinuityTracker / BUILD-04F / render_bridge / ffmpeg_exec core semantics  
- H1 `fs_lock.py` logic (except if frozen path needs normalize — prefer compose root only)  
- H2 auth fail-closed paths (extend, do not weaken)  
- Scheduler ready_to_upload H4 fix  
- Phase E2E runners (no soft-handoff weakening)

---

## Dependency reproducibility target

`DEPENDENCY_REPRODUCIBILITY = PARTIAL` → improve to **PARTIAL→near FULL for direct deps** via pinned `requirements.txt` + separate `requirements-dev.txt`. Full transitive lockfile optional if pip-tools not already present (ABSENT) — do not introduce poetry/uv solely for H5.
