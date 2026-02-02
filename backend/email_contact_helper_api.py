# email_contact_helper_api.py
# API endpoint para el agente email-contact-helper
# Recibe datos de formularios web, valida, inserta en BD y dispara procesamiento asíncrono

import logging
import re
import os
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, EmailStr, field_validator, model_validator

# Cargar .env si está disponible (para asegurar que las variables estén disponibles)
try:
    from dotenv import load_dotenv
    # Intentar cargar .env desde el directorio backend
    current_file = Path(__file__)
    backend_dir = current_file.parent  # email_contact_helper_api.py está en backend/
    env_path = backend_dir / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
    else:
        # Fallback: intentar cargar desde directorio actual
        load_dotenv(override=False)
except ImportError:
    # dotenv no disponible, continuar sin cargar (asumiendo que main.py ya lo cargó)
    pass

from services.supabase_rest import SupabaseREST
from services.email_contact_helper_agent import process_contact

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

# API Key: se espera en header X-API-Key. Valor en env EMAIL_CONTACT_HELPER_API_KEY
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)
EXPECTED_API_KEY = os.getenv("EMAIL_CONTACT_HELPER_API_KEY", "").strip()


def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Comprueba que el header X-API-Key coincida con EMAIL_CONTACT_HELPER_API_KEY."""
    if not EXPECTED_API_KEY:
        logger.error("[EMAIL_CONTACT_HELPER] EMAIL_CONTACT_HELPER_API_KEY no configurada en .env")
        raise HTTPException(
            status_code=500,
            detail="API key no configurada en el servidor"
        )
    if not api_key or not api_key.strip():
        raise HTTPException(
            status_code=401,
            detail="Falta el header X-API-Key"
        )
    if api_key.strip() != EXPECTED_API_KEY:
        raise HTTPException(
            status_code=403,
            detail="API key inválida"
        )
    return api_key.strip()


# ============================================================================
# VALIDACIÓN Y NORMALIZACIÓN
# ============================================================================

# Regex patterns (Python re no soporta \p{L}; \w con UNICODE incluye letras de cualquier idioma)
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')
PHONE_REGEX = re.compile(r'^\+?[0-9]{9,15}$')
NAME_REGEX = re.compile(r'^[\w\s\'\-\.]{2,100}$', re.UNICODE)
URL_REGEX = re.compile(r'^https?://[^\s<>"{}|\\^`\[\]]+$')


def normalize_string(value: Optional[str]) -> Optional[str]:
    """Normaliza un string: trim + colapsar espacios múltiples."""
    if value is None:
        return None
    # Trim
    value = value.strip()
    # Colapsar espacios múltiples
    value = re.sub(r'\s+', ' ', value)
    return value if value else None


def normalize_email(email: str) -> str:
    """Normaliza email: trim + lowercase."""
    return email.strip().lower()


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """
    Normaliza teléfono:
    - Elimina espacios, guiones, paréntesis
    - Si no tiene código de país y tiene 9 dígitos, añade +34 (España)
    """
    if phone is None:
        return None
    
    # Eliminar caracteres no numéricos excepto +
    phone = re.sub(r'[^\d+]', '', phone)
    
    if not phone:
        return None
    
    # Si empieza con 00, reemplazar por +
    if phone.startswith('00'):
        phone = '+' + phone[2:]
    
    # Si tiene 9 dígitos y no tiene código de país, añadir +34
    if len(phone) == 9 and phone[0] in '6789':
        phone = '+34' + phone
    
    # Si no empieza con +, añadirlo
    if not phone.startswith('+'):
        phone = '+' + phone
    
    return phone


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ContactRequest(BaseModel):
    """Request model para el endpoint de contacto."""
    source_url: Optional[str] = None
    name: str
    email: str
    phone: Optional[str] = None
    company: Optional[str] = None
    message: Optional[str] = None
    
    @model_validator(mode='before')
    @classmethod
    def normalize_all_fields(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza todos los campos antes de la validación."""
        if isinstance(values, dict):
            # Normalizar strings
            if 'name' in values:
                values['name'] = normalize_string(values.get('name'))
            if 'company' in values:
                values['company'] = normalize_string(values.get('company'))
            if 'message' in values:
                values['message'] = normalize_string(values.get('message'))
            if 'source_url' in values:
                values['source_url'] = normalize_string(values.get('source_url'))
            
            # Normalizar email
            if 'email' in values and values.get('email'):
                values['email'] = normalize_email(values['email'])
            
            # Normalizar teléfono
            if 'phone' in values:
                values['phone'] = normalize_phone(values.get('phone'))
        
        return values
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Valida el nombre."""
        if not v:
            raise ValueError('El nombre es obligatorio')
        if len(v) < 2:
            raise ValueError('El nombre debe tener al menos 2 caracteres')
        if len(v) > 100:
            raise ValueError('El nombre no puede exceder 100 caracteres')
        # Permitir letras, espacios, apóstrofes, guiones y puntos
        if not re.match(r'^[\w\s\'\-\.]+$', v, re.UNICODE):
            raise ValueError('El nombre contiene caracteres no válidos')
        return v
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Valida el formato del email."""
        if not v:
            raise ValueError('El email es obligatorio')
        if not EMAIL_REGEX.match(v):
            raise ValueError('El formato del email no es válido')
        if len(v) > 254:
            raise ValueError('El email es demasiado largo')
        return v
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Valida el formato del teléfono."""
        if v is None:
            return None
        if not PHONE_REGEX.match(v):
            raise ValueError('El formato del teléfono no es válido. Use formato internacional (+34612345678)')
        return v
    
    @field_validator('company')
    @classmethod
    def validate_company(cls, v: Optional[str]) -> Optional[str]:
        """Valida la empresa."""
        if v is None:
            return None
        if len(v) > 200:
            raise ValueError('El nombre de empresa no puede exceder 200 caracteres')
        return v
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v: Optional[str]) -> Optional[str]:
        """Valida el mensaje."""
        if v is None:
            return None
        if len(v) > 5000:
            raise ValueError('El mensaje no puede exceder 5000 caracteres')
        return v
    
    @field_validator('source_url')
    @classmethod
    def validate_source_url(cls, v: Optional[str]) -> Optional[str]:
        """Valida la URL de origen."""
        if v is None:
            return None
        if not URL_REGEX.match(v):
            raise ValueError('La URL de origen no es válida')
        if len(v) > 500:
            raise ValueError('La URL de origen es demasiado larga')
        return v


class ContactResponse(BaseModel):
    """Response model para el endpoint de contacto."""
    status: str  # "success" o "error"
    contact_id: Optional[int] = None
    error_details: Optional[Dict[str, str]] = None


# ============================================================================
# ENDPOINT
# ============================================================================

@router.post("/email-contact-helper", response_model=ContactResponse)
async def handle_contact_form(
    request: ContactRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_api_key),
):
    """
    Procesa un formulario de contacto web.
    
    1. Valida y normaliza los datos de entrada
    2. Inserta el contacto en la base de datos (status='new')
    3. Dispara un BackgroundTask para procesar prospección y enviar email
    4. Devuelve inmediatamente el contact_id
    
    El procesamiento (prospección web + email) ocurre de forma asíncrona.
    El estado del contacto se puede consultar en la tabla web_contacts.
    """
    logger.info("=" * 60)
    logger.info(f"[EMAIL_CONTACT_HELPER] Nuevo contacto recibido: {request.name} ({request.email})")
    
    try:
        # Preparar datos para insertar
        contact_data = {
            "source_url": request.source_url,
            "name": request.name,
            "email": request.email,
            "phone": request.phone,
            "company": request.company,
            "message": request.message,
            "status": "new"
        }
        
        logger.info(f"[EMAIL_CONTACT_HELPER] Datos normalizados: {contact_data}")
        
        # Insertar en Supabase
        sb = SupabaseREST()
        result = await sb.post("web_contacts", contact_data)
        
        if not result or len(result) == 0:
            logger.error("[EMAIL_CONTACT_HELPER] Error insertando contacto: resultado vacío")
            raise HTTPException(
                status_code=500,
                detail="Error guardando el contacto"
            )
        
        contact_id = result[0].get("id")
        logger.info(f"[EMAIL_CONTACT_HELPER] Contacto insertado con ID: {contact_id}")
        
        # Disparar BackgroundTask para procesar el contacto
        background_tasks.add_task(process_contact, contact_id)
        logger.info(f"[EMAIL_CONTACT_HELPER] BackgroundTask disparado para contacto {contact_id}")
        
        logger.info("=" * 60)
        
        # Devolver inmediatamente
        return ContactResponse(
            status="success",
            contact_id=contact_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[EMAIL_CONTACT_HELPER] Error procesando contacto: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno: {str(e)}"
        )


@router.get("/email-contact-helper/{contact_id}", response_model=Dict[str, Any])
async def get_contact_status(
    contact_id: int,
    _: str = Depends(verify_api_key),
):
    """
    Obtiene el estado de procesamiento de un contacto.
    
    Útil para verificar si el email ya fue enviado o si hubo errores.
    """
    try:
        sb = SupabaseREST()
        result = await sb.get_single(
            "web_contacts",
            "id,name,email,status,email_sent_at,error,created_at",
            {"id": contact_id}
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Contacto no encontrado")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[EMAIL_CONTACT_HELPER] Error obteniendo contacto {contact_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
