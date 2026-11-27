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
from urllib.request import Request, urlopen

from ament_index_python.packages import get_package_share_path


CALIBRATION_INTERRUPTED = "INTERRUPTED_FOR_CALIBRATION"
TERMINAL = {"COMPLETE", "COMPLETE_WITH_MISSES", "ABORTED", CALIBRATION_INTERRUPTED}
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
                or report["quality_schema_version"] != "0.1" or report["status"] not in ("OK", "DAMAGED", "CAPTURED")
                or report["images"] != IMAGE_NAMES):
            raise ValueError(f"Malformed or cross-inspection evidence in {bundle.name}.")
        event = observations.get(report["observation_id"])
        reference_time = utc(report["observation_timestamp"])
        delay = (utc(report["timestamp"]) - reference_time).total_seconds()
        capture = report["status"] == "CAPTURED"
        occupancy = report.get("occupancy") if capture else "occupied"
        if capture and (delay != 0 or occupancy not in {"occupied", "empty", "uncertain"}):
            raise ValueError(f"Invalid observation capture in {quality_id}.")
        if delay < 0 or (event is not None and (
            (event["slot_id"], event["pallet_id"], event["occupancy"], utc(event["timestamp"]))
            != (report["slot_id"], report["pallet_id"], occupancy, reference_time)
        )):
            raise ValueError(f"Evidence {quality_id} disagrees with its inventory observation.")
        images = {key: (bundle / name).read_bytes() for key, name in IMAGE_NAMES.items()}
        if any(not data.startswith(b"\x89PNG\r\n\x1a\n") for data in images.values()):
            raise ValueError(f"Invalid evidence image in {quality_id}.")
        bundles[quality_id] = (report, images, delay, event is not None)
    return sorted(bundles.values(), key=lambda bundle: (bundle[0]["slot_id"], bundle[0]["timestamp"]))


def fetch_business(base_url, inspection_id, evidence):
    if evidence:
        endpoint = f"{base_url.rstrip('/')}/api/business/quality"
        for report, photos, _, linked in evidence:
            if not linked:
                continue
            bundle = {"report": report, "images": {key: b64encode(data).decode("ascii") for key, data in photos.items()}}
            request = Request(endpoint, json.dumps(bundle).encode(), {"Content-Type": "application/json"})
            with urlopen(request, timeout=12):
                pass
    query = urlencode({"inspection_id": inspection_id})
    with urlopen(f"{base_url.rstrip('/')}/api/business/summary?{query}", timeout=6) as response:
        return json.load(response)


def e(value):
    return escape(str(value), quote=True)


def image_url(data):
    return "data:image/png;base64," + b64encode(data).decode("ascii")


