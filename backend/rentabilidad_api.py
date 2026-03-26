"""
API de Análisis de Rentabilidad por ASIN.
Cruza datos de ventas, COGS, y publicidad (Ads) para calcular
la rentabilidad real por ASIN, país y periodo.
"""

import httpx
import logging
import os
import csv
import io
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Depends
from pydantic import BaseModel
from typing import Optional
import certifi
from auth import get_current_user, UserInDB

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rentabilidad", tags=["rentabilidad"])

# ---------------------------------------------------------------------------
# Mapping de países (nombre en español -> código ISO)
# ---------------------------------------------------------------------------
COUNTRY_NAME_TO_CODE = {
    "españa": "ES", "spain": "ES",
    "italia": "IT", "italy": "IT",
    "francia": "FR", "france": "FR",
    "alemania": "DE", "germany": "DE",
    "países bajos": "NL", "paises bajos": "NL", "netherlands": "NL",
    "bélgica": "BE", "belgica": "BE", "belgium": "BE",
    "suecia": "SE", "sweden": "SE",
    "polonia": "PL", "poland": "PL",
    "reino unido": "GB", "united kingdom": "GB",
    "portugal": "PT",
    "austria": "AT",
}

COUNTRY_CODE_TO_MARKETPLACE = {
    "ES": "amazon.es", "IT": "amazon.it", "FR": "amazon.fr",
    "DE": "amazon.de", "NL": "amazon.nl", "BE": "amazon.com.be",
    "SE": "amazon.se", "PL": "amazon.pl", "GB": "amazon.co.uk",
    "PT": "amazon.es", "AT": "amazon.de",
}

# ---------------------------------------------------------------------------
# Mapping de columnas del Excel de Amazon Ads (español)
# ---------------------------------------------------------------------------
# Keys are already normalized (no accents, no NBSP, lowercase, stripped)
ADS_COLUMN_MAP = {
    "fecha de inicio": "fecha_inicio",
    "fecha de finalizacion": "fecha_fin",
    "nombre de campana": "campaign_name",
    "nombre de la campana": "campaign_name",
    "nombre del grupo de anuncios": "ad_group_name",
    "pais": "country",
    "sku anunciados": "sku",
    "asin anunciados": "asin",
    "impresiones": "impressions",
    "clics": "clicks",
    "indice de clics (ctr)": "ctr",
    # CPC: formato con/sin conversión y formato simplificado
    "coste por clic (cpc), con conversion": "cpc",
    "coste por clic (cpc): sin conversion": "_cpc_raw",
    "coste por clic (cpc)": "cpc",
    # Spend: formato "Inversión" (antiguo) y "Gasto" (nuevo)
    "inversion, con conversion": "spend",
    "inversion: sin conversion": "_spend_raw",
    "gasto": "spend",
    # Sales 7d: formato con/sin conversión y formato con moneda "(€)"
    "ventas totales en 7 dias, con conversion": "sales_7d",
    "ventas totales en 7 dias: sin conversion": "_sales_7d_raw",
    "ventas totales de 7 dias (\u20ac)": "sales_7d",
    "coste publicitario de las ventas (acos) total": "acos",
    "retorno de la inversion publicitaria (roas) total": "roas",
    "pedidos totales de 7 dias (#)": "orders_7d",
    "unidades totales de 7 dias (#)": "units_7d",
    # Moneda/Divisa
    "moneda, con conversion": "currency",
    "divisa": "currency",
}

BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sb_headers(content_type: str = "application/json") -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": content_type,
    }


def _safe_float(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _safe_int(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _country_to_code(name: str) -> str | None:
    if not name:
        return None
    return COUNTRY_NAME_TO_CODE.get(name.strip().lower())


def _parse_date(val) -> str | None:
    """Convierte datetime o string a YYYY-MM-DD."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date().isoformat()
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s  # devolver tal cual si no se puede parsear


# ---------------------------------------------------------------------------
# Parseo de ficheros (reutiliza patrón de ventas_api.py)
# ---------------------------------------------------------------------------
def _parse_csv_bytes(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _parse_xlsx_bytes(content: bytes) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl no instalado")
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h else "" for h in next(rows_iter)]
    result = []
    for row_values in rows_iter:
        row_dict = {}
        for i, val in enumerate(row_values):
            if i < len(headers) and headers[i]:
                row_dict[headers[i]] = val
        result.append(row_dict)
    wb.close()
    return result


def _normalize_header(s: str) -> str:
    """Normaliza un header: quita tildes, NBSP, espacios extra."""
    import unicodedata
    s = s.strip().replace("\u00a0", " ")  # NBSP -> space
    # Remove accents
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip()


def _map_ads_row(raw: dict) -> dict | None:
    """Mapea una fila raw del Excel de Ads a nuestro esquema."""
    mapped = {}
    for raw_col, val in raw.items():
        norm = _normalize_header(raw_col)
        key = ADS_COLUMN_MAP.get(norm)
        # Fallback: "ventas totales de 7 dias (£)", "(SEK)", etc.
        if key is None and norm.startswith("ventas totales de 7 dias"):
            key = "sales_7d"
        if key and not key.startswith("_"):
            mapped[key] = val

    asin = mapped.get("asin")
    if not asin:
        return None

    country = str(mapped.get("country", "")).strip()
    country_code = _country_to_code(country)

    return {
        "fecha_inicio": _parse_date(mapped.get("fecha_inicio")),
        "fecha_fin": _parse_date(mapped.get("fecha_fin")),
        "campaign_name": mapped.get("campaign_name"),
        "ad_group_name": mapped.get("ad_group_name"),
        "country": country,
        "country_code": country_code,
        "sku": mapped.get("sku"),
        "asin": str(asin).strip(),
        "impressions": _safe_int(mapped.get("impressions", 0)),
        "clicks": _safe_int(mapped.get("clicks", 0)),
        "ctr": _safe_float(mapped.get("ctr")),
        "cpc": _safe_float(mapped.get("cpc")),
        "spend": _safe_float(mapped.get("spend")) or 0,
        "sales_7d": _safe_float(mapped.get("sales_7d")),
        "orders_7d": _safe_int(mapped.get("orders_7d")),
        "units_7d": _safe_int(mapped.get("units_7d")),
        "acos": _safe_float(mapped.get("acos")),
        "roas": _safe_float(mapped.get("roas")),
        "currency": mapped.get("currency", "EUR"),
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    asins: list[str] = []
    date_from: str
    date_to: str
    countries: list[str] = []
    categorias: list[str] = []
    group_by: str = "asin"  # asin | country | asin_country | month


class CogsUpdate(BaseModel):
    amazon_referral_fee_pct: Optional[float] = None
    fba_fee_es: Optional[float] = None
    fba_fee_it: Optional[float] = None
    fba_fee_de: Optional[float] = None
    fba_fee_fr: Optional[float] = None
    other_fixed_costs: Optional[float] = None
    cost: Optional[float] = None
    categoria: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _parse_ads_file(fname: str, content: bytes) -> tuple[list[dict], list[dict]]:
    """Parsea y mapea un fichero de ads. Devuelve (mapped_rows, parse_errors)."""
    if fname.endswith(".csv"):
        raw_rows = _parse_csv_bytes(content)
    else:
        raw_rows = _parse_xlsx_bytes(content)

    if not raw_rows:
        raise HTTPException(status_code=400, detail="El fichero no contiene filas")

    mapped_rows = []
    parse_errors = []
    for i, row in enumerate(raw_rows):
        try:
            mapped = _map_ads_row(row)
            if mapped:
                mapped_rows.append(mapped)
        except Exception as e:
            parse_errors.append({"row": i + 2, "error": str(e)})

    if not mapped_rows:
        raise HTTPException(status_code=400, detail="No se pudieron procesar filas válidas")

    return mapped_rows, parse_errors


async def _check_duplicates(mapped_rows: list[dict]) -> list[dict]:
    """Comprueba cuántas filas ya existen en ads_data. Devuelve las duplicadas."""
    # Extraer combinaciones únicas de (asin, country_code, fecha_inicio, fecha_fin)
    unique_keys = set()
    for r in mapped_rows:
        unique_keys.add((r["asin"], r.get("country_code"), r.get("fecha_inicio"), r.get("fecha_fin")))

    duplicates = []
    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        for asin, cc, fi, ff in unique_keys:
            url = (
                f"{SUPABASE_URL}/rest/v1/ads_data"
                f"?select=id,asin,country_code,campaign_name,fecha_inicio,fecha_fin,spend"
                f"&asin=eq.{asin}"
                f"&fecha_inicio=eq.{fi}"
                f"&fecha_fin=eq.{ff}"
            )
            if cc:
                url += f"&country_code=eq.{cc}"
            r = await client.get(url, headers=_sb_headers())
            if r.status_code == 200:
                duplicates.extend(r.json())

    return duplicates


async def _upsert_ads(mapped_rows: list[dict]) -> tuple[int, list[dict]]:
    """Inserta o actualiza filas en ads_data usando UPSERT."""
    inserted = 0
    insert_errors = []
    url = f"{SUPABASE_URL}/rest/v1/ads_data"
    headers = {
        **_sb_headers(),
        "Prefer": "return=minimal,resolution=merge-duplicates",
    }

    async with httpx.AsyncClient(timeout=60, verify=certifi.where()) as client:
        for batch_start in range(0, len(mapped_rows), BATCH_SIZE):
            batch = mapped_rows[batch_start:batch_start + BATCH_SIZE]
            try:
                resp = await client.post(url, headers=headers, json=batch)
                if resp.status_code in (200, 201):
                    inserted += len(batch)
                else:
                    insert_errors.append({
                        "batch_start": batch_start,
                        "status": resp.status_code,
                        "error": resp.text[:300],
                    })
            except Exception as e:
                insert_errors.append({"batch_start": batch_start, "error": str(e)})

    return inserted, insert_errors


@router.post("/ads/check")
async def check_ads_file(
    file: UploadFile = File(...),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Parsea el fichero y comprueba si hay datos duplicados.
    Devuelve el número de duplicados para que el frontend pida confirmación.
    """
    fname = (file.filename or "").lower()
    if not (fname.endswith(".csv") or fname.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Solo se admiten CSV o XLSX")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    try:
        mapped_rows, parse_errors = _parse_ads_file(fname, content)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error parseando fichero de ads: %s", e)
        raise HTTPException(status_code=400, detail=f"Error parseando fichero: {str(e)}")

    duplicates = await _check_duplicates(mapped_rows)

    return {
        "total_rows": len(mapped_rows),
        "duplicates_count": len(duplicates),
        "duplicates_sample": duplicates[:5],
        "parse_errors": parse_errors[:20],
    }


@router.post("/ads/upload")
async def upload_ads_file(
    file: UploadFile = File(...),
    force: bool = Query(False, description="Si true, hace upsert sobreescribiendo duplicados"),
    current_user: UserInDB = Depends(get_current_user),
):
    """Sube un CSV/XLSX de Amazon Ads. Si force=true, actualiza duplicados."""
    fname = (file.filename or "").lower()
    if not (fname.endswith(".csv") or fname.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Solo se admiten CSV o XLSX")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    try:
        mapped_rows, parse_errors = _parse_ads_file(fname, content)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error parseando fichero de ads: %s", e)
        raise HTTPException(status_code=400, detail=f"Error parseando fichero: {str(e)}")

    logger.info("Ads upload: %s, %d filas mapeadas, force=%s, usuario=%s",
                file.filename, len(mapped_rows), force, current_user.username)

    if not force:
        # Insertar normal (falla si hay duplicados)
        inserted = 0
        insert_errors = []
        url = f"{SUPABASE_URL}/rest/v1/ads_data"
        headers = {**_sb_headers(), "Prefer": "return=minimal"}
        async with httpx.AsyncClient(timeout=60, verify=certifi.where()) as client:
            for batch_start in range(0, len(mapped_rows), BATCH_SIZE):
                batch = mapped_rows[batch_start:batch_start + BATCH_SIZE]
                try:
                    resp = await client.post(url, headers=headers, json=batch)
                    if resp.status_code in (200, 201):
                        inserted += len(batch)
                    elif resp.status_code == 409:
                        # Conflicto de duplicados - informar al frontend
                        return {
                            "ok": False,
                            "conflict": True,
                            "filename": file.filename,
                            "total_rows": len(mapped_rows),
                            "inserted": inserted,
                            "message": "Se encontraron datos duplicados. Confirma para actualizar.",
                            "parse_errors": parse_errors[:20],
                            "insert_errors": [],
                        }
                    else:
                        insert_errors.append({
                            "batch_start": batch_start,
                            "status": resp.status_code,
                            "error": resp.text[:300],
                        })
                except Exception as e:
                    insert_errors.append({"batch_start": batch_start, "error": str(e)})
    else:
        # Upsert: actualizar duplicados
        inserted, insert_errors = await _upsert_ads(mapped_rows)

    logger.info("Ads upload completado: %d upserted de %d", inserted, len(mapped_rows))

    return {
        "ok": inserted > 0,
        "conflict": False,
        "filename": file.filename,
        "total_rows": len(mapped_rows),
        "inserted": inserted,
        "parse_errors": parse_errors[:20],
        "insert_errors": insert_errors[:10],
    }


@router.delete("/ads")
async def delete_ads(
    asin: str = None,
    country: str = None,
    date_from: str = None,
    date_to: str = None,
    current_user: UserInDB = Depends(get_current_user),
):
    """Elimina registros de ads_data con filtros."""
    url = f"{SUPABASE_URL}/rest/v1/ads_data?"
    filters = []
    if asin:
        filters.append(f"asin=eq.{asin}")
    if country:
        filters.append(f"country_code=eq.{country}")
    if date_from:
        filters.append(f"fecha_inicio=gte.{date_from}")
    if date_to:
        filters.append(f"fecha_fin=lte.{date_to}")

    if not filters:
        raise HTTPException(status_code=400, detail="Especifica al menos un filtro para borrar")

    url += "&".join(filters)
    headers = {**_sb_headers(), "Prefer": "return=representation"}

    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        r = await client.delete(url, headers=headers)
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail=f"Error borrando ads: {r.text[:200]}")
        deleted = r.json() if r.status_code == 200 else []
        return {"deleted": len(deleted)}


@router.get("/asins")
async def list_asins(current_user: UserInDB = Depends(get_current_user)):
    """Lista todos los ASINs disponibles (unión de ventas + cogs + ads)."""
    asins = set()
    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        headers = _sb_headers()

        # ASINs de ventas (distintos)
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/rpc/get_distinct_asins",
            headers=headers,
        )
        # Si la función RPC no existe, fallback a query directa
        if r.status_code != 200:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/ventas?select=ASIN&ASIN=not.is.null",
                headers=headers,
            )
            if r.status_code == 200:
                for row in r.json():
                    if row.get("ASIN"):
                        asins.add(row["ASIN"])
        else:
            for row in r.json():
                if row.get("asin") or row.get("ASIN"):
                    asins.add(row.get("asin") or row.get("ASIN"))

        # ASINs de COGS
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/cogs?select=ASIN",
            headers=headers,
        )
        if r.status_code == 200:
            for row in r.json():
                if row.get("ASIN"):
                    asins.add(row["ASIN"])

        # ASINs de ads
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/ads_data?select=asin",
            headers=headers,
        )
        if r.status_code == 200:
            for row in r.json():
                if row.get("asin"):
                    asins.add(row["asin"])

    return sorted(asins)


@router.get("/countries")
async def list_countries(current_user: UserInDB = Depends(get_current_user)):
    """Lista países disponibles desde ventas y ads."""
    countries = set()
    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        headers = _sb_headers()

        # Países de ventas (SALE_ARRIVAL_COUNTRY)
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/ventas?select=SALE_ARRIVAL_COUNTRY&SALE_ARRIVAL_COUNTRY=not.is.null",
            headers=headers,
        )
        if r.status_code == 200:
            for row in r.json():
                c = row.get("SALE_ARRIVAL_COUNTRY", "").strip()
                if c:
                    countries.add(c)

        # Países de ads
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/ads_data?select=country_code&country_code=not.is.null",
            headers=headers,
        )
        if r.status_code == 200:
            for row in r.json():
                c = row.get("country_code", "").strip()
                if c:
                    countries.add(c)

    return sorted(countries)


@router.get("/categorias")
async def list_categorias(current_user: UserInDB = Depends(get_current_user)):
    """Lista categorías únicas desde la tabla COGS."""
    url = f"{SUPABASE_URL}/rest/v1/cogs?select=categoria&categoria=not.is.null"
    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        r = await client.get(url, headers=_sb_headers())
        if r.status_code != 200:
            return []
        cats = {row["categoria"] for row in r.json() if row.get("categoria")}
    return sorted(cats)


@router.get("/cogs")
async def get_cogs(current_user: UserInDB = Depends(get_current_user)):
    """Obtiene todos los registros de COGS."""
    url = f"{SUPABASE_URL}/rest/v1/cogs?select=*"
    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        r = await client.get(url, headers=_sb_headers())
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Error consultando COGS")
        return r.json()


@router.patch("/cogs/{asin}/{sku}")
async def update_cogs(
    asin: str,
    sku: str,
    data: CogsUpdate,
    current_user: UserInDB = Depends(get_current_user),
):
    """Actualiza los costes de un ASIN/SKU en la tabla COGS."""
    # Mapear nombres Pydantic a nombres de columna en DB
    col_map = {"cost": "Cost"}
    raw = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data = {col_map.get(k, k): v for k, v in raw.items()}
    if not update_data:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")

    update_data["updated_at"] = datetime.utcnow().isoformat()

    url = f"{SUPABASE_URL}/rest/v1/cogs?ASIN=eq.{asin}&SKU=eq.{sku}"
    headers = {**_sb_headers(), "Prefer": "return=representation"}

    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        r = await client.patch(url, headers=headers, json=update_data)
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail=f"Error actualizando COGS: {r.text[:200]}")
        result = r.json()
        if not result:
            raise HTTPException(status_code=404, detail="ASIN/SKU no encontrado en COGS")
        return result[0]


