"""Serve the packaged browser UI and mission-specific actions over loopback."""

import json
import re
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from rackonaut_localization.node import SLAM_MAP

from .measured_map import DETAIL, FRAME, MAP_TOPIC, VOXEL_METRES
from .route_review import ROUTE_FILES
from rackonaut_localization.learned_map import MAP_FILE
from .service import COOKIE
from .teaching import CAPTURE_ID, SESSION_ID, session_path

STATIC = {"/": ("index.html", "text/html"), "/style.css": ("style.css", "text/css"),
          "/twin.css": ("twin.css", "text/css"),
          **{f"/{name}": (name, "text/javascript") for name in (
              "app.js", "business.js", "service.js", "manual.js", "teaching.js", "route.js", "twin.js", "rack-templates.js", "twin-scene.js", "scan.js", "vendor/three.module.min.js",
              "vendor/three.core.min.js", "vendor/OrbitControls.js")},
          "/vendor/three-LICENSE.txt": ("vendor/three-LICENSE.txt", "text/plain")}
RUN = r"INS-[A-Z0-9-]{1,60}"
REPORT = re.compile(fr"/reports/({RUN})$")
RECOVERY = re.compile(r"/recoveries/(REC-[A-F0-9]{12}\.json)$")
BUSINESS_PHOTO = re.compile(fr"/api/business/quality/{RUN}/Q-[A-F0-9]{{32}}/(?:original|annotated)\.png$")
BUSINESS_VERIFY = re.compile(r"/api/business/issues/ISS-[A-F0-9]{20}/verify$")
PHOTO = re.compile(fr"/evidence/({RUN})/(Q-[A-Z0-9]{{32}})/(camera|annotated)\.png$")
MAPPING_RESULT = re.compile(fr"/api/service/mapping/({SESSION_ID})/([a-z.-]+)$")
TEACHING_PHOTO = re.compile(fr"/api/service/mapping/({SESSION_ID})/locations/({CAPTURE_ID})/reference\.jpg$")
TEACHING_PREVIEW = re.compile(fr"/api/service/teaching/preview/({CAPTURE_ID})/reference\.jpg$")
TEACHING_ACTION = re.compile(r"/api/service/teaching/(capture|save|rename|delete)$")
ROUTE_STATE = re.compile(fr"/api/service/route/({SESSION_ID})$")
ROUTE_ACTION = re.compile(r"/api/service/route/(review|validate|approve|plan)$")
WAREHOUSE_ACTION = re.compile(r"/api/service/warehouses/(seal|verify|activate)$")
VISUALIZATION_RUN = re.compile(fr"/api/visualization/run/({RUN})$")
VISUALIZATION_SERVICE = re.compile(fr"/api/service/visualization/(warehouse|calibration)/(WH-[A-F0-9]{{32}}|{SESSION_ID})$")


