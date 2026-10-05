# Chernobyl 30 observation tick — compact JSON only (no PSObject bloat).
$ErrorActionPreference = "Continue"
$Root = "e:\All Project\AutoMovieProSAAS\AutoMoviePro-Software"
$Out = Join-Path $Root "output\Chernobyl_30_TrainCompare"
$Monitor = Join-Path $Out "monitor_status.json"

function Read-JsonFile([string]$path) {
  if (-not (Test-Path $path)) { return $null }
  $text = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
  if ($text.StartsWith([char]0xFEFF)) { $text = $text.Substring(1) }
  return ($text | ConvertFrom-Json)
}

$procs = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'chernobyl_30_train\.py' })
$wd = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_chernobyl_watchdog' })
$p = Read-JsonFile (Join-Path $Out "progress.json")
$doneList = @()
$passed = 0; $failed = 0; $errs = 0; $lastId = $null
if ($null -ne $p) {
  if ($p.completed_ids) { $doneList = @($p.completed_ids | ForEach-Object { [int]$_ }) }
  $passed = [int]($p.passed); $failed = [int]($p.failed); $errs = [int]($p.agent_errors); $lastId = $p.last_id
}

$log = Join-Path $Out "chernobyl30.log"
$logAgeSec = 99999
$lastLog = ""
$errSnips = New-Object System.Collections.Generic.List[string]
if (Test-Path $log) {
  $logAgeSec = [int]((Get-Date) - (Get-Item $log).LastWriteTime).TotalSeconds
  $tail = [System.IO.File]::ReadAllLines($log)
  if ($tail.Length -gt 0) {
    $start = [Math]::Max(0, $tail.Length - 80)
    for ($i = $start; $i -lt $tail.Length; $i++) {
      $line = [string]$tail[$i]
      $lastLog = $line
      if ($line -match 'ERROR|CLIP \d+ FAILED|localization failed|pad_av_tail failed|Traceback') {
        if ($errSnips.Count -lt 6) { [void]$errSnips.Add($line.Substring(0, [Math]::Min(180, $line.Length))) }
      }
    }
  }
}

$clipDirs = @(Get-ChildItem $Out -Directory -Filter "clip_*" -ErrorAction SilentlyContinue | Sort-Object Name)
$localizedOk = 0
$clips = New-Object System.Collections.Generic.List[string]
foreach ($c in $clipDirs) {
  $langs = New-Object System.Collections.Generic.List[string]
  $loc = Join-Path $c.FullName "LOCALIZED"
  if (Test-Path $loc) {
    foreach ($d in (Get-ChildItem $loc -Directory -ErrorAction SilentlyContinue)) {
      $v = Join-Path $d.FullName "video.mp4"
      if ((Test-Path $v) -and ((Get-Item $v).Length -gt 5000)) { [void]$langs.Add([string]$d.Name) }
    }
  }
  if ($langs.Count -ge 1) { $localizedOk++ }
  $mp4 = @(Get-ChildItem $c.FullName -Filter "*.mp4" -File -ErrorAction SilentlyContinue).Count
  [void]$clips.Add(("{0}:mp4={1};langs={2}" -f $c.Name, $mp4, ($langs -join "+")))
}

$status = "ok"
if ($doneList.Count -ge 30) { $status = "complete" }
elseif ($procs.Count -eq 0) { $status = "dead_runner" }
elseif ($logAgeSec -gt 720) { $status = "stale_log" }
elseif ($procs.Count -gt 2) { $status = "duplicate_runners" }

$obj = [ordered]@{
  ts = (Get-Date).ToString("s")
  status = $status
  done = $doneList.Count
  completed_ids = $doneList
  passed = $passed
  failed = $failed
  agent_errors = $errs
  last_id = $lastId
  runner_count = $procs.Count
  runner_pids = @($procs | ForEach-Object { [int]$_.ProcessId })
  watchdog_count = $wd.Count
  log_age_sec = $logAgeSec
  clip_dirs = $clipDirs.Count
  localized_ok = $localizedOk
  last_log = $lastLog.Substring(0, [Math]::Min(220, $lastLog.Length))
  recent_errors = @($errSnips)
  clips = @($clips)
}
$json = ($obj | ConvertTo-Json -Compress -Depth 5)
[System.IO.File]::WriteAllText($Monitor, $json, [System.Text.UTF8Encoding]::new($false))
Write-Output ("AGENT_LOOP_TICK_chernobyl " + $json)
