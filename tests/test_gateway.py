"""Optional real Caddy gateway test with local OAuth and upstream doubles."""
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest


def test_gateway_authentication_and_header_stripping(tmp_path):
    binary = os.environ.get("CADDY_BIN") or shutil.which("caddy")
    if not binary:
        pytest.skip("Set CADDY_BIN to run the real local gateway check")

    class OAuth(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.headers.get("Cookie") == "session=allowed":
                self.send_response(204)
                self.send_header("X-Auth-Request-User", "verified-google-subject")
                self.send_header("X-Auth-Request-Email", "allowed@example.com")
            else:
                self.send_response(401)
            self.end_headers()

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"user": self.headers.get("X-Auth-User"), "email": self.headers.get("X-Auth-Email"), "secret": self.headers.get("X-Proxy-Secret"), "body": self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()}).encode())

        do_POST = do_GET

    oauth = ThreadingHTTPServer(("127.0.0.1", 0), OAuth)
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    for server in [oauth, upstream]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        gateway_port = s.getsockname()[1]
    config = Path("deploy/Caddyfile").read_text()
    config = "{\n admin off\n auto_https off\n}\n" + config.replace("{$APP_DOMAIN}", f"http://127.0.0.1:{gateway_port}").replace("{$QS_PROXY_SECRET}", "test-private-gateway-secret").replace("oauth:4180", f"127.0.0.1:{oauth.server_port}").replace("app:8000", f"127.0.0.1:{upstream.server_port}")
    path = tmp_path / "Caddyfile"
    path.write_text(config)
    process = subprocess.Popen([binary, "run", "--config", str(path), "--adapter", "caddyfile"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{gateway_port}", timeout=2) as client:
            for attempt in range(50):
                try:
                    response = client.get("/api/v1/auth/me")
                    break
                except httpx.ConnectError:
                    time.sleep(0.1)
            else:
                pytest.fail("Gateway did not start")
            assert response.status_code == 401
            assert client.get("/markets").status_code == 302
            spoofed = {"X-Auth-User": "forged", "X-Auth-Email": "forged@example.com", "X-Proxy-Secret": "forged", "X-Auth-Request-User": "forged"}
            assert client.get("/api/v1/portfolios", headers=spoofed).status_code == 401
            response = client.post("/api/v1/portfolios", headers={**spoofed, "Cookie": "session=allowed"}, content="body-preserved")
            assert response.status_code == 200
            assert response.json() == {"user": "verified-google-subject", "email": "allowed@example.com", "secret": "test-private-gateway-secret", "body": "body-preserved"}
    finally:
        process.terminate()
        process.wait(timeout=5)
        for server in [oauth, upstream]:
            server.shutdown()
            server.server_close()
