# Test_Konfig — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Funktionsfähigen Prototyp des Plattenkonfigurators (FLEX TABLE) bauen — Browser-Frontend → FastAPI → APS Fusion Automation → STEP-Download.

**Architecture:** FastAPI-Backend als APS-Gateway: nimmt Konfigurationsparameter entgegen, submitet ein APS Design Automation WorkItem mit der Fusion-Referenzdatei, pollt den Status und liefert die fertige STEP-Datei aus. Frontend ist eine einzige HTML-Datei mit Three.js CDN (kein Build-Step), Vanilla JS pollt den Status selbst.

**Tech Stack:** Python 3.11+, FastAPI, httpx (async), pytest + respx (Mocking), Vanilla HTML/CSS/JS, Three.js r169 via CDN, APS Design Automation v3, APS OSS v2, Git LFS für `.f3d`-Dateien.

---

## Dateistruktur

```
Test_Konfig/
├── frontend/
│   └── index.html                         # Gesamtes Frontend (Slider, Three.js, Polling)
├── backend/
│   ├── main.py                            # FastAPI App (3 Endpoints)
│   ├── aps_client.py                      # APS: Token, OSS, Design Automation
│   ├── aps_addin/
│   │   └── flex_table/
│   │       ├── flex_addin.py              # Fusion Add-In (headless)
│   │       ├── PackageContents.xml        # AppBundle-Manifest
│   │       └── params.example.json        # Beispiel-Parameter für Lokaltest
│   ├── scripts/
│   │   └── setup_aps.py                   # Einmalig: AppBundle + Activity registrieren
│   ├── tests/
│   │   ├── conftest.py                    # Fixtures (sys.path, workitem-Store reset)
│   │   ├── test_aps_client.py             # APSClient-Tests (respx-gemockt)
│   │   └── test_main.py                   # FastAPI-Endpoint-Tests (TestClient)
│   ├── .env.example                       # APS_CLIENT_ID, APS_CLIENT_SECRET
│   ├── pytest.ini                         # asyncio_mode = auto
│   └── requirements.txt
├── .gitattributes                         # LFS für *.f3d, *.f3z
└── README.md
```

---

## Task 1: Projekt-Scaffold

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/pytest.ini`
- Create: `.gitattributes`

- [ ] **Schritt 1: requirements.txt anlegen**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
httpx==0.27.0
python-dotenv==1.0.1
pytest==8.2.0
pytest-asyncio==0.23.7
respx==0.21.1
httpx==0.27.0
python-multipart==0.0.9
```

Datei speichern als `backend/requirements.txt`.

- [ ] **Schritt 2: .env.example anlegen**

```
APS_CLIENT_ID=deine_client_id_hier
APS_CLIENT_SECRET=dein_client_secret_hier
APS_BUCKET=test-konfig-flex
APS_APPBUNDLE_ALIAS=prod
APS_ACTIVITY_ALIAS=prod
```

Datei speichern als `backend/.env.example`.

- [ ] **Schritt 3: pytest.ini anlegen**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

Datei speichern als `backend/pytest.ini`.

- [ ] **Schritt 4: .gitattributes anlegen**

```
*.f3d filter=lfs diff=lfs merge=lfs -text
*.f3z filter=lfs diff=lfs merge=lfs -text
```

Datei speichern als `.gitattributes` (Repo-Root).

- [ ] **Schritt 5: Verzeichnisstruktur erstellen**

```bash
mkdir -p backend/aps_addin/flex_table
mkdir -p backend/scripts
mkdir -p backend/tests
mkdir -p frontend
```

- [ ] **Schritt 6: Leere `__init__.py` für Tests**

```bash
touch backend/__init__.py
touch backend/tests/__init__.py
```

- [ ] **Schritt 7: Dependencies installieren**

```bash
cd backend
pip install -r requirements.txt
```

Erwartete Ausgabe: alle Pakete installiert ohne Fehler.

- [ ] **Schritt 8: Commit**

```bash
git add .gitattributes backend/requirements.txt backend/.env.example backend/pytest.ini backend/__init__.py backend/tests/__init__.py
git commit -m "chore: project scaffold — requirements, pytest config, gitattributes"
```

---

## Task 2: APSClient — Token-Management

