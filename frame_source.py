"""Single-reader camera capture with fan-out to many consumers.

Only this class ever touches the physical camera. Everything else (web,
websocket, virtual camera, RTSP) reads the most recent frame from here.
That is what avoids the Windows "device is already in use by another app"
problem: the OS sees exactly one consumer of the real camera.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger("capture")


class FrameSource:
    def __init__(
        self,
        source,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
        backend: Optional[int] = None,
        reconnect_delay: float = 2.0,
    ):
        self._source = source
        self._req_width = width
        self._req_height = height
        self._req_fps = fps
        self._backend = backend
        self._reconnect_delay = reconnect_delay

        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._seq = 0
        self._cond = threading.Condition()
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # live telemetry (read by the /status endpoint)
        self.actual_width = 0
        self.actual_height = 0
        self.measured_fps = 0.0
        self.connected = False
        self.last_error: Optional[str] = None
        self.started_at: Optional[float] = None

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._loop, name="capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running.clear()
        with self._cond:
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=3.0)
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    # ------------------------------------------------------------------ #
    # capture loop
    # ------------------------------------------------------------------ #
    def _open(self) -> Optional[cv2.VideoCapture]:
        if self._backend is not None:
            cap = cv2.VideoCapture(self._source, self._backend)
        else:
            cap = cv2.VideoCapture(self._source)
        if not cap.isOpened():
            cap.release()
            return None
        if self._req_width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._req_width)
        if self._req_height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._req_height)
        if self._req_fps:
            cap.set(cv2.CAP_PROP_FPS, self._req_fps)
        # Keep buffering low so we always serve the freshest frame.
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap

    def _loop(self) -> None:
        frames = 0
        t_window = time.monotonic()
        while self._running.is_set():
            if self._cap is None:
                self._cap = self._open()
                if self._cap is None:
                    self.connected = False
                    self.last_error = f"Could not open source {self._source!r}"
                    log.warning("%s; retrying in %.1fs", self.last_error, self._reconnect_delay)
                    time.sleep(self._reconnect_delay)
                    continue
                self.connected = True
                self.last_error = None
                log.info("Camera opened: %r", self._source)

            ok, frame = self._cap.read()
            if not ok or frame is None:
                self.connected = False
                self.last_error = "Frame read failed (device disconnected?)"
                log.warning("%s; reopening", self.last_error)
                self._cap.release()
                self._cap = None
                time.sleep(self._reconnect_delay)
                continue

            h, w = frame.shape[:2]
            self.actual_width, self.actual_height = w, h

            with self._cond:
                self._frame = frame
                self._seq += 1
                self._cond.notify_all()

            frames += 1
            now = time.monotonic()
            if now - t_window >= 1.0:
                self.measured_fps = frames / (now - t_window)
                frames = 0
                t_window = now

    # ------------------------------------------------------------------ #
    # consumer API
    # ------------------------------------------------------------------ #
    def snapshot(self) -> Tuple[Optional[np.ndarray], int]:
        """Return (copy of latest frame, sequence number) without blocking."""
        with self._cond:
            if self._frame is None:
                return None, self._seq
            return self._frame.copy(), self._seq

    def wait_for_frame(self, last_seq: int, timeout: float = 1.0) -> Tuple[Optional[np.ndarray], int]:
        """Block until a frame newer than last_seq exists (or timeout)."""
        with self._cond:
            if self._seq == last_seq:
                self._cond.wait(timeout=timeout)
            if self._frame is None:
                return None, self._seq
            return self._frame.copy(), self._seq
