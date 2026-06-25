"""Runtime configuration for the camera monitor.

A single Config object is built once in main.py from command-line arguments
and passed to the web server and the status endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


@dataclass
class Config:
    # --- capture ---
    source: Union[int, str] = 0          # camera index, file path, or stream URL
    width: Optional[int] = None          # requested capture width  (device may ignore)
    height: Optional[int] = None         # requested capture height
    fps: Optional[float] = None          # requested capture fps
    backend: str = "auto"                # auto | dshow | msmf | v4l2 | any
    label: str = "CAM-01"               # shown in the web viewer header

    # --- web / websocket stream ---
    host: str = "0.0.0.0"
    port: int = 8000
    stream_fps: float = 20.0             # frames/sec pushed to browsers
    jpeg_quality: int = 80               # 1-100
    stream_max_width: int = 0            # downscale browser stream if wider; 0 = off

    # --- virtual camera ---
    vcam_enabled: bool = True
    vcam_fps: Optional[float] = None     # defaults to capture fps or 30
    vcam_device: Optional[str] = None    # e.g. "OBS Virtual Camera"
    vcam_backend: Optional[str] = None   # e.g. "obs", "unitycapture", "v4l2loopback"

    # --- rtsp (optional) ---
    rtsp_url: Optional[str] = None       # e.g. rtsp://localhost:8554/cam ; None = off
    rtsp_fps: float = 25.0
    rtsp_bitrate: str = "3M"
    ffmpeg: str = "ffmpeg"               # ffmpeg binary path

    # --- misc ---
    log_level: str = "info"
    started_at: float = field(default=0.0)
