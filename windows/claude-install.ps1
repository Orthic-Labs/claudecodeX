# Resolve an official, updater-managed Claude Desktop installation on Windows.
# Supports both the Microsoft Store/MSIX package and Anthropic's non-admin
# Squirrel installer. Unmanaged extracted copies are intentionally rejected.

function Assert-AnthropicSignature {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Description
    )

    $signature = Get-AuthenticodeSignature -LiteralPath $Path -ErrorAction Stop
    if (
        $signature.Status -ne 'Valid' -or
        -not $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch 'Anthropic, PBC'
    ) {
        throw "$Description is not signed by Anthropic, PBC: $Path"
    }
}

function ConvertTo-ClaudeVersion {
    param([Parameter(Mandatory)][string]$DirectoryName)

    $parsed = $null
    $raw = $DirectoryName -replace '^app-', ''
    if ([version]::TryParse($raw, [ref]$parsed)) { return $parsed }
    return [version]'0.0'
}

function Resolve-ClaudeDesktopInstall {
    [CmdletBinding()]
    param()

    # Prefer Anthropic's updater when both installers remain registered. This avoids
    # selecting an abandoned or partially removed MSIX after a user migrates.
    $squirrelRoot = Join-Path $env:LOCALAPPDATA 'AnthropicClaude'
    $stableLauncher = Join-Path $squirrelRoot 'claude.exe'
    $updater = Join-Path $squirrelRoot 'Update.exe'
    if ((Test-Path -LiteralPath $stableLauncher) -and (Test-Path -LiteralPath $updater)) {
        Assert-AnthropicSignature -Path $stableLauncher -Description 'The updater-managed Claude launcher'

        $current = Get-ChildItem -LiteralPath $squirrelRoot -Directory -Filter 'app-*' -ErrorAction Stop |
            Where-Object {
                (Test-Path -LiteralPath (Join-Path $_.FullName 'claude.exe')) -and
                (Test-Path -LiteralPath (Join-Path $_.FullName 'resources\app.asar'))
            } |
            Sort-Object @{ Expression = { ConvertTo-ClaudeVersion $_.Name }; Descending = $true } |
            Select-Object -First 1

        if (-not $current) {
            throw "Anthropic's Claude updater is installed, but no complete app-* version was found in $squirrelRoot."
        }

        $currentExe = Join-Path $current.FullName 'claude.exe'
        $currentAsar = Join-Path $current.FullName 'resources\app.asar'
        Assert-AnthropicSignature -Path $currentExe -Description 'The current updater-managed Claude executable'
        return [pscustomobject]@{
            InstallKind = 'squirrel'
            DisplayVersion = ($current.Name -replace '^app-', '')
            ExecutablePath = $currentExe
            AsarPath = $currentAsar
            IconResource = "$currentExe,0"
        }
    }

    $pkg = Get-AppxPackage -Name 'Claude' -ErrorAction SilentlyContinue
    if ($pkg) {
        $exe = Join-Path $pkg.InstallLocation 'app\Claude.exe'
        $asar = Join-Path $pkg.InstallLocation 'app\resources\app.asar'
        if ((Test-Path -LiteralPath $exe) -and (Test-Path -LiteralPath $asar)) {
            Assert-AnthropicSignature -Path $exe -Description 'The packaged Claude executable'
            return [pscustomobject]@{
                InstallKind = 'msix'
                DisplayVersion = [string]$pkg.Version
                ExecutablePath = $exe
                AsarPath = $asar
                IconResource = "$exe,0"
            }
        }
    }

    throw "No official updater-managed Claude Desktop installation was found. Install Claude from the Microsoft Store or https://claude.com/download."
}
