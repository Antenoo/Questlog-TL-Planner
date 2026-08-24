param(
    [Parameter(Mandatory = $true)]
    [string]$RelayImage,

    [Parameter(Mandatory = $true)]
    [string]$BatchDirectory,

    [int]$IntervalMilliseconds = 800
)

$ErrorActionPreference = 'Stop'
$resolvedRelay = [System.IO.Path]::GetFullPath($RelayImage)
$resolvedBatch = [System.IO.Path]::GetFullPath($BatchDirectory)
[System.IO.Directory]::CreateDirectory($resolvedBatch) | Out-Null

$sequence = 0
$lastWriteTicks = 0L

while ($true) {
    try {
        $source = Get-Item -LiteralPath $resolvedRelay -ErrorAction Stop
        if ($source.LastWriteTimeUtc.Ticks -ne $lastWriteTicks) {
            $sequence++
            $destination = Join-Path $resolvedBatch ('frame-{0:D5}.png' -f $sequence)
            Copy-Item -LiteralPath $resolvedRelay -Destination $destination -Force
            $lastWriteTicks = $source.LastWriteTimeUtc.Ticks
        }
    }
    catch {
        # The live relay can briefly replace its frame between reads. Retry next tick.
    }

    Start-Sleep -Milliseconds $IntervalMilliseconds
}
