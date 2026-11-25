"""Serve the packaged browser UI and mission-specific actions over loopback."""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


STATIC = {"/": ("index.html", "text/html"), "/style.css": ("style.css", "text/css"),
          "/app.js": ("app.js", "text/javascript")}
RUN = r"INS-[A-Z0-9-]{1,60}"
REPORT = re.compile(fr"/reports/({RUN})$")
PHOTO = re.compile(fr"/evidence/({RUN})/(Q-[A-Z0-9]{{32}})/(camera|annotated)\.png$")


def serve(control, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, data, media_type):
            self.send_response(code)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def json(self, code, payload):
            self.reply(code, json.dumps(payload, separators=(",", ":")).encode(), "application/json")

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
                elif path == "/api/frame.jpg":
                    frame = control.frame()
                    self.reply(200, frame, "image/jpeg") if frame else self.json(404, {"error": "Waiting for camera"})
                elif match := REPORT.fullmatch(path):
                    report = control.data / "reports" / match[1] / "index.html"
                    self.reply(200, report.read_bytes(), "text/html; charset=utf-8")
                elif match := PHOTO.fullmatch(path):
                    photo = control.data / "quality" / match[1] / match[2] / f"{match[3]}.png"
                    self.reply(200, photo.read_bytes(), "image/png")
                else:
                    self.json(404, {"error": "Not found"})
            except FileNotFoundError:
                self.json(404, {"error": "File not found"})
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            try:
                host = self.headers.get("Host")
                allowed = {f"localhost:{port}", f"127.0.0.1:{port}"}
                origin = self.headers.get("Origin")
                if host not in allowed or (origin and origin != f"http://{host}"):
                    self.json(403, {"error": "Open the local Control Center URL to send mission commands."})
                    return
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192 or self.headers.get_content_type() != "application/json":
                    raise ValueError("Expected a small JSON request.")
                selection = json.loads(self.rfile.read(size))
                if not isinstance(selection, dict):
                    raise ValueError("Expected a JSON object.")
                actions = {"/api/plan": control.preview, "/api/start": control.begin, "/api/abort": control.abort}
                action = actions.get(urlsplit(self.path).path)
                if action:
                    self.json(200, action(selection))
                else:
                    self.json(404, {"error": "Not found"})
            except ValueError as error:
                self.json(400, {"error": str(error)})
            except (OSError, RuntimeError) as error:
                self.json(409, {"error": str(error)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
