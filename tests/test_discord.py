"""Client Discord testé contre un faux serveur HTTP local qui imite l'API."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from edt_bot.discord_api import Discord, DiscordError


class FakeDiscord(BaseHTTPRequestHandler):
    calls: list = []
    rate_limit_next = False

    def log_message(self, *a):  # silence
        pass

    def _reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._reply(200, {"id": "1", "username": "edt-bot"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        FakeDiscord.calls.append((self.path, self.headers.get("Authorization"), self.headers.get("Content-Type"), body))
        if self.headers.get("Authorization") != "Bot good-token":
            return self._reply(401, {"message": "401: Unauthorized"})
        if FakeDiscord.rate_limit_next:
            FakeDiscord.rate_limit_next = False
            return self._reply(429, {"message": "You are being rate limited.", "retry_after": 0.05})
        if self.path == "/api/v10/users/@me/channels":
            assert json.loads(body)["recipient_id"] == "4242"
            return self._reply(200, {"id": "dm-99"})
        if self.path.startswith("/api/v10/channels/") and self.path.endswith("/messages"):
            return self._reply(200, {"id": "m1"})
        self._reply(404, {"message": "Unknown"})


@pytest.fixture
def server():
    FakeDiscord.calls = []
    srv = HTTPServer(("127.0.0.1", 0), FakeDiscord)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}/api/v10"
    srv.shutdown()


def test_dm_text(server):
    d = Discord("good-token", api_base=server)
    d.send_dm("4242", "Bonjour")
    d.send_dm("4242", "Encore")  # salon DM mis en cache : ouvert une seule fois
    paths = [c[0] for c in FakeDiscord.calls]
    assert paths == ["/api/v10/users/@me/channels", "/api/v10/channels/dm-99/messages", "/api/v10/channels/dm-99/messages"]
    msg = json.loads(FakeDiscord.calls[1][3])
    assert msg["content"] == "Bonjour" and msg["allowed_mentions"] == {"parse": []}


def test_dm_with_pdf_attachment(server, tmp_path):
    pdf = tmp_path / "rapport.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    Discord("good-token", api_base=server).send_dm("4242", "Voir PDF", [str(pdf)])
    path, auth, ctype, body = FakeDiscord.calls[-1]
    assert ctype.startswith("multipart/form-data")
    assert b'name="payload_json"' in body and b'"filename": "rapport.pdf"' in body
    assert b'name="files[0]"; filename="rapport.pdf"' in body and b"%PDF-1.4 test" in body


def test_long_message_is_split(server):
    Discord("good-token", api_base=server).send("123", "\n".join("x" * 150 for _ in range(30)))
    assert len(FakeDiscord.calls) == 3


def test_rate_limit_is_retried(server):
    FakeDiscord.rate_limit_next = True
    Discord("good-token", api_base=server).send("123", "hello")
    assert len(FakeDiscord.calls) == 2


def test_bad_token_raises(server):
    with pytest.raises(DiscordError, match="401"):
        Discord("bad", api_base=server).send("123", "hello")
