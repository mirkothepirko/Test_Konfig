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

APS_OSS_BASE = "https://developer.api.autodesk.com/oss/v2"

@respx.mock
async def test_ensure_bucket_creates_if_missing(client):
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer"
    }))
    respx.post(f"{APS_OSS_BASE}/buckets").mock(
        return_value=httpx.Response(200, json={"bucketKey": "test-bucket"})
    )
    await client.ensure_bucket()
    assert respx.calls.call_count == 2  # token + create bucket

@respx.mock
async def test_ensure_bucket_ok_if_already_exists(client):
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer"
    }))
    respx.post(f"{APS_OSS_BASE}/buckets").mock(
        return_value=httpx.Response(409, json={"reason": "Bucket already exists"})
    )
    await client.ensure_bucket()  # darf kein Exception werfen

@respx.mock
async def test_upload_file(client, tmp_path):
    test_file = tmp_path / "test.f3d"
    test_file.write_bytes(b"fake-fusion-data")

    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer"
    }))
    respx.put(f"{APS_OSS_BASE}/buckets/test-bucket/objects/test.f3d").mock(
        return_value=httpx.Response(200, json={"objectKey": "test.f3d"})
    )
    url = await client.upload_file(str(test_file), "test.f3d")
    assert url == f"{APS_OSS_BASE}/buckets/test-bucket/objects/test.f3d"

@respx.mock
async def test_download_file(client):
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer"
    }))
    step_content = b"STEP;FILE_SCHEMA;"
    respx.get(f"{APS_OSS_BASE}/buckets/test-bucket/objects/result_wi123.step").mock(
        return_value=httpx.Response(200, content=step_content)
    )
    data = await client.download_file("result_wi123.step")
    assert data == step_content
