# E2E UI Automation Engine (Camoufox / Playwright)

Modular package under `pipeline/e2e_ui/`:

| Class | Module | Role |
|-------|--------|------|
| `BrowserEngine` | `browser_engine.py` | Camoufox (`humanize=True`) + persistent `user_data_dir` / storage_state; Playwright fallback |
| `HumanInteractionManager` | `human_input.py` | Bézier mouse, 50–180ms typing, staggered wheel scrolls |
| `WorkflowTaskRunner` | `workflows.py` | Task A discovery, B engagement, C inbox |
| `AlertHandler` | `alert_handler.py` | CAPTCHA/challenge detect → pause → webhook/beep → operator resume |

## CLI

```powershell
cd AutoMoviePro-Software
python scripts/run_e2e_ui.py --platform youtube --query "space science" --tasks a --watch 15
python scripts/run_e2e_ui.py --platform youtube --tasks b --like --comment "Great video"
```

## API

- `GET  /api/e2e-ui/status`
- `POST /api/e2e-ui/resume`
- `POST /api/e2e-ui/run`  body: `{platform, query, url, tasks, subscribe, like, comment, watch_seconds, headless}`

Challenge unlock also works via existing `POST /api/captcha-unlock` (sets `e2e_challenge_resume`).

## Env

- `AMP_E2E_HEADLESS=1`
- `AMP_E2E_FORCE_PLAYWRIGHT=1` — skip Camoufox
- `AMP_E2E_PROFILE_DIR=...` — profile root

## Install / first-run (customer auto-bootstrap)

Camoufox + Playwright Chromium install automatically on customer machines via `START.bat` → `python -m app.bootstrap_runtime`.

```powershell
python -m app.bootstrap_runtime --status
python scripts\bootstrap_customer_tools.py --force
```

Manual (dev only):

```powershell
pip install camoufox playwright playwright-stealth
python -m playwright install chromium
python -m camoufox fetch
```

Without Camoufox, the engine falls back to Playwright. Skip Camoufox with `AMP_BOOTSTRAP_SKIP_CAMOUFOX=1`.