def evidence_card(bundle):
    report, images, delay, linked = bundle
    damaged = report["status"] == "DAMAGED"
    capture = report["status"] == "CAPTURED"
    slot = e(report["slot_id"])
    pallet = e(report["pallet_id"] or {"empty": "Empty location", "uncertain": "Uncertain occupancy"}
               .get(report.get("occupancy"), "Unreadable pallet label"))
    quality = "damage" if damaged else "ok"
    link_state = "Matched to API history" if linked else "Local evidence · awaiting inventory link"
    return f"""
      <article class="evidence {quality}" id="{e(report['quality_id'])}">
        <div class="evidence-title"><div><span class="eyebrow">LOCATION {slot}</span>
          <h3>{pallet}</h3></div><span class="badge">{e(report['status'])}</span></div>
        <img class="photo" src="{image_url(images['original' if capture else 'annotated'])}" alt="Camera image at {slot}">
        <div class="evidence-copy"><strong>{e(report['reason'])}</strong>
          <dl>
            <div><dt>Inventory observation (UTC)</dt><dd>{e(report['observation_timestamp'])}</dd></div>
            <div><dt>Evidence photo (UTC)</dt><dd>{e(report['timestamp'])}</dd></div>
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
    planned = mission.get("planned_slots")
    for location in summary["slots"]:
        slot = location["slot_id"]
        observation = observations.get(location["observation_id"], {})
        confirmed = "Confirmed" if slot in mission["confirmed"] else "—"
        outcome = location["outcome"]
        comparison = "Pending comparison" if outcome == "pending" else outcome.replace("_", " ").capitalize()
        if planned is not None:
            if slot not in planned:
                confirmed = "Outside scope"
            elif slot in mission["missed"]:
                confirmed = "Missed"
            elif slot not in mission["confirmed"]:
                confirmed = "Unconfirmed"
            if slot in mission.get("adaptive", {}).get("manual_review", {}):
                confirmed = "Manual verification"
        label = observation.get("label_status", "uninspected").replace("_", " ").capitalize()
        occupancy = observation.get("occupancy", "uninspected").capitalize()
        rows.append(f"<tr><th scope='row'>{e(slot)}</th><td>{e(location['observed_pallet_id'] or '—')}</td>"
                    f"<td>{e(occupancy)}</td><td>{e(label)}</td><td>{confirmed}</td>"
                    f"<td><span class='outcome {e(outcome)}'>{e(comparison)}</span></td></tr>")
    return "".join(rows)


def adaptive_history(mission):
    adaptive = mission.get("adaptive")
    if adaptive is None:
        return ""
    rows = []
    for attempt in adaptive["attempts"]:
        reading = " / ".join(value for value in (attempt["reading"] or []) if value)
        rows.append("<tr>" + "".join(f"<td>{e(value)}</td>" for value in (
            attempt["slot_id"], attempt["attempt"], attempt["reason"].capitalize(), reading or "—",
            attempt["outcome"], attempt["observation_id"] or "—", attempt["quality_id"] or "—",
        )) + "</tr>")
    manual = ", ".join(adaptive["manual_review"]) or "None"
    return f"""
  <section aria-labelledby="adaptive-title">
    <h2 id="adaptive-title">Adaptive inspection</h2>
    <p>{len(mission["visited"])} locations · {adaptive["retries"]} additional attempts ·
       {len(adaptive["resolved"])} resolved · {len(adaptive["manual_review"])} manual checks</p>
    <p>Manual verification · {e(manual)}</p>
    <div class="table-wrap"><table aria-label="All adaptive inspection attempts">
      <thead><tr><th>Location</th><th>Attempt</th><th>Viewpoint</th><th>Reading</th>
        <th>Outcome</th><th>Observation ID</th><th>Quality ID</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table></div>
  </section>"""


def energy_history(mission):
    energy = mission.get("energy")
    if energy is None:
        return ""

    def percent(value):
        return f"{value:.1f}%" if value is not None else "—"

    rows = []
    for flight in energy["sorties"]:
        done = [slot for slot in flight.get("completed_after", []) if slot not in flight["completed_before"]]
        rows.append("<tr>" + "".join(f"<td>{e(value)}</td>" for value in (
            flight["departure"], percent(flight["start_percent"]), percent(flight.get("end_percent")),
            percent(flight.get("charged_percent")), flight.get("result", "—").replace("_", " ").title(),
            ", ".join(done) or "—",
        )) + "</tr>")
    interrupted = ", ".join(item["slot"] for item in energy["interrupted"]) or "None"
    return f"""
  <section aria-labelledby="energy-title">
    <h2 id="energy-title">Simulated energy and dock visits</h2>
    <p>{energy["departures"]} sorties under this inspection ID · {len(energy["remaining"])} unfinished locations</p>
    <p>Interrupted observations · {e(interrupted)}</p>
    <div class="table-wrap"><table aria-label="Flights and dock charging">
      <thead><tr><th>Departure</th><th>Start battery</th><th>End battery</th><th>After charging</th>
        <th>Outcome</th><th>Locations finished on this flight</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table></div>
  </section>"""


def business_report(snapshot, evidence):
    business = snapshot.get("business")
    if not business:
        return ""
    metrics = business["metrics"]
    accuracy = (f"{100*metrics['accuracy']:.1f}% ({metrics['matches']}/{metrics['decisive']} conclusive)"
                if metrics["accuracy"] is not None else "No conclusive locations")
    photos = {report["quality_id"]: report for report, _, _, linked in evidence if linked}
    issues = {item["issue_id"]: item for item in business["issues"]}
    rows = []
    for item in issues.values():
        observations = ", ".join(f"{event['slot_id']} · {event['observation_id']}" for event in item["evidence"])
        related = " / ".join(f"{issues[key]['type'].replace('_', ' ')} at {issues[key]['slot_id']}"
                             for key in item["related_issue_ids"])
        proof = [quality["quality_id"] for quality in item["quality"] if quality["quality_id"] in photos]
        events = {event["observation_id"] for event in item["evidence"] if event["slot_id"] == item["slot_id"]}
        proof = proof or [key for key, photo in photos.items() if photo["observation_id"] in events]
        links = " ".join(f'<a href="#{e(key)}">Camera evidence</a>' for key in proof)
        rows.append(f"""<tr><td>{e(item['priority'])}<br>{e(item['type'].replace('_',' '))}<br>
          <code>{e(item['issue_id'])}</code></td><td>{e(item['slot_id'])}<br>{e(item['hu_id'] or '—')}</td>
          <td>{e(item['reason'])}<br><strong>{e(item['action'])}</strong></td>
          <td>{e(observations)}<br>{e(related)} {links}</td><td>{e(item['status'])}</td></tr>""")
    return f"""<section aria-label="Warehouse Intelligence" class="business">
      <div class="section-head"><h2>Warehouse Intelligence</h2><p class="subtitle">Mock SAP comparison · synthetic product data</p></div>
      <p><strong>{e(accuracy)}</strong> inventory accuracy · {metrics['observed']}/{metrics['total']} locations observed ·
        {metrics['inventory_discrepancies']} stock discrepancies · {metrics['damaged_packages']} damaged packages ·
        {metrics['discontinued_products']} discontinued products · {metrics['manual_review_locations']} locations for manual review</p>
      <p class="subtitle">Recommendations require an operator decision. Verification records a review of the evidence.</p>
      <div class="table-wrap"><table aria-label="Recommended warehouse actions"><thead><tr><th>Issue</th><th>Location / HU</th>
        <th>Evidence and recommendation</th><th>Observations and related issues</th><th>Review</th></tr></thead>
        <tbody>{"".join(rows) or '<tr><td colspan="5">No issues from the inspected locations</td></tr>'}</tbody></table></div>
      </section>"""


def render(snapshot, evidence, observations):
    mission, api = snapshot["mission"], snapshot["api"]
    summary = api["summary"]
    pending = summary["outcomes"]["pending"]
    fixture = api["health"].get("mode") == "fixture"
    damage = {(report["slot_id"], report["pallet_id"])
              for report, _, _, _ in evidence if report["status"] == "DAMAGED"}
    cards = "".join(evidence_card(bundle) for bundle in evidence)
    photographed = {report["observation_id"] for report, _, _, linked in evidence if linked}
    missing = [event for key, event in observations.items() if key not in photographed]
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
        api_source="Mock API fixture" if fixture else "Mock SAP" if api["health"].get("mode") == "mock_sap" else "Warehouse API",
        business=business_report(snapshot, evidence),
        comparison=f"{pending} pending" if fixture
        else f"{int(summary['discrepancy_count'])} reported discrepancies · {pending} pending",
        events=len(observations),
        distinct=int(summary["slots_observed"]),
        rows=inventory_rows(mission, summary, observations),
        adaptive_history=adaptive_history(mission),
        energy_history=energy_history(mission),
        cards=cards or '<p class="empty">No camera evidence was archived for this inspection.</p>',
        missing_evidence=('<p class="subtitle">No camera evidence saved for these observations:</p><ul>'
                          + "".join(f"<li>{e(event['slot_id'])} · {e(event['observation_id'])}</li>" for event in missing)
                          + "</ul>") if missing else "",
    )


def export(snapshot, directory, output_dir, *, backend=None):
    mission = snapshot["mission"]
    inspection_id = finished_id(mission)
    observations = check_api(mission, snapshot["api"])
    evidence = collect_evidence(directory, inspection_id, observations)
    if backend and snapshot["api"]["health"].get("mode") == "mock_sap":
        snapshot["business"] = fetch_business(backend, inspection_id, evidence)
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
        backend = None if args.snapshot else args.backend_url or "http://127.0.0.1:8000"
        print(export(snapshot, directory, args.output_dir.expanduser(), backend=backend))
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"Report export failed: {error}\n")
