"""Sector 6 Test Suite: Portable FFmpeg Loader & 1-Click Customer Self-Diagnostics."""
import os
import shutil
from pathlib import Path
import pytest


def test_portable_ffmpeg_loader():
    """Verify bundled FFmpeg 8.1.1 / local bin discovery and PATH auto-injection."""
    from pipeline.compose import ensure_portable_ffmpeg_in_path, ffmpeg_bin, ffprobe_bin
    from app.config import ensure_portable_ffmpeg

    # Run detection
    injected = ensure_portable_ffmpeg_in_path()
    assert injected is not None or shutil.which("ffmpeg") is not None, "Portable FFmpeg or system FFmpeg must be found"

    ff = ffmpeg_bin()
    pr = ffprobe_bin()
    assert Path(ff).is_file() or shutil.which("ffmpeg") is not None
    assert Path(pr).is_file() or shutil.which("ffprobe") is not None

    # Verify config helper
    info = ensure_portable_ffmpeg()
    assert info["ok"] is True
    assert info["in_path"] is True
    assert "ffmpeg" in info
    assert "ffprobe" in info


def test_portable_ffmpeg_path_injection_simulation(monkeypatch):
    """Simulate bare customer PC with empty PATH and ensure auto-injection works."""
    from pipeline.compose import ensure_portable_ffmpeg_in_path

    # Strip ffmpeg from PATH
    monkeypatch.setenv("PATH", "C:\\Windows\\System32;C:\\Windows")
    monkeypatch.delenv("AMP_FFMPEG_BIN", raising=False)
    monkeypatch.delenv("AMP_FFPROBE_BIN", raising=False)

    injected = ensure_portable_ffmpeg_in_path()
    assert injected is not None, "Should auto-detect bundled ffmpeg-8.1.1-full_build folder"
    assert injected in os.environ["PATH"], "Bundled directory must be injected into PATH"
    assert (Path(injected) / "ffmpeg.exe").is_file()


def test_check_internet_connectivity():
    from app.diagnostics.engine import check_internet_connectivity

    res = check_internet_connectivity()
    assert "status" in res
    assert res["status"] in ("PASS", "WARN", "FAIL")
    assert "average_latency_ms" in res
    assert "endpoints" in res
    assert "message_bn" in res
    assert "message_en" in res


def test_check_ai_keys():
    from app.diagnostics.engine import check_ai_keys

    res = check_ai_keys()
    assert "status" in res
    assert res["status"] in ("PASS", "WARN", "FAIL")
    assert "details" in res
    assert "total_active_keys" in res["details"]
    assert "message_bn" in res


def test_check_hardware_ffmpeg():
    from app.diagnostics.engine import check_hardware_ffmpeg

    res = check_hardware_ffmpeg()
    assert res["status"] in ("PASS", "WARN")
    assert res["ffmpeg_available"] is True
    assert res["ffprobe_available"] is True
    assert "ffmpeg_version" in res
    assert res["cpu_cores"] >= 1
    assert "message_bn" in res


def test_check_disk_space():
    from app.diagnostics.engine import check_disk_space

    res = check_disk_space()
    assert res["status"] in ("PASS", "WARN", "FAIL")
    assert res["total_gb"] > 0
    assert res["free_gb"] > 0
    assert 0 <= res["used_percent"] <= 100
    assert "message_bn" in res


def test_check_browser_sessions():
    from app.diagnostics.engine import check_browser_sessions

    res = check_browser_sessions()
    assert res["status"] in ("PASS", "WARN")
    assert "linked_sessions_count" in res
    assert "browser_engine_ready" in res
    assert "message_bn" in res


def test_run_full_diagnostics():
    from app.diagnostics import run_full_diagnostics

    res = run_full_diagnostics()
    assert res["ok"] is True
    assert "overall_status" in res
    assert 0 <= res["health_score"] <= 100
    assert "results" in res

    results = res["results"]
    assert "internet" in results
    assert "ai_keys" in results
    assert "hardware_ffmpeg" in results
    assert "disk_space" in results
    assert "browser_sessions" in results

    assert "recommendations_bn" in res
    assert "recommendations_en" in res
    assert res["stats"]["total_checks"] == 5


def test_api_diagnostics_endpoint():
    from app.main import api_diagnostics_run

    res = api_diagnostics_run()
    assert res["ok"] is True
    assert "overall_status" in res
    assert "health_score" in res
