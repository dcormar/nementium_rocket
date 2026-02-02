# email_contact_helper_agent.py
# Agente para procesar contactos web y enviar emails de prospección

import os
import logging
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

# Cargar .env si está disponible
try:
    from dotenv import load_dotenv
    current_file = Path(__file__)
    backend_dir = current_file.parent.parent
    env_path = backend_dir / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
    else:
        load_dotenv(override=False)
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Configuración
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
NOTIFICATION_EMAIL = "davidcortijo@nementium.ai"

# Importar servicios
from services.supabase_rest import SupabaseREST
from services.consulta_web_tools import web_search, fetch_url
from services.email_service import send_email

# Importar LLMs
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logger.warning("LangChain no disponible")


# ============================================================================
# CONFIGURACIÓN DEL AGENTE
# ============================================================================

def get_llm():
    """Obtiene el LLM configurado."""
    if not LANGCHAIN_AVAILABLE:
        raise ValueError("LangChain no disponible")
    
    if GOOGLE_API_KEY:
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=GOOGLE_API_KEY,
            temperature=0.3,
            convert_system_message_to_human=True
        )
    elif OPENAI_API_KEY:
        return ChatOpenAI(
            model="gpt-4o-mini",
            openai_api_key=OPENAI_API_KEY,
            temperature=0.3
        )
    else:
        raise ValueError("No hay API key de LLM configurada (GOOGLE_API_KEY o OPENAI_API_KEY)")


def get_nementium_services() -> str:
    """Lee el archivo de servicios de Nementium para el fit analysis."""
    try:
        services_path = Path(__file__).parent.parent.parent / "docs" / "ragdocuments" / "nementium" / "about_us_nementium.md"
        if services_path.exists():
            return services_path.read_text(encoding="utf-8")
        else:
            logger.warning(f"[CONTACT_HELPER] No se encontró {services_path}")
            return ""
    except Exception as e:
        logger.error(f"[CONTACT_HELPER] Error leyendo servicios de Nementium: {e}")
        return ""


# ============================================================================
# PROSPECCIÓN WEB
# ============================================================================

