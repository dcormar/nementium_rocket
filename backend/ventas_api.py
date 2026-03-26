
import httpx
import hashlib
import logging, os, csv, io
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import certifi
from auth import get_current_user, UserInDB

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ventas", tags=["ventas"])

class Venta(BaseModel):
    ID: Optional[int]
    UNIQUE_ACCOUNT_IDENTIFIER: Optional[str]
    ACTIVITY_PERIOD: Optional[str]
    SALES_CHANNEL: Optional[str]
    MARKETPLACE: Optional[str]
    PROGRAM_TYPE: Optional[str]
    TRANSACTION_TYPE: Optional[str]
    TRANSACTION_EVENT_ID: Optional[str]
    ACTIVITY_TRANSACTION_ID: Optional[str]
    TAX_CALCULATION_DATE: Optional[str]
    TRANSACTION_DEPART_DATE: Optional[str]
    TRANSACTION_ARRIVAL_DATE: Optional[str]
    TRANSACTION_COMPLETE_DATE: Optional[str]
    SELLER_SKU: Optional[str]
    ASIN: Optional[str]
    ITEM_DESCRIPTION: Optional[str]
    ITEM_MANUFACTURE_COUNTRY: Optional[str]
    QTY: Optional[int]
    ITEM_WEIGHT: Optional[float]
    TOTAL_ACTIVITY_WEIGHT: Optional[float]
    COST_PRICE_OF_ITEMS: Optional[str]
    PRICE_OF_ITEMS_AMT_VAT_EXCL: Optional[str]
    PROMO_PRICE_OF_ITEMS_AMT_VAT_EXCL: Optional[str]
    TOTAL_PRICE_OF_ITEMS_AMT_VAT_EXCL: Optional[str]
    SHIP_CHARGE_AMT_VAT_EXCL: Optional[str]
    PROMO_SHIP_CHARGE_AMT_VAT_EXCL: Optional[str]
    TOTAL_SHIP_CHARGE_AMT_VAT_EXCL: Optional[str]
    GIFT_WRAP_AMT_VAT_EXCL: Optional[str]
    PROMO_GIFT_WRAP_AMT_VAT_EXCL: Optional[str]
    TOTAL_GIFT_WRAP_AMT_VAT_EXCL: Optional[str]
    TOTAL_ACTIVITY_VALUE_AMT_VAT_EXCL: Optional[str]
    PRICE_OF_ITEMS_VAT_RATE_PERCENT: Optional[str]
    PRICE_OF_ITEMS_VAT_AMT: Optional[str]
    PROMO_PRICE_OF_ITEMS_VAT_AMT: Optional[str]
    TOTAL_PRICE_OF_ITEMS_VAT_AMT: Optional[str]
    SHIP_CHARGE_VAT_RATE_PERCENT: Optional[str]
    SHIP_CHARGE_VAT_AMT: Optional[str]
    PROMO_SHIP_CHARGE_VAT_AMT: Optional[str]
    TOTAL_SHIP_CHARGE_VAT_AMT: Optional[str]
    GIFT_WRAP_VAT_RATE_PERCENT: Optional[str]
    GIFT_WRAP_VAT_AMT: Optional[str]
    PROMO_GIFT_WRAP_VAT_AMT: Optional[str]
    TOTAL_GIFT_WRAP_VAT_AMT: Optional[str]
    TOTAL_ACTIVITY_VALUE_VAT_AMT: Optional[str]
    PRICE_OF_ITEMS_AMT_VAT_INCL: Optional[float]
    PROMO_PRICE_OF_ITEMS_AMT_VAT_INCL: Optional[float]
    TOTAL_PRICE_OF_ITEMS_AMT_VAT_INCL: Optional[float]
    SHIP_CHARGE_AMT_VAT_INCL: Optional[str]
    PROMO_SHIP_CHARGE_AMT_VAT_INCL: Optional[str]
    TOTAL_SHIP_CHARGE_AMT_VAT_INCL: Optional[str]
    GIFT_WRAP_AMT_VAT_INCL: Optional[str]
    PROMO_GIFT_WRAP_AMT_VAT_INCL: Optional[str]
    TOTAL_GIFT_WRAP_AMT_VAT_INCL: Optional[str]
    TOTAL_ACTIVITY_VALUE_AMT_VAT_INCL: Optional[str]
    TRANSACTION_CURRENCY_CODE: Optional[str]
    COMMODITY_CODE: Optional[str]
    STATISTICAL_CODE_DEPART: Optional[str]
    STATISTICAL_CODE_ARRIVAL: Optional[str]
    COMMODITY_CODE_SUPPLEMENTARY_UNIT: Optional[str]
    ITEM_QTY_SUPPLEMENTARY_UNIT: Optional[str]
    TOTAL_ACTIVITY_SUPPLEMENTARY_UNIT: Optional[str]
    PRODUCT_TAX_CODE: Optional[str]
    DEPATURE_CITY: Optional[str]
    DEPARTURE_COUNTRY: Optional[str]
    DEPARTURE_POST_CODE: Optional[str]
    ARRIVAL_CITY: Optional[str]
    ARRIVAL_COUNTRY: Optional[str]
    ARRIVAL_POST_CODE: Optional[str]
    SALE_DEPART_COUNTRY: Optional[str]
    SALE_ARRIVAL_COUNTRY: Optional[str]
    TRANSPORTATION_MODE: Optional[str]
    DELIVERY_CONDITIONS: Optional[str]
    SELLER_DEPART_VAT_NUMBER_COUNTRY: Optional[str]
    SELLER_DEPART_COUNTRY_VAT_NUMBER: Optional[str]
    SELLER_ARRIVAL_VAT_NUMBER_COUNTRY: Optional[str]
    SELLER_ARRIVAL_COUNTRY_VAT_NUMBER: Optional[str]
    TRANSACTION_SELLER_VAT_NUMBER_COUNTRY: Optional[str]
    TRANSACTION_SELLER_VAT_NUMBER: Optional[str]
    BUYER_VAT_NUMBER_COUNTRY: Optional[str]
    BUYER_VAT_NUMBER: Optional[str]
    VAT_CALCULATION_IMPUTATION_COUNTRY: Optional[str]
    TAXABLE_JURISDICTION: Optional[str]
    TAXABLE_JURISDICTION_LEVEL: Optional[str]
    VAT_INV_NUMBER: Optional[str]
    VAT_INV_CONVERTED_AMT: Optional[str]
    VAT_INV_CURRENCY_CODE: Optional[str]
    VAT_INV_EXCHANGE_RATE: Optional[str]
    VAT_INV_EXCHANGE_RATE_DATE: Optional[str]
    EXPORT_OUTSIDE_EU: Optional[str]
    INVOICE_URL: Optional[str]
    BUYER_NAME: Optional[str]
    ARRIVAL_ADDRESS: Optional[str]
    SUPPLIER_NAME: Optional[str]
    SUPPLIER_VAT_NUMBER: Optional[str]
    TAX_REPORTING_SCHEME: Optional[str]
    TAX_COLLECTION_RESPONSIBILITY: Optional[str]
    TRANSACTION_COMPLETE_DATE_DT: Optional[str]
    upload_id: Optional[int]

