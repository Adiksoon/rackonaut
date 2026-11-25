"""Bounded retry policy driven by accepted readings and linked visual evidence."""

MAX_RETRIES = 2
RETRY_SECONDS = 36.
RETURN_MARGIN = 6.
QUALITY_SECONDS = 4.2

RETRY_TEXT = {
    "unreadable": "Label unreadable — adjusting viewpoint",
    "uncertain": "Occupancy uncertain — inspecting from another angle",
    "missing": "No accepted reading — correcting the camera viewpoint",
    "damage": "Damage detected — capturing additional evidence",
}


def reading_issue(event):
    if event is None:
        return "missing"
    if event["occupancy"] == "uncertain":
        return "uncertain"
    if event["label_status"] == "unreadable":
        return "unreadable"
    return None


def next_issue(event, quality, closeup_requested):
    issue = reading_issue(event)
    if issue:
        return issue
    if quality and quality["status"] == "DAMAGED" and not closeup_requested:
        return "damage"
    return None


def first_unused(views, issue, used):
    return next((pose for pose in views.get(issue, ()) if pose not in used), None)
