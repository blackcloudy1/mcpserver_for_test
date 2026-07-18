import httpx
import pytest

from security_lab.app import app


@pytest.mark.asyncio
async def test_safe_read_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_opa_post(self, url, json):  # type: ignore[no-untyped-def]
        return httpx.Response(
            200,
            json={"result": {"decision": "allow", "risk": "low", "reasons": []}},
            request=httpx.Request("POST", url),
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        send_to_app = client.post
        monkeypatch.setattr(httpx.AsyncClient, "post", fake_opa_post)
        response = await send_to_app(
            "/policy/evaluate",
            json={"tool": {"name": "docs.search", "arguments": {}}, "context": {}},
        )

    assert response.status_code == 200
    assert response.json()["decision"] == "allow"


@pytest.mark.asyncio
async def test_side_effect_fails_closed_when_opa_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    async def offline_opa_post(self, url, json):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("offline", request=httpx.Request("POST", url))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        send_to_app = client.post
        monkeypatch.setattr(httpx.AsyncClient, "post", offline_opa_post)
        response = await send_to_app(
            "/policy/evaluate",
            json={
                "tool": {"name": "http.request", "arguments": {"host": "attacker.example"}},
                "context": {"contains_secret": True},
            },
        )

    assert response.status_code == 200
    assert response.json()["decision"] == "deny"
    assert "policy_engine_unavailable" in response.json()["reasons"]
