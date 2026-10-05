#!/usr/bin/env python3
"""
Keep Chernobyl 30-train alive until 30/30.

- Prints diagnosis (quota, localization gaps, dead trainer)
- Restarts trainer if process died OR stuck sleeping forever
- Caps / resets poisoned quota streak so localization can retry
- Does NOT kill a healthy Agnes/TTS mid-clip

Run:  venv\\Scripts\\python.exe scripts\\chernobyl_keep_alive.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "output" / "Chernobyl_30_TrainCompare"
PROGRESS = OUT / "progress.json"
LOG = OUT / "keep_alive.log"
TRAIN = ROOT / "scripts" / "chernobyl_30_train.py"
PY = ROOT / "venv" / "Scripts" / "python.exe"
WATCHDOG = ROOT / "scripts" / "run_chernobyl_watchdog.ps1"
STATUS = OUT / "KEEP_ALIVE_STATUS.txt"

POLL_SEC = 90
STUCK_SLEEP_SEC = 700  # if log says sleeping remaining > this and no progress, bounce


def _log(msg: str) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _progress() -> Tuple[int, List[int]]:
    if not PROGRESS.exists():
        return 0, []
    try:
        raw = PROGRESS.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
        ids = [int(x) for x in (data.get("completed_ids") or [])]
        return len(ids), sorted(ids)
    except Exception:
        return 0, []


def _train_procs() -> List[Dict[str, Any]]:
    try:
        import wmi  # type: ignore

        c = wmi.WMI()
        out = []
        for p in c.Win32_Process(Name="python.exe"):
            cl = p.CommandLine or ""
            if "chernobyl_30_train.py" in cl:
                out.append(
                    {
                        "pid": int(p.ProcessId),
                        "ppid": int(p.ParentProcessId or 0),
                        "exe": p.ExecutablePath or "",
                        "cmd": cl,
                    }
                )
        return out
    except Exception:
        # Fallback: PowerShell
        ps = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -match 'chernobyl_30_train\\.py' } | "
            "ForEach-Object { \"$($_.ProcessId)|$($_.ParentProcessId)|$($_.ExecutablePath)\" }"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
        )
        out = []
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split("|", 2)
            if len(parts) >= 2:
                out.append(
                    {
                        "pid": int(parts[0]),
                        "ppid": int(parts[1]),
                        "exe": parts[2] if len(parts) > 2 else "",
                        "cmd": "",
                    }
                )
        return out


def _logical_alive(procs: List[Dict[str, Any]]) -> bool:
    return len(procs) > 0


def _watchdog_alive() -> bool:
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -match 'run_chernobyl_watchdog' } | "
        "Measure-Object | Select-Object -ExpandProperty Count"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
    )
    try:
        return int((r.stdout or "0").strip() or "0") > 0
    except Exception:
        return False


def _localization_gaps() -> List[str]:
    gaps = []
    for i in range(1, 31):
        d = OUT / f"clip_{i:02d}"
        if not d.exists():
            continue
        loc = d / "LOCALIZED"
        n = 0
        if loc.exists():
            for sub in loc.iterdir():
                if sub.is_dir() and (sub / "video.mp4").exists():
                    n += 1
        en = (d / "narration_en.txt").exists()
        # completed clips should aim for 6 langs; flag if <6 and has English master
        master = any(d.glob("scene_00_*.mp4"))
        if master and n < 6:
            gaps.append(f"clip_{i:02d}: loc_videos={n}/6 en_txt={en}")
        if not en and i >= 20:
            gaps.append(f"clip_{i:02d}: missing narration_en.txt")
    return gaps


def _quota_state() -> Dict[str, Any]:
    p = ROOT / "pipeline" / "quota_backoff_state.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _reset_poisoned_streak() -> None:
    p = ROOT / "pipeline" / "quota_backoff_state.json"
    state = _quota_state()
    streak = int(state.get("streak") or 0)
    if streak > 4:
        state["streak"] = 2
        state["last_hit_ts"] = time.time() - (25 * 60)  # almost out of 30m cool-down
        p.write_text(json.dumps(state, indent=2), encoding="utf-8")
        _log(f"Reset poisoned quota streak {streak} → 2 (allow retry soon)")


def _tail_log_issues() -> List[str]:
    log = OUT / "chernobyl30.log"
    if not log.exists():
        return ["no chernobyl30.log yet"]
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
    except Exception:
        return ["log read failed"]
    issues = []
    for ln in lines:
        low = ln.lower()
        if any(
            x in low
            for x in (
                "resource_exhausted",
                "429",
                "translation failed",
                "localization failed",
                "clip ",
                "failed",
                "sleeping",
                "cool-down",
                "unauthenticated",
            )
        ):
            if "http request" in low:
                continue
            issues.append(ln[-220:])
    # unique last few
    seen = set()
    out = []
    for x in reversed(issues):
        k = x[:80]
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
        if len(out) >= 12:
            break
    return list(reversed(out))


def _sleeping_remaining_from_log() -> int:
    log = OUT / "chernobyl30.log"
    if not log.exists():
        return 0
    try:
        # Only trust recent lines (avoid stale "sleeping remaining 10799s")
        mtime = log.stat().st_mtime
        if time.time() - mtime > 180:
            return 0
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
    except Exception:
        return 0
    import re

    for ln in reversed(lines):
        m = re.search(r"sleeping remaining (\d+)s", ln, re.I)
        if m:
            return int(m.group(1))
        m = re.search(r"Sleeping (\d+)s for google quota", ln, re.I)
        if m:
            return int(m.group(1))
    return 0


def _start_trainer() -> None:
    lock = OUT / "chernobyl.lock"
    if lock.exists():
        try:
            lock.unlink()
        except Exception:
            pass
    _reset_poisoned_streak()
    subprocess.Popen(
        [str(PY), str(TRAIN)],
        cwd=str(ROOT),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _log("Started chernobyl_30_train.py (venv)")


def _start_watchdog() -> None:
    if _watchdog_alive():
        return
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(WATCHDOG),
        ],
        cwd=str(ROOT),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _log("Started watchdog")


def _kill_trainers() -> None:
    for p in _train_procs():
        try:
            subprocess.run(
                ["taskkill", "/PID", str(p["pid"]), "/F"],
                capture_output=True,
            )
            _log(f"Killed trainer PID={p['pid']}")
        except Exception as exc:
            _log(f"kill failed {p['pid']}: {exc}")


def diagnose_and_print(done: int, ids: List[int]) -> Dict[str, Any]:
    procs = _train_procs()
    gaps = _localization_gaps()
    qs = _quota_state()
    sleep_rem = _sleeping_remaining_from_log()
    issues = _tail_log_issues()
    report = {
        "progress": f"{done}/30",
        "completed_ids": ids,
        "trainer_alive": _logical_alive(procs),
        "trainer_pids": [p["pid"] for p in procs],
        "watchdog": _watchdog_alive(),
        "quota_streak": qs.get("streak"),
        "sleep_remaining_hint_sec": sleep_rem,
        "localization_gaps": gaps[:20],
        "recent_log_issues": issues,
    }
    STATUS.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _log("=" * 60)
    _log(f"STATUS progress={done}/30 trainer={report['trainer_alive']} watchdog={report['watchdog']}")
    _log(f"quota_streak={report['quota_streak']} sleep_hint={sleep_rem}s")
    if gaps:
        _log("LOCALIZATION GAPS:")
        for g in gaps[:15]:
            _log("  - " + g)
    else:
        _log("LOCALIZATION GAPS: none detected among existing masters")
    if issues:
        _log("RECENT PROBLEMS:")
        for x in issues[-8:]:
            _log("  ! " + x)
    return report


def _try_relocalize_gaps(keys: List[str]) -> None:
    """Retry missing language packs without regenerating Agnes (API-light when quota recovers)."""
    if not keys:
        return
    from pipeline.localization import localize_master_clip

    for i in range(1, 31):
        d = OUT / f"clip_{i:02d}"
        en_txt = d / "narration_en.txt"
        if not en_txt.exists():
            continue
        loc = d / "LOCALIZED"
        n_ok = 0
        if loc.exists():
            n_ok = sum(
                1
                for sub in loc.iterdir()
                if sub.is_dir() and (sub / "video.mp4").exists()
            )
        if n_ok >= 6:
            continue
        marker = d / "scene_00_master_for_localize.txt"
        master = None
        if marker.exists():
            mp = Path(marker.read_text(encoding="utf-8").strip())
            if mp.exists():
                master = mp
        if master is None:
            cands = sorted(d.glob("scene_00_*_unpadded.mp4"), key=lambda p: p.stat().st_mtime)
            if not cands:
                cands = sorted(
                    [
                        p
                        for p in d.glob("scene_00_*.mp4")
                        if "tmp" not in p.name and "mux" not in p.name and "picture" not in p.name
                    ],
                    key=lambda p: p.stat().st_mtime,
                )
            master = cands[-1] if cands else None
        if master is None or not master.exists():
            continue
        audio = d / "narration_en_from_agnes.m4a"
        narration = en_txt.read_text(encoding="utf-8").strip()
        _log(f"Re-localize attempt clip_{i:02d} (have {n_ok}/6) master={master.name}")
        try:
            localize_master_clip(
                master_video=master,
                english_narration=narration,
                out_dir=loc,
                google_api_keys=keys,
                slug=f"clip_{i:02d}",
                size="1080x1920",
                english_audio=audio if audio.exists() else None,
            )
        except Exception as exc:
            _log(f"Re-localize clip_{i:02d} failed: {exc}")
            # one gap attempt per loop to avoid quota storm
            break


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    _log("Chernobyl keep-alive started")
    _start_watchdog()
    last_done, _ = _progress()
    keys: List[str] = []
    try:
        from pipeline.api_keys import load_api_bundle

        keys = list((load_api_bundle().get("google_keys") or []))
    except Exception as exc:
        _log(f"keys load failed: {exc}")

    loops = 0
    while True:
        done, ids = _progress()
        report = diagnose_and_print(done, ids)
        if done >= 30:
            # Final pass: try fill localization gaps
            _try_relocalize_gaps(keys)
            gaps = _localization_gaps()
            if not gaps:
                _log("ALL 30 CLIPS COMPLETED + localization OK — keep-alive exit")
                return 0
            _log(f"30/30 masters done but localization gaps remain: {len(gaps)}")
            # keep retrying localize every few loops
            if loops % 3 == 0:
                _try_relocalize_gaps(keys)
            time.sleep(POLL_SEC)
            loops += 1
            continue

        alive = report["trainer_alive"]
        sleep_rem = int(report.get("sleep_remaining_hint_sec") or 0)

        if not alive:
            _log("Trainer dead — restarting")
            _start_trainer()
            time.sleep(20)
        elif sleep_rem >= STUCK_SLEEP_SEC:
            _log(
                f"Trainer stuck in long quota sleep (~{sleep_rem}s) — "
                "bounce with capped cool-down so work continues"
            )
            _kill_trainers()
            time.sleep(3)
            _start_trainer()
            time.sleep(20)
        elif done > last_done:
            _log(f"Progress advanced {last_done} → {done}")
            last_done = done
            # After each new clip, try fill older localization gaps once
            _try_relocalize_gaps(keys)

        if loops % 5 == 0:
            _try_relocalize_gaps(keys)

        time.sleep(POLL_SEC)
        loops += 1


if __name__ == "__main__":
    raise SystemExit(main())
