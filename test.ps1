# test.ps1 - Launch LeiShen Monitor GUI
$script = Join-Path $PSScriptRoot "leishen_monitor.pyw"
$pythonw = "$env:LocalAppData\Programs\Python\Python314\pythonw.exe"

if (-not (Test-Path $pythonw)) {
    $pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
}
if (-not $pythonw) {
    Write-Host "ERROR: pythonw.exe not found" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$isAdmin = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    Start-Process -FilePath $pythonw -ArgumentList $script
} else {
    Start-Process -FilePath $pythonw -ArgumentList $script -Verb RunAs
}
