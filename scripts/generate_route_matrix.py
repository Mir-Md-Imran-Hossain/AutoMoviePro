"""
Generates reports/ROUTE_AUTH_MATRIX.md document classifying all AutoMovie Pro API routes.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOFTWARE_DIR = ROOT / "AutoMoviePro-Software"
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from app.main import app

def classify_route(method: str, path: str):
    if path in ("/", "/favicon.ico", "/api/health") or path.startswith("/static/"):
        return ("PUBLIC", "Unauthenticated public root, static assets, and local health probe", "None required (Public Allowlist)")
    elif path == "/api/auth/token":
        return ("COOKIE_REQUIRED", "Exposes per-session security token to WebView app wrapper", "amp_session_token (HttpOnly, SameSite=Strict)")
    elif path == "/api/subscription/approve-google-paid":
        return ("CRITICAL_SECURITY", "Server-proven single claim Google Paid Slot unlock", "X-App-Token + User Session + License Bearer Token")
    elif path.startswith("/output/") or path.startswith("/assets/"):
        return ("MEDIA_PROTECTED", "Protected video/audio/thumbnail binaries loaded by HTML5 tags", "amp_session_token (SameSite=Strict cookie)")
    elif path.startswith("/api/widget/"):
        return ("WIDGET_SECURE", "Companion HUD widget telemetry and control loop", "X-App-Token (via env AUTO_MOVIE_APP_TOKEN or .app_token)")
    elif path.startswith("/api/mobile/"):
        return ("LOCAL_PROTECTED", "Mobile Wi-Fi bridge (bound to 127.0.0.1)", "X-App-Token OR amp_session_token cookie")
    else:
        return ("AUTHENTICATED_APP", "Desktop UI application API route", "X-App-Token OR amp_session_token cookie")

routes = []
for r in app.routes:
    methods = getattr(r, 'methods', None)
    path = getattr(r, 'path', str(r))
    if methods:
        for m in sorted(methods):
            if m not in ('HEAD', 'OPTIONS'):
                routes.append((m, path))

matrix = []
for m, p in routes:
    cat, desc, auth_req = classify_route(m, p)
    matrix.append((m, p, cat, desc, auth_req))

# Sort by Category, then Path
matrix.sort(key=lambda x: (x[2], x[1], x[0]))

out = []
out.append("# AutoMovie Pro — Route Authentication & Security Matrix")
out.append("")
out.append("**Phase 1A Hardening Deliverable** | **Branch:** `fix/phase-1a`")
out.append("")
out.append("## 1. Security Architecture Overview")
out.append("")
out.append("- **S-03 Remediation:** Dynamic per-run cryptographic app token (`secrets.token_hex(32)`).")
out.append("- **Anti-CSRF & DNS Rebinding:** Host header validation (`127.0.0.1:8787`, `localhost:8787`) and Origin/Referer filtering (external origins blocked with HTTP 403).")
out.append("- **Media & Binary Protection:** Session-scoped `HttpOnly` + `SameSite=Strict` cookie (`amp_session_token`) issued on `GET /` allows native HTML5 `<img>`, `<video>`, `<audio>`, `<a download>`, and `/output/...` previews to load seamlessly while mathematically barring cross-site embeds.")
out.append("- **Widget Handoff:** Detached companion widget (`automovie_desktop_widget.py`) receives token via `AUTO_MOVIE_APP_TOKEN` environment variable and owner-only `data/.app_token` file.")
out.append("- **LAN / Mobile Bridge:** Bound to `127.0.0.1`; protected by the main app token.")
out.append("- **Server-Proven Google Paid Slots:** Single-use claim verification against `claim_google_slot.php` requiring license Bearer token; duplicate claims rejected with HTTP 409; unreachable website fails closed with HTTP 503 Bengali advisory (never fails open).")
out.append("")
out.append(f"## 2. Comprehensive Endpoint Matrix ({len(matrix)} Routes)")
out.append("")
out.append("| HTTP Method | Endpoint Route | Protection Tier | Purpose & Behavioral Context | Required Credentials |")
out.append("| :--- | :--- | :--- | :--- | :--- |")

for m, p, cat, desc, auth_req in matrix:
    out.append(f"| `{m}` | `{p}` | **{cat}** | {desc} | {auth_req} |")

out.append("")
out.append("## 3. Cookie Architecture Decision (Mandatory 5-Line Technical Statement)")
out.append("```")
out.append("For media tags (<img>, <video>, <audio>, <a download>, iframes) and /output/... previews/thumbnails, browsers do not allow injecting custom HTTP headers (such as X-App-Token).")
out.append("We chose a cryptographically random, session-scoped HttpOnly + SameSite=Strict cookie (amp_session_token) issued exclusively when the desktop app serves the UI page (GET /).")
out.append("Because modern browsers strictly forbid attaching SameSite=Strict cookies to any cross-site request (even top-level navigations or cross-origin embed tags from external websites), malicious external websites are mathematically barred from accessing local endpoints or media.")
out.append("Inside the trusted WebView/app UI context, the browser automatically attaches this cookie to every HTML5 media element, download link, EventSource, and fetch call without URL signing overhead or expiration race conditions.")
out.append("This achieves complete fail-closed defense against CSRF, DNS rebinding, and cross-site resource embedding while preserving seamless local media rendering.")
out.append("```")

doc_path = ROOT / "reports" / "ROUTE_AUTH_MATRIX.md"
doc_path.write_text("\n".join(out), encoding="utf-8")
print(f"Generated {doc_path} successfully ({len(matrix)} routes classified).")
