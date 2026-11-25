"""Export a finished mission and its linked photos as portable HTML."""

import argparse
import json
import os
import re
from base64 import b64encode
from datetime import datetime
from html import escape
from pathlib import Path
from string import Template
from tempfile import TemporaryDirectory
from time import monotonic
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

from ament_index_python.packages import get_package_share_path


TERMINAL = {"COMPLETE", "COMPLETE_WITH_MISSES", "ABORTED"}
IMAGE_NAMES = {"original": "camera.png", "annotated": "annotated.png"}


def live_mission():
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from std_msgs.msg import String

    rclpy.init()
    node = Node("rackonaut_report_export")
    messages = []
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    node.create_subscription(String, "/rackonaut/mission/status", messages.append, qos)
    try:
        deadline = monotonic() + 5
        while not messages and monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.2)
        if not messages:
            raise ValueError("No mission status received. Check the ROS domain and the showcase launch.")
        return json.loads(messages[-1].data)
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def finished_id(mission):
    inspection_id = mission["inspection_id"]
    if not re.fullmatch(r"INS-[A-Z0-9]+(?:-[A-Z0-9]+)*", inspection_id) or len(inspection_id) > 64:
        raise ValueError("The mission has an invalid inspection ID.")
    if mission["stage"] not in TERMINAL:
        raise ValueError(f"{inspection_id} is still at {mission['stage']}. Export after the mission finishes.")
    return inspection_id


def fetch_api(base_url, inspection_id):
    url = urlsplit(base_url)
    if url.scheme not in ("http", "https") or not url.hostname or url.query or url.fragment:
        raise ValueError("--backend-url must be an HTTP(S) base URL.")
    query = urlencode({"inspection_id": inspection_id})
    paths = {"health": "/health"}
    paths.update({name: f"/api/{name}?{query}" for name in ("observations", "summary", "discrepancies")})
    results = {}
    for name, path in paths.items():
        with urlopen(f"{base_url.rstrip('/')}{path}", timeout=4) as response:
            results[name] = json.load(response)
    return results


def check_api(mission, api):
    inspection_id = finished_id(mission)
    observations = api["observations"]
    by_id = {event["observation_id"]: event for event in observations}
    if len(by_id) != len(observations) or any(event["inspection_id"] != inspection_id for event in observations):
        raise ValueError("The API returned duplicate events or observations from another inspection.")
    for slot, event in mission["confirmed"].items():
        if event["slot_id"] != slot or by_id.get(event["observation_id"]) != event:
            raise ValueError(f"The API history does not match the mission confirmation for {slot}.")
    summary = api["summary"]
    if (summary["inspection_id"] != inspection_id or summary["observations_total"] != len(observations)
            or summary["slots_observed"] != len({event["slot_id"] for event in observations})):
        raise ValueError("The API history and summary disagree. Retry once the backend has settled.")
    return by_id


def utc(when):
    result = datetime.fromisoformat(when.replace("Z", "+00:00"))
    if result.utcoffset() is None or result.utcoffset().total_seconds():
        raise ValueError("Evidence timestamps must be UTC.")
    return result


def collect_evidence(directory, inspection_id, observations):
    bundles = {}
    for bundle in sorted(directory.glob("Q-*")):
        report = json.loads((bundle / "report.json").read_text(encoding="utf-8"))
        quality_id = report["quality_id"]
        if (report["inspection_id"] != inspection_id or quality_id != bundle.name or quality_id in bundles
                or report["quality_schema_version"] != "0.1" or report["status"] not in ("OK", "DAMAGED")
                or report["images"] != IMAGE_NAMES):
            raise ValueError(f"Malformed or cross-inspection evidence in {bundle.name}.")
        event = observations.get(report["observation_id"])
        reference_time = utc(report["observation_timestamp"])
        delay = (utc(report["timestamp"]) - reference_time).total_seconds()
        if delay < 0 or (event is not None and (
            (event["slot_id"], event["pallet_id"], event["occupancy"], utc(event["timestamp"]))
            != (report["slot_id"], report["pallet_id"], "occupied", reference_time)
        )):
            raise ValueError(f"Evidence {quality_id} disagrees with its inventory observation.")
        images = {key: (bundle / name).read_bytes() for key, name in IMAGE_NAMES.items()}
        if any(not data.startswith(b"\x89PNG\r\n\x1a\n") for data in images.values()):
            raise ValueError(f"Invalid evidence image in {quality_id}.")
        bundles[quality_id] = (report, images, delay, event is not None)
    return sorted(bundles.values(), key=lambda bundle: (bundle[0]["slot_id"], bundle[0]["timestamp"]))


def e(value):
    return escape(str(value), quote=True)


def image_url(data):
    return "data:image/png;base64," + b64encode(data).decode("ascii")


