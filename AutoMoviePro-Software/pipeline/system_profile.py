"""
Detect host RAM/CPU and expose encode settings so the app survives ~2GB PCs.

Profiles:
  low   — ≤3 GiB RAM (or AMP_FORCE_LOW_RAM=1)
  mid   — ≤8 GiB
  high  — otherwise
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _ram_bytes() -> int:
    try:
        import psutil  # type: ignore

        return int(psutil.virtual_memory().total)
    except Exception:
        pass
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return int(stat.ullTotalPhys)
    except Exception:
        return 8 * 1024**3  # assume mid if unknown


@lru_cache(maxsize=1)
def detect_profile() -> Dict[str, Any]:
    if os.environ.get("AMP_FORCE_LOW_RAM", "").strip() == "1":
        tier = "low"
        ram = _ram_bytes()
    else:
        ram = _ram_bytes()
        gib = ram / (1024**3)
        if gib <= 3.0:
            tier = "low"
        elif gib <= 8.0:
            tier = "mid"
        else:
            tier = "high"
    if tier == "low":
        cfg = {
            "tier": "low",
            "ram_bytes": ram,
            "ffmpeg_preset": "ultrafast",
            "ffmpeg_crf": "24",
            "ffmpeg_threads": "1",
            "max_parallel_scenes": 1,
            "agnes_create_gap_sec": 70.0,
            "prefer_image_fallback_ sooner": False,
            "note": "2–3GB RAM profile: single-thread ffmpeg, ultrafast, low peak memory",
        }
    elif tier == "mid":
        cfg = {
            "tier": "mid",
            "ram_bytes": ram,
            "ffmpeg_preset": "veryfast",
            "ffmpeg_crf": "22",
            "ffmpeg_threads": "2",
            "max_parallel_scenes": 1,
            "agnes_create_gap_sec": 55.0,
            "note": "4–8GB RAM profile",
        }
    else:
        cfg = {
            "tier": "high",
            "ram_bytes": ram,
            "ffmpeg_preset": "veryfast",
            "ffmpeg_crf": "20",
            "ffmpeg_threads": "0",  # auto
            "max_parallel_scenes": 1,
            "agnes_create_gap_sec": 55.0,
            "note": "8GB+ RAM profile",
        }
    logger.info(
        "System profile=%s RAM=%.1fGiB preset=%s threads=%s",
        cfg["tier"],
        ram / (1024**3),
        cfg["ffmpeg_preset"],
        cfg["ffmpeg_threads"],
    )
    return cfg


def ffmpeg_x264_args() -> List[str]:
    """Args after -c:v libx264 for memory-safe encodes."""
    p = detect_profile()
    args = ["-preset", str(p["ffmpeg_preset"]), "-crf", str(p["ffmpeg_crf"])]
    th = str(p.get("ffmpeg_threads") or "0")
    if th and th != "0":
        args.extend(["-threads", th])
    # Limit buffer sizes on low RAM to reduce ffmpeg spikes
    if p["tier"] == "low":
        args.extend(["-max_muxing_queue_size", "1024"])
    return args


def agnes_create_gap_sec() -> float:
    env = os.environ.get("AMP_AGNES_CREATE_GAP_SEC", "").strip()
    if env:
        try:
            return max(35.0, float(env))
        except ValueError:
            pass
    return float(detect_profile().get("agnes_create_gap_sec") or 55.0)
