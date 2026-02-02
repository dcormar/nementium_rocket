# supabase_rest.py
# Wrapper para llamadas REST a Supabase usando httpx

import os
import re
import httpx
import urllib.parse
from typing import Any, Dict, List, Optional

def _validate_supabase_env():
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not re.match(r"^https://[a-z0-9\-]+\.supabase\.co$", url):
        raise ValueError("SUPABASE_URL inválida")
    if not re.match(r"^sb_secret_[A-Za-z0-9_\-]+$|^eyJ[^.]+\.[^.]+\.[^.]+$", key):
        raise ValueError("SUPABASE key inválida (sb_secret_ o JWT legacy)")
    return url, key

class SupabaseREST:
    def __init__(self, timeout=15.0):
        self.base_url, self.key = _validate_supabase_env()
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.base_url}/rest/v1/{path.lstrip('/')}"

    async def get(
        self, 
        table: str, 
        select: str, 
        params: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Realiza una consulta GET a una tabla.
        
        Args:
            table: Nombre de la tabla
            select: Campos a seleccionar (ej: "id,nombre,email")
            params: Diccionario de filtros (ej: {"username": "eq.david", "activo": "eq.true"})
        
        Returns:
            Lista de registros
        """
        if params and len(params) > 0:
            # Codificar valores de parámetros
            encoded_params = []
            for k, v in params.items():
                # Si el valor ya tiene el operador (eq., ne., etc.), usarlo directamente
                if isinstance(v, str) and ("eq." in v or "ne." in v or "gt." in v or "lt." in v or "like." in v):
                    encoded_params.append(f"{k}={urllib.parse.quote(v, safe='')}")
                elif isinstance(v, bool):
                    # Valores booleanos: true o false (sin comillas en PostgREST)
                    encoded_params.append(f"{k}=eq.{str(v).lower()}")
                else:
                    # Por defecto, usar eq. y codificar el valor
                    encoded_params.append(f"{k}=eq.{urllib.parse.quote(str(v), safe='')}")
            query_str = "&".join(encoded_params)
            url = self._url(f"{table}?select={select}&{query_str}")
        else:
            url = self._url(f"{table}?select={select}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(url, headers=self.headers)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []

    async def get_single(
        self,
        table: str,
        select: str,
        params: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene un solo registro. Si hay múltiples, devuelve el primero.
        """
        results = await self.get(table, select, params)
        return results[0] if results else None

    async def post(
        self,
        table: str,
        data: Dict[str, Any],
        return_representation: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Inserta un nuevo registro.
        
        Args:
            table: Nombre de la tabla
            data: Datos a insertar
            return_representation: Si True, devuelve el registro insertado
        
        Returns:
            Lista con el registro insertado
        """
        headers = self.headers.copy()
        if return_representation:
            headers["Prefer"] = "return=representation"
        
        url = self._url(table)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, headers=headers, json=data)
        r.raise_for_status()
        result = r.json()
        return result if isinstance(result, list) else [result] if result else []

    async def patch(
        self,
        table: str,
        data: Dict[str, Any],
        params: Optional[Dict[str, str]] = None,
        return_representation: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Actualiza registros.
        
        Args:
            table: Nombre de la tabla
            data: Datos a actualizar
            params: Filtros para seleccionar qué registros actualizar
            return_representation: Si True, devuelve los registros actualizados
        
        Returns:
            Lista de registros actualizados
        """
        headers = self.headers.copy()
        if return_representation:
            headers["Prefer"] = "return=representation"
        
        if params and len(params) > 0:
            encoded_params = []
            for k, v in params.items():
                if isinstance(v, str) and ("eq." in v or "ne." in v):
                    encoded_params.append(f"{k}={urllib.parse.quote(v, safe='')}")
                elif isinstance(v, bool):
                    # Valores booleanos: true o false (sin comillas en PostgREST)
                    encoded_params.append(f"{k}=eq.{str(v).lower()}")
                else:
                    encoded_params.append(f"{k}=eq.{urllib.parse.quote(str(v), safe='')}")
            query_str = "&".join(encoded_params)
            url = self._url(f"{table}?{query_str}")
        else:
            url = self._url(table)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.patch(url, headers=headers, json=data)
        r.raise_for_status()
        # PostgREST devuelve cuerpo vacío (204) si no se usa Prefer: return=representation
        if not r.content or r.content.strip() == b"":
            return []
        result = r.json()
        return result if isinstance(result, list) else [result] if result else []

    async def delete(
        self,
        table: str,
        params: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Elimina registros.
        
        Args:
            table: Nombre de la tabla
            params: Filtros para seleccionar qué registros eliminar
        
        Returns:
            Lista de registros eliminados
        """
        if params and len(params) > 0:
            encoded_params = []
            for k, v in params.items():
                if isinstance(v, str) and ("eq." in v or "ne." in v):
                    encoded_params.append(f"{k}={urllib.parse.quote(v, safe='')}")
                elif isinstance(v, bool):
                    # Valores booleanos: true o false (sin comillas en PostgREST)
                    encoded_params.append(f"{k}=eq.{str(v).lower()}")
                else:
                    encoded_params.append(f"{k}=eq.{urllib.parse.quote(str(v), safe='')}")
            query_str = "&".join(encoded_params)
            url = self._url(f"{table}?{query_str}")
        else:
            url = self._url(table)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.delete(url, headers=self.headers)
        r.raise_for_status()
        if not r.content or r.content.strip() == b"":
            return []
        result = r.json()
        return result if isinstance(result, list) else [result] if result else []

    async def rpc(
        self,
        function_name: str,
        params: Dict[str, Any]
    ) -> Any:
        """
        Llama a una función RPC de PostgreSQL.
        
        Args:
            function_name: Nombre de la función
            params: Parámetros de la función
        
        Returns:
            Resultado de la función
        """
        url = self._url(f"rpc/{function_name}")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, headers=self.headers, json=params)
        r.raise_for_status()
        return r.json()
