"""Launch installed Chrome/Edge without Playwright automation flags (Google/Facebook login)."""
from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

CHROME_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-extensions",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-default-apps",
    "--no-service-autorun",
    "--disable-sync",
    "--remote-allow-origins=*",
]


def chrome_candidates() -> List[Path]:
    extras = []
    for env_name in ("CHROME_PATH", "AMP_CHROME_PATH"):
        raw = (os.environ.get(env_name) or "").strip()
        if raw:
            extras.append(Path(raw))
    local = Path(os.environ.get("LOCALAPPDATA") or "") / "Google" / "Chrome" / "Application" / "chrome.exe"
    return extras + [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        local,
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]


def find_browser_exe() -> Optional[Path]:
    for p in chrome_candidates():
        if p.exists():
            return p
    return None


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def wait_cdp(port: int, proc: subprocess.Popen, *, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    last_err = "cdp_timeout"
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("browser_exited_before_login")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            return
        except Exception as exc:
            last_err = str(exc)
        time.sleep(0.35)
    raise RuntimeError(f"chrome_debug_port_failed: {last_err}")


def launch_connectable_chrome(user_data: Path, url: str) -> Tuple[subprocess.Popen, int, str]:
    exe = find_browser_exe()
    if not exe:
        raise RuntimeError("Chrome/Edge not found — install Google Chrome")
    user_data.mkdir(parents=True, exist_ok=True)
    port = free_port()
    args = [
        str(exe),
        f"--user-data-dir={user_data}",
        f"--remote-debugging-port={port}",
        *CHROME_ARGS,
        url,
    ]
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_cdp(port, proc)
    return proc, port, exe.name
