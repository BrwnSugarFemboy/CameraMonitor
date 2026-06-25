"""List available cameras and the index OpenCV uses for each.

Probes indices 0..N with OpenCV: reports whether each opens, its resolution, and
whether the frame is actually black (closed shutter / IR camera / privacy block).
On Windows it also shows DirectShow device names when pygrabber is installed
(`pip install pygrabber`); those names line up with the `dshow` backend's index
order.
"""
from __future__ import annotations

import sys

import cv2


def _backend_const(name: str):
    name = (name or "auto").lower()
    table = {
        "any": getattr(cv2, "CAP_ANY", 0),
        "dshow": getattr(cv2, "CAP_DSHOW", None),
        "msmf": getattr(cv2, "CAP_MSMF", None),
        "v4l2": getattr(cv2, "CAP_V4L2", None),
    }
    if name == "auto":
        return None
    return table.get(name)


def _device_names():
    """Friendly DirectShow names in index order (Windows + pygrabber only)."""
    if not sys.platform.startswith("win"):
        return None
    try:
        from pygrabber.dshow_graph import FilterGraph
        return FilterGraph().get_input_devices()
    except Exception:
        return None


def list_cameras(max_index: int = 8, backend: str = "auto") -> None:
    names = _device_names()
    be = _backend_const(backend)

    print(f"Scanning camera indices 0..{max_index - 1}  (backend: {backend})\n")

    if names:
        print("DirectShow device names (these match --backend dshow indices):")
        for i, n in enumerate(names):
            print(f"  [{i}] {n}")
        print()
    elif sys.platform.startswith("win"):
        print("(Install pygrabber for device names:  pip install pygrabber)\n")

    found = 0
    for i in range(max_index):
        cap = cv2.VideoCapture(i, be) if be is not None else cv2.VideoCapture(i)
        if not cap.isOpened():
            cap.release()
            continue

        ok, frame = cap.read()
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        if ok and frame is not None:
            mean = float(frame.mean())
            note = "live picture" if mean > 6 else "opens but BLACK (shutter/IR/privacy?)"
        else:
            note = "opens but returns no frame"
        name = f"  - {names[i]}" if names and i < len(names) else ""
        print(f"  index {i}:  {w}x{h:<6}  {note}{name}")
        found += 1

    if found == 0:
        print("  no cameras opened.")
        print("  Try a different backend, e.g.  --list-cameras --backend msmf")
    print(f"\nUse one with:  --source <index>"
          + (f"  --backend {backend}" if backend != "auto" else ""))
