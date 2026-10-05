# CUSTOMER WINDOWS PRODUCT COMPLETION AUDIT

**Date:** 2026-09-03  
**Mode:** READ-ONLY (no source/test/config/state modifications; no installs; no paid APIs)  
**PDF source:** workspace root `AutoMovie Pro ফুল আপডেট প্ল্যান.pdf` (21 pages; text extraction OCR/garbled Bengali — requirements reconstructed from readable fragments + structure; noted where ambiguous)  
**Codebase:** `AutoMoviePro-Software/`  
**Package authority:** root `README.md`, `PACKAGE_INFO.json`  
**AMP-004 state:** H1–H5 PASS-WITH-LIMITATION / Phase-02→10 PASS (from existing reports; state file inspected read-only)

**Final verdict:** `CUSTOMER-WINDOWS-AUDIT-COMPLETE`

**CUSTOMER PRODUCTION TEST READY:** **NO**

---

## 1. Executive Summary

AutoMovie Pro’s **Windows customer application** is a **local FastAPI + static HTML/JS desktop UI** (`START.bat` → uvicorn → `ui/index.html`). Behind it sits a **strong industrial generation engine** (AMP-004 Phase-02→10 + BUILD-03/04 + H1–H5) with fail-closed publishability, idempotency, continuity, artifact/audio/localization/render gates, and release identity.

That engine is **not** the same as a completed **customer product**.

| Layer | Maturity (qualitative) |
|-------|------------------------|
| Backend video pipeline / gates | **GREEN / YELLOW** (engine certified with known limitations) |
| Windows packaging / ops | **YELLOW** (H5 source path supported; PyInstaller PARTIAL) |
| Customer UI / journey | **ORANGE / RED** for many PDF requirements |
| Publishing / browser automation | **ORANGE** (Playwright upload exists) + **NEEDS_REDESIGN** for PDF anti-bot / captcha-solve / auto-engagement goals |
| Website / payment / mobile (PDF later sections) | **OUT OF SCOPE** for Windows-first gate (existing website folder separate) |

**Largest product gap:** customers cannot operate a guided, visible, recoverable path from login → topic choice → script approval → quality diagnosis → preview → publish → URL history without developer knowledge. Generation is largely **one-click fire-and-forget** into a live panel + job list, while quality/publishability remain engine-internal.

---

## 2. Audit Scope

**In scope:** Windows customer software requirements from the PDF’s **PC সফটওয়্যার** sections + actual `AutoMoviePro-Software` surface.

**Out of scope for implementation (this audit only observes):** website landing/payment/admin (PDF pages ~12–21), mobile monitoring/payment apps, marketing WhatsApp systems — flagged as **website/mobile later**, not Windows V1 blockers unless Windows already depends on them.

**Not executed:** live YouTube/Facebook upload, paid providers, package rebuilds, migrations.

---

## 3. Authority Map

### 3.1 Business / product documents

| Document | Role | Notes |
|----------|------|-------|
| Root `README.md` | Package deploy narrative | Highest **package** authority for Website + Software split |
| `PACKAGE_INFO.json` | Package metadata | version `1.0.0-final` |
| PDF full update plan | Customer feature wishlist (PC + website + mobile) | Conflicts with safety/V1 doctrine in automation sections |
| `ARCHITECTURE_FREEZE.md` / AMP-004 contracts | **Technical quality authority** | Lifecycle PREVENT→PUBLISH; UNKNOWN≠PASS |
| H1–H5 reports | Hardening / release ops | Operational constraints |
| `Nish.Md` | Niche prompt catalog | Content prompts, not product UX |

**Conflict (reported, not resolved):** PDF demands heavy “local agent train-up”, human-like anti-bot browsing, captcha auto-solve, and automatic comment/message sending. AMP-004 industrial doctrine forbids pretending heuristic verification is provider vision and forbids unsafe bypasses. Engagement/anti-detection goals are **NEEDS_REDESIGN** toward official APIs + human-in-the-loop.

### 3.2 Technical authorities (canonical)

| Concern | Authority | Path | Production use |
|---------|-----------|------|----------------|
| Idempotency | BUILD-03 | `pipeline/idempotency/executor.py` | YES |
| SceneIntent | SceneIntent | `domain/scene_intent.py` + `scene_runtime` | YES |
| Continuity | ContinuityTracker | `pipeline/visual_semantic/continuity.py` | YES |
| Creative quality | BUILD-04F | `pipeline/quality/*` | YES |
| Multimodal | multimodal_consistency | `pipeline/multimodal_consistency/*` | YES |
| Artifact Verification | artifact_verification | `pipeline/artifact_verification/*` | YES |
| Audio | AudioPlan / audio_design | `pipeline/audio_design/*` | YES |
| Localization | LocalizationContract | `pipeline/localization*` | YES |
| Render / FFmpeg | compose + ffmpeg_exec + render_bridge | `pipeline/compose.py`, `ffmpeg_exec`, `idempotency/render_bridge` | YES |
| Rendering Integrity | rendering_integrity | `pipeline/rendering_integrity/*` | YES |
| Publishability | evaluate_publishability | `pipeline/quality/publishability.py` | YES (sole final readiness) |
| Topic/research | BUILD-04G / intelligence | `pipeline/intelligence/*` | YES (engine) |
| Config | Settings | `app/config.py` | YES |
| Release identity | release_identity | `app/release_identity.py` | YES (H5) |
| Backup | ops_backup | `app/ops_backup.py` | YES (ops; limited UI) |
| Scheduler | SchedulerService | `app/scheduler_service.py` | YES |
| Entry | START.bat / `app.main` | FastAPI | YES |
| Package export | export_upload_package | `pipeline/package_export.py` | YES |
| Upload | upload_service + Playwright uploaders | `publishers/*` | YES (browser automation primary) |
| Engagement | hidden_engage | `hidden_engage/*` | YES (risky PDF overlap) |

