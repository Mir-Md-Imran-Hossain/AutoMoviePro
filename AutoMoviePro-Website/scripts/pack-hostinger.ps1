# Pack AutoMoviePro-Website for Hostinger File Manager (public_html).
# Run:  powershell -File "AutoMoviePro-Website\scripts\pack-hostinger.ps1"

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = "python"

& $py -c @"
import sys
from pathlib import Path
import zipfile

root = Path(r'$root')
out = root / 'dist' / 'automoviepro-website-hostinger.zip'
out.parent.mkdir(exist_ok=True)

exclude_dirs = {'dist', 'storage', 'scripts', 'tests', '.git', 'rules', 'submissions', '__pycache__'}
exclude_files = {'config.php', 'config.local.php', '.local-demo', '.gitignore', 'install.lock'}
exclude_exts = {'.sqlite', '.sqlite3', '.db', '.sql', '.log', '.md', '.pyc'}

forbidden_patterns = ['tests/', 'scripts/', 'storage/', '.sqlite', 'config.php', 'install.lock']

files = []
for p in root.rglob('*'):
    if not p.is_file():
        continue
    rel = p.relative_to(root)
    # Check directory exclusion
    if any(part in exclude_dirs for part in rel.parts):
        continue
    if rel.parts[-1] in exclude_files:
        continue
    if p.suffix.lower() in exclude_exts:
        continue
    files.append(rel)

# Security Assertion: verify no forbidden file or pattern is included
violations = []
for rel in files:
    posix_path = rel.as_posix()
    for forb in forbidden_patterns:
        if forb in posix_path:
            violations.append((posix_path, forb))

if violations:
    print('SECURITY ASSERTION FAILED: Forbidden files found in package list!', file=sys.stderr)
    for v_path, v_rule in violations:
        print(f'  VIOLATION: {v_path} matches forbidden rule {v_rule}', file=sys.stderr)
    sys.exit(1)

out.unlink(missing_ok=True)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for rel in sorted(files):
        z.write(root / rel, arcname=rel.as_posix())

print('ZIP ready:', out)
print('files:', len(files), 'bytes:', out.stat().st_size)
print('Upload into Hostinger File Manager -> public_html, then Extract.')
"@
