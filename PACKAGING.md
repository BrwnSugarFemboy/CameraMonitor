# Packaging Camera Monitor as a single .exe

There are two separate things to solve:

1. **Make a standalone `.exe`** — done with **PyInstaller**.
2. **Not requiring users to install ffmpeg / mediamtx** — either **bundle** those
   binaries inside the exe (easy, recommended) or **replace ffmpeg** with a
   library that ships as a pip wheel (PyAV).

> **Important caveat about the virtual camera.** The virtual-camera feature needs
> an OS-level driver (OBS Virtual Camera on Windows/macOS, v4l2loopback on Linux).
> That is a system driver, **not** something PyInstaller can embed — so the
> virtual-camera output still requires OBS to be installed on the target machine.
> The **web viewer, MJPEG, WebSocket, and RTSP** outputs do **not** need OBS and
> are fully self-contained once you bundle the binaries below.

---

## Recommended path: bundle ffmpeg + mediamtx

This produces one `CameraMonitor.exe` that needs nothing else installed for the
web/RTSP features.

### 1. Get the binaries (Windows)

- **ffmpeg.exe** — download a static Windows build (e.g. from gyan.dev or
  BtbN/FFmpeg-Builds on GitHub) and take `ffmpeg.exe` out of the `bin` folder.
- **mediamtx.exe** (+ `mediamtx.yml`) — from
  <https://github.com/bluenviron/mediamtx/releases> (Windows amd64 zip).

Put them in a `bin/` folder next to the project:

```
camera-monitor/
├── main.py
├── camera_monitor.spec
└── bin/
    ├── ffmpeg.exe
    ├── mediamtx.exe
    └── mediamtx.yml        (optional)
```

Each file is optional — if you omit `ffmpeg.exe`/`mediamtx.exe`, the build still
works, you just won't have a self-contained RTSP feature.

### 2. Build

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt pyinstaller
pyinstaller camera_monitor.spec --clean
```

Result: `dist\CameraMonitor.exe` (one file).

### 3. Run

```bat
CameraMonitor.exe --source 0 --label FRONT-DOOR
CameraMonitor.exe --source 0 --rtsp rtsp://localhost:8554/cam
```

When `--rtsp` is used, the app auto-starts the bundled MediaMTX and points the
bundled ffmpeg at it — the user runs nothing manually. The code that finds the
bundled binaries lives in `resources.py` / `embedded_rtsp.py`; if no bundled
binary exists it transparently falls back to anything on `PATH`.

---

## How it stays self-contained

- `resources.find_ffmpeg()` prefers `bin/ffmpeg.exe` from inside the bundle
  (extracted to a temp dir at runtime) before falling back to PATH.
- `embedded_rtsp.EmbeddedRTSPServer` launches `bin/mediamtx.exe` if present, so
  `rtsp://localhost:8554/...` just works.
- OpenCV (`opencv-python`) already bundles its own FFmpeg **libraries** for
  reading camera/RTSP **inputs**; PyInstaller collects those automatically. The
  bundled `ffmpeg.exe` is only for the RTSP **output** encode.

---

## Build notes / troubleshooting

- **First launch is slow.** Onefile builds extract to a temp folder on startup.
  For faster startup use a folder build: change the spec to onedir, or just run
  `pyinstaller main.py --onedir --collect-all pyvirtualcam --collect-submodules uvicorn`.
- **Antivirus flags the exe.** Common with PyInstaller onefile. UPX is already
  disabled in the spec (it makes this worse). Code-signing the exe removes most
  warnings; otherwise onedir builds are flagged less often.
- **`CameraMonitor.exe` exits instantly / camera errors.** Run it from a terminal
  so you can see the logs. Keep `console=True` in the spec while debugging.
- **OpenCV can't open the camera in the build.** Add `--collect-all cv2` (CLI) or
  `collect_all("cv2")` in the spec.
- **Hide the console window.** Set `console=False` in the spec. Note you then
  can't Ctrl+C; stop it from Task Manager or add a tray/quit control.
- **Don't pass uvicorn an `"module:app"` string** — `main.py` passes the `app`
  object directly, which is what works when frozen. Keep it that way.

---

## Alternative: drop the ffmpeg.exe binary entirely (PyAV)

If you'd rather not ship `ffmpeg.exe`, swap the RTSP encoder to **PyAV**
(`pip install av`). PyAV bundles the FFmpeg **libraries** inside its wheel, so
PyInstaller packages them automatically (`collect_all("av")`) and there's no
separate executable to carry.

What PyAV changes and doesn't change:

- ✅ Removes the external `ffmpeg.exe` — encoding happens in-process.
- ❌ Does **not** remove the RTSP **server**. RTSP is a client/server protocol;
  publishing to `rtsp://localhost:8554/...` still needs something listening
  there. So you'd still bundle `mediamtx.exe` (it's a ~25 MB single Go binary
  with no dependencies, which packages cleanly).

### If you want to remove MediaMTX too

True `rtsp://` **serving** in pure Python has no mature, production-grade option,
so to drop the server you change the delivery protocol:

- **You already have two server-free live feeds**: MJPEG (`/stream.mjpg`) and the
  WebSocket (`/ws`). Those need zero external binaries and work in any browser
  today — for a lot of "security monitor" use cases that's enough.
- For **low-latency** browser viewing without ffmpeg/mediamtx, **WebRTC via
  `aiortc`** (pure pip, bundles its own native deps) is the clean route. It
  encodes H.264/VP8 in-process and serves directly to the browser.

If you want, I can convert the RTSP path to PyAV (keeps `rtsp://` for VLC/NVRs,
drops ffmpeg.exe) or add an `aiortc` WebRTC endpoint (drops both ffmpeg.exe and
mediamtx) — say which fits your viewers and I'll wire it in.
