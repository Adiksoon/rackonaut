"""Large demonstration view rendered from a native-resolution analysis."""

from dataclasses import dataclass, field

import cv2
import numpy as np

BACKGROUND = (28, 22, 17)
PANEL = (44, 36, 29)
LINE = (72, 57, 46)
WHITE = (251, 246, 236)
MUTED = (169, 155, 136)
GREEN = (151, 231, 70)
AMBER = (65, 191, 255)
CYAN = (248, 213, 107)
GRAY = (168, 159, 151)
FONT = cv2.FONT_HERSHEY_DUPLEX


@dataclass
class OverlayState:
    inspection_id: str
    fps: float = 0
    inspected: int = 0
    total: int = 0
    api_status: str = "LOCAL"
    api_detail: str = "No backend configured"
    counts: dict = field(default_factory=dict)
    mode: str = "LIVE CAMERA"


def colour(classification):
    if classification.label_status in ("unreadable", "unknown"):
        return AMBER
    return GREEN


def text(canvas, message, x, y, size=.6, shade=WHITE, weight=1):
    cv2.putText(canvas, str(message), (x, y), FONT, size, shade, weight, cv2.LINE_AA)


def crop_polygon(polygon, factor, origin):
    if not np.isfinite(polygon).all():
        return None
    return np.rint(np.clip(polygon * factor + origin, -10000, 10000)).astype(np.int32)


def render(image, result, state):
    canvas = np.full((684, 1200, 3), BACKGROUND, dtype=np.uint8)
    cv2.rectangle(canvas, (0, 0), (1199, 74), PANEL, -1)
    cv2.rectangle(canvas, (0, 0), (7, 73), GREEN, -1)
    text(canvas, "RACKONAUT", 26, 45, 1.14, WHITE, 2)
    text(canvas, "LIVE INVENTORY INSPECTION", 247, 44, .48, MUTED)
    text(canvas, state.inspection_id[:35], 758, 44, .57, CYAN, 1)
    text(canvas, f"{state.fps:04.1f} FPS", 1050, 44, .67, GREEN, 2)

    scale = min(760 / image.shape[1], 560 / image.shape[0])
    video = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    vh, vw = video.shape[:2]
    view = video.copy()
    zero = np.float32([0, 0])
    for reading in result.readings:
        c = colour(reading.classification)
        target = crop_polygon(reading.label_roi, scale, zero)
        shelf = crop_polygon(reading.shelf_roi, scale, zero)
        if target is not None:
            cv2.polylines(view, [target], True, c, 2, cv2.LINE_AA)
        if shelf is not None:
            cv2.polylines(view, [shelf], True, AMBER, 2, cv2.LINE_AA)
    for tag in result.markers:
        c = CYAN if tag.kind == "slot" else GREEN
        polygon = crop_polygon(tag.corners, scale, zero)
        cv2.polylines(view, [polygon], True, c, 3, cv2.LINE_AA)
        x, y = polygon.min(axis=0)
        text(view, tag.name, max(6, x), max(17, y - 8), .48, (10, 10, 10), 3)
        text(view, tag.name, max(6, x), max(17, y - 8), .48, c, 1)
    # Preserve the camera's aspect ratio inside a fixed presentation frame.
    xv, yv = 22 + (760 - vw) // 2, 94 + (560 - vh) // 2
    cv2.rectangle(canvas, (21, 93), (782, 654), LINE, 1)
    canvas[yv:yv + vh, xv:xv + vw] = view
    text(canvas, f"{state.mode}   /   NATIVE {image.shape[1]} x {image.shape[0]}", 25, 674, .42, MUTED)

    x = 803
    cv2.rectangle(canvas, (800, 93), (1177, 654), PANEL, -1)
    text(canvas, "LOCATIONS INSPECTED", x + 17, 127, .48, MUTED)
    text(canvas, f"{state.inspected:02d} / {state.total:02d}", x + 15, 173, 1.18, WHITE, 2)
    cv2.line(canvas, (x + 16, 191), (1158, 191), LINE, 1)
    text(canvas, f"API   {state.api_status}", x + 17, 218, .58,
         GREEN if state.api_status == "SENT" else AMBER, 1)
    text(canvas, state.api_detail[:42], x + 17, 243, .44, MUTED)
    cv2.line(canvas, (x + 16, 263), (1158, 263), LINE, 1)
    text(canvas, "IN THIS FRAME", x + 17, 291, .50, MUTED)
    if not result.readings:
        text(canvas, "No location marker in view", x + 17, 334, .56, GRAY)
        text(canvas, "Face an inspection placard.", x + 17, 364, .47, MUTED)
    for index, reading in enumerate(result.readings[:3]):
        y = 308 + index * 90
        result_colour = colour(reading.classification)
        cv2.rectangle(canvas, (x + 16, y), (1158, y + 78), BACKGROUND, -1)
        cv2.rectangle(canvas, (x + 16, y), (x + 19, y + 78), result_colour, -1)
        text(canvas, reading.slot.name, x + 31, y + 25, .62, WHITE)
        text(canvas, reading.classification.occupancy.upper(), x + 207, y + 25, .45, result_colour)
        label = reading.classification.pallet_id or reading.classification.label_status.replace("_", " ")
        text(canvas, f"Label  /  {label}", x + 31, y + 46, .45, result_colour)
        text(canvas, reading.reason, x + 31, y + 66, .43, MUTED)
    text(canvas, "CYAN  LOCATION   GREEN  PALLET", x + 17, 622, .41, MUTED)
    text(canvas, "OUTLINES  LABEL REGION + SHELF BAND", x + 17, 642, .39, MUTED)
    return canvas
