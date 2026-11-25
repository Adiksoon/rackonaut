#!/usr/bin/python3
"""Regenerate the small synthetic camera images using Ubuntu OpenCV."""
from pathlib import Path

import cv2
import numpy as np

DIRECTORY = Path(__file__).resolve().parent


def write(name, image):
    if not cv2.imwrite(str(DIRECTORY / name), image):
        raise RuntimeError(f"Could not write {name}")


def label(text):
    image = np.full((54, 204, 3), 245, np.uint8)
    cv2.rectangle(image, (1, 1), (202, 52), (35, 35, 35), 2)
    cv2.putText(image, text, (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.92, (25, 25, 25), 2, cv2.LINE_AA)
    return image


def main():
    rack = np.full((360, 640, 3), (170, 181, 186), np.uint8)
    for x in (56, 306, 556):
        cv2.rectangle(rack, (x, 60), (x + 16, 345), (132, 93, 42), -1)
    for y in (60, 189, 318):
        cv2.rectangle(rack, (56, y), (572, y + 12), (132, 93, 42), -1)
    cv2.rectangle(rack, (105, 210), (284, 316), (90, 152, 190), -1)
    slot_label = label("A-01-01")
    pallet_label = label("P001")
    rack[139:183, 77:243] = cv2.resize(slot_label, (166, 44))
    rack[245:289, 115:281] = cv2.resize(pallet_label, (166, 44))
    cv2.putText(rack, "SYNTHETIC FIXTURE", (57, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (34, 34, 34), 2, cv2.LINE_AA)
    write("mock_rack.png", rack)
    write("mock_slot_label.png", slot_label)
    write("mock_pallet_label.png", pallet_label)


if __name__ == "__main__":
    main()
