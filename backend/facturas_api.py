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


def build_supabase_filters(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    proveedor: Optional[str] = None,
    pais_origen: Optional[str] = None,
    importe_min: Optional[float] = None,
    importe_max: Optional[float] = None,
    categoria: Optional[str] = None,
    moneda: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None
) -> List[str]:
    """
    Construye lista de parámetros de filtro para Supabase PostgREST.
    Retorna lista de strings en formato 'campo=operador.valor'
    
    Args:
        desde: Fecha inicio (YYYY-MM-DD) - usa operador gte
        hasta: Fecha fin (YYYY-MM-DD) - usa operador lte
        proveedor: Búsqueda parcial (ilike) - búsqueda case-insensitive
        pais_origen: Igualdad exacta (eq)
        importe_min: Importe mínimo (gte) sobre importe_total_euro
        importe_max: Importe máximo (lte) sobre importe_total_euro
        categoria: Igualdad exacta (eq)
        moneda: Igualdad exacta (eq)
        limit: Límite de resultados
        offset: Offset para paginación
    
    Returns:
        Lista de strings con parámetros de filtro para Supabase
    """
    params = []
    
    # Filtros de fecha
    if desde:
        params.append(f"fecha_dt=gte.{desde}")
    if hasta:
        params.append(f"fecha_dt=lte.{hasta}")
    
    # Filtro de proveedor (búsqueda parcial, case-insensitive)
    if proveedor and proveedor.strip():
        # Escapar caracteres especiales para URL
        proveedor_escaped = proveedor.strip().replace("%", "%25").replace("&", "%26")
        params.append(f"proveedor=ilike.*{proveedor_escaped}*")
    
    # Filtro de país (igualdad exacta)
    if pais_origen and pais_origen.strip():
        params.append(f"pais_origen=eq.{pais_origen.strip()}")
    
    # Filtros de importe
    if importe_min is not None:
        params.append(f"importe_total_euro=gte.{importe_min}")
    if importe_max is not None:
        params.append(f"importe_total_euro=lte.{importe_max}")
    
    # Filtro de categoría (igualdad exacta)
    if categoria and categoria.strip():
        params.append(f"categoria=eq.{categoria.strip()}")
    
    # Filtro de moneda (igualdad exacta)
    if moneda and moneda.strip():
        params.append(f"moneda=eq.{moneda.strip().upper()}")
    
    # Paginación
    if limit is not None:
        params.append(f"limit={limit}")
    if offset is not None:
        params.append(f"offset={offset}")
    
    return params

class Factura(BaseModel):
    id: Optional[int]
    fecha: str
    proveedor: str
    #total: Optional[float] = None
    importe_sin_iva_euro: Optional[float] = None
    importe_total_euro: Optional[float] = None
    pais_origen: Optional[str] = None
    ubicacion_factura: Optional[str] = None

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
    # Clasificación fiscal
    pais_factura: Optional[str] = None
    pais_ue: Optional[str] = None
    tipo_adquisicion: Optional[str] = None
    servicio_intracomunitario_sin_iva: Optional[str] = None
    servicio_extracomunitario_sin_iva: Optional[str] = None
    inversion_sujeto_pasivo: Optional[str] = None
    dua: Optional[str] = None
    gasto_nacional_iva_deducible: Optional[str] = None

