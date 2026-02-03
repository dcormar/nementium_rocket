# consulta_web_tools.py
# Herramientas de búsqueda online para el agente de consulta

import logging
import asyncio
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from langchain.tools import tool
import httpx

logger = logging.getLogger(__name__)

# Timeout por defecto para búsquedas web (segundos)
DEFAULT_WEB_SEARCH_TIMEOUT = 15

# Serper.dev API key (fallback cuando DuckDuckGo falla)
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
SERPER_API_URL = "https://google.serper.dev/search"

try:
    from duckduckgo_search import DDGS
    DDG_AVAILABLE = True
except ImportError:
    DDG_AVAILABLE = False
    logger.warning("duckduckgo-search no está instalado.")

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("beautifulsoup4 no está instalado. fetch_url no disponible.")


def _serper_search_sync(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Búsqueda usando Serper.dev (Google Search API).
    Usado como fallback cuando DuckDuckGo falla.
    """
    if not SERPER_API_KEY:
        logger.warning("[SERPER] API key no configurada (SERPER_API_KEY)")
        return []

    try:
        response = httpx.post(
            SERPER_API_URL,
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "q": query,
                "num": max_results,
                "gl": "es",  # España
                "hl": "es"   # Español
            },
            timeout=10.0
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("organic", [])[:max_results]:
            results.append({
                "name": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", "")
            })

        logger.info(f"[SERPER] Encontrados {len(results)} resultados para: {query[:50]}...")
        return results

    except httpx.TimeoutException:
        logger.warning(f"[SERPER] Timeout para query: {query}")
        return []
    except Exception as e:
        logger.error(f"[SERPER] Error en búsqueda: {e}")
        return []


def _web_search_sync(query: str, max_results: int = 5, timeout: int = DEFAULT_WEB_SEARCH_TIMEOUT) -> List[Dict[str, str]]:
    """
    Función interna síncrona para búsqueda web.
    Intenta primero con DuckDuckGo, si falla usa Serper.dev como fallback.
    """
    if max_results > 10:
        max_results = 10
    if max_results < 1:
        max_results = 5

    results = []

    # 1. Intentar con DuckDuckGo primero
    if DDG_AVAILABLE:
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "name": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")
                    })
            if results:
                logger.debug(f"[WEB_SEARCH] DDG encontró {len(results)} resultados")
                return results
        except Exception as e:
            logger.warning(f"[WEB_SEARCH] DuckDuckGo falló ({e}), intentando Serper...")

    # 2. Fallback a Serper.dev si DDG no disponible o falló/vacío
    if not results and SERPER_API_KEY:
        logger.info(f"[WEB_SEARCH] Usando Serper.dev como fallback para: {query[:50]}...")
        results = _serper_search_sync(query, max_results)

    return results


@tool
def web_search(query: str, max_results: int = 5, timeout: int = DEFAULT_WEB_SEARCH_TIMEOUT) -> List[Dict[str, str]]:
    """
    Busca información en internet usando un motor de búsqueda.
    Útil para verificar datos de proveedores, obtener tipos de cambio,
    buscar información contextual sobre facturas, etc.

    Args:
        query: Términos de búsqueda (ej: "Amazon España NIF", "tipo cambio USD EUR")
        max_results: Número máximo de resultados a retornar (default: 5, máx: 10)
        timeout: Timeout en segundos (default: 15)

    Returns:
        Lista de diccionarios con:
        - url: URL del resultado
        - snippet: Fragmento de texto relevante
        - name: Nombre/título del resultado
    """
    if not DDG_AVAILABLE:
        logger.warning("[WEB_SEARCH] DuckDuckGo no disponible, retornando lista vacía")
        return []

    logger.info(f"[WEB_SEARCH] Buscando: {query} (max_results={max_results}, timeout={timeout}s)")

    try:
        # Ejecutar búsqueda con timeout usando ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_web_search_sync, query, max_results, timeout)
            try:
                results = future.result(timeout=timeout)
                logger.info(f"[WEB_SEARCH] Encontrados {len(results)} resultados")
                return results
            except TimeoutError:
                logger.warning(f"[WEB_SEARCH] Timeout ({timeout}s) para query: {query}")
                return []
    except Exception as e:
        logger.error(f"[WEB_SEARCH] Error en búsqueda: {e}")
        return []


async def web_search_async(query: str, max_results: int = 5, timeout: int = DEFAULT_WEB_SEARCH_TIMEOUT) -> List[Dict[str, str]]:
    """
    Versión asíncrona de web_search para uso con asyncio.gather.
    Permite ejecutar múltiples búsquedas en paralelo.

    Args:
        query: Términos de búsqueda
        max_results: Número máximo de resultados (default: 5, máx: 10)
        timeout: Timeout en segundos (default: 15)

    Returns:
        Lista de diccionarios con resultados (lista vacía si timeout o error)
    """
    if not DDG_AVAILABLE:
        logger.warning("[WEB_SEARCH_ASYNC] DuckDuckGo no disponible, retornando lista vacía")
        return []

    logger.info(f"[WEB_SEARCH_ASYNC] Buscando: {query} (max_results={max_results}, timeout={timeout}s)")

    try:
        loop = asyncio.get_event_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(None, _web_search_sync, query, max_results, timeout),
            timeout=timeout
        )
        logger.info(f"[WEB_SEARCH_ASYNC] Encontrados {len(results)} resultados para: {query[:50]}...")
        return results
    except asyncio.TimeoutError:
        logger.warning(f"[WEB_SEARCH_ASYNC] Timeout ({timeout}s) para query: {query}")
        return []
    except Exception as e:
        logger.error(f"[WEB_SEARCH_ASYNC] Error en búsqueda: {e}")
        return []


@tool
def search_exchange_rate(
    currency_from: str, 
    currency_to: str, 
    date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Busca el tipo de cambio entre dos monedas.
    Si no se especifica fecha, busca el tipo de cambio actual.
    
    Args:
        currency_from: Moneda origen (ej: "USD", "GBP", "EUR")
        currency_to: Moneda destino (ej: "EUR")
        date: Fecha en formato YYYY-MM-DD (opcional, default: hoy)
    
    Returns:
        Dict con:
        - rate: Tipo de cambio (float)
        - date: Fecha del tipo de cambio
        - currency_from: Moneda origen
        - currency_to: Moneda destino
        - source: Fuente de la información
    """
    if not DDG_AVAILABLE:
        raise ValueError("Búsqueda web no disponible: duckduckgo-search no está instalado")
    
    # Normalizar códigos de moneda
    currency_from = currency_from.upper().strip()
    currency_to = currency_to.upper().strip()
    
    # Construir query de búsqueda
    if date:
        query = f"tipo de cambio {currency_from} {currency_to} {date}"
    else:
        query = f"tipo de cambio {currency_from} {currency_to} hoy"
    
    logger.info(f"[EXCHANGE_RATE] Buscando tipo de cambio: {currency_from} -> {currency_to} ({date or 'hoy'})")
    
    try:
        # Buscar información del tipo de cambio
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        
        if not results:
            raise ValueError(f"No se encontró información del tipo de cambio {currency_from}/{currency_to}")
        
        # Intentar extraer el tipo de cambio del primer resultado
        # Esto es una aproximación - en producción podrías usar una API especializada
        first_result = results[0]
        snippet = first_result.get("body", "").lower()
        
        # Buscar números que parezcan tipos de cambio (ej: "1 USD = 0.92 EUR")
        import re
        # Patrón: número seguido de moneda = número seguido de moneda
        pattern = r'(\d+\.?\d*)\s*(?:usd|eur|gbp|usd|eur|gbp)'
        matches = re.findall(pattern, snippet)
        
        # Si no encontramos patrón claro, retornar información básica
        rate = None
        if matches and len(matches) >= 2:
            try:
                # Intentar calcular ratio
                val1 = float(matches[0])
                val2 = float(matches[1])
                if currency_from == "EUR" and currency_to != "EUR":
                    rate = val2 / val1 if val1 != 0 else None
                else:
                    rate = val1 / val2 if val2 != 0 else None
            except (ValueError, ZeroDivisionError):
                pass
        
        result = {
            "currency_from": currency_from,
            "currency_to": currency_to,
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "rate": rate,
            "source": first_result.get("href", ""),
            "snippet": first_result.get("body", "")[:200]  # Primeros 200 chars
        }
        
        logger.info(f"[EXCHANGE_RATE] Tipo de cambio encontrado: {rate}")
        return result
        
    except Exception as e:
        logger.error(f"[EXCHANGE_RATE] Error buscando tipo de cambio: {e}")
        raise ValueError(f"Error buscando tipo de cambio: {str(e)}")


@tool
def verify_company_info(company_name: str, country: Optional[str] = None) -> Dict[str, Any]:
    """
    Verifica información de una empresa/proveedor en internet.
    Busca NIF/VAT, dirección, información de contacto, etc.
    
    Args:
        company_name: Nombre de la empresa (ej: "Amazon España", "Meta Platforms")
        country: País (opcional, para refinar búsqueda, ej: "España", "ES")
    
    Returns:
        Dict con información encontrada:
        - company_name: Nombre de la empresa
        - nif_vat: NIF/VAT encontrado (si aplica)
        - address: Dirección (si encontrada)
        - website: Sitio web
        - snippets: Fragmentos de texto relevantes
        - sources: URLs de las fuentes
    """
    if not DDG_AVAILABLE:
        raise ValueError("Búsqueda web no disponible: duckduckgo-search no está instalado")
    
    # Construir query de búsqueda
    if country:
        query = f"{company_name} {country} NIF VAT información empresa"
    else:
        query = f"{company_name} NIF VAT información empresa"
    
    logger.info(f"[VERIFY_COMPANY] Verificando información de: {company_name} ({country or 'sin país'})")
    
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        
        if not results:
            return {
                "company_name": company_name,
                "nif_vat": None,
                "address": None,
                "website": None,
                "snippets": [],
                "sources": [],
                "found": False
            }
        
        # Extraer información de los resultados
        snippets = [r.get("body", "") for r in results]
        sources = [r.get("href", "") for r in results]
        
        # Buscar NIF/VAT en los snippets
        import re
        nif_vat = None
        # Patrones comunes: B12345678, ESB12345678, VAT: ES123456789
        nif_patterns = [
            r'\b([A-Z]\d{8})\b',  # B12345678
            r'\b(ES[A-Z]\d{8})\b',  # ESB12345678
            r'VAT[:\s]+([A-Z]{2}?\d{8,9})',  # VAT: ES123456789
            r'NIF[:\s]+([A-Z]?\d{8,9})',  # NIF: B12345678
        ]
        
        for snippet in snippets:
            for pattern in nif_patterns:
                match = re.search(pattern, snippet, re.IGNORECASE)
                if match:
                    nif_vat = match.group(1).upper()
                    break
            if nif_vat:
                break
        
        # Buscar dirección (patrón básico)
        address = None
        address_pattern = r'(Calle|Avenida|Av\.|Plaza|Paseo)[\s\w,]+(?:Madrid|Barcelona|Valencia|Sevilla|España)'
        for snippet in snippets:
            match = re.search(address_pattern, snippet, re.IGNORECASE)
            if match:
                address = match.group(0)
                break
        
        # Buscar website
        website = None
        url_pattern = r'https?://(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})'
        for source in sources:
            match = re.search(url_pattern, source)
            if match:
                website = match.group(0)
                break
        
        result = {
            "company_name": company_name,
            "nif_vat": nif_vat,
            "address": address,
            "website": website,
            "snippets": snippets[:3],  # Primeros 3 snippets
            "sources": sources[:3],  # Primeras 3 fuentes
            "found": True
        }
        
        logger.info(f"[VERIFY_COMPANY] Información encontrada - NIF: {nif_vat}, Website: {website}")
        return result
        
    except Exception as e:
        logger.error(f"[VERIFY_COMPANY] Error verificando empresa: {e}")
        raise ValueError(f"Error verificando información de empresa: {str(e)}")


@tool
async def fetch_url(url: str, max_chars: int = 5000) -> Dict[str, Any]:
    """
    Obtiene el contenido de una URL y extrae el texto limpio.
    Útil para analizar páginas web de empresas, perfiles de LinkedIn, etc.
    
    Args:
        url: URL completa a visitar (ej: "https://empresa.com/about")
        max_chars: Máximo de caracteres a retornar (default: 5000)
    
    Returns:
        Dict con:
        - url: URL visitada
        - title: Título de la página
        - content: Texto limpio extraído (limitado a max_chars)
        - success: Si la extracción fue exitosa
        - error: Mensaje de error si falló
    """
    if not BS4_AVAILABLE:
        return {
            "url": url,
            "title": "",
            "content": "",
            "success": False,
            "error": "beautifulsoup4 no está instalado"
        }
    
    # Validar URL
    if not url.startswith(("http://", "https://")):
        return {
            "url": url,
            "title": "",
            "content": "",
            "success": False,
            "error": "URL debe comenzar con http:// o https://"
        }
    
    # Limitar max_chars
    if max_chars > 10000:
        max_chars = 10000
    if max_chars < 500:
        max_chars = 500
    
    logger.info(f"[FETCH_URL] Obteniendo contenido de: {url}")
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        }
        
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
        
        # Parsear HTML
        soup = BeautifulSoup(response.text, "lxml")
        
        # Obtener título
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        
        # Eliminar scripts, styles y otros elementos no relevantes
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
            element.decompose()
        
        # Extraer texto
        text = soup.get_text(separator=" ", strip=True)
        
        # Limpiar espacios múltiples
        import re
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Limitar caracteres
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        
        logger.info(f"[FETCH_URL] Extraídos {len(text)} caracteres de {url}")
        
        return {
            "url": url,
            "title": title,
            "content": text,
            "success": True,
            "error": None
        }
        
    except httpx.TimeoutException:
        logger.error(f"[FETCH_URL] Timeout al obtener {url}")
        return {
            "url": url,
            "title": "",
            "content": "",
            "success": False,
            "error": "Timeout al cargar la página"
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"[FETCH_URL] Error HTTP {e.response.status_code} al obtener {url}")
        return {
            "url": url,
            "title": "",
            "content": "",
            "success": False,
            "error": f"Error HTTP {e.response.status_code}"
        }
    except Exception as e:
        logger.error(f"[FETCH_URL] Error al obtener {url}: {e}")
        return {
            "url": url,
            "title": "",
            "content": "",
            "success": False,
            "error": str(e)
        }


# Lista de herramientas de búsqueda web
WEB_SEARCH_TOOLS = [web_search, search_exchange_rate, verify_company_info, fetch_url]

# Exportar también funciones async para uso directo
__all__ = ['web_search', 'web_search_async', 'search_exchange_rate', 'verify_company_info', 'fetch_url', 'WEB_SEARCH_TOOLS', 'DEFAULT_WEB_SEARCH_TIMEOUT']
