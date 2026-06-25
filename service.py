"""Run Camera Monitor as a Windows service (pywin32).

The service reads its settings from the ProgramData config file written by
`--install-service` (or `--write-config`), so it needs no command-line arguments.

Control commands (run from an *administrator* terminal):
    CameraMonitor.exe --install-service
    CameraMonitor.exe --start-service
    CameraMonitor.exe --stop-service
    CameraMonitor.exe --uninstall-service

When the Service Control Manager launches the service, it runs the exe with the
hidden --run-as-service flag, which calls run_as_service() below.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import shutil
import sys
import time

import servicemanager
import win32event
import win32service
import win32serviceutil

from config_store import (app_data_dir, default_config_path, load_config_file,
                          log_dir, resolve_config)
from runner import AppRunner

SERVICE_NAME = "CameraMonitor"
SERVICE_DISPLAY = "Camera Monitor"
SERVICE_DESC = "Captures a camera and serves web, virtual-camera, and RTSP outputs."


def installed_exe_path() -> str:
    """Stable location the service runs from: ProgramData\\CameraMonitor."""
    return os.path.join(app_data_dir(), "CameraMonitor.exe")


def _exe_and_args():
    """What the SCM should launch. For a frozen build this is the copy we keep
    in ProgramData (see install()); from source it's python + main.py."""
    if getattr(sys, "frozen", False):
        return installed_exe_path(), "--run-as-service"
    main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return sys.executable, f'"{main_py}" --run-as-service'


def _setup_service_logging():
    d = log_dir()
    os.makedirs(d, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        os.path.join(d, "service.log"), maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s %(name)-8s %(message)s", "%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # avoid duplicate handlers if SvcDoRun is ever re-entered
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)


class CameraMonitorService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY
    _svc_description_ = SERVICE_DESC

    def __init__(self, args):
        super().__init__(args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._runner = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self._runner:
            self._runner.stop()
        win32event.SetEvent(self._stop_event)

    def SvcDoRun(self):
        _setup_service_logging()
        log = logging.getLogger("service")
        try:
            # A service's default working dir is System32; move to ProgramData so
            # child processes (e.g. MediaMTX) write runtime files somewhere writable.
            try:
                os.makedirs(app_data_dir(), exist_ok=True)
                os.chdir(app_data_dir())
            except Exception:
                pass
            cfg = resolve_config({}, load_config_file(default_config_path()))
            log.info("Service starting (source=%s, rtsp=%s)", cfg.source, cfg.rtsp_url)
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} starting")
            self._runner = AppRunner(cfg, service_mode=True)
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            self._runner.run_blocking(handle_signals=False)  # blocks until SvcStop
            log.info("Service stopped cleanly")
        except Exception as exc:  # noqa: BLE001
            log.exception("Service crashed: %s", exc)
            servicemanager.LogErrorMsg(f"{SERVICE_NAME} error: {exc}")


# --------------------------------------------------------------------------- #
# control actions (call from main.py; require administrator rights)
# --------------------------------------------------------------------------- #
def _service_exists() -> bool:
    try:
        win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        return True
    except Exception:
        return False


def _wait_stopped(timeout: float = 10.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            state = win32serviceutil.QueryServiceStatus(SERVICE_NAME)[1]
        except Exception:
            return
        if state == win32service.SERVICE_STOPPED:
            return
        time.sleep(0.3)


def install():
    target, args = _exe_and_args()

    # Remove any existing service first: this frees the target file (so we can
    # overwrite it) and lets us re-point/upgrade it cleanly.
    if _service_exists():
        try:
            win32serviceutil.StopService(SERVICE_NAME)
            _wait_stopped()
        except Exception:
            pass
        try:
            win32serviceutil.RemoveService(SERVICE_NAME)
        except Exception:
            pass

    # Copy the running exe into ProgramData so the service uses a stable copy
    # that doesn't depend on the original folder (dist/, Downloads, etc.).
    if getattr(sys, "frozen", False):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        src = sys.executable
        same = os.path.exists(target) and os.path.samefile(src, target)
        if not same:
            try:
                shutil.copy2(src, target)
                print(f"Copied program to {target}")
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"Could not copy the exe to {target}: {exc}\n"
                    "  (stop the service / close the file and retry)")
    else:
        print("Running from source: service will launch python + main.py "
              "(no self-copy). Build the exe for a standalone service.")

    # Register, retrying briefly in case the just-removed service is still
    # 'marked for deletion' by the SCM.
    last = None
    for _ in range(10):
        try:
            win32serviceutil.InstallService(
                pythonClassString=f"service.{CameraMonitorService.__name__}",
                serviceName=SERVICE_NAME,
                displayName=SERVICE_DISPLAY,
                description=SERVICE_DESC,
                startType=win32service.SERVICE_AUTO_START,
                exeName=target,
                exeArgs=args,
            )
            print(f'Service "{SERVICE_DISPLAY}" installed (auto-start on boot).')
            print(f"  runs: {target} {args}")
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.5)
    raise RuntimeError(f"Install failed after removing the old service: {last}")


def uninstall():
    if _service_exists():
        try:
            win32serviceutil.StopService(SERVICE_NAME)
            _wait_stopped()
        except Exception:
            pass
        try:
            win32serviceutil.RemoveService(SERVICE_NAME)
            print(f'Service "{SERVICE_DISPLAY}" removed.')
        except Exception as exc:  # noqa: BLE001
            print(f"Could not remove service: {exc}")
    else:
        print("Service is not installed.")

    # Delete the ProgramData copy, unless we're the one currently running.
    target = installed_exe_path()
    if os.path.exists(target):
        running_this = (getattr(sys, "frozen", False)
                        and os.path.samefile(sys.executable, target))
        if running_this:
            print(f"Note: {target} is the running program; delete it manually "
                  "afterwards if you want it gone.")
        else:
            try:
                os.remove(target)
                print(f"Deleted {target}")
            except Exception as exc:  # noqa: BLE001
                print(f"Could not delete {target}: {exc}")


def start():
    win32serviceutil.StartService(SERVICE_NAME)
    print(f'Service "{SERVICE_DISPLAY}" started.')


def stop():
    win32serviceutil.StopService(SERVICE_NAME)
    print(f'Service "{SERVICE_DISPLAY}" stopped.')


def run_as_service():
    """Entry point used when the SCM launches the exe with --run-as-service."""
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(CameraMonitorService)
    servicemanager.StartServiceCtrlDispatcher()
