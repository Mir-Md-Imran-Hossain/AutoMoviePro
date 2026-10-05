# Fixed observation loop for Chernobyl 30 — emits AGENT_LOOP_TICK_chernobyl every 4 minutes.
$ErrorActionPreference = "Continue"
$Tick = "e:\All Project\AutoMovieProSAAS\AutoMoviePro-Software\scripts\chernobyl_monitor_tick.ps1"
while ($true) {
  Start-Sleep -Seconds 240
  try {
    & $Tick
  } catch {
    Write-Output ('AGENT_LOOP_TICK_chernobyl {"status":"monitor_error","err":"' + $_.Exception.Message.Replace('"','') + '"}')
  }
}
