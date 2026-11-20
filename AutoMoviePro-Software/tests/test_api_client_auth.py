import httpx
import pytest
from app.api_client import LicenseClient


def test_license_client_headers_contain_bearer_token():
    token = "test_amp_jwt_token_12345"
    client = LicenseClient(base_url="http://127.0.0.1:8787", token=token)
    headers = client._headers()
    assert headers.get("Authorization") == f"Bearer {token}"
    assert headers.get("Content-Type") == "application/json"


def test_license_client_get_does_not_pass_token_in_query(monkeypatch):
    captured_requests = []

    def mock_get(self, url, *args, **kwargs):
        captured_requests.append({
            "url": str(url),
            "headers": kwargs.get("headers") or {},
            "params": kwargs.get("params")
        })
        return httpx.Response(200, json={"ok": True, "data": "test"})

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    token = "secret_customer_token_999"
    client = LicenseClient(base_url="http://127.0.0.1:8787", token=token)
    res = client._get("/api/customer.php")

    assert res == {"ok": True, "data": "test"}
    assert len(captured_requests) == 1
    req = captured_requests[0]

    # W-04 Assertion: Query parameters must not contain token
    assert req["params"] is None or "token" not in req["params"]
    assert "token=" not in req["url"]

    # Header must contain Bearer token
    assert req["headers"].get("Authorization") == f"Bearer {token}"