**Legacy / adapter (not removed):** `prompt_engineering` dual; TTS legacy fallback; `scene_builder` string graphs (DEF-AMP004-008).

---

## 4. PDF Customer Requirements (Windows PC Software)

Reconstructed from PDF pages 1–12 (PC software). Website/mobile pages 12–21 listed as **non-Windows-first**.

### 4.1 Authentication & account

| ID | Requirement |
|----|-------------|
| W-AUTH-01 | Secure login |
| W-AUTH-02 | Persistent login (no repeated login) |
| W-AUTH-03 | Admin restriction immediately blocks login |
| W-AUTH-04 | Same account cannot use multiple PCs |
| W-AUTH-05 | Password change via email OTP |
| W-AUTH-06 | Integrate mature open-source SaaS login (PDF suggestion) |
| W-AUTH-07 | Terms acceptance on first login + auto-features disclaimer |

### 4.2 Onboarding / channel / language

| ID | Requirement |
|----|-------------|
| W-ONB-01 | Easy post-registration basic setup |
| W-ONB-02 | User name + mobile |
| W-ONB-03 | Niche dropdown |
| W-ONB-04 | YouTube channel name + Facebook page name |
| W-ONB-05 | English primary + secondary language selection |
| W-ONB-06 | Language entitlement packages (2999 / 999 / 4999 pricing) |
| W-ONB-07 | Per-language YT/FB connect + browser cookie setup buttons |
| W-ONB-08 | Per-language long/short upload schedules |
| W-ONB-09 | Per-language logo + intro upload |

### 4.3 API configuration

| ID | Requirement |
|----|-------------|
| W-API-01 | API setup as first-class post-open task |
| W-API-02 | APIs scaled to unlocked languages |
| W-API-03 | Grok = agent + topic research + script |
| W-API-04 | Google AI Studio = TTS + localization (+ Grok fallback agent) |
| W-API-05 | OpenRouter = fallback |
| W-API-06 | Agnes = video generation |
| W-API-07 | Pixel = stock image/video Agnes fallback |
| W-API-08 | Pollination = image/thumbnail generation |
| W-API-09 | Two Google AI Studio keys per language for routing |

### 4.4 Topic / script / generation

| ID | Requirement |
|----|-------------|
| W-TOP-01 | Niche-based latest SEO topic research |
| W-TOP-02 | Separate long vs short topics + storage |
| W-TOP-03 | Strong anti-duplicate topics |
| W-TOP-04 | ≥5 reserved backup topics; daily re-rank |
| W-TOP-05 | Script with hooks, ≤9s dialogue scenes |
| W-TOP-06 | Per-scene visual + audio + subtitle prompts; JSON folders |
| W-TOP-07 | Local agent monitors/regenerates bad scenes (PDF “train”) |
| W-VIS-01 | Agnes primary A/V clips; seed continuity |
| W-VIS-02 | Image-to-video fallback with effects |
| W-AUD-01 | Localization + Google TTS; skip EN TTS if Agnes already has EN audio |
| W-SUB-01 | Timed subtitles per language |
| W-REN-01 | Compose per language; short vs long aspect rules |
| W-FIN-01 | Final concat + intro after hook + logo burn |
| W-META-01 | Title/description/tags per language + Pollination thumbnail |
| W-Q-01 | Continuous agent QA across stages |

### 4.5 Publish / monitor / social

| ID | Requirement |
|----|-------------|
| W-PUB-01 | Timed upload to correct language page/channel |
| W-PUB-02 | FB reels vs video; YT age/settings; SEO fields |
| W-PUB-03 | Save video URL; visible in admin |
| W-PUB-04 | Video performance page (views/likes/comments) |
| W-REP-01 | Auto-reply comments + page messages (20–25 min), human-like |
| W-BRW-01 | Background human-like browsing 08:00–24:00 |
| W-BRW-02 | Admin favorite channels; gradual trust pattern |
| W-CAP-01 | Captcha: easy auto-solve; hard → mobile notify |
| W-UI-01 | Multilingual UI |
| W-HELP-01 | In-app help agent (+ store APIs via chat) |
| W-HELP-02 | Per-control “i” info |
| W-FBK-01 | Feedback/complaint with screenshot/video + ticket |
| W-REV-01 | Review/rating with periodic prompts |
| W-NOT-01 | Scrolling admin notification bar |

### 4.6 Explicitly later / non-Windows-first (PDF)

Website landing, registration, payment (bKash/Nagad/Binance), admin panel, WhatsApp marketing, mobile user/admin/payment apps — **DEFERRED** relative to Windows customer production-test gate (root README still couples website for license issuance).

### 4.7 V1 / safety conflicts with PDF

