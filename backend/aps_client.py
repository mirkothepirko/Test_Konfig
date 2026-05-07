import time
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

APS_AUTH_URL = "https://developer.api.autodesk.com/authentication/v2/token"
APS_OSS_BASE = "https://developer.api.autodesk.com/oss/v2"
APS_DA_BASE = "https://developer.api.autodesk.com/da/us-east/v3"


class APSClient:
    def __init__(self):
        self._client_id = os.environ["APS_CLIENT_ID"]
        self._client_secret = os.environ["APS_CLIENT_SECRET"]
        self._bucket = os.environ["APS_BUCKET"]
        self._appbundle_alias = os.environ.get("APS_APPBUNDLE_ALIAS", "prod")
        self._activity_alias = os.environ.get("APS_ACTIVITY_ALIAS", "prod")
        self._token: str | None = None
        self._token_expiry: float = 0.0

    async def get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 300:
            return self._token
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                APS_AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "scope": "data:read data:write data:create bucket:read bucket:create code:all",
                },
                auth=(self._client_id, self._client_secret),
            )
            resp.raise_for_status()
            body = resp.json()
        self._token = body["access_token"]
        self._token_expiry = time.time() + body["expires_in"]
        return self._token

    async def ensure_bucket(self) -> None:
        token = await self.get_token()
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"{APS_OSS_BASE}/buckets",
                headers={"Authorization": f"Bearer {token}"},
                json={"bucketKey": self._bucket, "policyKey": "persistent"},
            )
            if resp.status_code not in (200, 409):
                resp.raise_for_status()

    async def upload_file(self, local_path: str, object_key: str) -> str:
        token = await self.get_token()
        with open(local_path, "rb") as f:
            data = f.read()
        async with httpx.AsyncClient() as http:
            resp = await http.put(
                f"{APS_OSS_BASE}/buckets/{self._bucket}/objects/{object_key}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/octet-stream",
                },
                content=data,
            )
            resp.raise_for_status()
        return f"{APS_OSS_BASE}/buckets/{self._bucket}/objects/{object_key}"

    async def download_file(self, object_key: str) -> bytes:
        token = await self.get_token()
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{APS_OSS_BASE}/buckets/{self._bucket}/objects/{object_key}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.content

    async def submit_workitem(self, params: dict, f3d_oss_url: str) -> str:
        token = await self.get_token()
        import json as _json

        activity_id = f"test-konfig.FlexTableActivity+{self._activity_alias}"

        payload = {
            "activityId": activity_id,
            "arguments": {
                "params": {
                    "url": "data:application/json," + _json.dumps(params),
                },
                "model": {
                    "url": f3d_oss_url,
                    "headers": {"Authorization": f"Bearer {token}"},
                    "verb": "get",
                },
                "result": {
                    "url": f"{APS_OSS_BASE}/buckets/{self._bucket}/objects/result_{{workItemId}}.step",
                    "headers": {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/octet-stream",
                    },
                    "verb": "put",
                },
            },
        }

        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"{APS_DA_BASE}/workitems",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["id"]

    async def poll_status(self, workitem_id: str) -> str:
        token = await self.get_token()
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{APS_DA_BASE}/workitems/{workitem_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()["status"]
