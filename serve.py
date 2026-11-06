"""Serve index.html (built by build.py) on 127.0.0.1; nothing else in the directory is exposed.
Put it on the tailnet with `tailscale serve`:

    python3 serve.py [--port 8550]
    tailscale serve --bg --https=8550 http://127.0.0.1:8550   # -> https://wsl.tail0fe898.ts.net:8550/
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = Path(__file__).resolve().parent / "index.html"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] not in ("/", "/index.html"):
            return self.send_error(404)
        body = PAGE.read_bytes()  # re-read each time so a rebuild shows up on refresh
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8550)
    args = ap.parse_args()
    print(f"serving {PAGE.name} on http://127.0.0.1:{args.port}/")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