| PDF ask | Conflict |
|---------|----------|
| Strong “train local agent” for all stages | Conflicts with AMP-004 honesty (no fake PROVIDER_VERIFIED); risks unbounded regeneration cost |
| Anti-bot / human evasion browsing | Platform ToS / safety — **NEEDS_REDESIGN** |
| Captcha auto-solving | **NEEDS_REDESIGN** (no bypass implementation in this audit’s recommendations) |
| Fully automatic comment/message send | Prefer suggest + approve |

---

## 5. Current Windows Application Architecture

| Item | Evidence | Status |
|------|----------|--------|
| App type | Local web UI + Python backend | FastAPI serves `ui/` |
| Entry | `START.bat` → `python -m app.main` | SUPPORTED (H5) |
| UI | `ui/index.html` + `ui/static/js/app.js` | SPA-like panels |
| Tabs | home, live, channel, jobs, settings | Present |
| Login panel | `#loginView` | Present |
| Help FAB | `#chatFab` → `/api/agent-chat` | Present |
| i18n | `ui/static/js/i18n.js` | Present |
| Scheduler | APScheduler in-process | Present |
| Persistence | SQLite `app/db.py` `data/` | Present |
| Packaging | H5 source + PyInstaller PARTIAL | Documented |
| FFmpeg | Bundled discovery `compose.py` | AVAILABLE on certified host |

### UI surface inventory

| Path / component | Purpose | Status |
|------------------|---------|--------|
| Login view | Credentials + API base | PARTIAL (defaults show admin/admin123 in HTML — H2 blocks in PRODUCTION if misused) |
| Dashboard home | Stats + Generate Short/Long | PARTIAL |
| Live activity | Phase/API/events + stop | PARTIAL (good visibility for run; not quality gates) |
| Channel setup | Niche, langs, APIs, logo/intro, YT/FB login | PARTIAL |
| Language purchase | Request/sync/local-approve | PARTIAL (engine+UI; payment is website) |
| Jobs list | Title/type/upload_status | PARTIAL (no preview/URL deep UX) |
| Settings | Logout + “system optimization” (hidden engage) | PARTIAL / risky |
| Help chat | Agent help | PARTIAL |
| Topic picker UI | — | **ABSENT** |
| Script editor/approve | — | **ABSENT** |
| Quality/publishability UI | — | **ABSENT** |
| Preview player | — | **ABSENT** |
| Comment inbox/approve | — | **ABSENT** (backend reply job exists) |
| Performance analytics page | — | **ABSENT** in UI (API posts/stats exist) |

---

## 6. Customer Journey Audit

| Stage | Engine? | Customer UI? | Wired? | Persist? | Status UX? | Fail/retry? | Idempotent? | Tests? | Customer-operable? |
|-------|---------|--------------|--------|----------|------------|-------------|-------------|--------|--------------------|
| INSTALL | H5 docs | START.bat | Y | N/A | PARTIAL | PARTIAL | N/A | H5 | PARTIAL |
| START | main/startup | browser open | Y | session | health APIs | PARTIAL | N/A | H5 | Y |
| LOGIN | LicenseClient + local | login view | Y | session SQLite | errors | PARTIAL | N/A | H2 | PARTIAL |
| SESSION | store session | userBox | Y | Y | Y | PARTIAL | N/A | — | PARTIAL |
| ACCOUNT / ENTITLEMENT | website license + lang requests | lang buy UI | PARTIAL | Y | PARTIAL | PARTIAL | — | — | PARTIAL |
| ONBOARDING | channel form | channel tab | Y | Y | PARTIAL | PARTIAL | — | — | PARTIAL |
| LANGUAGE | lang entitlement | secondary + buy | PARTIAL | Y | PARTIAL | PARTIAL | H3 dedupe | P06 | PARTIAL |
| CHANNEL/PAGE | channel + session_vault | YT/FB login buttons | Y | browser profiles | session-health API | PARTIAL | — | — | PARTIAL |
| API CONFIG | api_keys + slots | dropdown keys | Y | channel JSON (**plaintext DEF-H2-007**) | readiness banner | PARTIAL | — | H2 | PARTIAL |
| TOPIC | intelligence/04G | **no UI** | auto in generate | PARTIAL | **no** | engine | BUILD-03 | BUILD-04G | **ENGINE ONLY** |
| RESEARCH | intelligence | **no UI** | auto | PARTIAL | **no** | engine | — | — | **ENGINE ONLY** |
| SCRIPT | script runtime | **no UI** | auto | work dir | **no** | repair engine | — | P07 | **ENGINE ONLY** |
| SCENE / VISUAL | SceneIntent + Agnes bridge | **no UI** | generate_video | artifacts | live phase only | gates/repair | BUILD-03 | P03–P04 | **ENGINE ONLY** |
| AUDIO/TTS | audio + tts_bridge | **no UI** | Y | Y | **no** | gate | H3 | P05 | **ENGINE ONLY** |
| SUBTITLE/LOC | localization | **no UI** | Y | LOCALIZED/ | **no** | H4 packaging | H3 | P06 | **ENGINE ONLY** |
| QUALITY | 04F + multimodal + AV | **no UI** | Y | gate JSON | **no** | fail-closed | — | P02–P10 | **ENGINE ONLY** |
| REPAIR | repair bridges | **no UI** | Y | attempts | **no** | bounded | — | phases | **ENGINE ONLY** |
| RENDER | render_bridge/ffmpeg | **no UI** | Y | final | live phase | RI gate | BUILD-03 | P08/P10 | **ENGINE ONLY** |
| PREVIEW | — | **ABSENT** | N | file exists | N | N | N | N | **NOT_IMPLEMENTED** |
| APPROVAL | — | **ABSENT** | N | N | N | N | N | N | **NOT_IMPLEMENTED** |
| UPLOAD | upload_service Playwright | schedule times only | Y | job status | job list | retry pending | day_key | — | PARTIAL |
| PUBLISH URL | uploader return | weak | PARTIAL | job fields | weak | PARTIAL | — | — | PARTIAL |
| HISTORY | jobs list | jobs tab | Y | Y | upload_status | N | — | — | PARTIAL |
| MONITORING | live panel + posts APIs | live tab; no perf page | PARTIAL | activity | PARTIAL | stop btn | — | — | PARTIAL |
| COMMENT/MSG | comment_reply_agent | **no inbox UI** | scheduler | PARTIAL | **no** | PARTIAL | — | — | **ENGINE ONLY / REDESIGN** |
| NEXT JOB | idle pregen + timed upload | times on channel | Y | jobs | weak | PARTIAL | H1 locks | H4 | PARTIAL |
| RECOVERY | BUILD-03/H1/H4 | **no customer recovery UX** | Y | checkpoints | weak | Y engine | Y | BUILD-03/H1 | **ENGINE ONLY** |