def evidence_card(bundle):
    report, images, delay, linked = bundle
    damaged = report["status"] == "DAMAGED"
    slot = e(report["slot_id"])
    pallet = e(report["pallet_id"] or "Unreadable pallet label")
    quality = "damage" if damaged else "ok"
    link_state = "Matched to API history" if linked else "Local evidence · awaiting inventory link"
    return f"""
      <article class="evidence {quality}">
        <div class="evidence-title"><div><span class="eyebrow">LOCATION {slot}</span>
          <h3>{pallet}</h3></div><span class="badge">{e(report['status'])}</span></div>
        <img class="photo" src="{image_url(images['annotated'])}" alt="Annotated carton image at {slot}">
        <div class="evidence-copy"><strong>{e(report['reason'])}</strong>
          <dl>
            <div><dt>Inventory observation (UTC)</dt><dd>{e(report['observation_timestamp'])}</dd></div>
            <div><dt>Quality photo (UTC)</dt><dd>{e(report['timestamp'])}</dd></div>
          </dl>
          <p class="link-state">{e(link_state)} · {delay:.3f} s between timestamps</p>
          <code>{e(report['observation_id'])}</code>
          <code>{e(report['quality_id'])}</code>
          <details><summary>Open original camera image</summary>
            <img class="original" src="{image_url(images['original'])}" alt="Original camera frame at {slot}">
          </details>
        </div>
      </article>"""


def inventory_rows(mission, summary, observations):
    rows = []
    for location in summary["slots"]:
        slot = location["slot_id"]
        observation = observations.get(location["observation_id"], {})
        confirmed = "Confirmed" if slot in mission["confirmed"] else "—"
        outcome = location["outcome"]
        comparison = "Pending comparison" if outcome == "pending" else outcome.replace("_", " ").capitalize()
        label = observation.get("label_status", "uninspected").replace("_", " ").capitalize()
        occupancy = observation.get("occupancy", "uninspected").capitalize()
        rows.append(f"<tr><th scope='row'>{e(slot)}</th><td>{e(location['observed_pallet_id'] or '—')}</td>"
                    f"<td>{e(occupancy)}</td><td>{e(label)}</td><td>{confirmed}</td>"
                    f"<td><span class='outcome {e(outcome)}'>{e(comparison)}</span></td></tr>")
    return "".join(rows)


def render(snapshot, evidence, observations):
    mission, api = snapshot["mission"], snapshot["api"]
    summary = api["summary"]
    pending = summary["outcomes"]["pending"]
    fixture = api["health"].get("mode") == "fixture"
    damage = {(report["slot_id"], report["pallet_id"])
              for report, _, _, _ in evidence if report["status"] == "DAMAGED"}
    cards = "".join(evidence_card(bundle) for bundle in evidence)
    template = get_package_share_path("rackonaut_mission") / "templates/inspection.html"
    return Template(template.read_text(encoding="utf-8")).substitute(
        inspection_id=e(mission["inspection_id"]),
        status=e(mission["stage"].replace("_", " ").title()),
        detail=e(mission["detail"]),
        landed="Touchdown confirmed" if mission["landed"] else "Touchdown unconfirmed",
        duration=f"{float(mission['elapsed_seconds']):.1f}",
        planned=int(mission["total"]),
        confirmed=len(mission["confirmed"]),
        damaged=len(damage),
        linked=sum(linked for _, _, _, linked in evidence),
        saved=len(evidence),
        api_source="Mock API" if fixture else "Warehouse API",
        comparison=f"{pending} pending" if fixture
        else f"{int(summary['discrepancy_count'])} reported discrepancies · {pending} pending",
        events=len(observations),
        distinct=int(summary["slots_observed"]),
        rows=inventory_rows(mission, summary, observations),
        cards=cards or '<p class="empty">No stable carton captures were archived for this inspection.</p>',
    )


def export(snapshot, directory, output_dir):
    mission = snapshot["mission"]
    inspection_id = finished_id(mission)
    observations = check_api(mission, snapshot["api"])
    evidence = collect_evidence(directory, inspection_id, observations)
    html = render(snapshot, evidence, observations)
    destination = output_dir / inspection_id
    output_dir.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"{destination} already exists. Choose another --output-dir for a second export.")
    with TemporaryDirectory(dir=output_dir, prefix=".report-") as staging:
        draft = Path(staging)
        (draft / "index.html").write_text(html, encoding="utf-8")
        (draft / "run.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        for report, photos, _, _ in evidence:
            bundle = draft / "quality" / report["quality_id"]
            bundle.mkdir(parents=True)
            (bundle / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            for kind, name in IMAGE_NAMES.items():
                (bundle / name).write_bytes(photos[kind])
        draft.rename(destination)
    return destination / "index.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    log_dir = Path(os.environ.get("ROS_LOG_DIR", Path.home() / ".ros" / "log"))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--backend-url", help="Live backend base URL, default http://127.0.0.1:8000")
    source.add_argument("--snapshot", type=Path, help="Previously exported run.json for offline regeneration")
    parser.add_argument("--quality-dir", type=Path, help="Parent of the per-inspection Quality Evidence directories")
    parser.add_argument("--output-dir", type=Path, default=log_dir / "reports", help="Parent directory for reports")
    args = parser.parse_args()
    try:
        if args.snapshot:
            snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        else:
            mission = live_mission()
            snapshot = {"mission": mission, "api": fetch_api(args.backend_url or "http://127.0.0.1:8000",
                                                             finished_id(mission))}
        run = finished_id(snapshot["mission"])
        if args.quality_dir:
            directory = args.quality_dir.expanduser() / run
        else:
            directory = args.snapshot.parent / "quality" if args.snapshot else log_dir / "quality" / run
        print(export(snapshot, directory, args.output_dir.expanduser()))
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"Report export failed: {error}\n")
