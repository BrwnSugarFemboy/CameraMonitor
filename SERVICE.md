# Config file + running as a Windows service

## Where settings live

The app reads a JSON config from:

```
C:\ProgramData\CameraMonitor\config.json
```

Priority order (later wins): **built-in defaults → config file → command-line flags.**
So the service (which runs with no flags) is driven entirely by that file, while
you can still override anything on the command line for testing.

### Create / update the config

The easiest way is to pass the settings you want once and let the app write them:

```powershell
CameraMonitor.exe --source 0 --rtsp rtsp://localhost:8554/cam --label FRONT-DOOR --write-config
```

That produces `C:\ProgramData\CameraMonitor\config.json`:

```json
{
  "source": 0,
  "backend": "auto",
  "label": "FRONT-DOOR",
  "host": "0.0.0.0",
  "port": 8000,
  "stream_fps": 20.0,
  "jpeg_quality": 80,
  "vcam_enabled": true,
  "rtsp_url": "rtsp://localhost:8554/cam",
  "rtsp_fps": 25.0,
  "...": "..."
}
```

You can hand-edit that file afterward; the service picks it up on next start.
(`source` may be a number like `0` or a string URL like `"rtsp://..."`.)

Use a different file with `--config "D:\some\path.json"` on any command.

## Install the service

The service support uses pywin32, which is bundled into the exe. Run these from
an **administrator** terminal (right-click → "Run as administrator"):

```powershell
CameraMonitor.exe --install-service     # registers it, auto-start on boot,
                                        # and saves current settings to config.json
CameraMonitor.exe --start-service
```

On install the exe **copies itself to `C:\ProgramData\CameraMonitor\CameraMonitor.exe`**
and registers the service against that copy. So the service no longer depends on
where you ran it from — you can delete the original `dist\` folder and the
service keeps working across reboots. Re-running `--install-service` (e.g. after
a rebuild) stops the old service, refreshes that copy, and re-registers.

Check it:

```powershell
sc query CameraMonitor
sc qc CameraMonitor      # shows BINARY_PATH_NAME -> ...\ProgramData\CameraMonitor\CameraMonitor.exe
```

It now starts automatically on boot, runs headless (no console), and Windows
runs it without anyone logging in.

Stop / remove:

```powershell
CameraMonitor.exe --stop-service
CameraMonitor.exe --uninstall-service
```

`--uninstall-service` also deletes the copied exe in ProgramData (unless you
happen to run that copy itself, since a running exe can't delete itself — in that
case it tells you to remove the file manually).

> All four service commands need administrator rights — they talk to the Windows
> Service Control Manager. If you see "Access is denied" or "failed", you're not
> in an elevated terminal.

## Logs

A service has no console, so it logs to a rotating file:

```
C:\ProgramData\CameraMonitor\logs\service.log
```

Start there if the service starts but the feed isn't working. Service
start/stop/error events are also written to the Windows **Event Viewer**
(Windows Logs → Application, source "CameraMonitor").

## Updating settings while installed

1. `CameraMonitor.exe --stop-service`
2. edit `config.json` (or re-run `--write-config` with new flags)
3. `CameraMonitor.exe --start-service`

## A note on the virtual camera + services

A Windows service runs in an isolated session (session 0) with no desktop. The
**web and RTSP outputs work fine** there. The **virtual camera** may not be
visible to apps running in your normal desktop session, because virtual cameras
are session-scoped. If your goal is "feed available to Zoom/Teams on this PC,"
the virtual camera is better run interactively in your user session (or via the
Task Scheduler option below, set to run in your session). For a headless
appliance serving web/RTSP to other machines, the service is ideal — consider
adding `vcam_enabled: false` to the config in that case.

## If the native service gives you trouble

Two reliable alternatives that need no code:

**NSSM** (Non-Sucking Service Manager) wraps the exe as a service without any of
the pywin32 machinery:

```powershell
nssm install CameraMonitor "C:\path\to\CameraMonitor.exe"
nssm start CameraMonitor
```

**Task Scheduler** ("run whether logged on or not", trigger "At startup") gets
you boot-start without a true service, and keeps the process in a session where
the virtual camera is visible. Simplest if the virtual camera matters.

## Build note

The spec already lists pywin32's hidden imports (including `win32timezone`, the
one PyInstaller classically misses). Just make sure `pip install pywin32` ran in
the environment you build from, then `pyinstaller camera_monitor.spec --clean`.
