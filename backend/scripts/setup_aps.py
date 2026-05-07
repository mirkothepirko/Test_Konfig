"""
Einmalig ausführen: registriert AppBundle + Activity in APS Design Automation.
Voraussetzung: backend/aps_addin/flex_table/ ist vollständig (Task 6 zuerst ausführen).
Aufruf: python scripts/setup_aps.py
"""
import asyncio
import os
import zipfile
import tempfile
import httpx
from dotenv import load_dotenv

load_dotenv()

APS_AUTH_URL = "https://developer.api.autodesk.com/authentication/v2/token"
APS_DA_BASE = "https://developer.api.autodesk.com/da/us-east/v3"

CLIENT_ID = os.environ["APS_CLIENT_ID"]
CLIENT_SECRET = os.environ["APS_CLIENT_SECRET"]
BUNDLE_ALIAS = os.environ.get("APS_APPBUNDLE_ALIAS", "prod")
ACTIVITY_ALIAS = os.environ.get("APS_ACTIVITY_ALIAS", "prod")
BUCKET = os.environ["APS_BUCKET"]
ENGINE = "Autodesk.Fusion+2701_00"
BUNDLE_NAME = "FlexTableBundle"
ACTIVITY_NAME = "FlexTableActivity"
OWNER = "test-konfig"


async def get_token() -> str:
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            APS_AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "scope": "code:all data:read data:write data:create bucket:read bucket:create",
            },
            auth=(CLIENT_ID, CLIENT_SECRET),
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def zip_addin() -> str:
    addin_dir = os.path.join(os.path.dirname(__file__), "..", "aps_addin", "flex_table")
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(addin_dir):
            for fname in files:
                full = os.path.join(root, fname)
                arcname = os.path.relpath(full, addin_dir)
                zf.write(full, arcname)
    return tmp.name


async def register_appbundle(token: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as http:
        payload = {
            "id": BUNDLE_NAME,
            "engine": ENGINE,
            "description": "FLEX TABLE parametric step export",
        }
        resp = await http.post(f"{APS_DA_BASE}/appbundles", headers=headers, json=payload)
        if resp.status_code == 409:
            resp = await http.post(
                f"{APS_DA_BASE}/appbundles/{BUNDLE_NAME}/versions",
                headers=headers,
                json={"engine": ENGINE, "description": "update"},
            )
        resp.raise_for_status()
        body = resp.json()
        upload_url = body["uploadParameters"]["endpointURL"]
        form_data = body["uploadParameters"]["formData"]
        version = body["version"]
        print(f"  AppBundle version: {version}")

    zip_path = zip_addin()
    async with httpx.AsyncClient() as http:
        with open(zip_path, "rb") as f:
            files = {**{k: (None, v) for k, v in form_data.items()}, "file": ("bundle.zip", f)}
            resp = await http.post(upload_url, files=files)
            resp.raise_for_status()
    os.unlink(zip_path)
    print("  AppBundle ZIP uploaded.")

    async with httpx.AsyncClient() as http:
        alias_resp = await http.post(
            f"{APS_DA_BASE}/appbundles/{BUNDLE_NAME}/aliases",
            headers=headers,
            json={"id": BUNDLE_ALIAS, "version": version},
        )
        if alias_resp.status_code == 409:
            alias_resp = await http.patch(
                f"{APS_DA_BASE}/appbundles/{BUNDLE_NAME}/aliases/{BUNDLE_ALIAS}",
                headers=headers,
                json={"version": version},
            )
        alias_resp.raise_for_status()
    print(f"  Alias '{BUNDLE_ALIAS}' -> version {version}")
    return f"{OWNER}.{BUNDLE_NAME}+{BUNDLE_ALIAS}"


async def register_activity(token: str, bundle_ref: str):
    headers = {"Authorization": f"Bearer {token}"}
    activity = {
        "id": ACTIVITY_NAME,
        "appbundles": [bundle_ref],
        "engine": ENGINE,
        "parameters": {
            "params": {"description": "JSON parameter input", "localName": "params.json", "verb": "get", "required": True},
            "model": {"description": "Fusion reference model", "localName": "flex_reference.f3d", "verb": "get", "required": True},
            "result": {"description": "STEP output", "localName": "result.step", "verb": "put", "required": True},
        },
        "commandLine": [
            "$(engine.path)\\FusionDA.exe",
            "--script",
            "$(appbundles[FlexTableBundle].path)\\flex_addin.py",
        ],
    }
    async with httpx.AsyncClient() as http:
        resp = await http.post(f"{APS_DA_BASE}/activities", headers=headers, json=activity)
        if resp.status_code == 409:
            resp = await http.post(
                f"{APS_DA_BASE}/activities/{ACTIVITY_NAME}/versions",
                headers=headers,
                json=activity,
            )
        resp.raise_for_status()
        version = resp.json()["version"]
        print(f"  Activity version: {version}")

        alias_resp = await http.post(
            f"{APS_DA_BASE}/activities/{ACTIVITY_NAME}/aliases",
            headers=headers,
            json={"id": ACTIVITY_ALIAS, "version": version},
        )
        if alias_resp.status_code == 409:
            alias_resp = await http.patch(
                f"{APS_DA_BASE}/activities/{ACTIVITY_NAME}/aliases/{ACTIVITY_ALIAS}",
                headers=headers,
                json={"version": version},
            )
        alias_resp.raise_for_status()
    print(f"  Alias '{ACTIVITY_ALIAS}' -> version {version}")


async def main():
    print("APS Design Automation Setup")
    print("============================")
    token = await get_token()
    print("Token OK")

    print(f"\nRegistering AppBundle '{BUNDLE_NAME}'...")
    bundle_ref = await register_appbundle(token)
    print(f"  Ref: {bundle_ref}")

    print(f"\nRegistering Activity '{ACTIVITY_NAME}'...")
    await register_activity(token, bundle_ref)

    print("\nDone. APS is ready.")


if __name__ == "__main__":
    asyncio.run(main())
