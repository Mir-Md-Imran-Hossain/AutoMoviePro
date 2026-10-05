# H5 Operations — Backup / Restore / Rollback

**Supported deployment:** Windows local process (`START.bat` → venv → FastAPI + APScheduler) with project-bundled FFmpeg/ffprobe.

**Unsupported:** Docker / Linux service — `UNSUPPORTED / NOT CERTIFIED`.  
**PyInstaller:** `PARTIAL / NOT CERTIFIED` until a full frozen media smoke is green (spec now includes binaries).

---

## Release identity

Canonical module: `app/release_identity.py`  
Endpoints: `/api/health`, `/api/status` (includes `release`), `/api/media-capability`, `/api/operational-readiness`  
Manifest: `release/manifest.json` via `python -m scripts.generate_release_manifest` or `app.ops_release.write_release_manifest`.

---

## What to back up

| Include | Path |
|---------|------|
| Persistent DB / meta | `data/` |
| Optional (operator choice) | `.env` — **not** in default automated backup |

## What NOT to back up by default

- `.env` secrets (unless operator explicitly opts in)
- `venv/`
- `output/` render trees
- `dist/` / `build/`
- temporary work folders under job outputs
- customer uploaded media caches unless required for recovery

Default backup API: `app.ops_backup.create_app_backup(include_env=False)` → `backups/amp_backup_*.zip`

---

## Restore

1. Stop the app (`Ctrl+C` / close console).  
2. Validate archive: `validate_backup_archive`.  
3. Restore into `data/` (or a staging dir then swap).  
4. Start `START.bat`.  
5. Check `/api/health` and `/api/operational-readiness`.

---

## Rollback

1. Keep previous backup zip before installing a new release tree.  
2. On failure: restore `data/` from backup; reinstall previous source tree / previous `requirements.txt` pins.  
3. There is **no** automatic binary rollback framework — operator procedure only.  
4. Schema: ad-hoc SQLite `ALTER` — prefer restore from backup over downgrade scripts.

---

## Health vs media

| Endpoint | Meaning |
|----------|---------|
| `/api/health` | Process alive |
| `/api/status` | Login + channel API readiness + release id — **not** media-ready |
| `/api/media-capability` | FFmpeg/ffprobe discovery + execution |
| `/api/operational-readiness` | Media + data prerequisites (not publishability) |

Publishability remains the sole authority for upload readiness of generated artifacts.
