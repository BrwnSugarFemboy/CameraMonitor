"""Locate resources/binaries that may be bundled into a PyInstaller build.

When frozen with PyInstaller (onefile), data files are extracted at runtime to
``sys._MEIPASS``. When running from source, they sit next to this file. This
module hides that difference so the rest of the app can just ask for a path.
"""
from __future__ import annotations

import os
import shutil
import sys
from typing import Optional


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_path(rel_path: str) -> str:
    """Absolute path to a bundled resource, in source or frozen builds."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel_path)


def _exe(name: str) -> str:
    return name + ".exe" if sys.platform.startswith("win") else name


def find_ffmpeg(configured: str = "ffmpeg") -> str:
    """Return the ffmpeg to use.

    Preference order:
      1. a copy bundled under ./bin (so the user installs nothing)
      2. the configured path / name (which may resolve via PATH)
    """
    bundled = resource_path(os.path.join("bin", _exe("ffmpeg")))
    if os.path.exists(bundled):
        return bundled
    # honour an explicit path if the user gave one
    if configured and (os.path.sep in configured or os.path.exists(configured)):
        return configured
    found = shutil.which(configured or "ffmpeg")
    return found or configured


def find_mediamtx() -> Optional[str]:
    """Path to a bundled MediaMTX binary, or None if not packaged."""
    bundled = resource_path(os.path.join("bin", _exe("mediamtx")))
    if os.path.exists(bundled):
        return bundled
    return shutil.which("mediamtx")


def mediamtx_config() -> Optional[str]:
    """Path to a bundled mediamtx.yml, if present."""
    cfg = resource_path(os.path.join("bin", "mediamtx.yml"))
    return cfg if os.path.exists(cfg) else None
