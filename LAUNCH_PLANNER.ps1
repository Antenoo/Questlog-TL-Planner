$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Url = "http://127.0.0.1:8765"
$HealthUrl = "$Url/api/health"

function Test-PlannerServer {
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 1
        return ($response.StatusCode -eq 200)
    } catch {
        return $false
    }
}

if (-not (Test-PlannerServer)) {
    # START_APP.bat launches the dedicated uvicorn console and then exits.
    Start-Process -FilePath "$Root\START_APP.bat" -WorkingDirectory $Root -WindowStyle Hidden

    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-PlannerServer) {
            break
        }
    }
}

if (Test-PlannerServer) {
    Start-Process $Url
    exit 0
}

try {
    $shell = New-Object -ComObject WScript.Shell
    $null = $shell.Popup(
        "Questlog TL Farm Planner did not start within 30 seconds.`n`nRun START_APP.bat once to see the server error.",
        0,
        "Questlog TL Farm Planner",
        16
    )
} catch {
}

exit 1
