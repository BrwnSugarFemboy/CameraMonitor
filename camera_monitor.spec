# -*- mode: python ; coding: utf-8 -*-
#
# Build a single self-contained CameraMonitor.exe:
#     pip install pyinstaller
#     pyinstaller camera_monitor.spec --clean
#
# Optional bundled binaries (so end users install NOTHING):
#   Put these next to this spec, in a ./bin folder, before building:
#       bin/ffmpeg.exe       -> enables RTSP encoding without an ffmpeg install
#       bin/mediamtx.exe     -> the RTSP server, auto-started by the app
#       bin/mediamtx.yml     -> (optional) MediaMTX config
#   If a file is absent it is simply skipped; the web/WebSocket/virtual-camera
#   features never need any of them.

import os
from PyInstaller.utils.hooks import collect_submodules, collect_all

datas = []
binaries = []
hiddenimports = []

# --- uvicorn / starlette load protocol + loop backends dynamically ---
hiddenimports += collect_submodules("uvicorn")
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "websockets",
    "websockets.legacy",
    "websockets.legacy.server",
    "anyio",
    "h11",
    "click",
]

# --- pyvirtualcam ships a native virtual-camera library that the standard
#     analysis won't pick up on its own ---
pv_datas, pv_binaries, pv_hidden = collect_all("pyvirtualcam")
datas += pv_datas
binaries += pv_binaries
hiddenimports += pv_hidden

# --- pywin32 pieces needed for the Windows service ---
hiddenimports += [
    "win32serviceutil",
    "win32service",
    "win32event",
    "servicemanager",
    "win32timezone",   # classic PyInstaller-missing pywin32 module
    "win32api",
    "win32con",
    "pywintypes",
    "pythoncom",
]

# --- bundle the external tools if present (each is optional) ---
for fname in ("ffmpeg.exe", "mediamtx.exe", "mediamtx.yml"):
    p = os.path.join("bin", fname)
    if os.path.exists(p):
        datas.append((p, "bin"))

# --- bundle the OBS-free virtual-camera filter (Unity Capture, MIT) so the app
#     can register a virtual camera with --install-vcam (no OBS required).
#     Download the two DLLs from https://github.com/schellingb/UnityCapture
#     and place them under ./vcam before building. ---
for fname in ("UnityCaptureFilter64.dll", "UnityCaptureFilter32.dll"):
    p = os.path.join("vcam", fname)
    if os.path.exists(p):
        datas.append((p, "vcam"))

# Local app modules live next to this spec. Spec builds (unlike `pyinstaller
# main.py`) don't auto-add the project dir to the import path, so do it here.
hiddenimports += [
    "config", "frame_source", "virtual_camera", "rtsp_publisher",
    "webserver", "viewer", "resources", "embedded_rtsp", "vcam_install",
    "camera_list", "runner", "config_store", "service", "startup",
]

a = Analysis(
    ["main.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CameraMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX often trips antivirus; leave off
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,             # no console window (silent for end users)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                 # set to "app.ico" if you have one
)