@router.get("/", response_model=List[Venta])
async def get_ventas(
    desde: str = Query(None, description="Fecha inicio YYYY-MM-DD"),
    hasta: str = Query(None, description="Fecha fin YYYY-MM-DD"),
    asin: str = Query(None, description="Filtrar por ASIN"),
    current_user: UserInDB = Depends(get_current_user),
):
    logger.debug(f"Recibida petición de ventas desde={desde} hasta={hasta} asin={asin}")
    url = f"{SUPABASE_URL}/rest/v1/ventas"
    params = []
    if desde:
        params.append(f"TRANSACTION_COMPLETE_DATE_DT=gte.{desde}")
    if hasta:
        params.append(f"TRANSACTION_COMPLETE_DATE_DT=lte.{hasta}")
    if asin:
        params.append(f"ASIN=eq.{asin}")
    if params:
        url += '?' + '&'.join(params)
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        logger.debug(f"Consultando Supabase: {url}")
        r = await client.get(url, headers=headers)
        logger.debug(f"Respuesta Supabase status={r.status_code} body={r.text}")
        if r.status_code != 200:
            logger.error(f"Error consultando Supabase: {r.text}")
            raise HTTPException(status_code=500, detail="Error consultando Supabase")
        data = r.json()
        total = sum(v.get('TOTAL_PRICE_OF_ITEMS_AMT_VAT_INCL') or 0 for v in data)
        logger.info(f"Ventas recuperadas: {len(data)} registros. Total: {total}")
        return data

