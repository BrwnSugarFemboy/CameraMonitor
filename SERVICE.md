# Deployment, config file, and the Windows service

This covers how to run Camera Monitor unattended and where its settings live.
There are three deployment modes — pick the one that matches your goal.

## Which mode do I want?

| Goal | Mode |
|---|---|
| Just try it / run while you're at the keyboard | **Interactive** |
| Virtual camera in Teams/Zoom/browser on *this* PC, auto-start at login | **Login auto-start** |
| Headless box, runs before/without login, feed consumed over the network | **Service** |
| Headless box **and** virtual camera once a user logs in | **Service + bridge** |

The key constraint behind all of this: a Windows **service runs in session 0**,
where a virtual camera is **invisible** to normal desktop apps. So a service can
serve web/RTSP headless, but it cannot itself provide a usable virtual camera.
The "bridge" mode below works around that.

---

## Where settings live

The app reads a JSON config from:

```
C:\ProgramData\CameraMonitor\config.json
```

Priority order (later wins): **built-in defaults → config file → command-line flags.**
A service or auto-start entry runs with no flags, so it is driven entirely by the
file. Create/update it by passing the settings you want once:

```powershell
CameraMonitor.exe --source 0 --rtsp rtsp://localhost:8554/cam --label FRONT-DOOR --write-config
```

You can hand-edit the file afterward (it's picked up on next start). `source` may
be a number like `0` or a string URL. Use a different file with
`--config "D:\some\path.json"` on any command.

---

## Mode 1 — Interactive

```powershell
CameraMonitor.exe --source 0 --rtsp rtsp://localhost:8554/cam
```

Runs everything (capture, web, virtual camera, RTSP) while the window is open.
Ctrl+C to stop. Best for testing.

## Mode 2 — Login auto-start (virtual camera on this PC)

Runs the full app in **your** desktop session at login, so the virtual camera is
visible to Teams/Zoom/browsers. No admin, not a scheduled task — it uses the
per-user HKCU Run key.

```powershell
CameraMonitor.exe --install-vcam                  # once, admin (registers the camera)
CameraMonitor.exe --source 0 --rtsp rtsp://localhost:8554/cam --write-config
CameraMonitor.exe --install-startup               # run at login, in your session
```

Manage it: `--startup-status`, `--uninstall-startup`. To start it now without
logging out: just run `CameraMonitor.exe`.

## Mode 3 — Service (headless, network only)

Runs at boot with nobody logged in. Serves web + RTSP. **Turn the virtual camera
off** — nothing in session 0 can see it.

```powershell
CameraMonitor.exe --source 0 --rtsp rtsp://localhost:8554/cam --no-vcam --write-config
CameraMonitor.exe --install-service               # admin
CameraMonitor.exe --start-service
```

Consume the feed from another machine at `http://<box-ip>:8000/` or
`rtsp://<box-ip>:8554/cam`.

On install the exe **copies itself to `C:\ProgramData\CameraMonitor\CameraMonitor.exe`**
and registers the service against that copy, so it no longer depends on where you
ran it from (you can delete `dist\`). Re-running `--install-service` after a
rebuild refreshes that copy. Verify the path with `sc qc CameraMonitor`.

Manage it: `--stop-service`, `--uninstall-service` (which also deletes the copied
exe unless it's the one currently running).

> All `*-service` commands need an **administrator** terminal — they talk to the
> Service Control Manager. "Access is denied"/"failed" means you're not elevated.

## Mode 4 — Service + bridge (headless boot **and** virtual camera at login)

This is how you get both at once. The trick: only the **service** opens the
camera; a tiny **bridge** in the user session reads the service's local stream
and pushes it into the virtual camera, so the two never contend for the device.

```powershell
# Service owns the camera + serves web/RTSP, virtual camera OFF:
CameraMonitor.exe --source 0 --rtsp rtsp://localhost:8554/cam --no-vcam --write-config
CameraMonitor.exe --install-service        # admin

# Login bridge feeds the virtual camera from the local stream (opens no camera):
CameraMonitor.exe --install-startup --vcam-bridge
```

At boot the service serves the feed over `localhost`; when a user logs in, the
bridge connects to `http://localhost:8000/stream.mjpg` and drives the virtual
camera in that session. (localhost works across sessions, which is what makes
this possible.)

The bridge defaults to the local MJPEG URL on your configured port. For best
quality you can point it at RTSP instead:
`--install-startup --vcam-bridge "rtsp://localhost:8554/cam"`.

> Don't run Mode 2 and Mode 3/4 together — Mode 2's full app and the service would
> both open the physical camera and fight over it. The bridge exists precisely so
> Mode 4 avoids that.

---

## The Windows Camera app (and other Media Foundation apps)

The bundled virtual camera (Unity Capture) is a **DirectShow** device. The
Windows **Camera app**, Windows Hello-style apps, and some newer apps use
**Media Foundation**, which cannot see DirectShow virtual cameras — so the camera
won't appear there (it shows no device / no switcher). This is a Windows API
split, not a bug, and it applies to every mode above.

Apps that **do** see it: Teams, Zoom, Discord, OBS, and most browsers
(DirectShow). If you specifically need the Windows Camera app or other Media
Foundation apps, the practical option is the **OBS Virtual Camera** (install OBS
28+, run once, then `--vcam-backend obs`) — it registers a Media Foundation
camera on Windows 11, at the cost of the OBS dependency.

## Logs

Interactive/auto-start runs log to `C:\ProgramData\CameraMonitor\logs\app.log`;
the service logs to `...\logs\service.log`. Both rotate. Service start/stop/error
events also go to the Windows Event Viewer (Application log, source
"CameraMonitor").

## Silent (no console) builds

For an end-user/auto-start deployment, build with `console=False` in
`camera_monitor.spec` so no window appears at login. Logs still go to `app.log`
(the app detects the missing console and routes logging to file only). Keep
`console=True` for your own debugging builds.

## If the native service gives you trouble

Two no-code alternatives:

- **NSSM** wraps the exe as a service without the pywin32 machinery:
  `nssm install CameraMonitor "C:\ProgramData\CameraMonitor\CameraMonitor.exe"`.
- **Task Scheduler** ("at log on", "run only when user is logged on") is an
  alternative to `--install-startup` for the in-session case.

## Build note

The spec lists pywin32's hidden imports (including `win32timezone`, the one
PyInstaller classically misses). Ensure `pip install pywin32` ran in your build
environment, then `pyinstaller camera_monitor.spec --clean`.
