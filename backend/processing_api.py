# processing_api.py
# Endpoints para el procesamiento paso a paso de facturas
# Usa servicios locales de Python (Gemini/LangChain y Google Drive) en vez de n8n

from fastapi import APIRouter, HTTPException, Depends
import httpx
import os
import logging
import certifi
import json
from auth import get_current_user, UserInDB

# Importar servicios locales
from services.invoice_analyzer_service import extract_invoice_data
from services.drive_service import upload_to_drive

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/processing", tags=["processing"])

# =========================
#   CONFIG
# =========================
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()


def supabase_headers(extra: dict | None = None):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Configura SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY")
    base = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if extra:
        base.update(extra)
    return base


async def get_upload(upload_id: str) -> dict:
    """Obtiene un registro de uploads por ID"""
    async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/uploads?id=eq.{upload_id}&select=*",
            headers=supabase_headers()
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Error leyendo upload: {resp.text}")
    rows = resp.json()
    if not rows:
        raise HTTPException(status_code=404, detail="Upload no encontrado")
    return rows[0]


async def update_upload(upload_id: str, data: dict) -> dict:
    """Actualiza un registro de uploads"""
    # Serializar campos JSONB correctamente
    if "ai_result" in data and data["ai_result"] is not None:
        if isinstance(data["ai_result"], dict):
            data["ai_result"] = json.dumps(data["ai_result"])
    if "meta" in data and data["meta"] is not None:
        if isinstance(data["meta"], dict):
            data["meta"] = json.dumps(data["meta"])
    
    async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/uploads?id=eq.{upload_id}",
            headers=supabase_headers(),
            json=data
        )
    if resp.status_code not in (200, 204):
        logger.error("Error actualizando upload %s: %s", upload_id, resp.text)
        raise HTTPException(status_code=502, detail=f"Error actualizando upload: {resp.text}")
    result = resp.json()
    return result[0] if result else data


async def update_factura(factura_id: int, data: dict) -> None:
    """Actualiza un registro de facturas"""
    async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/facturas?id=eq.{factura_id}",
            headers=supabase_headers(),
            json=data
        )
    if resp.status_code not in (200, 204):
        logger.warning("Error actualizando factura %s: %s", factura_id, resp.text)


