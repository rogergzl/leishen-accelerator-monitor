# launcher.ps1 - LeiShen Monitor Launcher
param()

$scriptDir = $PSScriptRoot
$script = Join-Path $scriptDir "leishen_monitor.pyw"

# ============================================================
# 1. Find / Install Python
# ============================================================
function Find-Python {
    $candidates = @(
        "$scriptDir\python\python.exe",
        "$env:LocalAppData\Programs\Python\Python314\python.exe",
        "$env:LocalAppData\Programs\Python\Python313\python.exe",
        "$env:LocalAppData\Programs\Python\Python312\python.exe",
        "C:\Python314\python.exe", "C:\Python313\python.exe", "C:\Python312\python.exe"
    )
    foreach ($p in $candidates) { if (Test-Path $p) { return $p } }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Install-PythonEmbedded {
    Write-Host "  Python not found, downloading..." -ForegroundColor DarkYellow
    $pythonDir = Join-Path $scriptDir "python"
    $zipFile = Join-Path $scriptDir "python-embed.zip"
    $url = "https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip"
    try {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($winget) {
            Write-Host "  Trying winget..." -ForegroundColor DarkGray
            winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent 2>$null
            Start-Sleep 5
            $found = Find-Python
            if ($found) { return $found }
        }
    } catch {}
    Write-Host "  Downloading Python (~10MB)..." -ForegroundColor DarkGray
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $zipFile -UseBasicParsing
    Write-Host "  Extracting..." -ForegroundColor DarkGray
    Expand-Archive -Path $zipFile -DestinationPath $pythonDir -Force
    Remove-Item $zipFile -Force
    $pthFile = Join-Path $pythonDir "python312._pth"
    if (Test-Path $pthFile) {
        (Get-Content $pthFile) -replace '#import site', 'import site' | Set-Content $pthFile
    }
    $pyw = Join-Path $pythonDir "pythonw.exe"
    if (-not (Test-Path $pyw)) { Copy-Item (Join-Path $pythonDir "python.exe") $pyw }
    return Join-Path $pythonDir "python.exe"
}

# ============================================================
# 2. Check admin
# ============================================================
$isAdmin = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

# ============================================================
# 3. Banner
# ============================================================
$C = "Cyan"; $G = "Green"; $Y = "Yellow"; $R = "Red"; $W = "White"; $DG = "DarkGray"
Write-Host ""
Write-Host "  ==========================================" -ForegroundColor $C
Write-Host "    LeiShen Monitor v1.0" -ForegroundColor $W
Write-Host "  ==========================================" -ForegroundColor $C
Write-Host ""

# ============================================================
# 4. Find / Download Python
# ============================================================
$python = Find-Python
if (-not $python) {
    $python = Install-PythonEmbedded
}
if (-not $python) {
    Write-Host "  [FAIL] Cannot find or install Python." -ForegroundColor $R
    Write-Host "  Download manually: https://www.python.org/downloads/" -ForegroundColor $Y
    Read-Host "  Press Enter to exit"
    exit 1
}
Write-Host "  [OK]" -NoNewline -ForegroundColor $G
Write-Host " Python ready" -ForegroundColor $W
Write-Host ""

# ============================================================
# 5. Launch
# ============================================================
if ($isAdmin) {
    # Already admin: run directly in this window
    & $python $script --console 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] Python exited with code $LASTEXITCODE" -ForegroundColor $R
    }
    Read-Host "  Press Enter to exit"
} else {
    Write-Host "  [*] Requesting admin rights..." -ForegroundColor $Y
    Write-Host "  [*] This window will close in 3 seconds." -ForegroundColor $DG
    try {
        Start-Process -FilePath $python -ArgumentList "`"$script`" --console" -Verb RunAs
    } catch {
        Write-Host "  [FAIL] UAC cancelled: $_" -ForegroundColor $R
        Read-Host "  Press Enter to exit"
    }
    Start-Sleep 3
}
