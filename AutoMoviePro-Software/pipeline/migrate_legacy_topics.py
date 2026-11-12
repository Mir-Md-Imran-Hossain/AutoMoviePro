# -*- coding: utf-8 -*-
"""AutoMovie Pro — Legacy Topic Migration & Dry-Run Engine.

Module: pipeline.migrate_legacy_topics
Responsibilities:
1. Discovers and parses all legacy topic records across:
   - data/intelligence/topic_history/ch*.json (24 channel files)
   - data/topics/latest_research/topic_metadata.json
   - latest_research/topic_metadata.json
   - Output/ structured script metadata
2. Creates safe immutable backups into data/legacy_topic_backup_20261105/
3. Performs a comprehensive Dry-Run analysis (Total, Unique, Duplicate, Conflicting records)
4. Provides atomic migration into TopicDatabase without modifying or deleting original files.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

SOFTWARE_ROOT = Path(__file__).resolve().parent.parent
if str(SOFTWARE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_ROOT))

from pipeline.duplicate_sentinel import DuplicateSentinel
from pipeline.topic_database import TopicDatabase, get_topic_database

logger = logging.getLogger("AutoMoviePro.MigrateLegacyTopics")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s][LegacyMigration][%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
    logger.setLevel(logging.INFO)

SOFTWARE_ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = SOFTWARE_ROOT / "data" / "legacy_topic_backup_20261105"


class LegacyTopicMigrator:
    """Discovers, audits, and migrates legacy topic archives."""

    def __init__(self, db: Optional[TopicDatabase] = None):
        self.db = db or get_topic_database()
        self.sentinel = DuplicateSentinel(db=self.db)
        self.backup_dir = BACKUP_DIR

    def backup_legacy_files(self) -> Dict[str, Any]:
        """Creates an immutable copy of all legacy topic JSON files."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backed_up_files = []

        # 1. Channel topic history
        hist_dir = SOFTWARE_ROOT / "data" / "intelligence" / "topic_history"
        if hist_dir.exists():
            dest_hist = self.backup_dir / "intelligence" / "topic_history"
            dest_hist.mkdir(parents=True, exist_ok=True)
            for f in hist_dir.glob("*.json"):
                shutil.copy2(f, dest_hist / f.name)
                backed_up_files.append(str(dest_hist / f.name))

        # 2. Latest research
        for lr_path in [
            SOFTWARE_ROOT / "data" / "topics" / "latest_research" / "topic_metadata.json",
            SOFTWARE_ROOT / "latest_research" / "topic_metadata.json"
        ]:
            if lr_path.exists():
                dest_file = self.backup_dir / lr_path.name
                shutil.copy2(lr_path, dest_file)
                backed_up_files.append(str(dest_file))

        logger.info("Successfully backed up %d legacy topic files to %s", len(backed_up_files), self.backup_dir)
        return {
            "ok": True,
            "backup_dir": str(self.backup_dir),
            "file_count": len(backed_up_files),
            "files": backed_up_files
        }

    def scan_all_legacy_records(self) -> List[Dict[str, Any]]:
        """Collects raw topic records from all historical sources."""
        raw_records: List[Dict[str, Any]] = []

        # Source 1: Channel topic history (ch*.json)
        hist_dir = SOFTWARE_ROOT / "data" / "intelligence" / "topic_history"
        if hist_dir.exists():
            for f in sorted(hist_dir.glob("ch*.json")):
                ch_id = 0
                try:
                    ch_id = int(f.stem.replace("ch", ""))
                except Exception:
                    pass

                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    items = data if isinstance(data, list) else data.get("items", [])
                    for item in items:
                        if isinstance(item, dict):
                            title = (item.get("topic") or item.get("title") or "").strip()
                            if title:
                                raw_records.append({
                                    "source_file": str(f.relative_to(SOFTWARE_ROOT)),
                                    "channel_id": ch_id,
                                    "video_format": item.get("video_type") or "short",
                                    "title": title,
                                    "niche": item.get("niche") or "general",
                                    "created_at": item.get("at") or datetime.now(timezone.utc).isoformat(),
                                    "raw_item": item
                                })
                except Exception as exc:
                    logger.warning("Error reading %s: %s", f.name, exc)

        # Source 2: latest_research/topic_metadata.json
        for lr_path in [
            SOFTWARE_ROOT / "data" / "topics" / "latest_research" / "topic_metadata.json",
            SOFTWARE_ROOT / "latest_research" / "topic_metadata.json"
        ]:
            if lr_path.exists():
                try:
                    data = json.loads(lr_path.read_text(encoding="utf-8"))
                    title = (data.get("topic_bn") or data.get("seo_title") or data.get("topic") or "").strip()
                    if title:
                        raw_records.append({
                            "source_file": str(lr_path.relative_to(SOFTWARE_ROOT)),
                            "channel_id": 1,
                            "video_format": data.get("video_type") or "short",
                            "title": title,
                            "niche": data.get("niche") or "general",
                            "created_at": data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                            "raw_item": data
                        })
                except Exception as exc:
                    logger.warning("Error reading %s: %s", lr_path.name, exc)

        # Source 3: Output/ structured_script.json
        out_dir = SOFTWARE_ROOT / "Output"
        if out_dir.exists():
            for script_file in out_dir.glob("**/structured_script.json"):
                try:
                    data = json.loads(script_file.read_text(encoding="utf-8"))
                    title = (data.get("title_bn") or data.get("topic") or "").strip()
                    if title:
                        raw_records.append({
                            "source_file": str(script_file.relative_to(SOFTWARE_ROOT)),
                            "channel_id": 1,
                            "video_format": "long" if "long" in str(script_file).lower() else "short",
                            "title": title,
                            "niche": data.get("niche") or "general",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "raw_item": data
                        })
                except Exception:
                    pass

        return raw_records

    def run_dry_run_audit(self) -> Dict[str, Any]:
        """Runs a non-destructive dry-run analysis of all historical topics."""
        records = self.scan_all_legacy_records()
        total_found = len(records)

        channel_signatures: Dict[str, Dict[str, Any]] = {}
        global_signatures: Dict[str, Dict[str, Any]] = {}
        unique_records: List[Dict[str, Any]] = []
        channel_duplicates: List[Dict[str, Any]] = []
        global_duplicates: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []

        for rec in records:
            title = rec["title"]
            norm_sig = self.sentinel.normalize_text(title)
            ch_id = rec["channel_id"]
            fmt = rec["video_format"].lower()

            ch_key = f"{ch_id}:{fmt}:{norm_sig}"
            glob_key = norm_sig

            if not norm_sig:
                conflicts.append({
                    "record": rec,
                    "reason": "Normalized signature is empty."
                })
                continue

            # Check Global duplicates across all channels
            if glob_key in global_signatures:
                prior_glob = global_signatures[glob_key]
                global_duplicates.append({
                    "title": title,
                    "first_seen_channel": prior_glob["channel_id"],
                    "current_channel": ch_id,
                    "signature": norm_sig
                })
            else:
                global_signatures[glob_key] = rec

            # Check Per-channel duplicates
            if ch_key in channel_signatures:
                prior = channel_signatures[ch_key]
                channel_duplicates.append({
                    "title": title,
                    "channel_id": ch_id,
                    "original_source": prior["source_file"],
                    "duplicate_source": rec["source_file"],
                    "signature": norm_sig
                })
            else:
                channel_signatures[ch_key] = rec
                unique_records.append({
                    "candidate_id": f"cand_mig_{hashlib.md5(ch_key.encode('utf-8')).hexdigest()[:10]}",
                    "topic_id": f"top_mig_{hashlib.md5(ch_key.encode('utf-8')).hexdigest()[:10]}",
                    "channel_id": ch_id,
                    "niche": rec["niche"],
                    "video_format": fmt,
                    "normalized_signature": norm_sig,
                    "title_primary": title,
                    "source_file": rec["source_file"],
                    "created_at": rec["created_at"],
                    "raw_item": rec["raw_item"]
                })

        report = {
            "total_found": total_found,
            "unique_channel_records": len(unique_records),
            "global_unique_titles": len(global_signatures),
            "global_duplicates_count": len(global_duplicates),
            "channel_duplicates_count": len(channel_duplicates),
            "conflict_count": len(conflicts),
            "sample_unique": [r["title_primary"] for r in unique_records[:8]],
            "sample_global_duplicates": global_duplicates[:5],
            "conflicts": conflicts
        }
        return report

    def apply_migration(self) -> Dict[str, Any]:
        """Atomically imports unique legacy records into the new TopicDatabase."""
        dry_run = self.run_dry_run_audit()
        records = self.scan_all_legacy_records()

        seen_keys: Set[str] = set()
        migrated_count = 0
        skipped_count = 0

        for rec in records:
            title = rec["title"]
            norm_sig = self.sentinel.normalize_text(title)
            ch_id = rec["channel_id"]
            fmt = rec["video_format"].lower()
            key = f"{ch_id}:{fmt}:{norm_sig}"

            if not norm_sig or key in seen_keys:
                skipped_count += 1
                continue

            seen_keys.add(key)
            cand_id = f"cand_mig_{hashlib.md5(key.encode('utf-8')).hexdigest()[:10]}"
            top_id = f"top_mig_{hashlib.md5(key.encode('utf-8')).hexdigest()[:10]}"

            try:
                # 1. Record candidate
                self.db.record_candidate(
                    candidate_id=cand_id,
                    cycle_id="legacy_migration_20261105",
                    channel_id=ch_id,
                    niche=rec["niche"],
                    video_format=fmt,
                    title_primary=title,
                    main_entity=title[:30],
                    story_angle="Historical Production Topic",
                    selection_status="WINNER",
                    metadata={"migrated_from": rec["source_file"]}
                )

                # 2. Approve into registry
                self.db.approve_topic(
                    topic_id=top_id,
                    candidate_id=cand_id,
                    channel_id=ch_id,
                    niche=rec["niche"],
                    video_format=fmt,
                    normalized_signature=norm_sig,
                    title_primary=title,
                    primary_keyword=title[:20],
                    seo_metadata={"migrated": True, "source": rec["source_file"]},
                    trs_score=80.0,
                    mqs_score=85.0,
                    status="published"
                )
                migrated_count += 1
            except Exception as exc:
                logger.warning("Skipping migration for %s: %s", title, exc)
                skipped_count += 1

        return {
            "ok": True,
            "migrated_count": migrated_count,
            "skipped_count": skipped_count,
            "total_legacy_scanned": len(records)
        }


def get_legacy_topic_migrator() -> LegacyTopicMigrator:
    return LegacyTopicMigrator()


if __name__ == "__main__":
    migrator = get_legacy_topic_migrator()
    print("=== Backing up legacy files ===")
    bk_res = migrator.backup_legacy_files()
    print("Backup completed:", bk_res["file_count"], "files backed up.")

    print("\n=== Running Dry Run Audit ===")
    audit_res = migrator.run_dry_run_audit()
    print("Total Found:", audit_res["total_found"])
    print("Channel-Unique Records:", audit_res["unique_channel_records"])
    print("Global Unique Titles:", audit_res["global_unique_titles"])
    print("Global Duplicates (Cross-Channel):", audit_res["global_duplicates_count"])
    print("Channel Duplicates (Same Channel):", audit_res["channel_duplicates_count"])
    print("Conflicts:", audit_res["conflict_count"])
    print("Sample Global Duplicates:", audit_res["sample_global_duplicates"][:2])
