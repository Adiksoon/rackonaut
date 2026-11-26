"""Inspect a saved native frame using the same image logic as the live node."""

import argparse
import json

import cv2
from ament_index_python.packages import get_package_share_path

from .overlay import OverlayState, render
from .vision import Inspector, load_markers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--annotated")
    parser.add_argument("--markers", default=get_package_share_path("rackonaut_perception") / "config/markers.json")
    args = parser.parse_args()
    image = cv2.imread(args.image)
    if image is None:
        parser.error(f"Cannot read {args.image}")
    locations, pallets = load_markers(args.markers)
    result = Inspector(locations, pallets).inspect(image)
    print(json.dumps([{"slot_id": r.slot.name, **vars(r.classification), "reason": r.reason} for r in result.readings]))
    if args.annotated:
        panel = render(image, result, OverlayState("OFFLINE FRAME", total=len(locations), mode="SAVED CAMERA FRAME"))
        if not cv2.imwrite(args.annotated, panel):
            raise RuntimeError(f"Cannot write {args.annotated}")