@router.delete("/cogs/{asin}/{sku}")
async def delete_cogs(
    asin: str,
    sku: str,
    current_user: UserInDB = Depends(get_current_user),
):
    """Elimina un registro ASIN/SKU de la tabla COGS."""
    url = f"{SUPABASE_URL}/rest/v1/cogs?ASIN=eq.{asin}&SKU=eq.{sku}"
    headers = {**_sb_headers(), "Prefer": "return=representation"}
    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        r = await client.delete(url, headers=headers)
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail=f"Error eliminando COGS: {r.text[:200]}")
        result = r.json() if r.status_code == 200 else []
        if not result:
            raise HTTPException(status_code=404, detail="ASIN/SKU no encontrado en COGS")
        return {"deleted": True}


@router.get("/ads")
async def get_ads(
    asin: str = None,
    country: str = None,
    date_from: str = None,
    date_to: str = None,
    current_user: UserInDB = Depends(get_current_user),
):
    """Lista datos de ads con filtros opcionales."""
    url = f"{SUPABASE_URL}/rest/v1/ads_data?select=*&order=fecha_inicio.desc"
    if asin:
        url += f"&asin=eq.{asin}"
    if country:
        url += f"&country_code=eq.{country}"
    if date_from:
        url += f"&fecha_fin=gte.{date_from}"
    if date_to:
        url += f"&fecha_inicio=lte.{date_to}"

    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        r = await client.get(url, headers=_sb_headers())
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Error consultando ads")
        return r.json()


