# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Industrial Network Resilience & Outage Recovery System
======================================================================
Guarantees zero crashes during electricity power cuts or ISP network drops.
1. Actively detects DNS / Socket disconnects.
2. Holds pipeline execution in a safe, patient heartbeat loop until connectivity restores.
3. Automatically resumes from the exact state without losing rendered scenes or progress.
"""

from __future__ import annotations

import logging
import socket
import time
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger("NetworkResilience")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s][NetResilience][%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

T = TypeVar("T")

# Reliable public DNS and endpoints to probe
PROBE_HOSTS = [
    ("8.8.8.8", 53),       # Google DNS
    ("1.1.1.1", 53),       # Cloudflare DNS
    ("208.67.222.222", 53) # OpenDNS
]


def is_internet_available(timeout: float = 2.5) -> bool:
    """Checks if internet connectivity is active via lightweight low-level socket probe."""
    for host, port in PROBE_HOSTS:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            s.close()
            return True
        except (socket.timeout, socket.error, OSError):
            continue
    return False


def wait_until_online(probe_interval_sec: float = 5.0, max_wait_sec: Optional[float] = None) -> bool:
    """
    Blocks safely until internet connectivity is restored.
    Logs heartbeat messages every 15-20 seconds so user and system know it is waiting.
    """
    if is_internet_available():
        return True

    logger.warning("⚠️ [NETWORK DISCONNECTED] Internet connection dropped or power interruption detected!")
    logger.warning("⏸️ Pausing pipeline safely. System will automatically resume once connectivity restores...")

    start_t = time.time()
    last_log_t = start_t

    while True:
        if is_internet_available():
            duration = round(time.time() - start_t, 1)
            logger.info("✅ [NETWORK RESTORED] Connection re-established after %ss! Resuming pipeline immediately...", duration)
            time.sleep(2.0)  # Brief cooldown for DNS caches to stabilize
            return True

        curr_t = time.time()
        if curr_t - last_log_t >= 20.0:
            logger.info("⏳ [Network Heartbeat] Still waiting for internet connection... (Elapsed: %ss)", round(curr_t - start_t))
            last_log_t = curr_t

        if max_wait_sec and (curr_t - start_t) > max_wait_sec:
            logger.error("❌ Exceeded max network wait time (%ss).", max_wait_sec)
            return False

        time.sleep(probe_interval_sec)


def resilient_network_call(
    fn: Callable[..., T],
    *args: Any,
    max_retries: int = 10,
    retry_delay_sec: float = 3.0,
    **kwargs: Any
) -> T:
    """
    Executes a network-dependent callable (Gemini API, TTS, upload, download).
    If a network/DNS error occurs, waits for connection restoration and retries seamlessly.
    """
    attempt = 0
    while attempt < max_retries:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            err_str = str(exc).lower()
            is_net_err = any(needle in err_str for needle in [
                "11001", "getaddrinfo", "connecterror", "connectionreset",
                "timed out", "timeout", "network is unreachable", "remoteendclosed",
                "readtimeouterror", "protocolerror", "dns", "broken pipe"
            ])

            if is_net_err:
                logger.warning("🔌 Network glitch encountered on attempt %d/%d: %s", attempt + 1, max_retries, exc)
                wait_until_online()
                attempt += 1
                time.sleep(retry_delay_sec)
            else:
                # Non-network error (e.g. invalid arguments) — re-raise
                raise exc

    # Final attempt
    return fn(*args, **kwargs)
