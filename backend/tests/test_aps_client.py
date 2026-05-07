import time
import pytest
import respx
import httpx
from aps_client import APSClient

APS_AUTH_URL = "https://developer.api.autodesk.com/authentication/v2/token"
APS_OSS_BASE = "https://developer.api.autodesk.com/oss/v2"
APS_DA_BASE = "https://developer.api.autodesk.com/da/us-east/v3"


@pytest.fixture
def client():
    return APSClient()


def _mock_token():
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer",
    }))


@respx.mock
async def test_get_token_fetches_and_caches(client):
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok_abc", "expires_in": 3600, "token_type": "Bearer",
    }))

    token = await client.get_token()
    assert token == "tok_abc"
    token2 = await client.get_token()
    assert token2 == "tok_abc"
    assert respx.calls.call_count == 1


@respx.mock
async def test_get_token_refreshes_when_expiring(client):
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok_fresh", "expires_in": 3600, "token_type": "Bearer",
    }))
    client._token = "tok_old"
    client._token_expiry = time.time() + 200

    token = await client.get_token()
    assert token == "tok_fresh"


@respx.mock
async def test_ensure_bucket_creates_if_missing(client):
    _mock_token()
    respx.post(f"{APS_OSS_BASE}/buckets").mock(
        return_value=httpx.Response(200, json={"bucketKey": "test-bucket"})
    )
    await client.ensure_bucket()
    assert respx.calls.call_count == 2


@respx.mock
async def test_ensure_bucket_ok_if_already_exists(client):
    _mock_token()
    respx.post(f"{APS_OSS_BASE}/buckets").mock(
        return_value=httpx.Response(409, json={"reason": "Bucket already exists"})
    )
    await client.ensure_bucket()


@respx.mock
async def test_upload_file_uses_signed_s3(client, tmp_path):
    test_file = tmp_path / "test.f3d"
    test_file.write_bytes(b"fake-fusion-data")

    _mock_token()
    s3_put_url = "https://s3.amazonaws.com/aps-bucket/upload-target?signature=abc"
    respx.get(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/test.f3d/signeds3upload"
    ).mock(return_value=httpx.Response(200, json={
        "uploadKey": "upkey_xyz",
        "urls": [s3_put_url],
    }))
    s3_route = respx.put(s3_put_url).mock(return_value=httpx.Response(200))
    finalize_route = respx.post(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/test.f3d/signeds3upload"
    ).mock(return_value=httpx.Response(200, json={"objectKey": "test.f3d"}))

    object_key = await client.upload_file(str(test_file), "test.f3d")
    assert object_key == "test.f3d"
    assert s3_route.called
    assert finalize_route.called
    assert finalize_route.calls.last.request.read() == b'{"uploadKey": "upkey_xyz"}'


@respx.mock
async def test_get_signed_download(client):
    _mock_token()
    signed = "https://s3.amazonaws.com/aps/result.step?sig=xyz"
    respx.get(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/result_wi.step/signeds3download"
    ).mock(return_value=httpx.Response(200, json={"url": signed, "status": "complete"}))

    url = await client.get_signed_download("result_wi.step")
    assert url == signed


@respx.mock
async def test_init_signed_upload(client):
    _mock_token()
    s3_put = "https://s3/put?sig=1"
    respx.get(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/result_wi.step/signeds3upload"
    ).mock(return_value=httpx.Response(200, json={
        "uploadKey": "upk_1",
        "urls": [s3_put],
    }))

    upload_key, put_url = await client.init_signed_upload("result_wi.step")
    assert upload_key == "upk_1"
    assert put_url == s3_put


@respx.mock
async def test_finalize_upload(client):
    _mock_token()
    route = respx.post(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/result_wi.step/signeds3upload"
    ).mock(return_value=httpx.Response(200, json={"objectKey": "result_wi.step"}))

    await client.finalize_upload("result_wi.step", "upk_1")
    assert route.called
    assert route.calls.last.request.read() == b'{"uploadKey": "upk_1"}'


@respx.mock
async def test_download_file_uses_signed_s3(client):
    _mock_token()
    signed = "https://s3.amazonaws.com/aps/result.step?sig=abc"
    respx.get(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/result_wi123.step/signeds3download"
    ).mock(return_value=httpx.Response(200, json={"url": signed, "status": "complete"}))
    respx.get(signed).mock(return_value=httpx.Response(200, content=b"STEP;FILE_SCHEMA;"))

    data = await client.download_file("result_wi123.step")
    assert data == b"STEP;FILE_SCHEMA;"


@respx.mock
async def test_submit_workitem_returns_id(client):
    _mock_token()
    respx.get(f"{APS_DA_BASE}/forgeapps/me").mock(
        return_value=httpx.Response(200, json="test_owner")
    )
    route = respx.post(f"{APS_DA_BASE}/workitems").mock(
        return_value=httpx.Response(200, json={"id": "wi_abc123", "status": "pending"})
    )

    params = {"breite": 1200, "tiefe": 600, "r_ecke": 0, "r_kante": 0, "dicke": 28.6}
    model_url = "https://s3/get?sig=m"
    result_url = "https://s3/put?sig=r"

    wi_id = await client.submit_workitem(params, model_url, result_url)
    assert wi_id == "wi_abc123"
    body = route.calls.last.request.read().decode()
    assert "https://s3/get?sig=m" in body
    assert "https://s3/put?sig=r" in body
    assert '"verb": "get"' in body
    assert '"verb": "put"' in body
    assert '"activityId": "test_owner.FlexTableActivity+prod"' in body


@respx.mock
async def test_get_owner_caches(client):
    _mock_token()
    route = respx.get(f"{APS_DA_BASE}/forgeapps/me").mock(
        return_value=httpx.Response(200, json="my_app_id")
    )
    assert await client.get_owner() == "my_app_id"
    assert await client.get_owner() == "my_app_id"
    assert route.call_count == 1


@respx.mock
async def test_poll_status_returns_status_string(client):
    _mock_token()
    respx.get(f"{APS_DA_BASE}/workitems/wi_abc123").mock(
        return_value=httpx.Response(200, json={"id": "wi_abc123", "status": "inProgress"})
    )

    status = await client.poll_status("wi_abc123")
    assert status == "inProgress"


@respx.mock
async def test_poll_status_succeeded(client):
    _mock_token()
    respx.get(f"{APS_DA_BASE}/workitems/wi_xyz").mock(
        return_value=httpx.Response(200, json={"id": "wi_xyz", "status": "succeeded"})
    )

    status = await client.poll_status("wi_xyz")
    assert status == "succeeded"
