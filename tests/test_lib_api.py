"""
HTTP against Memori, tested by import.

The identity token and the client key ride on every request, so the thing worth
pinning down is where they are allowed to travel.
"""

import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from conftest import configure
from memori import api


class Server(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/away":
            return self.__redirect(self.server.elsewhere + "/stolen")

        if self.path == "/here":
            return self.__redirect(f"http://{self.headers['Host']}/landed")

        self.server.reached.append(self.path)
        self.server.headers_seen = dict(self.headers)

        payload = b"{}"
        self.send_response(200)
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def __redirect(self, where):
        self.send_response(302)
        self.send_header("Location", where)
        self.end_headers()

    def log_message(self, *args):
        pass


def serve():
    server = HTTPServer(("127.0.0.1", 0), Server)
    server.reached = []
    server.headers_seen = {}
    server.elsewhere = ""

    threading.Thread(target=server.serve_forever, daemon=True).start()

    return server


@pytest.fixture
def servers(settings):
    """A Memori, and a second host it might be redirected to."""

    memori, other = serve(), serve()
    memori.elsewhere = f"http://127.0.0.1:{other.server_port}"

    configure({"api_url": f"http://127.0.0.1:{memori.server_port}"})
    settings()

    yield memori, other

    for server in (memori, other):
        server.shutdown()
        server.server_close()


def test_a_redirect_to_another_host_is_refused(servers):
    # urllib copies every header onto the redirected request with no same-origin
    # check, so following one would hand the credentials to whoever answered.
    _, other = servers

    with pytest.raises(urllib.error.HTTPError):
        api.get("/away")

    assert other.reached == []
    assert other.headers_seen == {}


def test_the_refusal_says_why(servers):
    with pytest.raises(urllib.error.HTTPError) as raised:
        api.get("/away")

    assert "another host" in str(raised.value.reason)
    assert "api url" in str(raised.value.reason)


def test_a_redirect_off_https_is_refused(servers):
    # Same host, so the netloc check passes -- but plain http would put the
    # credentials on the wire in the clear.
    memori, _ = servers
    handler = api.SameHostRedirects()

    request = urllib.request.Request("https://api.example/v1/recall")

    with pytest.raises(urllib.error.HTTPError) as raised:
        handler.redirect_request(
            request, None, 302, "Found", {}, "http://api.example/v1/recall"
        )

    assert "https to plain http" in str(raised.value.reason)


def test_an_upgrade_to_https_is_allowed(servers):
    handler = api.SameHostRedirects()
    request = urllib.request.Request("http://api.example/v1/recall")

    allowed = handler.redirect_request(
        request, None, 302, "Found", {}, "https://api.example/v1/recall"
    )

    assert allowed.full_url == "https://api.example/v1/recall"


def test_a_redirect_within_the_same_host_is_followed(servers):
    # Ordinary path normalisation. The credentials are not going anywhere new.
    memori, _ = servers

    api.get("/here")

    assert memori.reached == ["/landed"]


def test_the_credentials_reach_memori_itself(servers):
    memori, _ = servers

    api.get("/v1/compaction")

    assert memori.headers_seen["Authorization"] == "Bearer id_test_acme_abcdefgh"
    assert memori.headers_seen["X-Memori-Api-Key"] == "test-client-key"