**Files:**
- Create: `backend/aps_client.py` (nur Token-Teil)
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_aps_client.py` (nur Token-Tests)

- [ ] **Schritt 1: Failing Test schreiben**

`backend/tests/conftest.py`:
```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("APS_CLIENT_ID", "test_id")
    monkeypatch.setenv("APS_CLIENT_SECRET", "test_secret")
    monkeypatch.setenv("APS_BUCKET", "test-bucket")
    monkeypatch.setenv("APS_APPBUNDLE_ALIAS", "prod")
    monkeypatch.setenv("APS_ACTIVITY_ALIAS", "prod")
```

`backend/tests/test_aps_client.py`:
```python
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
```

- [ ] **Schritt 2: Test ausführen — muss FAIL sein**

```bash
cd backend
pytest tests/test_aps_client.py -v
```

Erwartete Ausgabe: `ImportError: No module named 'aps_client'`

- [ ] **Schritt 3: APSClient mit Token-Logik implementieren**

`backend/aps_client.py`:
```python
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
```

- [ ] **Schritt 4: Test ausführen — muss PASS sein**

```bash
cd backend
pytest tests/test_aps_client.py -v
```

Erwartete Ausgabe: `2 passed`

- [ ] **Schritt 5: Commit**

```bash
git add backend/aps_client.py backend/tests/conftest.py backend/tests/test_aps_client.py
git commit -m "feat: APSClient token management with auto-refresh"
```

---

## Task 3: APSClient — OSS-Operationen

**Files:**
- Modify: `backend/aps_client.py` (OSS-Methoden hinzufügen)
- Modify: `backend/tests/test_aps_client.py` (OSS-Tests hinzufügen)

- [ ] **Schritt 1: Failing Tests schreiben**

An `backend/tests/test_aps_client.py` anhängen:

```python
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
```

- [ ] **Schritt 2: Tests ausführen — müssen FAIL sein**

```bash
cd backend
pytest tests/test_aps_client.py -v -k "oss or bucket or upload or download"
```

Erwartete Ausgabe: `AttributeError: 'APSClient' object has no attribute 'ensure_bucket'`

- [ ] **Schritt 3: OSS-Methoden implementieren**

An `backend/aps_client.py` anhängen (innerhalb der `APSClient`-Klasse):

```python
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
```

- [ ] **Schritt 4: Tests ausführen — müssen PASS sein**

```bash
cd backend
pytest tests/test_aps_client.py -v
```

Erwartete Ausgabe: `6 passed`

- [ ] **Schritt 5: Commit**

```bash
git add backend/aps_client.py backend/tests/test_aps_client.py
git commit -m "feat: APSClient OSS operations (ensure_bucket, upload, download)"
```

---

## Task 4: APSClient — Design Automation WorkItems

**Files:**
- Modify: `backend/aps_client.py` (DA-Methoden hinzufügen)
- Modify: `backend/tests/test_aps_client.py` (DA-Tests hinzufügen)

- [ ] **Schritt 1: Failing Tests schreiben**

An `backend/tests/test_aps_client.py` anhängen:

```python
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
```

- [ ] **Schritt 2: Tests ausführen — müssen FAIL sein**

```bash
cd backend
pytest tests/test_aps_client.py -v -k "workitem or poll"
```

Erwartete Ausgabe: `AttributeError: 'APSClient' object has no attribute 'submit_workitem'`

- [ ] **Schritt 3: DA-Methoden implementieren**

An `backend/aps_client.py` anhängen (innerhalb der `APSClient`-Klasse):

```python
    async def submit_workitem(self, params: dict, f3d_oss_url: str) -> str:
        token = await self.get_token()
        import json as _json

        activity_id = f"test-konfig.FlexTableActivity+{self._activity_alias}"
        output_object = f"result_{{workitem}}.step"

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
                    "url": f"{APS_OSS_BASE}/buckets/{self._bucket}/objects/result_{{{{workItemId}}}}.step",
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
```

- [ ] **Schritt 4: Tests ausführen — müssen PASS sein**

```bash
cd backend
pytest tests/test_aps_client.py -v
```

Erwartete Ausgabe: `9 passed`

- [ ] **Schritt 5: Commit**

```bash
git add backend/aps_client.py backend/tests/test_aps_client.py
git commit -m "feat: APSClient Design Automation WorkItem submit and poll"
```

---

## Task 5: Setup-Script (AppBundle + Activity — einmalig)

**Files:**
- Create: `backend/scripts/setup_aps.py`

Dieses Script wird **einmalig manuell** ausgeführt, bevor der erste echte WorkItem-Test läuft. Es braucht keine automatisierten Tests, da es direkte APS-Admin-Calls macht.

- [ ] **Schritt 1: setup_aps.py erstellen**

`backend/scripts/setup_aps.py`:
```python
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
        # AppBundle erstellen oder neue Version anlegen
        payload = {
            "id": BUNDLE_NAME,
            "engine": ENGINE,
            "description": "FLEX TABLE parametric step export",
        }
        resp = await http.post(f"{APS_DA_BASE}/appbundles", headers=headers, json=payload)
        if resp.status_code == 409:
            # Bereits vorhanden → neue Version
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

    # ZIP hochladen
    zip_path = zip_addin()
    async with httpx.AsyncClient() as http:
        with open(zip_path, "rb") as f:
            files = {**{k: (None, v) for k, v in form_data.items()}, "file": ("bundle.zip", f)}
            resp = await http.post(upload_url, files=files)
            resp.raise_for_status()
    os.unlink(zip_path)
    print("  AppBundle ZIP uploaded.")

    # Alias setzen
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
    print(f"  Alias '{BUNDLE_ALIAS}' → version {version}")
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
    print(f"  Alias '{ACTIVITY_ALIAS}' → version {version}")


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
```

- [ ] **Schritt 2: Script syntaktisch prüfen**

```bash
cd backend
python -c "import ast; ast.parse(open('scripts/setup_aps.py').read()); print('OK')"
```

Erwartete Ausgabe: `OK`

- [ ] **Schritt 3: Commit**

```bash
git add backend/scripts/setup_aps.py
git commit -m "feat: APS setup script for AppBundle and Activity registration"
```

---

## Task 6: Fusion Add-In (flex_addin.py)

**Files:**
- Create: `backend/aps_addin/flex_table/flex_addin.py`
- Create: `backend/aps_addin/flex_table/PackageContents.xml`
- Create: `backend/aps_addin/flex_table/params.example.json`

Dieser Code läuft im APS-Worker (headless Fusion) sowie lokal in Fusion 360. Kein pytest — der Test ist das manuelle Ausführen in Fusion.

- [ ] **Schritt 1: flex_addin.py erstellen**

`backend/aps_addin/flex_table/flex_addin.py`:
```python
"""
Fusion 360 Add-In: FLEX TABLE parametrische STEP-Exportierung.
Läuft headless im APS DA Worker und lokal in Fusion 360.

APS DA Worker legt bereit:
  - params.json  (workDir)
  - flex_reference.f3d  (workDir)
Erwartet als Output:
  - result.step  (workDir)

Lokaltest in Fusion:
  Werkzeuge → Skripts und Add-Ins → Add-Ins → "+" → diesen Ordner wählen → Run
"""
import adsk.core
import adsk.fusion
import json
import os
import traceback