---

## 7. Core Video Pipeline Audit

Canonical path (engine — proven in Phase-09/10/H4):

`generate_video` → SceneIntent/Continuity → generation bridges → Artifact Verification → Audio/Localization/Creative/RI gates → BUILD-04F + publishability → (multilingual) localize packages → `ready_to_upload` → package export.

| Stage | Engine | Product UI | Notes |
|-------|--------|------------|-------|
| Research/topic | YES | NO | Auto inside pipeline |
| Script | YES | NO | No edit/approve |
| SceneIntent | YES | NO | Soft-handoff offline E2E only |
| Continuity | YES | NO | |
| Visual | YES | NO | Agnes/Pixel/Pollination adapters |
| Audio/TTS | YES | NO | Google/TTS bridges |
| Localization | YES | NO | H4 packaging before ready |
| Quality | YES | NO | UNKNOWN≠PASS in engine |
| Render/RI | YES | NO | Bundled FFmpeg |
| Publishability | YES | NO | Sole upload readiness |
| ready_to_upload | YES | job status string only | Scheduler does not force ready (H4) |

**Customer can run without developer?** Only as **opaque generate button** if APIs/channel ready — **not** as guided industrial workflow.

---

## 8. Provider Audit

| Provider | Intended (PDF) | Implementation evidence | Customer config UI | Health | Notes |
|----------|----------------|-------------------------|--------------------|--------|-------|
| Grok | Agent/topic/script | LLM routing / intelligence (provider names in slots) | Channel API dropdown | readiness slots | No paid calls this audit |
| Google AI Studio | TTS/localization | TTS + translate paths | Keys (multi) | PARTIAL | Per-lang dual keys **PARTIAL** |
| OpenRouter | Fallback | Key slots / llm_router | YES | PARTIAL | |
| Agnes | Video | `agnes_bridge` | YES | PARTIAL | |
| Pixel / Pexels | Stock fallback | api keys / stock paths | YES (naming varies) | PARTIAL | PDF “Pixel” vs code Pexels — verify mapping |
| Pollination | Image/thumb | media_assets / keys | YES | PARTIAL | |

**Paid API usage this audit:** 0.

---

## 9. Publishing Audit

| Platform | Mechanism | Auth | Upload | Metadata | URL persist | Customer UI | Classification |
|----------|-----------|------|--------|----------|-------------|-------------|----------------|
| YouTube | **Browser automation** (`youtube_uploader.py` Playwright Studio) | session_vault login | YES | title/desc/tags/thumb/not-for-kids | PARTIAL | Login button + schedule | PARTIAL / not Official API |
| Facebook | **Browser automation** (`facebook_uploader.py`) | session_vault | YES | PARTIAL | PARTIAL | Login button + schedule | PARTIAL / not Official API |
| Dry-run | `settings.dry_run_publish` default true | — | Simulated | — | dry_run_uploaded | Status shows dry-run | SAFE default |

**Official Data API publishing:** not evidenced as primary path.  
**Manual workflow:** not first-class UI.  
**Duplicate prevention:** day_key upload once; quality fail remains retryable.

---

## 10. Browser Automation Audit

| PDF feature | Current | Classification |
|-------------|---------|----------------|
| Cookie/session setup for YT/FB | `youtube-login` / `facebook-login` + session_vault | PARTIAL |
| Human-like upload | `human_browser.py` + uploaders | PARTIAL |
| Auto browse/like/comment/follow | `hidden_engage/*`, trust_browse, settings “system optimization” | **NEEDS_REDESIGN** (ToS/anti-bot) |
| Captcha soft stop / unlock | captcha APIs + alerts | PARTIAL human unlock; **auto-solve = NEEDS_REDESIGN** |
| Auto comment/message reply | `comment_reply_agent` on 20-min schedule | **NEEDS_REDESIGN** toward suggest+approve |

---

## 11. Comment / Message Audit

| Capability | Status |
|------------|--------|
| Retrieval | PARTIAL (agent/pass internals) |
| Language-aware reply | CLAIMED in PDF; evidence PARTIAL |
| AI suggestion vs auto-send | **Auto-send path exists** — product approval UI **ABSENT** |
| History / audit trail | PARTIAL logs |
| Customer inbox UI | **NOT_IMPLEMENTED** |

