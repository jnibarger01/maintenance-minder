"""Local development server.

    python3 server.py

Then open http://localhost:4173. Serves the static frontend from this directory
and resolves vehicle photos through photo_resolver.

For deployment, api/index.py exposes the same routes as a FastAPI app.
"""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import photo_resolver

ROOT = photo_resolver.ROOT
PORT = 4173


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parts = urlsplit(self.path)

        if parts.path == "/api/vehicle-image":
            values = parse_qs(parts.query)
            try:
                year = int(values.get("year", [""])[0])
            except ValueError:
                year = 0
            payload = photo_resolver.resolve(
                year,
                values.get("model", [""])[0],
                values.get("trim", [""])[0],
            )
            self._send_json(payload, cache=False)
            return

        if parts.path == "/api/health":
            self._send_json({"status": "ok"}, cache=False)
            return

        return super().do_GET()

    def _send_json(self, payload, cache):
        import json

        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # The resolver falls back to live scraping, so results are not immutable.
        self.send_header("Cache-Control", "no-store" if not cache else "max-age=3600")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print("%s - %s" % (self.log_date_time_string(), format % args))


if __name__ == "__main__":
    print(f"Honda Maintenance Minder Explainer on http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()