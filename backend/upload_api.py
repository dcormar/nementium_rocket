# upload_api.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request, Body
from pathlib import Path
import shutil, re, os, logging, hashlib, httpx
from auth import get_current_user, UserInDB
from datetime import datetime
import certifi

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/upload", tags=["upload"])

# =========================
#   CONFIG / HELPERS
# =========================
def sanitize_folder(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9@\.\-_]", "_", name or "user")

def get_upload_base() -> Path:
    return Path(os.getenv("UPLOAD_BASE", "/tmp/uploads"))

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
N8N_WEBHOOK_URL = (os.getenv("N8N_WEBHOOK_URL") or "").strip()
N8N_WEBHOOK_SECRET = (os.getenv("N8N_WEBHOOK_SECRET") or "").strip()

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

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def parse_decimal_es(s: str | None) -> float:
    if not s or s.strip().upper() == "N/A":
        return 0.0
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return float(s)
    except Exception:
        return 0.0

def parse_date_ddmmyyyy(s: str | None) -> str | None:
    if not s:
        return None
    try:
        dt = datetime.strptime(s.strip(), "%d/%m/%Y").date()
        return dt.isoformat()
    except Exception:
        return None

def parse_tipo_cambio(valor: str | float | None) -> float | None:
    if valor is None:
        return 1.0
    # Si ya es un número, devolverlo directamente
    if isinstance(valor, (int, float)):
        return float(valor) if valor != 0 else None
    # Si es string, procesarlo
    s = valor.strip().upper()
    if s in {"N/A", "NA", "N.A.", "NONE", "-", ""}:
        return None
    s = s.replace(",", ".")
    try:
        result = float(s)
        return result if result != 0 else None
    except ValueError:
        return 1.0

def parse_importe_a_eur(importe_str: str | float | None, tipo_cambio: str | float | None) -> float | None:
    if importe_str is None:
        return None
    try:
        if isinstance(importe_str, (int, float)):
            importe = float(importe_str)
        else:
            importe = float(importe_str.replace(".", "").replace(",", "."))
    except Exception:
        return None
    if tipo_cambio is None:
        return None
    if isinstance(tipo_cambio, str) and tipo_cambio.strip().upper() in ("N/A", "NA", "-", ""):
        return None
    try:
        if isinstance(tipo_cambio, (int, float)):
            tc = float(tipo_cambio)
        else:
            tc = float(tipo_cambio.replace(",", "."))
    except Exception:
        return None
    if tc == 0:
        return None
    return round(importe * tc, 2)

