"""FastAPI application exposing the feed over HTTP and WebSocket.

Endpoints
  GET  /              -> the web viewer page
  GET  /stream.mjpg   -> MJPEG stream (works directly in an <img> tag)
  WS   /ws            -> binary JPEG frames over a WebSocket
  GET  /snapshot.jpg  -> single most-recent frame
  GET  /status        -> JSON telemetry consumed by the viewer
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from viewer import VIEWER_HTML

log = logging.getLogger("web")


def create_app(source, vcam, rtsp, cfg) -> FastAPI:
    app = FastAPI(title="Camera Monitor", docs_url=None, redoc_url=None)
    # viewer counters (only mutated inside the single asyncio event loop)
    counters = {"mjpeg": 0, "ws": 0}

    def encode_jpeg(frame) -> Optional[bytes]:
        if cfg.stream_max_width and frame.shape[1] > cfg.stream_max_width:
            scale = cfg.stream_max_width / frame.shape[1]
            frame = cv2.resize(frame, (cfg.stream_max_width, int(frame.shape[0] * scale)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(cfg.jpeg_quality)])
        return buf.tobytes() if ok else None

    # ------------------------------------------------------------------ #
    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(VIEWER_HTML)

    @app.get("/status")
    async def status():
        def feature(obj):
            if obj is None:
                return {"enabled": False, "active": False, "error": None}
            return {
                "enabled": getattr(obj, "available", False),
                "active": getattr(obj, "active", False),
                "device": getattr(obj, "device_name", None) or getattr(obj, "url", None),
                "error": getattr(obj, "last_error", None),
            }

        uptime = time.time() - (source.started_at or time.time())
        return JSONResponse({
            "label": cfg.label,
            "source": str(cfg.source),
            "connected": source.connected,
            "width": source.actual_width,
            "height": source.actual_height,
            "measured_fps": round(source.measured_fps, 2),
            "stream_fps": cfg.stream_fps,
            "viewers": counters["mjpeg"] + counters["ws"],
            "uptime": uptime,
            "virtual_camera": feature(vcam),
            "rtsp": feature(rtsp),
        })

    @app.get("/snapshot.jpg")
    async def snapshot():
        frame, _ = source.snapshot()
        if frame is None:
            return Response(status_code=503, content=b"no frame")
        data = await asyncio.to_thread(encode_jpeg, frame)
        if not data:
            return Response(status_code=500, content=b"encode failed")
        return Response(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})

    @app.get("/stream.mjpg")
    async def mjpeg():
        async def gen():
            counters["mjpeg"] += 1
            last = -1
            dt = 1.0 / cfg.stream_fps
            try:
                while True:
                    t0 = time.monotonic()
                    frame, seq = source.snapshot()
                    if frame is not None and seq != last:
                        last = seq
                        data = await asyncio.to_thread(encode_jpeg, frame)
                        if data:
                            yield (b"--frame\r\nContent-Type: image/jpeg\r\n"
                                   b"Content-Length: " + str(len(data)).encode() +
                                   b"\r\n\r\n" + data + b"\r\n")
                    await asyncio.sleep(max(0.0, dt - (time.monotonic() - t0)))
            finally:
                counters["mjpeg"] -= 1

        return StreamingResponse(
            gen(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        counters["ws"] += 1
        last = -1
        dt = 1.0 / cfg.stream_fps
        try:
            while True:
                t0 = time.monotonic()
                frame, seq = source.snapshot()
                if frame is not None and seq != last:
                    last = seq
                    data = await asyncio.to_thread(encode_jpeg, frame)
                    if data:
                        await ws.send_bytes(data)
                await asyncio.sleep(max(0.0, dt - (time.monotonic() - t0)))
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001 - client dropped, etc.
            log.debug("ws closed: %s", exc)
        finally:
            counters["ws"] -= 1

    return app
