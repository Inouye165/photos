"""Focused checks for LAN pairing, CSRF/DNS-rebinding defenses, and local API security."""

import asyncio
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from backend import app as app_module
from backend.gdrive_auth import _consume_verifier, _save_verifier
from backend.gdrive_service import _escape_gdrive_query_value
from backend.document_ai import analyze_document


def make_request(client_host, path="/api/stats", method="GET", host_header="localhost:8500", extra_headers=None, cookies=None):
    """Creates a minimal ASGI request for middleware checks."""
    headers = [(b"host", host_header.encode("latin-1"))]
    if extra_headers:
        for k, v in extra_headers.items():
            headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    if cookies:
        cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
        headers.append((b"cookie", cookie_header.encode("latin-1")))
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
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


def test_dns_rebinding_untrusted_host_rejected():
    response = call_pairing_middleware(make_request("127.0.0.1", host_header="evil.attacker.example:8500"))
    assert response.status_code == 403


def test_cross_site_csrf_requests_rejected():
    # Cross-site Origin on state-changing request is blocked
    res_origin = call_pairing_middleware(make_request(
        "127.0.0.1",
        path="/api/trash/empty",
        method="POST",
        extra_headers={"Origin": "https://evil.example.com"},
    ))
    assert res_origin.status_code == 403

    # Sec-Fetch-Site: cross-site on state-changing request is blocked
    res_sec_fetch = call_pairing_middleware(make_request(
        "127.0.0.1",
        path="/api/documents/clear-catalog",
        method="POST",
        extra_headers={"Sec-Fetch-Site": "cross-site"},
    ))
    assert res_sec_fetch.status_code == 403

    # Same-origin local Origin is allowed
    res_valid = call_pairing_middleware(make_request(
        "127.0.0.1",
        path="/api/trash/empty",
        method="POST",
        extra_headers={"Origin": "http://localhost:8500"},
    ))
    assert res_valid.status_code == 200


def test_oauth_callback_escapes_html_xss():
    client = TestClient(app_module.app)
    xss_payload = "<script>alert('xss')</script>"
    res = client.get("/api/backup/auth/callback", params={"error": xss_payload})
    assert res.status_code == 400
    assert xss_payload not in res.text
    assert "&lt;script&gt;" in res.text


def test_oauth_state_strict_validation():
    _save_verifier("valid_state_123", "pkce_secret_xyz")
    with pytest.raises(ValueError):
        _consume_verifier(None)
    with pytest.raises(ValueError):
        _consume_verifier("wrong_state")
    with pytest.raises(ValueError):
        _consume_verifier("latest")

    # Valid state succeeds once and is then consumed
    assert _consume_verifier("valid_state_123") == "pkce_secret_xyz"
    with pytest.raises(ValueError):
        _consume_verifier("valid_state_123")


def test_gdrive_query_escaping():
    raw = "My 'Vacation'\\Photos"
    escaped = _escape_gdrive_query_value(raw)
    assert escaped == "My \\'Vacation\\'\\\\Photos"


def test_ai_model_validation_blocks_invalid_model_names():
    with pytest.raises(ValueError):
        analyze_document({"id": 1, "title": "test", "extracted_text": "hello"}, [], model="bad model; rm -rf")


def test_photo_directory_validation_blocks_unc_and_windows_system():
    assert not app_module._is_allowed_photo_directory(r"\\attacker-server\share\photos")
    assert not app_module._is_allowed_photo_directory(r"C:\Windows\System32")
    assert app_module._is_allowed_photo_directory(app_module.WORKSPACE_DIR)
