# app/routes/dashboard.py
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List
from decimal import Decimal
import os
import httpx
import logging
from auth import get_current_user, UserInDB

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)

class MesResumen(BaseModel):
    anio: int
    mes: int
    ventas_mes: float
    gastos_mes: float
    facturas_trimestre: int

class DashboardResponse(BaseModel):
    ultimos_seis_meses: List[MesResumen]

def _to_float(x):
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(Decimal(str(x)))
    except Exception:
        return 0.0

@router.get("/", response_model=DashboardResponse)
async def get_dashboard(
    months: int = Query(6, ge=1, le=24),
    tz: str = Query("Europe/Madrid"),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Devuelve agregados de los últimos `months` meses listos para el dashboard.
    Llama al RPC `dashboard_ultimos_meses` en Supabase.
    """
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

    if not supabase_url or not supabase_key:
        logger.error("Faltan variables de entorno: SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY")
        raise HTTPException(status_code=500, detail="Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY")

    rpc_url = f"{supabase_url}/rest/v1/rpc/dashboard_ultimos_meses"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": "return=representation",
    }
    payload = {"p_meses": months, "p_tz": tz}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(rpc_url, headers=headers, json=payload)
    except httpx.RequestError as e:
        logger.exception("Error de red al llamar a Supabase")
        raise HTTPException(status_code=502, detail=f"Error de red al llamar a Supabase: {e}") from e

    if resp.status_code != 200:
        # Propaga el error del RPC para depurar en front/logs
        logger.error("RPC fallo %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail={"rpc_status": resp.status_code, "rpc_body": resp.text})

    rows = resp.json() or []
    logger.info("RPC dashboard_ultimos_meses devolvió %d filas (months=%d)", len(rows), months)
    if rows:
        logger.debug("Primera fila RPC: %s", rows[0])

    data = [
        MesResumen(
            anio=int(r.get("anio")),
            mes=int(r.get("mes")),
            ventas_mes=_to_float(r.get("ventas_mes")),
            gastos_mes=_to_float(r.get("gastos_mes")),
            facturas_trimestre=int(r.get("facturas_trimestre") or 0),
        )
        for r in rows
    ]
    return DashboardResponse(ultimos_seis_meses=data)


class HistoricoResponse(BaseModel):
    items: list[dict]  # o crea un modelo Operacion

@router.get("/historico", response_model=HistoricoResponse)
async def historico(limit: int = 10, current_user: UserInDB = Depends(get_current_user)):
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not supabase_url or not supabase_key:
        logger.error("Faltan variables de entorno: SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY")
        raise HTTPException(status_code=500, detail="Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY")
    
    rpc_url = f"{supabase_url}/rest/v1/rpc/dashboard_ultimas_ops"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": "return=representation",
    }
    payload = {"p_limit": limit, "p_tz": "Europe/Madrid"}

    try:
        #logger.info("URL enviado al RPC: %s", rpc_url)
        logger.info("Payload enviado al RPC: %s", payload)
        #logger.info("Payload enviado al RPC: %s", headers)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(rpc_url, headers=headers, json=payload)
        logger.info("Respuesta RPC %s: %s", resp.status_code, resp.text)
    except httpx.RequestError as e:
        logger.exception("Error de red al llamar a Supabase")
        raise HTTPException(status_code=502, detail=f"Error de red al llamar a Supabase: {e}") from e

    if resp.status_code != 200:
        # Propaga el error del RPC para depurar en front/logs
        logger.error("RPC fallo %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail={"rpc_status": resp.status_code, "rpc_body": resp.text})

    rows = resp.json() or []
    logger.info("RPC dashboard_historico devolvió %d filas (days=%d)", len(rows), limit)
    if rows:
        logger.debug("Primera fila RPC: %s", rows[0])
    # normalizamos nombres por si quieres usarlos como en el front:
    items = [
        {
            "tipo": r["tipo"],
            "fecha": r["fecha"],
            "descripcion": r["descripcion"],
            "importe_eur": float(r["importe_eur"] or 0),
        }
        for r in rows
    ]
    return {"items": items}