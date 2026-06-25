"""Persistent configuration in ProgramData.

Settings live in  %ProgramData%/CameraMonitor/config.json  (typically
C:/ProgramData/CameraMonitor/config.json). This is machine-wide and writable by
the LocalSystem account, so the Windows service can read it.

Precedence when the app resolves its settings:
    built-in defaults (config.Config)  <  config file  <  command-line flags
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from typing import Optional

from config import Config

APP_NAME = "CameraMonitor"

# Only these fields are persisted / overridable via the file.
_CONFIG_KEYS = [
    "source", "width", "height", "fps", "backend", "label",
    "host", "port", "stream_fps", "jpeg_quality", "stream_max_width",
    "vcam_enabled", "vcam_fps", "vcam_device", "vcam_backend",
    "rtsp_url", "rtsp_fps", "rtsp_bitrate", "ffmpeg", "log_level",
]


def app_data_dir() -> str:
    base = (os.environ.get("ProgramData")
            or os.environ.get("ALLUSERSPROFILE")
            or r"C:\ProgramData")
    return os.path.join(base, APP_NAME)


def default_config_path() -> str:
    return os.path.join(app_data_dir(), "config.json")


def log_dir() -> str:
    return os.path.join(app_data_dir(), "logs")


def setup_logging(level: str = "info") -> None:
    """Configure logging so it works whether or not the app has a console.

    Always writes to a rotating file in ProgramData; adds a console handler only
    when a real stderr exists (i.e. a console build). This lets you build with
    `console=False` for a silent end-user app without losing logs or crashing on
    a missing stderr.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(name)-8s %(message)s", "%H:%M:%S")

    if getattr(sys, "stderr", None) is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

    try:
        os.makedirs(log_dir(), exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir(), "app.log"), maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass


def load_config_file(path: Optional[str]) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k in _CONFIG_KEYS}


def write_config_file(path: str, cfg: Config) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {k: getattr(cfg, k) for k in _CONFIG_KEYS}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


def resolve_config(cli_overrides: dict, file_cfg: dict) -> Config:
    """defaults < file < CLI. CLI/file values of None mean 'not set'."""
    cfg = Config()
    for k, v in file_cfg.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    for k, v in cli_overrides.items():
        if v is not None and hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg
