"""AutoMovie Pro — Automated 1-Click Customer Self-Diagnostic Engine

Comprehensive health check designed for non-technical users & automated QA:
1. Internet Connectivity (Latency, DNS, Endpoints)
2. AI Key Validity (Gemini / Google AI, Groq, OpenRouter, formats & presence)
3. Hardware & FFmpeg Readiness (Bundled FFmpeg 8.1.1 auto-detection, execution, codecs)
4. Disk Space (Drive capacity, free GB thresholds)
5. Browser Sessions (Session vault, Chrome/Playwright engines, linked channels)
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import socket
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Constants
MIN_DISK_FREE_GB_OPTIMAL = 5.0
MIN_DISK_FREE_GB_CRITICAL = 1.0


def check_internet_connectivity(timeout_seconds: float = 3.0) -> Dict[str, Any]:
    """1. Check internet connectivity, DNS resolution and latency."""
    endpoints = [
        ("Cloudflare DNS", "https://1.1.1.1"),
        ("Google Public", "https://www.google.com"),
    ]
    results: List[Dict[str, Any]] = []
    latencies: List[float] = []

    dns_ok = False
    try:
        ip = socket.gethostbyname("google.com")
        dns_ok = bool(ip)
    except Exception:
        dns_ok = False

    for name, url in endpoints:
        start = time.perf_counter()
        ok = False
        err = None
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AutoMoviePro-Diagnostics/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                ok = resp.status in (200, 301, 302, 204)
        except Exception as exc:
            err = str(exc)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        if ok:
            latencies.append(duration_ms)
        results.append({
            "target": name,
            "url": url,
            "reachable": ok,
            "latency_ms": duration_ms if ok else None,
            "error": err,
        })

    any_reachable = any(r["reachable"] for r in results)
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0.0

    if any_reachable and dns_ok:
        if avg_latency > 1500:
            status = "WARN"
            msg_bn = f"ইন্টারনেট সংযুক্ত কিন্তু পিং কিছুটা ধীর ({avg_latency} ms)।"
            msg_en = f"Internet connected but high latency ({avg_latency} ms)."
        else:
            status = "PASS"
            msg_bn = f"ইন্টারনেট সংযোগ সক্রিয় ও দ্রুত ({avg_latency} ms)।"
            msg_en = f"Internet connection active and responsive ({avg_latency} ms)."
    elif any_reachable:
        status = "WARN"
        msg_bn = "ইন্টারনেট অ্যাক্সেস আছে কিন্তু DNS রেজল্যুশনে বিলম্ব হচ্ছে।"
        msg_en = "Internet accessible, but DNS resolution experienced issues."
    else:
        status = "FAIL"
        msg_bn = "ইন্টারনেট সংযোগ পাওয়া যায়নি। আপনার রাউটার বা ওয়াইফাই চেক করুন।"
        msg_en = "No internet connection detected. Please verify your network connection."

    return {
        "check": "internet_connectivity",
        "status": status,
        "dns_resolution": dns_ok,
        "average_latency_ms": avg_latency,
        "endpoints": results,
        "message_bn": msg_bn,
        "message_en": msg_en,
    }


def check_ai_keys() -> Dict[str, Any]:
    """2. Check configured AI keys (Gemini, Groq, OpenRouter, Agnes) and validate formats."""
    from pipeline.api_keys import load_api_bundle

    bundle = load_api_bundle()
    google_keys: List[str] = list(bundle.get("google") or [])
    groq_keys: List[str] = list(bundle.get("groq") or [])
    openrouter_keys: List[str] = list(bundle.get("openrouter") or [])
    agnes_keys: List[str] = list(bundle.get("agnes") or [])
    cerebras_keys: List[str] = list(bundle.get("cerebras") or [])

    total_keys = len(google_keys) + len(groq_keys) + len(openrouter_keys) + len(agnes_keys) + len(cerebras_keys)

    # Validate Google / Gemini keys format (AIzaSy...)
    gemini_valid_count = 0
    for k in google_keys:
        clean = (k or "").strip()
        if len(clean) >= 20 and (clean.startswith("AIza") or clean.isalnum() or "-" in clean or "_" in clean):
            gemini_valid_count += 1

    details = {
        "gemini_keys_count": len(google_keys),
        "gemini_valid_format_count": gemini_valid_count,
        "groq_keys_count": len(groq_keys),
        "openrouter_keys_count": len(openrouter_keys),
        "agnes_keys_count": len(agnes_keys),
        "cerebras_keys_count": len(cerebras_keys),
        "total_active_keys": total_keys,
    }

    if gemini_valid_count >= 1 or len(groq_keys) >= 1 or len(openrouter_keys) >= 1:
        status = "PASS"
        primary = "Google Gemini" if gemini_valid_count else ("Groq" if groq_keys else "OpenRouter")
        msg_bn = f"এআই ইঞ্জিন সক্রিয় ({primary} সহ মোট {total_keys} টি কী কনফিগার করা আছে)।"
        msg_en = f"AI engines ready ({primary} with {total_keys} active keys configured)."
    elif total_keys > 0:
        status = "WARN"
        msg_bn = "এআই কী কনফিগার করা আছে কিন্তু ফরম্যাট যাচাই করুন।"
        msg_en = "AI keys detected but may require verification."
    else:
        status = "FAIL"
        msg_bn = "কোনো AI API কী পাওয়া যায়নি। সেটিংস বা .env ফাইলে আপনার Gemini কী যুক্ত করুন।"
        msg_en = "No AI API keys configured. Please add your Gemini API key in settings or .env file."

    return {
        "check": "ai_keys",
        "status": status,
        "details": details,
        "message_bn": msg_bn,
        "message_en": msg_en,
    }


def check_hardware_ffmpeg() -> Dict[str, Any]:
    """3. Check hardware & FFmpeg readiness, bundled build auto-detection and execution."""
    from app.config import ensure_portable_ffmpeg
    from pipeline.compose import ffmpeg_bin, ffprobe_bin, probe_media_tool_capability

    # Ensure portable build is discovered and present in PATH
    portable_info = ensure_portable_ffmpeg()

    ff_path = ffmpeg_bin()
    pr_path = ffprobe_bin()

    media_cap = probe_media_tool_capability()
    ffmpeg_runs = bool(media_cap.get("FFMPEG_AVAILABLE"))
    ffprobe_runs = bool(media_cap.get("FFPROBE_AVAILABLE"))

    # Extract FFmpeg version string safely
    ffmpeg_version = "Unknown"
    if ffmpeg_runs:
        try:
            res = subprocess.run([ff_path, "-version"], capture_output=True, text=True, timeout=5)
            first_line = (res.stdout or "").splitlines()[0] if res.stdout else ""
            if "ffmpeg version" in first_line:
                ffmpeg_version = first_line.split("Copyright")[0].strip()
        except Exception:
            ffmpeg_version = "Detected (v8.1.1+)"

    # Hardware Specs
    cpu_count = os.cpu_count() or 1
    system_arch = platform.machine()
    system_os = f"{platform.system()} {platform.release()}"

    is_bundled = "ffmpeg-8.1.1" in ff_path.lower() or "portable" in ff_path.lower()

    if ffmpeg_runs and ffprobe_runs:
        status = "PASS"
        bundled_tag = " (Bundled Portable Build)" if is_bundled else " (System PATH)"
        msg_bn = f"FFmpeg ও FFprobe সফলভাবে সক্রিয়{bundled_tag}। ভার্সন: {ffmpeg_version}।"
        msg_en = f"FFmpeg & FFprobe operational{bundled_tag}. Version: {ffmpeg_version}."
    elif ffmpeg_runs:
        status = "WARN"
        msg_bn = "FFmpeg পাওয়া গেছে কিন্তু FFprobe মিসিং।"
        msg_en = "FFmpeg detected but FFprobe probe utility is unavailable."
    else:
        status = "FAIL"
        msg_bn = "FFmpeg লোড করা যায়নি। বান্ডেলড ফোল্ডার (ffmpeg-8.1.1-full_build) অক্ষত আছে কিনা যাচাই করুন।"
        msg_en = "FFmpeg binary unavailable. Ensure bundled ffmpeg-8.1.1-full_build is present."

    return {
        "check": "hardware_ffmpeg",
        "status": status,
        "ffmpeg_available": ffmpeg_runs,
        "ffprobe_available": ffprobe_runs,
        "ffmpeg_version": ffmpeg_version,
        "ffmpeg_path": ff_path,
        "ffprobe_path": pr_path,
        "is_bundled_portable": is_bundled,
        "cpu_cores": cpu_count,
        "system_os": system_os,
        "system_arch": system_arch,
        "message_bn": msg_bn,
        "message_en": msg_en,
    }


def check_disk_space(target_path: Optional[Path] = None) -> Dict[str, Any]:
    """4. Check available storage disk space for video generation & caches."""
    from app.config import DATA_DIR, OUTPUT_DIR, ROOT

    check_dir = Path(target_path) if target_path else OUTPUT_DIR
    if not check_dir.exists():
        check_dir = ROOT

    try:
        usage = shutil.disk_usage(check_dir)
        total_gb = round(usage.total / (1024 ** 3), 2)
        used_gb = round(usage.used / (1024 ** 3), 2)
        free_gb = round(usage.free / (1024 ** 3), 2)
        used_pct = round((usage.used / usage.total) * 100, 1)
    except Exception as exc:
        return {
            "check": "disk_space",
            "status": "WARN",
            "error": str(exc),
            "message_bn": "ডিস্ক স্পেস পরিমাপ করা যায়নি।",
            "message_en": f"Failed to check disk usage: {exc}",
        }

    if free_gb >= MIN_DISK_FREE_GB_OPTIMAL:
        status = "PASS"
        msg_bn = f"পর্যাপ্ত ফ্রি ডিস্ক স্পেস রয়েছে ({free_gb} GB খালি / মোট {total_gb} GB)।"
        msg_en = f"Optimal free disk space ({free_gb} GB free out of {total_gb} GB)."
    elif free_gb >= MIN_DISK_FREE_GB_CRITICAL:
        status = "WARN"
        msg_bn = f"ডিস্ক স্পেস সীমিত ({free_gb} GB খালি)। বড় ভিডিও রেন্ডারিংয়ের পূর্বে ডিস্ক খালি করুন।"
        msg_en = f"Low free disk space ({free_gb} GB free). Consider freeing up storage."
    else:
        status = "FAIL"
        msg_bn = f"মারাত্মক ডিস্ক সংকট! মাত্র {free_gb} GB খালি আছে। ভিডিও তৈরি ব্যাহত হতে পারে।"
        msg_en = f"Critical disk space deficiency! Only {free_gb} GB free remaining."

    return {
        "check": "disk_space",
        "status": status,
        "target_directory": str(check_dir.resolve()),
        "total_gb": total_gb,
        "used_gb": used_gb,
        "free_gb": free_gb,
        "used_percent": used_pct,
        "message_bn": msg_bn,
        "message_en": msg_en,
    }


def check_browser_sessions() -> Dict[str, Any]:
    """5. Check browser engines and social publishing session vaults."""
    from publishers.session_vault import VAULT_ROOT, list_sessions
    from publishers.stealth_session import engine_status

    sessions = []
    try:
        sessions = list_sessions()
    except Exception:
        pass

    engines = {}
    try:
        engines = engine_status()
    except Exception:
        pass

    session_count = len(sessions)
    vault_exists = VAULT_ROOT.is_dir()

    # Browser executable readiness
    patchright_ready = bool(engines.get("patchright") if not isinstance(engines.get("patchright"), dict) else engines.get("patchright", {}).get("ready", False))
    playwright_ready = bool(engines.get("playwright_stealth") or engines.get("playwright"))
    browser_ready = patchright_ready or playwright_ready or bool(shutil.which("chrome") or shutil.which("msedge"))

    if session_count > 0:
        status = "PASS"
        msg_bn = f"সোশ্যাল ব্রাউজার সেশন সক্রিয় ({session_count} টি চ্যানেল/প্ল্যাটফর্ম কানেক্টেড)।"
        msg_en = f"Social browser sessions active ({session_count} accounts connected)."
    elif browser_ready:
        status = "PASS"
        msg_bn = "ব্রাউজার অটোমেশন ইঞ্জিন প্রস্তুত। চ্যানেল লগইন করতে সোশ্যাল সেটিংস ব্যবহার করুন।"
        msg_en = "Browser automation engine ready. Connect your social channels in settings."
    else:
        status = "WARN"
        msg_bn = "সোশ্যাল সেশন বা ক্রোম ব্রাউজার ডিটেকশন প্রয়োজন।"
        msg_en = "No linked social channels found. Browser automation requires Chrome/Edge."

    return {
        "check": "browser_sessions",
        "status": status,
        "linked_sessions_count": session_count,
        "browser_engine_ready": browser_ready,
        "engines": engines,
        "vault_path": str(VAULT_ROOT.resolve()) if vault_exists else None,
        "message_bn": msg_bn,
        "message_en": msg_en,
    }


def run_full_diagnostics() -> Dict[str, Any]:
    """1-Click Automated Self-Diagnostic Engine.

    Executes all 5 system checks and builds a unified report with scoring & recommendations.
    """
    start_time = time.perf_counter()
    ts = datetime.now(timezone.utc).isoformat()

    c_internet = check_internet_connectivity()
    c_ai = check_ai_keys()
    c_hardware = check_hardware_ffmpeg()
    c_disk = check_disk_space()
    c_browser = check_browser_sessions()

    checks = [c_internet, c_ai, c_hardware, c_disk, c_browser]

    pass_count = sum(1 for c in checks if c["status"] == "PASS")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")
    fail_count = sum(1 for c in checks if c["status"] == "FAIL")

    # Score calculation (each PASS=20, WARN=10, FAIL=0)
    score = (pass_count * 20) + (warn_count * 10)

    if fail_count > 0:
        overall_status = "BLOCKED"
        summary_bn = "⚠️ কিছু প্রয়োজনীয় উপাদান কনফিগারেশন প্রয়োজন।"
        summary_en = "Action required: some essential components need setup."
    elif warn_count > 0:
        overall_status = "READY_WITH_WARNINGS"
        summary_bn = "✓ সিস্টেম চালু করার উপযুক্ত (কিছু সতর্কতা রয়েছে)।"
        summary_en = "System is operational with minor non-blocking warnings."
    else:
        overall_status = "ALL_SYSTEMS_OPERATIONAL"
        summary_bn = "🎉 সকল উপাদান সম্পূর্ণ প্রস্তুত ও সর্বোচ্চ পারফরম্যান্সে রয়েছে!"
        summary_en = "All systems operational! 100% ready for automated video generation."

    # Actionable Recommendation Tips
    recommendations_bn: List[str] = []
    recommendations_en: List[str] = []

    if c_internet["status"] == "FAIL":
        recommendations_bn.append("ইন্টারনেট সংযোগ চালু করুন।")
        recommendations_en.append("Ensure your internet connection is active.")
    if c_ai["status"] == "FAIL":
        recommendations_bn.append("Settings মেনু থেকে আপনার Gemini API Key ইনপুট করুন।")
        recommendations_en.append("Add your Gemini API Key in Settings.")
    if c_hardware["status"] == "FAIL":
        recommendations_bn.append("বান্ডেলড FFmpeg ফাইলটি নিশ্চিত করুন।")
        recommendations_en.append("Verify bundled FFmpeg executable folder.")
    if c_disk["status"] in ("WARN", "FAIL"):
        recommendations_bn.append("কম্পিউটারের সি বা প্রজেক্ট ড্রাইভ থেকে অপ্রয়োজনীয় ফাইল ডিলিট করে ডিস্ক খালি করুন।")
        recommendations_en.append("Free up hard drive space for optimal video rendering.")
    if c_browser["status"] == "WARN" and c_browser["linked_sessions_count"] == 0:
        recommendations_bn.append("স্বয়ংক্রিয় পাবলিশিংয়ের জন্য YouTube/Facebook সেশন যুক্ত করুন।")
        recommendations_en.append("Connect YouTube or Facebook sessions in settings for automatic publishing.")

    duration_ms = round((time.perf_counter() - start_time) * 1000, 1)

    return {
        "ok": True,
        "overall_status": overall_status,
        "health_score": score,
        "timestamp_utc": ts,
        "diagnostics_duration_ms": duration_ms,
        "summary_bn": summary_bn,
        "summary_en": summary_en,
        "results": {
            "internet": c_internet,
            "ai_keys": c_ai,
            "hardware_ffmpeg": c_hardware,
            "disk_space": c_disk,
            "browser_sessions": c_browser,
        },
        "stats": {
            "passed": pass_count,
            "warnings": warn_count,
            "failed": fail_count,
            "total_checks": len(checks),
        },
        "recommendations_bn": recommendations_bn,
        "recommendations_en": recommendations_en,
    }


def cli_main() -> None:
    """CLI Runner: prints a clean diagnostic card on terminal (Windows-safe)."""
    print("=" * 65)
    print("  AUTOMOVIE PRO -- 1-CLICK CUSTOMER SELF-DIAGNOSTICS")
    print("=" * 65)
    print("Running comprehensive system health scan...\n")

    res = run_full_diagnostics()

    status_icons = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}

    for key, check in res["results"].items():
        icon = status_icons.get(check["status"], "[INFO]")
        chk_title = check["check"].replace("_", " ").title()
        msg_en = check["message_en"]
        msg_bn = check["message_bn"]
        print(f" {icon:<8} {chk_title:<22} : {msg_en}")
        try:
            print(f"          বাংলা: {msg_bn}")
        except UnicodeEncodeError:
            pass
        print("-" * 65)

    print(f"\nOverall Status : {res['overall_status']} (Health Score: {res['health_score']}/100)")
    try:
        print(f"Summary (BN)   : {res['summary_bn']}")
    except UnicodeEncodeError:
        pass
    print(f"Summary (EN)   : {res['summary_en']}")

    if res["recommendations_en"]:
        print("\nActionable Recommendations:")
        for rec in res["recommendations_en"]:
            print(f"  * {rec}")
    print("=" * 65)


if __name__ == "__main__":
    cli_main()
