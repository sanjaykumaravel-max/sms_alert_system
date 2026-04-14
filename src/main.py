"""
SMS Alert App Main Entry Point with Backend Optimizations.

This module provides the main entry point for the SMS Alert application
with comprehensive backend optimizations including:

- Async/await patterns throughout the application
- Redis caching layer for frequently accessed data
- Background job processing with Celery
- Database connection pooling and query optimization
- CDN integration for static assets
"""

import sys
import os
import logging
import argparse
from pathlib import Path
from typing import List, Optional, Dict, Any
import subprocess
import time
import json

# Ensure src and project root are on sys.path for both package and module runs
_this_src_dir = Path(__file__).resolve().parent
_project_root = _this_src_dir.parent
if str(_this_src_dir) not in sys.path:
    sys.path.insert(0, str(_this_src_dir))
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from .app_paths import app_data_root, data_path
except Exception:
    from app_paths import app_data_root, data_path


def _load_ui_mode_preference() -> str:
    """Read persisted appearance mode from env/settings files."""
    env_mode = str(os.environ.get("UI_MODE", "")).strip().lower()
    if env_mode in ("dark", "light", "system"):
        return env_mode

    candidates = [
        data_path("settings.json"),
    ]
    for p in candidates:
        try:
            if not p.exists():
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            mode = str(data.get("ui_mode", "")).strip().lower()
            if mode in ("dark", "light", "system"):
                return mode
        except Exception:
            continue

    return "dark"

# Optional Sentry integration
try:
    import importlib
    sentry_sdk = importlib.import_module("sentry_sdk")
    _sentry_dsn = os.environ.get("SENTRY_DSN")
    if _sentry_dsn:
        sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0.05)
        logging.getLogger().info("Sentry initialized")
except Exception:
    # not fatal if sentry not available
    pass

# Optional APScheduler background scheduler
_SCHEDULER = None
try:
    from apscheduler.schedulers.background import BackgroundScheduler # type: ignore
    _SCHEDULER = BackgroundScheduler()
    _SCHEDULER.start()
except Exception:
    _SCHEDULER = None

# Try relative import when running as a package; fall back to absolute
# import when running the module as a script (no package context).
try:
    from .ui import theme as theme_mod
except Exception:
    import sys as _sys
    from pathlib import Path as _Path
    _src_dir = _Path(__file__).resolve().parent
    if str(_src_dir) not in _sys.path:
        _sys.path.insert(0, str(_src_dir))
    from ui import theme as theme_mod

# Add src to path for imports
def _ensure_src_in_path() -> None:
    """Ensure the src directory is in the Python path."""
    src_dir = Path(__file__).resolve().parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

async def initialize_services() -> None:
    """Initialize backend services asynchronously."""
    # central logging configuration
    _ensure_src_in_path()
    try:
        from logger import configure_logging
        configure_logging()
    except Exception:
        # fallback
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not os.environ.get("VIRTUAL_ENV"):
        logging.warning("Virtual environment not activated. Recommended: run with your project's venv Python.")

    # Initialize backend services
    try:
        # Initialize database
        from models import init_db, cache
        await init_db()
        await cache.initialize()
        logging.info("Database and cache initialized")

        # Initialize CDN service
        from cdn_service import cdn_service
        logging.info("CDN service initialized")

        # Initialize async SMS service
        from sms_service_async import initialize_sms_service
        await initialize_sms_service()
        logging.info("Async SMS service initialized")

    except Exception as exc:
        logging.exception("Failed to initialize backend services: %s", exc)
        raise

