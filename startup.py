"""Auto-start Camera Monitor at login, in the user's desktop session.

Why not the service? A Windows service runs in session 0, where the virtual
camera is invisible to normal apps (Teams, Camera, browsers). A per-user startup
entry runs the app in *your* session, so the virtual camera works. It uses the
HKEY_CURRENT_USER Run key, which needs no administrator rights.

The entry launches the exe with no arguments, so it reads its settings from the
ProgramData config file (set those first with --write-config).
"""
from __future__ import annotations

import os
import sys

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE = "CameraMonitor"


def _command(extra_args: str = "") -> str:
    if getattr(sys, "frozen", False):
        cmd = f'"{sys.executable}"'
    else:
        main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
        cmd = f'"{sys.executable}" "{main_py}"'
    if extra_args:
        cmd += " " + extra_args
    return cmd


def install(extra_args: str = "") -> bool:
    if not sys.platform.startswith("win"):
        print("Login auto-start is Windows-only.")
        return False
    import winreg
    cmd = _command(extra_args)
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, _VALUE, 0, winreg.REG_SZ, cmd)
    except Exception as exc:  # noqa: BLE001
        print("Could not enable auto-start:", exc)
        return False
    print("Auto-start enabled - runs at login in your desktop session:")
    print("  " + cmd)
    return True


def uninstall() -> bool:
    if not sys.platform.startswith("win"):
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, _VALUE)
        print("Auto-start disabled.")
        return True
    except FileNotFoundError:
        print("Auto-start was not enabled.")
        return True
    except Exception as exc:  # noqa: BLE001
        print("Could not remove auto-start:", exc)
        return False


def status() -> bool:
    if not sys.platform.startswith("win"):
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as k:
            val, _ = winreg.QueryValueEx(k, _VALUE)
        print("Auto-start is ENABLED:\n  " + val)
        return True
    except FileNotFoundError:
        print("Auto-start is not enabled.")
        return False
