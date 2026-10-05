"""
AutoMovie Pro — Client Distribution Package Generator
Generates a clean, ready-to-deliver zip bundle for paying customers.
Excludes developer test suites, internal run cache, and temporary artifacts.
"""
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
DIST_DIR.mkdir(parents=True, exist_ok=True)
OUT_ZIP = DIST_DIR / "AutoMoviePro-Desktop-Client-Latest.zip"

INCLUDE_DIRS = [
    "app",
    "pipeline",
    "publishers",
    "marketing",
    "domain",
    "ui",
    "assets",
    "ffmpeg-8.1.1-full_build",
    "third_party",
]

INCLUDE_ROOT_FILES = [
    "Start_AutoMovie_Pro.bat",
    "AutoMoviePro_Setup.bat",
    "AutoMoviePro_Silent.vbs",
    "START.bat",
    "README_CLIENT_বাংলা.txt",
    "requirements.txt",
    ".env",
    ".env.example",
]

# Important scripts needed for client preflight
INCLUDE_SCRIPTS = [
    "installer_gui.py",
    "generate_voice_cues.py",
]

EXCLUDE_EXTENSIONS = {".pyc", ".pyd", ".tmp", ".log"}
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git", ".idea", ".vscode"}


def collect_files():
    files_to_pack = []
    
    # 1. Root files
    for fname in INCLUDE_ROOT_FILES:
        fpath = ROOT / fname
        if fpath.is_file():
            files_to_pack.append((fpath, Path(fname)))
            
    # 2. Included directories
    for dname in INCLUDE_DIRS:
        dp = ROOT / dname
        if not dp.is_dir():
            continue
        for p in dp.rglob("*"):
            if not p.is_file():
                continue
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            if p.suffix.lower() in EXCLUDE_EXTENSIONS:
                continue
            # Skip massive temp caches
            if "marathon_runs" in p.parts or "customer_generation_work" in p.parts:
                continue
            rel = p.relative_to(ROOT)
            files_to_pack.append((p, rel))
            
    # 3. Selected helper scripts
    for sname in INCLUDE_SCRIPTS:
        sp = ROOT / "scripts" / sname
        if sp.is_file():
            files_to_pack.append((sp, Path("scripts") / sname))
            
    return files_to_pack


def main():
    print(f">> Packing Client Distribution: {OUT_ZIP} ...")
    files = collect_files()
    print(f">> Collected {len(files)} clean distribution files.")
    
    if OUT_ZIP.exists():
        OUT_ZIP.unlink()
        
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for idx, (fpath, arcname) in enumerate(files):
            zf.write(fpath, arcname.as_posix())
            if idx % 100 == 0:
                print(f"   [{idx}/{len(files)}] Packing: {arcname.as_posix()[:60]}")
                
    size_mb = OUT_ZIP.stat().st_size / (1024 * 1024)
    print("=" * 70)
    print("[SUCCESS] CLIENT DISTRIBUTION BUNDLE READY!")
    print(f"Location: {OUT_ZIP}")
    print(f"File Size: {size_mb:.2f} MB")
    print(f"Total Files: {len(files)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
