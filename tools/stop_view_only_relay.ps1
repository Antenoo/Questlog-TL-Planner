[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDirectory = Split-Path -Parent $scriptDirectory
$relayDirectory = Join-Path $projectDirectory ".view-only-relay"
$relayStatePath = Join-Path $relayDirectory "relay-state.json"

if (-not (Test-Path -LiteralPath $relayStatePath)) {
    Write-Host "The view-only relay is not running."
    exit 0
}

try {
    $relayState = Get-Content -LiteralPath $relayStatePath -Raw | ConvertFrom-Json
    $relayProcess = Get-Process -Id ([int]$relayState.ProcessId) -ErrorAction Stop
    $actualStartTicks = $relayProcess.StartTime.ToUniversalTime().Ticks

    if ($actualStartTicks -ne [long]$relayState.ProcessStartTimeUtcTicks) {
        throw "The saved process identifier now belongs to a different process."
    }

    Stop-Process -Id $relayProcess.Id -ErrorAction Stop
    Write-Host "The view-only relay has stopped."
} catch {
    Write-Warning "No matching relay process was stopped: $($_.Exception.Message)"
} finally {
    Remove-Item -LiteralPath $relayStatePath -Force -ErrorAction SilentlyContinue
}
