# AutoMovie Pro — Route Authentication & Security Matrix

**Phase 1A Hardening Deliverable** | **Branch:** `fix/phase-1a`

## 1. Security Architecture Overview

- **S-03 Remediation:** Dynamic per-run cryptographic app token (`secrets.token_hex(32)`).
- **Anti-CSRF & DNS Rebinding:** Host header validation (`127.0.0.1:8787`, `localhost:8787`) and Origin/Referer filtering (external origins blocked with HTTP 403).
- **Media & Binary Protection:** Session-scoped `HttpOnly` + `SameSite=Strict` cookie (`amp_session_token`) issued on `GET /` allows native HTML5 `<img>`, `<video>`, `<audio>`, `<a download>`, and `/output/...` previews to load seamlessly while mathematically barring cross-site embeds.
- **Widget Handoff:** Detached companion widget (`automovie_desktop_widget.py`) receives token via `AUTO_MOVIE_APP_TOKEN` environment variable and owner-only `data/.app_token` file.
- **LAN / Mobile Bridge:** Bound to `127.0.0.1`; protected by the main app token.
- **Server-Proven Google Paid Slots:** Single-use claim verification against `claim_google_slot.php` requiring license Bearer token; duplicate claims rejected with HTTP 409; unreachable website fails closed with HTTP 503 Bengali advisory (never fails open).

## 2. Comprehensive Endpoint Matrix (215 Routes)

