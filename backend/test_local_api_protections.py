"""Focused checks for LAN pairing and complete identity-review confirmation."""

import asyncio

from starlette.requests import Request
from starlette.responses import Response

from backend import app as app_module


def make_request(client_host, path="/api/stats", cookies=None):
    """Creates a minimal ASGI request for middleware checks."""
    headers = [(b"host", b"localhost:8500")]
    if cookies:
        cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
        headers.append((b"cookie", cookie_header.encode("latin-1")))
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": (client_host, 43210),
        "server": ("localhost", 8500),
    })


def call_pairing_middleware(request):
    """Runs the HTTP middleware with a successful downstream response."""
    async def downstream(_request):
        return Response("ok", status_code=200)

    return asyncio.run(app_module.require_lan_pairing(request, downstream))


def test_remote_api_requires_paired_session():
    response = call_pairing_middleware(make_request("192.168.1.20"))
    assert response.status_code == 401

    response = call_pairing_middleware(make_request(
        "192.168.1.20",
        cookies={app_module._LAN_SESSION_COOKIE: app_module._LAN_ACCESS_STATE["session_token"]},
    ))
    assert response.status_code == 200


def test_loopback_api_remains_available_without_pairing():
    response = call_pairing_middleware(make_request("127.0.0.1"))
    assert response.status_code == 200