async def main_async(args) -> None:
    """
    Async main entry point for the SMS Alert desktop application GUI.

    Args:
        args: Parsed arguments.
    """
    # central logging configuration
    _ensure_src_in_path()
    try:
        from logger import configure_logging
        configure_logging()
    except Exception:
        # fallback
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not os.environ.get("VIRTUAL_ENV"):
        logging.warning("Virtual environment not activated. Recommended: run with your project's venv Python.")

    # Start backend initialization in background so UI can show a splash
    import threading
    try:
        from config import settings, APP_EXECUTABLE_NAME, APP_NAME
    except Exception:
        settings = None
        APP_EXECUTABLE_NAME = "MiningMaintenanceSystem"
        APP_NAME = "Mining Maintenance System"

    # Optionally auto-start a local API server used by the UI. Controlled
    # via environment variable `AUTO_START_API_SERVER` (defaults to '1').
    api_server_proc = None
    api_log_file = None
    try:
        auto_start = os.environ.get('AUTO_START_API_SERVER', None)
        if auto_start is None and settings is not None:
            auto_start = '1' if getattr(settings, 'AUTO_START_API_SERVER', True) else '0'
        if str(auto_start).lower() not in ('0', 'false', 'no'):
            try:
                server_log = app_data_root() / 'server.log'
                api_log_file = open(server_log, 'ab')
                env = os.environ.copy()
                # honor CLI port and host if provided
                port_str = str(getattr(args, 'port', os.environ.get('PORT', str(getattr(settings, 'API_PORT', 8000)))))
                host_str = str(getattr(args, 'host', os.environ.get('HOST', str(getattr(settings, 'API_HOST', '0.0.0.0')))))
                env['PORT'] = port_str

                # Choose server engine: prefer uvicorn if available and requested
                requested = os.environ.get('API_SERVER_ENGINE')
                engine = None
                try:
                    if requested:
                        engine = requested.lower()
                    else:
                        # prefer uvicorn when installed
                        import importlib.util as _ils
                        engine = 'uvicorn' if _ils.find_spec('uvicorn') else 'flask'
                except Exception:
                    engine = 'flask'

                if engine == 'uvicorn':
                    # start uvicorn with the async app (src.server_async:app)
                    api_server_proc = subprocess.Popen([
                        sys.executable, '-m', 'uvicorn', 'src.server_async:app',
                        '--host', host_str, '--port', port_str, '--log-level', 'info'
                    ], env=env, stdout=api_log_file, stderr=api_log_file)
                    logging.info('Started uvicorn API server (pid=%s) on %s:%s, logging to %s', api_server_proc.pid, host_str, port_str, server_log)
                else:
                    api_server_proc = subprocess.Popen([
                        sys.executable, '-u', '-m', 'src.server'
                    ], env=env, stdout=api_log_file, stderr=api_log_file)
                    logging.info('Started Flask API server (pid=%s), logging to %s', api_server_proc.pid, server_log)

                # register atexit handler to brutally kill the subprocess if the main process crashes
                import atexit
                def cleanup_proc():
                    if api_server_proc:
                        try:
                            api_server_proc.terminate()
                            api_server_proc.wait(timeout=1)
                        except Exception:
                            try:
                                api_server_proc.kill()
                            except Exception:
                                pass
                atexit.register(cleanup_proc)

                # give server a moment to start
                time.sleep(0.25)
            except Exception:
                logging.exception('Failed to start local API server')
    except Exception:
        api_server_proc = None

    init_state = {'done': False}

    def _init_bg():
        try:
            import asyncio as _asyncio
            # Prefer centralized service lifecycle which initializes DB, SMS, etc.
            try:
                try:
                    from src.services import start_services
                except Exception:
                    from services import start_services
                start_services()
            except Exception:
                # fallback to legacy initializer
                _asyncio.run(initialize_services())
        except Exception:
            pass
        finally:
            init_state['done'] = True

    t = threading.Thread(target=_init_bg, daemon=True)
    t.start()

    # Run GUI application (show splash while backend initializes)
    try:
        from ui.login import LoginWindow
        from ui.dashboard import Dashboard
        from ui.mine_details import MineSetupFrame
        import customtkinter as ctk
        try:
            from mine_store import get_active_mine
        except Exception:
            get_active_mine = None
    except Exception as exc:
        logging.exception("Failed to import UI modules: %s", exc)
        raise

    try:
        ctk.set_appearance_mode(_load_ui_mode_preference())
    except Exception:
        pass

    root = ctk.CTk()
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_EXECUTABLE_NAME}.Desktop")
    except Exception:
        pass

    try:
        active_mine_name = str(((get_active_mine() or {}) if callable(get_active_mine) else {}).get("mine_name") or "").strip()
    except Exception:
        active_mine_name = ""
    root.title(f"{APP_NAME} - {active_mine_name}" if active_mine_name else APP_NAME)
    root.geometry("1440x900")
    root.minsize(1200, 760)
    try:
        if os.name == "nt":
            root.state("zoomed")
    except Exception:
        pass
    root.resizable(True, True)
    root.lift()
    root.focus_force()

    # Install global exception handler that surfaces friendly UI message and logs
    try:
        from logger import install_thread_excepthook
        install_thread_excepthook()
    except Exception:
        logging.exception('Failed to install thread excepthook')

    import sys as _sys
    from tkinter import messagebox as _msgbox

    def _show_fatal(exc_type, exc_value, exc_tb):
        try:
            logging.getLogger().exception('Unhandled exception', exc_info=(exc_type, exc_value, exc_tb))
        except Exception:
            pass
        try:
            _msgbox.showerror('Application Error', 'An unexpected error occurred. The error has been logged. Please restart the application.')
        except Exception:
            pass

    try:
        _sys.excepthook = _show_fatal
    except Exception:
        pass

    # Keyboard shortcuts: Ctrl+Q quit, Ctrl+F find (if dashboard implements), Ctrl+N new
    try:
        def _on_quit(ev=None):
            try:
                root.quit()
            except Exception:
                root.destroy()

        root.bind_all('<Control-q>', lambda e: _on_quit(e))
        root.bind_all('<Control-Q>', lambda e: _on_quit(e))

        def _on_find(ev=None):
            try:
                # if dashboard implements `focus_search()` call it
                if hasattr(root, 'dashboard') and getattr(root, 'dashboard') is not None and hasattr(root.dashboard, 'focus_search'):
                    root.dashboard.focus_search()
            except Exception:
                pass

        root.bind_all('<Control-f>', lambda e: _on_find(e))
    except Exception:
        pass

    # Simple splash overlay
    splash = ctk.CTkFrame(root, fg_color=theme_mod.SIMPLE_PALETTE.get('card', '#0b1220'))
    splash.place(relx=0.5, rely=0.5, anchor='center')
    splash_label = ctk.CTkLabel(splash, text="Initializing services...", font=("Arial", 14))
    splash_label.pack(padx=20, pady=10)
    try:
        from tkinter import ttk
        pb = ttk.Progressbar(splash, mode='indeterminate', length=200)
        pb.pack(padx=10, pady=(0,10))
        pb.start(10)
    except Exception:
        pb = None

    def _poll_init():
        if init_state.get('done'):
            try:
                if pb:
                    pb.stop()
            except Exception:
                pass
            splash.destroy()
        else:
            root.after(250, _poll_init)

    root.after(100, _poll_init)

    def show_dashboard(user):
        # Clear root
        for widget in root.winfo_children():
            widget.destroy()
        # Create dashboard
        dashboard = Dashboard(root, user)
        dashboard.pack(fill="both", expand=True)
        # Dashboard will lazily load content as needed

    def on_login_success(user):
        for widget in root.winfo_children():
            widget.destroy()
        mine_setup = MineSetupFrame(root, user=user, on_complete=show_dashboard)
        mine_setup.pack(fill="both", expand=True)

    if args.user:
        logging.info("Opening Dashboard for user: %s", args.user)
        # Create a mock user dict
        user: Dict[str, str] = {"name": args.user, "role": "admin", "username": args.user}
        on_login_success(user)
    else:
        # Show login frame
        login = LoginWindow(root, on_success=on_login_success)
        login.pack(fill="both", expand=True)

    root.mainloop()

    # Clean up: stop API server started by this process (best-effort)
    try:
        try:
            try:
                from src.services import stop_services
            except Exception:
                from services import stop_services
            stop_services()
        except Exception:
            pass
        if api_server_proc:
            try:
                logging.info('Shutting down local API server (pid=%s)', api_server_proc.pid)
                api_server_proc.terminate()
                api_server_proc.wait(timeout=2)
            except Exception:
                try:
                    api_server_proc.kill()
                except Exception:
                    pass
        if api_log_file:
            try:
                api_log_file.close()
            except Exception:
                pass
            # shutdown scheduler
            try:
                if _SCHEDULER is not None:
                    _SCHEDULER.shutdown(wait=False)
            except Exception:
                pass
    except Exception:
        pass

