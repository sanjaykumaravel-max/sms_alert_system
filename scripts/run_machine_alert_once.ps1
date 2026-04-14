$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$systemPython = "C:\Users\sanjay\AppData\Local\Programs\Python\Python313\python.exe"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$mainPy = Join-Path $repoRoot "src\main.py"
$sitePackages = Join-Path $repoRoot ".venv\Lib\site-packages"
$portableExe = Join-Path $repoRoot "dist_portable\MiningMaintenanceSystem.exe"
$onedirExe = Join-Path $repoRoot "dist\sms_alert_app\MiningMaintenanceSystem.exe"

$pythonCmd = $null
if (Test-Path $venvPython) {
    $pythonCmd = $venvPython
} elseif (Test-Path $systemPython) {
    $pythonCmd = $systemPython
} else {
    $pythonCmd = "python"
}

$existingPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Process")
if ($existingPath) {
    $env:PYTHONPATH = "$sitePackages;$repoRoot;$existingPath"
} else {
    $env:PYTHONPATH = "$sitePackages;$repoRoot"
}

& $pythonCmd $mainPy --machine-alert-once
if ($LASTEXITCODE -eq 0) {
    exit 0
}

if (Test-Path $portableExe) {
    & $portableExe --machine-alert-once
    exit $LASTEXITCODE
}

if (Test-Path $onedirExe) {
    & $onedirExe --machine-alert-once
    exit $LASTEXITCODE
}

exit $LASTEXITCODE