PARAM_MAP = {
    "breite": "Breite",
    "tiefe": "Tiefe",
    "r_ecke": "R_Ecke",
    "r_kante": "R_Kante",
    "dicke": "Dicke",
}


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        work_dir = os.path.dirname(os.path.abspath(__file__))
        params_path = os.path.join(work_dir, "params.json")
        model_path = os.path.join(work_dir, "flex_reference.f3d")
        output_path = os.path.join(work_dir, "result.step")

        with open(params_path, "r") as f:
            params = json.load(f)

        params.setdefault("dicke", 28.6)

        import_mgr = app.importManager
        options = import_mgr.createFusionArchiveImportOptions(model_path)
        doc = import_mgr.importToNewDocument(options)
        doc.activate()

        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType

        user_params = design.userParameters
        for key, fusion_name in PARAM_MAP.items():
            value_mm = params.get(key)
            if value_mm is None:
                continue
            param = user_params.itemByName(fusion_name)
            if param is None:
                raise RuntimeError(f"User Parameter '{fusion_name}' nicht gefunden. Bitte im Modell anlegen.")
            param.expression = f"{value_mm} mm"

        export_mgr = design.exportManager
        step_options = export_mgr.createSTEPExportOptions(output_path)
        export_mgr.execute(step_options)

        doc.close(False)

    except Exception:
        if ui:
            ui.messageBox(f"flex_addin Fehler:\n{traceback.format_exc()}")
        raise