async def create_or_update_factura(ai_data: dict) -> int | None:
    """
    Crea o actualiza un registro en la tabla facturas con los datos extraídos por IA.
    
    Args:
        ai_data: Diccionario con los datos extraídos de la factura
        
    Returns:
        El ID del registro creado/actualizado, o None si falla
    """
    from datetime import datetime
    
    # Mapear campos de ai_data a la estructura de facturas
    id_ext = ai_data.get("id_factura", "").strip() if ai_data.get("id_factura") else None
    
    if not id_ext:
        logger.warning("No se puede crear factura: falta id_factura en ai_data")
        return None
    
    # Parsear fecha de DD/MM/YYYY a diferentes formatos
    fecha_str = ai_data.get("fecha", "")
    fecha_txt = None
    fecha_iso = None
    
    if fecha_str:
        try:
            dt = datetime.strptime(fecha_str, "%d/%m/%Y")
            fecha_txt = fecha_str  # Mantener formato original para campo texto
            fecha_iso = dt.strftime("%Y-%m-%d")  # ISO para campo date
        except ValueError:
            fecha_txt = fecha_str
    
    # Construir fila para facturas
    factura_row = {
        "id_ext": id_ext,
        "supplier_vat_number": ai_data.get("proveedor_vat") if ai_data.get("proveedor_vat") != "N/A" else None,
        "fecha": fecha_txt,
        "proveedor": ai_data.get("proveedor"),
        "categoria": ai_data.get("categoria"),
        "descripcion": ai_data.get("descripcion") or "Sin descripción",
        "moneda": ai_data.get("moneda", "EUR"),
        "tarifa_cambio": ai_data.get("tipo_cambio"),
        "pais_origen": ai_data.get("pais_origen"),
        "notas": ai_data.get("notas") if ai_data.get("notas") != "N/A" else None,
        "importe_sin_iva_local": ai_data.get("importe_sin_iva"),
        "iva_local": ai_data.get("iva_porcentaje"),
        "total_moneda_local": ai_data.get("importe_total"),
        # Campos de clasificación fiscal
        "pais_factura": ai_data.get("pais_factura"),
        "pais_ue": ai_data.get("pais_ue"),
        "tipo_adquisicion": ai_data.get("tipo_adquisicion"),
        "servicio_intracomunitario_sin_iva": ai_data.get("servicio_intracomunitario_sin_iva"),
        "servicio_extracomunitario_sin_iva": ai_data.get("servicio_extracomunitario_sin_iva"),
        "inversion_sujeto_pasivo": ai_data.get("inversion_sujeto_pasivo"),
        "dua": ai_data.get("dua"),
        "gasto_nacional_iva_deducible": ai_data.get("gasto_nacional_iva_deducible"),
    }
    
    # Añadir fecha_dt si se parseó correctamente
    if fecha_iso:
        factura_row["fecha_dt"] = fecha_iso
    
    # Calcular importes en EUR si hay tipo de cambio
    tipo_cambio = ai_data.get("tipo_cambio")
    if tipo_cambio and ai_data.get("moneda") != "EUR":
        importe_sin_iva = ai_data.get("importe_sin_iva")
        importe_total = ai_data.get("importe_total")
        if importe_sin_iva:
            factura_row["importe_sin_iva_euro"] = round(importe_sin_iva / tipo_cambio, 2)
        if importe_total:
            factura_row["importe_total_euro"] = round(importe_total / tipo_cambio, 2)
    elif ai_data.get("moneda") == "EUR":
        # Si ya está en EUR, copiar los valores
        factura_row["importe_sin_iva_euro"] = ai_data.get("importe_sin_iva")
        factura_row["importe_total_euro"] = ai_data.get("importe_total")
    
    # Upsert: si existe id_ext, actualizar; si no, crear
    # Usamos on_conflict para manejar duplicados
    url = f"{SUPABASE_URL}/rest/v1/facturas"
    headers = supabase_headers({"Prefer": "return=representation"})
    
    try:
        async with httpx.AsyncClient(timeout=20, verify=certifi.where()) as client:
            # Primero intentar insertar
            resp = await client.post(url, headers=headers, json=factura_row)
            
            if resp.status_code in (200, 201):
                body = resp.json()
                if isinstance(body, list) and body:
                    factura_id = body[0].get("id")
                    logger.info("Factura creada con ID: %s", factura_id)
                    return factura_id
                elif isinstance(body, dict):
                    factura_id = body.get("id")
                    logger.info("Factura creada con ID: %s", factura_id)
                    return factura_id
            
            # Si falla por duplicado (código 409 o error de constraint), buscar la existente
            if resp.status_code == 409 or "duplicate" in resp.text.lower() or "unique" in resp.text.lower():
                logger.info("Factura con id_ext=%s ya existe, buscando...", id_ext)
                # Buscar factura existente
                search_resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/facturas?id_ext=eq.{id_ext}&select=id",
                    headers=supabase_headers()
                )
                if search_resp.status_code == 200:
                    rows = search_resp.json()
                    if rows:
                        factura_id = rows[0].get("id")
                        logger.info("Factura existente encontrada con ID: %s", factura_id)
                        return factura_id
            
            logger.error("Error creando factura: %s - %s", resp.status_code, resp.text)
            return None
            
    except Exception as e:
        logger.exception("Error en create_or_update_factura: %s", e)
        return None


# =========================
#   ENDPOINTS
# =========================

