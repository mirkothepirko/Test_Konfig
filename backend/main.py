import json
import os
import uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import httpx
from aps_client import APSClient

load_dotenv()

app = FastAPI(title="Test_Konfig APS Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# wi_id -> {"object_key": str, "upload_key": str, "finalized": bool}
_workitem_outputs: dict[str, dict] = {}

F3D_PATH = str(
    Path(__file__).parent / "aps_addin" / "flex_table" / "flex_reference.f3d"
)
FEATURES_JSON = Path(__file__).parent / "aps_addin" / "flex_table" / "features.json"
VARIANTS_JSON = Path(__file__).parent / "aps_addin" / "flex_table" / "variants.json"


class PlateParams(BaseModel):
    breite: float = Field(..., ge=600, le=1800, description="Breite in mm")
    tiefe: float = Field(..., ge=400, le=900, description="Tiefe in mm")
    r_ecke: float = Field(..., ge=0, le=50, description="Eckenradius in mm")
    r_kante: float = Field(..., ge=0, le=5, description="Kantenradius in mm")
    variant: str | None = Field(None, description="ID einer Variante aus variants.json")


@app.get("/features")
async def get_features():
    """Liefert Hole-Features aus der .f3d-Referenz + Varianten-Konfiguration
    für das Frontend-Preview."""
    if not FEATURES_JSON.exists():
        raise HTTPException(status_code=404, detail="features.json fehlt — bitte dump_fusion_features.py in Fusion ausführen.")
    with open(FEATURES_JSON, "r", encoding="utf-8") as f:
        features = json.load(f)
    variants = {"default_variant": None, "variants": []}
    if VARIANTS_JSON.exists():
        with open(VARIANTS_JSON, "r", encoding="utf-8") as f:
            variants = json.load(f)
    return {"features": features, "variants": variants}


@app.post("/configure")
async def configure(params: PlateParams):
    aps = APSClient()
    await aps.ensure_bucket()
    await aps.upload_file(F3D_PATH, "flex_reference.f3d")
    model_url = await aps.get_signed_download("flex_reference.f3d")

    result_key = f"result_{uuid.uuid4().hex}.step"
    upload_key, result_put_url = await aps.init_signed_upload(result_key)

    payload = params.model_dump()
    payload["dicke"] = 28.6

    wi_id = await aps.submit_workitem(payload, model_url, result_put_url)
    _workitem_outputs[wi_id] = {
        "object_key": result_key,
        "upload_key": upload_key,
        "finalized": False,
    }
    return {"workItemId": wi_id}


@app.get("/status/{workitem_id}")
async def get_status(workitem_id: str):
    aps = APSClient()
    status = await aps.poll_status(workitem_id)
    return {"status": status}


@app.get("/download/{workitem_id}")
async def download(workitem_id: str):
    entry = _workitem_outputs.get(workitem_id)
    if not entry:
        raise HTTPException(status_code=404, detail="WorkItem nicht gefunden")
    aps = APSClient()
    if not entry["finalized"]:
        try:
            await aps.finalize_upload(entry["object_key"], entry["upload_key"])
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Finalize fehlgeschlagen: {e.response.status_code} {e.response.text[:200]}",
            )
        entry["finalized"] = True
    data = await aps.download_file(entry["object_key"])
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="flex_{workitem_id}.step"'},
    )
