"""Camera monitor entry point.

Captures one camera and simultaneously serves a web viewer + MJPEG + WebSocket
stream, a system virtual camera, and (optionally) an RTSP stream.

Settings are resolved from (lowest to highest priority):
    built-in defaults  <  config file  <  command-line flags
The config file defaults to %ProgramData%/CameraMonitor/config.json and is what
the Windows service reads.

Run `python main.py --help` for all options.
"""
from __future__ import annotations

import argparse
import logging
import multiprocessing

from config_store import (default_config_path, load_config_file,
                          resolve_config, setup_logging, write_config_file)
from runner import AppRunner, run_vcam_bridge

log = logging.getLogger("main")


def parse_source(value):
    """A bare integer means a camera index; anything else is a path/URL."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Single-camera security monitor with web, virtual-cam, and RTSP output.")

    # Capture/stream options default to None so we can tell whether the user set
    # them; unset values fall back to the config file, then to config.Config.
    p.add_argument("--source", default=None, help="Camera index (e.g. 0) or file path / stream URL.")
    p.add_argument("--width", type=int, default=None, help="Requested capture width.")
    p.add_argument("--height", type=int, default=None, help="Requested capture height.")
    p.add_argument("--fps", type=float, default=None, help="Requested capture fps.")
    p.add_argument("--backend", default=None, choices=["auto", "any", "dshow", "msmf", "v4l2"],
                   help="OpenCV capture backend (default: auto).")
    p.add_argument("--label", default=None, help="Name shown in the web viewer.")

    p.add_argument("--host", default=None, help="Web server bind address (default 0.0.0.0).")
    p.add_argument("--port", type=int, default=None, help="Web server port (default 8000).")
    p.add_argument("--stream-fps", type=float, default=None, help="Frames/sec pushed to browsers.")
    p.add_argument("--jpeg-quality", type=int, default=None, help="JPEG quality for web/ws (1-100).")
    p.add_argument("--stream-max-width", type=int, default=None,
                   help="Downscale the browser stream if wider than this (0 = full size).")

    p.add_argument("--no-vcam", action="store_true", help="Disable the virtual camera output.")
    p.add_argument("--vcam-fps", type=float, default=None, help="Virtual camera fps.")
    p.add_argument("--vcam-device", default=None, help="Virtual camera device name.")
    p.add_argument("--vcam-backend", default=None, help="pyvirtualcam backend (obs | unitycapture | v4l2loopback).")

    p.add_argument("--rtsp", dest="rtsp_url", default=None,
                   help="Publish RTSP to this URL (e.g. rtsp://localhost:8554/cam).")
    p.add_argument("--rtsp-fps", type=float, default=None, help="RTSP output fps.")
    p.add_argument("--rtsp-bitrate", default=None, help="RTSP H.264 bitrate (e.g. 3M).")
    p.add_argument("--ffmpeg", default=None, help="Path to the ffmpeg binary.")

    p.add_argument("--log-level", default=None, choices=["debug", "info", "warning", "error"])

    cf = p.add_argument_group("configuration file")
    cf.add_argument("--config", default=None,
                    help=f"Config file path (default: {default_config_path()}).")
    cf.add_argument("--write-config", action="store_true",
                    help="Write the resolved settings to the config file and exit.")

    sv = p.add_argument_group("windows service (run from an admin terminal)")
    sv.add_argument("--install-service", action="store_true",
                    help="Install the auto-start service (also saves current settings to the config file).")
    sv.add_argument("--uninstall-service", action="store_true", help="Remove the Windows service.")
    sv.add_argument("--start-service", action="store_true", help="Start the Windows service.")
    sv.add_argument("--stop-service", action="store_true", help="Stop the Windows service.")
    sv.add_argument("--run-as-service", action="store_true", help=argparse.SUPPRESS)

    au = p.add_argument_group("login auto-start (your user session; no admin, virtual-camera-friendly)")
    au.add_argument("--install-startup", action="store_true",
                    help="Run at login in your desktop session (virtual camera works here). No admin needed.")
    au.add_argument("--uninstall-startup", action="store_true", help="Remove the login auto-start entry.")
    au.add_argument("--startup-status", action="store_true", help="Show whether login auto-start is enabled.")
    au.add_argument("--vcam-bridge", nargs="?", const="", default=None, metavar="URL",
                    help="User-session helper: feed the virtual camera from a stream instead of the "
                         "camera (use alongside a headless service). Defaults to the local MJPEG URL.")

    g = p.add_argument_group("virtual camera setup (run once, then exit)")
    g.add_argument("--install-vcam", action="store_true",
                   help="Register the bundled OBS-free virtual camera (prompts for admin) and exit.")
    g.add_argument("--uninstall-vcam", action="store_true", help="Unregister the bundled virtual camera and exit.")
    g.add_argument("--check-vcam", action="store_true",
                   help="Check whether a virtual-camera backend is usable and exit.")

    d = p.add_argument_group("diagnostics")
    d.add_argument("--list-cameras", action="store_true",
                   help="List camera indices (with resolution + black-frame check) and exit.")
    d.add_argument("--max-index", type=int, default=8,
                   help="Highest camera index to probe with --list-cameras (default 8).")
    return p


def _cli_overrides(args) -> dict:
    return {
        "source": parse_source(args.source),
        "width": args.width, "height": args.height, "fps": args.fps,
        "backend": args.backend, "label": args.label,
        "host": args.host, "port": args.port,
        "stream_fps": args.stream_fps, "jpeg_quality": args.jpeg_quality,
        "stream_max_width": args.stream_max_width,
        "vcam_fps": args.vcam_fps, "vcam_device": args.vcam_device,
        "vcam_backend": args.vcam_backend,
        "rtsp_url": args.rtsp_url, "rtsp_fps": args.rtsp_fps,
        "rtsp_bitrate": args.rtsp_bitrate, "ffmpeg": args.ffmpeg,
        "log_level": args.log_level,
        "vcam_enabled": (False if args.no_vcam else None),
    }


def main() -> None:
    multiprocessing.freeze_support()  # required for safe frozen (PyInstaller) startup
    args = build_parser().parse_args()

    # Launched by the Service Control Manager.
    if args.run_as_service:
        import service
        service.run_as_service()
        return

    setup_logging(args.log_level or "info")

    # Virtual-camera setup, then exit.
    if args.install_vcam or args.uninstall_vcam or args.check_vcam:
        import vcam_install
        if args.install_vcam:
            vcam_install.install()
        elif args.uninstall_vcam:
            vcam_install.uninstall()
        else:
            vcam_install.check()
        return

    # Diagnostics, then exit.
    if args.list_cameras:
        import camera_list
        camera_list.list_cameras(max_index=args.max_index, backend=args.backend or "auto")
        return

    # Login auto-start (user session), then exit.
    if args.install_startup or args.uninstall_startup or args.startup_status:
        import startup
        if args.install_startup:
            extra = ""
            if args.vcam_bridge is not None:
                extra = "--vcam-bridge"
                if args.vcam_bridge:  # an explicit URL was given
                    extra += f' "{args.vcam_bridge}"'
            startup.install(extra)
        elif args.uninstall_startup:
            startup.uninstall()
        else:
            startup.status()
        return

    # Resolve settings: defaults < config file < CLI.
    config_path = args.config or default_config_path()
    cfg = resolve_config(_cli_overrides(args), load_config_file(config_path))

    # Write config, then exit.
    if args.write_config:
        path = write_config_file(config_path, cfg)
        print(f"Wrote configuration to {path}")
        return

    # Windows service control, then exit.
    if args.install_service or args.uninstall_service or args.start_service or args.stop_service:
        import service
        try:
            if args.install_service:
                write_config_file(config_path, cfg)  # persist current settings for the service
                print(f"Saved settings to {config_path}")
                service.install()
            elif args.uninstall_service:
                service.uninstall()
            elif args.start_service:
                service.start()
            else:
                service.stop()
        except Exception as exc:  # noqa: BLE001
            print(f"Service command failed: {exc}")
            print("Tip: run this from an *administrator* terminal.")
        return

    # Virtual-camera bridge mode (user session, feeds vcam from the local stream).
    if args.vcam_bridge is not None:
        url = args.vcam_bridge or f"http://localhost:{cfg.port}/stream.mjpg"
        run_vcam_bridge(url, cfg)
        return

    # Normal interactive run (Ctrl+C to quit).
    AppRunner(cfg).run_blocking(handle_signals=True)


if __name__ == "__main__":
    main()