def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point - wraps async main for compatibility."""
    import asyncio

    # Parse args first
    try:
        from config import APP_EXECUTABLE_NAME, APP_NAME
    except Exception:
        APP_EXECUTABLE_NAME = "MiningMaintenanceSystem"
        APP_NAME = "Mining Maintenance System"

    parser = argparse.ArgumentParser(prog=APP_EXECUTABLE_NAME, description=f"{APP_NAME} desktop app")
    parser.add_argument("--user", "-u", help="Open dashboard for given user")
    parser.add_argument("--server", action="store_true", help="Run async web server instead of GUI")
    parser.add_argument("--machine-alert-once", action="store_true", help="Run one automatic machine SMS scan and exit")
    parser.add_argument("--machine-alert-runner", action="store_true", help="Run the automatic machine SMS loop without opening the GUI")
    parser.add_argument("--install-machine-alert-task", action="store_true", help="Install the Windows scheduled task for background machine alerts")
    parser.add_argument("--remove-machine-alert-task", action="store_true", help="Remove the Windows scheduled task for background machine alerts")
    parser.add_argument("--machine-alert-task-status", action="store_true", help="Show whether the Windows scheduled task is installed")
    parser.add_argument("--task-interval-minutes", type=int, default=None, help="Override interval when installing the machine alert task")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    args = parser.parse_args(argv)

    if args.machine_alert_once:
        try:
            from machine_alert_runner import run_machine_alert_scan
        except Exception:
            from src.machine_alert_runner import run_machine_alert_scan
        summary = run_machine_alert_scan()
        logging.info("Machine alert one-shot completed: %s", summary)
        return

    if args.machine_alert_runner:
        try:
            from machine_alert_runner import run_machine_alert_loop
        except Exception:
            from src.machine_alert_runner import run_machine_alert_loop
        run_machine_alert_loop()
        return

    if args.install_machine_alert_task:
        try:
            from windows_task_runner import install_machine_alert_task
        except Exception:
            from src.windows_task_runner import install_machine_alert_task
        result = install_machine_alert_task(args.task_interval_minutes)
        print(result.get("stdout") or result.get("stderr") or result)
        return

    if args.remove_machine_alert_task:
        try:
            from windows_task_runner import remove_machine_alert_task
        except Exception:
            from src.windows_task_runner import remove_machine_alert_task
        result = remove_machine_alert_task()
        print(result.get("stdout") or result.get("stderr") or result)
        return

    if args.machine_alert_task_status:
        try:
            from windows_task_runner import query_machine_alert_task
        except Exception:
            from src.windows_task_runner import query_machine_alert_task
        result = query_machine_alert_task()
        print(result.get("stdout") or result.get("stderr") or result)
        return

    if args.server:
        # For server mode
        asyncio.run(initialize_services())

        # Now start the server
        logging.info("Starting async web server on %s:%d", args.host, args.port)
        try:
            import importlib
            if importlib.util.find_spec("uvicorn") is not None:
                try:
                    from src.server_async import app as asgi_app
                except Exception:
                    from server_async import app as asgi_app
                uvicorn = importlib.import_module("uvicorn")
                uvicorn.run(
                    asgi_app,
                    host=args.host,
                    port=args.port,
                    log_level="info"
                )
            else:
                logging.warning("uvicorn not installed; falling back to Flask server.")
                try:
                    from src.server import app as flask_app
                except Exception:
                    from server import app as flask_app
                flask_app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
        except Exception as exc:
            logging.exception("Failed to start web server: %s", exc)
            raise
    else:
        # For GUI mode
        asyncio.run(main_async(args))

if __name__ == "__main__":
    main()