# ===== Helper: Insertar registro en automations =====
async def insert_automation_record(n8n_workflow_name: str) -> str | None:
    """
    Inserta un registro en la tabla 'automations' con status='STARTED'.
    Retorna el ID del registro insertado o None si falla.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("insert_automation_record: Supabase no configurado")
        return None
    
    automation_payload = {
        "n8n_workflow_name": n8n_workflow_name,
        "status": "STARTED",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/automations",
                headers=supabase_headers(),
                json=automation_payload
            )
        if resp.status_code not in (200, 201):
            logger.error("Insert automation falló %s: %s", resp.status_code, resp.text)
            return None
        result = resp.json()
        automation_id = result[0].get("id") if isinstance(result, list) and result else result.get("id") if isinstance(result, dict) else None
        logger.info("Automation record creado: id=%s, workflow=%s", automation_id, n8n_workflow_name)
        return automation_id
    except httpx.RequestError as e:
        logger.exception("Error de red insertando automation record: %s", e)
        return None
    except Exception as e:
        logger.exception("Error insertando automation record: %s", e)
        return None

# ===== CAMBIO: logs + sin verificación TLS en la llamada a n8n =====
async def post_to_n8n(payload: dict) -> tuple[int, str]:
    """
    Lanza el webhook a n8n y devuelve (status_code, text).
    - Loguea el inicio y el resultado (status + primeros 500 chars del body).
    - Desactiva la verificación TLS (verify=False) SOLO para esta llamada.
      ⚠️ Úsalo bajo tu responsabilidad / entorno controlado.
    """
    if not N8N_WEBHOOK_URL:
        logger.warning("post_to_n8n: N8N_WEBHOOK_URL no configurado; se omite llamada")
        return (599, "N8N_WEBHOOK_URL no configurado")

    headers = {"Content-Type": "application/json"}
    if N8N_WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = N8N_WEBHOOK_SECRET

    logger.info("n8n webhook => %s  payload=%s", N8N_WEBHOOK_URL, payload)
    try:
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            resp = await client.post(N8N_WEBHOOK_URL, json=payload, headers=headers)
        logger.info("n8n webhook <= status=%s body=%s", resp.status_code, (resp.text or "")[:500])
        return (resp.status_code, resp.text)
    except httpx.RequestError as e:
        logger.exception("n8n webhook EXCEPTION: %s", e)
        return (599, f"ex:{e}")

# =========================
#   SUBIDA
# =========================
@router.post("/", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    tipo: str = Form(...),
    iaprocess: str = Form("true"),  # Por defecto true para mantener compatibilidad
    current_user: UserInDB = Depends(get_current_user),
):
    base = get_upload_base()
    base.mkdir(parents=True, exist_ok=True)

    tipo = (tipo or "").lower().strip()
    if tipo not in ("factura", "venta"):
        raise HTTPException(status_code=400, detail="tipo debe ser 'factura' o 'venta'")

    fname_lower = (file.filename or "").lower()
    if not (fname_lower.endswith(".pdf") or fname_lower.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Solo se admiten PDF o XLSX")

    user_folder = base / sanitize_folder(current_user.username) / tipo
    user_folder.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-.]+", "_", file.filename or "file")
    dest_file = user_folder / safe_name

    logger.info("Guardando archivo en: %s", dest_file)
    try:
        with dest_file.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    except Exception:
        logger.exception("Error guardando archivo en disco")
        raise HTTPException(status_code=500, detail="Error guardando archivo")

    if not dest_file.exists():
        raise HTTPException(status_code=500, detail="Archivo no encontrado tras guardado")

    size_bytes = dest_file.stat().st_size
    mime_type = file.content_type or ("application/pdf" if fname_lower.endswith(".pdf") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    sha256 = sha256_file(dest_file)
    storage_path = str(dest_file)

    # Insert metadatos (UPLOADED) -> Supabase (seguimos verificando TLS aquí)
    try:
        async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
            if tipo == "venta":
                payload = {
                    "status": "UPLOADED",
                    "original_filename": safe_name,
                    "storage_path": storage_path,
                    "mime_type": mime_type,
                    "file_size_bytes": size_bytes,
                    "sha256": sha256,
                    "notes": f"Subido por {current_user.username}",
                }
                resp = await client.post(
                    f"{SUPABASE_URL}/rest/v1/ventas_uploads",
                    headers=supabase_headers(),
                    json=payload
                )
            else:
                payload = {
                    "tipo": "FACTURA",
                    "status": "UPLOADED",
                    "original_filename": safe_name,
                    "storage_path": storage_path,
                    "mime_type": mime_type,
                    "file_size_bytes": size_bytes,
                    "sha256": sha256,
                    "source": "manual",
                    "manual":  not iaprocess,
                }
                resp = await client.post(
                    f"{SUPABASE_URL}/rest/v1/uploads",
                    headers=supabase_headers(),
                    json=payload
                )

        if resp.status_code not in (200, 201):
            logger.error("Insert Supabase falló %s: %s", resp.status_code, resp.text)
            raise HTTPException(status_code=502, detail=f"Error insertando metadatos en BD: {resp.text}")

        db_row = resp.json()[0] if isinstance(resp.json(), list) and resp.json() else resp.json()
        upload_id = db_row.get("id")
    except httpx.RequestError as e:
        logger.exception("Error de red con Supabase")
        raise HTTPException(status_code=502, detail=f"Error de red con Supabase: {e}") from e


    
    # Insertar registro en automations antes de llamar a n8n
    await insert_automation_record(tipo)
    
    # Llamada a n8n (sin verificar TLS y con logs)
    # iaprocess puede ser "true" o "false" como string
    iaprocess_bool = iaprocess.lower() == "true"
    n8n_payload = {
        "tipo": tipo,            # "factura" | "venta"
        "storage": "local",
        "user": current_user.username,
        "filename": safe_name,
        "upload_id": upload_id,
        "iaprocess": iaprocess_bool,  # Añadido parámetro iaprocess
    }
    try:
        status, text = await post_to_n8n(n8n_payload)
        if status >= 300:
            logger.error("Webhook n8n devolvió %s: %s", status, text)
            # Marca FAILED para que el front enseñe botón de "Reintentar"
            async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
                if tipo == "venta":
                    await client.patch(
                        f"{SUPABASE_URL}/rest/v1/ventas_uploads?id=eq.{upload_id}",
                        headers=supabase_headers(),
                        json={"status": "FAILED", "notes": f"n8n {status}: {text[:200]}",}
                    )
                else:
                    await client.patch(
                        f"{SUPABASE_URL}/rest/v1/uploads?id=eq.{upload_id}",
                        headers=supabase_headers(),
                        json={"status": "FAILED", "meta": {"n8n_error": text[:200]}}
                    )
        else:
            logger.info("Webhook n8n OK (%s): %s", status, n8n_payload)
    except Exception as e:
        logger.exception("Error llamando al webhook n8n: %s", e)
        # Marca FAILED
        async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
            if tipo == "venta":
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/ventas_uploads?id=eq.{upload_id}",
                    headers=supabase_headers(),
                    json={"status": "FAILED", "notes": f"ex:{str(e)[:200]}",}
                )
            else:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/uploads?id=eq.{upload_id}",
                    headers=supabase_headers(),
                    json={"status": "FAILED", "meta": {"ex": str(e)[:200]}}
                )

    return {
        "ok": True,
        "path": storage_path,
        "filename": safe_name,
        "tipo": tipo,
        "usuario": current_user.username,
        "db_row": db_row,
    }

# =========================
#   RETRY WEBHOOK (FACTURA/VENTA)
# =========================
@router.post("/{upload_id}/retry", status_code=202)
async def retry_webhook(
    upload_id: str,
    tipo: str = Body(..., embed=True),       # "factura" | "venta"
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Relanza la llamada al webhook de n8n para un upload concreto.
    """
    tipo = (tipo or "").lower().strip()
    if tipo not in ("factura", "venta"):
        raise HTTPException(status_code=400, detail="tipo debe ser 'factura' o 'venta'")

    # 1) Cargar fila (Supabase con verificación TLS)
    try:
        async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
            if tipo == "venta":
                r = await client.get(
                    f"{SUPABASE_URL}/rest/v1/ventas_uploads?id=eq.{upload_id}&select=id,original_filename,status",
                    headers=supabase_headers()
                )
            else:
                r = await client.get(
                    f"{SUPABASE_URL}/rest/v1/uploads?id=eq.{upload_id}&select=id,original_filename,status,tipo,manual",
                    headers=supabase_headers()
                )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Error leyendo upload: {r.text}")
        rows = r.json()
        if not rows:
            raise HTTPException(status_code=404, detail="upload no encontrado")
        row = rows[0]
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Error de red leyendo upload: {e}") from e

    filename = row.get("original_filename")
    manual = row.get("manual")
    if not filename:
        raise HTTPException(status_code=400, detail="El upload no tiene filename")

    # Insertar registro en automations antes de llamar a n8n
    await insert_automation_record(tipo)

    # 2) Lanzar webhook (sin TLS verify + logs)
    payload = {
        "tipo": tipo,
        "storage": "local",
        "user": current_user.username,
        "filename": filename,
        "iaprocess": not manual,
        "upload_id": upload_id,
    }
    try:
        status, text = await post_to_n8n(payload)
    except Exception as e:
        status, text = (599, f"ex:{e}")

    # 3) Actualizar estado (Supabase con TLS verify normal)
    try:
        async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
            if status < 300:
                # Éxito: consideramos reencolado → UPLOADED
                if tipo == "venta":
                    presp = await client.patch(
                        f"{SUPABASE_URL}/rest/v1/ventas_uploads?id=eq.{upload_id}",
                        headers=supabase_headers(),
                        json={"status": "UPLOADED", "notes": "reintento OK"}
                    )
                else:
                    presp = await client.patch(
                        f"{SUPABASE_URL}/rest/v1/uploads?id=eq.{upload_id}",
                        headers=supabase_headers(),
                        json={"status": "UPLOADED", "meta": {"retry": True}}
                    )
            else:
                # Error: marcamos FAILED para que siga saliendo el botón
                if tipo == "venta":
                    presp = await client.patch(
                        f"{SUPABASE_URL}/rest/v1/ventas_uploads?id=eq.{upload_id}",
                        headers=supabase_headers(),
                        json={"status": "FAILED", "notes": f"n8n {status}: {text[:200]}"}
                    )
                else:
                    presp = await client.patch(
                        f"{SUPABASE_URL}/rest/v1/uploads?id=eq.{upload_id}",
                        headers=supabase_headers(),
                        json={"status": "FAILED", "meta": {"n8n_error": text[:200], "retry": True}}
                    )
        if presp.status_code not in (200, 204):
            logger.warning("No se pudo actualizar estado tras retry (%s): %s", presp.status_code, presp.text)
    except httpx.RequestError as e:
        logger.exception("Error de red al actualizar estado tras retry: %s", e)

    return {
        "ok": status < 300,
        "n8n_status": status,
        "n8n_text": text[:500],
        "upload_id": upload_id,
        "tipo": tipo,
    }

