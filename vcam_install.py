"""Install / remove an OBS-free virtual camera.

The virtual-camera output needs a system virtual-camera device registered with
Windows. Instead of requiring users to install OBS, we bundle the MIT-licensed
Unity Capture DirectShow filter and register it ourselves.

Get the two filter DLLs from https://github.com/schellingb/UnityCapture
(UnityCaptureFilter64.dll and UnityCaptureFilter32.dll) and place them in a
'vcam' folder next to the app, or bundle them via camera_monitor.spec.

Registering a DirectShow filter writes to HKCR, so it needs administrator
rights. This is true of every virtual camera (OBS does the same during install).
The functions here trigger a single UAC prompt and wait for it to finish.
"""
from __future__ import annotations

import ctypes
import os
import sys
import tempfile

from resources import resource_path

DEVICE_NAME = "Unity Video Capture"
_DLL64 = "UnityCaptureFilter64.dll"
_DLL32 = "UnityCaptureFilter32.dll"

_IS_WINDOWS = sys.platform.startswith("win")


def _vcam_dir() -> str:
    return resource_path("vcam")


def dll_paths():
    d = _vcam_dir()
    return os.path.join(d, _DLL64), os.path.join(d, _DLL32)


def filters_present() -> bool:
    d64, d32 = dll_paths()
    return os.path.exists(d64) or os.path.exists(d32)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# elevated execution (single UAC prompt, waits for completion)
# --------------------------------------------------------------------------- #
if _IS_WINDOWS:
    from ctypes import wintypes

    _SEE_MASK_NOCLOSEPROCESS = 0x00000040
    _SEE_MASK_NO_CONSOLE = 0x00008000
    _SW_HIDE = 0
    _INFINITE = 0xFFFFFFFF

    class _SHELLEXECUTEINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    def _shell_execute_wait(file: str, params: str, verb: str = "runas") -> bool:
        sei = _SHELLEXECUTEINFO()
        sei.cbSize = ctypes.sizeof(sei)
        sei.fMask = _SEE_MASK_NOCLOSEPROCESS | _SEE_MASK_NO_CONSOLE
        sei.lpVerb = verb
        sei.lpFile = file
        sei.lpParameters = params
        sei.nShow = _SW_HIDE
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
            return False  # user cancelled UAC or launch failed
        if sei.hProcess:
            ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, _INFINITE)
            code = wintypes.DWORD()
            ctypes.windll.kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(sei.hProcess)
            return code.value == 0
        return True


def _regsvr_cmds(unregister: bool):
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    regsvr64 = os.path.join(sysroot, "System32", "regsvr32.exe")  # 64-bit
    regsvr32 = os.path.join(sysroot, "SysWOW64", "regsvr32.exe")  # 32-bit
    d64, d32 = dll_paths()
    flag = "/u /s" if unregister else "/s"
    cmds = []
    if os.path.exists(d64):
        cmds.append(f'"{regsvr64}" {flag} "{d64}"')
    if os.path.exists(d32) and os.path.exists(regsvr32):
        cmds.append(f'"{regsvr32}" {flag} "{d32}"')
    return cmds


def _run_elevated(cmds) -> bool:
    if not cmds:
        return False
    fd, bat = tempfile.mkstemp(suffix=".bat")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("@echo off\r\n")
            for c in cmds:
                f.write(c + "\r\n")
        return _shell_execute_wait("cmd.exe", f'/c "{bat}"')
    finally:
        try:
            os.remove(bat)  # safe: we waited for completion
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# public actions (return True on success)
# --------------------------------------------------------------------------- #
def install() -> bool:
    if not _IS_WINDOWS:
        print("On Linux install the v4l2loopback kernel module instead:")
        print("  sudo apt install v4l2loopback-dkms")
        print("  sudo modprobe v4l2loopback devices=1 card_label='Camera Monitor'")
        return False
    if not filters_present():
        print(f"Virtual-camera filter DLLs not found in: {_vcam_dir()}")
        print("Download UnityCaptureFilter64.dll and UnityCaptureFilter32.dll from")
        print("  https://github.com/schellingb/UnityCapture")
        print("and place them in that folder (or bundle them via the .spec).")
        return False
    ok = _run_elevated(_regsvr_cmds(unregister=False))
    print(f'Virtual camera registered as "{DEVICE_NAME}".' if ok
          else "Registration failed or was cancelled at the UAC prompt.")
    return ok


def uninstall() -> bool:
    if not _IS_WINDOWS:
        print("On Linux: sudo modprobe -r v4l2loopback")
        return False
    ok = _run_elevated(_regsvr_cmds(unregister=True))
    print("Virtual camera removed." if ok
          else "Removal failed or was cancelled at the UAC prompt.")
    return ok


def check() -> bool:
    """Report whether a usable virtual-camera backend exists right now."""
    try:
        import pyvirtualcam
    except Exception as exc:  # noqa: BLE001
        print("pyvirtualcam is not available:", exc)
        return False
    try:
        with pyvirtualcam.Camera(width=320, height=240, fps=20) as cam:
            print("Virtual camera OK ->", cam.device)
            return True
    except Exception as exc:  # noqa: BLE001
        print("No usable virtual-camera backend found.")
        print("  detail:", exc)
        print('  fix:   run "CameraMonitor.exe --install-vcam"  (bundled, no OBS)')
        print("         or install OBS Studio.")
        return False
