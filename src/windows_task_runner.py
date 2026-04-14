from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

try:
    from .app_paths import is_frozen
    from .settings_store import load_settings
except Exception:
    from app_paths import is_frozen
    from settings_store import load_settings


TASK_NAME = "MiningMaintenanceSystemMachineAlerts"


def _normalize_task_timestamp(raw_value: Any) -> str | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    lowered = value.lower()
    if lowered in {"n/a", "never", "0"}:
        return None
    if value.startswith("0001-01-01"):
        return None
    return value


def _query_task_with_powershell() -> Dict[str, Any] | None:
    script = rf"""
$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction Stop
$info = $task | Get-ScheduledTaskInfo
[PSCustomObject]@{{
    installed = $true
    task_name = $task.TaskName
    state = [string]$task.State
    last_run_time = if ($info.LastRunTime -and $info.LastRunTime.Year -gt 1900) {{ $info.LastRunTime.ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
    last_result = [string]$info.LastTaskResult
    next_run_time = if ($info.NextRunTime -and $info.NextRunTime.Year -gt 1900) {{ $info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
    command = (($task.Actions | ForEach-Object {{ $_.Execute }}) -join '; ')
    arguments = (($task.Actions | ForEach-Object {{ $_.Arguments }}) -join ' ')
}} | ConvertTo-Json -Compress
"""
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout.strip() or "{}")
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    payload["installed"] = bool(payload.get("installed", False))
    payload["last_run_time"] = _normalize_task_timestamp(payload.get("last_run_time"))
    payload["next_run_time"] = _normalize_task_timestamp(payload.get("next_run_time"))
    payload["last_result"] = str(payload.get("last_result") or "").strip() or None
    return payload


def _repo_main_path() -> Path:
    return Path(__file__).resolve().parent / "main.py"


def _repo_root() -> Path:
    return _repo_main_path().parent.parent


def _runner_script_path() -> Path:
    return _repo_root() / "scripts" / "run_machine_alert_once.ps1"


def task_command() -> str:
    if is_frozen():
        return f'"{Path(sys.executable).resolve()}" --machine-alert-once'
    script_path = _runner_script_path().resolve()
    return f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{script_path}"'


def install_machine_alert_task(interval_minutes: int | None = None) -> Dict[str, Any]:
    cfg = load_settings()
    interval = max(1, int(interval_minutes or cfg.get("machine_alert_interval_minutes", 5) or 5))
    command = [
        "schtasks",
        "/Create",
        "/TN",
        TASK_NAME,
        "/TR",
        task_command(),
        "/SC",
        "MINUTE",
        "/MO",
        str(interval),
        "/F",
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    success = completed.returncode == 0
    return {
        "success": success,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": " ".join(command),
    }


def remove_machine_alert_task() -> Dict[str, Any]:
    command = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    completed = subprocess.run(command, capture_output=True, text=True)
    success = completed.returncode == 0
    return {
        "success": success,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": " ".join(command),
    }


def query_machine_alert_task() -> Dict[str, Any]:
    powershell_result = _query_task_with_powershell()
    if powershell_result is not None:
        return {
            "success": True,
            "installed": bool(powershell_result.get("installed")),
            "state": powershell_result.get("state"),
            "last_run_time": powershell_result.get("last_run_time"),
            "last_result": powershell_result.get("last_result"),
            "next_run_time": powershell_result.get("next_run_time"),
            "command": powershell_result.get("command"),
            "arguments": powershell_result.get("arguments"),
            "stdout": json.dumps(powershell_result, ensure_ascii=False),
            "stderr": "",
        }

    command = ["schtasks", "/Query", "/TN", TASK_NAME]
    completed = subprocess.run(command, capture_output=True, text=True)
    success = completed.returncode == 0
    return {
        "success": success,
        "installed": success,
        "state": None,
        "last_run_time": None,
        "last_result": None,
        "next_run_time": None,
        "command": "",
        "arguments": "",
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
