[CmdletBinding()]
param(
    [int]$Monitor = -1,
    [ValidateRange(250, 60000)]
    [int]$IntervalMs = 1500,
    [string]$OutputPath = "",
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDirectory = Split-Path -Parent $scriptDirectory
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $projectDirectory ".view-only-relay\current-screen.png"
}

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

try {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class ViewOnlyRelayNative {
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetProcessDPIAware();
}
"@ -ErrorAction SilentlyContinue
    [void][ViewOnlyRelayNative]::SetProcessDPIAware()
} catch {
    # Capture still works when Windows has already selected the process DPI mode.
}

$screens = [System.Windows.Forms.Screen]::AllScreens
if ($screens.Count -eq 0) {
    throw "Windows did not report any displays."
}

if ($Monitor -lt 0) {
    $selectedIndex = 0
    for ($index = 0; $index -lt $screens.Count; $index++) {
        if ($screens[$index].Primary) {
            $selectedIndex = $index
            break
        }
    }
} elseif ($Monitor -ge $screens.Count) {
    throw "Monitor index $Monitor is unavailable. Windows reported $($screens.Count) display(s)."
} else {
    $selectedIndex = $Monitor
}

$selectedScreen = $screens[$selectedIndex]
$bounds = $selectedScreen.Bounds
$outputDirectory = Split-Path -Parent $OutputPath
$temporaryPath = "$OutputPath.new"
$relayStatePath = Join-Path $outputDirectory "relay-state.json"
$relayMutex = New-Object System.Threading.Mutex($false, "Local\QuestlogTLPlannerViewOnlyRelay")
$ownsRelayMutex = $false

[System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null

try {
    $ownsRelayMutex = $relayMutex.WaitOne(0)
} catch [System.Threading.AbandonedMutexException] {
    $ownsRelayMutex = $true
}

if (-not $ownsRelayMutex) {
    $relayMutex.Dispose()
    throw "The view-only relay is already running."
}

$relayProcess = Get-Process -Id $PID
$relayState = [ordered]@{
    ProcessId = $PID
    ProcessStartTimeUtcTicks = $relayProcess.StartTime.ToUniversalTime().Ticks
    Monitor = $selectedIndex
    OutputPath = $OutputPath
}
[System.IO.File]::WriteAllText(
    $relayStatePath,
    ($relayState | ConvertTo-Json),
    [System.Text.UTF8Encoding]::new($false)
)

function Write-RelayFrame {
    $bitmap = $null
    $graphics = $null

    try {
        $bitmap = New-Object System.Drawing.Bitmap(
            $bounds.Width,
            $bounds.Height,
            [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
        )
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen(
            $bounds.Left,
            $bounds.Top,
            0,
            0,
            $bitmap.Size,
            [System.Drawing.CopyPixelOperation]::SourceCopy
        )
        $bitmap.Save($temporaryPath, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        if ($null -ne $graphics) {
            $graphics.Dispose()
        }
        if ($null -ne $bitmap) {
            $bitmap.Dispose()
        }
    }

    Move-Item -LiteralPath $temporaryPath -Destination $OutputPath -Force
}

Write-Host "Questlog TL Planner - view-only relay"
Write-Host "Monitor: $selectedIndex ($($selectedScreen.DeviceName), $($bounds.Width)x$($bounds.Height))"
Write-Host "Frame:   $OutputPath"
Write-Host "Mode:    one overwritten PNG; no audio, input, or frame history"

try {
    Write-RelayFrame

    if ($Once) {
        Write-Host "One test frame captured."
        exit 0
    }

    Write-Host "Relay active. Minimize this window; press Ctrl+C or close it to stop."
    while ($true) {
        Start-Sleep -Milliseconds $IntervalMs
        Write-RelayFrame
    }
} finally {
    if ([System.IO.File]::Exists($temporaryPath)) {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }
    if ([System.IO.File]::Exists($relayStatePath)) {
        try {
            $currentRelayState = Get-Content -LiteralPath $relayStatePath -Raw | ConvertFrom-Json
            if ($currentRelayState.ProcessId -eq $PID) {
                Remove-Item -LiteralPath $relayStatePath -Force -ErrorAction SilentlyContinue
            }
        } catch {
            # A stale state file is harmless and will be validated before stopping.
        }
    }
    if ($ownsRelayMutex) {
        $relayMutex.ReleaseMutex()
    }
    $relayMutex.Dispose()
}
