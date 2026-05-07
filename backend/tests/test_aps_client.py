import time
import pytest
import respx
import httpx
from aps_client import APSClient

APS_AUTH_URL = "https://developer.api.autodesk.com/authentication/v2/token"

@pytest.fixture
def client():
    return APSClient()

@respx.mock
async def test_get_token_fetches_and_caches(client):
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok_abc",
        "expires_in": 3600,
        "token_type": "Bearer",
    }))

    token = await client.get_token()
    assert token == "tok_abc"
    # Zweiter Aufruf darf NICHT nochmals HTTP machen (Cache)
    token2 = await client.get_token()
    assert token2 == "tok_abc"
    assert respx.calls.call_count == 1

@respx.mock
async def test_get_token_refreshes_when_expiring(client):
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok_fresh",
        "expires_in": 3600,
        "token_type": "Bearer",
    }))
    # Token künstlich als bald ablaufend setzen
    client._token = "tok_old"
    client._token_expiry = time.time() + 200  # < 300s Puffer

    token = await client.get_token()
    assert token == "tok_fresh"
