' Silent launcher — runs launch.ps1 with no console window (WindowStyle 0).
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
ps1 = fso.GetParentFolderName(WScript.ScriptFullName) & "\launch.ps1"
powerShell = sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\PowerShell\7\pwsh.exe"
If Not fso.FileExists(powerShell) Then
    Set processEnv = sh.Environment("Process")
    systemModules = sh.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\WindowsPowerShell\v1.0\Modules"
    processEnv("PSModulePath") = systemModules & ";" & processEnv("PSModulePath")
    powerShell = sh.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\WindowsPowerShell\v1.0\powershell.exe"
End If

launchExitCode = sh.Run("""" & powerShell & """ -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """", 0, True)
If launchExitCode <> 0 Then
    errorLog = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\claudecodex\profile\launcher-error.log"
    MsgBox "claudecodex could not start. See " & errorLog & " for the exact error.", vbCritical, "claudecodex"
End If
WScript.Quit launchExitCode
