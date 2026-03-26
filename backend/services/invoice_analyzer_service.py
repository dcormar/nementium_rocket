# invoice_analyzer_service.py
# Servicio para extraer datos de facturas usando Google Gemini con fallback a OpenAI

import os
import logging
import base64
from datetime import datetime
from typing import Optional
from pathlib import Path

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
import openai

# Reducir el logging de OpenAI
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Configuración
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Configurar la API de Gemini
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)


EXTRACTION_PROMPT = """Mi empresa es David Cortijo Martín, que es el receptor de la factura.

A partir del documento de factura proporcionado, extrae los siguientes campos y devuelve un objeto JSON con los campos en el orden exacto listado a continuación:

Campos a extraer:
- tipo: clasifica el documento como "factura" o "venta"
- id_factura: número o identificador único de la factura
- proveedor_vat: NIF o VAT del proveedor. Si no aparece, usa "N/A"
- fecha: fecha de emisión en formato DD/MM/YYYY (ej: 15/01/2024)
- categoria: clasifica el gasto en una de estas categorías:
    • Nota de Crédito
    • Tarifas de Logística de Amazon
    • Tarifas de Vender en Amazon
    • Tarifas de Anuncios de Amazon
    • Software
    • Hardware
    • Servicios profesionales
    • Marketing
    • Viajes
    • Material de oficina
    • Otros (especificar en notas)
- proveedor: nombre de la empresa o persona que emitió la factura (NO es David Cortijo Martín, sino la entidad emisora)
- descripcion: breve explicación del producto o servicio prestado. IMPORTANTE: SIEMPRE traducir al español, aunque la factura esté en otro idioma
- importe_sin_iva: precio neto total antes de IVA (número con punto decimal, sin símbolos de moneda. Ej: 1200.00)
- iva_porcentaje: porcentaje de IVA aplicado (número. Ej: 21). Si no hay IVA, usar 0
- importe_total: importe total con IVA incluido (número con punto decimal, sin símbolos de moneda. Ej: 1452.00)
- moneda: código de moneda ISO en mayúsculas (EUR, USD, GBP, etc.)
- tipo_cambio: ratio Euro/moneda local si aparece en el documento, o null si la moneda es EUR
- pais_origen: país desde el que se emite la factura, en formato ISO 3166-2 (ES, FR, DE, etc.)
- notas: cualquier anotación relevante para contabilidad o aclaraciones, siempre en idioma español. Si no aplica, usa "N/A"

--- CLASIFICACIÓN FISCAL (para modelos de Hacienda) ---
Analiza la factura y determina los siguientes campos fiscales. Usa la información del NIF/VAT del proveedor, la dirección, el tipo de servicio/bien, y el IVA aplicado para clasificar:

- pais_factura: código ISO del país del proveedor, deducido del NIF/VAT (ej: "ES" si empieza por ES, "FR" si empieza por FR, "DE" si empieza por DE, etc.). Si no hay NIF, deducir de la dirección. Formato: código ISO 3166-2 de 2 letras.
- pais_ue: "SI" si el país del proveedor pertenece a la UE (los 27 estados miembros actuales), "NO" si no.
- tipo_adquisicion: clasificar como:
    • "Gasto" si es un pago a instituciones públicas sin IVA asociado, un DUA (documento único administrativo de aduanas), o similar
    • "Bienes" si se adquieren productos físicos/tangibles
    • "Servicios" si se contratan servicios (software, consultoría, logística, publicidad, etc.)
- servicio_intracomunitario_sin_iva: "SI" si es un servicio recibido de un proveedor de la UE (no España) SIN IVA repercutido (IVA = 0 y proveedor UE no español). "NO" en cualquier otro caso.
- servicio_extracomunitario_sin_iva: "SI" si es un servicio recibido de un proveedor fuera de la UE SIN IVA. "NO" en cualquier otro caso.
- inversion_sujeto_pasivo: "SI" si aplica inversión del sujeto pasivo (servicios intracomunitarios o extracomunitarios sin IVA donde el receptor debe autorepercutirse el IVA). "NO" en cualquier otro caso.
- dua: "SI" si el documento es un DUA (Documento Único Administrativo) de importación. "NO" en cualquier otro caso.
- gasto_nacional_iva_deducible: "SI" si es un gasto de un proveedor español con IVA repercutido deducible (IVA > 0 y proveedor español). "NO" en cualquier otro caso.

Ejemplo de respuesta esperada:
{"tipo": "factura", "id_factura": "FAC-2024-001", "proveedor_vat": "B12345678", "fecha": "15/01/2024", "categoria": "Software", "proveedor": "Empresa S.L.", "descripcion": "Licencia anual de software", "importe_sin_iva": 100.00, "iva_porcentaje": 21, "importe_total": 121.00, "moneda": "EUR", "tipo_cambio": null, "pais_origen": "ES", "notas": "N/A", "pais_factura": "ES", "pais_ue": "SI", "tipo_adquisicion": "Servicios", "servicio_intracomunitario_sin_iva": "NO", "servicio_extracomunitario_sin_iva": "NO", "inversion_sujeto_pasivo": "NO", "dua": "NO", "gasto_nacional_iva_deducible": "SI"}

IMPORTANTE:
- Responde ÚNICAMENTE con el JSON, sin texto adicional ni markdown.
- Ningún campo debe quedar vacío: usa "N/A" donde no haya datos.
- Para los campos SI/NO, usa exactamente "SI" o "NO" (sin tilde).
- Mantén el orden exacto de los campos.
- Los campos "descripcion" y "notas" DEBEN estar SIEMPRE en español, traducidos si es necesario."""