---

## 12. Scheduler / Recovery Audit

| Job | Interval | Role | Customer-safe? |
|-----|----------|------|----------------|
| heartbeat | 5m | License | PARTIAL |
| timed_upload | 1m | Upload pending ready jobs | PARTIAL |
| idle_pregenerate | 2m | Generate when queue empty | PARTIAL (can surprise users) |
| comment_reply | 20m | Auto replies | **REDESIGN** |
| captcha_watch | 30s | Captcha | PARTIAL |
| hidden_engage / trust_browse | scheduled | Engagement browsing | **REDESIGN** |

Locks/idempotency: H1 + BUILD-03.  
Customer pause/resume of automation: **weak** (stop live process only).  
Timezone: local machine clock.  
Per-language schedules: PDF asks per-lang; UI has single short/long times on channel — **PARTIAL**.

---

## 13. Security Audit

| Item | Status |
|------|--------|
| Production local login fail-closed | H2 PASS |
| AMP_SKIP blocked in PRODUCTION | H2 |
| dry_run default | true |
| Channel keys at rest | **DEF-H2-007 OPEN** |
| HTML login defaults admin/admin123 | UX smell; production path fail-closed |
| Secret redaction | H2/H5 diagnostics |
| Engagement / anti-bot features | Safety risk if enabled for customers |

---

## 14. Packaging Audit

| Item | Status |
|------|--------|
| Windows source+venv+bundled FFmpeg | **SUPPORTED** (H5) |
| PyInstaller | **PARTIAL_NOT_CERTIFIED** |
| Docker/Linux | **UNSUPPORTED** |
| Release identity 0.5.0 | Present |
| Dependency pins | PARTIAL |
| Backup/restore | ops module + docs; limited customer UI |
| Secrets in package | .env gitignored; must not ship |

---

## 15. Full Requirement Gap Matrix (master)

Legend: **E**=Engine, **P**=Product classification from §20.

| ID | Category | PDF req | Existing | Path / Authority | E | P | Priority | Remaining |
|----|----------|---------|----------|------------------|---|---|----------|-----------|
| W-AUTH-01 | Auth | Secure login | License + local login | `app/main.py` login | Y | PARTIAL | P0 | Harden UX; remove demo defaults in HTML |
| W-AUTH-02 | Auth | Persistent login | Session SQLite | `app/db.py` | Y | PARTIAL | P1 | Explicit remember/session TTL UX |
| W-AUTH-03 | Auth | Admin block | Website license status | LicenseClient | PARTIAL | PARTIAL | P0 | Prove live revoke→local block E2E |
| W-AUTH-04 | Auth | Multi-PC lock | Not evidenced | — | N | NOT_IMPLEMENTED | P1 | Device binding design |
| W-AUTH-05 | Auth | OTP password reset | Not in Windows UI | — | N | NOT_IMPLEMENTED | P1 | Or website-only flow documented |
| W-AUTH-06 | Auth | OSS SaaS login integrate | Not done | — | N | DEFERRED/REDESIGN | P2 | |
| W-AUTH-07 | Auth | T&C first run | Not evidenced in UI | — | N | NOT_IMPLEMENTED | P1 | Modal + store acceptance |
| W-ONB-01 | Onboard | Easy setup | Channel form | `ui/index.html` | Y | PARTIAL | P0 | Wizard UX |
| W-ONB-02 | Onboard | Name/mobile | Not first-class Windows fields | — | N | PARTIAL | P1 | Profile fields |
| W-ONB-03 | Onboard | Niche | Niche select locked | channel form | Y | COMPLETE | — | |
| W-ONB-04 | Onboard | YT/FB names | Fields + login | channel | Y | PARTIAL | P1 | Per-language destinations |
| W-ONB-05 | Onboard | Languages | EN + secondary | lang UI | Y | PARTIAL | P0 | Per-lang destination matrix |
| W-ONB-06 | Onboard | Paid lang packs | Request/sync UI | languages APIs | PARTIAL | PARTIAL | P1 | Depends website payment |
| W-ONB-07 | Onboard | Per-lang cookie buttons | Single channel login | session_vault | PARTIAL | PARTIAL | P0 | Multi destination UI |
| W-ONB-08 | Onboard | Per-lang schedules | One short/long time | channel fields | PARTIAL | PARTIAL | P1 | |
| W-ONB-09 | Onboard | Per-lang logo/intro | Single logo/intro | channel form | PARTIAL | PARTIAL | P1 | |
| W-API-01..09 | API | Provider map | Slots + keys UI | `channel_api_slots`, `api_keys` | Y | PARTIAL | P0 | Per-lang Google dual keys; Pixel naming |
| W-TOP-01..04 | Topic | Research/reserve/dedupe | intelligence/04G | `pipeline/intelligence` | Y | **PROD_ENGINE_ONLY** | P0 | Customer topic board |
| W-TOP-05..07 | Script | Hooks/JSON/agent | script + quality | pipeline | Y | **PROD_ENGINE_ONLY** | P0 | Script review UI; constrain “train” |
| W-VIS/AUD/SUB/REN/FIN | Media | Full pipeline | AMP-004 generate_video | `video_pipeline` | Y | **PROD_ENGINE_ONLY** | P0 | Progress by stage + artifacts browser |
| W-META-01 | Meta | SEO package | package_export + thumb | pipeline | Y | PARTIAL | P1 | Show/edit before upload |
| W-Q-01 | Quality | Agent QA | Gates fail-closed | publishability etc. | Y | **PROD_ENGINE_ONLY** | P0 | Surface verdicts to UI |
| W-PUB-01..04 | Publish | Timed upload+URL+stats | upload_service + posts APIs | publishers | Y | PARTIAL | P0 | Preview, confirm, URL history page |
| W-REP-01 | Social | Auto reply | comment_reply_agent | publishers | Y | **NEEDS_REDESIGN** | P1 | Suggest+approve inbox |
| W-BRW-01..02 | Social | Trust browse | hidden_engage | hidden_engage | Y | **NEEDS_REDESIGN** | P2 | Official API / manual only |
| W-CAP-01 | Social | Captcha solve | soft stop/unlock | captcha APIs | PARTIAL | **NEEDS_REDESIGN** | P1 | Human-only solve |
| W-UI-01 | UI | Multilingual UI | i18n.js | ui | Y | PARTIAL | P2 | Coverage completeness |
| W-HELP-01..02 | Help | Agent + i buttons | chat + help_content | ui/api | PARTIAL | PARTIAL | P2 | |
| W-FBK/REV/NOT | Ops | Feedback/review/bar | weak/absent | — | N | NOT_IMPLEMENTED | P2 | |
| Website/Mobile PDF | Non-Win | Landing/pay/admin/apps | `AutoMoviePro-Website` exists | separate | PARTIAL | **DEFERRED** | — | After Windows gate |

