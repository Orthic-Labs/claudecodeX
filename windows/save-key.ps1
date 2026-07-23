<#
.SYNOPSIS
  Save a provider key as a persistent user environment variable.

.DESCRIPTION
  Reads the value as a secure string so it is never echoed, never stored in
  PowerShell history, and never written into this repository. Writes it to the
  User scope, which survives reboots and is what the Windows launcher reads.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File windows\save-key.ps1 DASHSCOPE_API_KEY
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidatePattern('^[A-Za-z0-9_]+$')]
  [string] $Name
)

$ErrorActionPreference = 'Stop'

$secure = Read-Host -Prompt "Paste the value for $Name (input hidden)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if ([string]::IsNullOrWhiteSpace($value)) {
  Write-Error 'No value entered, nothing written.'
}

[Environment]::SetEnvironmentVariable($Name, $value, 'User')
Set-Item -Path "Env:$Name" -Value $value

Write-Host "Saved $Name to the User environment."
Write-Host 'It is live in this session. Other running apps, including Claude Desktop and Codex, need a restart to see it.'
Write-Host 'Then start the proxy: python proxy.py'
