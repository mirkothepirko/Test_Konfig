import json as _json
import time
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

APS_AUTH_URL = "https://developer.api.autodesk.com/authentication/v2/token"
APS_OSS_BASE = "https://developer.api.autodesk.com/oss/v2"
APS_DA_BASE = "https://developer.api.autodesk.com/da/us-east/v3"

SIGNED_URL_MINUTES = 60


class APSClient:
    def __init__(self):
        self._client_id = os.environ["APS_CLIENT_ID"]
        self._client_secret = os.environ["APS_CLIENT_SECRET"]
        self._bucket = os.environ["APS_BUCKET"]
        self._appbundle_alias = os.environ.get("APS_APPBUNDLE_ALIAS", "prod")
        self._activity_alias = os.environ.get("APS_ACTIVITY_ALIAS", "prod")
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._owner: str | None = None

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
        """Signed-S3 upload: init -> PUT to S3 -> finalize. Returns object_key."""
        token = await self.get_token()
        with open(local_path, "rb") as f:
            data = f.read()
        async with httpx.AsyncClient() as http:
            init = await http.get(
                f"{APS_OSS_BASE}/buckets/{self._bucket}/objects/{object_key}/signeds3upload",
                params={"minutesExpiration": SIGNED_URL_MINUTES},
                headers={"Authorization": f"Bearer {token}"},
            )
            init.raise_for_status()
            body = init.json()
            upload_key = body["uploadKey"]
            s3_url = body["urls"][0]

            put = await http.put(s3_url, content=data)
            put.raise_for_status()

            finalize = await http.post(
                f"{APS_OSS_BASE}/buckets/{self._bucket}/objects/{object_key}/signeds3upload",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"uploadKey": upload_key},
            )
            finalize.raise_for_status()
        return object_key

    async def get_signed_download(self, object_key: str) -> str:
        token = await self.get_token()
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{APS_OSS_BASE}/buckets/{self._bucket}/objects/{object_key}/signeds3download",
                params={"minutesExpiration": SIGNED_URL_MINUTES},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()["url"]

    async def init_signed_upload(self, object_key: str) -> tuple[str, str]:
        """Init signed S3 upload, returns (uploadKey, presigned_put_url)."""
        token = await self.get_token()
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{APS_OSS_BASE}/buckets/{self._bucket}/objects/{object_key}/signeds3upload",
                params={"minutesExpiration": SIGNED_URL_MINUTES},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            body = resp.json()
            return body["uploadKey"], body["urls"][0]

    async def finalize_upload(self, object_key: str, upload_key: str) -> None:
        token = await self.get_token()
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"{APS_OSS_BASE}/buckets/{self._bucket}/objects/{object_key}/signeds3upload",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"uploadKey": upload_key},
            )
            resp.raise_for_status()

    async def download_file(self, object_key: str) -> bytes:
        signed = await self.get_signed_download(object_key)
        async with httpx.AsyncClient() as http:
            resp = await http.get(signed)
            resp.raise_for_status()
            return resp.content

    async def get_owner(self) -> str:
        """Owner string for namespacing AppBundles/Activities. Equals the
        APS app nickname if set, otherwise the raw client_id."""
        if self._owner:
            return self._owner
        token = await self.get_token()
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{APS_DA_BASE}/forgeapps/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            self._owner = resp.json()
            return self._owner

    async def submit_workitem(
        self,
        params: dict,
        model_signed_get_url: str,
        result_signed_put_url: str,
    ) -> str:
        token = await self.get_token()
        owner = await self.get_owner()
        activity_id = f"{owner}.FlexTableActivity+{self._activity_alias}"

        payload = {
            "activityId": activity_id,
            "arguments": {
                "params": {
                    "url": "data:application/json," + _json.dumps(params),
                },
                "model": {
                    "url": model_signed_get_url,
                    "verb": "get",
                },
                "result": {
                    "url": result_signed_put_url,
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