**Generate UX defect (evidence):** `app.js` `generate()` alerts `res.result?.title`, but `/api/generate` returns `{started, job_id}` for background work — product feedback incorrect (**PARTIAL / P0**).

---

## 16. Top 20 Largest Gaps

1. **No customer quality/publishability visibility** — blocks trust; engine-only; P0; show gate verdicts before upload.  
2. **No preview/approve step** — unsafe auto-upload path; P0.  
3. **No topic/script customer control** — opaque automation; P0.  
4. **Per-language destination/schedule/logo incomplete** — PDF core; P0.  
5. **Generate UX async mismatch** — false success messaging; P0.  
6. **Publishing is Playwright not Official API** — brittle; P0/P1; document + harden or API plan.  
7. **URL/history/performance UX thin** — P0.  
8. **Auto engagement / trust browse** — ToS risk; **NEEDS_REDESIGN**; P1.  
9. **Auto comment/message send without approval** — **NEEDS_REDESIGN**; P1.  
10. **Captcha auto-solve ambition** — **NEEDS_REDESIGN**; P1.  
11. **Multi-PC / OTP / T&C** — account security gaps; P1.  
12. **DEF-H2-007 keys at rest** — security; P1 (carry).  
13. **Idle pregenerate surprises** — ops; P1 pause controls.  
14. **PyInstaller not certified** — distribution; P1 for exe customers.  
15. **Long-form/batch not certified** — H4 limitation; P2 for scale.  
16. **VLM/ASR L3 incomplete** — quality depth; P2 (honest heuristic).  
17. **Per-lang dual Google keys** — PDF; P1.  
18. **Feedback/review/notification bar** — retention; P2.  
19. **Help agent “store all APIs via chat”** — security risk if over-powered; P2 redesign.  
20. **Website payment coupling for entitlements** — Windows alone cannot complete paid lang packs; P1 dependency.

---

## 17. Dependency Graph (evidence-based order)

Recommended customer completion stages (validate vs PDF + code):

```
C01 Windows Product Foundation (identity, health honesty, generate UX fix, live/job truthfulness)
  → C02 Auth / Account / Entitlement / T&C
  → C03 Onboarding Wizard
  → C04 Channel / Language / API / Sessions (per-lang destinations)
  → C05 Topic / Research / Script UX (extend intelligence — no new engine)
  → C06 Production UX (stage progress, artifacts, quality, repair status)
  → C07 Scheduler controls / recovery UX
  → C08 Publishing confirm + URL history (harden Playwright; plan Official API)
  → C09 Preview / Approval gate before upload
  → C10 Comments/Messages (suggest+approve; disable silent auto-send)
  → C11 Official/safe automation (replace anti-bot browse)
  → C12 Help / i-buttons / feedback
  → C13 Packaging certification (PyInstaller smoke)
  → C14 Real Customer Production Certification
```

Do **not** start website marketing/payment work as C01; license entitlement may remain website-backed but Windows must fail clearly when entitlement missing.

---

## 18. Duplicate Authority Findings

| Area | Canonical | Other | Class |
|------|-----------|-------|-------|
| Publishability | `quality/publishability.py` | package `upload_ready` meta | ADAPTER (folder semantics) |
| FFmpeg | `compose` discovery | none second | CANONICAL |
| Prompt | SceneIntent compiler | `prompt_engineering` | LEGACY dual |
| TTS | tts_bridge | legacy fallback | ADAPTER |
| Scheduler | SchedulerService | — | CANONICAL |
| Engagement | hidden_engage | PDF browse goals | DUPLICATE RISK vs safe product |
| Config | Settings | api_keys | SPLIT OK |
| Release | release_identity | PACKAGE_INFO 1.0.0-final | **VERSION CONFLICT** (package vs app 0.5.0) — report only |

