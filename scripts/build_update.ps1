[CmdletBinding(DefaultParameterSetName = 'Build')]
param(
    [Parameter(ParameterSetName = 'Build')]
    [string]$OutputDirectory = 'dist',

    [Parameter(ParameterSetName = 'Validate', Mandatory = $true)]
    [switch]$ValidateOnly,

    [Parameter(ParameterSetName = 'Validate', Mandatory = $true)]
    [string]$PackagePath,

    [string]$MetadataPath = 'release/publish.json'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$VersionPattern = '^[0-9]+\.[0-9]+\.[0-9]+$'

# This is the complete update-package allowlist. Nothing else is traversed or copied.
$PackageAllowlist = @(
    [pscustomobject]@{ Source = 'update_manager.py';              Archive = 'update_manager.py' },
    [pscustomobject]@{ Source = 'LIVE_UPDATE_HELPER.py';          Archive = 'LIVE_UPDATE_HELPER.py' },
    [pscustomobject]@{ Source = 'START_APP.bat';                  Archive = 'START_APP.bat' },
    [pscustomobject]@{ Source = 'APPLY_UPDATE.bat';               Archive = 'APPLY_UPDATE.bat' },
    [pscustomobject]@{ Source = 'ROLLBACK_LAST_UPDATE.bat';       Archive = 'ROLLBACK_LAST_UPDATE.bat' },
    [pscustomobject]@{ Source = 'backend.py';                     Archive = '_update_payload/backend.py' },
    [pscustomobject]@{ Source = 'scraper_engine.py';              Archive = '_update_payload/scraper_engine.py' },
    [pscustomobject]@{ Source = 'launcher.py';                    Archive = '_update_payload/launcher.py' },
    [pscustomobject]@{ Source = 'config_bootstrap.py';            Archive = '_update_payload/config_bootstrap.py' },
    [pscustomobject]@{ Source = 'config.example.json';            Archive = '_update_payload/config.example.json' },
    [pscustomobject]@{ Source = 'release_metadata.py';            Archive = '_update_payload/release_metadata.py' },
    [pscustomobject]@{ Source = 'release/publish.json';            Archive = '_update_payload/release/publish.json' },
    [pscustomobject]@{ Source = 'requirements.txt';               Archive = '_update_payload/requirements.txt' },
    [pscustomobject]@{ Source = 'SETUP_FIRST_TIME.bat';           Archive = '_update_payload/SETUP_FIRST_TIME.bat' },
    [pscustomobject]@{ Source = 'LAUNCH_PLANNER.ps1';             Archive = '_update_payload/LAUNCH_PLANNER.ps1' },
    [pscustomobject]@{ Source = 'OPEN_APP.bat';                   Archive = '_update_payload/OPEN_APP.bat' },
    [pscustomobject]@{ Source = 'INSTALL_APP_SHORTCUT.bat';       Archive = '_update_payload/INSTALL_APP_SHORTCUT.bat' },
    [pscustomobject]@{ Source = 'REMOVE_APP_SHORTCUT.bat';        Archive = '_update_payload/REMOVE_APP_SHORTCUT.bat' },
    [pscustomobject]@{ Source = 'assets/Questlog_TL_Farm_Planner.ico'; Archive = '_update_payload/assets/Questlog_TL_Farm_Planner.ico' },
    [pscustomobject]@{ Source = 'static/assets/planner-route-logo.png'; Archive = '_update_payload/static/assets/planner-route-logo.png' },
    [pscustomobject]@{ Source = 'static/index.html';              Archive = '_update_payload/static/index.html' }
)

$RequiredEntries = @(
    '_update_payload/backend.py',
    '_update_payload/static/index.html',
    '_update_payload/static/assets/planner-route-logo.png',
    'update_manager.py',
    'LIVE_UPDATE_HELPER.py',
    'START_APP.bat'
)

$ForbiddenSegments = @(
    '.git', '.venv', 'venv', 'env', '__pycache__',
    'data', 'cache', 'caches', 'exports', 'logs',
    'diagnostics', 'diagnostic_bundles', 'backups', 'update_backups',
    'user_knowledge', 'updates', '_update_staging'
)

$ForbiddenNames = @(
    'config.json', 'planner_state.json', 'scan_history.json',
    'health_report.json', 'update_state.json',
    'live_update_download.json', 'live_update_result.json',
    'live_update_restart.log', '.env', 'secrets.json', 'local_config.json'
)

$ForbiddenExtensions = @(
    '.zip', '.exe', '.msi', '.lnk', '.log', '.tmp', '.temp',
    '.bak', '.backup', '.old', '.pyc', '.pyo'
)

function Resolve-FromRepo([string]$Path) {
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Path))
}

