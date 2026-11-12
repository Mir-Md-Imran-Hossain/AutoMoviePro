"""Automated Storage Janitor Agent (StorageJanitorAgent)
Autonomous background cache & scratch purger for AutoMovie Pro.

Responsibilities:
1. Cleans orphaned FFmpeg assembly scratch folders (AppData/Local/Temp/am_assembly_*).
2. Cleans transient render scratch files (> TTL, default 24h).
3. Purges 0-byte ghost databases and dead test files.
4. Preserves STRICT WHITELIST:
   - User exported master videos in output/
   - SQLite databases (local.db)
   - Configuration (.env)
   - Golden test fixtures (job2108)
   - Fonts and assets
5. Supports:
   - On-startup sweep (sweep_on_startup)
   - Daily scheduled background daemon (start_background_janitor_daemon)
   - Manual one-click sweep (run_janitor_sweep)
"""

from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("StorageJanitor")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s][StorageJanitor][%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Strict Preservation Whitelist
PROTECTED_PATTERNS = [
    "job2108",
    "local.db",
    ".env",
    "assets",
    "models",
    "master_category_",
    "master_",
]


class StorageJanitorAgent:
    _instance: Optional["StorageJanitorAgent"] = None
    _lock = threading.Lock()

    def __init__(self, root_dir: Optional[str] = None) -> None:
        if root_dir:
            self.root = Path(root_dir).resolve()
        else:
            self.root = Path(__file__).resolve().parent.parent

        self.history_file = self.root / "data" / "storage_janitor_history.json"
        self._daemon_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @classmethod
    def get_instance(cls, root_dir: Optional[str] = None) -> "StorageJanitorAgent":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(root_dir)
            return cls._instance

    def _is_protected(self, path_str: str) -> bool:
        p_norm = path_str.replace("\\", "/").lower()
        for prot in PROTECTED_PATTERNS:
            if prot.lower() in p_norm:
                return True
        return False

    def sweep_temp_assemblies(self, max_age_hours: float = 2.0) -> Dict[str, Any]:
        """Purge orphaned am_assembly_* and am_render_* directories in Windows temp."""
        tmp = Path(tempfile.gettempdir())
        reclaimed_bytes = 0
        purged_items: List[str] = []
        now = time.time()
        cutoff_sec = max_age_hours * 3600.0

        for pattern in ["am_assembly_*", "am_render_*", "am_stitched_*"]:
            for item in tmp.glob(pattern):
                try:
                    mtime = item.stat().st_mtime
                    age_sec = now - mtime
                    # Only delete if older than cutoff or explicitly orphaned
                    if age_sec >= cutoff_sec:
                        item_size = 0
                        if item.is_dir():
                            for root, _, files in os.walk(item):
                                for f in files:
                                    fp = os.path.join(root, f)
                                    try:
                                        item_size += os.path.getsize(fp)
                                    except Exception:
                                        pass
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item_size = item.stat().st_size
                            item.unlink(missing_ok=True)

                        reclaimed_bytes += item_size
                        purged_items.append(item.name)
                        logger.info("Purged orphaned temp: %s (%.2f MB, age: %.1fh)", item.name, item_size / (1024 * 1024), age_sec / 3600.0)
                except Exception as exc:
                    logger.debug("Failed to purge temp %s: %s", item, exc)

        return {
            "reclaimed_bytes": reclaimed_bytes,
            "reclaimed_mb": round(reclaimed_bytes / (1024 * 1024), 2),
            "purged_count": len(purged_items),
            "purged_items": purged_items,
        }

    def sweep_scratch_and_cache(self, max_age_hours: float = 24.0) -> Dict[str, Any]:
        """Purge old transient files from scratch/ and intermediate test runs."""
        reclaimed_bytes = 0
        purged_count = 0
        now = time.time()
        cutoff_sec = max_age_hours * 3600.0

        targets = [
            self.root / "scratch" / "continuous_evolution",
            self.root / "scratch" / "temp",
            self.root / "output" / "temp",
        ]

        for target in targets:
            if not target.exists():
                continue
            for item in target.iterdir():
                if self._is_protected(str(item)):
                    continue
                try:
                    mtime = item.stat().st_mtime
                    if (now - mtime) >= cutoff_sec:
                        item_sz = 0
                        if item.is_dir():
                            for root, _, files in os.walk(item):
                                for f in files:
                                    try:
                                        item_sz += os.path.getsize(os.path.join(root, f))
                                    except Exception:
                                        pass
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item_sz = item.stat().st_size
                            item.unlink(missing_ok=True)
                        reclaimed_bytes += item_sz
                        purged_count += 1
                except Exception as exc:
                    logger.debug("Error purging scratch item %s: %s", item, exc)

        return {
            "reclaimed_bytes": reclaimed_bytes,
            "reclaimed_mb": round(reclaimed_bytes / (1024 * 1024), 2),
            "purged_count": purged_count,
        }

    def sweep_zero_byte_ghosts(self) -> Dict[str, Any]:
        """Purge zero-byte database and test artifact ghosts."""
        reclaimed_count = 0
        ghost_candidates = [
            self.root / "automovie.db",
            self.root / "data" / "automovie.db",
            self.root / "data" / "app.db",
            self.root / "test_bn_voice.mp3",
        ]
        for gc in ghost_candidates:
            if gc.exists() and gc.is_file():
                try:
                    if gc.stat().st_size == 0:
                        gc.unlink(missing_ok=True)
                        reclaimed_count += 1
                        logger.info("Purged 0-byte ghost file: %s", gc.name)
                except Exception:
                    pass

        return {"purged_ghost_count": reclaimed_count}

    def run_janitor_sweep(self, max_temp_age_hours: float = 2.0, max_scratch_age_hours: float = 24.0) -> Dict[str, Any]:
        """Execute a full, safe janitor sweep across all transient locations."""
        logger.info("🧹 [StorageJanitor] Initiating autonomous cleanup sweep...")
        start_t = time.time()

        temp_res = self.sweep_temp_assemblies(max_age_hours=max_temp_age_hours)
        scratch_res = self.sweep_scratch_and_cache(max_age_hours=max_scratch_age_hours)
        ghost_res = self.sweep_zero_byte_ghosts()

        total_bytes = temp_res["reclaimed_bytes"] + scratch_res["reclaimed_bytes"]
        total_mb = round(total_bytes / (1024 * 1024), 2)
        total_gb = round(total_bytes / (1024 * 1024 * 1024), 3)

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_sec": round(time.time() - start_t, 2),
            "total_reclaimed_mb": total_mb,
            "total_reclaimed_gb": total_gb,
            "temp_reclaimed_mb": temp_res["reclaimed_mb"],
            "scratch_reclaimed_mb": scratch_res["reclaimed_mb"],
            "purged_temp_count": temp_res["purged_count"],
            "purged_scratch_count": scratch_res["purged_count"],
            "purged_ghost_count": ghost_res["purged_ghost_count"],
            "status": "COMPLETED_SUCCESSFULLY",
        }

        # Persist report
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            history = []
            if self.history_file.exists():
                try:
                    history = json.loads(self.history_file.read_text(encoding="utf-8"))
                    if not isinstance(history, list):
                        history = []
                except Exception:
                    history = []
            history.insert(0, report)
            history = history[:50]  # Keep last 50 sweep reports
            self.history_file.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed to record janitor history: %s", exc)

        logger.info(
            "✅ [StorageJanitor] Sweep finished in %.2fs: Reclaimed %.2f MB (%.3f GB), %d items purged.",
            report["elapsed_sec"],
            total_mb,
            total_gb,
            temp_res["purged_count"] + scratch_res["purged_count"] + ghost_res["purged_ghost_count"],
        )
        return report

    def sweep_on_startup(self) -> Dict[str, Any]:
        """Perform on-startup cleanup for leftover crashed assemblies (age > 1 hour)."""
        logger.info("🚀 [StorageJanitor] Running startup sweep for orphaned assemblies...")
        return self.run_janitor_sweep(max_temp_age_hours=1.0, max_scratch_age_hours=48.0)

    def start_background_janitor_daemon(self, interval_hours: float = 24.0) -> None:
        """Start a persistent background daemon thread that performs daily auto-clean sweeps."""
        if self._daemon_thread is not None and self._daemon_thread.is_alive():
            logger.info("StorageJanitor daemon is already running.")
            return

        self._stop_event.clear()

        def _daemon_loop():
            logger.info("StorageJanitor background daemon started (Schedule: every %.1f hours).", interval_hours)
            while not self._stop_event.is_set():
                # Sleep in short increments to allow graceful shutdown
                sleep_seconds = int(interval_hours * 3600)
                for _ in range(sleep_seconds):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)

                if not self._stop_event.is_set():
                    try:
                        self.run_janitor_sweep()
                    except Exception as e:
                        logger.error("StorageJanitor scheduled sweep error: %s", e)

            logger.info("StorageJanitor background daemon stopped.")

        self._daemon_thread = threading.Thread(target=_daemon_loop, name="StorageJanitorDaemon", daemon=True)
        self._daemon_thread.start()

    def stop_background_janitor_daemon(self) -> None:
        """Stop the background daemon thread."""
        self._stop_event.set()
        if self._daemon_thread:
            self._daemon_thread.join(timeout=2.0)
            self._daemon_thread = None


def get_storage_janitor(root_dir: Optional[str] = None) -> StorageJanitorAgent:
    return StorageJanitorAgent.get_instance(root_dir)


if __name__ == "__main__":
    janitor = get_storage_janitor()
    rep = janitor.run_janitor_sweep(max_temp_age_hours=0.0)  # purge current temp test assemblies
    print(json.dumps(rep, indent=2))
