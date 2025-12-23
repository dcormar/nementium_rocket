import httpx
import logging, os
from fastapi import APIRouter, HTTPException, Query, Depends, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional
from auth import get_current_user, UserInDB
from datetime import datetime
import certifi

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/facturas", tags=["facturas"])

class Factura(BaseModel):
    id: Optional[int]
    fecha: str
    proveedor: str
    #total: Optional[float] = None
    importe_sin_iva_euro: float
    importe_total_euro: float
    pais_origen: str
    ubicacion_factura: str

class FacturaManual(BaseModel):
    fecha: str
    fecha_dt: Optional[str] = None
    proveedor: str
    supplier_vat_number: Optional[str] = None
    importe_sin_iva_local: Optional[float] = None
    iva_local: Optional[float] = None
    total_moneda_local: Optional[float] = None
    moneda: Optional[str] = "EUR"
    tarifa_cambio: Optional[float] = None
    importe_sin_iva_euro: Optional[float] = None
    importe_total_euro: Optional[float] = None
    pais_origen: Optional[str] = "ES"
    id_ext: Optional[str] = None
    notas: Optional[str] = None
    descripcion: Optional[str] = None
    categoria: Optional[str] = None

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

@router.post("/manual", status_code=201)
async def add_factura_manual(
    fecha: str = Form(...),
    fecha_dt: Optional[str] = Form(None),
    proveedor: str = Form(...),
    supplier_vat_number: Optional[str] = Form(None),
    importe_sin_iva_local: Optional[str] = Form(None),
    iva_local: Optional[str] = Form(None),
    total_moneda_local: Optional[str] = Form(None),
    moneda: Optional[str] = Form("EUR"),
    tarifa_cambio: Optional[str] = Form(None),
    importe_sin_iva_euro: Optional[str] = Form(None),
    importe_total_euro: Optional[str] = Form(None),
    pais_origen: Optional[str] = Form("ES"),
    id_ext: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    descripcion: Optional[str] = Form(None),
    categoria: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Endpoint para añadir una factura manualmente.
    Si se proporciona un archivo, se sube primero con iaprocess: false y luego se guarda la factura.
    """
    from upload_api import get_upload_base, sanitize_folder, sha256_file, post_to_n8n, insert_automation_record
    from pathlib import Path
    import re, shutil, hashlib
    
    upload_id = None
    
    # Función helper para convertir string a float
    def parse_float(s: Optional[str]) -> Optional[float]:
        if not s or s.strip() == "":
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None
    
    # Procesar fecha: convertir de YYYY-MM-DD a YYYY/MM/DD para el campo fecha (texto)
    # y a formato datetime ISO (YYYY-MM-DD) para fecha_dt
    # fecha_dt es la misma que fecha pero en formato datetime
    fecha_text = None
    fecha_dt_iso = None
    
    if fecha:
        fecha = fecha.strip()
        try:
            # Intentar parsear como YYYY-MM-DD (formato del input date)
            dt = datetime.strptime(fecha, "%Y-%m-%d")
            # Convertir a YYYY/MM/DD para el campo fecha (texto)
            fecha_text = dt.strftime("%Y/%m/%d")
            # Convertir a formato ISO (YYYY-MM-DD) para fecha_dt (datetime)
            fecha_dt_iso = dt.date().isoformat()
        except ValueError:
            # Si no es YYYY-MM-DD, intentar YYYY/MM/DD
            try:
                dt = datetime.strptime(fecha, "%Y/%m/%d")
                fecha_text = dt.strftime("%Y/%m/%d")
                fecha_dt_iso = dt.date().isoformat()
            except ValueError:
                # Si no se puede parsear, usar el valor original para fecha_text
                # y dejar fecha_dt_iso como None
                fecha_text = fecha
                fecha_dt_iso = None
    
    # Preparar datos para insertar en facturas
    factura_row = {
        "fecha": fecha_text,
        "fecha_dt": fecha_dt_iso,
        "proveedor": proveedor,
        "supplier_vat_number": supplier_vat_number if supplier_vat_number and supplier_vat_number.strip() else None,
        "importe_sin_iva_local": parse_float(importe_sin_iva_local),
        "iva_local": parse_float(iva_local),
        "total_moneda_local": parse_float(total_moneda_local),
        "moneda": moneda or "EUR",
        "tarifa_cambio": parse_float(tarifa_cambio),
        "importe_sin_iva_euro": parse_float(importe_sin_iva_euro),
        "importe_total_euro": parse_float(importe_total_euro),
        "pais_origen": pais_origen or "ES",
        "id_ext": id_ext if id_ext and id_ext.strip() else None,
        "notas": notas if notas and notas.strip() else None,
        "descripcion": descripcion if descripcion and descripcion.strip() else "Añadida manualmente",
        "categoria": categoria if categoria and categoria.strip() else None,
    }
    
    # Eliminar None values
    factura_row = {k: v for k, v in factura_row.items() if v is not None}
    
    # Insertar en facturas
    url = f"{SUPABASE_URL}/rest/v1/facturas?on_conflict=id_ext_compound"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=representation"
    }
    
    try:
        async with httpx.AsyncClient(timeout=20, verify=certifi.where()) as client:
            resp = await client.post(url, headers=headers, json=factura_row)
    except httpx.RequestError as e:
        logger.exception("Error de red con Supabase (facturas)")
        raise HTTPException(status_code=502, detail=f"Error de red con Supabase: {e}") from e
    
    if resp.status_code not in (200, 201):
        logger.error("Upsert factura falló %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail=f"Error insertando/actualizando factura: {resp.text}")
    
    db_row = resp.json()[0] if isinstance(resp.json(), list) and resp.json() else resp.json()
    factura_id = db_row.get("id")
     # Si hay archivo, subirlo lo ultimo con iaprocess: false
    if file:
        try:
            base = get_upload_base()
            base.mkdir(parents=True, exist_ok=True)
            user_folder = base / sanitize_folder(current_user.username) / "factura"
            user_folder.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^\w\-.]+", "_", file.filename or "file")
            dest_file = user_folder / safe_name
            
            # Guardar archivo
            with dest_file.open("wb") as out:
                shutil.copyfileobj(file.file, out)
            
            size_bytes = dest_file.stat().st_size
            fname_lower = (file.filename or "").lower()
            mime_type = file.content_type or ("application/pdf" if fname_lower.endswith(".pdf") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            sha256 = sha256_file(dest_file)
            storage_path = str(dest_file)
            
            # Insertar en uploads
            async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
                payload = {
                    "tipo": "FACTURA",
                    "status": "UPLOADED",
                    "original_filename": safe_name,
                    "storage_path": storage_path,
                    "mime_type": mime_type,
                    "file_size_bytes": size_bytes,
                    "sha256": sha256,
                    "source": "manual",
                    "factura_id": factura_id,
                    "manual": True,
                }
                resp = await client.post(
                    f"{SUPABASE_URL}/rest/v1/uploads",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation",
                    },
                    json=payload
                )
                
                if resp.status_code not in (200, 201):
                    raise HTTPException(status_code=502, detail=f"Error insertando metadatos: {resp.text}")
                
                db_row = resp.json()[0] if isinstance(resp.json(), list) and resp.json() else resp.json()
                upload_id = db_row.get("id")
            
            # Insertar registro en automations
            await insert_automation_record("factura")
            
            # Llamar a n8n con iaprocess: false
            n8n_payload = {
                "tipo": "factura",
                "storage": "local",
                "user": current_user.username,
                "filename": safe_name,
                "upload_id": upload_id,
                "iaprocess": False,
            }
            status, text = await post_to_n8n(n8n_payload)
            if status >= 300:
                logger.error("Webhook n8n devolvió %s: %s", status, text)
                # Marcar como FAILED
                async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
                    await client.patch(
                        f"{SUPABASE_URL}/rest/v1/uploads?id=eq.{upload_id}",
                        headers={
                            "apikey": SUPABASE_KEY,
                            "Authorization": f"Bearer {SUPABASE_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={"status": "FAILED", "meta": {"n8n_error": text[:200]}}
                    )
        except Exception as e:
            logger.exception("Error subiendo archivo manual: %s", e)
            # Continuar sin archivo si falla la subida
    


    body = resp.json()
    factura_created = body[0] if isinstance(body, list) and body else body
    
    return {
        "ok": True,
        "factura": factura_created,
        "upload_id": upload_id,
    }
