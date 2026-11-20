"""
AutoMovie Pro - Companion Desktop HUD Widget Service
Manages widget lifecycle, background persistence, configuration,
and aggregates real-time production telemetry for the floating desktop widget.
"""

from __future__ import annotations

import os
import sys
import json
import time
import ctypes
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
WIDGET_CONFIG_FILE = DATA_DIR / "widget_settings.json"
WIDGET_PID_FILE = DATA_DIR / "widget_process.pid"
WIDGET_SCRIPT = ROOT_DIR / "automovie_desktop_widget.py"
LAUNCHER_SCRIPT = ROOT_DIR / "launch_desktop_app.py"

_SERVER_START_TIME = time.time()


# ---------------------------------------------------------------------------
# Windows System Resource Telemetry (ctypes zero-dependency + fast)
# ---------------------------------------------------------------------------
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
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_ulong),
        ("dwHighDateTime", ctypes.c_ulong),
    ]


_last_cpu_sample = {"time": 0.0, "idle": 0, "kernel": 0, "user": 0, "cached_pct": 5}


def _filetime_to_int(ft: FILETIME) -> int:
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


def get_system_load() -> Tuple[int, int]:
    """Returns (cpu_percent, ram_percent) using native Windows APIs without external wheels."""
    # 1. RAM Usage
    ram_pct = 40
    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            ram_pct = int(stat.dwMemoryLoad)
    except Exception:
        pass

    # 2. CPU Usage
    cpu_pct = _last_cpu_sample.get("cached_pct", 5)
    now_t = time.time()
    if now_t - _last_cpu_sample["time"] >= 1.0:
        try:
            idle_ft, kern_ft, usr_ft = FILETIME(), FILETIME(), FILETIME()
            if ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle_ft), ctypes.byref(kern_ft), ctypes.byref(usr_ft)
            ):
                cur_idle = _filetime_to_int(idle_ft)
                cur_kern = _filetime_to_int(kern_ft)
                cur_usr = _filetime_to_int(usr_ft)

                last_idle = _last_cpu_sample["idle"]
                last_kern = _last_cpu_sample["kernel"]
                last_usr = _last_cpu_sample["user"]

                if _last_cpu_sample["time"] > 0:
                    d_idle = cur_idle - last_idle
                    d_kern = cur_kern - last_kern
                    d_usr = cur_usr - last_usr
                    total = d_kern + d_usr
                    if total > 0:
                        cpu_pct = max(0, min(100, int(round((total - d_idle) * 100.0 / total))))
                        _last_cpu_sample["cached_pct"] = cpu_pct

                _last_cpu_sample["time"] = now_t
                _last_cpu_sample["idle"] = cur_idle
                _last_cpu_sample["kernel"] = cur_kern
                _last_cpu_sample["user"] = cur_usr
        except Exception:
            pass

    return cpu_pct, ram_pct


# ---------------------------------------------------------------------------
# Configuration Persistence
# ---------------------------------------------------------------------------
DEFAULT_WIDGET_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "always_on_top": True,
    "keep_active_on_minimize": True,
    "compact_mode": False,
    "refresh_rate_sec": 2,
    "dock_position": "top_right",
}


def get_widget_config() -> Dict[str, Any]:
    """Reads widget settings safely with atomic defaults."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if WIDGET_CONFIG_FILE.exists():
        try:
            with open(WIDGET_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = dict(DEFAULT_WIDGET_CONFIG)
                merged.update(data)
                return merged
        except Exception:
            pass
    return dict(DEFAULT_WIDGET_CONFIG)


def save_widget_config(cfg: Dict[str, Any]) -> bool:
    """Saves widget settings safely with atomic temp file swap."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        tmp_file = WIDGET_CONFIG_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        tmp_file.replace(WIDGET_CONFIG_FILE)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Process & Lifecycle Management
# ---------------------------------------------------------------------------
def _is_pid_alive(pid: int) -> bool:
    """Checks if a Windows process PID exists and is running."""
    if pid <= 0:
        return False
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            # STILL_ACTIVE = 259
            return exit_code.value == 259
    except Exception:
        pass
    return False


