import pytest
import respx
import httpx
from fastapi.testclient import TestClient

APS_AUTH_URL = "https://developer.api.autodesk.com/authentication/v2/token"
APS_OSS_BASE = "https://developer.api.autodesk.com/oss/v2"
APS_DA_BASE = "https://developer.api.autodesk.com/da/us-east/v3"


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


def _mock_token():
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer",
    }))


@respx.mock
def test_configure_returns_workitem_id(client):
    _mock_token()
    respx.post(f"{APS_OSS_BASE}/buckets").mock(
        return_value=httpx.Response(409, json={"reason": "exists"})
    )
    # signed S3 upload init for the model
    s3_put_model = "https://s3/model-put?sig=m"
    respx.get(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/flex_reference.f3d/signeds3upload"
    ).mock(return_value=httpx.Response(200, json={
        "uploadKey": "upk_model",
        "urls": [s3_put_model],
    }))
    respx.put(s3_put_model).mock(return_value=httpx.Response(200))
    # finalize upload + signed-download for the model share the same path,
    # so respx will dispatch by method (POST vs GET) below.
    respx.post(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/flex_reference.f3d/signeds3upload"
    ).mock(return_value=httpx.Response(200, json={"objectKey": "flex_reference.f3d"}))
    respx.get(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/flex_reference.f3d/signeds3download"
    ).mock(return_value=httpx.Response(200, json={
        "url": "https://s3/model-get?sig=g",
        "status": "complete",
    }))
    # signed S3 upload init for the result (object key is randomized, so match by regex)
    s3_put_result = "https://s3/result-put?sig=r"
    respx.get(
        url__regex=rf"{APS_OSS_BASE}/buckets/test-bucket/objects/result_[0-9a-f]+\.step/signeds3upload"
    ).mock(return_value=httpx.Response(200, json={
        "uploadKey": "upk_result",
        "urls": [s3_put_result],
    }))
    respx.get(f"{APS_DA_BASE}/forgeapps/me").mock(
        return_value=httpx.Response(200, json="test_owner")
    )
    respx.post(f"{APS_DA_BASE}/workitems").mock(
        return_value=httpx.Response(200, json={"id": "wi_test001", "status": "pending"})
    )

    resp = client.post("/configure", json={
        "breite": 1200, "tiefe": 600, "r_ecke": 0, "r_kante": 0,
    })
    assert resp.status_code == 200
    assert resp.json()["workItemId"] == "wi_test001"


@respx.mock
def test_configure_validates_params(client):
    resp = client.post("/configure", json={
        "breite": 9999,  # > 1800, ungültig
        "tiefe": 600,
        "r_ecke": 0,
        "r_kante": 0,
    })
    assert resp.status_code == 422


@respx.mock
def test_status_returns_pending(client):
    _mock_token()
    respx.get(f"{APS_DA_BASE}/workitems/wi_test001").mock(
        return_value=httpx.Response(200, json={"id": "wi_test001", "status": "pending"})
    )

    resp = client.get("/status/wi_test001")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


@respx.mock
def test_download_finalizes_then_streams_step(client):
    from main import _workitem_outputs
    object_key = "result_wi_dl001.step"
    _workitem_outputs["wi_dl001"] = {
        "object_key": object_key,
        "upload_key": "upk_dl",
        "finalized": False,
    }

    _mock_token()
    finalize_route = respx.post(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/{object_key}/signeds3upload"
    ).mock(return_value=httpx.Response(200, json={"objectKey": object_key}))
    signed_get = "https://s3/result-get?sig=dl"
    respx.get(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/{object_key}/signeds3download"
    ).mock(return_value=httpx.Response(200, json={
        "url": signed_get, "status": "complete",
    }))
    respx.get(signed_get).mock(
        return_value=httpx.Response(200, content=b"STEP;FILE_SCHEMA;('AP214');")
    )

    resp = client.get("/download/wi_dl001")
    assert resp.status_code == 200
    assert b"STEP" in resp.content
    assert resp.headers["content-type"] == "application/octet-stream"
    assert finalize_route.called
    assert _workitem_outputs["wi_dl001"]["finalized"] is True


@respx.mock
def test_download_skips_finalize_when_already_done(client):
    from main import _workitem_outputs
    object_key = "result_wi_dl002.step"
    _workitem_outputs["wi_dl002"] = {
        "object_key": object_key,
        "upload_key": "upk_dl",
        "finalized": True,
    }

    _mock_token()
    finalize_route = respx.post(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/{object_key}/signeds3upload"
    ).mock(return_value=httpx.Response(200))
    signed_get = "https://s3/result-get?sig=dl2"
    respx.get(
        f"{APS_OSS_BASE}/buckets/test-bucket/objects/{object_key}/signeds3download"
    ).mock(return_value=httpx.Response(200, json={
        "url": signed_get, "status": "complete",
    }))
    respx.get(signed_get).mock(return_value=httpx.Response(200, content=b"STEP;"))

    resp = client.get("/download/wi_dl002")
    assert resp.status_code == 200
    assert not finalize_route.called


def test_download_unknown_workitem(client):
    resp = client.get("/download/wi_unknown")
    assert resp.status_code == 404
