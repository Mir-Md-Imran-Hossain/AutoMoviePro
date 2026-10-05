"""
Agent-assisted API key collection from provider portals.

Non-tech flow (WhatsApp-like guided connect):
  1) Agent opens a headed Chrome window on the provider portal
  2) User signs in once if needed (cookies persist in session_vault)
  3) Agent watches the page for created/visible keys (AIza…, gsk_…, sk-or-…)
  4) Keys are saved into channel API slots — user never pastes into Settings

Best-effort DOM heuristics — portals change; CAPTCHA pauses for admin.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.api_guides import PROVIDER_PORTALS
from pipeline.channel_api_slots import MIN_REQUIRED, channel_provider_keys, empty_slot_map

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}

_TOKEN_PATTERNS = {
    "google": re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    "groq": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    "openrouter": re.compile(r"sk-or-v1-[A-Za-z0-9]{20,}|sk-or-[A-Za-z0-9_\-]{20,}"),
    "huggingface": re.compile(r"hf_[A-Za-z0-9]{20,}"),
    "pexels": re.compile(r"\b[A-Za-z0-9]{32,64}\b"),
    "pollinations": re.compile(r"\b[A-Za-z0-9_\-]{24,}\b"),
    "agnes": re.compile(r"\b[A-Za-z0-9_\-]{24,}\b"),
    "cerebras": re.compile(r"csk-[A-Za-z0-9_\-]{20,}|[A-Za-z0-9_\-]{32,}"),
    "freetheai": re.compile(r"\b[A-Za-z0-9_\-]{24,}\b"),
}

_CREATE_BUTTON_LABELS = (
    "Create API key",
    "Create API Key",
    "Get API key",
    "Create key",
    "Generate API key",
    "Create new key",
    "New API key",
    "Create token",
    "New token",
    "Generate token",
    "Create secret key",
)


def get_job(job_id: str) -> Dict[str, Any]:
    with _lock:
        st = dict(_jobs.get(job_id) or {})
    if not st:
        return {"ok": False, "status": "unknown", "error": "job_not_found"}
    st["ok"] = st.get("status") not in ("failed",)
    return st


def list_active_jobs() -> List[Dict[str, Any]]:
    with _lock:
        return [dict(v) for v in _jobs.values() if v.get("status") in ("starting", "opening", "waiting_login", "collecting")]


def _set(job_id: str, **fields: Any) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def start_collect(
    provider: str,
    *,
    channel_id: int = 0,
    timeout_sec: int = 300,
) -> Dict[str, Any]:
    provider = (provider or "").strip().lower()
    if provider not in PROVIDER_PORTALS and provider != "missing":
        return {"ok": False, "error": "unknown_provider", "provider": provider}

    if provider == "missing":
        return start_collect_missing(channel_id=channel_id, timeout_sec=timeout_sec)

    job_id = uuid.uuid4().hex[:10]
    with _lock:
        for jid, st in list(_jobs.items()):
            if (
                st.get("provider") == provider
                and st.get("status") in ("starting", "opening", "waiting_login", "collecting")
            ):
                return {"ok": True, "job_id": jid, "status": st.get("status"), "message": "already_running"}
        _jobs[job_id] = {
            "job_id": job_id,
            "provider": provider,
            "channel_id": channel_id,
            "status": "starting",
            "keys_found": 0,
            "error": "",
            "message": "Starting guided API collection…",
            "started_at": time.time(),
        }

    t = threading.Thread(
        target=_run_collect,
        args=(job_id, provider, channel_id, timeout_sec),
        daemon=True,
        name=f"api-collect-{provider}",
    )
    t.start()
    time.sleep(0.3)
    return get_job(job_id)


def start_collect_missing(*, channel_id: int = 0, timeout_sec: int = 300) -> Dict[str, Any]:
    """Queue required providers that still need keys (sequential)."""
    from app import db as store
    from pipeline.channel_api_slots import PROVIDER_DEFS

    ch = store.get_channel(channel_id) if channel_id else (store.list_channels() or [None])[0]
    if not ch:
        return {"ok": False, "error": "no_channel"}
    keys = channel_provider_keys(ch)
    missing = [pid for pid, _, req in PROVIDER_DEFS if req and len(keys.get(pid) or []) < MIN_REQUIRED]
    if not missing:
        return {"ok": True, "status": "done", "message": "all_required_keys_present", "missing": []}

    job_id = uuid.uuid4().hex[:10]
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "provider": "missing",
            "channel_id": int(ch["id"]),
            "status": "starting",
            "queue": missing,
            "keys_found": 0,
            "error": "",
            "message": f"Will collect: {', '.join(missing)}",
            "started_at": time.time(),
        }

    def _seq():
        total = 0
        cid = int(ch["id"])
        for pid in missing:
            _set(job_id, status="collecting", provider=pid, message=f"Collecting {pid}…")
            sub = start_collect(pid, channel_id=cid, timeout_sec=timeout_sec)
            sub_id = sub.get("job_id") or ""
            # Wait for sub-job
            for _ in range(timeout_sec + 30):
                st = get_job(sub_id)
                if st.get("status") in ("saved", "failed", "timeout"):
                    total += int(st.get("keys_found") or 0)
                    break
                time.sleep(1)
        _set(
            job_id,
            status="saved" if total else "failed",
            keys_found=total,
            message=f"Collected {total} key(s) across missing providers",
            provider="missing",
        )

    threading.Thread(target=_seq, daemon=True, name="api-collect-missing").start()
    time.sleep(0.3)
    return get_job(job_id)


def _profile_dir(provider: str) -> Path:
    from publishers.session_vault import VAULT_ROOT

    d = VAULT_ROOT / f"api_portal_{provider}"
    d.mkdir(parents=True, exist_ok=True)
    return d / "chrome_profile"


def _scrape_keys(page, provider: str) -> List[str]:
    pat = _TOKEN_PATTERNS.get(provider) or re.compile(r"[A-Za-z0-9_\-]{32,}")
    found: List[str] = []
    try:
        text = page.content() or ""
    except Exception:
        text = ""
    for m in pat.finditer(text):
        tok = m.group(0)
        if tok not in found and len(tok) >= 20:
            found.append(tok)
    # Also check input values / code blocks via JS
    try:
        extras = page.evaluate(
            """() => {
              const out = [];
              document.querySelectorAll('input, textarea, code, pre, [data-testid]').forEach(el => {
                const v = (el.value || el.textContent || '').trim();
                if (v && v.length >= 20 && v.length < 500) out.push(v);
              });
              return out.slice(0, 40);
            }"""
        )
        for v in extras or []:
            for m in pat.finditer(str(v)):
                tok = m.group(0)
                if tok not in found:
                    found.append(tok)
    except Exception:
        pass
    # Filter obvious noise
    junk = ("http", "https", "password", "example", "xxxxxx", "your_api")
    clean = []
    for t in found:
        low = t.lower()
        if any(j in low for j in junk):
            continue
        if provider == "google" and not t.startswith("AIza"):
            continue
        if provider == "groq" and not t.startswith("gsk_"):
            continue
        if provider == "openrouter" and "sk-or" not in t:
            continue
        if provider == "huggingface" and not t.startswith("hf_"):
            continue
        clean.append(t)
    return clean[:5]


def _try_click_create(page) -> bool:
    from publishers.human_browser import human_click, human_sleep

    for label in _CREATE_BUTTON_LABELS:
        try:
            btn = page.get_by_role("button", name=re.compile(re.escape(label), re.I))
            if btn.count():
                human_click(page, btn.first)
                human_sleep(1.0, 2.5)
                return True
            link = page.get_by_text(label, exact=False)
            if link.count():
                human_click(page, link.first)
                human_sleep(1.0, 2.5)
                return True
        except Exception:
            continue
    return False


def _apply_keys(channel_id: int, provider: str, keys: List[str]) -> int:
    from app import db as store
    from app.main import _apply_api_keys_dict

    # Prefer first channel if id missing
    if not channel_id:
        chs = store.list_channels()
        if not chs:
            return 0
        channel_id = int(chs[0]["id"])
    payload = empty_slot_map()
    payload[provider] = keys[:5]
    # _apply_api_keys_dict expects provider→list and merges into current channel
    # Use a focused merge via store directly if main helper needs session
    try:
        result = _apply_api_keys_dict({provider: keys[:5]})
        return int((result or {}).get("applied_count") or len(keys))
    except Exception:
        ch = store.get_channel(channel_id)
        if not ch:
            return 0
        from pipeline.channel_api_slots import merge_keep_existing, serialize_api_keys_json

        existing = channel_provider_keys(ch)
        merged = merge_keep_existing(existing, {provider: keys})
        ch["api_keys_json"] = serialize_api_keys_json(merged)
        store.upsert_channel(ch, channel_id)
        return len(keys)


def _run_collect(job_id: str, provider: str, channel_id: int, timeout_sec: int) -> None:
    from publishers.human_browser import (
        CaptchaBlockedError,
        assert_no_captcha,
        aimless_scroll,
        human_sleep,
        reading_pause,
    )
    from publishers.stealth_session import stealth_browser

    meta = PROVIDER_PORTALS.get(provider) or {}
    url = meta.get("portal_url") or ""
    if not url:
        _set(job_id, status="failed", error="no_portal_url")
        return

    profile = str(_profile_dir(provider))
    storage = str(Path(profile).parent / "storage_state.json")
    try:
        _set(job_id, status="opening", message=f"Opening {meta.get('portal_label') or provider}…")
        with stealth_browser(
            storage_state=storage if Path(storage).exists() else "",
            user_data_dir=profile,
            headless=False,
        ) as (_pw, _b, page, engine):
            logger.info("api collect %s via %s", provider, engine)
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            human_sleep(1.5, 3.0)
            try:
                assert_no_captcha(page, platform=f"api_portal:{provider}", url=url)
            except CaptchaBlockedError:
                _set(job_id, status="failed", error="captcha_locked", message="CAPTCHA — admin must unlock")
                return

            _set(job_id, status="waiting_login", message="Sign in if asked — agent will grab keys automatically")
            deadline = time.time() + max(60, int(timeout_sec))
            clicked_create = False
            saved_keys: List[str] = []

            while time.time() < deadline:
                if page.is_closed():
                    break
                try:
                    assert_no_captcha(page, platform=f"api_portal:{provider}", url=page.url)
                except CaptchaBlockedError:
                    _set(job_id, status="failed", error="captcha_locked")
                    return

                keys = _scrape_keys(page, provider)
                if keys:
                    saved_keys = keys
                    _set(job_id, status="collecting", keys_found=len(keys), message=f"Found {len(keys)} key(s)")
                    if len(keys) >= MIN_REQUIRED:
                        break
                    # Keep looking for a second key if only one
                if not clicked_create and random_should_create():
                    clicked_create = _try_click_create(page)
                    if clicked_create:
                        _set(job_id, message="Clicked create-key — finish any popup, agent watches…")
                        reading_pause(2.0)

                if time.time() % 12 < 1.2:
                    aimless_scroll(page, bursts=1)
                human_sleep(1.2, 2.4)

            try:
                page.context.storage_state(path=storage)
            except Exception:
                pass

        if not saved_keys:
            _set(
                job_id,
                status="timeout",
                error="no_keys_found",
                message="No key detected — create one on the page and ask agent again, or paste into chat.",
            )
            return

        n = _apply_keys(channel_id, provider, saved_keys)
        _set(
            job_id,
            status="saved",
            keys_found=n or len(saved_keys),
            message=f"Saved {n or len(saved_keys)} {provider} key(s) into Settings",
        )
    except Exception as exc:
        logger.exception("api collect failed")
        _set(job_id, status="failed", error=str(exc)[:300])


def random_should_create() -> bool:
    # Always try once early; function name kept for clarity at call site
    return True