function Assert-SafeRelativePath([string]$Path, [switch]$ArchiveEntry) {
    $normalized = $Path.Replace('\', '/')
    if ([string]::IsNullOrWhiteSpace($normalized) -or
        $normalized.StartsWith('/') -or
        [System.IO.Path]::IsPathRooted($normalized)) {
        throw "Unsafe rooted or empty path: $Path"
    }

    $parts = @($normalized.Split('/') | Where-Object { $_ -ne '' })
    if ($parts.Count -eq 0 -or $parts -contains '..' -or $parts -contains '.') {
        throw "Unsafe relative path: $Path"
    }

    if ($ArchiveEntry -and $parts[0] -eq '_update_payload') {
        $parts = @($parts | Select-Object -Skip 1)
        if ($parts.Count -eq 0) {
            throw "Update payload entry has no file path: $Path"
        }
    } elseif ($ArchiveEntry -and $parts.Count -gt 1) {
        throw "Archive entry must be a root file or live below _update_payload/: $Path"
    }

    foreach ($part in $parts) {
        if ($ForbiddenSegments -icontains $part) {
            throw "Forbidden private/runtime path segment '$part' in: $Path"
        }
    }

    $leaf = $parts[-1]
    if ($ForbiddenNames -icontains $leaf) {
        throw "Forbidden private/runtime filename '$leaf' in: $Path"
    }

    $extension = [System.IO.Path]::GetExtension($leaf)
    if ($ForbiddenExtensions -icontains $extension) {
        throw "Forbidden generated/private extension '$extension' in: $Path"
    }
}

function Get-ReleaseMetadata {
    $path = Resolve-FromRepo $MetadataPath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Release metadata does not exist: $path"
    }
    $metadata = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
    $expected = @('schema_version', 'version', 'publish', 'prerelease', 'display_name', 'notes')
    $actual = @($metadata.PSObject.Properties.Name)
    $difference = @(Compare-Object -ReferenceObject $expected -DifferenceObject $actual)
    if ($difference.Count -ne 0) {
        throw 'release/publish.json does not match the required schema'
    }
    if ($metadata.schema_version -ne 1) {
        throw 'Unsupported release metadata schema_version'
    }
    if ([string]$metadata.version -notmatch $VersionPattern) {
        throw 'Release version must use X.Y.Z numeric format'
    }
    if ($metadata.publish -isnot [bool] -or $metadata.prerelease -isnot [bool]) {
        throw 'Release publish and prerelease values must be booleans'
    }
    if ([string]$metadata.display_name -notmatch '^[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}$') {
        throw 'Release display_name contains unsafe characters or is too long'
    }
    $notes = [string]$metadata.notes
    if ([string]::IsNullOrWhiteSpace($notes) -or $notes.Length -gt 20000 -or $notes.Contains([char]0)) {
        throw 'Release notes are empty, unsafe, or too long'
    }
    return $metadata
}

function Assert-NoPrivateContent([string]$SourcePath, [string]$RelativePath) {
    $textExtensions = @('.py', '.html', '.json', '.txt', '.ps1', '.bat', '.md', '.yml', '.yaml')
    if ($textExtensions -notcontains [System.IO.Path]::GetExtension($SourcePath).ToLowerInvariant()) {
        return
    }

    $content = Get-Content -Raw -LiteralPath $SourcePath
    $checks = @(
        [pscustomobject]@{ Name = 'Windows user profile path'; Pattern = '(?i)[A-Z]:\\Users\\' },
        [pscustomobject]@{ Name = 'GitHub token'; Pattern = '(?i)github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]+' },
        [pscustomobject]@{ Name = 'Questlog build-shaped URL'; Pattern = '(?i)https?://questlog\.gg/(?:[^/\s"''<>]+/){2,}' }
    )
    foreach ($check in $checks) {
        if ($content -match $check.Pattern) {
            throw "$($check.Name) detected in allowlisted source: $RelativePath"
        }
    }
}

function Get-ExpectedEntrySet {
    $set = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($item in $PackageAllowlist) {
        if (-not $set.Add([string]$item.Archive)) {
            throw "Duplicate archive destination in allowlist: $($item.Archive)"
        }
    }
    return $set
}

