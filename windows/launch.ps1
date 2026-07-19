# anyclaude launcher (Windows) — starts the proxy if needed, then opens an isolated
# Claude Desktop instance pointed at it, with its own taskbar button.
$ErrorActionPreference = 'Stop'
$root       = Split-Path $PSScriptRoot -Parent           # repo root
$profileDir = Join-Path $env:LOCALAPPDATA 'anyclaude\profile'
$claudeConfigDir = Join-Path $profileDir 'claude-config'
$coworkDir  = Join-Path $profileDir 'cowork-user-files'
$desktopConfig = Join-Path $profileDir 'claude_desktop_config.json'
$cfg        = Join-Path $root 'config.json'
$launcherErrorLog = Join-Path $profileDir 'launcher-error.log'
$resolverPath = Join-Path $PSScriptRoot 'claude-install.ps1'

trap {
    [System.IO.Directory]::CreateDirectory($profileDir) | Out-Null
    $failure = @(
        (Get-Date).ToString('o')
        $_.Exception.Message
        $_.InvocationInfo.PositionMessage
    ) -join [Environment]::NewLine
    [System.IO.File]::WriteAllText($launcherErrorLog, $failure)
    exit 1
}

if (Test-Path -LiteralPath $launcherErrorLog) {
    Remove-Item -LiteralPath $launcherErrorLog -Force
}
if (-not (Test-Path -LiteralPath $resolverPath)) {
    throw "Claude Desktop install resolver not found: $resolverPath"
}
. $resolverPath

if (-not (Test-Path $cfg)) { throw "config.json not found. Copy one from examples\ first (see README)." }
$config = Get-Content $cfg -Raw | ConvertFrom-Json
$port = $config.port
if (-not $port) { $port = 8801 }
$keyEnv = $config.upstream.key_env
if (-not [Environment]::GetEnvironmentVariable($keyEnv, 'Process')) {
    $storedKey = [Environment]::GetEnvironmentVariable($keyEnv, 'User')
    if ($storedKey) { [Environment]::SetEnvironmentVariable($keyEnv, $storedKey, 'Process') }
}
if (-not [Environment]::GetEnvironmentVariable($keyEnv, 'Process')) {
    throw "$keyEnv is not set. Add the provider key as a user environment variable (see README)."
}

