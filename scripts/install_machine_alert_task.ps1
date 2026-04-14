param(
    [int]$IntervalMinutes = 5,
    [string]$ExecutablePath = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$taskName = "MiningMaintenanceSystemMachineAlerts"
$runScript = Join-Path $repoRoot "scripts\run_machine_alert_once.ps1"

function Resolve-RunnerPath {
    param([string]$PreferredPath)

    if ($PreferredPath) {
        return (Resolve-Path $PreferredPath).Path
    }

    return "powershell-script"
}

$runnerPath = Resolve-RunnerPath -PreferredPath $ExecutablePath
if ($runnerPath.ToLower().EndsWith(".exe")) {
    $taskCommand = "`"$runnerPath`" --machine-alert-once"
} else {
    $taskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runScript`""
}

Write-Host "Installing scheduled task '$taskName' with interval $IntervalMinutes minute(s)..."
schtasks /Create /TN $taskName /TR $taskCommand /SC MINUTE /MO $IntervalMinutes /F
Write-Host "Task installed."