def _parse_json_response(text: str) -> dict:
    """Parsea la respuesta JSON de la IA, limpiando posibles artefactos"""
    import json
    
    # Limpiar posibles markdown code blocks
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Error parseando JSON: {e}\nTexto: {text[:500]}")
        raise ValueError(f"Respuesta de IA no es JSON válido: {str(e)}")


def _is_rate_limit_error(error: Exception) -> bool:
    """Detecta si el error es un rate limit (429)"""
    error_str = str(error).lower()
    
    # Detectar errores de rate limit de diferentes formas
    if "429" in error_str:
        return True
    if "resource exhausted" in error_str:
        return True
    if "quota" in error_str:
        return True
    if "rate limit" in error_str:
        return True
    if isinstance(error, google_exceptions.ResourceExhausted):
        return True
    
    return False


async def _extract_with_gemini(file_path: Path) -> str:
    """
    Extrae datos usando Gemini.
    Retorna el texto de respuesta o lanza excepción.
    """
    # Subir el archivo a Gemini
    logger.info(f"[Gemini] Subiendo archivo: {file_path.name}")
    uploaded_file = genai.upload_file(file_path)
    logger.info(f"[Gemini] Archivo subido correctamente")
    
    try:
        # Crear el modelo y generar contenido
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        response = model.generate_content([uploaded_file, EXTRACTION_PROMPT])
        return response.text
    finally:
        # Limpiar el archivo subido
        try:
            genai.delete_file(uploaded_file.name)
            logger.debug(f"[Gemini] Archivo temporal eliminado")
        except Exception as e:
            logger.warning(f"[Gemini] No se pudo eliminar archivo temporal: {e}")