---

## 18b. Error / Recovery Matrix (customer-relevant)

| Failure | Expected (product) | Current behavior (evidence) | Recovery | Customer visibility | Gap |
|---------|--------------------|-----------------------------|----------|---------------------|-----|
| Invalid API key | Clear block + fix guidance | Readiness / provider errors in logs/live | Re-enter keys | PARTIAL (banner/live) | P0 clearer UI |
| Expired API key | Same | Same as invalid (provider-dependent) | Re-auth | PARTIAL | P1 |
| Provider unavailable | Fail stage; retry policy | Circuit/retry in adapters (H3 shared circuit limitation) | Retry/fallback slots | Live events | P1 |
| Quota exhausted | Fail-closed; no false ready | Provider errors; no dedicated quota UX | Wait/rotate keys | LOW | P1 |
| Network interruption | Checkpoint resume | BUILD-03/H1 locks; job may fail | Restart/retry job | LOW | P0 recovery UX |
| Script failure | Block continue; repair option | Engine repair/fail | Regen | Live phase | P0 script UI |
| Visual generation failure | Bounded repair then block | Gates + repair bridges | Retry | Live | Engine OK / product thin |
| Audio failure | Audio gate fail-closed | audio quality gate | Repair TTS | Hidden | P0 |
| Localization failure | Not ready_to_upload | H4 fail-closed packaging | Fix lang/APIs | Hidden | P0 |
| Subtitle failure | Block publish | Localization/subtitle validation | Repair | Hidden | P0 |
| Render failure | RI fail; no upload | rendering_integrity | Re-render | Live phase | P0 |
| Artifact corruption | AV reject | artifact_verification | Regen | Hidden | P0 |
| Publish failure | Retryable status | upload_service pending/fail | Reschedule | Jobs list | PARTIAL |
| Duplicate job | Idempotent skip | BUILD-03 / day_key upload | N/A | LOW | OK engine |
| App crash mid-job | Resume or mark failed | Checkpoints/locks | Restart | Weak | P0 |
| Scheduler interruption | Resume on start | Scheduler starts with app | Auto | Weak | P1 |
| Partial artifact | Fail-closed | Gates | Clean/retry | Hidden | P0 |
| Missing FFmpeg | media_ready false | H5 media-capability | Install/bundle | API | P0 UI surface |
| Missing ffprobe | Same | compose media tools | Bundle | API | P0 |

## 18c. H1–H5 vs Customer V1

| Hardening | Status | Customer V1 impact |
|-----------|--------|--------------------|
| H1 reliability locks | PASS | Enables safe concurrent jobs; product still needs recovery UX |
| H2 security/config | PASS-WITH-LIMITATION | DEF-H2-007 keys-at-rest = P1 for customer |
| H3 performance/cost | PASS-WITH-LIMITATION | Shared circuit / cost = FUTURE SCALE unless multi-tenant |
| H4 real workflow | PASS-WITH-LIMITATION | Localize-before-ready is critical; soft-handoff offline only |
| H5 release ops | PASS-WITH-LIMITATION | Source path OK; PyInstaller PARTIAL = P1 for exe |
| Semantic L3 VLM/ASR | Incomplete | Honest UNKNOWN≠PASS; P2 depth |
| Long-form / batch scale | Not certified | FUTURE SCALE / P2 |
| Dual prompt legacy | Open | Internal; P2 cleanup |
| Critic skip / repair overlap | Limitations | Engine honesty; P2 |

## 19. Customer Production Gate

**CUSTOMER WINDOWS SOFTWARE — PRODUCTION TEST READY** requires ALL:

1. Clean install via START.bat on fresh Windows  
2. Login + entitlement proven  
3. T&C accepted  
4. Channel + language + API readiness  
5. Per-language destinations connected (or explicit EN-only scope)  
6. Customer-visible topic → script → generate progress  
7. Quality/publishability visible; UNKNOWN/BLOCKED cannot upload  
8. Preview + explicit approve  
9. Publish (dry-run then live) with URL saved  
10. Jobs history + restart recovery visible  
11. Scheduler controllable (pause pregen/engage)  
12. Auto social features off or human-approved only  
13. Logs without secrets  
14. Packaged runtime path documented; FFmpeg capability true  
15. No false-ready (`/api/status` ≠ media/publish ready — already partially fixed H5)

**Current:** fails multiple P0 items → **NO**.

---

## 20. Real Customer E2E Acceptance Scenario (definition only)

INSTALL → START → LOGIN → ACCEPT T&C → CREATE CHANNEL (niche, EN+lang) → ENTER APIs → CONNECT YT/FB SESSIONS → VIEW TOPIC CANDIDATES → APPROVE SCRIPT → GENERATE → WATCH STAGE GATES → OPEN PREVIEW → SEE PUBLISHABILITY → APPROVE UPLOAD → (DRY_RUN then LIVE) → CONFIRM URL IN HISTORY → RESTART APP → STATE INTACT → SCHEDULE NEXT → OBSERVE LIVE PANEL → (OPTIONAL) REVIEW COMMENT SUGGESTIONS → APPROVE REPLY  

Do **not** execute live publish in audit mode.

---

## 21. Final Implementation Roadmap

