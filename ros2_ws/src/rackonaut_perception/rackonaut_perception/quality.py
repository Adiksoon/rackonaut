"""Assess the visible upper face of a showcase kraft carton."""

from dataclasses import dataclass

import cv2
import numpy as np

from .vision import UNIT_MARKER, project, rectangle


# Slot-marker units. The region lies above the pallet placard and inside
# the nominal carton edges. The bottom rows are a local lighting reference.
CARTON_FACE = (2.67, -2.72, 5.22, -1.91)
PATCH_WIDTH, PATCH_HEIGHT = 108, 36
PATCH_CORNERS = np.float32(rectangle((0, 0, PATCH_WIDTH - 1, PATCH_HEIGHT - 1)))
KERNEL = np.ones((3, 3), np.uint8)


@dataclass
class QualityVerdict:
    status: str
    reason: str
    region: np.ndarray | None = None
    defect: np.ndarray | None = None


def largest_region(mask, acceptable):
    clean = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, KERNEL)
    clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, KERNEL)
    _, _, stats, _ = cv2.connectedComponentsWithStats(clean, connectivity=8)
    return max((row for row in stats[1:] if acceptable(*row)), key=lambda row: row[4], default=None)


def inspect_carton(image, reading):
    if reading.classification.occupancy != "occupied":
        return QualityVerdict("UNCERTAIN", "Carton location unclear")

    corners = reading.slot.corners
    edges = reading.slot.edges
    if min(edges) < 26 or min(edges) < .75 * max(edges):
        return QualityVerdict("UNCERTAIN", "Move closer and face carton")
    to_image = cv2.getPerspectiveTransform(UNIT_MARKER, corners)
    region = project(rectangle(CARTON_FACE), to_image)
    height, width = image.shape[:2]
    if not np.isfinite(region).all() or ((region < 1) | (region >= [width - 1, height - 1])).any():
        return QualityVerdict("UNCERTAIN", "Frame the whole carton")

    to_patch = cv2.getPerspectiveTransform(region, PATCH_CORNERS)
    patch = cv2.warpPerspective(image, to_patch, (PATCH_WIDTH, PATCH_HEIGHT))
    hue, saturation, value = cv2.split(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV))
    kraft = (hue >= 8) & (hue <= 29) & (saturation >= 44) & (saturation <= 116)
    reference = kraft[-8:]
    if reference.mean() < .72 or kraft[:6].mean() < .42:
        return QualityVerdict("UNCERTAIN", "Carton outline incomplete", region)
    brightness = np.median(value[-8:][reference])
    if brightness < 65:
        return QualityVerdict("UNCERTAIN", "Carton face too dark", region)

    opening = largest_region(
        value < brightness * .74,
        lambda x, y, w, h, area: area >= 300 and x > 2 and x + w < PATCH_WIDTH - 2 and h >= 8,
    )
    notch = largest_region(
        ~kraft,
        lambda x, y, w, h, area: y <= 3 and 20 <= w <= 78 and h >= 10 and area >= 220,
    )
    bounds = opening if opening is not None else notch
    if bounds is not None:
        x, y, w, h, _ = bounds
        defect = project(rectangle((x, y, x + w - 1, y + h - 1)),
                         cv2.getPerspectiveTransform(PATCH_CORNERS, region))
        reason = "Dark surface break" if opening is not None else "Collapsed upper contour"
        return QualityVerdict("DAMAGED", reason, region, defect)
    if kraft.mean() >= .90 and (value < brightness * .82).mean() <= .045:
        return QualityVerdict("OK", "Visible face intact", region)
    return QualityVerdict("UNCERTAIN", "Surface evidence inconclusive", region)