# === CALLBACK DE n8n ==================================================
@router.post("/automate/callback", status_code=201)
async def automate_callback(request: Request):
    """
    Recibe el cuerpo desde n8n tras procesar una FACTURA.
    - Upsert en public.facturas (on_conflict = id_ext_compound) con resolution=ignore-duplicates.
    - Si se ignora por duplicado, marcamos uploads.status='DUPLICATED'.
    - Si inserta, marcamos uploads.status='PROCESSED' y enlazamos factura_id.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido en callback")

    # Normaliza a un dict con los campos
    payload = None
    if isinstance(body, list) and body:
        first = body[0]
        if isinstance(first, dict) and "JsonString" in first and isinstance(first["JsonString"], list) and first["JsonString"]:
            payload = first["JsonString"][0]
    elif isinstance(body, dict):
        payload = body

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Formato de callback no reconocido")

    # Campos mínimos
    id_ext = (payload.get("ID Factura") or "").strip()
    if not id_ext:
        raise HTTPException(status_code=400, detail="Falta 'ID Factura' en callback")

    status_n8n = (payload.get("status_n8n") or "OK").strip()
    
    # Verificar si iaprocess es false
    iaprocess = payload.get("iaprocess", True)
    if isinstance(iaprocess, str):
        iaprocess = iaprocess.lower() == "true"
    iaprocess = bool(iaprocess) if iaprocess is not None else True

    # Si iaprocess es false, solo actualizar ubicacion_factura
    if not iaprocess:
        ubicacion_factura = (payload.get("ubicacion_factura") or "").strip() or None
        
        if status_n8n == "ERROR":
            logger.warning("Callback con iaprocess=false y status_n8n=ERROR para ID Factura: %s", id_ext)
            return {"ok": False, "error": "status_n8n=ERROR", "id_ext": id_ext}
        try:
            async with httpx.AsyncClient(timeout=20, verify=certifi.where()) as client:
                # Primero tenemos que obtener de Supabase el id_factura, buscándolo en uploads
                get_resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/uploads?id=eq.{id_ext}&select=factura_id", 
                    headers=supabase_headers()
                )
                if get_resp.status_code != 200:
                    logger.error("Error buscando upload por id: %s", get_resp.text)
                    raise HTTPException(status_code=502, detail=f"Error buscando upload: {get_resp.text}")
                rows = get_resp.json()
                if not rows:
                    raise HTTPException(status_code=404, detail="upload no encontrado")
                row = rows[0]
                factura_id = row.get("factura_id")
                
                # Actualizar solo ubicacion_factura en la factura existente
                patch_data = {"ubicacion_factura": ubicacion_factura}
                patch_resp = await client.patch(
                    f"{SUPABASE_URL}/rest/v1/facturas?id=eq.{factura_id}",
                    headers=supabase_headers({"Prefer": "return=representation"}),
                    json=patch_data
                )
                
                if patch_resp.status_code not in (200, 204):
                    logger.error("Error actualizando ubicacion_factura: %s", patch_resp.text)
                    raise HTTPException(status_code=502, detail=f"Error actualizando factura: {patch_resp.text}")
                
                # Verificar si se actualizó alguna fila
                # PostgREST devuelve un array con las filas actualizadas, o un objeto vacío si no hay filas
                updated_rows = None
                try:
                    response_body = patch_resp.json()
                    if isinstance(response_body, list):
                        updated_rows = response_body
                    elif isinstance(response_body, dict):
                        # Si es un objeto, podría ser una sola fila o vacío
                        updated_rows = [response_body] if response_body else []
                    else:
                        updated_rows = []
                except Exception:
                    # Si no hay JSON o está vacío, verificar Content-Range header
                    content_range = patch_resp.headers.get("Content-Range", "")
                    # Content-Range tiene formato "0-0/0" si no hay filas, o "0-0/1" si hay 1 fila
                    if content_range and "/" in content_range:
                        total = content_range.split("/")[-1]
                        updated_rows = [] if total == "0" else [{}]  # Simulamos que hay filas si total > 0
                    else:
                        updated_rows = []
                
                # Actualizar status en uploads según el resultado
                if not updated_rows or len(updated_rows) == 0:
                    logger.warning("No se actualizó ninguna fila en facturas para factura_id=%s (id_ext=%s)", factura_id, id_ext)
                    # Actualizar uploads con status=FAILED
                    try:
                        patch_upload_resp = await client.patch(
                            f"{SUPABASE_URL}/rest/v1/uploads?id=eq.{id_ext}",
                            headers=supabase_headers(),
                            json={"status": "FAILED"}
                        )
                        if patch_upload_resp.status_code not in (200, 204):
                            logger.warning("No se pudo actualizar uploads a FAILED para id=%s: %s %s",
                                         id_ext, patch_upload_resp.status_code, patch_upload_resp.text)
                        else:
                            logger.info("uploads actualizado a FAILED para id=%s", id_ext)
                    except httpx.RequestError:
                        logger.exception("Error de red al actualizar uploads (status FAILED)")
                    return {"ok": False, "error": "No se encontró factura para actualizar", "id_ext": id_ext, "factura_id": factura_id}
                
                # Se actualizó correctamente, marcar uploads como PROCESSED
                try:
                    patch_upload_resp = await client.patch(
                        f"{SUPABASE_URL}/rest/v1/uploads?id=eq.{id_ext}",
                        headers=supabase_headers(),
                        json={"status": "PROCESSED"}
                    )
                    if patch_upload_resp.status_code not in (200, 204):
                        logger.warning("No se pudo actualizar uploads a PROCESSED para id=%s: %s %s",
                                     id_ext, patch_upload_resp.status_code, patch_upload_resp.text)
                    else:
                        logger.info("uploads actualizado a PROCESSED para id=%s", id_ext)
                except httpx.RequestError:
                    logger.exception("Error de red al actualizar uploads (status PROCESSED)")
                
                logger.info("Factura con id=%s actualizada con ubicacion_factura=%s (iaprocess=false)", factura_id, ubicacion_factura)
                return {"ok": True, "id_ext": id_ext, "factura_id": factura_id, "iaprocess": False}
                
        except httpx.RequestError as e:
            logger.exception("Error de red actualizando factura (iaprocess=false)")
            raise HTTPException(status_code=502, detail=f"Error de red: {e}") from e

    # Procesamiento normal cuando iaprocess es true o no se especifica
    if status_n8n is not "ERROR": 
        fecha_txt = (payload.get("Fecha de la Factura") or "").strip()  # DD/MM/YYYY
        fecha_iso = parse_date_ddmmyyyy(fecha_txt)

        categoria   = payload.get("Categoría") or payload.get("Categoria")
        proveedor   = payload.get("Emisor") or payload.get("Proveedor")
        descripcion = payload.get("Descripción") or payload.get("Descripcion")
        importe_sin_iva = parse_decimal_es(payload.get("Importe (sin IVA)"))
        iva_pct         = parse_decimal_es(payload.get("IVA %"))
        importe_total           = parse_decimal_es(payload.get("Total"))
        moneda          = (payload.get("Moneda") or "").strip() or None
        # Manejar "Tipo Cambio" que puede venir como float o string
        tipo_cambio_raw = payload.get("Tipo Cambio")
        if tipo_cambio_raw is None:
            tipo_cambio = None
        elif isinstance(tipo_cambio_raw, (int, float)):
            tipo_cambio = tipo_cambio_raw
        else:
            tipo_cambio = (str(tipo_cambio_raw).strip() or None) if tipo_cambio_raw else None
        importe_sin_iva_eur = parse_importe_a_eur(importe_sin_iva, tipo_cambio)
        importe_total_eur = parse_importe_a_eur(importe_total, tipo_cambio)
        pais_origen     = payload.get("País origen") or payload.get("Pais origen")
        notas           = (payload.get("Notas") or "").strip() or None
        supplier_vat_number = (payload.get("provider_VAT") or "").strip() or None
        ubicacion_factura = (payload.get("ubicacion_factura") or "").strip() or None


        # Fila para facturas
        factura_row = {
            "id_ext": id_ext,
            "supplier_vat_number": supplier_vat_number,   
            "fecha": fecha_txt or None,                   
            "total_moneda_local": importe_total or None,
            "proveedor": proveedor or None,
            "categoria": categoria or None,
            "descripcion": descripcion or "Pending Process",
            "moneda": moneda,
            "tarifa_cambio": parse_tipo_cambio(tipo_cambio),
            "pais_origen": pais_origen,
            "notas": notas,
            "ubicacion_factura": ubicacion_factura,
            "iva_local": iva_pct,
            "importe_sin_iva_local": importe_sin_iva,
            "importe_sin_iva_euro": importe_sin_iva_eur,
            "importe_total_euro": importe_total_eur
        }
        if fecha_iso:
            factura_row["fecha_dt"] = fecha_iso  # si tienes la columna date
    else:
        factura_row = {

        }
    # Upsert por clave compuesta generada
    # - No queremos actualizar si ya existe -> resolution=ignore-duplicates
    url = f"{SUPABASE_URL}/rest/v1/facturas?on_conflict=id_ext_compound"
    headers = supabase_headers({"Prefer": "resolution=ignore-duplicates,return=representation"})

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, headers=headers, json=factura_row)
    except httpx.RequestError as e:
        logger.exception("Error de red con Supabase (facturas)")
        raise HTTPException(status_code=502, detail=f"Error de red con Supabase: {e}") from e

    if resp.status_code not in (200, 201):
        logger.error("Upsert factura falló %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail=f"Error insertando/actualizando factura: {resp.text}")

    # PostgREST puede devolver [] si se ignoró por duplicado con 'ignore-duplicates'
    body = None
    try:
        body = resp.json()
    except Exception:
        body = None

    inserted = None
    if isinstance(body, list):
        inserted = body[0] if body else None
    elif isinstance(body, dict):
        inserted = body

    # Adivinar nombre de archivo para enlazar upload (ej: "ES-...-....pdf")
    guess_filename = f"{id_ext}.pdf"

    # Si no hay 'inserted' => ignorado por duplicado → marcamos DUPLICATED
    if not inserted:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                patch = {"status": "DUPLICATED"}
                uresp = await client.patch(
                    f"{SUPABASE_URL}/rest/v1/uploads?original_filename=eq.{guess_filename}",
                    headers=supabase_headers(),
                    json=patch
                )
            if uresp.status_code not in (200, 204):
                logger.warning("No se pudo marcar DUPLICATED en uploads para %s: %s %s",
                               guess_filename, uresp.status_code, uresp.text)
            else:
                logger.info("uploads marcado DUPLICATED para %s", guess_filename)
        except httpx.RequestError:
            logger.exception("Error de red al actualizar uploads (status DUPLICATED)")

        return {"ok": True, "duplicated": True, "tipo": "factura", "id_ext": id_ext}

    # Si se insertó, marcamos PROCESSED y enlazamos factura_id
    factura_id = inserted.get("id")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            patch = {"status": "PROCESSED", "factura_id": factura_id}
            uresp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/uploads?original_filename=eq.{guess_filename}",
                headers=supabase_headers(),
                json=patch
            )
        if uresp.status_code not in (200, 204):
            logger.warning("No se pudo actualizar uploads a PROCESSED para %s: %s %s",
                           guess_filename, uresp.status_code, uresp.text)
        else:
            logger.info("uploads actualizado a PROCESSED para %s (factura_id=%s)", guess_filename, factura_id)
    except httpx.RequestError:
        logger.exception("Error de red al actualizar uploads (status PROCESSED)")

    return {"ok": True, "duplicated": False, "tipo": "factura", "id_ext": id_ext, "factura_id": factura_id}