@router.post("/", response_model=Venta)
async def add_venta(venta: Venta, current_user: UserInDB = Depends(get_current_user)):
    url = f"{SUPABASE_URL}/rest/v1/ventas"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        r = await client.post(url, headers=headers, json=venta.dict(exclude_unset=True))
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Error insertando en Supabase")
        return r.json()[0] if isinstance(r.json(), list) else r.json()


# ===== Columnas conocidas de la tabla ventas (sin ID, auto-generado) =====
VENTAS_COLUMNS = {f.alias or name for name, f in Venta.model_fields.items()} - {"ID"}


def _parse_date_ddmmyyyy(s: str | None) -> str | None:
    """Convierte dd-mm-yyyy o dd/mm/yyyy a yyyy-mm-dd (ISO)."""
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _safe_float(val: str | None) -> float | None:
    """Convierte string a float, devolviendo None si falla."""
    if val is None or val.strip() == "":
        return None
    try:
        return float(val.replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _safe_int(val: str | None) -> int | None:
    """Convierte string a int, devolviendo None si falla."""
    if val is None or val.strip() == "":
        return None
    try:
        return int(float(val))
    except (ValueError, AttributeError):
        return None


def _clean_row(row: dict) -> dict:
    """
    Limpia una fila del CSV:
    - Filtra solo columnas conocidas
    - Convierte campos numericos al tipo correcto
    - Genera TRANSACTION_COMPLETE_DATE_DT desde TRANSACTION_COMPLETE_DATE
    - Reemplaza strings vacios por None
    """
    cleaned: dict = {}

    for col in VENTAS_COLUMNS:
        val = row.get(col)
        if val is not None and isinstance(val, str):
            val = val.strip()
            if val == "":
                val = None
        cleaned[col] = val

    # Campos float
    float_fields = [
        "ITEM_WEIGHT", "TOTAL_ACTIVITY_WEIGHT",
        "PRICE_OF_ITEMS_AMT_VAT_INCL", "PROMO_PRICE_OF_ITEMS_AMT_VAT_INCL",
        "TOTAL_PRICE_OF_ITEMS_AMT_VAT_INCL",
    ]
    for f in float_fields:
        if f in cleaned:
            cleaned[f] = _safe_float(cleaned.get(f))

    # Campo int
    if "QTY" in cleaned:
        cleaned["QTY"] = _safe_int(cleaned.get("QTY"))

    # Derivar TRANSACTION_COMPLETE_DATE_DT
    raw_date = cleaned.get("TRANSACTION_COMPLETE_DATE")
    cleaned["TRANSACTION_COMPLETE_DATE_DT"] = _parse_date_ddmmyyyy(raw_date)

    return cleaned


def _parse_csv_bytes(content: bytes) -> list[dict]:
    """Parsea bytes de un CSV (con posible BOM) y devuelve lista de dicts."""
    # Decodificar con utf-8-sig para eliminar BOM si existe
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _parse_xlsx_bytes(content: bytes) -> list[dict]:
    """
    Parsea bytes de un XLSX y devuelve lista de dicts.
    Usa openpyxl si esta disponible, sino lanza error.
    """
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="openpyxl no instalado. Solo se admiten archivos CSV."
        )

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h else "" for h in next(rows_iter)]

    result = []
    for row_values in rows_iter:
        row_dict = {}
        for i, val in enumerate(row_values):
            if i < len(headers) and headers[i]:
                row_dict[headers[i]] = str(val) if val is not None else None
        result.append(row_dict)
    wb.close()
    return result


BATCH_SIZE = 500  # Filas por batch insert en Supabase

# ===== Deduplicación =====
DEDUP_KEY_COLS = ("TRANSACTION_EVENT_ID", "ACTIVITY_TRANSACTION_ID")
DEDUP_CHUNK_SIZE = 200


def _sha256_bytes(content: bytes) -> str:
    """Calcula SHA256 del contenido del fichero."""
    return hashlib.sha256(content).hexdigest()


def _row_key(row: dict) -> str:
    """Clave compuesta para deduplicación de filas."""
    return f"{row.get('TRANSACTION_EVENT_ID', '')}|{row.get('ACTIVITY_TRANSACTION_ID', '')}"


