# Camera Monitor

A single-camera security / auditing monitor for Windows, written in Python. It
captures one camera **once** and fans the feed out to every consumer at the same
time — so apps never fight over the device — and can run unattended as a Windows
service.

![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20(Linux%2FmacOS%20core)-lightgrey)
![License](https://img.shields.io/badge/license-GPL--2.0-orange)
![Written by Claude](https://img.shields.io/badge/code-written%20by%20Claude-d97757)

> **Disclaimer:** All of the code in this project was written by **Claude**, an
> AI assistant made by Anthropic. It was produced through an interactive
> session and should be reviewed and tested before any production use. No
> warranty is provided (see the License section).

## Features

- **One capture, many outputs** — a single reader of the physical camera feeds everything else, which avoids the Windows "device is already in use" problem.
- **Web viewer** — a self-contained control-room page (live feed + telemetry) at `http://<host>:8000/`.
- **MJPEG** stream (`/stream.mjpg`) and **WebSocket** stream (`/ws`) — work in any browser, no plugins.
- **Virtual camera** — appears as a normal webcam in Zoom, Teams, OBS, browsers, etc. No OBS install required (bundles the Unity Capture filter).
- **RTSP** (optional) — H.264 via a bundled FFmpeg + MediaMTX, readable in VLC / NVRs at `rtsp://<host>:8554/cam`.
- **Single .exe** — packaged with PyInstaller; FFmpeg, MediaMTX, and the virtual-camera filter are bundled, so end users install nothing.
- **Unattended deployment** — run at login in your session, or as a headless Windows service (auto-start on boot), or both via a session bridge. Settings persist in `C:\ProgramData\CameraMonitor\config.json`.
- **Diagnostics** — `--list-cameras` shows every device index, its resolution, and flags black frames (closed shutter / IR cam).
- **Auto-reconnect** if the camera drops.

## How it works

Only `FrameSource` ever opens the physical camera. Everything else reads the
latest frame from it, so the OS sees exactly one consumer of the real device.

```
                      +-----------> Web viewer / MJPEG (HTTP 8000)
 Physical camera      |
      |               +-----------> WebSocket (8000)
  capture thread -----+
 (the only reader)    +-----------> Virtual camera ---> Zoom / Teams / browser
                      |
                      +-----------> FFmpeg --(RTMP)--> MediaMTX --> RTSP (8554)
```

## Requirements

- **Windows 10/11** for the virtual-camera and service features.
  (The web / MJPEG / WebSocket / RTSP core also runs on Linux and macOS.)
- **Python 3.10–3.13** (to run from source or build the exe).

## Quick start (from source)

```powershell
git clone https://github.com/<you>/camera-monitor.git
cd camera-monitor
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Open <http://localhost:8000/>. If the feed is black/offline, your camera is on a
different index — find it with:

```powershell
python main.py --list-cameras
```

…then run `python main.py --source <index>`.

## Bundled binaries (not in this repo)

FFmpeg, MediaMTX, and the Unity Capture DLLs are **not committed** (they're large
and have their own licenses). Download them and drop them in before building or
using the matching features:

```
camera-monitor/
├── bin/
│   ├── ffmpeg.exe        # https://www.gyan.dev/ffmpeg/builds/  (or BtbN/FFmpeg-Builds)
│   ├── mediamtx.exe      # https://github.com/bluenviron/mediamtx/releases
│   └── mediamtx.yml      # from the MediaMTX zip (see Configuration note below)
└── vcam/
    ├── UnityCaptureFilter64.dll   # https://github.com/schellingb/UnityCapture
    └── UnityCaptureFilter32.dll
```

Each is optional — features whose binaries are missing are simply skipped. The
web/MJPEG/WebSocket outputs need none of them.

> **MediaMTX config:** an empty MediaMTX config rejects all publishes. Make sure
> `bin/mediamtx.yml` contains at least:
> ```yaml
> rtpAddress: :8002
> rtcpAddress: :8003
> paths:
>   all_others:
> ```

## Building a standalone .exe

```powershell
pip install pyinstaller
pyinstaller camera_monitor.spec --clean
```

Produces `dist\CameraMonitor.exe`, with whatever is in `bin/` and `vcam/` bundled
inside. Full details and troubleshooting: [PACKAGING.md](PACKAGING.md).

## Optional features

| Feature | Setup | Docs |
|---|---|---|
| Virtual camera (no OBS) | `CameraMonitor.exe --install-vcam` (admin, once) | [VIRTUALCAM.md](VIRTUALCAM.md) |
| RTSP output | add `bin/ffmpeg.exe` + `bin/mediamtx.exe`, run with `--rtsp rtsp://localhost:8554/cam` | [PACKAGING.md](PACKAGING.md) |
| Auto-start, service, headless, config file | login auto-start, Windows service, or service + bridge | [SERVICE.md](SERVICE.md) |

> **Heads up:** the bundled virtual camera is a DirectShow device, so it appears
> in Teams, Zoom, Discord, OBS, and browsers — but **not** the Windows Camera app
> or other Media Foundation apps. See [SERVICE.md](SERVICE.md) for why and the
> OBS-backend workaround.

## Configuration

Settings resolve in this order (later wins):

> built-in defaults  →  `config.json`  →  command-line flags

The file lives at `C:\ProgramData\CameraMonitor\config.json`. Generate it from
the flags you want:

```powershell
CameraMonitor.exe --source 0 --rtsp rtsp://localhost:8554/cam --label FRONT-DOOR --write-config
```

The Windows service runs with no flags, so it is driven entirely by that file.
See [SERVICE.md](SERVICE.md) for the full workflow and the session-0 caveat about
the virtual camera under a service.

## Command-line reference

| Flag | Description |
|---|---|
| `--source <n\|url>` | Camera index, file path, or stream URL |
| `--backend auto\|dshow\|msmf\|v4l2` | OpenCV capture backend |
| `--width / --height / --fps` | Requested capture settings |
| `--label <name>` | Name shown in the web viewer |
| `--host / --port` | Web server bind (default `0.0.0.0:8000`) |
| `--stream-fps / --jpeg-quality / --stream-max-width` | Browser stream tuning |
| `--no-vcam` | Disable the virtual camera |
| `--vcam-backend / --vcam-device` | Pick a virtual-camera backend/device |
| `--rtsp <url>` | Publish RTSP (e.g. `rtsp://localhost:8554/cam`) |
| `--rtsp-fps / --rtsp-bitrate` | RTSP encode settings |
| `--config <path>` / `--write-config` | Use / write the config file |
| `--install-service` / `--uninstall-service` / `--start-service` / `--stop-service` | Windows service control (admin) |
| `--install-startup` / `--uninstall-startup` / `--startup-status` | Login auto-start in your user session (no admin) |
| `--vcam-bridge [url]` | Feed the virtual camera from a stream instead of the camera (use with a headless service) |
| `--install-vcam` / `--uninstall-vcam` / `--check-vcam` | Virtual-camera registration (admin) |
| `--list-cameras` / `--max-index <n>` | Enumerate camera indices and exit |

Run `python main.py --help` for the complete list.

## Project layout

| File | Purpose |
|---|---|
| `main.py` | CLI entry point, argument parsing, command dispatch |
| `config.py` | `Config` dataclass (defaults) |
| `config_store.py` | ProgramData JSON config: load / write / resolve precedence |
| `runner.py` | Builds and runs all components (shared by CLI and service) |
| `frame_source.py` | Single-reader camera capture + thread-safe frame fan-out |
| `webserver.py` | FastAPI app: viewer page, MJPEG, WebSocket, snapshot, status |
| `viewer.py` | The embedded HTML/JS control-room viewer page |
| `virtual_camera.py` | Virtual-camera output via pyvirtualcam |
| `vcam_install.py` | Register/unregister the bundled Unity Capture filter |
| `rtsp_publisher.py` | FFmpeg → RTMP → MediaMTX publishing |
| `embedded_rtsp.py` | Launches the bundled MediaMTX server |
| `service.py` | Windows service (install/start/stop/uninstall + self-copy) |
| `camera_list.py` | `--list-cameras` diagnostics |
| `resources.py` | Locate bundled binaries in source and frozen builds |
| `camera_monitor.spec` | PyInstaller build spec |

## Third-party components & licenses

This project depends on / bundles the following. **Two are copyleft (GPL)** and
drive the licensing of the whole thing — read the next section.

| Component | Role | License |
|---|---|---|
| pyvirtualcam | virtual-camera output | **GPL-2.0** |
| FFmpeg (gyan.dev / BtbN build w/ libx264) | RTSP H.264 encode | **GPL** |
| MediaMTX | RTSP/RTMP server | MIT |
| Unity Capture (filter DLL) | virtual-camera device | MIT |
| OpenCV (`opencv-python`) | capture + JPEG encode | Apache-2.0 |
| FastAPI | web framework | MIT |
| uvicorn | ASGI server | BSD-3-Clause |
| NumPy | arrays | BSD-3-Clause |
| pygrabber *(optional)* | camera names | MIT |
| pywin32 *(optional)* | Windows service | PSF |

## License

Because this project imports **pyvirtualcam (GPL-2.0)** and bundles a **GPL build
of FFmpeg**, a distributed copy (source or the built `.exe`) is effectively
subject to the **GNU GPL**. The simplest compliant choice is to license your own
code under the **GPL-2.0** as well, and to make the corresponding source
available to anyone you give the binary to.

If you would rather not be bound by the GPL, you can:
- drop the virtual-camera feature (remove pyvirtualcam), and
- use an **LGPL** FFmpeg build (no GPL components like x264).

Add a `LICENSE` file to the repo reflecting your choice. *This is a summary, not
legal advice — review each component's license and consult a professional if you
intend to distribute.*

When redistributing the bundled binaries, keep each project's license/notice file
alongside it (MIT and GPL both require preserving their notices).

## Responsible use

This is a monitoring tool for cameras **you own or are authorized to operate**.
Recording or streaming people without their consent or another lawful basis may
be illegal where you live. There is no authentication on the web/WebSocket
endpoints — keep it on a trusted LAN, bind to `--host 127.0.0.1`, or put it
behind a VPN / reverse proxy. You are responsible for how you deploy it.

## Acknowledgements

Built on [OpenCV](https://opencv.org/), [FastAPI](https://fastapi.tiangolo.com/),
[uvicorn](https://www.uvicorn.org/), [pyvirtualcam](https://github.com/letmaik/pyvirtualcam),
[Unity Capture](https://github.com/schellingb/UnityCapture),
[MediaMTX](https://github.com/bluenviron/mediamtx), and [FFmpeg](https://ffmpeg.org/).