@router.get("/", response_model=List[Factura])
async def get_facturas(
    desde: Optional[str] = Query(None, description="Fecha inicio YYYY-MM-DD"),
    hasta: Optional[str] = Query(None, description="Fecha fin YYYY-MM-DD"),
    proveedor: Optional[str] = Query(None, description="Filtrar por proveedor (búsqueda parcial)"),
    pais_origen: Optional[str] = Query(None, description="Filtrar por país de origen"),
    importe_min: Optional[float] = Query(None, description="Importe mínimo en EUR"),
    importe_max: Optional[float] = Query(None, description="Importe máximo en EUR"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    moneda: Optional[str] = Query(None, description="Filtrar por moneda"),
    limit: Optional[int] = Query(None, description="Límite de resultados (máx 1000)", ge=1, le=1000),
    offset: Optional[int] = Query(None, description="Offset para paginación", ge=0),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Obtiene facturas con múltiples filtros opcionales.
    Mantiene compatibilidad: si solo se pasan desde/hasta, funciona igual que antes.
    """
    logger.debug(f"Recibida petición de facturas - desde={desde}, hasta={hasta}, proveedor={proveedor}, "
                 f"pais_origen={pais_origen}, importe_min={importe_min}, importe_max={importe_max}, "
                 f"categoria={categoria}, moneda={moneda}, limit={limit}, offset={offset}")
    
    # Validaciones
    if importe_min is not None and importe_min < 0:
        raise HTTPException(
            status_code=400,
            detail=f"importe_min debe ser mayor o igual a 0, se recibió: {importe_min}"
        )
    
    if importe_max is not None and importe_max < 0:
        raise HTTPException(
            status_code=400,
            detail=f"importe_max debe ser mayor o igual a 0, se recibió: {importe_max}"
        )
    
    if importe_min is not None and importe_max is not None:
        if importe_min > importe_max:
            raise HTTPException(
                status_code=400,
                detail=f"importe_min ({importe_min}) no puede ser mayor que importe_max ({importe_max})"
            )
    
    # Validar formato de fechas si se proporcionan
    if desde:
        try:
            datetime.strptime(desde, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Formato de fecha 'desde' inválido. Se espera YYYY-MM-DD, se recibió: {desde}"
            )
    
    if hasta:
        try:
            datetime.strptime(hasta, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Formato de fecha 'hasta' inválido. Se espera YYYY-MM-DD, se recibió: {hasta}"
            )
    
    # Nota: No requerimos filtros obligatorios para mantener compatibilidad
    # Si no se proporciona ningún filtro, se retornan todas las facturas (puede ser costoso)
    # En producción, considerar requerir al menos desde/hasta
    
    # Construir filtros usando el helper
    filter_params = build_supabase_filters(
        desde=desde,
        hasta=hasta,
        proveedor=proveedor,
        pais_origen=pais_origen,
        importe_min=importe_min,
        importe_max=importe_max,
        categoria=categoria,
        moneda=moneda,
        limit=limit,
        offset=offset
    )
    
    # Construir URL
    url = f"{SUPABASE_URL}/rest/v1/facturas"
    if filter_params:
        url += '?' + '&'.join(filter_params)
    
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    
    async with httpx.AsyncClient() as client:
        logger.debug(f"Consultando Supabase: {url}")
        r = await client.get(url, headers=headers)
        logger.debug(f"Respuesta Supabase status={r.status_code} body={r.text}")
        if r.status_code != 200:
            logger.error(f"Supabase error {r.status_code}: {r.text}")
            raise HTTPException(status_code=500, detail=f"Error consultando Supabase: {r.text}")
        data = r.json()
        logger.info(f"Facturas recuperadas: {len(data)} registros")
        return data

@router.post("/", response_model=Factura)
async def add_factura(factura: Factura, current_user: UserInDB = Depends(get_current_user)):
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
    pais_factura: Optional[str] = Form(None),
    pais_ue: Optional[str] = Form(None),
    tipo_adquisicion: Optional[str] = Form(None),
    servicio_intracomunitario_sin_iva: Optional[str] = Form(None),
    servicio_extracomunitario_sin_iva: Optional[str] = Form(None),
    inversion_sujeto_pasivo: Optional[str] = Form(None),
    dua: Optional[str] = Form(None),
    gasto_nacional_iva_deducible: Optional[str] = Form(None),
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
        "pais_factura": pais_factura if pais_factura and pais_factura.strip() else None,
        "pais_ue": pais_ue if pais_ue and pais_ue.strip() else None,
        "tipo_adquisicion": tipo_adquisicion if tipo_adquisicion and tipo_adquisicion.strip() else None,
        "servicio_intracomunitario_sin_iva": servicio_intracomunitario_sin_iva if servicio_intracomunitario_sin_iva and servicio_intracomunitario_sin_iva.strip() else None,
        "servicio_extracomunitario_sin_iva": servicio_extracomunitario_sin_iva if servicio_extracomunitario_sin_iva and servicio_extracomunitario_sin_iva.strip() else None,
        "inversion_sujeto_pasivo": inversion_sujeto_pasivo if inversion_sujeto_pasivo and inversion_sujeto_pasivo.strip() else None,
        "dua": dua if dua and dua.strip() else None,
        "gasto_nacional_iva_deducible": gasto_nacional_iva_deducible if gasto_nacional_iva_deducible and gasto_nacional_iva_deducible.strip() else None,
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
