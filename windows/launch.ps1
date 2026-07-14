# anyclaude launcher (Windows) — starts the proxy if needed, then opens an isolated
# Claude Desktop instance pointed at it, with its own taskbar button.
$ErrorActionPreference = 'Stop'
$root       = Split-Path $PSScriptRoot -Parent           # repo root
$profileDir = Join-Path $env:LOCALAPPDATA 'anyclaude\profile'
$cfg        = Join-Path $root 'config.json'

if (-not (Test-Path $cfg)) { throw "config.json not found. Copy one from examples\ first (see README)." }
$port = (Get-Content $cfg -Raw | ConvertFrom-Json).port
if (-not $port) { $port = 8801 }

# --- 1. proxy up? start it hidden if not ---
$listening = Get-NetTCPConnection -State Listen -LocalPort $port -EA SilentlyContinue
if (-not $listening) {
    $pyw = (Get-Command pythonw.exe -EA SilentlyContinue).Source
    if (-not $pyw) { throw "pythonw.exe not on PATH — install Python 3.9+." }
    Start-Process -FilePath $pyw -ArgumentList "`"$root\proxy.py`"" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

# --- 2. resolve Claude Desktop (path carries the version; look it up at runtime) ---
$pkg = Get-AppxPackage -Name 'Claude'
if (-not $pkg) { throw 'Claude Desktop is not installed.' }
$exe = Join-Path $pkg.InstallLocation 'app\Claude.exe'

# Warn (don't silently no-op) if a Desktop update dropped the isolation env var.
$asar = Join-Path $pkg.InstallLocation 'app\resources\app.asar'
if ((Test-Path $asar) -and -not ([System.IO.File]::ReadAllText($asar, [System.Text.Encoding]::UTF8)).Contains('CLAUDE_USER_DATA_DIR')) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "Claude Desktop $($pkg.Version) no longer supports CLAUDE_USER_DATA_DIR.`n`n" +
        "anyclaude cannot isolate the second instance on this build. See the repo README.",
        'anyclaude', 'OK', 'Warning') | Out-Null
    exit 1
}

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

# --- 3. self-heal the gateway config from the repo seed (no secrets in it) ---
$seed = Join-Path $root 'configLibrary'
$live = Join-Path $profileDir 'configLibrary'
if ((Test-Path $seed) -and -not (Test-Path (Join-Path $live '_meta.json'))) {
    New-Item -ItemType Directory -Force -Path $live | Out-Null
    Copy-Item (Join-Path $seed '*') -Destination $live -Force
}

# --- 4. launch isolated instance (UseShellExecute=false so env vars reach the child) ---
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $exe
$psi.UseShellExecute = $false
$psi.EnvironmentVariables['CLAUDE_USER_DATA_DIR'] = $profileDir
$proc = [System.Diagnostics.Process]::Start($psi)

# --- 5. give it its own taskbar button (AUMID lives on the HWND; re-applied each launch) ---
$sep = Join-Path $PSScriptRoot 'separate-taskbar.ps1'
if (Test-Path $sep) {
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        $proc.Refresh()
        if ($proc.HasExited) { break }
        if ($proc.MainWindowHandle -ne [IntPtr]::Zero) { & $sep -TargetPid $proc.Id; break }
    }
}