@router.post("/{upload_id}/start-ai", status_code=200)
async def start_ai_processing(
    upload_id: str,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Inicia el procesamiento con IA (Gemini) para extraer datos de la factura.
    
    1. Valida que status == UPLOADED o FAILED_AI
    2. Actualiza status = PROCESSING_AI
    3. Llama al servicio local de Gemini (gemini_service)
    4. Si OK: guarda ai_result, actualiza status = AI_COMPLETED
    5. Si FAIL: actualiza status = FAILED_AI
    """
    # 1. Obtener upload y validar status
    upload = await get_upload(upload_id)
    current_status = upload.get("status")
    
    if current_status not in ("UPLOADED", "FAILED_AI"):
        raise HTTPException(
            status_code=400, 
            detail=f"No se puede procesar: status actual es '{current_status}', debe ser 'UPLOADED' o 'FAILED_AI'"
        )
    
    # 2. Actualizar status a PROCESSING_AI
    await update_upload(upload_id, {"status": "PROCESSING_AI"})
    
    # 3. Obtener ruta del archivo
    storage_path = upload.get("storage_path")
    if not storage_path:
        await update_upload(upload_id, {
            "status": "FAILED_AI",
            "meta": {"ai_error": "No hay storage_path en el upload"},
        })
        return {
            "success": False,
            "status": "FAILED_AI",
            "ai_data": None,
            "error": "No hay archivo asociado al upload",
        }
    
    # 4. Llamar al servicio de Gemini
    try:
        logger.info("Iniciando extracción con Gemini para upload %s", upload_id)
        ai_data = await extract_invoice_data(storage_path)
        
        # 5a. Éxito: crear/actualizar factura con los datos extraídos
        factura_id = await create_or_update_factura(ai_data)
        
        # 5b. Guardar resultado y vincular con factura
        update_data = {
            "status": "AI_COMPLETED",
            "ai_result": ai_data,
        }
        if factura_id:
            update_data["factura_id"] = factura_id
        
        await update_upload(upload_id, update_data)
        
        logger.info("Procesamiento IA completado para upload %s, factura_id=%s", upload_id, factura_id)
        return {
            "success": True,
            "status": "AI_COMPLETED",
            "ai_data": ai_data,
            "factura_id": factura_id,
            "error": None,
        }
        
    except FileNotFoundError as e:
        error_msg = f"Archivo no encontrado: {str(e)}"
        await update_upload(upload_id, {
            "status": "FAILED_AI",
            "meta": {"ai_error": error_msg},
        })
        logger.error("Procesamiento IA falló para upload %s: %s", upload_id, error_msg)
        return {
            "success": False,
            "status": "FAILED_AI",
            "ai_data": None,
            "error": error_msg,
        }
        
    except ValueError as e:
        error_msg = str(e)
        await update_upload(upload_id, {
            "status": "FAILED_AI",
            "meta": {"ai_error": error_msg},
        })
        logger.error("Procesamiento IA falló para upload %s: %s", upload_id, error_msg)
        return {
            "success": False,
            "status": "FAILED_AI",
            "ai_data": None,
            "error": error_msg,
        }
        
    except Exception as e:
        error_msg = f"Error inesperado: {str(e)}"
        await update_upload(upload_id, {
            "status": "FAILED_AI",
            "meta": {"ai_error": error_msg},
        })
        logger.exception("Procesamiento IA falló para upload %s: %s", upload_id, error_msg)
        return {
            "success": False,
            "status": "FAILED_AI",
            "ai_data": None,
            "error": error_msg,
        }


@router.post("/{upload_id}/start-drive", status_code=200)
async def start_drive_upload(
    upload_id: str,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Inicia la subida del archivo a Google Drive.
    
    1. Valida que status == AI_COMPLETED o FAILED_DRIVE
    2. Actualiza status = UPLOADING_DRIVE
    3. Lee ai_result de la BD
    4. Llama al servicio local de Drive (drive_service)
    5. Si OK: actualiza status = COMPLETED, guarda URL en facturas
    6. Si FAIL: actualiza status = FAILED_DRIVE
    """
    # 1. Obtener upload y validar status
    upload = await get_upload(upload_id)
    current_status = upload.get("status")
    
    if current_status not in ("AI_COMPLETED", "FAILED_DRIVE"):
        raise HTTPException(
            status_code=400,
            detail=f"No se puede subir a Drive: status actual es '{current_status}', debe ser 'AI_COMPLETED' o 'FAILED_DRIVE'"
        )
    
    # 2. Actualizar status a UPLOADING_DRIVE
    await update_upload(upload_id, {"status": "UPLOADING_DRIVE"})
    
    # 3. Obtener datos necesarios
    storage_path = upload.get("storage_path")
    original_filename = upload.get("original_filename", "factura.pdf")
    ai_result = upload.get("ai_result") or {}
    
    # Parsear ai_result si viene como string JSON
    if isinstance(ai_result, str):
        import json
        try:
            ai_result = json.loads(ai_result)
        except json.JSONDecodeError:
            ai_result = {}
    
    if not storage_path:
        await update_upload(upload_id, {
            "status": "FAILED_DRIVE",
            "meta": {"drive_error": "No hay storage_path en el upload"},
        })
        return {
            "success": False,
            "status": "FAILED_DRIVE",
            "drive_url": None,
            "error": "No hay archivo asociado al upload",
        }
    
    # 4. Llamar al servicio de Drive
    try:
        logger.info("Iniciando subida a Drive para upload %s", upload_id)
        result = await upload_to_drive(
            file_path=storage_path,
            file_name=original_filename,
            ai_data=ai_result
        )
        
        if result["success"]:
            drive_url = result["drive_url"]
            
            # 5a. Éxito: actualizar status y guardar URL en facturas
            await update_upload(upload_id, {"status": "COMPLETED"})
            
            # Si hay factura_id asociada, actualizar ubicacion_factura
            factura_id = upload.get("factura_id")
            if factura_id and drive_url:
                await update_factura(factura_id, {"ubicacion_factura": drive_url})
            
            logger.info("Subida a Drive completada para upload %s: %s", upload_id, drive_url)
            return {
                "success": True,
                "status": "COMPLETED",
                "drive_url": drive_url,
                "error": None,
            }
        else:
            # 5b. Fallo desde el servicio
            error_msg = result.get("error", "Error desconocido")
            await update_upload(upload_id, {
                "status": "FAILED_DRIVE",
                "meta": {"drive_error": error_msg},
            })
            logger.error("Subida a Drive falló para upload %s: %s", upload_id, error_msg)
            return {
                "success": False,
                "status": "FAILED_DRIVE",
                "drive_url": None,
                "error": error_msg,
            }
            
    except Exception as e:
        error_msg = f"Error inesperado: {str(e)}"
        await update_upload(upload_id, {
            "status": "FAILED_DRIVE",
            "meta": {"drive_error": error_msg},
        })
        logger.exception("Subida a Drive falló para upload %s: %s", upload_id, error_msg)
        return {
            "success": False,
            "status": "FAILED_DRIVE",
            "drive_url": None,
            "error": error_msg,
        }


@router.post("/{upload_id}/retry", status_code=200)
async def retry_processing(
    upload_id: str,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Reintenta el paso fallido según el status actual.
    
    - Si FAILED_AI: llama a start-ai
    - Si FAILED_DRIVE: llama a start-drive
    """
    upload = await get_upload(upload_id)
    current_status = upload.get("status")
    
    if current_status == "FAILED_AI":
        return await start_ai_processing(upload_id, current_user)
    elif current_status == "FAILED_DRIVE":
        return await start_drive_upload(upload_id, current_user)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"No hay nada que reintentar: status actual es '{current_status}'"
        )


@router.get("/{upload_id}/status", status_code=200)
async def get_processing_status(
    upload_id: str,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Obtiene el estado actual del procesamiento de un upload.
    """
    upload = await get_upload(upload_id)
    
    return {
        "upload_id": upload_id,
        "status": upload.get("status"),
        "ai_result": upload.get("ai_result"),
        "factura_id": upload.get("factura_id"),
        "meta": upload.get("meta"),
    }