async def do_web_prospecting(contact_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Realiza prospección web para un contacto.
    Busca información sobre la empresa y persona.
    
    Returns:
        prospecting_json estructurado
    """
    name = contact_data.get("name", "")
    email = contact_data.get("email", "")
    company = contact_data.get("company", "")
    message = contact_data.get("message", "")
    
    logger.info(f"[CONTACT_HELPER] Iniciando prospección para: {name} ({company or 'sin empresa'})")
    
    prospecting = {
        "company": {
            "name": company or "No especificada",
            "website": None,
            "linkedin_url": None,
            "sector": None,
            "size_employees": None,
            "tech_stack_hints": []
        },
        "person": {
            "name": name,
            "linkedin_url": None,
            "role": None
        },
        "signals": {
            "automation_interest": None,
            "pain_points": [],
            "current_tools": []
        },
        "sources": [],
        "service_fit": None,
        "next_steps": []
    }
    
    try:
        # 1. Buscar empresa si existe
        if company:
            logger.info(f"[CONTACT_HELPER] Buscando empresa: {company}")
            try:
                company_results = web_search.invoke({
                    "query": f"{company} España empresa web oficial",
                    "max_results": 5
                })
                
                if company_results and not isinstance(company_results, dict):
                    for result in company_results[:3]:
                        url = result.get("url", "")
                        if url:
                            prospecting["sources"].append(url)
                        
                        # Detectar website oficial
                        snippet = result.get("snippet", "").lower()
                        if not prospecting["company"]["website"]:
                            if company.lower().replace(" ", "") in url.lower():
                                prospecting["company"]["website"] = url
                        
                        # Detectar LinkedIn
                        if "linkedin.com/company" in url.lower():
                            prospecting["company"]["linkedin_url"] = url
            except Exception as e:
                logger.warning(f"[CONTACT_HELPER] Error buscando empresa: {e}")
            
            # Buscar señales de sector/tamaño
            try:
                sector_results = web_search.invoke({
                    "query": f"{company} sector empleados tamaño empresa",
                    "max_results": 3
                })
                if sector_results and not isinstance(sector_results, dict):
                    for result in sector_results:
                        snippet = result.get("snippet", "")
                        # Extraer pistas de sector
                        sectors = ["tecnología", "software", "retail", "ecommerce", "servicios", 
                                   "consultoría", "finanzas", "salud", "educación", "logística",
                                   "manufactura", "construcción", "marketing", "legal"]
                        for sector in sectors:
                            if sector in snippet.lower() and not prospecting["company"]["sector"]:
                                prospecting["company"]["sector"] = sector.capitalize()
                                break
            except Exception as e:
                logger.warning(f"[CONTACT_HELPER] Error buscando sector: {e}")
        
        # 2. Buscar persona
        logger.info(f"[CONTACT_HELPER] Buscando persona: {name}")
        try:
            person_query = f"{name} LinkedIn"
            if company:
                person_query = f"{name} {company} LinkedIn"
            
            person_results = web_search.invoke({
                "query": person_query,
                "max_results": 3
            })
            
            if person_results and not isinstance(person_results, dict):
                for result in person_results:
                    url = result.get("url", "")
                    if "linkedin.com/in/" in url.lower():
                        prospecting["person"]["linkedin_url"] = url
                        prospecting["sources"].append(url)
                        
                        # Intentar extraer rol del snippet
                        snippet = result.get("snippet", "")
                        roles = ["CEO", "CTO", "CFO", "COO", "Director", "Manager", "Founder",
                                "Owner", "Gerente", "Jefe", "Responsable", "Lead", "Head"]
                        for role in roles:
                            if role.lower() in snippet.lower():
                                prospecting["person"]["role"] = role
                                break
                        break
        except Exception as e:
            logger.warning(f"[CONTACT_HELPER] Error buscando persona: {e}")
        
        # 3. Buscar señales de automatización
        if company:
            try:
                auto_results = web_search.invoke({
                    "query": f"{company} automatización digitalización software herramientas",
                    "max_results": 3
                })
                if auto_results and not isinstance(auto_results, dict):
                    for result in auto_results:
                        snippet = result.get("snippet", "").lower()
                        tools = ["salesforce", "hubspot", "zoho", "sap", "odoo", "microsoft", 
                                "google workspace", "slack", "notion", "asana", "monday"]
                        for tool in tools:
                            if tool in snippet and tool not in prospecting["signals"]["current_tools"]:
                                prospecting["signals"]["current_tools"].append(tool)
            except Exception as e:
                logger.warning(f"[CONTACT_HELPER] Error buscando señales: {e}")
        
        # 4. Analizar mensaje para pain points
        if message:
            pain_keywords = {
                "tiempo": "Falta de tiempo para tareas administrativas",
                "manual": "Procesos manuales que quieren automatizar",
                "factura": "Gestión de facturación",
                "cliente": "Atención al cliente",
                "dato": "Procesamiento de datos",
                "informe": "Generación de informes",
                "repetitivo": "Tareas repetitivas",
                "eficiencia": "Mejora de eficiencia",
                "coste": "Reducción de costes",
                "error": "Reducción de errores"
            }
            
            message_lower = message.lower()
            for keyword, pain in pain_keywords.items():
                if keyword in message_lower and pain not in prospecting["signals"]["pain_points"]:
                    prospecting["signals"]["pain_points"].append(pain)
        
        # 5. Determinar interés en automatización
        if message:
            auto_keywords = ["automatizar", "automatización", "ia", "inteligencia artificial",
                           "chatbot", "asistente", "bot", "eficiencia", "optimizar", "ahorrar tiempo"]
            message_lower = message.lower()
            for keyword in auto_keywords:
                if keyword in message_lower:
                    prospecting["signals"]["automation_interest"] = "Alto - menciona directamente automatización/IA"
                    break
            
            if not prospecting["signals"]["automation_interest"]:
                if prospecting["signals"]["pain_points"]:
                    prospecting["signals"]["automation_interest"] = "Medio - tiene pain points que podríamos resolver"
                else:
                    prospecting["signals"]["automation_interest"] = "Por determinar - requiere calificación"
        
        # 6. Limpiar sources duplicados
        prospecting["sources"] = list(set(prospecting["sources"]))[:5]
        
        logger.info(f"[CONTACT_HELPER] Prospección completada: {len(prospecting['sources'])} fuentes encontradas")
        
    except Exception as e:
        logger.exception(f"[CONTACT_HELPER] Error en prospección web: {e}")
    
    return prospecting


# ============================================================================
# GENERACIÓN DE EMAIL
# ============================================================================

async def generate_email_content(
    contact_data: Dict[str, Any],
    prospecting: Dict[str, Any],
    nementium_services: str
) -> Dict[str, str]:
    """
    Genera el contenido del email usando LLM.
    
    Returns:
        Dict con 'subject' y 'html_body'
    """
    logger.info("[CONTACT_HELPER] Generando contenido del email con LLM")
    
    try:
        llm = get_llm()
        
        system_prompt = """Eres un asistente que genera emails de notificación de leads para el equipo comercial de Nementium.
        
El email debe ser:
- Profesional pero cercano
- Bien estructurado con secciones claras
- Incluir TODOS los datos proporcionados
- Generar preguntas de calificación útiles basadas en el mensaje
- Evaluar el fit con los servicios de Nementium
- Sugerir próximos pasos concretos

IMPORTANTE: 
- NO inventes información que no tengas
- Si no hay datos de prospección para algún campo, indica "No encontrado"
- Usa formato HTML con estilos inline para mejor visualización"""

        user_prompt = f"""Genera un email de notificación para David (davidcortijo@nementium.ai) sobre un nuevo lead.

DATOS DEL CONTACTO:
- Nombre: {contact_data.get('name', 'No proporcionado')}
- Email: {contact_data.get('email', 'No proporcionado')}
- Teléfono: {contact_data.get('phone', 'No proporcionado')}
- Empresa: {contact_data.get('company', 'No especificada')}
- Formulario: {contact_data.get('source_url', 'No especificado')}
- Mensaje original: {contact_data.get('message', 'Sin mensaje')}

RESULTADOS DE PROSPECCIÓN ONLINE:
{json.dumps(prospecting, indent=2, ensure_ascii=False)}

SERVICIOS DE NEMENTIUM (para evaluar fit):
{nementium_services[:3000] if nementium_services else 'No disponible'}

Genera el email con estas secciones:
1. Saludo a David
2. Aviso de nuevo lead con datos del contacto
3. Interpretación del mensaje + 3-4 preguntas de calificación sugeridas
4. Resumen de prospección online con links clickeables
5. Evaluación de fit con servicios de Nementium
6. Próximos pasos recomendados

El formato debe ser HTML limpio con estilos inline. Usa colores corporativos (#2563eb azul, #1e3a5f azul oscuro).

Responde SOLO con un JSON válido con esta estructura:
{{"subject": "asunto del email", "html_body": "contenido HTML completo"}}"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = llm.invoke(messages)
        content = response.content.strip()
        
        # Extraer JSON de la respuesta
        # A veces el LLM envuelve el JSON en ```json ... ```
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        
        logger.info(f"[CONTACT_HELPER] Email generado: {result.get('subject', 'Sin asunto')[:50]}...")
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"[CONTACT_HELPER] Error parseando JSON del LLM: {e}")
        # Fallback: generar email básico
        return generate_fallback_email(contact_data, prospecting)
    except Exception as e:
        logger.exception(f"[CONTACT_HELPER] Error generando email: {e}")
        return generate_fallback_email(contact_data, prospecting)


def generate_fallback_email(contact_data: Dict[str, Any], prospecting: Dict[str, Any]) -> Dict[str, str]:
    """Genera un email básico si el LLM falla."""
    
    name = contact_data.get('name', 'No proporcionado')
    email = contact_data.get('email', 'No proporcionado')
    phone = contact_data.get('phone', 'No proporcionado')
    company = contact_data.get('company', 'No especificada')
    message = contact_data.get('message', 'Sin mensaje')
    source_url = contact_data.get('source_url', 'No especificado')
    
    # Construir sección de prospección
    prosp_html = ""
    if prospecting.get("company", {}).get("website"):
        prosp_html += f"<li><strong>Web empresa:</strong> <a href='{prospecting['company']['website']}'>{prospecting['company']['website']}</a></li>"
    if prospecting.get("company", {}).get("linkedin_url"):
        prosp_html += f"<li><strong>LinkedIn empresa:</strong> <a href='{prospecting['company']['linkedin_url']}'>{prospecting['company']['linkedin_url']}</a></li>"
    if prospecting.get("person", {}).get("linkedin_url"):
        prosp_html += f"<li><strong>LinkedIn persona:</strong> <a href='{prospecting['person']['linkedin_url']}'>{prospecting['person']['linkedin_url']}</a></li>"
    if prospecting.get("company", {}).get("sector"):
        prosp_html += f"<li><strong>Sector:</strong> {prospecting['company']['sector']}</li>"
    if prospecting.get("signals", {}).get("automation_interest"):
        prosp_html += f"<li><strong>Interés en automatización:</strong> {prospecting['signals']['automation_interest']}</li>"
    
    if not prosp_html:
        prosp_html = "<li>No se encontró información adicional online</li>"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">🎯 Nuevo Lead Web</h1>
        </div>
        
        <div style="background: #f9fafb; padding: 24px; border: 1px solid #e5e7eb; border-top: none;">
            <p>Hola David,</p>
            
            <p>Alguien ha rellenado el formulario de contacto en <strong>{source_url}</strong></p>
            
            <div style="background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #2563eb; margin: 16px 0;">
                <h3 style="margin-top: 0; color: #1e3a5f;">📋 Datos del contacto</h3>
                <ul style="list-style: none; padding: 0;">
                    <li><strong>Nombre:</strong> {name}</li>
                    <li><strong>Email:</strong> <a href="mailto:{email}">{email}</a></li>
                    <li><strong>Teléfono:</strong> {phone}</li>
                    <li><strong>Empresa:</strong> {company}</li>
                </ul>
            </div>
            
            <div style="background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #10b981; margin: 16px 0;">
                <h3 style="margin-top: 0; color: #1e3a5f;">💬 Mensaje original</h3>
                <p style="white-space: pre-wrap;">{message}</p>
            </div>
            
            <div style="background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #f59e0b; margin: 16px 0;">
                <h3 style="margin-top: 0; color: #1e3a5f;">🔍 Prospección online</h3>
                <ul>{prosp_html}</ul>
            </div>
            
            <div style="background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #8b5cf6; margin: 16px 0;">
                <h3 style="margin-top: 0; color: #1e3a5f;">📌 Próximos pasos sugeridos</h3>
                <ol>
                    <li>Revisar el mensaje y contexto del lead</li>
                    <li>Responder en las próximas 24h</li>
                    <li>Agendar llamada de calificación si hay fit</li>
                </ol>
            </div>
        </div>
        
        <div style="text-align: center; color: #6b7280; font-size: 12px; margin-top: 20px;">
            <p>© 2025 Nementium.ai - Email generado automáticamente</p>
        </div>
    </body>
    </html>
    """
    
    return {
        "subject": f"🎯 Nuevo lead: {name}" + (f" ({company})" if company and company != "No especificada" else ""),
        "html_body": html_body
    }


# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================

async def process_contact(contact_id: int) -> Dict[str, Any]:
    """
    Procesa un contacto web de forma asíncrona.
    
    1. Lee el contacto de BD
    2. Actualiza status a 'processing'
    3. Ejecuta prospección web
    4. Guarda prospecting_json
    5. Genera y envía email
    6. Actualiza status a 'emailed' o 'error'
    
    Args:
        contact_id: ID del contacto en web_contacts
        
    Returns:
        Dict con resultado del procesamiento
    """
    logger.info(f"[CONTACT_HELPER] ========== Procesando contacto {contact_id} ==========")
    
    sb = SupabaseREST()
    
    try:
        # 1. Leer contacto de BD
        contact = await sb.get_single(
            "web_contacts",
            "*",
            {"id": contact_id}
        )
        
        if not contact:
            logger.error(f"[CONTACT_HELPER] Contacto {contact_id} no encontrado")
            return {"success": False, "error": "Contacto no encontrado"}
        
        logger.info(f"[CONTACT_HELPER] Contacto cargado: {contact.get('name')} ({contact.get('email')})")
        
        # 2. Actualizar status a 'processing'
        await sb.patch(
            "web_contacts",
            {"status": "processing"},
            {"id": contact_id}
        )
        
        # 3. Ejecutar prospección web
        prospecting = await do_web_prospecting(contact)
        
        # 4. Guardar prospecting_json
        await sb.patch(
            "web_contacts",
            {"prospecting_json": prospecting},
            {"id": contact_id}
        )
        
        # 5. Leer servicios de Nementium
        nementium_services = get_nementium_services()
        
        # 6. Generar contenido del email
        email_content = await generate_email_content(contact, prospecting, nementium_services)
        
        # 7. Determinar service_fit y next_steps basados en la prospección
        service_fit = "Por evaluar"
        if prospecting.get("signals", {}).get("automation_interest"):
            interest = prospecting["signals"]["automation_interest"]
            if "Alto" in interest:
                service_fit = "Alto - Lead caliente, menciona automatización/IA directamente"
            elif "Medio" in interest:
                service_fit = "Medio - Tiene pain points que podríamos resolver"
            else:
                service_fit = "Por determinar - Requiere calificación"
        
        prospecting["service_fit"] = service_fit
        prospecting["next_steps"] = [
            "Revisar mensaje y contexto del lead",
            "Responder en las próximas 24h",
            "Agendar llamada de calificación si hay fit"
        ]
        
        # Actualizar prospecting_json con fit y next_steps
        await sb.patch(
            "web_contacts",
            {"prospecting_json": prospecting},
            {"id": contact_id}
        )
        
        # 8. Enviar email
        logger.info(f"[CONTACT_HELPER] Enviando email a {NOTIFICATION_EMAIL}")
        
        email_result = await send_email(
            to=NOTIFICATION_EMAIL,
            subject=email_content["subject"],
            html=email_content["html_body"]
        )
        
        if email_result.get("success"):
            # 9. Actualizar status a 'emailed'
            await sb.patch(
                "web_contacts",
                {
                    "status": "emailed",
                    "email_sent_at": datetime.now().isoformat()
                },
                {"id": contact_id}
            )
            
            logger.info(f"[CONTACT_HELPER] ✅ Contacto {contact_id} procesado exitosamente")
            return {"success": True, "contact_id": contact_id, "email_id": email_result.get("id")}
        else:
            raise Exception(f"Error enviando email: {email_result.get('error')}")
        
    except Exception as e:
        logger.exception(f"[CONTACT_HELPER] ❌ Error procesando contacto {contact_id}: {e}")
        
        # Actualizar status a 'error'
        try:
            await sb.patch(
                "web_contacts",
                {
                    "status": "error",
                    "error": str(e)[:500]  # Limitar longitud del error
                },
                {"id": contact_id}
            )
        except Exception as db_error:
            logger.error(f"[CONTACT_HELPER] Error actualizando status a error: {db_error}")
        
        return {"success": False, "contact_id": contact_id, "error": str(e)}


def process_contact_sync_wrapper(contact_id: int):
    """
    Wrapper síncrono para ejecutar process_contact desde BackgroundTasks.
    BackgroundTasks de FastAPI puede ejecutar tanto funciones sync como async,
    pero necesitamos manejar el event loop correctamente.
    """
    import asyncio
    
    try:
        # Intentar obtener el loop existente
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Si hay un loop corriendo, crear una tarea
            asyncio.ensure_future(process_contact(contact_id))
        else:
            # Si no hay loop, ejecutar directamente
            loop.run_until_complete(process_contact(contact_id))
    except RuntimeError:
        # No hay loop, crear uno nuevo
        asyncio.run(process_contact(contact_id))