function Test-UpdatePackage([string]$Path, [string]$ExpectedFileName) {
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw "Update package does not exist: $fullPath"
    }
    if ([System.IO.Path]::GetFileName($fullPath) -cne $ExpectedFileName) {
        throw "Package filename must be exactly $ExpectedFileName"
    }

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $expected = Get-ExpectedEntrySet
    $actual = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    $archive = [System.IO.Compression.ZipFile]::OpenRead($fullPath)
    try {
        foreach ($entry in $archive.Entries) {
            $name = $entry.FullName.Replace('\', '/')
            if ($name.EndsWith('/')) {
                throw "Directory entries are not permitted in the update ZIP: $name"
            }
            Assert-SafeRelativePath -Path $name -ArchiveEntry
            if (-not $actual.Add($name)) {
                throw "Duplicate ZIP entry: $name"
            }
        }
    } finally {
        $archive.Dispose()
    }

    $missing = @($expected | Where-Object { -not $actual.Contains($_) } | Sort-Object)
    $extra = @($actual | Where-Object { -not $expected.Contains($_) } | Sort-Object)
    if ($missing.Count -ne 0 -or $extra.Count -ne 0) {
        throw "ZIP allowlist mismatch. Missing=[$($missing -join ', ')] Extra=[$($extra -join ', ')]"
    }
    foreach ($required in $RequiredEntries) {
        if (-not $actual.Contains($required)) {
            throw "Required updater entry is missing: $required"
        }
    }
    return @($actual | Sort-Object)
}

$metadata = Get-ReleaseMetadata
$version = [string]$metadata.version
$versionToken = $version.Replace('.', '_')
$expectedFileName = "Questlog_TL_Farm_Planner_UPDATE_v$versionToken.zip"

if ($ValidateOnly) {
    $resolvedPackage = Resolve-FromRepo $PackagePath
    $entries = Test-UpdatePackage -Path $resolvedPackage -ExpectedFileName $expectedFileName
    Write-Output "Validated $resolvedPackage"
    Write-Output "Version: $version"
    Write-Output 'Entries:'
    $entries | ForEach-Object { Write-Output "  $_" }
    exit 0
}

$repoPrefix = $RepoRoot.TrimEnd('\') + '\'
foreach ($item in $PackageAllowlist) {
    Assert-SafeRelativePath -Path ([string]$item.Source)
    Assert-SafeRelativePath -Path ([string]$item.Archive) -ArchiveEntry
    $sourcePath = Resolve-FromRepo ([string]$item.Source)
    if (-not $sourcePath.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Allowlisted source resolves outside the repository: $($item.Source)"
    }
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Allowlisted source is missing: $($item.Source)"
    }
    $sourceItem = Get-Item -LiteralPath $sourcePath -Force
    if (($sourceItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Allowlisted source may not be a symlink/reparse point: $($item.Source)"
    }
    Assert-NoPrivateContent -SourcePath $sourcePath -RelativePath ([string]$item.Source)
}

$resolvedOutputDirectory = Resolve-FromRepo $OutputDirectory
New-Item -ItemType Directory -Path $resolvedOutputDirectory -Force | Out-Null
$outputPath = Join-Path $resolvedOutputDirectory $expectedFileName
if (Test-Path -LiteralPath $outputPath) {
    throw "Refusing to overwrite existing package: $outputPath"
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$fileStream = $null
$zip = $null
try {
    $fileStream = [System.IO.File]::Open($outputPath, [System.IO.FileMode]::CreateNew)
    $zip = [System.IO.Compression.ZipArchive]::new(
        $fileStream,
        [System.IO.Compression.ZipArchiveMode]::Create,
        $false
    )
    foreach ($item in $PackageAllowlist) {
        $sourcePath = Resolve-FromRepo ([string]$item.Source)
        $entry = $zip.CreateEntry(
            [string]$item.Archive,
            [System.IO.Compression.CompressionLevel]::Optimal
        )
        $entry.LastWriteTime = [System.DateTimeOffset]::new(1980, 1, 1, 0, 0, 0, [System.TimeSpan]::Zero)
        $input = [System.IO.File]::OpenRead($sourcePath)
        $output = $entry.Open()
        try {
            $input.CopyTo($output)
        } finally {
            $output.Dispose()
            $input.Dispose()
        }
    }
} catch {
    $buildError = $_
    if ($zip) { $zip.Dispose() }
    if ($fileStream) { $fileStream.Dispose() }
    if (Test-Path -LiteralPath $outputPath) {
        try {
            Remove-Item -LiteralPath $outputPath -Force
        } catch {
            Write-Warning "Could not remove partial package: $outputPath"
        }
    }
    throw $buildError
} finally {
    if ($zip) { $zip.Dispose() }
    if ($fileStream) { $fileStream.Dispose() }
}

$entries = Test-UpdatePackage -Path $outputPath -ExpectedFileName $expectedFileName
Write-Output "Built and validated $outputPath"
Write-Output "Version: $version"
Write-Output "Publishing enabled: $($metadata.publish)"
Write-Output 'Entries:'
$entries | ForEach-Object { Write-Output "  $_" }
