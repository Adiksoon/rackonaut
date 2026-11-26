"""Persist accepted observations, linked photos and issue acknowledgements."""

import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from .mock_api import InventoryStore, capture_time, error, event_key


def comparison(expected, observation):
    if observation["occupancy"] == "uncertain":
        return "uncertain"
    if observation["occupancy"] == "empty":
        return "missing_pallet" if expected else "match"
    if observation["label_status"] != "readable":
        return "unreadable_label"
    if expected is None:
        return "unexpected_pallet"
    return "match" if expected == observation["pallet_id"] else "wrong_pallet"


class SapStore(InventoryStore):
    def __init__(self, inventory, database):
        super().__init__(inventory)
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS observations (
                    inspection TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (inspection, id)
                );
                CREATE TABLE IF NOT EXISTS quality (
                    inspection TEXT NOT NULL, id TEXT NOT NULL, observation TEXT NOT NULL,
                    report TEXT NOT NULL, original BLOB NOT NULL, annotated BLOB NOT NULL,
                    PRIMARY KEY(inspection, id),
                    FOREIGN KEY(inspection, observation) REFERENCES observations(inspection, id)
                );
                CREATE TABLE IF NOT EXISTS verification (
                    inspection TEXT NOT NULL, issue TEXT NOT NULL, revision TEXT NOT NULL, verified_at TEXT NOT NULL,
                    PRIMARY KEY (inspection, issue, revision)
                );
            """)

    @contextmanager
    def connect(self, write=False):
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db

    def record(self, observation):
        key = event_key(observation)
        with self.connect(write=True) as db:
            row = db.execute("SELECT payload FROM observations WHERE inspection=? AND id=?", key).fetchone()
            if row:
                if json.loads(row[0]) != observation:
                    raise error(409, "observation_conflict", "This inspection already has this observation_id.")
                return 200
            if observation["slot_id"] not in self.expected:
                raise error(404, "unknown_slot", "slot_id does not exist in the expected inventory.")
            db.execute("INSERT INTO observations VALUES (?,?,?)", (*key, json.dumps(observation)))
            return 201

    def history(self, inspection_id, db=None):
        if db is None:
            with self.connect() as connection:
                return self.history(inspection_id, connection)
        rows = db.execute("SELECT payload FROM observations WHERE inspection=?", (inspection_id,))
        return sorted((json.loads(row[0]) for row in rows), key=lambda event: (capture_time(event), event["observation_id"]))

    def outcome(self, expected, event):
        return comparison(expected, event)

    def record_quality(self, report, original, annotated):
        key = report["inspection_id"], report["quality_id"]
        with self.connect(write=True) as db:
            previous = db.execute("SELECT report, original, annotated FROM quality WHERE inspection=? AND id=?", key).fetchone()
            if previous:
                if (json.loads(previous[0]), *previous[1:]) != (report, original, annotated):
                    raise error(409, "quality_conflict", "This inspection already has this quality_id.")
                return 200
            row = db.execute("SELECT payload FROM observations WHERE inspection=? AND id=?",
                             (key[0], report["observation_id"])).fetchone()
            if not row:
                raise error(409, "unlinked_quality", "Submit the linked inventory observation first.")
            event = json.loads(row[0])
            if (event["slot_id"], event["pallet_id"], capture_time(event), event["occupancy"]) != (
                    report["slot_id"], report["pallet_id"], capture_time({"timestamp": report["observation_timestamp"]}),
                    "occupied"):
                raise error(422, "quality_link_mismatch", "Quality evidence differs from the referenced observation.")
            db.execute("INSERT INTO quality VALUES (?,?,?,?,?,?)",
                       (*key, report["observation_id"], json.dumps(report), original, annotated))
            return 201

    def quality(self, db, inspection_id):
        rows = db.execute("SELECT report FROM quality WHERE inspection=?", (inspection_id,))
        return sorted((json.loads(row[0]) for row in rows), key=lambda item: (capture_time(item), item["quality_id"]))

    def photo(self, inspection, quality, kind):
        with self.connect() as db:
            row = db.execute("SELECT original, annotated FROM quality WHERE inspection=? AND id=?", (inspection, quality)).fetchone()
        if not row:
            raise error(404, "unknown_quality", "No evidence for this inspection and quality ID.")
        return row[0 if kind == "original" else 1]
