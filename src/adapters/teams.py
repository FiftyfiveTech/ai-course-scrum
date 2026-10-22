"""Teams adapter. Step 1: receive activities on /api/messages and print them."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST, PORT = "127.0.0.1", 3978


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/api/messages":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        activity = json.loads(self.rfile.read(length))
        print(json.dumps(activity, indent=2))
        self.send_response(200)
        self.end_headers()


if __name__ == "__main__":
    print(f"listening on http://{HOST}:{PORT}/api/messages")
    HTTPServer((HOST, PORT), Handler).serve_forever()
