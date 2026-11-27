"""Rules for translating observed evidence into reviewable warehouse work."""

from collections import Counter, defaultdict
import hashlib
import json

from .mock_api import DISCREPANCIES

DECISIVE = {"match", "wrong_pallet", "missing_pallet", "unexpected_pallet"}
RULES = {
    "WRONG_PALLET": ("HIGH", "A different handling unit was read at this location.",
                     "Verify both labels and move the handling unit only after confirming its destination."),
    "MISSING_PALLET": ("HIGH", "The inspected location is empty and Mock SAP expects a handling unit.",
                       "Review the last warehouse movements and check the assigned handling unit."),
    "UNEXPECTED_PALLET": ("HIGH", "A handling unit was read at a location recorded as empty.",
                          "Verify the goods receipt and the handling unit's storage assignment."),
    "UNREADABLE_LABEL": ("MEDIUM", "The location is occupied and the label could not be read.",
                         "Verify the handling unit identity and replace or reprint the unreadable label."),
    "UNCERTAIN": ("MEDIUM", "The camera observation is inconclusive.",
                  "Schedule an adaptive rescan or inspect the location manually."),
    "DISCONTINUED_PRODUCT": ("HIGH", "The observed handling unit contains a discontinued product in Mock SAP.",
                             "Confirm the lifecycle record and follow the withdrawal or return procedure."),
    "BLOCKED_PRODUCT": ("HIGH", "The observed handling unit contains a blocked product in Mock SAP.",
                        "Keep the stock on hold and ask the inventory or quality owner to review the block."),
    "UNKNOWN_PRODUCT_STATUS": ("MEDIUM", "Mock SAP does not provide a verified lifecycle status for the observed handling unit.",
                               "Check the product master and handling-unit record before making a stock decision."),
    "DAMAGED_PACKAGE": ("HIGH", "A linked camera capture shows damage to the package.",
                        "Refer to quality control and assess repacking or isolation of the goods."),
    "MISPLACED_PALLET": ("HIGH", "The expected bay was observed empty and its handling unit was read in another bay.",
                         "Check both observations and warehouse movements before approving relocation."),
}


def digest(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:20].upper()


def photo_urls(inspection, quality_id):
    base = f"/api/business/quality/{inspection}/{quality_id}"
    return {kind: f"{base}/{kind}.png" for kind in ("original", "annotated")}


def build(store, products, db, inspection):
    history = store.history(inspection, db)
    slots = store.slots(history)
    by_slot = defaultdict(list)
    for event in history:
        by_slot[event["slot_id"]].append(event)
    latest = {slot: events[-1] for slot, events in by_slot.items()}
    photos = [{**item, "photos": photo_urls(inspection, item["quality_id"])} for item in store.quality(db, inspection)]
    by_evidence = defaultdict(list)
    for item in photos:
        by_evidence[item["slot_id"]].append(item)
    verified = {(issue, revision): on for issue, revision, on in db.execute(
        "SELECT issue, revision, verified_at FROM verification WHERE inspection=?", (inspection,))}
    issues = []

    def issue(kind, slot, hu, events, evidence=(), rationale=None, related=()):
        priority, description, action = RULES[kind]
        issue_id = "ISS-" + digest([inspection, kind, slot, hu])
        evidence_ids = [item["quality_id"] for item in evidence]
        revision = digest([[event["observation_id"] for event in events], evidence_ids, rationale, related])
        acknowledged = verified.get((issue_id, revision))
        entry = {"issue_id": issue_id, "revision": revision, "type": kind, "priority": priority,
                 "slot_id": slot, "hu_id": hu, "description": description, "action": action,
                 "reason": rationale or description, "evidence": events, "quality": list(evidence),
                 "related_issue_ids": list(related), "status": "VERIFIED" if acknowledged else "OPEN",
                 "verified_at": acknowledged}
        issues.append(entry)
        return issue_id

    inventory_issues, found, missing = {}, defaultdict(list), {}
    assessed = damaged = 0
    discontinued = set()
    manual = set()
    for row in slots:
        slot = row["slot_id"]
        event = latest.get(slot)
        expected = row["expected_pallet_id"]
        outcome = row["outcome"]
        row.update(expected_product=products.get(expected), observed_product=None,
                   readings=by_slot[slot], quality_history=by_evidence[slot], active_quality=None)
        if event is None:
            continue
        hu = event["pallet_id"]
        assessed += outcome in DECISIVE
        if outcome in DISCREPANCIES:
            relevant = hu or (expected if outcome == "missing_pallet" else None)
            reason = None
            if outcome == "wrong_pallet" and (placement := (products.get(hu) or {}).get("expected_slot")):
                reason = f"Mock SAP assigns the observed handling unit {hu} to {placement}."
            inventory_issues[slot] = issue(outcome.upper(), slot, relevant, [event], rationale=reason)
        if outcome in {"unreadable_label", "uncertain"}:
            manual.add(slot)
        if outcome == "missing_pallet":
            missing[expected] = slot
        if hu:
            found[hu].append(slot)
            product = products.get(hu)
            row["observed_product"] = product or {"hu_id": hu, "lifecycle_status": "UNKNOWN"}
            lifecycle = row["observed_product"]["lifecycle_status"]
            if lifecycle != "ACTIVE":
                kind = {"DISCONTINUED": "DISCONTINUED_PRODUCT", "BLOCKED": "BLOCKED_PRODUCT",
                        "UNKNOWN": "UNKNOWN_PRODUCT_STATUS"}[lifecycle]
                issue(kind, slot, hu, [event], rationale=(
                    f"Read {hu}. Product {product['sku']} has lifecycle {lifecycle} in Mock SAP."
                    if product else f"The readable handling unit {hu} has no product master record in this dataset."))
                if lifecycle == "DISCONTINUED":
                    discontinued.add(hu)
                if lifecycle == "UNKNOWN":
                    manual.add(slot)
        if event["occupancy"] == "occupied":
            relevant = [item for item in by_evidence[slot] if item["status"] != "CAPTURED"
                        and (item["observation_id"] == event["observation_id"]
                             or (hu is not None and item["pallet_id"] == hu))]
            if relevant:
                quality = relevant[-1]
                row["active_quality"] = quality
                if quality["status"] == "DAMAGED":
                    damaged += 1
                    issue("DAMAGED_PACKAGE", slot, hu, [event], [quality], rationale=quality["reason"])

    for hu, expected_slot in missing.items():
        locations = found[hu]
        if len(locations) != 1 or locations[0] == expected_slot:
            continue
        actual_slot = locations[0]
        linked = [inventory_issues[slot] for slot in (expected_slot, actual_slot)]
        issue("MISPLACED_PALLET", actual_slot, hu, [latest[expected_slot], latest[actual_slot]],
              rationale=f"{expected_slot} was observed empty. The label {hu} was read at {actual_slot}.",
              related=linked)
    counts = Counter(row["outcome"] for row in slots)
    issues.sort(key=lambda item: (item["priority"] != "HIGH", item["slot_id"], item["type"]))
    return {"inspection_id": inspection, "source": "mock_sap", "synthetic_product_master": True,
            "metrics": {"observed": len(latest), "total": len(slots), "matches": counts["match"],
                        "decisive": assessed, "accuracy": counts["match"]/assessed if assessed else None,
                        "inventory_discrepancies": sum(counts[k] for k in DECISIVE - {"match"}),
                        "inventory_attention": sum(counts[k] for k in DISCREPANCIES),
                        "damaged_packages": damaged, "discontinued_products": len(discontinued),
                        "manual_review_locations": len(manual)},
            "issues": issues, "slots": slots}
