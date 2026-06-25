# Fixing the virtual camera (no OBS required)

## What the problem is

The virtual-camera feature needs a **system virtual-camera device** registered
with Windows. `pyvirtualcam` does not contain that device — it only sends frames
to one that already exists. On a clean machine nothing is registered, so the
feature normally depends on OBS Studio being installed. PyInstaller can't embed
this because the device is a registered **DirectShow filter**, not a Python
dependency.

## The fix: bundle a standalone filter

Ship the **Unity Capture** filter (its DLL is MIT-licensed, so redistribution is
allowed) and register it once. No OBS needed. `pyvirtualcam` uses it via its
`unitycapture` backend automatically.

> Registering any virtual camera writes machine-wide registry keys, so it needs
> administrator rights **once**. That's true of OBS too — there's no way around a
> one-time elevation for a system-wide camera device.

### 1. Add the filter DLLs

Download from <https://github.com/schellingb/UnityCapture> and place both files
in a `vcam/` folder next to the project (and they'll be bundled by the spec):

```
camera-monitor/
├── main.py
├── camera_monitor.spec
└── vcam/
    ├── UnityCaptureFilter64.dll
    └── UnityCaptureFilter32.dll
```

(Keep the Unity Capture LICENSE file alongside them — MIT requires preserving the
copyright/permission notice when you redistribute the DLL.)

### 2. Register it (one time, per machine)

From source:

```bash
python main.py --install-vcam
```

From the built exe:

```bat
CameraMonitor.exe --install-vcam
```

You'll get a single UAC prompt. After that, `"Unity Video Capture"` appears in
the camera picker of Zoom, Teams, browsers, etc.

Verify any time with:

```bat
CameraMonitor.exe --check-vcam
```

Remove it with:

```bat
CameraMonitor.exe --uninstall-vcam
```

### 3. Run normally

```bat
CameraMonitor.exe --source 0
```

`pyvirtualcam` picks up whatever backend is registered (Unity Capture or OBS). To
force Unity Capture explicitly:

```bat
CameraMonitor.exe --source 0 --vcam-backend unitycapture --vcam-device "Unity Video Capture"
```

## What changed in the code

- `vcam_install.py` — registers/unregisters the bundled filter via `regsvr32`
  with a single elevation prompt; `--check-vcam` reports whether a backend works.
- `main.py` — `--install-vcam` / `--uninstall-vcam` / `--check-vcam` flags.
- `virtual_camera.py` — if no backend is found at runtime, the error now tells
  the user exactly how to fix it (and it shows in the web telemetry panel too).
- `camera_monitor.spec` — bundles `vcam/UnityCaptureFilter{64,32}.dll`.

## Notes & alternatives

- **Both DLLs matter.** The 64-bit filter serves 64-bit apps; the 32-bit filter
  serves 32-bit apps (some conferencing/browser components are still 32-bit).
  Registering both maximizes compatibility.
- **Antivirus / SmartScreen.** Registering a DirectShow filter can draw a warning
  on locked-down machines. Code-signing the DLL and the exe avoids most of this.
- **Linux:** the equivalent is the `v4l2loopback` kernel module
  (`sudo modprobe v4l2loopback devices=1`). `--install-vcam` prints this hint
  when run on Linux.
- **Windows 11 only, future option:** Windows 11 added a native virtual-camera
  API (`MFCreateVirtualCamera`). It avoids any third-party filter, but requires a
  C++/COM Media Foundation source and only works on Win11 — not practical from
  Python today, but worth knowing it exists if you later move the camera layer to
  native code.
- **Don't need app compatibility at all?** If every consumer of the feed can read
  the web/MJPEG/WebSocket/RTSP outputs, you can skip the virtual camera entirely
  with `--no-vcam` and avoid this whole topic.
