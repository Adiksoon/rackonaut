"""Read accepted observations through the common HTTP contract."""

import json
from datetime import datetime, timezone
from http.client import HTTPException
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def fetch_observations(base_url, inspection_id):
    query = urlencode({"inspection_id": inspection_id})
    request = Request(f"{base_url}/api/observations?{query}", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=1.2) as response:
            events = json.load(response)
    except (URLError, OSError, HTTPException, ValueError) as error:
        return [], f"Observation API unavailable ({error})"
    if not isinstance(events, list):
        return [], "Observation API returned an unexpected body"
    return events, ""


def current_observation(events, inspection_id, slot_id, since, seen, now=None):
    now = now or datetime.now(timezone.utc)
    eligible = []
    for event in events:
        if not isinstance(event, dict) or (event.get("inspection_id"), event.get("slot_id")) != (
            inspection_id, slot_id
        ):
            continue
        event_id = event.get("observation_id")
        if not isinstance(event_id, str) or not event_id.startswith("OBS-") or event_id in seen:
            continue
        if event.get("occupancy") not in ("occupied", "empty", "uncertain"):
            continue
        try:
            stamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if stamp.tzinfo and since <= stamp <= now:
            eligible.append((stamp, event_id, event))
    return max(eligible, default=(None, None, None), key=lambda item: item[:2])[2]
