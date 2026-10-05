"""
Customer first-run / install bootstrap — auto-download & install external tools.

Runs from:
  - START.bat  →  python -m app.bootstrap_runtime
  - app.main startup (background if already mostly ready; sync on first run)
  - POST /api/bootstrap/run

Idempotent: writes data/bootstrap/runtime_tools.json marker.
Heavy steps skip when marker version matches and probes pass (unless --force).

Tools covered
-------------
1) Pip packages: edge-tts, camoufox, playwright(+stealth), faster-whisper,
   scenedetect, arabic-reshaper, python-bidi, Pillow
2) Playwright Chromium browser binary → data/playwright_browsers
3) Camoufox browser fetch (`python -m camoufox fetch`)
4) FFmpeg/ffprobe — prefer bundled; else download portable essentials into tools/ffmpeg
5) Faster-Whisper ASR model prefetch (tiny, default speech observer)

Optional (not auto-downloaded — user/PATH):
  - Piper TTS CLI/model (offline TTS slot only; Edge-TTS is primary)
  - FFmpeg full build with libvmaf (essentials zip has no VMAF; UNKNOWN ≠ PASS)

Env
---
AMP_BOOTSTRAP_SKIP=1          disable entirely
AMP_BOOTSTRAP_FORCE=1         ignore marker, re-run
AMP_BOOTSTRAP_SKIP_CAMOUFOX=1 skip camoufox fetch
AMP_BOOTSTRAP_SKIP_FFMPEG=1   skip ffmpeg download
AMP_BOOTSTRAP_SKIP_WHISPER=1  skip whisper model prefetch
AMP_BOOTSTRAP_SYNC=1          startup must run sync (block until done)
AMP_WHISPER_MODEL=tiny        model size to prefetch (default tiny)
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import urlretrieve

logger = logging.getLogger(__name__)

BOOTSTRAP_VERSION = 3

# Packages customers need beyond a bare venv (also listed in requirements.txt).
BOOTSTRAP_PIP: Tuple[str, ...] = (
    "edge-tts>=6.1.0",
    "camoufox>=0.4.0",
    "playwright==1.61.0",
    "playwright-stealth==1.0.6",
    "faster-whisper>=1.0.0",
    "scenedetect[opencv]>=0.6.0",
    "arabic-reshaper>=3.0.0",
    "python-bidi>=0.4.2",
    "Pillow==11.3.0",
)

# Portable FFmpeg essentials (Windows x64) — used only if no bundled/PATH ffmpeg.
FFMPEG_ZIP_URL = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
)


def _root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _data_dir() -> Path:
    try:
        from app.config import DATA_DIR

        d = Path(DATA_DIR)
    except Exception:
        d = _root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _marker_path() -> Path:
    p = _data_dir() / "bootstrap"
    p.mkdir(parents=True, exist_ok=True)
    return p / "runtime_tools.json"


def _log_path() -> Path:
    return _data_dir() / "bootstrap" / "bootstrap.log"


def _append_log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}\n"
    try:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    logger.info("%s", msg)


def apply_runtime_env() -> None:
    """Point the running process at customer-local browser/ffmpeg trees."""
    browsers = _data_dir() / "playwright_browsers"
    browsers.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    ff_root = _root() / "tools" / "ffmpeg"
    if (ff_root / "bin").is_dir() or any(ff_root.rglob("ffmpeg.exe")) or any(
        ff_root.rglob("ffmpeg")
    ):
        os.environ.setdefault("AMP_FFMPEG_ROOT", str(ff_root))
        bin_dir = ff_root / "bin"
        if bin_dir.is_dir():
            path = os.environ.get("PATH") or ""
            prefix = str(bin_dir)
            if prefix.lower() not in path.lower():
                os.environ["PATH"] = prefix + os.pathsep + path


def _py() -> str:
    return sys.executable


def _run(
    cmd: List[str],
    *,
    timeout: int = 600,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str]:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged,
            cwd=str(_root()),
        )
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        return int(proc.returncode), out[-4000:]
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as exc:
        return 1, str(exc)


def _load_marker() -> Dict[str, Any]:
    path = _marker_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_marker(payload: Dict[str, Any]) -> None:
    payload = dict(payload)
    payload["version"] = BOOTSTRAP_VERSION
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _marker_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- steps
def ensure_pip_packages(*, force: bool = False) -> Dict[str, Any]:
    if getattr(sys, "frozen", False):
        return {"ok": True, "skipped": True, "reason": "frozen_bundle"}
    missing: List[str] = []
    for spec in BOOTSTRAP_PIP:
        name = spec.split(">=")[0].split("==")[0].split("[")[0].strip()
        mod = {
            "edge-tts": "edge_tts",
            "playwright-stealth": "playwright_stealth",
            "camoufox": "camoufox",
            "playwright": "playwright",
            "faster-whisper": "faster_whisper",
            "scenedetect": "scenedetect",
            "arabic-reshaper": "arabic_reshaper",
            "python-bidi": "bidi",
            "Pillow": "PIL",
        }.get(name, name.replace("-", "_"))
        try:
            __import__(mod)
        except Exception:
            missing.append(spec)
    if not missing and not force:
        return {"ok": True, "installed": [], "already_ok": True}
    to_install = list(BOOTSTRAP_PIP) if force else missing
    if not to_install:
        return {"ok": True, "installed": []}
    _append_log(f"pip install: {to_install}")
    code, out = _run([_py(), "-m", "pip", "install", "--upgrade", *to_install], timeout=900)
    return {"ok": code == 0, "installed": to_install, "exit": code, "log": out[-800:]}


def ensure_playwright_chromium(*, force: bool = False) -> Dict[str, Any]:
    # Point browsers into customer data when frozen / shared machines
    browsers_path = _data_dir() / "playwright_browsers"
    browsers_path.mkdir(parents=True, exist_ok=True)
    env = {"PLAYWRIGHT_BROWSERS_PATH": str(browsers_path)}
    # Probe
    if not force:
        code, out = _run(
            [_py(), "-c", "from playwright.sync_api import sync_playwright;\n"
             "p=sync_playwright().start();\n"
             "b=p.chromium.launch(headless=True);\n"
             "b.close(); p.stop(); print('ok')"],
            timeout=120,
            env=env,
        )
        if code == 0 and "ok" in out:
            return {"ok": True, "already_ok": True, "browsers_path": str(browsers_path)}
    _append_log("playwright install chromium …")
    code, out = _run(
        [_py(), "-m", "playwright", "install", "chromium"],
        timeout=1200,
        env=env,
    )
    # Also install OS deps where supported (no-op / fail soft on Windows)
    _run([_py(), "-m", "playwright", "install-deps", "chromium"], timeout=300, env=env)
    return {
        "ok": code == 0,
        "exit": code,
        "browsers_path": str(browsers_path),
        "log": out[-800:],
    }


def ensure_camoufox(*, force: bool = False) -> Dict[str, Any]:
    if (os.environ.get("AMP_BOOTSTRAP_SKIP_CAMOUFOX") or "").strip() in ("1", "true", "yes"):
        return {"ok": True, "skipped": True}
    try:
        import camoufox  # noqa: F401
    except Exception as exc:
        # Try pip once more
        _run([_py(), "-m", "pip", "install", "--upgrade", "camoufox>=0.4.0"], timeout=600)
        try:
            import camoufox  # noqa: F401
        except Exception as exc2:
            return {"ok": False, "error": f"camoufox_import:{exc2}", "prior": str(exc)}

    marker = _data_dir() / "bootstrap" / "camoufox_fetched.flag"
    if marker.is_file() and not force:
        return {"ok": True, "already_ok": True}
    _append_log("camoufox fetch (browser download) …")
    code, out = _run([_py(), "-m", "camoufox", "fetch"], timeout=1800)
    if code == 0:
        try:
            marker.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        except Exception:
            pass
    return {"ok": code == 0, "exit": code, "log": out[-800:]}


def _ffmpeg_ok() -> bool:
    try:
        from pipeline.compose import ffmpeg_bin, ffprobe_bin

        ff = ffmpeg_bin()
        fp = ffprobe_bin()
        if not ff or not fp:
            return False
        c1, _ = _run([ff, "-version"], timeout=20)
        c2, _ = _run([fp, "-version"], timeout=20)
        return c1 == 0 and c2 == 0
    except Exception:
        return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def ensure_ffmpeg(*, force: bool = False) -> Dict[str, Any]:
    if (os.environ.get("AMP_BOOTSTRAP_SKIP_FFMPEG") or "").strip() in ("1", "true", "yes"):
        return {"ok": True, "skipped": True}
    if _ffmpeg_ok() and not force:
        return {"ok": True, "already_ok": True, "source": "bundled_or_path"}

    dest = _root() / "tools" / "ffmpeg"
    dest.mkdir(parents=True, exist_ok=True)
    # If tools/ffmpeg already has binaries, done
    hits = list(dest.rglob("ffmpeg.exe")) + list(dest.rglob("ffmpeg"))
    if hits and not force:
        return {"ok": True, "already_ok": True, "path": str(hits[0])}

    zip_path = _data_dir() / "bootstrap" / "ffmpeg-essentials.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    _append_log(f"Downloading FFmpeg essentials → {zip_path}")
    try:
        urlretrieve(FFMPEG_ZIP_URL, str(zip_path))
    except Exception as exc:
        return {
            "ok": False,
            "error": f"ffmpeg_download_failed:{exc}",
            "hint": "Place ffmpeg.exe under tools/ffmpeg/bin or set AMP_FFMPEG_BIN",
        }

    extract_to = _data_dir() / "bootstrap" / "ffmpeg_extract"
    if extract_to.exists():
        shutil.rmtree(extract_to, ignore_errors=True)
    extract_to.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_to)
    except Exception as exc:
        return {"ok": False, "error": f"ffmpeg_unzip_failed:{exc}"}

    # Move bin/* into tools/ffmpeg/bin
    bin_src = None
    for p in extract_to.rglob("ffmpeg.exe"):
        bin_src = p.parent
        break
    if not bin_src:
        for p in extract_to.rglob("ffmpeg"):
            if p.is_file():
                bin_src = p.parent
                break
    if not bin_src:
        return {"ok": False, "error": "ffmpeg_bin_not_in_zip"}

    target_bin = dest / "bin"
    target_bin.mkdir(parents=True, exist_ok=True)
    for item in bin_src.iterdir():
        tgt = target_bin / item.name
        if item.is_file():
            shutil.copy2(item, tgt)

    ok = _ffmpeg_ok()
    return {
        "ok": ok,
        "path": str(target_bin),
        "source": "downloaded_essentials",
    }


def ensure_whisper_model(*, force: bool = False) -> Dict[str, Any]:
    """Prefetch faster-whisper weights so first ASR job is not cold-start."""
    if (os.environ.get("AMP_BOOTSTRAP_SKIP_WHISPER") or "").strip() in ("1", "true", "yes"):
        return {"ok": True, "skipped": True}
    model_size = (os.environ.get("AMP_WHISPER_MODEL") or "tiny").strip() or "tiny"
    marker = _data_dir() / "bootstrap" / f"whisper_{model_size}.flag"
    if marker.is_file() and not force:
        return {"ok": True, "already_ok": True, "model": model_size}
    try:
        import faster_whisper  # noqa: F401
    except Exception as exc:
        return {"ok": False, "error": f"faster_whisper_missing:{exc}"}
    _append_log(f"faster-whisper prefetch model={model_size} …")
    code, out = _run(
        [
            _py(),
            "-c",
            (
                "from faster_whisper import WhisperModel\n"
                f"WhisperModel({model_size!r}, device='cpu', compute_type='int8')\n"
                "print('ok')\n"
            ),
        ],
        timeout=1800,
    )
    if code == 0 and "ok" in out:
        try:
            marker.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        except Exception:
            pass
        return {"ok": True, "model": model_size, "prefetched": True}
    return {"ok": False, "exit": code, "model": model_size, "log": out[-800:]}


def probe_optional_modules() -> Dict[str, Any]:
    status: Dict[str, Any] = {}
    for label, mod in (
        ("edge_tts", "edge_tts"),
        ("camoufox", "camoufox"),
        ("playwright", "playwright"),
        ("faster_whisper", "faster_whisper"),
        ("scenedetect", "scenedetect"),
        ("arabic_reshaper", "arabic_reshaper"),
        ("bidi", "bidi"),
        ("PIL", "PIL"),
    ):
        try:
            __import__(mod)
            status[label] = True
        except Exception:
            status[label] = False
    status["ffmpeg"] = _ffmpeg_ok()
    whisper_flag = _data_dir() / "bootstrap" / "whisper_tiny.flag"
    status["whisper_model_cached"] = whisper_flag.is_file()
    return status


def status() -> Dict[str, Any]:
    marker = _load_marker()
    return {
        "ok": True,
        "bootstrap_version": BOOTSTRAP_VERSION,
        "marker": marker,
        "probes": probe_optional_modules(),
        "marker_path": str(_marker_path()),
        "log_path": str(_log_path()),
        "running": _is_running(),
    }


_lock = threading.Lock()
_running = False
_last_result: Dict[str, Any] = {}


def _is_running() -> bool:
    return _running


def ensure_all(*, force: bool = False) -> Dict[str, Any]:
    """Run full customer tool bootstrap. Safe to call repeatedly."""
    global _running, _last_result
    if (os.environ.get("AMP_BOOTSTRAP_SKIP") or "").strip() in ("1", "true", "yes"):
        return {"ok": True, "skipped": True}
    force = force or (os.environ.get("AMP_BOOTSTRAP_FORCE") or "").strip() in (
        "1",
        "true",
        "yes",
    )

    with _lock:
        if _running:
            return {"ok": True, "already_running": True, "last": _last_result}
        _running = True

    t0 = time.time()
    results: Dict[str, Any] = {"version": BOOTSTRAP_VERSION, "steps": {}}
    try:
        apply_runtime_env()
        marker = _load_marker()
        if (
            not force
            and int(marker.get("version") or 0) >= BOOTSTRAP_VERSION
            and marker.get("ok")
            and _ffmpeg_ok()
        ):
            # Fast path — still refresh probes
            results["steps"]["fast_path"] = True
            results["probes"] = probe_optional_modules()
            results["ok"] = bool(results["probes"].get("ffmpeg"))
            results["elapsed_sec"] = round(time.time() - t0, 2)
            _last_result = results
            return results

        _append_log("=== bootstrap ensure_all start ===")
        results["steps"]["pip"] = ensure_pip_packages(force=force)
        results["steps"]["playwright"] = ensure_playwright_chromium(force=force)
        results["steps"]["camoufox"] = ensure_camoufox(force=force)
        results["steps"]["ffmpeg"] = ensure_ffmpeg(force=force)
        apply_runtime_env()  # pick up freshly installed ffmpeg/browsers
        results["steps"]["whisper"] = ensure_whisper_model(force=force)
        results["probes"] = probe_optional_modules()

        critical_ok = bool(results["probes"].get("ffmpeg")) and bool(
            results["steps"].get("playwright", {}).get("ok")
        )
        results["ok"] = critical_ok
        results["elapsed_sec"] = round(time.time() - t0, 2)
        _save_marker(
            {
                "ok": critical_ok,
                "results": {
                    k: {"ok": (v or {}).get("ok"), "skipped": (v or {}).get("skipped")}
                    for k, v in results["steps"].items()
                    if isinstance(v, dict)
                },
                "probes": results["probes"],
                "elapsed_sec": results["elapsed_sec"],
            }
        )
        _append_log(f"=== bootstrap done ok={critical_ok} elapsed={results['elapsed_sec']}s ===")
        _last_result = results
        return results
    finally:
        _running = False


def ensure_all_async(*, force: bool = False) -> None:
    """Fire-and-forget for app startup (non-blocking)."""

    def _job() -> None:
        try:
            ensure_all(force=force)
        except Exception as exc:
            _append_log(f"bootstrap async failed: {exc}")

    threading.Thread(target=_job, name="amp-bootstrap", daemon=True).start()


def maybe_run_on_startup() -> None:
    """Called from FastAPI startup — sync on first run, else background refresh."""
    if (os.environ.get("AMP_BOOTSTRAP_SKIP") or "").strip() in ("1", "true", "yes"):
        return
    apply_runtime_env()
    marker = _load_marker()
    first = int(marker.get("version") or 0) < BOOTSTRAP_VERSION or not marker.get("ok")
    sync = first or (os.environ.get("AMP_BOOTSTRAP_SYNC") or "").strip() in (
        "1",
        "true",
        "yes",
    )
    if sync:
        _append_log("startup bootstrap (sync first-run)")
        ensure_all(force=False)
    else:
        ensure_all_async(force=False)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="AutoMovie Pro customer tools bootstrap")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args(argv)
    if args.status:
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return 0
    result = ensure_all(force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
