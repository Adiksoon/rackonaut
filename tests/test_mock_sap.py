import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, sleep
from unittest import TestCase
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator
import uvicorn

from backend.mock_api import CONTRACT
from backend.sap_api import create_sap_app

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jh7sAAAAASUVORK5CYII="


def observation(slot, hu, item, second, *, inspection="INS-TEST", state="occupied", label="readable"):
    return dict(schema_version="1.0", inspection_id=inspection, observation_id=f"OBS-{item}", slot_id=slot,
                pallet_id=hu, occupancy=state, label_status=label, timestamp=f"2026-11-25T12:00:{second:02}Z")


class SapApiTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "sap.sqlite3"
        self.start()
        self.addCleanup(self.stop)

    def start(self):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.endpoint = f"http://127.0.0.1:{self.listener.getsockname()[1]}"
        config = uvicorn.Config(create_sap_app(self.database), log_level="error", lifespan="off")
        self.server = uvicorn.Server(config)
        self.thread = Thread(target=self.server.run, kwargs={"sockets": [self.listener]}, daemon=True)
        self.thread.start()
        end = monotonic()+4
        while not self.server.started and monotonic() < end:
            sleep(.015)
        assert self.server.started

    def stop(self):
        self.server.should_exit = True
        self.thread.join(4)
        self.listener.close()

    def request(self, path, body=None):
        raw = json.dumps(body).encode() if body is not None else None
        q = Request(self.endpoint+path, data=raw, headers={"Content-Type": "application/json"})
        try:
            response = urlopen(q, timeout=4)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, response.read(), response.headers.get_content_type()

    def api(self, path, body=None):
        status, data, _ = self.request(path, body)
        return status, json.loads(data)

    def put(self, item):
        return self.api("/api/observations", item)

    def summary(self, key="summary", run="INS-TEST"):
        return self.api(f"/api/{key}?inspection_id={run}")[1]

    def test_rules_unknown_product_correlation_and_uninspected(self):
        for item in (
            observation("A-01-01","P001","AB",1),
            observation("A-01-02","P003","AC",2),
            observation("A-01-03",None,"AD",3,state="empty",label="not_applicable"),
            observation("A-01-04","P999","AE",4),
            observation("A-01-05",None,"AF",5,label="unreadable"),
            observation("A-01-06","P006","AG",6),
            observation("A-01-07",None,"AH",7,state="uncertain",label="unknown"),
            observation("B-01-02","P022","AI",8),
            observation("B-02-01",None,"AJ",9,state="empty",label="not_applicable"),
        ):
            self.assertEqual(self.put(item), (201,item))
        summary = self.summary()
        self.assertEqual(summary["outcomes"], {"match": 4,"wrong_pallet": 1,"missing_pallet": 1,
                         "unexpected_pallet": 1,"unreadable_label": 1,"uninspected": 2,"uncertain": 1,"pending": 0})
        validator = Draft202012Validator({"$ref": "#/components/schemas/Summary", "components": CONTRACT["components"]})
        validator.validate(summary)
        business = self.summary("business/summary")
        by_type = {row["type"]: row for row in business["issues"]}
        self.assertEqual(business["metrics"]["accuracy"], 4/7)
        self.assertEqual(by_type["DISCONTINUED_PRODUCT"]["hu_id"], "P001")
        self.assertEqual(by_type["BLOCKED_PRODUCT"]["hu_id"], "P006")
        self.assertEqual({i["hu_id"] for i in business["issues"] if i["type"]=="UNKNOWN_PRODUCT_STATUS"}, {"P022","P999"})
        pair = by_type["MISPLACED_PALLET"]
        self.assertEqual({e["slot_id"] for e in pair["evidence"]}, {"A-01-02","A-01-03"})
        self.assertEqual(set(pair["related_issue_ids"]), {by_type[key]["issue_id"] for key in ("WRONG_PALLET","MISSING_PALLET")})
        self.assertNotIn("A-01-08", {item["slot_id"] for item in business["issues"]})
        self.assertEqual(self.api("/openapi.json")[1], CONTRACT)
        self.assertEqual(self.api("/health")[1]["mode"], "mock_sap")

    def test_capture_history_idempotency_conflicts_and_persistence(self):
        latest = observation("A-01-01","P001","BC",12)
        initial = observation("A-01-01",None,"BA",7,label="unreadable")
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sorted(pool.map(lambda _: self.put(latest)[0], range(4))), [200,200,200,201])
        self.assertEqual(self.put({**latest,"pallet_id":"P008"})[0], 409)
        self.assertEqual(self.put(initial)[0], 201)
        self.assertEqual(self.put(observation("A-01-01",None,"BB",12,label="unreadable"))[0], 201)
        self.assertEqual(self.put({**latest,"inspection_id":"INS-OTHER"})[0], 201)
        self.assertEqual(self.summary()["outcomes"]["match"], 1)
        self.assertEqual(self.summary(run="INS-UNKNOWN")["outcomes"]["uninspected"], 11)
        self.assertEqual(self.summary("business/summary", run="INS-UNKNOWN")["issues"], [])
        self.stop()
        self.start()
        self.assertEqual([v["observation_id"] for v in self.summary("observations")], ["OBS-BA","OBS-BB","OBS-BC"])
        self.assertEqual(self.summary(run="INS-OTHER")["observations_total"],1)

    def test_quality_link_and_operator_verification_remain_independent(self):
        event = observation("A-01-01","P001","1",1)
        quality = "Q-"+"A"*32
        report = dict(quality_schema_version="0.1",quality_id=quality,inspection_id="INS-TEST",
                      observation_id=event["observation_id"],slot_id=event["slot_id"],pallet_id=event["pallet_id"],
                      observation_timestamp=event["timestamp"],timestamp="2026-11-25T12:00:02Z",
                      status="DAMAGED",reason="Camera-visible tear",
                      images={"original":"camera.png","annotated":"annotated.png"})
        body = {"report": report,"images":{"original":PNG,"annotated":PNG}}
        endpoint = "/api/business/quality"
        self.assertEqual(self.api(endpoint,body)[0],409)
        self.assertEqual(self.put(event)[0],201)
        self.assertEqual(self.api(endpoint,{**body,"report":{**report,"slot_id":"A-01-02"}})[0],422)
        self.assertEqual(self.api(endpoint,body)[0],201)
        self.assertEqual(self.api(endpoint,body)[0],200)
        self.assertEqual(self.api(endpoint,{**body,"report":{**report,"reason":"Altered fictional damage"}})[0],409)
        summary=self.summary("business/summary")
        issues={item["type"]:item for item in summary["issues"]}
        self.assertEqual(summary["metrics"]["matches"],1)
        self.assertEqual(set(issues),{"DAMAGED_PACKAGE","DISCONTINUED_PRODUCT"})
        image=issues["DAMAGED_PACKAGE"]["quality"][0]["photos"]["original"]
        self.assertEqual(self.request(image),(200,base64.b64decode(PNG),"image/png"))
        item=issues["DAMAGED_PACKAGE"]
        approval=f"/api/business/issues/{item['issue_id']}/verify"
        self.assertEqual(self.api(approval,{"inspection_id":"INS-TEST","revision":item["revision"]})[0],200)
        self.assertEqual(self.api(approval,{"inspection_id":"INS-OTHER","revision":item["revision"]})[0],404)
        self.stop()
        self.start()
        verified=next(i for i in self.summary("business/summary")["issues"] if i["issue_id"]==item["issue_id"])
        self.assertEqual(verified["status"],"VERIFIED")
        self.assertEqual(self.put({**event,"observation_id":"OBS-2","timestamp":"2026-11-25T12:00:03Z"})[0],201)
        self.assertEqual(self.api(approval,{"inspection_id":"INS-TEST","revision":item["revision"]})[0],409)
        opened=next(i for i in self.summary("business/summary")["issues"] if i["issue_id"]==item["issue_id"])
        self.assertEqual(opened["status"],"OPEN")
