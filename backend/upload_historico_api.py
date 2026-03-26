from fastapi import APIRouter, HTTPException, Depends
import httpx, os, logging
from pydantic import BaseModel
from typing import List, Optional
from auth import get_current_user, UserInDB
import certifi

router = APIRouter(prefix="/api/uploads", tags=["uploads"])
logger = logging.getLogger(__name__)

class UploadItem(BaseModel):
    id: str
    fecha: str
    tipo: str
    descripcion: str
    tam_bytes: Optional[int]
    storage_path: Optional[str]
    status: Optional[str] = None
    original_filename: str

class UploadsResponse(BaseModel):
    items: List[UploadItem]
    total: int
    page: int
    total_pages: int

@router.get("/historico", response_model=UploadsResponse)
async def uploads_historico(
    limit: int = 20,
    offset: int = 0,
    order_by: str = "fecha",
    order_dir: str = "desc",
    tz: str = "Europe/Madrid",
    current_user: UserInDB = Depends(get_current_user),
):
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not supabase_url or not supabase_key:
        raise HTTPException(status_code=500, detail="Config supabase incompleta")

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }

    # Validar order_by y order_dir
    valid_order_by = ["fecha", "tipo", "original_filename", "tam_bytes", "status"]
    if order_by not in valid_order_by:
        order_by = "fecha"
    
    order_dir = order_dir.lower()
    if order_dir not in ["asc", "desc"]:
        order_dir = "desc"

    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        # Obtener total de registros
        count_resp = await client.get(
            f"{supabase_url}/rest/v1/uploads?select=id",
            headers={**headers, "Prefer": "count=exact"}
        )
        total = int(count_resp.headers.get("content-range", "0").split("/")[-1]) if count_resp.status_code == 200 else 0

        # Mapear columnas de ordenamiento
        column_mapping = {
            "fecha": "created_at",
            "tipo": "tipo",
            "original_filename": "original_filename",
            "tam_bytes": "file_size_bytes",
            "status": "status"
        }
        order_column = column_mapping.get(order_by, "created_at")
        
        # Obtener uploads con factura_id para luego obtener descripciones
        query_url = (
            f"{supabase_url}/rest/v1/uploads"
            f"?select=id,created_at,tipo,original_filename,file_size_bytes,storage_path,status,factura_id"
            f"&order={order_column}.{order_dir}"
            f"&limit={limit}"
            f"&offset={offset}"
        )
        
        resp = await client.get(query_url, headers=headers)

        if resp.status_code != 200:
            logger.error("📛 Query uploads falló %s: %s", resp.status_code, resp.text)
            raise HTTPException(status_code=502, detail=resp.text)

        rows = resp.json() or []
        logger.info("📦 Query uploads devolvió %d filas (total: %d)", len(rows), total)
        
        # Obtener descripciones desde facturas si hay factura_id
        factura_ids = [r.get("factura_id") for r in rows if r.get("factura_id")]
        descripciones_map = {}
        
        if factura_ids:
            # Obtener facturas en batch
            factura_ids_str = ",".join(str(fid) for fid in factura_ids)
            facturas_resp = await client.get(
                f"{supabase_url}/rest/v1/facturas?id=in.({factura_ids_str})&select=id,descripcion",
                headers=headers
            )
            if facturas_resp.status_code == 200:
                facturas = facturas_resp.json() or []
                descripciones_map = {f["id"]: f.get("descripcion") or "Pending Processing" for f in facturas}
        
        # Calcular página actual y total de páginas
        page = (offset // limit) + 1 if limit > 0 else 1
        total_pages = (total + limit - 1) // limit if limit > 0 else 1
        
        return {
            "items": [
                {
                    "id": r["id"],
                    "fecha": r.get("created_at", ""),
                    "tipo": r.get("tipo", ""),
                    "descripcion": descripciones_map.get(r.get("factura_id")) or "Pending Processing",
                    "tam_bytes": r.get("file_size_bytes"),
                    "storage_path": r.get("storage_path"),
                    "status": r.get("status"),
                    "original_filename": r.get("original_filename") or "",
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "total_pages": total_pages,
        }

@router.get("/{upload_id}/factura")
async def get_factura_from_upload(
    upload_id: str,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Obtiene los detalles de la factura asociada a un upload.
    """
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not supabase_url or not supabase_key:
        raise HTTPException(status_code=500, detail="Config supabase incompleta")

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
            # Primero obtener el factura_id del upload
            upload_resp = await client.get(
                f"{supabase_url}/rest/v1/uploads?id=eq.{upload_id}&select=factura_id,tipo",
                headers=headers
            )
            
            if upload_resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Error obteniendo upload: {upload_resp.text}")
            
            upload_rows = upload_resp.json()
            if not upload_rows:
                raise HTTPException(status_code=404, detail="Upload no encontrado")
            
            upload = upload_rows[0]
            factura_id = upload.get("factura_id")
            tipo = upload.get("tipo")
            
            # Si no es una factura, retornar null
            if tipo != "FACTURA":
                return {"factura": None, "factura_id": None}
            
            # Si no tiene factura_id, retornar null pero con factura_id None
            if not factura_id:
                return {"factura": None, "factura_id": None}
            
            # Obtener los detalles de la factura
            factura_resp = await client.get(
                f"{supabase_url}/rest/v1/facturas?id=eq.{factura_id}",
                headers=headers
            )
            
            if factura_resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Error obteniendo factura: {factura_resp.text}")
            
            factura_rows = factura_resp.json()
            if not factura_rows:
                return {"factura": None, "factura_id": factura_id}
            
            return {"factura": factura_rows[0], "factura_id": factura_id}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error obteniendo factura desde upload %s", upload_id)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")