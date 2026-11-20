# CHANGELOG: System Hardening & Security Stabilization

This changelog records all surgical fixes, security remediations, and quality gate verifications applied under the **MASTER RULES — Phase 1A Hardening Directives**.

---

## [Phase 1A] - 2026-11-19

### 1. Root Cause Analysis: Fail-Closed Injection Failures (Scripts `test_amp004_*.py`)
- **Finding:** 63 test nodes in `scripts/test_amp004_*.py` reported failure during baseline freeze.
- **Root Cause Verified:** Single shared root cause `ServerTicketError: RENDER_LOCKED` originating in `pipeline/compose.py` (`assert_generation_ticket_valid()`). Offline standalone fixture generators invoke `make_color_clip()` without mocking signed server cryptographic render tickets.
- **Quality Gate Integrity:** Evaluated standalone and verified **100% intact**. Downstream quality evaluation gates (`evaluate_publishability`, `run_publishability_gate`, `H4PublishabilityInvariantTests`) **pass 100%** and strictly reject invalid render outputs. System fails closed, never open.
- **Status:** Cataloged in `tests/baseline_known_failures.json` under `scripts_amp004_analysis` (Class: `TEST BUG / MISSING FIXTURE TICKET`, Owner Phase: Phase 4).

---

### 2. S-03 Security & Authentication Hardening
- **Local App Token Architecture:**
  - Implemented dynamic per-session cryptographic token generator in `app/security.py` using `secrets.token_hex(32)`.
  - Persisted to `data/.app_token` with restricted owner-only permissions.
  - Subprocess handoff: Environment variable `AUTO_MOVIE_APP_TOKEN` automatically passed to detached companion widget subprocess in `app/widget_service.py`.
- **CORS & Host Header Hardening:**
  - Eliminated wildcard `allow_origins=["*"]` with credentials.
  - Constrained CORS via regex strictly to local loopback and authorized LAN subnets (`127.0.0.1`, `localhost`, `192.168.*`, `10.*`).
  - Added strict `Host` header check rejecting foreign hosts (DNS rebinding prevention) with HTTP 400.
  - Added `Origin` and `Referer` validation rejecting foreign websites with HTTP 403.
- **Media & Binary Cookie Authentication (Owner Decision 2a):**
  - Configured `amp_session_token` cookie with `HttpOnly` and `SameSite=Strict` attributes issued on `GET /`.
  - Enables native HTML5 tags (`<img>`, `<video>`, `<audio>`, `<a download>`, `iframe`, `/output/...` previews and thumbnails) to render securely without URL query signing expiration races.
  - Completely blocks cross-site resource embedding and CSRF from external websites.
- **Frontend & Widget Token Wiring:**
  - Updated `AutoMoviePro-Software/ui/static/js/app.js`: Central `api()` wrapper retrieves token via session-authenticated `/api/auth/token` on boot and attaches `X-App-Token` header to all outbound API calls.
  - Updated `AutoMoviePro-Software/automovie_desktop_widget.py`: Telemetry worker and scheduler toggle actions attach `X-App-Token` via `_get_auth_headers()`.
- **Google AI Pro Paid Slots Server-Proof (Owner Decision 3):**
  - **Database Migration:** Added `google_slot_claimed` (INT DEFAULT 0) and `google_slot_claimed_at` (DATETIME NULL) to `AutoMoviePro-Website/includes/migrate.php`.
  - **Backend Endpoint:** Created `AutoMoviePro-Website/api/claim_google_slot.php` requiring license Bearer token. Atomically updates `google_slot_claimed = 1 WHERE google_slot_claimed = 0`. Duplicate claims rejected with HTTP 409 Conflict.
  - **Desktop Integration:** Refactored `/api/subscription/approve-google-paid` in `AutoMoviePro-Software/app/main.py`. Calls `LicenseClient.claim_google_slot(order_id)`.
  - **Fail-Closed Guarantee:** If the website backend is unreachable or returns a network error, slot unlock is **strictly aborted**, returning HTTP 503 and clear Bengali advisory `"সার্ভারের সাথে সংযোগ স্থাপন করা যায়নি। ইন্টারনেট কানেকশন চেক করুন।"`. Never fails open.
- **Security Verification Suite:**
  - Created `AutoMoviePro-Software/tests/test_s03_security_and_auth.py` (13 test cases, 100% passing).
  - Created `AutoMoviePro-Website/tests/test_claim_google_slot.php` (7 test cases, 100% passing).
  - Re-verified Phase 0 reproduction of S-03: Unauthenticated injection is 100% blocked with HTTP 401.

---

### 3. Secret Hygiene & Release Packaging Hardening
- **Script Sanitization:**
  - Sanitized `AutoMoviePro-Website/scripts/_upload_helper.py` and `deploy_whatsapp_fix.py`: Removed hardcoded Hostinger API tokens. Updated to read `HOSTINGER_AUTH_KEY`, `HOSTINGER_REST_KEY`, `HOSTINGER_BASE_URL` from environment.
  - Enabled strict TLS certificate verification (`ssl.create_default_context()`).
- **Packaging Hardening (Owner Decision on Packaging):**
  - Updated `package_release.py`: Excluded `local.db`, `*.sqlite`, `*.sqlite3`, `.env`, `*.log`, `__pycache__`, `tests`, `.git`.
  - Added `verify_package_cleanliness(INSTALLER_DIR)` post-assembly assertion that scans the staged release directory and raises `RuntimeError` if any forbidden debug, secret, database, or test artifact is found.
  - Verified package assembly: Produces clean, turnkey `AutoMoviePro_v2.0_Setup.zip`.

---

### 4. Real Desktop App Launch Verification
- **Automated End-to-End Suite:**
  - Created `scripts/verify_real_desktop_app.py`.
  - Spawned real backend server process on `127.0.0.1:8787`.
  - Tested root UI rendering, cookie issuance, auth token retrieval, and unauthenticated attack blocking.
  - Exercised core desktop endpoints: `/api/dashboard`, `/api/channels`, `/api/system/holistic-status`, `/api/widget/telemetry`, `/api/widget/action`.
  - Launched native WebView2/Edge instance via Playwright: Loaded desktop UI cleanly with zero console crash, verified Bengali typography rendering, and captured proof screenshot at `reports/screenshots/app_desktop_live_verified.png`.
