
import httpx
import logging, os
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import certifi

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ventas", tags=["ventas"])

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

@router.get("/", response_model=List[Venta])
async def get_ventas(
    desde: str = Query(None, description="Fecha inicio YYYY-MM-DD"),
    hasta: str = Query(None, description="Fecha fin YYYY-MM-DD")
):
    logger.debug(f"Recibida petición de ventas desde={desde} hasta={hasta}")
    url = f"{SUPABASE_URL}/rest/v1/ventas"
    params = []
    if desde:
        params.append(f"TRANSACTION_COMPLETE_DATE_DT=gte.{desde}")
    if hasta:
        params.append(f"TRANSACTION_COMPLETE_DATE_DT=lte.{hasta}")
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
async def add_venta(venta: Venta):
    url = f"{SUPABASE_URL}/rest/v1/ventas"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        r = await client.post(url, headers=headers, json=venta.dict(exclude_unset=True))
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Error insertando en Supabase")
        return r.json()[0] if isinstance(r.json(), list) else r.json()
