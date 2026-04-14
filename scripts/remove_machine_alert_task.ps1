$ErrorActionPreference = "Stop"
$taskName = "MiningMaintenanceSystemMachineAlerts"

Write-Host "Removing scheduled task '$taskName'..."
schtasks /Delete /TN $taskName /F
Write-Host "Task removed."