async def _extract_with_openai(file_path: Path) -> str:
    """
    Extrae datos usando OpenAI GPT-4o-mini como fallback.
    Usa la Files API para subir el PDF y luego lo referencia en el chat.
    Retorna el texto de respuesta o lanza excepción.
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY no está configurada para fallback")
    
    logger.info(f"[OpenAI] Subiendo archivo: {file_path.name}")
    
    # Crear el cliente de OpenAI
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    uploaded_file = None
    try:
        # Subir el archivo a OpenAI Files API
        with open(file_path, "rb") as f:
            uploaded_file = client.files.create(
                file=f,
                purpose="assistants"  # Para usar en chat/completions con vision
            )
        
        logger.info(f"[OpenAI] Archivo subido correctamente")
        
        # Llamar a GPT-4o-mini con el archivo usando el formato correcto
        # Para PDFs, usamos el enfoque de file_id con la Responses API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "file",
                            "file": {
                                "file_id": uploaded_file.id,
                            },
                        },
                        {
                            "type": "text",
                            "text": EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
            max_tokens=2000,
        )
        
        logger.info(f"[OpenAI] Extracción completada")
        return response.choices[0].message.content
        
    except openai.RateLimitError as e:
        logger.error(f"[OpenAI] Rate limit error: {e}")
        raise ValueError(f"OpenAI también tiene rate limit: {str(e)}")
    except openai.BadRequestError as e:
        # Si el formato file no funciona, intentar con base64 para imágenes
        logger.warning(f"[OpenAI] Error con formato file, probando base64: {e}")
        
        # Leer el archivo y convertir a base64
        with open(file_path, "rb") as f:
            file_content = f.read()
        file_base64 = base64.standard_b64encode(file_content).decode("utf-8")
        
        # Determinar el tipo MIME
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            mime_type = "application/pdf"
        elif suffix in [".png", ".jpg", ".jpeg"]:
            mime_type = f"image/{suffix[1:]}"
        else:
            mime_type = "application/octet-stream"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{file_base64}",
                            },
                        },
                        {
                            "type": "text",
                            "text": EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
            max_tokens=2000,
        )
        
        logger.info(f"[OpenAI] Extracción completada (base64)")
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"[OpenAI] Error: {e}")
        raise ValueError(f"Error en procesamiento con OpenAI: {str(e)}")
    finally:
        # Limpiar el archivo subido si existe
        if uploaded_file:
            try:
                client.files.delete(uploaded_file.id)
                logger.debug(f"[OpenAI] Archivo temporal eliminado")
            except Exception as e:
                logger.warning(f"[OpenAI] No se pudo eliminar archivo temporal: {e}")


async def extract_invoice_data(file_path: str) -> dict:
    """
    Extrae datos estructurados de una factura usando Gemini.
    Si Gemini devuelve error 429 (rate limit), hace fallback a OpenAI GPT-4o-mini.
    
    Args:
        file_path: Ruta completa al archivo PDF de la factura
        
    Returns:
        Diccionario con los datos extraídos de la factura
        
    Raises:
        ValueError: Si no se puede procesar la factura
        FileNotFoundError: Si el archivo no existe
    """
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY no está configurada")
    
    logger.info(f"Extrayendo datos de factura: {Path(file_path).name}")
    
    # 1. Verificar que el archivo existe
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {file_path}")
    
    response_text = None
    used_provider = "gemini"
    
    # 2. Intentar con Gemini primero
    try:
        response_text = await _extract_with_gemini(path)
        logger.info("[Gemini] Extracción completada exitosamente")
        
    except Exception as e:
        if _is_rate_limit_error(e):
            logger.warning(f"[Gemini] Rate limit (429) detectado, intentando con OpenAI...")
            
            # Verificar si OpenAI está configurado
            if not OPENAI_API_KEY:
                raise ValueError("Gemini tiene rate limit y OPENAI_API_KEY no está configurada como fallback")
            
            # Fallback a OpenAI
            try:
                response_text = await _extract_with_openai(path)
                used_provider = "openai"
                logger.info("[OpenAI] Extracción completada exitosamente (fallback)")
                
            except Exception as openai_error:
                logger.error(f"[OpenAI] Error en fallback: {openai_error}")
                raise ValueError(f"Error en procesamiento con IA (Gemini: 429, OpenAI: {str(openai_error)})")
        else:
            # Otro tipo de error de Gemini
            logger.error(f"[Gemini] Error: {e}")
            raise ValueError(f"Error en procesamiento con IA: {str(e)}")
    
    # 3. Parsear la respuesta JSON
    try:
        data = _parse_json_response(response_text)
    except ValueError:
        raise
    
    # 4. Añadir metadato del proveedor usado
    data["_ai_provider"] = used_provider
    
    # 5. Validar y normalizar datos
    data = _normalize_invoice_data(data)
    
    # 6. Si la moneda no es EUR y no hay tipo de cambio, obtenerlo de Frankfurter
    data = await _enrich_with_exchange_rate(data)
    
    logger.info(f"Datos extraídos exitosamente ({used_provider}): {data.get('id_factura', 'sin ID')}")
    return data


def _normalize_invoice_data(data: dict) -> dict:
    """Normaliza y valida los datos extraídos"""
    # Normalizar tipo
    if data.get("tipo"):
        data["tipo"] = data["tipo"].lower().strip()
        if data["tipo"] not in ("factura", "venta"):
            data["tipo"] = "factura"  # Default
    else:
        data["tipo"] = "factura"
    
    # Asegurar que moneda tiene un valor por defecto
    if not data.get("moneda"):
        data["moneda"] = "EUR"
    else:
        data["moneda"] = data["moneda"].upper().strip()
    
    # Normalizar campos numéricos
    for field in ["importe_sin_iva", "iva_porcentaje", "importe_total", "tipo_cambio"]:
        if field in data and data[field] is not None:
            try:
                # Reemplazar coma por punto si viene en formato español
                if isinstance(data[field], str):
                    data[field] = data[field].replace(",", ".")
                data[field] = float(data[field])
            except (ValueError, TypeError):
                data[field] = None
    
    # Normalizar país
    if data.get("pais_origen"):
        data["pais_origen"] = data["pais_origen"].upper().strip()[:2]

    # Normalizar pais_factura
    if data.get("pais_factura"):
        data["pais_factura"] = data["pais_factura"].upper().strip()[:2]

    # Normalizar campos SI/NO fiscales
    si_no_fields = [
        "pais_ue", "servicio_intracomunitario_sin_iva",
        "servicio_extracomunitario_sin_iva", "inversion_sujeto_pasivo",
        "dua", "gasto_nacional_iva_deducible",
    ]
    for field in si_no_fields:
        val = data.get(field, "").strip().upper() if data.get(field) else "NO"
        data[field] = "SI" if val in ("SI", "SÍ", "YES", "TRUE", "1") else "NO"

    # Normalizar tipo_adquisicion
    if data.get("tipo_adquisicion"):
        val = data["tipo_adquisicion"].strip().capitalize()
        if val not in ("Gasto", "Bienes", "Servicios"):
            data["tipo_adquisicion"] = "Servicios"  # Default
        else:
            data["tipo_adquisicion"] = val

    # Asegurar N/A en campos de texto vacíos
    for field in ["proveedor_vat", "notas"]:
        if not data.get(field) or data[field] == "":
            data[field] = "N/A"

    return data


async def _enrich_with_exchange_rate(data: dict) -> dict:
    """
    Si la factura no es en EUR y no tiene tipo de cambio,
    obtiene el tipo de cambio de la API de Frankfurter.
    """
    from services.exchange_service import get_exchange_rate
    
    moneda = data.get("moneda", "EUR")
    tipo_cambio = data.get("tipo_cambio")
    
    # Solo obtener tipo de cambio si no es EUR y no hay uno ya
    if moneda != "EUR" and not tipo_cambio:
        fecha_str = data.get("fecha", "")
        if fecha_str:
            try:
                # Convertir fecha DD/MM/YYYY a YYYY-MM-DD
                dt = datetime.strptime(fecha_str, "%d/%m/%Y")
                fecha_iso = dt.strftime("%Y-%m-%d")
                
                logger.info(f"Obteniendo tipo de cambio para {moneda} en fecha {fecha_iso}")
                tipo_cambio = await get_exchange_rate(fecha_iso, moneda)
                
                if tipo_cambio:
                    data["tipo_cambio"] = tipo_cambio
                    logger.info(f"Tipo de cambio obtenido: {tipo_cambio}")
                else:
                    logger.warning(f"No se pudo obtener tipo de cambio para {moneda}")
            except ValueError as e:
                logger.warning(f"Fecha inválida para obtener tipo de cambio: {fecha_str} - {e}")
    
    return data