```

- [ ] **Schritt 2: PackageContents.xml erstellen**

`backend/aps_addin/flex_table/PackageContents.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0"
    Version="1.0"
    Id="{3A8F6E2C-1234-4B56-ABCD-FLEX00000001}"
    Description="FLEX TABLE STEP Exporter"
    Author="Flötotto"
    FriendlyName="FlexTable">
  <CompanyDetails Name="Flötotto" />
  <RuntimeRequirements OS="Win64" Platform="Fusion360" SeriesMin="2" SeriesMax="*" />
  <Components Description="FlexTable Add-In">
    <Addin Name="flex_addin" />
  </Components>
</ApplicationPackage>
```

- [ ] **Schritt 3: params.example.json erstellen**

`backend/aps_addin/flex_table/params.example.json`:
```json
{
  "breite": 1200,
  "tiefe": 600,
  "r_ecke": 0,
  "r_kante": 0,
  "dicke": 28.6
}
```

- [ ] **Schritt 4: Syntaxprüfung**

```bash
python -c "import ast; ast.parse(open('backend/aps_addin/flex_table/flex_addin.py').read()); print('OK')"
```

Erwartete Ausgabe: `OK`

- [ ] **Schritt 5: Commit**

```bash
git add backend/aps_addin/flex_table/
git commit -m "feat: Fusion Add-In flex_addin for FLEX TABLE headless STEP export"
```

---

## Task 7: FastAPI Endpoints

**Files:**
- Create: `backend/main.py`
- Create: `backend/tests/test_main.py`

- [ ] **Schritt 1: Failing Tests schreiben**

`backend/tests/test_main.py`:
```python
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
```

- [ ] **Schritt 2: Tests ausführen — müssen FAIL sein**

```bash
cd backend
pytest tests/test_main.py -v
```

Erwartete Ausgabe: `ImportError: No module named 'main'`

- [ ] **Schritt 3: conftest.py um workitem-Store-Reset erweitern**

In `backend/tests/conftest.py` hinzufügen:

```python
@pytest.fixture(autouse=True)
def clear_workitems():
    try:
        from main import _workitem_outputs
        _workitem_outputs.clear()
    except ImportError:
        pass
    yield
    try:
        from main import _workitem_outputs
        _workitem_outputs.clear()
    except ImportError:
        pass
```

- [ ] **Schritt 4: main.py implementieren**

`backend/main.py`:
```python
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from aps_client import APSClient

load_dotenv()

app = FastAPI(title="Test_Konfig APS Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

aps = APSClient()
_workitem_outputs: dict[str, str] = {}

F3D_PATH = str(
    Path(__file__).parent / "aps_addin" / "flex_table" / "flex_reference.f3d"
)


class PlateParams(BaseModel):
    breite: float = Field(..., ge=600, le=1800, description="Breite in mm")
    tiefe: float = Field(..., ge=400, le=900, description="Tiefe in mm")
    r_ecke: float = Field(..., ge=0, le=50, description="Eckenradius in mm")
    r_kante: float = Field(..., ge=0, le=5, description="Kantenradius in mm")


@app.post("/configure")
async def configure(params: PlateParams):
    await aps.ensure_bucket()
    f3d_url = await aps.upload_file(F3D_PATH, "flex_reference.f3d")

    payload = params.model_dump()
    payload["dicke"] = 28.6

    wi_id = await aps.submit_workitem(payload, f3d_url)
    _workitem_outputs[wi_id] = f"result_{wi_id}.step"
    return {"workItemId": wi_id}


@app.get("/status/{workitem_id}")
async def get_status(workitem_id: str):
    status = await aps.poll_status(workitem_id)
    return {"status": status}


@app.get("/download/{workitem_id}")
async def download(workitem_id: str):
    object_key = _workitem_outputs.get(workitem_id)
    if not object_key:
        raise HTTPException(status_code=404, detail="WorkItem nicht gefunden")
    data = await aps.download_file(object_key)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="flex_{workitem_id}.step"'},
    )
