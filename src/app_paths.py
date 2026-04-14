from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_DIR_NAME = "MiningMaintenanceSystem"

_SRC_DIR = Path(__file__).resolve().parent
_DEV_PROJECT_ROOT = _SRC_DIR.parent
_BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", _DEV_PROJECT_ROOT))
_IS_FROZEN = bool(getattr(sys, "frozen", False))


def is_frozen() -> bool:
    return _IS_FROZEN


def bundle_root() -> Path:
    return _BUNDLE_ROOT


def executable_dir() -> Path:
    if _IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return _DEV_PROJECT_ROOT


def app_data_root() -> Path:
    if not _IS_FROZEN:
        return _DEV_PROJECT_ROOT
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    root = local_app_data / APP_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def logs_dir() -> Path:
    path = app_data_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    path = app_data_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_path(*parts: str) -> Path:
    target = data_dir().joinpath(*parts)
    if target.exists() or not parts:
        return target

    source = resource_path("data", *parts)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_file():
            shutil.copy2(source, target)
        elif source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
    except Exception:
        pass
    return target


def exports_dir() -> Path:
    path = data_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def env_file_candidates() -> list[Path]:
    candidates: list[Path] = []

    exe_env = executable_dir() / ".env"
    candidates.append(exe_env)

    app_env = app_data_root() / ".env"
    if app_env not in candidates:
        candidates.append(app_env)

    dev_env = _DEV_PROJECT_ROOT / ".env"
    if dev_env not in candidates:
        candidates.append(dev_env)

    bundle_env = resource_path(".env")
    if bundle_env not in candidates:
        candidates.append(bundle_env)

    return candidates
