# claudecodex installer (Windows). Creates the Desktop + Start Menu shortcut and
# registers the proxy to start hidden at login. Re-runnable (idempotent).
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$resolverPath = Join-Path $PSScriptRoot 'claude-install.ps1'

if (-not (Test-Path -LiteralPath $resolverPath)) {
    throw "Claude Desktop install resolver not found: $resolverPath"
}
. $resolverPath
$claude = Resolve-ClaudeDesktopInstall

if (-not (Test-Path (Join-Path $root 'config.json'))) {
    Write-Warning "No config.json yet — copy one from examples\ and set your key's env var first (see README)."
}

$vbs   = Join-Path $PSScriptRoot 'claudecodex.vbs'
$icon  = $claude.IconResource
$sh    = New-Object -ComObject WScript.Shell

$desktop = [Environment]::GetFolderPath('Desktop')
$programs = [Environment]::GetFolderPath('Programs')
foreach ($dir in @($desktop, $programs)) {
    $lnk = $sh.CreateShortcut((Join-Path $dir 'claudecodex.lnk'))
    $lnk.TargetPath       = Join-Path $env:WINDIR 'System32\wscript.exe'
    $lnk.Arguments        = """$vbs"""
    $lnk.IconLocation     = $icon
    $lnk.Description       = 'Claude Desktop on your gateway model (claudecodex)'
    $lnk.WorkingDirectory = $root
    $lnk.Save()
    Write-Host "shortcut -> $dir\claudecodex.lnk"
}

# Start the proxy hidden at login (a .vbs in the Startup folder, windowless).
$startup = [Environment]::GetFolderPath('Startup')
$pxVbs = Join-Path $startup 'claudecodex-proxy.vbs'
@"
Set sh = CreateObject("WScript.Shell")
sh.Run "pythonw.exe ""$root\proxy.py""", 0, False
"@ | Set-Content -Encoding ASCII $pxVbs
Write-Host "proxy autostart -> $pxVbs"
Write-Host "`nDone. Set your API key env var (see README), then click the claudecodex shortcut."
