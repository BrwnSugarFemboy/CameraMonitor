"""Expose the captured feed as a system virtual camera.

Other programs (Zoom, Teams, OBS, browsers, any app with a camera picker)
then read from the virtual camera instead of the physical one, so they never
contend for the real device.

Windows backend: install OBS Studio (the built-in OBS Virtual Camera is used).
Linux backend: v4l2loopback. macOS backend: OBS Virtual Camera.
If pyvirtualcam or its backend is unavailable, this degrades gracefully and
the rest of the program keeps running.
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger("vcam")

try:
    import pyvirtualcam

    _HAS = True
except Exception as exc:  # noqa: BLE001 - any import/backend failure
    pyvirtualcam = None  # type: ignore
    _HAS = False
    _IMPORT_ERROR = str(exc)


class VirtualCameraWriter:
    def __init__(self, source, fps: float = 30.0, device=None, backend=None):
        self._source = source
        self._fps = max(1.0, float(fps))
        self._device = device
        self._backend = backend
        self._running = threading.Event()
        self._thread = None

        self.available = _HAS
        self.active = False
        self.device_name = None
        self.last_error = None if _HAS else f"pyvirtualcam unavailable ({_IMPORT_ERROR})"

    def start(self) -> None:
        if not self.available:
            log.warning("Virtual camera disabled: %s", self.last_error)
            return
        self._running.set()
        self._thread = threading.Thread(target=self._loop, name="vcam", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running.clear()
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

    def _loop(self) -> None:
        import cv2  # local import; only needed if a resize is required

        frame = self._wait_first_frame()
        if frame is None:
            return
        h, w = frame.shape[:2]

        kwargs = dict(width=w, height=h, fps=self._fps, fmt=pyvirtualcam.PixelFormat.BGR)
        if self._device:
            kwargs["device"] = self._device
        if self._backend:
            kwargs["backend"] = self._backend

        try:
            cam = pyvirtualcam.Camera(**kwargs)
        except Exception as exc:  # noqa: BLE001
            hint = ('No virtual-camera backend is registered. Run with '
                    '"--install-vcam" (bundled, no OBS needed) or install OBS Studio.')
            self.last_error = f"{exc} | {hint}"
            self.active = False
            log.error("Could not start virtual camera: %s", exc)
            log.error("%s", hint)
            return

        self.active = True
        self.device_name = cam.device
        log.info("Virtual camera running: %s (%dx%d @ %.0ffps)", cam.device, w, h, self._fps)

        try:
            with cam:
                while self._running.is_set():
                    f, _ = self._source.snapshot()
                    if f is not None:
                        if f.shape[1] != w or f.shape[0] != h:
                            f = cv2.resize(f, (w, h))
                        cam.send(f)  # BGR uint8 frame
                    # Maintain a steady output framerate even if the camera stalls;
                    # consumers of a virtual webcam expect constant frame delivery.
                    cam.sleep_until_next_frame()
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            log.error("Virtual camera stopped: %s", exc)
        finally:
            self.active = False
