from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import httpx
from datetime import datetime
import logging, os
from auth import get_current_user, UserInDB

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

router = APIRouter(prefix="/api/modelos", tags=["modelos"])

class EstadoModelos(BaseModel):
    ingresos_netos: float
    gastos_deducibles: float
    rendimiento_neto: float
    resultado_irpf: float
    ventas_nacionales_iva: float
    iva_repercutido: float
    entregas_intracomunitarias: float
    casilla_60: float
    adquisiciones_intracomunitarias: float
    servicios_intracomunitarios: float
    servicios_extracomunitarios: float
    importaciones_duas: float
    gastos_nacionales_iva: float

@router.get("/estado", response_model=EstadoModelos)
async def get_estado_modelos(current_user: UserInDB = Depends(get_current_user)):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    async with httpx.AsyncClient() as client:
        # Aquí deberías consultar y calcular cada campo según tus tablas y lógica
        # Por ahora, se devuelven valores dummy
        return EstadoModelos(
            ingresos_netos=10000,
            gastos_deducibles=2000,
            rendimiento_neto=8000,
            resultado_irpf=1200,
            ventas_nacionales_iva=9000,
            iva_repercutido=1890,
            entregas_intracomunitarias=0,
            casilla_60=0,
            adquisiciones_intracomunitarias=0,
            servicios_intracomunitarios=0,
            servicios_extracomunitarios=0,
            importaciones_duas=0,
            gastos_nacionales_iva=1500
        )
