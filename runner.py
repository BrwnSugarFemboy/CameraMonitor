"""Builds and runs all the components from a Config.

Both interactive mode (main.py) and the Windows service (service.py) use this,
so they behave identically. The only difference is that the service runs with
OS signal handlers disabled and uvicorn's console logging turned off.
"""
from __future__ import annotations

import logging
import sys
import time

import cv2
import uvicorn

from frame_source import FrameSource
from virtual_camera import VirtualCameraWriter
from rtsp_publisher import RTSPPublisher
from webserver import create_app
from resources import find_ffmpeg
from embedded_rtsp import EmbeddedRTSPServer

log = logging.getLogger("runner")


def resolve_backend(name: str):
    name = (name or "auto").lower()
    table = {
        "any": getattr(cv2, "CAP_ANY", 0),
        "dshow": getattr(cv2, "CAP_DSHOW", None),
        "msmf": getattr(cv2, "CAP_MSMF", None),
        "v4l2": getattr(cv2, "CAP_V4L2", None),
    }
    if name == "auto":
        # DirectShow is the most reliable default for USB webcams on Windows.
        if sys.platform.startswith("win"):
            return getattr(cv2, "CAP_DSHOW", None)
        return None  # OpenCV default elsewhere
    return table.get(name)


class AppRunner:
    def __init__(self, cfg, service_mode: bool = False):
        self.cfg = cfg
        self.service_mode = service_mode
        self.source = None
        self.vcam = None
        self.rtsp = None
        self.rtsp_server = None
        self.server = None

    def build(self):
        cfg = self.cfg

        # 1) the one and only reader of the physical camera
        self.source = FrameSource(
            cfg.source, width=cfg.width, height=cfg.height, fps=cfg.fps,
            backend=resolve_backend(cfg.backend),
        )
        self.source.start()

        # 2) virtual camera (optional)
        if cfg.vcam_enabled:
            self.vcam = VirtualCameraWriter(
                self.source, fps=cfg.vcam_fps or cfg.fps or 30.0,
                device=cfg.vcam_device, backend=cfg.vcam_backend,
            )
            self.vcam.start()

        # 3) RTSP (optional)
        if cfg.rtsp_url:
            self.rtsp_server = EmbeddedRTSPServer()
            self.rtsp_server.start()
            if self.rtsp_server.available:
                time.sleep(1.0)  # let the server bind before publishing
            self.rtsp = RTSPPublisher(
                self.source, cfg.rtsp_url, fps=cfg.rtsp_fps,
                bitrate=cfg.rtsp_bitrate, ffmpeg=find_ffmpeg(cfg.ffmpeg),
            )
            self.rtsp.start()

        # 4) web + websocket
        app = create_app(self.source, self.vcam, self.rtsp, cfg)
        host_display = "localhost" if cfg.host == "0.0.0.0" else cfg.host
        log.info("Viewer:    http://%s:%d/", host_display, cfg.port)
        log.info("MJPEG:     http://localhost:%d/stream.mjpg", cfg.port)
        log.info("WebSocket: ws://localhost:%d/ws", cfg.port)
        if self.rtsp:
            log.info("RTSP:      %s", cfg.rtsp_url)

        uv = dict(app=app, host=cfg.host, port=cfg.port, log_level=cfg.log_level)
        if self.service_mode:
            # No console in a service: don't let uvicorn attach stdout/stderr
            # handlers (they can be invalid and crash startup).
            uv["log_config"] = None
        self.server = uvicorn.Server(uvicorn.Config(**uv))
        return self.server

    def run_blocking(self, handle_signals: bool = True):
        if self.server is None:
            self.build()
        if not handle_signals:
            self.server.install_signal_handlers = lambda: None
        try:
            self.server.run()  # blocks until Ctrl+C (interactive) or stop() (service)
        finally:
            self.shutdown()

    def stop(self):
        """Ask the server to exit cleanly (called from the service stop handler)."""
        if self.server is not None:
            self.server.should_exit = True

    def shutdown(self):
        log.info("Shutting down...")
        if self.rtsp:
            self.rtsp.stop()
        if self.rtsp_server:
            self.rtsp_server.stop()
        if self.vcam:
            self.vcam.stop()
        if self.source:
            self.source.stop()
