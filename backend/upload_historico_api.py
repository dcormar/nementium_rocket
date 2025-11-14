from fastapi import APIRouter, HTTPException
import httpx, os, logging
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/api/uploads", tags=["uploads"])
logger = logging.getLogger(__name__)

class UploadItem(BaseModel):
    id: str
    fecha: str
    tipo: str
    descripcion: str
    tam_bytes: Optional[int]
    storage_path: Optional[str]
    status: Optional[str] = None
    original_filename: str

class UploadsResponse(BaseModel):
    items: List[UploadItem]

@router.get("/historico", response_model=UploadsResponse)
async def uploads_historico(limit: int = 20, tz: str = "Europe/Madrid"):
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not supabase_url or not supabase_key:
        raise HTTPException(status_code=500, detail="Config supabase incompleta")

    rpc_url = f"{supabase_url}/rest/v1/rpc/uploads_historico"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": "return=representation",
    }
    payload = {"p_limit": limit, "p_tz": tz}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(rpc_url, headers=headers, json=payload)

    if resp.status_code != 200:
        logger.error("📛 RPC uploads_historico falló %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail=resp.text)

    rows = resp.json() or []
    logger.info("📦 RPC uploads_historico devolvió %d filas", len(rows))
    if rows:
        logger.debug("🔍 Primera fila: %s", rows[0])
    return {
        "items": [
            {
                "id": r["id"],
                "fecha": r["fecha"],
                "tipo": r["tipo"],
                "descripcion": r["descripcion"] or "Pending Processing",
                "tam_bytes": r.get("tam_bytes"),
                "storage_path": r.get("storage_path"),
                "status": r.get("status"),
                "original_filename":r.get("original_filename"),
            }
            for r in rows
        ]
    }