async def _check_ventas_file_duplicate(
    sha256: str, headers: dict, client: httpx.AsyncClient
) -> dict | None:
    """Comprueba si ya se subió un fichero con este SHA256."""
    try:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/ventas_uploads"
            f"?sha256=eq.{sha256}"
            f"&select=id,original_filename,created_at,status,imported_rows"
            f"&order=created_at.desc&limit=1",
            headers=headers,
        )
        if resp.status_code == 200:
            rows = resp.json()
            if rows:
                return rows[0]
    except Exception as e:
        logger.exception("Error comprobando duplicado SHA256 de ventas: %s", e)
    return None


async def _find_existing_keys(
    cleaned_rows: list[dict], headers: dict, client: httpx.AsyncClient
) -> set[str]:
    """
    Devuelve el conjunto de claves compuestas (event_id|activity_id)
    que ya existen en la tabla ventas.
    """
    event_ids: set[str] = set()
    for row in cleaned_rows:
        eid = row.get("TRANSACTION_EVENT_ID")
        if eid:
            event_ids.add(eid)

    if not event_ids:
        return set()

    existing_keys: set[str] = set()
    event_id_list = list(event_ids)

    for i in range(0, len(event_id_list), DEDUP_CHUNK_SIZE):
        chunk = event_id_list[i : i + DEDUP_CHUNK_SIZE]
        ids_param = ",".join(chunk)
        try:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/ventas"
                f"?TRANSACTION_EVENT_ID=in.({ids_param})"
                f"&select=TRANSACTION_EVENT_ID,ACTIVITY_TRANSACTION_ID",
                headers=headers,
            )
            if resp.status_code == 200:
                for r in resp.json():
                    key = f"{r.get('TRANSACTION_EVENT_ID', '')}|{r.get('ACTIVITY_TRANSACTION_ID', '')}"
                    existing_keys.add(key)
        except Exception as e:
            logger.exception("Error comprobando filas duplicadas (chunk): %s", e)

    return existing_keys


