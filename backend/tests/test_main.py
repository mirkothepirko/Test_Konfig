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


@respx.mock
def test_configure_returns_workitem_id(client):
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer"
    }))
    respx.post(f"{APS_OSS_BASE}/buckets").mock(
        return_value=httpx.Response(409, json={"reason": "exists"})
    )
    respx.put(f"{APS_OSS_BASE}/buckets/test-bucket/objects/flex_reference.f3d").mock(
        return_value=httpx.Response(200, json={"objectKey": "flex_reference.f3d"})
    )
    respx.post(f"{APS_DA_BASE}/workitems").mock(
        return_value=httpx.Response(200, json={"id": "wi_test001", "status": "pending"})
    )

    resp = client.post("/configure", json={
        "breite": 1200, "tiefe": 600, "r_ecke": 0, "r_kante": 0
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
    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer"
    }))
    respx.get(f"{APS_DA_BASE}/workitems/wi_test001").mock(
        return_value=httpx.Response(200, json={"id": "wi_test001", "status": "pending"})
    )

    resp = client.get("/status/wi_test001")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


@respx.mock
def test_download_streams_step(client):
    # WorkItem-Output-URL in Store eintragen (simuliert POST /configure vorher)
    from main import _workitem_outputs
    _workitem_outputs["wi_dl001"] = "result_wi_dl001.step"

    respx.post(APS_AUTH_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600, "token_type": "Bearer"
    }))
    respx.get(f"{APS_OSS_BASE}/buckets/test-bucket/objects/result_wi_dl001.step").mock(
        return_value=httpx.Response(200, content=b"STEP;FILE_SCHEMA;('AP214');")
    )

    resp = client.get("/download/wi_dl001")
    assert resp.status_code == 200
    assert b"STEP" in resp.content
    assert resp.headers["content-type"] == "application/octet-stream"


def test_download_unknown_workitem(client):
    resp = client.get("/download/wi_unknown")
    assert resp.status_code == 404