@router.post("/analyze")
async def analyze_profitability(
    req: AnalyzeRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Calcula la rentabilidad por ASIN cruzando ventas, COGS y ads.
    """
    headers = _sb_headers()
    async with httpx.AsyncClient(timeout=60, verify=certifi.where()) as client:
        # 0. Si hay filtro de categorías, resolver a ASINs
        effective_asins = list(req.asins)
        if req.categorias:
            cat_filter = ",".join(req.categorias)
            cat_url = f"{SUPABASE_URL}/rest/v1/cogs?select=ASIN&categoria=in.({cat_filter})"
            r_cat = await client.get(cat_url, headers=headers)
            if r_cat.status_code == 200:
                cat_asins = {row["ASIN"] for row in r_cat.json() if row.get("ASIN")}
                if effective_asins:
                    # Intersección: solo ASINs que estén en ambos filtros
                    effective_asins = [a for a in effective_asins if a in cat_asins]
                else:
                    effective_asins = sorted(cat_asins)
                if not effective_asins:
                    # No hay ASINs que coincidan → devolver vacío
                    return {"summary": {"revenue": 0, "total_costs": 0, "net_profit": 0, "margin_pct": 0, "roi": 0, "cost_of_goods": 0, "amazon_referral_fee": 0, "fba_fee": 0, "dst": 0, "ads_spend": 0, "other_costs": 0}, "breakdown": [], "warnings": []}

        # 1. Consultar ventas
        ventas_url = (
            f"{SUPABASE_URL}/rest/v1/ventas"
            f"?select=ASIN,SELLER_SKU,ITEM_DESCRIPTION,SALE_ARRIVAL_COUNTRY,MARKETPLACE,"
            f"QTY,TOTAL_PRICE_OF_ITEMS_AMT_VAT_INCL,TOTAL_PRICE_OF_ITEMS_AMT_VAT_EXCL,"
            f"TRANSACTION_COMPLETE_DATE_DT"
            f"&TRANSACTION_COMPLETE_DATE_DT=gte.{req.date_from}"
            f"&TRANSACTION_COMPLETE_DATE_DT=lte.{req.date_to}"
            f"&TRANSACTION_TYPE=eq.SALE"
            f"&ASIN=not.is.null"
        )
        if effective_asins:
            ventas_url += f"&ASIN=in.({','.join(effective_asins)})"
        if req.countries:
            ventas_url += f"&SALE_ARRIVAL_COUNTRY=in.({','.join(req.countries)})"

        r_ventas = await client.get(ventas_url, headers=headers)
        if r_ventas.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Error consultando ventas: {r_ventas.text[:200]}")
        ventas = r_ventas.json()

        # 2. Consultar COGS
        cogs_url = f"{SUPABASE_URL}/rest/v1/cogs?select=*"
        if effective_asins:
            cogs_url += f"&ASIN=in.({','.join(effective_asins)})"
        r_cogs = await client.get(cogs_url, headers=headers)
        cogs_data = r_cogs.json() if r_cogs.status_code == 200 else []

        # Indexar COGS por ASIN (tomar el primero si hay varios SKUs)
        cogs_by_asin: dict[str, dict] = {}
        for c in cogs_data:
            asin = c.get("ASIN")
            if asin and asin not in cogs_by_asin:
                cogs_by_asin[asin] = c

        # 3. Consultar Ads
        ads_url = (
            f"{SUPABASE_URL}/rest/v1/ads_data?select=*"
            f"&fecha_fin=gte.{req.date_from}"
            f"&fecha_inicio=lte.{req.date_to}"
        )
        if effective_asins:
            ads_url += f"&asin=in.({','.join(effective_asins)})"
        if req.countries:
            ads_url += f"&country_code=in.({','.join(req.countries)})"
        r_ads = await client.get(ads_url, headers=headers)
        ads = r_ads.json() if r_ads.status_code == 200 else []

    # 4. Agregar datos
    # Clave de agrupación
    def _group_key(asin: str, country: str, date_str: str) -> str:
        if req.group_by == "country":
            return country or "???"
        elif req.group_by == "asin_country":
            return f"{asin}|{country}"
        elif req.group_by == "month":
            return date_str[:7] if date_str else "???"
        return asin  # default: asin

    # Agregar ventas
    groups: dict[str, dict] = {}
    for v in ventas:
        asin = v.get("ASIN", "")
        country = v.get("SALE_ARRIVAL_COUNTRY", "")
        date_str = v.get("TRANSACTION_COMPLETE_DATE_DT", "")
        key = _group_key(asin, country, date_str)

        if key not in groups:
            groups[key] = {
                "asin": asin,
                "country": country,
                "title": v.get("ITEM_DESCRIPTION", "")[:80],
                "units": 0,
                "revenue": 0.0,
                "vat": 0.0,
                "cogs": 0.0,
                "amazon_referral_fee": 0.0,
                "fba_fee": 0.0,
                "other_costs": 0.0,
                "dst": 0.0,
                "ads_spend": 0.0,
            }
            if req.group_by == "month":
                groups[key]["month"] = date_str[:7] if date_str else ""
                groups[key]["asin"] = ""
                groups[key]["country"] = ""

        g = groups[key]
        qty = v.get("QTY") or 0
        revenue_vat_incl = _safe_float(v.get("TOTAL_PRICE_OF_ITEMS_AMT_VAT_INCL")) or 0.0
        revenue_vat_excl = _safe_float(v.get("TOTAL_PRICE_OF_ITEMS_AMT_VAT_EXCL")) or 0.0
        vat = revenue_vat_incl - revenue_vat_excl

        g["units"] += qty
        g["revenue"] += revenue_vat_incl
        g["vat"] += vat

        # Aplicar COGS
        cog = cogs_by_asin.get(asin)
        if cog:
            unit_cost = cog.get("Cost") or 0
            ref_fee_pct = cog.get("amazon_referral_fee_pct") or 0
            # FBA fee por país (ES como fallback)
            _fba_country_map = {"ES": "fba_fee_es", "IT": "fba_fee_it", "DE": "fba_fee_de", "FR": "fba_fee_fr"}
            _fba_col = _fba_country_map.get(country, "fba_fee_es")
            fba_fee = cog.get(_fba_col) or cog.get("fba_fee_es") or 0
            other = cog.get("other_fixed_costs") or 0

            g["cogs"] += unit_cost * qty

            # Referral fee: 8% si PVP < 10€, sino el % configurado (default 15%)
            effective_ref_pct = 8.0 if revenue_vat_incl < 10.0 else ref_fee_pct
            referral_amount = revenue_vat_incl * effective_ref_pct / 100
            fba_amount = fba_fee * qty
            g["amazon_referral_fee"] += referral_amount
            g["fba_fee"] += fba_amount

            # Impuesto de servicios digitales (DST) — % sobre referral + FBA
            _dst_rates = {"ES": 0.03, "IT": 0.03, "FR": 0.03, "DE": 0.01}
            dst_rate = _dst_rates.get(country, 0.03)
            g["dst"] += (referral_amount + fba_amount) * dst_rate

            g["other_costs"] += other * qty

    # Agregar ads al grupo correspondiente
    for a in ads:
        asin = a.get("asin", "")
        country = a.get("country_code", "")
        date_str = a.get("fecha_inicio", "")
        key = _group_key(asin, country, date_str)

        if key in groups:
            groups[key]["ads_spend"] += a.get("spend") or 0
        else:
            # Ads sin ventas en ese periodo - crear grupo solo con gasto
            groups[key] = {
                "asin": asin,
                "country": country,
                "title": "",
                "units": 0,
                "revenue": 0.0,
                "vat": 0.0,
                "cogs": 0.0,
                "amazon_referral_fee": 0.0,
                "fba_fee": 0.0,
                "other_costs": 0.0,
                "dst": 0.0,
                "ads_spend": a.get("spend") or 0,
            }

    # 5. Calcular rentabilidad por grupo
    breakdown = []
    warnings = []
    asins_without_cogs = set()

    for key, g in groups.items():
        total_costs = g["vat"] + g["cogs"] + g["amazon_referral_fee"] + g["fba_fee"] + g["other_costs"] + g["dst"] + g["ads_spend"]
        net_profit = g["revenue"] - total_costs
        margin_pct = (net_profit / g["revenue"] * 100) if g["revenue"] > 0 else 0
        profit_per_unit = (net_profit / g["units"]) if g["units"] > 0 else 0
        acos_real = (g["ads_spend"] / g["revenue"] * 100) if g["revenue"] > 0 else 0
        roi = (net_profit / total_costs * 100) if total_costs > 0 else 0

        entry = {
            **g,
            "total_costs": round(total_costs, 2),
            "net_profit": round(net_profit, 2),
            "margin_pct": round(margin_pct, 2),
            "profit_per_unit": round(profit_per_unit, 2),
            "acos_real": round(acos_real, 2),
            "roi": round(roi, 2),
        }
        # Redondear todos los valores monetarios
        for field in ("revenue", "vat", "cogs", "amazon_referral_fee", "fba_fee", "other_costs", "dst", "ads_spend"):
            entry[field] = round(entry[field], 2)

        breakdown.append(entry)

        if g["asin"] and g["asin"] not in cogs_by_asin and g["asin"] not in asins_without_cogs:
            asins_without_cogs.add(g["asin"])
            warnings.append(f"ASIN {g['asin']} no tiene COGS configurado")

    # Ordenar por revenue descendente
    breakdown.sort(key=lambda x: x["revenue"], reverse=True)

    # 6. Resumen global
    summary = {
        "total_revenue": round(sum(b["revenue"] for b in breakdown), 2),
        "total_units": sum(b["units"] for b in breakdown),
        "total_vat": round(sum(b["vat"] for b in breakdown), 2),
        "total_cogs": round(sum(b["cogs"] for b in breakdown), 2),
        "total_amazon_fees": round(sum(b["amazon_referral_fee"] + b["fba_fee"] + b["other_costs"] + b["dst"] for b in breakdown), 2),
        "total_dst": round(sum(b["dst"] for b in breakdown), 2),
        "total_ads_spend": round(sum(b["ads_spend"] for b in breakdown), 2),
        "total_costs": round(sum(b["total_costs"] for b in breakdown), 2),
        "net_profit": round(sum(b["net_profit"] for b in breakdown), 2),
    }
    summary["margin_pct"] = round(
        (summary["net_profit"] / summary["total_revenue"] * 100) if summary["total_revenue"] > 0 else 0, 2
    )
    summary["roi"] = round(
        (summary["net_profit"] / summary["total_costs"] * 100) if summary["total_costs"] > 0 else 0, 2
    )

    return {
        "summary": summary,
        "breakdown": breakdown,
        "warnings": warnings,
    }
