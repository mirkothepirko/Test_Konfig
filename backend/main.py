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
    aps = APSClient()
    await aps.ensure_bucket()
    f3d_url = await aps.upload_file(F3D_PATH, "flex_reference.f3d")

    payload = params.model_dump()
    payload["dicke"] = 28.6

    wi_id = await aps.submit_workitem(payload, f3d_url)
    _workitem_outputs[wi_id] = f"result_{wi_id}.step"
    return {"workItemId": wi_id}


@app.get("/status/{workitem_id}")
async def get_status(workitem_id: str):
    aps = APSClient()
    status = await aps.poll_status(workitem_id)
    return {"status": status}


@app.get("/download/{workitem_id}")
async def download(workitem_id: str):
    object_key = _workitem_outputs.get(workitem_id)
    if not object_key:
        raise HTTPException(status_code=404, detail="WorkItem nicht gefunden")
    aps = APSClient()
    data = await aps.download_file(object_key)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="flex_{workitem_id}.step"'},
    )