| Stage | Objective | Extends | New authority? | Exit criteria |
|-------|-----------|---------|----------------|---------------|
| C01 | Foundation UX truth (generate async, health, jobs) | main/ui/live_activity | NO | Generate UX matches API; no false alerts |
| C02 | Auth/T&C/entitlement clarity | login, LicenseClient | NO | Persistent session + revoke behavior tested |
| C03 | Onboarding wizard | channel form | NO | First-run checklist complete |
| C04 | Per-lang destinations/APIs/schedules | session_vault, channel | NO | Multi-lang map works or EN-only certified |
| C05 | Topic/script UX | intelligence, script_runtime | NO | Customer can select/approve |
| C06 | Production visibility | gates JSON → UI | NO | Quality blocking reasons shown |
| C07 | Scheduler/recovery controls | SchedulerService | NO | Pause flags; resume after crash documented |
| C08 | Publishing UX + URL | upload_service | NO | Confirm upload; URL in history |
| C09 | Preview/approval hard gate | jobs + filesystem | NO | No upload without approve |
| C10 | Comments suggest+approve | comment_reply_agent | NO | Auto-send disabled by default |
| C11 | Safe automation policy | hidden_engage | NO | Anti-bot features gated off / redesigned |
| C12 | Help/feedback | agent-chat, help_content | NO | i-buttons + ticket optional |
| C13 | Packaging cert | installer spec | NO | Frozen smoke or documented source-only |
| C14 | Customer cert | e2e scenario | NO | Gate §19 green |

---

## 22. Known Limitations

- PDF OCR imperfect — some Bangla tokens ambiguous; English provider names clear.  
- Website/mobile PDF sections not deep-audited beyond existence of `AutoMoviePro-Website/`.  
- No live publish verification this audit.  
- H1–H5 / Phase limitations remain (keys-at-rest, L3 VLM/ASR, PyInstaller PARTIAL, long-form/batch).  
- PACKAGE_INFO `1.0.0-final` vs app `0.5.0` identity mismatch.

---

## 23. Evidence Index

- PDF: workspace root update plan (21 pages)  
- UI: `ui/index.html`, `ui/static/js/app.js`  
- API: `app/main.py` routes  
- Pipeline: `pipeline/video_pipeline.py`, quality/*, compose.py  
- Publish: `publishers/upload_service.py`, `youtube_uploader.py`, `facebook_uploader.py`  
- Engage: `hidden_engage/*`  
- Scheduler: `app/scheduler_service.py`  
- Hardening: `docs/marathon/production_hardening/H1..H5_*.md`  
- AMP-004: `ARCHITECTURE_FREEZE.md`, Phase reports, `AMP004_STATE.json`  
- Package: root `README.md`, `PACKAGE_INFO.json`

---

## 24. Final Verdict

```
CUSTOMER-WINDOWS-AUDIT-COMPLETE
```

| Field | Value |
|-------|-------|
| CURRENT WINDOWS PRODUCT MATURITY | Engine **YELLOW/GREEN**; Customer product **ORANGE** |
| CUSTOMER PRODUCTION TEST READY | **NO** |
| P0 GAPS | Quality/preview/approve UX; topic/script UX; per-lang destinations; generate UX truth; publish URL/history; entitlement clarity |
| P1 GAPS | Multi-PC/OTP/T&C; keys-at-rest; Playwright brittleness; dual Google keys; scheduler controls; PyInstaller cert |
| P2 GAPS | Help/i18n polish; feedback/review; long-form/batch; L3 semantics |
| DEFERRED | Website payment/landing/admin; mobile apps; WhatsApp marketing |
| NEEDS-REDESIGN | Anti-bot browsing; captcha solve; silent auto-reply; unbounded “train agent” loops |
| TOP NEXT STAGE | **C01 — Windows Product Foundation** (then C02–C04) |

---

## Scorecard (GREEN / YELLOW / ORANGE / RED)

| Area | Score | Why |
|------|-------|-----|
| A Foundation | YELLOW | Starts; H5 identity; UX gaps |
| B Authentication | ORANGE | Works; multi-PC/OTP/T&C missing |
| C Entitlement | ORANGE | Lang buy + license; website-coupled |
| D Customer UI | ORANGE | Tabs exist; missing core workflows |
| E API Configuration | YELLOW | Keys UI + readiness |
| F Topic Intelligence | YELLOW engine / RED product | No topic UI |
| G Script | YELLOW engine / RED product | No script UI |
| H Video Production | YELLOW engine / ORANGE product | One-click only |
| I Audio | YELLOW | Engine gates; no UI |
| J Localization | YELLOW | Engine+H4; weak product |
| K Subtitle | YELLOW | Engine; no UI |
| L Quality | GREEN engine / RED product | Fail-closed hidden |
| M Rendering | YELLOW | FFmpeg bundled; no UI |
| N Publishing | ORANGE | Playwright path |
| O Scheduler | YELLOW | Runs; weak controls |
| P Recovery | YELLOW engine / RED product | |
| Q Comments | ORANGE / REDESIGN | Auto agent |
| R Messaging | ORANGE / REDESIGN | |
| S Monitoring | ORANGE | Live panel only |
| T Help | YELLOW | Chat exists |
| U Packaging | YELLOW | Source supported |
| V Security | ORANGE | DEF-H2-007; engagement risk |
| W Observability | YELLOW | Logs/gates; little customer surface |

---

**STOP.** Do not implement C01+. Do not start website work. Await explicit implementation command.
