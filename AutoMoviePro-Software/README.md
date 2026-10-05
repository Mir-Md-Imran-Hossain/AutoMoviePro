# AutoMovie Pro Software (Windows Desktop)

Niche-based automatic video generation + scheduled YouTube/Facebook upload.

## Quick start
1. Copy `.env.example` → `.env` and set `API_BASE_URL`
2. Run `START.bat`
3. Login with credentials from the website after payment approval

See [INSTALL_GUIDE_BN.md](INSTALL_GUIDE_BN.md) for full Bengali guide.  
Ops (backup/health/media): [docs/marathon/production_hardening/H5_OPERATIONS.md](docs/marathon/production_hardening/H5_OPERATIONS.md)

**Supported:** Windows local process + venv + bundled FFmpeg.  
**PyInstaller:** PARTIAL / NOT CERTIFIED. **Docker/Linux:** UNSUPPORTED.

## Modules
- `app/` — FastAPI local UI + license client + scheduler
- `pipeline/` — script (Google AI) → clips (Agnes/Pexels) → FFmpeg compose
- `publishers/` — YouTube/Facebook upload (dry-run by default)
- `hidden_engage/` — promo follow/subscribe + daily variable watch
