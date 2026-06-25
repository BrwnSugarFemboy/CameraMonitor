"""Run a bundled MediaMTX RTSP server in-process.

If a MediaMTX binary is packaged with the app (under ./bin), this launches it
so the RTSP publish target (rtsp://localhost:8554/...) is available without the
user installing or starting anything. If no binary is bundled and none is on
PATH, it does nothing and the app falls back to whatever external server (if
any) is running.
"""
from __future__ import annotations

import logging
import subprocess
import threading

from resources import find_mediamtx, mediamtx_config

log = logging.getLogger("rtsp-srv")


class EmbeddedRTSPServer:
    def __init__(self):
        self._bin = find_mediamtx()
        self._proc = None
        self._reader = None
        self.available = self._bin is not None

    def start(self) -> None:
        if not self.available:
            log.info("No bundled/installed MediaMTX found; "
                     "RTSP needs an external server if you use --rtsp.")
            return
        cmd = [self._bin]
        cfg = mediamtx_config()
        if cfg:
            cmd.append(cfg)

        try:
            # Capture output so MediaMTX's own logs (including the real reason
            # for any publish rejection) are visible through our logger.
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )
            self._reader = threading.Thread(target=self._pump, name="rtsp-srv-log", daemon=True)
            self._reader.start()
            log.info("Started bundled MediaMTX: %s", self._bin)
        except Exception as exc:  # noqa: BLE001
            self.available = False
            log.error("Could not start MediaMTX: %s", exc)

    def _pump(self) -> None:
        try:
            for line in self._proc.stdout:
                line = line.rstrip()
                if line:
                    log.info("%s", line)
        except Exception:
            pass

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3.0)
            except Exception:
                self._proc.kill()