async def _delete_rows_by_keys(
    keys_to_delete: set[str], headers: dict, client: httpx.AsyncClient
) -> int:
    """Elimina filas existentes por clave compuesta para poder hacer upsert."""
    deleted = 0
    # Agrupar por TRANSACTION_EVENT_ID para borrar en batches
    event_to_activity: dict[str, list[str]] = {}
    for key in keys_to_delete:
        parts = key.split("|", 1)
        if len(parts) == 2 and parts[0]:
            event_to_activity.setdefault(parts[0], []).append(parts[1])

    event_ids = list(event_to_activity.keys())
    for i in range(0, len(event_ids), DEDUP_CHUNK_SIZE):
        chunk = event_ids[i : i + DEDUP_CHUNK_SIZE]
        ids_param = ",".join(chunk)
        try:
            resp = await client.delete(
                f"{SUPABASE_URL}/rest/v1/ventas"
                f"?TRANSACTION_EVENT_ID=in.({ids_param})",
                headers=headers,
            )
            if resp.status_code in (200, 204):
                # Contar aproximadamente las filas borradas
                deleted += sum(len(event_to_activity[eid]) for eid in chunk)
            else:
                logger.error("Error borrando filas duplicadas: %s %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.exception("Error de red borrando filas duplicadas: %s", e)
    return deleted


@router.post("/upload")
async def upload_ventas_file(
    file: UploadFile = File(...),
    force: str = Form("false"),
    mode: str = Form("skip"),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Sube un fichero CSV o XLSX de ventas, lo parsea e inserta las filas
    directamente en la tabla 'ventas' de Supabase.

    Parámetros:
    - force: "false" (default) → comprueba duplicados de fichero y filas.
             "true" → omite check SHA256 y gestiona duplicados según mode.
    - mode:  "skip"   → inserta solo filas nuevas (descarta duplicadas).
             "upsert" → reemplaza filas existentes con las nuevas.
    """
    is_force = force.lower() == "true"
    dedup_mode = mode.lower()  # "skip" | "upsert"

    fname = (file.filename or "").lower()
    if not (fname.endswith(".csv") or fname.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Solo se admiten CSV o XLSX")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacio")

    file_sha256 = _sha256_bytes(content)

    # Parsear segun formato
    try:
        if fname.endswith(".csv"):
            raw_rows = _parse_csv_bytes(content)
        else:
            raw_rows = _parse_xlsx_bytes(content)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error parseando fichero de ventas: %s", e)
        raise HTTPException(status_code=400, detail=f"Error parseando fichero: {str(e)}")

    if not raw_rows:
        raise HTTPException(status_code=400, detail="El fichero no contiene filas de datos")

    # Validar que las columnas del fichero son compatibles con la tabla ventas
    file_columns = set(raw_rows[0].keys())
    matching = file_columns & VENTAS_COLUMNS
    if len(matching) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"El fichero no parece ser de ventas. "
                   f"Solo {len(matching)} columnas coinciden con la tabla ventas. "
                   f"Columnas del fichero: {sorted(file_columns)[:10]}..."
        )

    logger.info(
        "Fichero de ventas recibido: %s, %d filas, %d/%d columnas válidas, usuario=%s",
        file.filename, len(raw_rows), len(matching), len(file_columns), current_user.username,
    )

    # Limpiar y preparar filas
    cleaned_rows: list[dict] = []
    parse_errors: list[dict] = []
    for i, row in enumerate(raw_rows):
        try:
            cleaned = _clean_row(row)
            if cleaned:
                cleaned_rows.append(cleaned)
        except Exception as e:
            parse_errors.append({"row": i + 2, "error": str(e)})

    if not cleaned_rows:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudieron procesar filas validas. Errores: {parse_errors[:10]}"
        )

    # ===== COMPROBACIÓN DE DUPLICADOS =====
    headers_sb = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    async with httpx.AsyncClient(timeout=60, verify=certifi.where()) as client:

        # --- 1) Check SHA256 del fichero ---
        if not is_force:
            existing_upload = await _check_ventas_file_duplicate(file_sha256, headers_sb, client)
            if existing_upload:
                logger.info(
                    "Fichero de ventas duplicado (SHA256): %s ya subido como upload_id=%s",
                    file.filename, existing_upload.get("id"),
                )
                return {
                    "ok": False,
                    "conflict": "file",
                    "filename": file.filename,
                    "total_rows": len(cleaned_rows),
                    "inserted": 0,
                    "existing_upload": {
                        "id": existing_upload.get("id"),
                        "filename": existing_upload.get("original_filename"),
                        "uploaded_at": existing_upload.get("created_at"),
                        "status": existing_upload.get("status"),
                        "imported_rows": existing_upload.get("imported_rows"),
                    },
                    "parse_errors": parse_errors[:20],
                    "insert_errors": [],
                }

        # --- 2) Check filas duplicadas ---
        existing_keys = await _find_existing_keys(cleaned_rows, headers_sb, client)

        duplicate_rows = [r for r in cleaned_rows if _row_key(r) in existing_keys]
        new_rows = [r for r in cleaned_rows if _row_key(r) not in existing_keys]

        # Filas sin clave de dedup (campos vacíos) → siempre se insertan como nuevas
        rows_without_key = [r for r in cleaned_rows if not r.get("TRANSACTION_EVENT_ID")]
        # Reclasificar: las que no tienen clave van a new_rows
        for r in rows_without_key:
            if r in duplicate_rows:
                duplicate_rows.remove(r)
                new_rows.append(r)

        if duplicate_rows and not is_force:
            logger.info(
                "Fichero de ventas con %d filas duplicadas de %d totales",
                len(duplicate_rows), len(cleaned_rows),
            )
            return {
                "ok": False,
                "conflict": "rows",
                "filename": file.filename,
                "total_rows": len(cleaned_rows),
                "new_rows_count": len(new_rows),
                "duplicate_rows_count": len(duplicate_rows),
                "inserted": 0,
                "parse_errors": parse_errors[:20],
                "insert_errors": [],
            }

        # --- 3) Decidir qué filas insertar ---
        if dedup_mode == "upsert" and duplicate_rows:
            # Borrar filas existentes que se van a reemplazar
            keys_to_delete = {_row_key(r) for r in duplicate_rows}
            deleted = await _delete_rows_by_keys(keys_to_delete, headers_sb, client)
            logger.info("Eliminadas %d filas existentes para upsert", deleted)
            rows_to_insert = cleaned_rows  # Insertar todas
        elif dedup_mode == "skip" and duplicate_rows:
            rows_to_insert = new_rows  # Solo nuevas
        else:
            rows_to_insert = cleaned_rows  # No hay duplicados

        if not rows_to_insert:
            return {
                "ok": True,
                "conflict": None,
                "filename": file.filename,
                "total_rows": len(cleaned_rows),
                "new_rows_count": len(new_rows),
                "duplicate_rows_count": len(duplicate_rows),
                "skipped": len(duplicate_rows),
                "inserted": 0,
                "upload_id": None,
                "parse_errors": parse_errors[:20],
                "insert_errors": [],
            }

        # --- 4) Crear registro en ventas_uploads ---
        inserted = 0
        insert_errors: list[dict] = []
        upload_id = None

        upload_payload = {
            "original_filename": file.filename,
            "mime_type": file.content_type or (
                "text/csv" if fname.endswith(".csv")
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            "file_size_bytes": len(content),
            "sha256": file_sha256,
            "status": "PROCESSING",
        }
        try:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/ventas_uploads",
                headers=headers_sb,
                json=upload_payload,
            )
            if resp.status_code in (200, 201):
                upload_row = resp.json()[0] if isinstance(resp.json(), list) else resp.json()
                upload_id = upload_row["id"]
                logger.info("ventas_uploads registro creado: id=%s, sha256=%s", upload_id, file_sha256[:16])
            else:
                logger.error("Error creando ventas_uploads: %s %s", resp.status_code, resp.text[:300])
        except Exception as e:
            logger.exception("Error de red creando ventas_uploads: %s", e)

        # --- 5) Asignar upload_id e insertar por batches ---
        if upload_id is not None:
            for row in rows_to_insert:
                row["upload_id"] = upload_id

        headers_sb["Prefer"] = "return=minimal"
        url = f"{SUPABASE_URL}/rest/v1/ventas"
        for batch_start in range(0, len(rows_to_insert), BATCH_SIZE):
            batch = rows_to_insert[batch_start:batch_start + BATCH_SIZE]
            all_keys: set[str] = set()
            for row in batch:
                all_keys.update(row.keys())
            batch = [{k: row.get(k) for k in all_keys} for row in batch]
            try:
                resp = await client.post(url, headers=headers_sb, json=batch)
                if resp.status_code in (200, 201):
                    inserted += len(batch)
                else:
                    error_detail = resp.text[:300]
                    logger.error(
                        "Error insertando batch (filas %d-%d): %s %s",
                        batch_start, batch_start + len(batch), resp.status_code, error_detail,
                    )
                    insert_errors.append({
                        "batch_start": batch_start,
                        "batch_size": len(batch),
                        "status": resp.status_code,
                        "error": error_detail,
                    })
            except Exception as e:
                logger.exception("Error de red insertando batch: %s", e)
                insert_errors.append({
                    "batch_start": batch_start,
                    "batch_size": len(batch),
                    "error": str(e),
                })

    # --- 6) Actualizar ventas_uploads con resultado final ---
    if upload_id is not None:
        final_status = "COMPLETED" if inserted > 0 and not insert_errors else (
            "FAILED" if inserted == 0 else "COMPLETED"
        )
        try:
            async with httpx.AsyncClient(timeout=10, verify=certifi.where()) as client:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/ventas_uploads?id=eq.{upload_id}",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={"status": final_status, "imported_rows": inserted},
                )
        except Exception as e:
            logger.warning("No se pudo actualizar ventas_uploads id=%s: %s", upload_id, e)

    logger.info(
        "Ventas upload completado: %d insertadas de %d filas (%d nuevas, %d duplicadas, mode=%s), "
        "%d errores de parseo, %d errores de insert",
        inserted, len(cleaned_rows), len(new_rows), len(duplicate_rows), dedup_mode,
        len(parse_errors), len(insert_errors),
    )

    return {
        "ok": inserted > 0,
        "conflict": None,
        "filename": file.filename,
        "total_rows": len(cleaned_rows),
        "new_rows_count": len(new_rows),
        "duplicate_rows_count": len(duplicate_rows),
        "skipped": len(duplicate_rows) if dedup_mode == "skip" and duplicate_rows else 0,
        "inserted": inserted,
        "upload_id": upload_id,
        "parse_errors": parse_errors[:20],
        "insert_errors": insert_errors[:10],
    }
