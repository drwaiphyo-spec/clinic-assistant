#!/usr/bin/env python3
"""Proxy: serve static + proxy /api/* → MedGemma with CORS + SSE streaming."""
import http.server, urllib.request, socketserver, os, json, sys, threading, socket

TARGET = "http://127.0.0.1:8080"
DIR = os.path.expanduser("~/clinic-assistant")
BUFSIZE = 65536

class H(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIR, **kw)

    def do_OPTIONS(self):
        self._cors(204)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._get_proxy()
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        self.send_error(405)

    def _get_proxy(self):
        """Forward GET /api/* → GET /v1/* on upstream (used for /models health check)."""
        url = TARGET + self.path.replace("/api/", "/v1/", 1)
        try:
            resp = urllib.request.urlopen(
                urllib.request.Request(url, method="GET"), timeout=5)
            data = resp.read()
            ct = resp.headers.get("Content-Type", "application/json")
            self._cors(200, {"Content-Type": ct, "Content-Length": str(len(data))})
            self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self._cors(e.code, {"Content-Type": "application/json",
                                "Content-Length": str(len(data))})
            self.wfile.write(data)
        except Exception as e:
            body = json.dumps({"ok": False, "error": str(e)}).encode()
            self._cors(502, {"Content-Type": "application/json",
                             "Content-Length": str(len(body))})
            self.wfile.write(body)

    def _proxy(self):
        clen = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(clen) if clen else b""
        url = TARGET + self.path.replace("/api/", "/v1/", 1)

        fwd_headers = {"Content-Type": "application/json"}
        if auth := self.headers.get("Authorization"):
            fwd_headers["Authorization"] = auth
        try:
            req = urllib.request.Request(url, data=body or None,
                headers=fwd_headers, method="POST")
            upstream = urllib.request.urlopen(req, timeout=180)
        except urllib.error.HTTPError as e:
            data = e.read()
            self._cors(e.code, {"Content-Type": "application/json",
                                "Content-Length": str(len(data))})
            self.wfile.write(data)
            return
        except urllib.error.URLError as e:
            timed_out = isinstance(e.reason, socket.timeout)
            code = 504 if timed_out else 502
            msg = "Upstream timed out after 180 s." if timed_out else str(e.reason)
            err_body = json.dumps({"error": msg}).encode()
            self._cors(code, {"Content-Type": "application/json",
                              "Content-Length": str(len(err_body))})
            self.wfile.write(err_body)
            return
        except Exception as e:
            err_body = json.dumps({"error": str(e)}).encode()
            self._cors(502, {"Content-Type": "application/json",
                             "Content-Length": str(len(err_body))})
            self.wfile.write(err_body)
            return

        ct = upstream.headers.get("Content-Type", "")
        is_stream = "text/event-stream" in ct or "application/x-ndjson" in ct

        if is_stream:
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", ct)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    chunk = upstream.read(BUFSIZE)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                upstream.close()
        else:
            data = upstream.read()
            self._cors(upstream.status, {
                "Content-Type": ct,
                "Content-Length": str(len(data))
            })
            self.wfile.write(data)

    def _cors(self, status, extra=None):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), H) as s:
        print(f"Serving at http://127.0.0.1:{port}")
        s.serve_forever()
