# Pack AutoMoviePro-Website for Hostinger File Manager (public_html).
# Run:  powershell -File "AutoMoviePro-Website\scripts\pack-hostinger.ps1"

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = "e:\All Project\AutoMovieProSAAS\AutoMoviePro-Software\venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

& $py -c @"
from pathlib import Path
import zipfile
root = Path(r'$root')
out = root / 'dist' / 'automoviepro-website-hostinger.zip'
out.parent.mkdir(exist_ok=True)
exclude_dirs = {'dist', 'storage', 'scripts', '.git'}
exclude_files = {'config.php', 'config.local.php', '.local-demo', '.gitignore'}
files = []
for p in root.rglob('*'):
    if not p.is_file():
        continue
    rel = p.relative_to(root)
    if rel.parts[0] in exclude_dirs:
        continue
    if rel.parts[-1] in exclude_files:
        continue
    files.append(rel)
out.unlink(missing_ok=True)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for rel in sorted(files):
        z.write(root / rel, arcname=rel.as_posix())
print('ZIP ready:', out)
print('files:', len(files), 'bytes:', out.stat().st_size)
print('Upload into Hostinger File Manager → public_html, then Extract.')
"@