# --- 1. proxy up? start it hidden if not ---
$listening = Get-NetTCPConnection -State Listen -LocalPort $port -EA SilentlyContinue
if (-not $listening) {
    $pyw = (Get-Command pythonw.exe -EA SilentlyContinue).Source
    if (-not $pyw) { throw "pythonw.exe not on PATH — install Python 3.9+." }
    Start-Process -FilePath $pyw -ArgumentList "`"$root\proxy.py`"" -WindowStyle Hidden
}

$healthy = $false
for ($i = 0; $i -lt 10; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 2
        if ($health.status -eq 'ok') { $healthy = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}
if (-not $healthy) { throw "anyclaude proxy on port $port did not pass /health. Check the provider key and proxy.log." }

# --- 2. resolve the current official updater-managed Claude Desktop build ---
$claude = Resolve-ClaudeDesktopInstall
$exe = $claude.ExecutablePath

# Warn (don't silently no-op) if a Desktop update dropped the isolation env var.
$asar = $claude.AsarPath
if ((Test-Path $asar) -and -not ([System.IO.File]::ReadAllText($asar, [System.Text.Encoding]::UTF8)).Contains('CLAUDE_USER_DATA_DIR')) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "Claude Desktop $($claude.DisplayVersion) no longer supports CLAUDE_USER_DATA_DIR.`n`n" +
        "anyclaude cannot isolate the second instance on this build. See the repo README.",
        'anyclaude', 'OK', 'Warning') | Out-Null
    exit 1
}

New-Item -ItemType Directory -Force -Path $profileDir, $claudeConfigDir, $coworkDir | Out-Null

# The isolated CLAUDE_CONFIG_DIR is meant to separate auth and Desktop state, but it also hides the
# skills and subagents already installed in ~/.claude: they simply do not exist in this profile, so
# Claude Code inside the anyclaude window silently has none of them. Link them back rather than copy,
# so the originals stay the single source of truth and edits land in both instances. Junctions are used
# because they need no elevation or Developer Mode, unlike symlinks.
#
# settings.json is deliberately NOT linked. It commonly pins an Anthropic-only model name, which the
# gateway provider does not serve. Set ANYCLAUDE_SHARE_CLAUDE_CODE=0 for a fully sealed profile.
if ($env:ANYCLAUDE_SHARE_CLAUDE_CODE -ne '0') {
    foreach ($share in 'skills', 'agents') {
        $shareSource = Join-Path $HOME ".claude\$share"
        $shareTarget = Join-Path $claudeConfigDir $share
        if (-not (Test-Path $shareSource)) { continue }
        $existing = Get-Item $shareTarget -Force -ErrorAction SilentlyContinue
        # Re-point a stale link, but never clobber a real directory the user put here.
        if ($existing -and $existing.LinkType) { $existing.Delete() }
        elseif ($existing) { continue }
        New-Item -ItemType Junction -Path $shareTarget -Target $shareSource -ErrorAction SilentlyContinue | Out-Null
    }
}

# Keep embedded Claude Code and Cowork state out of the subscription profile. Preserve a custom
# Cowork path; migrate only the default ~/Claude location into the isolated anyclaude profile.
if (Test-Path $desktopConfig) {
    $desktop = Get-Content $desktopConfig -Raw | ConvertFrom-Json
} else {
    $desktop = [PSCustomObject]@{}
}
$currentCowork = $desktop.coworkUserFilesPath
$defaultCowork = Join-Path $HOME 'Claude'
if (-not $currentCowork -or [string]::Equals(
        [System.IO.Path]::GetFullPath($currentCowork),
        [System.IO.Path]::GetFullPath($defaultCowork),
        [System.StringComparison]::OrdinalIgnoreCase)) {
    $desktop | Add-Member -NotePropertyName coworkUserFilesPath -NotePropertyValue $coworkDir -Force
    $temporaryConfig = "$desktopConfig.tmp"
    $desktop | ConvertTo-Json -Depth 32 | Set-Content -Encoding UTF8 $temporaryConfig
    Move-Item -Force $temporaryConfig $desktopConfig
}

# --- 3. self-heal the gateway config from the repo seed (no secrets in it) ---
$seed = Join-Path $root 'configLibrary'
$live = Join-Path $profileDir 'configLibrary'
if ((Test-Path $seed) -and -not (Test-Path (Join-Path $live '_meta.json'))) {
    New-Item -ItemType Directory -Force -Path $live | Out-Null
    Copy-Item (Join-Path $seed '*') -Destination $live -Force
}

# --- 4. launch isolated instance (UseShellExecute=false so env vars reach the child) ---
$launchStarted = Get-Date
$existingWindowPids = @(
    Get-Process -Name 'claude' -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero } |
        Select-Object -ExpandProperty Id
)
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $exe
$psi.UseShellExecute = $false
$psi.EnvironmentVariables['CLAUDE_USER_DATA_DIR'] = $profileDir
$psi.EnvironmentVariables['CLAUDE_CONFIG_DIR'] = $claudeConfigDir
$proc = [System.Diagnostics.Process]::Start($psi)

# --- 5. give it its own taskbar button (AUMID lives on the HWND; re-applied each launch) ---
$sep = Join-Path $PSScriptRoot 'separate-taskbar.ps1'
if (Test-Path $sep) {
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        $proc.Refresh()
        $windowProcess = if (-not $proc.HasExited -and $proc.MainWindowHandle -ne [IntPtr]::Zero) {
            $proc
        } else {
            Get-Process -Name 'claude' -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.Id -notin $existingWindowPids -and
                    $_.StartTime -ge $launchStarted -and
                    $_.MainWindowHandle -ne [IntPtr]::Zero
                } |
                Select-Object -First 1
        }
        if ($windowProcess) {
            & $sep -TargetPid $windowProcess.Id -IconResource $claude.IconResource
            break
        }
    }
}
