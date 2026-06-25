"""Optional RTSP output.

Frames are written as raw BGR to an FFmpeg subprocess that encodes H.264 and
hands the stream to MediaMTX. We publish over RTMP (FFmpeg's RTMP/FLV muxer is
far more robust than its RTSP muxer, which trips MediaMTX's strict RTSP parser
with a "400 Bad Request"). MediaMTX converts protocols automatically, so the
stream is still readable at the original rtsp:// URL.

Requires:
  * FFmpeg installed / bundled.
  * A media server listening locally (MediaMTX). RTMP publish goes to port 1935,
    which MediaMTX enables by default; reading happens on the rtsp:// URL (8554).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from urllib.parse import urlparse

log = logging.getLogger("rtsp")


def _rtmp_from_rtsp(rtsp_url: str) -> str:
    """rtsp://host:8554/cam  ->  rtmp://host:1935/cam"""
    u = urlparse(rtsp_url)
    host = u.hostname or "localhost"
    path = u.path or "/stream"
    return f"rtmp://{host}:1935{path}"


class RTSPPublisher:
    def __init__(self, source, url: str, fps: float = 25.0, bitrate: str = "3M", ffmpeg: str = "ffmpeg"):
        self._source = source
        self._url = url                          # rtsp:// URL clients read from
        self._publish_url = _rtmp_from_rtsp(url)  # rtmp:// URL we push to
        self._fps = max(1.0, float(fps))
        self._bitrate = bitrate
        self._ffmpeg = ffmpeg
        self._proc = None
        self._running = threading.Event()
        self._thread = None

        self.available = shutil.which(ffmpeg) is not None
        self.active = False
        self.url = url
        self.last_error = None if self.available else f"{ffmpeg} not found on PATH"

    def start(self) -> None:
        if not self.available:
            log.warning("RTSP disabled: %s", self.last_error)
            return
        self._running.set()
        self._thread = threading.Thread(target=self._loop, name="rtsp", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running.clear()
        if self._proc and self._proc.poll() is None:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
            except Exception:
                pass
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3.0)
            except Exception:
                self._proc.kill()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _wait_first_frame(self):
        last = -1
        while self._running.is_set():
            frame, seq = self._source.wait_for_frame(last, timeout=1.0)
            if frame is not None:
                return frame
            last = seq
        return None

    def _build_cmd(self, w: int, h: int):
        return [
            self._ffmpeg,
            "-loglevel", "warning",
            # raw input from stdin
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{w}x{h}",
            "-r", str(self._fps),
            "-i", "-",
            "-an",  # no audio
            # H.264, low-latency
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-profile:v", "baseline",  # well-formed header MediaMTX accepts
            "-bf", "0",                # no B-frames (low latency, simpler header)
            "-b:v", self._bitrate,
            "-g", str(int(self._fps * 2)),
            # publish over RTMP (robust) -> MediaMTX serves it back as RTSP.
            "-f", "flv",
            self._publish_url,
        ]

    def _loop(self) -> None:
        import cv2  # local import; only needed if a resize is required

        frame = self._wait_first_frame()
        if frame is None:
            return
        h, w = frame.shape[:2]
        cmd = self._build_cmd(w, h)
        log.info("FFmpeg publish %s  (read at %s)  %dx%d @ %.0ffps",
                 self._publish_url, self._url, w, h, self._fps)

        try:
            self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            log.error("Could not start FFmpeg: %s", exc)
            return

        self.active = True
        interval = 1.0 / self._fps
        next_t = time.monotonic()
        try:
            while self._running.is_set():
                f, _ = self._source.snapshot()
                if f is not None:
                    if f.shape[1] != w or f.shape[0] != h:
                        f = cv2.resize(f, (w, h))
                    try:
                        self._proc.stdin.write(f.tobytes())
                    except (BrokenPipeError, ValueError):
                        self.last_error = "FFmpeg pipe closed"
                        log.error(self.last_error)
                        break
                if self._proc.poll() is not None:
                    self.last_error = f"FFmpeg exited (code {self._proc.returncode})"
                    log.error(self.last_error)
                    break
                next_t += interval
                sleep = next_t - time.monotonic()
                if sleep > 0:
                    time.sleep(sleep)
                else:
                    next_t = time.monotonic()  # we fell behind; resync
        finally:
            self.active = False
