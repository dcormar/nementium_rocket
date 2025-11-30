import httpx
import logging, os
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/facturas", tags=["facturas"])

class Factura(BaseModel):
    id: Optional[int]
    fecha: str
    proveedor: str
    #total: Optional[float] = None
    importe_sin_iva_euro: float
    importe_total_euro: float
    pais_origen: str
    ubicacion_factura: str

@router.get("/", response_model=List[Factura])
async def get_facturas(
    desde: str = Query(None, description="Fecha inicio YYYY-MM-DD"),
    hasta: str = Query(None, description="Fecha fin YYYY-MM-DD")
):
    logger.debug(f"Recibida petición de facturas desde={desde} hasta={hasta}")
    url = f"{SUPABASE_URL}/rest/v1/facturas"
    params = []
    if desde:
        params.append(f"fecha_dt=gte.{desde}")
    if hasta:
        params.append(f"fecha_dt=lte.{hasta}")
    if params:
        url += '?' + '&'.join(params)
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    async with httpx.AsyncClient() as client:
        logger.debug(f"Consultando Supabase: {url}")
        r = await client.get(url, headers=headers)
        logger.debug(f"Respuesta Supabase status={r.status_code} body={r.text}")
        if r.status_code != 200:
            logger.error(f"Supabase error {r.status_code}: {r.text}")
            raise HTTPException(status_code=500, detail=f"Error consultando Supabase: {r.text}")
        data = r.json()
        logger.info(f"Facturas recuperadas: {data}")
        return data

@router.post("/", response_model=Factura)
async def add_factura(factura: Factura):
    url = f"{SUPABASE_URL}/rest/v1/facturas"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=factura.dict(exclude_unset=True))
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Error insertando en Supabase")
        return r.json()[0] if isinstance(r.json(), list) else r.json()
