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
