# Detached Chernobyl 30 watchdog — survives Cursor terminal kills.
# Windows venv note: venv\Scripts\python.exe is a stub that launches
# C:\Program Files\Python312\python.exe — BOTH appear in process list as ONE runner.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\run_chernobyl_watchdog.ps1

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "scripts\chernobyl_30_train.py"))) {
  $Root = "e:\All Project\AutoMovieProSAAS\AutoMoviePro-Software"
}
$Python = Join-Path $Root "venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\chernobyl_30_train.py"
$OutDir = Join-Path $Root "output\Chernobyl_30_TrainCompare"
$Log = Join-Path $OutDir "watchdog.log"
$Lock = Join-Path $OutDir "chernobyl.lock"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Write-Log($msg) {
  $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
  Add-Content -Path $Log -Value $line -Encoding UTF8
  Write-Host $line
}

function Get-LogicalTrainRunners {
  $all = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'chernobyl_30_train\.py' })
  if ($all.Count -eq 0) { return @() }

  # Collapse stub+base into one logical runner (child whose parent is also in set)
  $childIds = @{}
  foreach ($p in $all) {
    foreach ($q in $all) {
      if ($p.ProcessId -eq $q.ParentProcessId) { $childIds[$p.ProcessId] = $true }
    }
  }
  $roots = @($all | Where-Object { -not $childIds.ContainsKey($_.ProcessId) })
  if ($roots.Count -eq 0) { $roots = @($all | Sort-Object ProcessId | Select-Object -First 1) }
  return $roots
}

Write-Log "Watchdog started. Root=$Root Python=$Python"

while ($true) {
  $progress = Join-Path $OutDir "progress.json"
  $done = 0
  if (Test-Path $progress) {
    try {
      $p = Get-Content $progress -Raw -Encoding UTF8 | ConvertFrom-Json
      $done = @($p.completed_ids).Count
      if ($done -ge 30) {
        Write-Log "All 30 clips completed. Watchdog exit."
        break
      }
    } catch {}
  }

  $roots = @(Get-LogicalTrainRunners)

  if ($roots.Count -eq 0) {
    if (Test-Path $Lock) {
      Remove-Item $Lock -Force -ErrorAction SilentlyContinue
      Write-Log "Removed stale lock"
    }
    Write-Log "No runner found ($done/30). Starting chernobyl_30_train.py ..."
    Start-Process -FilePath $Python -ArgumentList "`"$Script`"" -WorkingDirectory $Root -WindowStyle Hidden
    Start-Sleep -Seconds 25
  } elseif ($roots.Count -gt 1) {
    # Prefer root whose command line is the venv stub
    $venvRoot = @($roots | Where-Object { $_.CommandLine -match 'venv\\Scripts\\python\.exe' } | Sort-Object ProcessId | Select-Object -First 1)
    if ($venvRoot.Count -eq 1) {
      $keep = $venvRoot[0].ProcessId
    } else {
      $keep = ($roots | Sort-Object ProcessId | Select-Object -First 1).ProcessId
    }
    foreach ($r in $roots) {
      if ($r.ProcessId -ne $keep) {
        Write-Log "Killing extra logical runner PID=$($r.ProcessId) (keep $keep)"
        # Kill root and its python children that run the same script
        $tree = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
          Where-Object { $_.CommandLine -match 'chernobyl_30_train\.py' -and ($_.ProcessId -eq $r.ProcessId -or $_.ParentProcessId -eq $r.ProcessId) }
        foreach ($t in $tree) {
          Stop-Process -Id $t.ProcessId -Force -ErrorAction SilentlyContinue
        }
      }
    }
  } else {
    Write-Log "Runner alive PID=$($roots[0].ProcessId) progress=$done/30"
  }
  Start-Sleep -Seconds 45
}