def serve(control, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, data, media_type, headers=None):
            self.send_response(code)
            self.send_header("Content-Type", media_type)
            if code not in {204, 304}:
                self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def json(self, code, payload, headers=None):
            self.reply(code, json.dumps(payload, separators=(",", ":")).encode(), "application/json", headers)

        def visualization(self, artifact):
            if artifact is None:
                self.json(202, {"status": "preparing"}, {"Retry-After": "2"})
                return
            body, etag = artifact
            unchanged = self.headers.get("If-None-Match") == etag
            self.reply(304 if unchanged else 200, b"" if unchanged else body, "application/json", {"ETag": etag})

        def local_request(self):
            host = self.headers.get("Host")
            origin = self.headers.get("Origin")
            return host in {f"localhost:{port}", f"127.0.0.1:{port}"} and (not origin or origin == f"http://{host}")

        def service_token(self):
            try:
                cookie = SimpleCookie(self.headers.get("Cookie", "")).get(COOKIE)
            except CookieError:
                return None
            return cookie.value if cookie else None

        def service_cookie(self, value, max_age):
            cookie = SimpleCookie({COOKIE: value})
            cookie[COOKIE]["path"] = "/api/service"
            cookie[COOKIE]["httponly"] = True
            cookie[COOKIE]["samesite"] = "Strict"
            cookie[COOKIE]["max-age"] = str(max_age)
            return {"Set-Cookie": cookie[COOKIE].OutputString()}

        def require_service(self):
            if control.service_access.authorized(self.service_token()):
                return True
            self.json(401, {"error": "Unlock Service to continue.",
                            "configured": control.service_access.code_digest is not None})
            return False

        def service_action(self, path, selection):
            access = control.service_access
            if path == "/api/service/unlock":
                status, token, error = access.unlock(selection.get("code"))
                if token:
                    access.revoke(self.service_token())
                    self.json(200, {"unlocked": True}, self.service_cookie(token, access.ttl))
                else:
                    self.json(status, {"error": error}, {"Retry-After": "60"} if status == 429 else None)
            elif path == "/api/service/lock":
                access.revoke(self.service_token())
                self.json(200, {"unlocked": False}, self.service_cookie("", 0))
            elif path == "/api/service/calibration/start":
                self.json(200, control.start_calibration(selection))
            elif path == "/api/service/calibration/cancel":
                self.json(200, control.cancel_calibration(selection))
            elif path == "/api/service/mapping/start":
                self.json(200, control.start_manual(selection, mapping=True))
            elif match := TEACHING_ACTION.fullmatch(path):
                self.json(200, control.teach_location(match[1], selection, self.service_token()))
            elif match := ROUTE_ACTION.fullmatch(path):
                self.json(200, control.review_route(match[1], selection, self.service_token()))
            elif match := WAREHOUSE_ACTION.fullmatch(path):
                self.json(200, control.warehouse_action(match[1], selection, self.service_token()))
            else:
                self.json(404, {"error": "Not found"})

        def service_read(self, path):
            if not self.local_request():
                self.json(403, {"error": "Open the local Control Center URL to access Service."})
            elif self.require_service():
                if path == "/api/service/state":
                    self.json(200, control.service_snapshot())
                elif path == "/api/service/teaching":
                    self.json(200, control.teaching_state())
                elif path == "/api/service/warehouses":
                    self.json(200, control.warehouse_catalog())
                elif match := VISUALIZATION_SERVICE.fullmatch(path):
                    self.visualization(control.visualizations.get(match[1], match[2], private=True))
                elif match := TEACHING_PREVIEW.fullmatch(path):
                    with control.teaching.operations:
                        preview = control.teaching.get_preview(match[1], self.service_token(), monotonic())
                    self.reply(200, preview.jpeg, "image/jpeg")
                elif match := TEACHING_PHOTO.fullmatch(path):
                    self.reply(200, control.teaching.photo(match[1], match[2]), "image/jpeg")
                elif match := ROUTE_STATE.fullmatch(path):
                    self.json(200, control.route_review.state(match[1]))
                elif match := MAPPING_RESULT.fullmatch(path):
                    root = control.data / "mapping"
                    if match[2] not in ROUTE_FILES | {"map.ply", "result.json", "locations.json", MAP_FILE}:
                        raise FileNotFoundError
                    if not session_path(root, match[1], "result.json").is_file():
                        raise FileNotFoundError
                    result = session_path(root, match[1], match[2])
                    content_type = "application/json" if match[2].endswith(".json") else "application/octet-stream"
                    self.reply(200, result.read_bytes(), content_type,
                               {"Content-Disposition": f'attachment; filename="{match[1]}-{match[2]}"'})
                else:
                    self.json(404, {"error": "Not found"})

        def measured_cloud(self, live):
            stream = control.map_stream()
            if stream is None:
                self.json(404, {"error": "3D Scan requires sensor-based localization."})
                return
            query = parse_qs(urlsplit(self.path).query)
            detail = "live" if live else query.get("detail", ["balanced"])[0]
            if not live and detail not in DETAIL:
                self.json(400, {"error": "Select low, balanced or high detail."})
                return
            sample = control.latest_scan() if live else stream.sample
            headers = {"X-Frame": FRAME}
            if not live:
                headers.update({"X-Map-Source": SLAM_MAP if stream is control.slam_map else MAP_TOPIC,
                                "X-Map-Session": stream.session, "X-Voxel-Metres": str(VOXEL_METRES),
                                "X-TF-Age-Ms": str(round((monotonic() - control.scan_tf_at) * 1000))
                                if control.scan_tf_at else ""})
            if sample is None:
                self.reply(204, b"", "application/octet-stream", headers)
                return
            etag = sample.etag(detail)
            headers.update({"ETag": etag, "X-Map-Session": sample.session, "X-Point-Count": str(len(sample.data) // 12),
                            "X-Received-At": sample.updated_at, "X-Sample-Age-Ms": str(sample.age_ms)})
            if self.headers.get("If-None-Match") == etag:
                self.reply(304, b"", "application/octet-stream", headers)
                return
            data = sample.data if live else stream.payload(sample, detail)
            self.reply(200, data, "application/octet-stream", headers)

        def business(self, path, payload=None):
            if control.backend_state["mode"] != "mock_sap":
                self.json(404, {"error": "Warehouse Intelligence requires the Mock SAP profile."})
                return
            data = json.dumps(payload).encode() if payload is not None else None
            try:
                request = Request(control.backend + path, data, {"Content-Type": "application/json"})
                with urlopen(request, timeout=6) as response:
                    self.reply(response.status, response.read(), response.headers.get_content_type())
            except HTTPError as error:
                body = json.load(error)
                detail = body.get("detail")
                self.json(error.code, {"error": detail.get("message", "Business request rejected.")
                                       if isinstance(detail, dict) else "Business request rejected."})
            except (OSError, ValueError):
                self.json(502, {"error": "Mock SAP is temporarily unavailable."})

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path in STATIC:
                    filename, media_type = STATIC[path]
                    self.reply(200, (control.web / filename).read_bytes(), media_type + "; charset=utf-8")
                elif path == "/api/layout":
                    self.json(200, control.layout)
                elif path == "/api/state":
                    self.json(200, control.snapshot())
                elif path in {"/api/measured-map", "/api/measured-scan"}:
                    self.measured_cloud(path == "/api/measured-scan")
                elif (path == "/api/visualization/active" and control.learned_mode) or VISUALIZATION_RUN.fullmatch(path):
                    if not self.local_request():
                        self.json(403, {"error": "Open the local Control Center URL to view warehouse models."})
                    elif path.endswith("/active"):
                        self.visualization(control.visualizations.active())
                    else:
                        self.visualization(control.visualizations.for_run(path.rsplit("/", 1)[1]))
                elif path.startswith("/api/service/"):
                    self.service_read(path)
                elif path == "/api/business/summary":
                    inspection = parse_qs(urlsplit(self.path).query).get("inspection_id", [""])[0]
                    if re.fullmatch(RUN, inspection):
                        self.business(path + "?" + urlencode({"inspection_id": inspection}))
                    else:
                        self.json(422, {"error": "Choose an inspection."})
                elif BUSINESS_PHOTO.fullmatch(path):
                    self.business(path)
                elif path in {"/api/frame.jpg", "/api/overview.jpg"}:
                    frame = control.frame(overview=path == "/api/overview.jpg")
                    self.reply(200, frame, "image/jpeg") if frame else self.json(404, {"error": "Waiting for camera"})
                elif match := REPORT.fullmatch(path):
                    report = control.data / "reports" / match[1] / "index.html"
                    self.reply(200, report.read_bytes(), "text/html; charset=utf-8")
                elif control.recovery_enabled and (match := RECOVERY.fullmatch(path)):
                    archive = control.data / "recoveries" / match[1]
                    self.reply(200, archive.read_bytes(), "application/json")
                elif match := PHOTO.fullmatch(path):
                    photo = control.data / "quality" / match[1] / match[2] / f"{match[3]}.png"
                    self.reply(200, photo.read_bytes(), "image/png")
                else:
                    self.json(404, {"error": "Not found"})
            except FileNotFoundError:
                self.json(404, {"error": "File not found"})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (ValueError, RuntimeError, OSError) as error:
                self.json(409, {"error": str(error)})

        def do_POST(self):
            try:
                if not self.local_request():
                    self.json(403, {"error": "Open the local Control Center URL to send mission commands."})
                    return
                path = urlsplit(self.path).path
                service = path.startswith("/api/service/")
                if service and path != "/api/service/unlock" and not self.require_service():
                    return
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192 or self.headers.get_content_type() != "application/json":
                    raise ValueError("Expected a small JSON request.")
                selection = json.loads(self.rfile.read(size))
                if not isinstance(selection, dict):
                    raise ValueError("Expected a JSON object.")
                actions = {"/api/plan": control.preview, "/api/start": control.begin, "/api/abort": control.abort,
                           "/api/manual/start": control.start_manual,
                           "/api/manual/movement": lambda body: control.manual_command(body, "movement"),
                           "/api/manual/return": lambda body: control.manual_command(body, "return"),
                           "/api/simulation/worker": control.move_worker, "/api/simulation/obstacle": control.move_obstacle}
                if service:
                    self.service_action(path, selection)
                    return
                if BUSINESS_VERIFY.fullmatch(path):
                    self.business(path, selection)
                    return
                if path in {"/api/recovery/evaluate", "/api/recovery/authorize", "/api/recovery/abort"}:
                    self.json(200, control.recovery_action(selection, path.rsplit("/", 1)[1]))
                    return
                action = actions.get(path)
                if action:
                    self.json(200, action(selection))
                else:
                    self.json(404, {"error": "Not found"})
            except ValueError as error:
                self.json(400, {"error": str(error)})
            except (OSError, RuntimeError) as error:
                self.json(409, {"error": str(error)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
