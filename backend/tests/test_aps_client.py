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

APS_DA_BASE = "https://developer.api.autodesk.com/da/us-east/v3"

@respx.mock
async def test_submit_workitem_returns_id(client):
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer"
    }))
    respx.post(f"{APS_DA_BASE}/workitems").mock(
        return_value=httpx.Response(200, json={"id": "wi_abc123", "status": "pending"})
    )

    params = {"breite": 1200, "tiefe": 600, "r_ecke": 0, "r_kante": 0, "dicke": 28.6}
    f3d_url = f"{APS_OSS_BASE}/buckets/test-bucket/objects/flex_reference.f3d"

    wi_id = await client.submit_workitem(params, f3d_url)
    assert wi_id == "wi_abc123"

@respx.mock
async def test_poll_status_returns_status_string(client):
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer"
    }))
    respx.get(f"{APS_DA_BASE}/workitems/wi_abc123").mock(
        return_value=httpx.Response(200, json={"id": "wi_abc123", "status": "inProgress"})
    )

    status = await client.poll_status("wi_abc123")
    assert status == "inProgress"

@respx.mock
async def test_poll_status_succeeded(client):
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer"
    }))
    respx.get(f"{APS_DA_BASE}/workitems/wi_xyz").mock(
        return_value=httpx.Response(200, json={"id": "wi_xyz", "status": "succeeded"})
    )

    status = await client.poll_status("wi_xyz")
    assert status == "succeeded"
