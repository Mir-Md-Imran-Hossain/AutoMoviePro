import os
import sys
import shutil
import zipfile
from pathlib import Path

ROOT = Path(r"E:\All Project\AutoMovie_Pro_SAAS_Final_Update")
SOURCE_DIR = ROOT / "AutoMoviePro-Software"
RELEASE_DIR = Path(r"E:\All Project\AutoMovie_Pro_Release_Package")
INSTALLER_DIR = RELEASE_DIR / "AutoMoviePro_Installer"
ZIP_PATH = RELEASE_DIR / "AutoMoviePro_v2.0_Setup.zip"

print(f"[*] Packaging AutoMovie Pro Release from: {SOURCE_DIR}")
print(f"[*] Destination Installer Dir: {INSTALLER_DIR}")
print(f"[*] Output ZIP File: {ZIP_PATH}")

if INSTALLER_DIR.exists():
    print("[*] Removing previous installer folder...")
    shutil.rmtree(INSTALLER_DIR)

INSTALLER_DIR.mkdir(parents=True, exist_ok=True)

# 1. Directories to include
INCLUDE_DIRS = [
    "app",
    "pipeline",
    "ui",
    "config",
    "domain",
    "publishers",
    "scripts",
    "desktop",
    "ffmpeg-8.1.1-full_build",
]

# 2. Files to include
INCLUDE_FILES = [
    "Install_AutoMovie_Pro.bat",
    "Launch_AutoMovie_Pro_App.vbs",
    "Uninstall_AutoMovie_Pro.bat",
    "launch_desktop_app.py",
    "requirements.txt",
    "app_icon.ico",
]

# 3. Special Assets handling (avoid huge gigabytes of test video caches)
EXCLUDE_ASSET_SUBDIRS = {
    "photoreal_abyss",
    "quantum_broll",
    "motion_cache",
    "news_cache",
    "test_e2e_output",
    "_test_hb_cues",
    "_test_hb_cues_dyn",
}

FORBIDDEN_IGNORE_PATTERNS = (
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    "test_out",
    "*.log",
    "tests",
    "local.db",
    "*.sqlite",
    "*.sqlite3",
    ".env",
    "*.env",
    ".git",
)

def copy_assets():
    src_assets = SOURCE_DIR / "assets"
    dst_assets = INSTALLER_DIR / "assets"
    dst_assets.mkdir(parents=True, exist_ok=True)
    
    for item in src_assets.iterdir():
        if item.name in EXCLUDE_ASSET_SUBDIRS:
            continue
        if item.name.startswith("test_") or item.name.startswith("_test_"):
            continue
        if item.name.lower() in ("local.db", ".env", ".git"):
            continue
        if item.suffix.lower() in (".sqlite", ".sqlite3", ".log", ".pyc"):
            continue
        dst_item = dst_assets / item.name
        if item.is_dir():
            shutil.copytree(item, dst_item, ignore=shutil.ignore_patterns(*FORBIDDEN_IGNORE_PATTERNS))
        else:
            shutil.copy2(item, dst_item)
    print("  [✓] Copied assets (excluding heavy caches and forbidden files)")

# Copy directories
for d in INCLUDE_DIRS:
    src = SOURCE_DIR / d
    dst = INSTALLER_DIR / d
    if src.exists():
        print(f"  -> Copying {d}...")
        shutil.copytree(
            src, 
            dst, 
            ignore=shutil.ignore_patterns(*FORBIDDEN_IGNORE_PATTERNS)
        )

# Copy assets
copy_assets()

# Copy root files
for f in INCLUDE_FILES:
    src = SOURCE_DIR / f
    dst = INSTALLER_DIR / f
    if src.exists():
        shutil.copy2(src, dst)
        print(f"  [✓] Copied {f}")

# Copy README guide
readme_src = RELEASE_DIR / "README_ইন্সটলেশন_সহজ_গাইড.txt"
if readme_src.exists():
    shutil.copy2(readme_src, INSTALLER_DIR / "README_ইন্সটলেশন_সহজ_গাইড.txt")

def verify_package_cleanliness(target_dir: Path):
    """Ensure no forbidden debug, database, test, or secret artifacts exist in the release."""
    print("\n[*] Running strict packaging hygiene verification...")
    forbidden_files = []
    forbidden_names = {"local.db", ".env", ".git"}
    forbidden_extensions = {".sqlite", ".sqlite3", ".log", ".pyc"}
    
    for root, dirs, files in os.walk(target_dir):
        rel_root = Path(root).relative_to(target_dir)
        parts = rel_root.parts
        if any(part in ("tests", "__pycache__", ".pytest_cache") for part in parts):
            forbidden_files.append(f"Forbidden directory: {rel_root}")
        for f in files:
            p = Path(root) / f
            rel = p.relative_to(target_dir)
            if f.lower() in forbidden_names:
                forbidden_files.append(f"Forbidden file: {rel}")
            if p.suffix.lower() in forbidden_extensions:
                forbidden_files.append(f"Forbidden extension: {rel}")
            if f.lower().endswith(".env"):
                forbidden_files.append(f"Forbidden env file: {rel}")
                
    if forbidden_files:
        print("[!] PACKAGING FAILED - FORBIDDEN ARTIFACTS FOUND:")
        for item in forbidden_files:
            print(f"    - {item}")
        raise RuntimeError(f"Build failed: {len(forbidden_files)} forbidden artifacts found in {target_dir}")
    print("  [✓] All cleanliness assertions passed: 0 forbidden artifacts detected.")

verify_package_cleanliness(INSTALLER_DIR)

print("\n[*] Installer directory assembled successfully!")

# Now create the ZIP file
print(f"[*] Creating ZIP archive: {ZIP_PATH} ...")
if ZIP_PATH.exists():
    ZIP_PATH.unlink()

with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(INSTALLER_DIR):
        for file in files:
            file_path = Path(root) / file
            arcname = file_path.relative_to(RELEASE_DIR)
            zipf.write(file_path, arcname)

zip_size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
print(f"\n[🎉 SUCCESS] Created AutoMoviePro_v2.0_Setup.zip ({zip_size_mb:.2f} MB)")