| HTTP Method | Endpoint Route | Protection Tier | Purpose & Behavioral Context | Required Credentials |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/activity` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/activity/stop` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/admin/killswitch` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/agent-chat` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/agent/collect-api` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/agent/collect-api/status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/analytics/growth-advice` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/analytics/overview` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/analytics/refresh` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/announcements/list` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/api-providers` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/assets/local-sync` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/auth-login/status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/auth/access` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/auth/device-info` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/auth/identity` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/auth/request-otp` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/auth/reset-password` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/auto-reply/status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/auto-reply/toggle` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/auto-reply/trigger` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/automation-mode` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/automation-mode` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/autoreply/logs` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/autoreply/process` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/bootstrap/run` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/bootstrap/status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/browser-glitches` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/browser-pool/register` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/browser-pool/status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/captcha-open` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/captcha-status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/captcha-unlock` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/captcha/resolve` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/captcha/status/{captcha_id}` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/channels` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/channels/list` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels/{channel_id}/activate` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels/{channel_id}/claim` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels/{channel_id}/deactivate` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels/{channel_id}/facebook-login` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels/{channel_id}/languages` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels/{channel_id}/providers` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels/{channel_id}/providers/{provider_id}/clear` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels/{channel_id}/session-disconnect` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels/{channel_id}/session-health` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels/{channel_id}/tiktok-login` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/channels/{channel_id}/youtube-login` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/comments/scan` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/comments/status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/comments/toggle` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/config/summary` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/dashboard` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/diagnostics/run` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/diagnostics/run` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/drive-accounts` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/drive-accounts` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/drive-accounts/{account_id}/refresh` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/e2e-ui/resume` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/e2e-ui/run` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/e2e-ui/status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/error-notes` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/error-notes/{note_id}/resolve` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/feedback/review` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/feedback/submit-review` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/feedback/submit-ticket` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/foundation` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/generate` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/generate/long` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/generate/short` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/helper/query` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/helper/tooltip` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/human-browsing/history` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/human-browsing/session` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/job/start` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/jobs` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/jobs/create` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/jobs/recent` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/jobs/{job_id}` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/languages` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/languages/local-approve` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/languages/request` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/languages/sync` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/legal/consent` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/legal/terms` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/library/content-bank` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/library/icon-render` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/library/icons` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/live-lab` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/live-lab/comment-check` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/live-lab/connect/{platform}` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/live-lab/live-publish` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/live-lab/names` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/live-lab/start` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/live-lab/stop` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/login` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/logout` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/marketing/broadcast` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/marketing/generate-copy` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/marketing/import-contacts` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/marketing/leads` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/matrix/keys` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/matrix/summary` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/matrix/validate` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/media-capability` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/niches` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/onboarding` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/onboarding/complete` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/onboarding/start` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/open-folder` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/operational-readiness` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/posts` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/posts/{post_id}/stats` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/products` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/products` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/products/ads` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `DELETE` | `/api/products/{product_id}` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/products/{product_id}` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/products/{product_id}/generate-ad` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/publisher/history` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/publisher/publish` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/reels/schedule` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/reels/schedule` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/run-hidden-once` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/script/generate` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/script/regenerate-scene` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/sessions` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/settings/api-keys` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/setup/google-pro-key` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/setup/google-pro-key` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/setup/language-profile` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/setup/overview` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/setup/package-tier` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/setup/unlock-language` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/setup/user-profile` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/storage/clean` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/storage/connect` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/storage/drive-config` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/storage/status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/storage/status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/storage/sync-now` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/subscription/activate-google-paid` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/subscription/google-paid-status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/subscription/order-google-paid` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/support/ticket` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/system/holistic-status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/system/status` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/topics` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/topics/add` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/topics/mark-used` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/trust-browse/log` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/trust-browse/run-once` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/trust-browse/sync` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/videos/library` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/voice/briefing` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/voice/commentary` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/voice/field-guidance` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/voice/preflight-advisory` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/voice/settings` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/voice/settings` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/activity-feed` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/approval` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/certification` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/entry-points` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/execution` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/generate` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/help/context` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/help/query` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/job/{job_id}/cancel` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/monitor` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/notifications` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/notifications/{notification_id}/read` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/preview` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/production-plan` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/production-plan` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/publishing` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/publishing/publish` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/publishing/refresh` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/publishing/schedule` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/publishing/schedule/{schedule_id}/cancel` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/publishing/schedule/{schedule_id}/refresh` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/publishing/schedule/{schedule_id}/reschedule` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/publishing/schedules` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/publishing/validate` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/queue` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/queue/tick` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/research` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/workspace/revision-history` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/script` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/script/approval` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/topic` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/workspace/topics/suggest` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/docs` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/docs/oauth2-redirect` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/openapi.json` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/redoc` | **AUTHENTICATED_APP** | Desktop UI application API route | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/auth/token` | **COOKIE_REQUIRED** | Exposes per-session security token to WebView app wrapper | amp_session_token (HttpOnly, SameSite=Strict) |
| `POST` | `/api/subscription/approve-google-paid` | **CRITICAL_SECURITY** | Server-proven single claim Google Paid Slot unlock | X-App-Token + User Session + License Bearer Token |
| `GET` | `/api/mobile/captcha` | **LOCAL_PROTECTED** | Mobile Wi-Fi bridge (bound to 127.0.0.1) | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/mobile/captcha/simulate` | **LOCAL_PROTECTED** | Mobile Wi-Fi bridge (bound to 127.0.0.1) | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/mobile/captcha/solve` | **LOCAL_PROTECTED** | Mobile Wi-Fi bridge (bound to 127.0.0.1) | X-App-Token OR amp_session_token cookie |
| `GET` | `/api/mobile/status` | **LOCAL_PROTECTED** | Mobile Wi-Fi bridge (bound to 127.0.0.1) | X-App-Token OR amp_session_token cookie |
| `POST` | `/api/mobile/upload/resume` | **LOCAL_PROTECTED** | Mobile Wi-Fi bridge (bound to 127.0.0.1) | X-App-Token OR amp_session_token cookie |
| `GET` | `/` | **PUBLIC** | Unauthenticated public root, static assets, and local health probe | None required (Public Allowlist) |
| `GET` | `/api/health` | **PUBLIC** | Unauthenticated public root, static assets, and local health probe | None required (Public Allowlist) |
| `POST` | `/api/widget/action` | **WIDGET_SECURE** | Companion HUD widget telemetry and control loop | X-App-Token (via env AUTO_MOVIE_APP_TOKEN or .app_token) |
| `POST` | `/api/widget/config` | **WIDGET_SECURE** | Companion HUD widget telemetry and control loop | X-App-Token (via env AUTO_MOVIE_APP_TOKEN or .app_token) |
| `POST` | `/api/widget/start` | **WIDGET_SECURE** | Companion HUD widget telemetry and control loop | X-App-Token (via env AUTO_MOVIE_APP_TOKEN or .app_token) |
| `GET` | `/api/widget/status` | **WIDGET_SECURE** | Companion HUD widget telemetry and control loop | X-App-Token (via env AUTO_MOVIE_APP_TOKEN or .app_token) |
| `POST` | `/api/widget/stop` | **WIDGET_SECURE** | Companion HUD widget telemetry and control loop | X-App-Token (via env AUTO_MOVIE_APP_TOKEN or .app_token) |
| `GET` | `/api/widget/telemetry` | **WIDGET_SECURE** | Companion HUD widget telemetry and control loop | X-App-Token (via env AUTO_MOVIE_APP_TOKEN or .app_token) |
| `POST` | `/api/widget/toggle` | **WIDGET_SECURE** | Companion HUD widget telemetry and control loop | X-App-Token (via env AUTO_MOVIE_APP_TOKEN or .app_token) |

## 3. Cookie Architecture Decision (Mandatory 5-Line Technical Statement)
```
For media tags (<img>, <video>, <audio>, <a download>, iframes) and /output/... previews/thumbnails, browsers do not allow injecting custom HTTP headers (such as X-App-Token).
We chose a cryptographically random, session-scoped HttpOnly + SameSite=Strict cookie (amp_session_token) issued exclusively when the desktop app serves the UI page (GET /).
Because modern browsers strictly forbid attaching SameSite=Strict cookies to any cross-site request (even top-level navigations or cross-origin embed tags from external websites), malicious external websites are mathematically barred from accessing local endpoints or media.
Inside the trusted WebView/app UI context, the browser automatically attaches this cookie to every HTML5 media element, download link, EventSource, and fetch call without URL signing overhead or expiration race conditions.
This achieves complete fail-closed defense against CSRF, DNS rebinding, and cross-site resource embedding while preserving seamless local media rendering.
```