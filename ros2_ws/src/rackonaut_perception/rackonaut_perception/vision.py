"""Pixel-based inference for the Rackonaut warehouse's placard and shelf geometry."""

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


UNIT_MARKER = np.float32([[-.5, -.5], [.5, -.5], [.5, .5], [-.5, .5]])
# Coordinates are multiples of the slot tag's side, relative to its centre.
PALLET_LABEL = (2.20, -1.95, 4.63, -.52)
SHELF_BAND = (2.28, .12, 4.78, .47)
CLEAR_SHELF = (1.70, .12, 2.10, .47)
BASE_BEAM = (2.28, .67, 4.78, .98)


def load_markers(path):
    book = json.loads(Path(path).read_text())
    if book["dictionary"] != "DICT_4X4_50":
        raise ValueError("The inspection geometry expects DICT_4X4_50.")
    locations = {int(key): value for key, value in book["locations"].items()}
    pallets = {int(key): value for key, value in book["pallets"].items()}
    if locations.keys() & pallets.keys() or not all(0 <= tag < 50 for tag in locations.keys() | pallets.keys()):
        raise ValueError("Marker IDs must belong to one namespace in DICT_4X4_50.")
    return locations, pallets


def project(points, transform):
    return cv2.perspectiveTransform(np.float32(points).reshape(1, -1, 2), transform)[0]


def rectangle(bounds):
    left, top, right, bottom = bounds
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def inside(point, bounds):
    x, y = point
    left, top, right, bottom = bounds
    return left <= x <= right and top <= y <= bottom


@dataclass
class Tag:
    number: int
    name: str
    kind: str
    corners: np.ndarray

    @property
    def centre(self):
        return np.mean(self.corners, axis=0)

    @property
    def edges(self):
        return np.linalg.norm(self.corners - np.roll(self.corners, 1, axis=0), axis=1)


@dataclass(frozen=True)
class Classification:
    occupancy: str
    label_status: str
    pallet_id: str | None = None


@dataclass
class Reading:
    slot: Tag
    classification: Classification
    reason: str
    label_roi: np.ndarray
    shelf_roi: np.ndarray


@dataclass
class FrameResult:
    markers: list[Tag]
    readings: list[Reading]


EMPTY = Classification("empty", "not_applicable")
UNREADABLE = Classification("occupied", "unreadable")
UNCERTAIN = Classification("uncertain", "unknown")


def hsv_patch(image, transform, bounds, width=48, height=10):
    polygon = project(rectangle(bounds), transform)
    if not np.isfinite(polygon).all():
        return None
    height_px, width_px = image.shape[:2]
    if ((polygon < 1) | (polygon >= np.float32([width_px - 1, height_px - 1]))).any():
        return None
    plane = cv2.getPerspectiveTransform(polygon, np.float32(rectangle((0, 0, width - 1, height - 1))))
    patch = cv2.warpPerspective(image, plane, (width, height))
    return cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)


def visible_shelf(hsv):
    h, s, v = cv2.split(hsv)
    return (h >= 5) & (h <= 30) & (s >= 145) & (v >= 115)


def classify_deck(image, transform):
    band = hsv_patch(image, transform, SHELF_BAND)
    reference = hsv_patch(image, transform, CLEAR_SHELF, width=12)
    beam = hsv_patch(image, transform, BASE_BEAM)
    label = project(rectangle(PALLET_LABEL), transform)
    h_px, w_px = image.shape[:2]
    if (any(patch is None for patch in (band, reference, beam))
            or not np.isfinite(label).all()
            or ((label < 1) | (label >= np.float32([w_px - 1, h_px - 1]))).any()):
        return UNCERTAIN, "Frame the whole slot"
    if visible_shelf(reference).mean() < .43 or visible_shelf(beam).mean() < .55:
        return UNCERTAIN, "Shelf edge unclear"

    h, s, v = cv2.split(band)
    ref_value = np.median(reference[:, :, 2][visible_shelf(reference)])
    wood = ((h >= 6) & (h <= 31) & (s >= 61) & (s < 148)
            & (v >= 54) & (v < .76 * ref_value))
    wood_coverage = float(wood.mean())
    shelf_coverage = float((visible_shelf(band) & (v > .72 * ref_value)).mean())
    if wood_coverage >= .60 and np.count_nonzero(wood.mean(axis=0) > .55) >= 31:
        return UNREADABLE, "Pallet base visible"
    if shelf_coverage >= .80 and wood_coverage < .10:
        return EMPTY, "Clear shelf surface"
    return UNCERTAIN, "Shelf partly obscured"


class Inspector:
    def __init__(self, locations, pallets):
        self.locations = locations
        self.pallets = pallets
        self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.parameters = cv2.aruco.DetectorParameters_create()

    def detect(self, image):
        corners, ids, _ = cv2.aruco.detectMarkers(
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), self.dictionary, parameters=self.parameters
        )
        if ids is None:
            return []
        tags = []
        for number, points in zip(ids.ravel(), corners):
            number = int(number)
            if number in self.locations:
                tags.append(Tag(number, self.locations[number], "slot", points[0]))
            elif number in self.pallets:
                tags.append(Tag(number, self.pallets[number], "pallet", points[0]))
        return tags

    def inspect(self, image):
        tags = self.detect(image)
        pallets = [tag for tag in tags if tag.kind == "pallet"]
        slots = [tag for tag in tags if tag.kind == "slot"]
        candidates = {}
        for slot in slots:
            transform = cv2.getPerspectiveTransform(UNIT_MARKER, slot.corners)
            inverse = cv2.getPerspectiveTransform(slot.corners, UNIT_MARKER)
            matches = [
                index for index, tag in enumerate(pallets)
                if .48 < np.median(tag.edges) / np.median(slot.edges) < 1.30
                and inside(project([tag.centre], inverse)[0], PALLET_LABEL)
            ]
            candidates[slot.name] = (slot, transform, matches)
        readings = []
        for slot, transform, matches in candidates.values():
            edge_lengths = slot.edges
            if sum(tag.name == slot.name for tag in slots) != 1:
                classification, reason = UNCERTAIN, "Duplicate location marker"
            elif min(edge_lengths) < 16 or min(edge_lengths) < .58 * max(edge_lengths):
                classification, reason = UNCERTAIN, "Move closer or face the rack"
            elif len(matches) > 1 or (matches and sum(matches[0] in m for _, _, m in candidates.values()) > 1):
                classification, reason = UNCERTAIN, "Pallet association ambiguous"
            elif matches:
                classification = Classification("occupied", "readable", pallets[matches[0]].name)
                reason = "Pallet label decoded"
            else:
                classification, reason = classify_deck(image, transform)
            readings.append(Reading(slot, classification, reason,
                                    project(rectangle(PALLET_LABEL), transform),
                                    project(rectangle(SHELF_BAND), transform)))
        return FrameResult(tags, sorted(readings, key=lambda reading: reading.slot.name))