```

- [ ] **Schritt 5: Tests ausführen — müssen PASS sein**

```bash
cd backend
pytest tests/test_main.py -v
```

Erwartete Ausgabe: `5 passed`

- [ ] **Schritt 6: Alle Tests ausführen**

```bash
cd backend
pytest -v
```

Erwartete Ausgabe: `14 passed` (9 aus test_aps_client.py + 5 aus test_main.py)

- [ ] **Schritt 7: Commit**

```bash
git add backend/main.py backend/tests/test_main.py backend/tests/conftest.py
git commit -m "feat: FastAPI endpoints configure/status/download with full test suite"
```

---

## Task 8: Frontend (index.html)

**Files:**
- Create: `frontend/index.html`

Kein automatisierter Test — manuelles Testen im Browser (Schritt 4).

- [ ] **Schritt 1: index.html erstellen**

`frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>FLEX TABLE Konfigurator</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, sans-serif;
      background: #f5f5f5;
      color: #1a1a1a;
      height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: #1a1a1a;
      color: #fff;
      padding: 12px 24px;
      font-size: 14px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }
    main {
      display: grid;
      grid-template-columns: 320px 1fr;
      flex: 1;
      overflow: hidden;
    }
    .panel {
      background: #fff;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 20px;
      overflow-y: auto;
      border-right: 1px solid #e0e0e0;
    }
    .panel h2 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #666; }
    .field { display: flex; flex-direction: column; gap: 6px; }
    .field label { font-size: 13px; font-weight: 500; display: flex; justify-content: space-between; }
    .field label span { font-weight: 400; color: #555; }
    .field input[type=range] { width: 100%; accent-color: #1a1a1a; }
    .field input[type=number] {
      width: 80px;
      padding: 4px 8px;
      border: 1px solid #ccc;
      border-radius: 4px;
      font-size: 13px;
    }
    .row { display: flex; align-items: center; gap: 10px; }
    .row input[type=range] { flex: 1; }
    button {
      padding: 10px 16px;
      border: none;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.15s;
    }
    button:disabled { opacity: 0.4; cursor: not-allowed; }
    #btn-configure { background: #1a1a1a; color: #fff; }
    #btn-download { background: #2d7d46; color: #fff; }
    .status-area {
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 32px;
      font-size: 13px;
      color: #555;
    }
    .spinner {
      width: 18px; height: 18px;
      border: 2px solid #ccc;
      border-top-color: #1a1a1a;
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
      display: none;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .spinner.active { display: block; }
    #status-msg.error { color: #c0392b; }
    #status-msg.success { color: #2d7d46; }
    .preview {
      background: #e8e8e8;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    canvas { display: block; }
  </style>
</head>
<body>
  <header>FLEX TABLE — Konfigurator</header>
  <main>
    <div class="panel">
      <h2>Parameter</h2>

      <div class="field">
        <label>Breite <span id="lbl-breite">1200 mm</span></label>
        <div class="row">
          <input type="range" id="sl-breite" min="600" max="1800" step="10" value="1200" />
          <input type="number" id="in-breite" min="600" max="1800" step="10" value="1200" />
        </div>
      </div>

      <div class="field">
        <label>Tiefe <span id="lbl-tiefe">600 mm</span></label>
        <div class="row">
          <input type="range" id="sl-tiefe" min="400" max="900" step="10" value="600" />
          <input type="number" id="in-tiefe" min="400" max="900" step="10" value="600" />
        </div>
      </div>

      <div class="field">
        <label>Eckenradius <span id="lbl-recke">0 mm</span></label>
        <div class="row">
          <input type="range" id="sl-recke" min="0" max="50" step="1" value="0" />
          <input type="number" id="in-recke" min="0" max="50" step="1" value="0" />
        </div>
      </div>

      <div class="field">
        <label>Kantenradius <span id="lbl-rkante">0 mm</span></label>
        <div class="row">
          <input type="range" id="sl-rkante" min="0" max="5" step="0.5" value="0" />
          <input type="number" id="in-rkante" min="0" max="5" step="0.5" value="0" />
        </div>
      </div>

      <div class="status-area">
        <div class="spinner" id="spinner"></div>
        <span id="status-msg">Bereit</span>
      </div>

      <button id="btn-configure">Für CNC exportieren</button>
      <button id="btn-download" disabled>STEP herunterladen</button>
    </div>

    <div class="preview" id="preview"></div>
  </main>

  <script type="importmap">
    { "imports": { "three": "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js" } }
  </script>
  <script type="module">
    import * as THREE from 'three';

    // === Three.js Live-Vorschau ===
    const container = document.getElementById('preview');
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xe8e8e8);

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 10000);
    camera.position.set(800, 600, 1200);
    camera.lookAt(0, 0, 0);

    scene.add(new THREE.AmbientLight(0xffffff, 0.7));
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(1, 2, 1);
    scene.add(dirLight);

    const geo = new THREE.BoxGeometry(1, 1, 1);
    const mat = new THREE.MeshStandardMaterial({ color: 0xd4b896, roughness: 0.7 });
    const mesh = new THREE.Mesh(geo, mat);
    scene.add(mesh);

    function resize() {
      const w = container.clientWidth;
      const h = container.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
    resize();
    window.addEventListener('resize', resize);

    function updateMesh(breite, tiefe) {
      const DICKE = 28.6;
      mesh.scale.set(breite, DICKE, tiefe);
    }

    function animate() {
      requestAnimationFrame(animate);
      mesh.rotation.y += 0.003;
      renderer.render(scene, camera);
    }
    animate();

    // === Parameter-Kopplung ===
    function linkParam(slId, inId, lblId) {
      const sl = document.getElementById(slId);
      const inp = document.getElementById(inId);
      const lbl = document.getElementById(lblId);

      function sync(val) {
        sl.value = val;
        inp.value = val;
        lbl.textContent = val + ' mm';
        updateMesh(
          parseFloat(document.getElementById('sl-breite').value),
          parseFloat(document.getElementById('sl-tiefe').value)
        );
      }
      sl.addEventListener('input', () => sync(sl.value));
      inp.addEventListener('change', () => {
        const clamped = Math.min(Math.max(parseFloat(inp.value), parseFloat(inp.min)), parseFloat(inp.max));
        sync(clamped);
      });
    }

    linkParam('sl-breite', 'in-breite', 'lbl-breite');
    linkParam('sl-tiefe', 'in-tiefe', 'lbl-tiefe');
    linkParam('sl-recke', 'in-recke', 'lbl-recke');
    linkParam('sl-rkante', 'in-rkante', 'lbl-rkante');
    updateMesh(1200, 600);

    // === API-Calls ===
    const API = 'http://localhost:8000';
    let currentWorkItemId = null;
    let pollInterval = null;

    const btnConfigure = document.getElementById('btn-configure');
    const btnDownload = document.getElementById('btn-download');
    const spinner = document.getElementById('spinner');
    const statusMsg = document.getElementById('status-msg');

    function setStatus(text, cls) {
      statusMsg.textContent = text;
      statusMsg.className = cls || '';
    }

    btnConfigure.addEventListener('click', async () => {
      clearInterval(pollInterval);
      btnDownload.disabled = true;
      btnConfigure.disabled = true;
      spinner.classList.add('active');
      setStatus('Wird verarbeitet…');

      const params = {
        breite: parseFloat(document.getElementById('sl-breite').value),
        tiefe: parseFloat(document.getElementById('sl-tiefe').value),
        r_ecke: parseFloat(document.getElementById('sl-recke').value),
        r_kante: parseFloat(document.getElementById('sl-rkante').value),
      };

      try {
        const res = await fetch(`${API}/configure`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        currentWorkItemId = data.workItemId;
        pollStatus();
      } catch (e) {
        spinner.classList.remove('active');
        btnConfigure.disabled = false;
        setStatus('Fehler: ' + e.message, 'error');
      }
    });

    function pollStatus() {
      pollInterval = setInterval(async () => {
        try {
          const res = await fetch(`${API}/status/${currentWorkItemId}`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const { status } = await res.json();

          if (status === 'succeeded') {
            clearInterval(pollInterval);
            spinner.classList.remove('active');
            btnConfigure.disabled = false;
            btnDownload.disabled = false;
            setStatus('Fertig — STEP bereit.', 'success');
          } else if (status === 'failed') {
            clearInterval(pollInterval);
            spinner.classList.remove('active');
            btnConfigure.disabled = false;
            setStatus('Fehler bei der Verarbeitung.', 'error');
          }
          // pending / inProgress → weiter pollen
        } catch (e) {
          clearInterval(pollInterval);
          spinner.classList.remove('active');
          btnConfigure.disabled = false;
          setStatus('Polling-Fehler: ' + e.message, 'error');
        }
      }, 2000);
    }

    btnDownload.addEventListener('click', async () => {
      if (!currentWorkItemId) return;
      const res = await fetch(`${API}/download/${currentWorkItemId}`);
      if (!res.ok) { setStatus('Download fehlgeschlagen.', 'error'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `flex_${currentWorkItemId}.step`;
      a.click();
      URL.revokeObjectURL(url);
    });
  </script>
</body>
</html>
```

- [ ] **Schritt 2: Frontend manuell im Browser testen**

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Browser öffnen: `frontend/index.html` als Datei öffnen (oder `python -m http.server 3000` im `frontend/`-Ordner).

Prüfen:
- [ ] Slider und Zahleneingabe sind gekoppelt (beide ändern sich zusammen)
- [ ] Three.js-Box skaliert live bei Slider-Bewegung
- [ ] "Für CNC exportieren" zeigt Spinner (auch ohne echtes Backend → Fehlermeldung erwartet)
- [ ] Fehlermeldung erscheint wenn Backend nicht erreichbar

- [ ] **Schritt 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: Vanilla HTML frontend with Three.js live preview and APS polling"
```

---

## Task 9: README + Push

**Files:**
- Create: `README.md`

- [ ] **Schritt 1: README erstellen**

`README.md`:
```markdown
# Test_Konfig — FLEX TABLE Prototyp

Plattenkonfigurator-Prototyp: Browser-Frontend → FastAPI → APS Fusion Automation → STEP-Download.

## Voraussetzungen

1. Python 3.11+
2. APS-App mit 2-legged OAuth (Client-ID + Secret)
3. Fusion 360 mit User Parameters `Breite`, `Tiefe`, `R_Ecke`, `R_Kante`, `Dicke` im Referenzmodell

## Setup

```bash
cd backend
cp .env.example .env
# .env mit echten APS_CLIENT_ID / APS_CLIENT_SECRET befüllen

pip install -r requirements.txt
```

## Einmalig: APS registrieren

Fusion Add-In-Ordner (`backend/aps_addin/flex_table/`) muss `flex_reference.f3d` enthalten.

```bash
cd backend
python scripts/setup_aps.py
```

## Backend starten

```bash
cd backend
uvicorn main:app --reload --port 8000
```

## Frontend öffnen

```bash
cd frontend
python -m http.server 3000
# Browser: http://localhost:3000
```

## Tests

```bash
cd backend
pytest -v
```

## Parameter (FLEX TABLE)

| Parameter  | Min  | Max  | Default | Einheit |
|------------|------|------|---------|---------|
| breite     | 600  | 1800 | 1200    | mm      |
| tiefe      | 400  | 900  | 600     | mm      |
| r_ecke     | 0    | 50   | 0       | mm      |
| r_kante    | 0    | 5    | 0       | mm      |
| dicke      | —    | —    | 28.6    | mm      |
```

- [ ] **Schritt 2: Alle Tests final ausführen**

```bash
cd backend
pytest -v
```

Erwartete Ausgabe: `14 passed`

- [ ] **Schritt 3: Commit**

```bash
git add README.md
git commit -m "docs: README with setup instructions"
```

- [ ] **Schritt 4: GitHub Remote anlegen und pushen**

```bash
# GitHub Repo "Test_Konfig" unter mirkothepirko anlegen (einmalig via gh CLI):
gh repo create mirkothepirko/Test_Konfig --public --source=. --remote=origin --push
```

Falls das Repo bereits existiert:
```bash
git remote add origin https://github.com/mirkothepirko/Test_Konfig.git
git push -u origin master
```

Erwartete Ausgabe: alle Commits auf GitHub sichtbar.

---

## Spec-Abdeckungs-Check

| Spec-Anforderung | Implementiert in |
|---|---|
| POST /configure → WorkItem starten | Task 7 (main.py) |
| GET /status/{id} → Status | Task 7 (main.py) |
| GET /download/{id} → STEP | Task 7 (main.py) |
| 2-legged Token + Auto-Refresh | Task 2 (aps_client.py) |
| OSS Bucket + Upload | Task 3 (aps_client.py) |
| WorkItem submit + poll | Task 4 (aps_client.py) |
| AppBundle + Activity registrieren | Task 5 (setup_aps.py) |
| Fusion Add-In headless | Task 6 (flex_addin.py) |
| Slider + Zahleneingabe gekoppelt | Task 8 (index.html) |
| Three.js Live-Vorschau | Task 8 (index.html) |
| Spinner statt Fortschrittsbalken | Task 8 (index.html) |
| Parameter-Validierung (Pydantic) | Task 7 (main.py PlateParams) |
| FLEX TABLE Parameter-Grenzen | Task 7 + Task 8 |
| .gitattributes LFS | Task 1 |
| kein Build-Step Frontend | Task 8 (CDN) |