def is_widget_running() -> Tuple[bool, Optional[int]]:
    """Checks whether the desktop widget process is actively running."""
    if not WIDGET_PID_FILE.exists():
        return False, None
    try:
        with open(WIDGET_PID_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            pid = data.get("pid")
            if pid and _is_pid_alive(int(pid)):
                return True, int(pid)
    except Exception:
        pass
    return False, None


def get_pythonw_path() -> str:
    """Finds silent pythonw executable."""
    candidates = [
        ROOT_DIR / "venv" / "Scripts" / "pythonw.exe",
        ROOT_DIR / "python_embedded" / "pythonw.exe",
        Path(sys.executable).parent / "pythonw.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "pythonw.exe"


def start_widget(force_restart: bool = False) -> bool:
    """Starts the companion desktop widget silently in the background detached."""
    is_running, existing_pid = is_widget_running()
    if is_running and not force_restart:
        return True
    if is_running and force_restart and existing_pid:
        stop_widget()
        time.sleep(0.3)

    if not WIDGET_SCRIPT.exists():
        return False

    pyw = get_pythonw_path()
    DETACHED_FLAGS = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | DETACHED_PROCESS

    try:
        env = os.environ.copy()
        try:
            from app.security import get_or_create_app_token
            env["AUTO_MOVIE_APP_TOKEN"] = get_or_create_app_token()
        except Exception:
            pass

        proc = subprocess.Popen(
            [pyw, str(WIDGET_SCRIPT)],
            cwd=str(ROOT_DIR),
            env=env,
            creationflags=DETACHED_FLAGS if sys.platform == "win32" else 0,
            close_fds=True,
        )
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(WIDGET_PID_FILE, "w", encoding="utf-8") as f:
            json.dump({"pid": proc.pid, "started_at": datetime.now().isoformat()}, f, indent=2)
        return True
    except Exception:
        return False


def stop_widget() -> bool:
    """Gracefully terminates the companion desktop widget process."""
    is_running, pid = is_widget_running()
    if not is_running or not pid:
        if WIDGET_PID_FILE.exists():
            try:
                WIDGET_PID_FILE.unlink()
            except Exception:
                pass
        return True

    try:
        PROCESS_TERMINATE = 0x0001
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if handle:
            ctypes.windll.kernel32.TerminateProcess(handle, 0)
            ctypes.windll.kernel32.CloseHandle(handle)
        if WIDGET_PID_FILE.exists():
            WIDGET_PID_FILE.unlink()
        return True
    except Exception:
        if WIDGET_PID_FILE.exists():
            try:
                WIDGET_PID_FILE.unlink()
            except Exception:
                pass
        return False


def toggle_widget() -> Dict[str, Any]:
    """Toggles the widget ON or OFF and updates persistent settings."""
    cfg = get_widget_config()
    is_running, _ = is_widget_running()

    if is_running:
        stop_widget()
        cfg["enabled"] = False
        save_widget_config(cfg)
        return {"ok": True, "enabled": False, "running": False, "message": "উইজেট বন্ধ করা হয়েছে"}
    else:
        cfg["enabled"] = True
        save_widget_config(cfg)
        ok = start_widget()
        return {"ok": ok, "enabled": True, "running": ok, "message": "উইজেট চালু করা হয়েছে"}


def ensure_widget_started_on_boot():
    """Starts widget if enabled in config AND customer is authenticated."""
    try:
        from app import db as store
        session = store.get_session()
        if not session or not session.get("login_id"):
            return  # Fail-closed: Never start desktop widget for unauthenticated users
    except Exception:
        return

    cfg = get_widget_config()
    if cfg.get("enabled", True):
        start_widget()


# ---------------------------------------------------------------------------
# Telemetry Aggregation for Desktop Widget HUD
# ---------------------------------------------------------------------------
STAGE_BANGLA_MAP: Dict[str, str] = {
    "QUEUED": "অপেক্ষমান • কিউতে রাখা হয়েছে",
    "PROCESSING": "প্রসেসিং চলছে...",
    "RESEARCHING": "টপিক রিসার্চ ও ডাটা বিশ্লেষণ",
    "SCRIPTING": "স্মার্ট এআই স্ক্রিপ্ট রচনা হচ্ছে",
    "AUDIO": "ভয়েসওভার ও স্টুডিও অডিও সংশ্লেষণ",
    "TTS": "ভয়েসওভার ও স্টুডিও অডিও সংশ্লেষণ",
    "RENDERING": "সিনেমাটিক ৪K/HD ফ্রেম ও সাবটাইটেল রেন্ডারিং",
    "UPLOADING": "সোশ্যাল মিডিয়ায় স্বয়ংক্রিয় রিলস আপলোড হচ্ছে",
    "READY": "ভিডিও তৈরি সম্পন্ন • রিভিউয়ের অপেক্ষায়",
    "COMPLETED": "সফলভাবে আপলোড সম্পন্ন হয়েছে",
    "FAILED": "ত্রুটি চিহ্নিত • সেলফ-হিলিং সক্রিয়",
    "IDLE": "স্ট্যান্ডবাই • অটোমেশন শিডিউলের অপেক্ষায়",
}


def to_bangla_digits(val: Any) -> str:
    """Converts english numbers to Bengali digits."""
    s = str(val)
    mapping = {"0": "০", "1": "১", "2": "২", "3": "৩", "4": "৪", "5": "৫", "6": "৬", "7": "৭", "8": "৮", "9": "৯"}
    for en, bn in mapping.items():
        s = s.replace(en, bn)
    return s


def get_widget_telemetry() -> Dict[str, Any]:
    """Aggregates all real-time engine telemetry for the widget."""
    from app import db as store
    import app.customer_job as cj

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # 1. System Load
    cpu_pct, ram_pct = get_system_load()

    # 2. Server Uptime
    uptime_sec = int(time.time() - _SERVER_START_TIME)
    uptime_hours = uptime_sec // 3600
    uptime_mins = (uptime_sec % 3600) // 60

    # 3. Active Channels & Primary Channel
    channels = store.list_channels()
    total_channels = len(channels)
    primary_channel_name = "AutoMovie Studio"
    primary_niche = "AI Automation & Faceless Content"
    if channels:
        ch0 = channels[0]
        primary_channel_name = ch0.get("name") or ch0.get("channel_name") or f"Channel #{ch0.get('id')}"
        primary_niche = ch0.get("niche") or primary_niche

    # 4. Active Job / Current Activity (বর্তমান কার্যক্রম)
    active_activity: Dict[str, Any] = {
        "is_busy": False,
        "job_id": None,
        "title": "স্বয়ংক্রিয় শিডিউলের অপেক্ষায় সিস্টেম প্রস্তুত",
        "stage": "IDLE",
        "stage_label_bn": STAGE_BANGLA_MAP["IDLE"],
        "progress": 0,
        "progress_bn": "০%",
        "channel_name": primary_channel_name,
        "niche": primary_niche,
        "detail": "পরবর্তী শিডিউল সময়ে স্বয়ংক্রিয়ভাবে ভিডিও তৈরি ও রিলস পাবলিশ হবে।",
    }

    recent_jobs = cj.list_customer_jobs(limit=10)
    for j in recent_jobs:
        status = (j.get("status") or j.get("customer_state") or "").upper()
        if status in ("QUEUED", "PROCESSING", "RUNNING", "SCRIPTING", "AUDIO", "TTS", "RENDERING", "UPLOADING"):
            stage_key = status
            if "RENDER" in status:
                stage_key = "RENDERING"
            elif "AUDIO" in status or "TTS" in status:
                stage_key = "AUDIO"
            elif "SCRIPT" in status:
                stage_key = "SCRIPTING"
            elif "UPLOAD" in status:
                stage_key = "UPLOADING"

            prog = int(j.get("progress") or 35)
            active_activity = {
                "is_busy": True,
                "job_id": j.get("id"),
                "title": j.get("title") or "স্মার্ট এআই রিলস জেনারেশন",
                "stage": stage_key,
                "stage_label_bn": STAGE_BANGLA_MAP.get(stage_key, "প্রসেসিং চলছে..."),
                "progress": prog,
                "progress_bn": f"{to_bangla_digits(prog)}%",
                "channel_name": j.get("channel_name") or primary_channel_name,
                "niche": primary_niche,
                "detail": f"কাজের পর্যায়: {STAGE_BANGLA_MAP.get(stage_key, stage_key)} | প্রগ্রেস: {prog}%",
            }
            break

    # 5. Upcoming Activities (পরবর্তী কার্যক্রমসমূহ & Countdown)
    all_slots = []
    topics_pool = []
    for ch in channels:
        st = store.get_channel_reel_settings(ch.get("id"))
        if st:
            slots = st.get("schedule_slots") or []
            for s in slots:
                if s not in all_slots:
                    all_slots.append(s)
            tp = st.get("topics_pool") or []
            for t in tp:
                if t not in topics_pool:
                    topics_pool.append(t)

    if not all_slots:
        all_slots = ["11:00", "16:00", "20:30"]

    all_slots_sorted = sorted(all_slots)

    # Find next upcoming slot
    now_mins = now.hour * 60 + now.minute
    next_slot_time_str = None
    next_slot_dt = None

    for slot in all_slots_sorted:
        parts = slot.split(":")
        s_h, s_m = int(parts[0]), int(parts[1])
        s_total = s_h * 60 + s_m
        if s_total > now_mins:
            next_slot_time_str = slot
            next_slot_dt = now.replace(hour=s_h, minute=s_m, second=0, microsecond=0)
            break

    # If all slots passed today, take first slot tomorrow
    if not next_slot_time_str and all_slots_sorted:
        first_slot = all_slots_sorted[0]
        parts = first_slot.split(":")
        s_h, s_m = int(parts[0]), int(parts[1])
        tomorrow = now + timedelta(days=1)
        next_slot_time_str = first_slot
        next_slot_dt = tomorrow.replace(hour=s_h, minute=s_m, second=0, microsecond=0)

    # Format slot in 12h
    def to_12h_format(slot_24: str) -> str:
        try:
            p = slot_24.split(":")
            h, m = int(p[0]), int(p[1])
            period = "AM" if h < 12 else "PM"
            h12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
            return f"{h12:02d}:{m:02d} {period}"
        except Exception:
            return slot_24

    slot_12h = to_12h_format(next_slot_time_str or "11:00")
    slot_12h_bn = to_bangla_digits(slot_12h).replace("AM", "সকাল/দুপুর").replace("PM", "বিকাল/রাত")

    countdown_sec = 0
    countdown_str_bn = "০ মিনিট"
    countdown_clock = "00:00:00"
    if next_slot_dt:
        diff = int((next_slot_dt - now).total_seconds())
        if diff > 0:
            countdown_sec = diff
            c_hrs = diff // 3600
            c_mins = (diff % 3600) // 60
            c_secs = diff % 60
            countdown_clock = f"{c_hrs:02d}:{c_mins:02d}:{c_secs:02d}"
            if c_hrs > 0:
                countdown_str_bn = f"{to_bangla_digits(c_hrs)} ঘণ্টা {to_bangla_digits(c_mins)} মিনিট"
            else:
                countdown_str_bn = f"{to_bangla_digits(c_mins)} মিনিট {to_bangla_digits(c_secs)} সেকেন্ড"

    upcoming_topic = topics_pool[0] if topics_pool else "AutoMovie Pro AI Video Creation & Faceless Income"

    upcoming_activities = {
        "next_slot_24h": next_slot_time_str,
        "next_slot_12h": slot_12h,
        "next_slot_bn": slot_12h_bn,
        "countdown_sec": countdown_sec,
        "countdown_clock": countdown_clock,
        "countdown_str_bn": countdown_str_bn,
        "target_platforms": "Facebook Reels & YouTube Shorts",
        "topic": upcoming_topic,
        "total_slots_today": len(all_slots_sorted),
        "all_slots_today": [to_12h_format(s) for s in all_slots_sorted],
    }

    # 6. Production & Engine Metrics (আজকের তৈরি ভিডিও ও স্বাস্থ্য)
    total_jobs_count = len(recent_jobs)
    videos_today_count = 0
    for j in recent_jobs:
        c_at = str(j.get("created_at") or "")
        if c_at.startswith(today_str):
            videos_today_count += 1

    engine_metrics = {
        "server_status": "ONLINE",
        "server_port": 8787,
        "uptime_str": f"{uptime_hours:02d}h {uptime_mins:02d}m",
        "uptime_bn": f"{to_bangla_digits(uptime_hours)} ঘণ্টা {to_bangla_digits(uptime_mins)} মিনিট",
        "cpu_percent": cpu_pct,
        "cpu_percent_bn": f"{to_bangla_digits(cpu_pct)}%",
        "ram_percent": ram_pct,
        "ram_percent_bn": f"{to_bangla_digits(ram_pct)}%",
        "videos_today": videos_today_count,
        "videos_today_bn": f"{to_bangla_digits(videos_today_count)} টি",
        "total_channels": total_channels,
        "total_channels_bn": f"{to_bangla_digits(total_channels)} টি",
        "scheduler_active": True,
    }

    # Widget Process Info
    is_running, pid = is_widget_running()

    return {
        "ok": True,
        "timestamp": now.isoformat(),
        "widget_running": is_running,
        "widget_pid": pid,
        "current_activity": active_activity,
        "upcoming_activities": upcoming_activities,
        "engine_metrics": engine_metrics,
    }


def launch_dashboard_window() -> bool:
    """Invokes launcher script to restore or open the native AutoMovie Pro desktop window."""
    pyw = get_pythonw_path()
    DETACHED_FLAGS = 0x08000000 | 0x00000200
    try:
        subprocess.Popen(
            [pyw, str(LAUNCHER_SCRIPT)],
            cwd=str(ROOT_DIR),
            creationflags=DETACHED_FLAGS if sys.platform == "win32" else 0,
            close_fds=True,
        )
        return True
    except Exception:
        return False
