# assistant_agent.py
# Agente LangGraph para el asistente overlay

import os
import logging
import json
import warnings
from typing import Literal, Dict, Any, List, Optional, TypedDict, Annotated
from datetime import datetime
from pathlib import Path

# Cargar .env si está disponible (para scripts que se ejecutan directamente)
try:
    from dotenv import load_dotenv
    # Intentar cargar .env desde el directorio backend
    # Si este módulo está en backend/services/, el .env está en backend/
    current_file = Path(__file__)
    backend_dir = current_file.parent.parent  # backend/services/ -> backend/
    env_path = backend_dir / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
    else:
        # Fallback: intentar cargar desde directorio actual también
        load_dotenv(override=False)
except ImportError:
    # dotenv no disponible, continuar sin cargar
    pass

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain.tools import tool

# Suprimir warnings
warnings.filterwarnings("ignore", message=".*Key 'title' is not supported in schema.*")
warnings.filterwarnings("ignore", message=".*Key 'default' is not supported in schema.*")

logger = logging.getLogger(__name__)

# Configuración (después de cargar .env)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Importar wrapper de Supabase REST
from services.supabase_rest import SupabaseREST

# Importar LLMs
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_openai import ChatOpenAI
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logger.warning("LangChain no disponible")


# ============================================================================
# FUNCIÓN PARA OBTENER CLIENTE SUPABASE REST
# ============================================================================

def get_supabase_client() -> SupabaseREST:
    """Obtiene cliente de Supabase REST."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise ValueError("SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY deben estar configurados")
    
    try:
        return SupabaseREST()
    except Exception as e:
        logger.exception(f"[ASSISTANT] Error creando cliente Supabase: {e}")
        raise


# ============================================================================
# ESTADO DEL AGENTE
# ============================================================================

def merge_messages(left: List[BaseMessage], right: List[BaseMessage]) -> List[BaseMessage]:
    """Combina listas de mensajes."""
    return left + right


class AssistantState(TypedDict):
    """Estado del agente asistente."""
    messages: Annotated[List[BaseMessage], merge_messages]
    user_message: str
    username: str
    iteration: int
    should_finish: bool
    final_response: Optional[str]
    actions_executed: List[Dict[str, Any]]
    # Campos para flujo determinístico de acciones finales
    final_action_triggered: bool  # Si se ejecutó una acción final
    final_action_result: Optional[str]  # Resultado de la acción final


# ============================================================================
# HERRAMIENTAS DEL ASISTENTE
# ============================================================================

@tool
async def rag_search(query: str, doc_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Busca información en la base de conocimiento (documentación de la app, Hacienda, Seguridad Social).
    
    Args:
        query: Pregunta o términos de búsqueda
        doc_type: Tipo de documento a buscar (opcional): 'app_manual', 'hacienda', 'seg_social'
    
    Returns:
        Lista de documentos relevantes con su contenido y similitud
    """
    from services.rag_service import search_documents
    
    logger.info(f"[ASSISTANT] RAG search: query='{query[:50]}...', doc_type={doc_type}")
    
    try:
        results = await search_documents(
            query=query,
            doc_type=doc_type,
            match_threshold=0.4,  # Umbral más bajo para más resultados
            match_count=5
        )
        
        # Formatear resultados
        formatted = []
        for doc in results:
            formatted.append({
                "title": doc.get("title", "Sin título"),
                "content": doc.get("content", "")[:500],  # Limitar contenido
                "doc_type": doc.get("doc_type"),
                "similarity": round(doc.get("similarity", 0), 3)
            })
        
        logger.info(f"[ASSISTANT] RAG encontró {len(formatted)} documentos")
        return formatted
        
    except Exception as e:
        logger.exception(f"[ASSISTANT] Error en RAG search: {e}")
        return [{"error": "No se pudo buscar en la documentación en este momento"}]


@tool
def web_search_hacienda(query: str) -> List[Dict[str, str]]:
    """
    Busca información en internet sobre Hacienda, impuestos, o Seguridad Social.
    Útil para información actualizada que no esté en la base de conocimiento.
    
    Args:
        query: Términos de búsqueda (ej: "plazo modelo 303 enero 2025")
    
    Returns:
        Lista de resultados con título, URL y extracto
    """
    from services.consulta_web_tools import web_search
    
    # Añadir contexto de Hacienda/SS a la búsqueda
    enhanced_query = f"AEAT Hacienda España {query}"
    
    logger.info(f"[ASSISTANT] Web search: {enhanced_query[:50]}...")
    
    try:
        results = web_search.invoke({"query": enhanced_query, "max_results": 5})
        return results
    except Exception as e:
        logger.exception(f"[ASSISTANT] Error en web search: {e}")
        return [{"error": "No se pudo buscar información en internet en este momento"}]


@tool
async def list_user_contacts(username: str, search_term: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lista los contactos del usuario actual. Puede filtrar por término de búsqueda.
    
    Args:
        username: Username del usuario
        search_term: Término opcional para buscar en nombres o emails (ej: "elena", "elena medrano")
    
    Returns:
        Lista de contactos con nombre, email, telegram, tipo
    """
    logger.info(f"[ASSISTANT] Listando contactos para: {username}" + (f" (búsqueda: '{search_term}')" if search_term else ""))
    
    try:
        sb = get_supabase_client()
        contacts = await sb.get(
            "user_contacts",
            "id,nombre,email,telegram_username,tipo,activo",
            {"username": username, "activo": True}
        )
        
        # Si hay un término de búsqueda, filtrar los contactos
        if search_term:
            search_lower = search_term.lower().strip()
            # Primero buscar coincidencias exactas o parciales en el nombre completo
            filtered = [
                c for c in contacts
                if search_lower in c.get("nombre", "").lower() or 
                   search_lower in c.get("email", "").lower()
            ]
            
            # Si no hay resultados con el término completo, intentar con la primera palabra
            if not filtered and " " in search_lower:
                first_word = search_lower.split()[0]
                filtered = [
                    c for c in contacts
                    if first_word in c.get("nombre", "").lower() or 
                       first_word in c.get("email", "").lower()
                ]
            
            contacts = filtered
            logger.info(f"[ASSISTANT] Encontrados {len(contacts)} contactos después del filtro '{search_term}'")
        else:
            logger.info(f"[ASSISTANT] Encontrados {len(contacts)} contactos")
        
        return contacts
        
    except Exception as e:
        logger.exception(f"[ASSISTANT] Error listando contactos: {e}")
        # No devolver detalles técnicos al usuario
        return [{"error": "No se pudieron cargar los contactos en este momento"}]


@tool
async def send_email_notification(
    contact_id: int,
    subject: str,
    body: str,
    username: str,
    expected_email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envía una notificación por email a un contacto.
    
    Args:
        contact_id: ID del contacto en la base de datos (DEBE ser el ID del contacto confirmado)
        subject: Asunto del email
        body: Contenido del mensaje
        username: Username del usuario que envía
        expected_email: Email esperado del contacto (para validación de seguridad). Si se proporciona, se valida que el contacto tenga este email.
    
    Returns:
        Resultado del envío con status y mensaje
    """
    from services.email_service import send_notification_email
    
    logger.info(f"[ASSISTANT] Enviando email a contacto {contact_id}" + (f" (email esperado: {expected_email})" if expected_email else ""))
    
    try:
        # Obtener datos del contacto
        sb = get_supabase_client()
        result = await sb.get_single(
            "user_contacts",
            "id,nombre,email",
            {"id": contact_id, "username": username}
        )
        
        if not result:
            logger.error(f"[ASSISTANT] Contacto {contact_id} no encontrado para usuario {username}")
            return {"success": False, "error": "Contacto no encontrado o no pertenece a este usuario"}
        
        contact = result
        contact_email = contact.get("email", "").strip().lower()
        
        if not contact_email:
            logger.error(f"[ASSISTANT] Contacto {contact_id} no tiene email configurado")
            return {"success": False, "error": "El contacto no tiene email configurado"}
        
        # VALIDACIÓN CRÍTICA: Verificar que el email del contacto coincide con el esperado
        if expected_email:
            expected_email_lower = expected_email.strip().lower()
            if contact_email != expected_email_lower:
                logger.error(
                    f"[ASSISTANT] ERROR CRÍTICO: El contact_id {contact_id} corresponde a {contact_email}, "
                    f"pero se esperaba {expected_email_lower}. NO se enviará el email por seguridad."
                )
                return {
                    "success": False,
                    "error": f"ERROR DE SEGURIDAD: El contacto con ID {contact_id} tiene el email {contact.get('email')}, pero se esperaba {expected_email}. Por seguridad, no se envió el email. Por favor, verifica el contacto correcto."
                }
        
        # Obtener nombre del usuario
        user_name = username.split("@")[0].title()  # Usar parte antes del @ como nombre
        
        # Enviar email (asegurar que el body se pasa completo)
        logger.debug(f"[ASSISTANT] Enviando email - body length: {len(body)} caracteres")
        logger.debug(f"[ASSISTANT] Body completo: {body}")
        logger.info(f"[ASSISTANT] Validación OK: contact_id {contact_id} -> email {contact.get('email')}")
        
        await send_notification_email(
            to_email=contact["email"],
            from_user_name=user_name,
            subject_content=subject,
            body=body  # Pasar el body completo sin truncar
        )
        
        logger.info(f"[ASSISTANT] Email enviado a {contact['email']}")
        return {
            "success": True,
            "message": f"✅ Email enviado correctamente a {contact['email']}"
        }
        
    except Exception as e:
        logger.exception(f"[ASSISTANT] Error enviando email: {e}")
        error_msg = str(e)
        return {
            "success": False, 
            "error": f"❌ No se pudo enviar el email. {error_msg if len(error_msg) < 100 else 'Error técnico. Por favor, inténtalo más tarde.'}"
        }


@tool
async def send_telegram_notification(
    contact_id: int,
    message: str,
    username: str,
    expected_telegram_username: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envía una notificación por Telegram a un contacto.
    
    Args:
        contact_id: ID del contacto en la base de datos (DEBE ser el ID del contacto confirmado)
        message: Mensaje a enviar
        username: Username del usuario que envía
        expected_telegram_username: Username de Telegram esperado del contacto (para validación de seguridad). Si se proporciona, se valida que el contacto tenga este username.
    
    Returns:
        Resultado del envío con status y mensaje
    """
    from services.telegram_service import send_telegram_message
    
    logger.info(f"[ASSISTANT] Enviando Telegram a contacto {contact_id}" + (f" (telegram_username esperado: {expected_telegram_username})" if expected_telegram_username else ""))
    
    try:
        # Obtener datos del contacto
        sb = get_supabase_client()
        result = await sb.get_single(
            "user_contacts",
            "id,nombre,telegram_chat_id,telegram_username",
            {"id": contact_id, "username": username}
        )
        
        if not result:
            logger.error(f"[ASSISTANT] Contacto {contact_id} no encontrado para usuario {username}")
            return {"success": False, "error": "Contacto no encontrado o no pertenece a este usuario"}
        
        contact = result
        if not contact.get("telegram_chat_id"):
            logger.error(f"[ASSISTANT] Contacto {contact_id} no tiene Telegram vinculado")
            return {"success": False, "error": "El contacto no tiene Telegram vinculado"}
        
        # VALIDACIÓN CRÍTICA: Verificar que el telegram_username del contacto coincide con el esperado
        if expected_telegram_username:
            contact_telegram_username = (contact.get("telegram_username") or "").strip().lower().lstrip("@")
            expected_telegram_username_clean = expected_telegram_username.strip().lower().lstrip("@")
            if contact_telegram_username != expected_telegram_username_clean:
                logger.error(
                    f"[ASSISTANT] ERROR CRÍTICO: El contact_id {contact_id} corresponde a @{contact.get('telegram_username')}, "
                    f"pero se esperaba @{expected_telegram_username}. NO se enviará el mensaje por seguridad."
                )
                return {
                    "success": False,
                    "error": f"ERROR DE SEGURIDAD: El contacto con ID {contact_id} tiene el username de Telegram @{contact.get('telegram_username')}, pero se esperaba @{expected_telegram_username}. Por seguridad, no se envió el mensaje. Por favor, verifica el contacto correcto."
                }
        
        # Obtener nombre del usuario
        user_name = username.split("@")[0].title()
        
        # Formatear mensaje
        formatted_message = f"📬 Notificación de {user_name}:\n\n{message}"
        
        logger.info(f"[ASSISTANT] Validación OK: contact_id {contact_id} -> telegram_username @{contact.get('telegram_username')}")
        
        # Enviar mensaje y verificar resultado
        result = await send_telegram_message(
            chat_id=contact["telegram_chat_id"],
            message=formatted_message
        )
        
        # Verificar si el envío fue exitoso
        if not result.get("success"):
            error_msg = result.get("error", "Error desconocido")
            logger.error(f"[ASSISTANT] Error en envío de Telegram: {error_msg}")
            return {
                "success": False,
                "error": f"❌ No se pudo enviar el mensaje de Telegram: {error_msg}"
            }
        
        logger.info(f"[ASSISTANT] Telegram enviado a {contact['nombre']}")
        telegram_username = contact.get("telegram_username", "el contacto")
        return {
            "success": True,
            "message": f"✅ Mensaje de Telegram enviado correctamente a @{telegram_username}"
        }
        
    except Exception as e:
        logger.exception(f"[ASSISTANT] Error enviando Telegram: {e}")
        error_msg = str(e)
        return {
            "success": False, 
            "error": f"❌ No se pudo enviar el mensaje de Telegram. {error_msg if len(error_msg) < 100 else 'Error técnico. Por favor, inténtalo más tarde.'}"
        }


@tool
def get_current_date() -> str:
    """
    Obtiene la fecha actual. Útil para preguntas sobre plazos y calendarios fiscales.
    
    Returns:
        Fecha actual en formato legible
    """
    now = datetime.now()
    return f"Hoy es {now.strftime('%d de %B de %Y')} ({now.strftime('%A')})"


# Lista de herramientas
ASSISTANT_TOOLS = [
    rag_search,
    web_search_hacienda,
    list_user_contacts,
    send_email_notification,
    send_telegram_notification,
    get_current_date,
]

# Herramientas que son "acciones finales" - después de ejecutarse,
# el flujo debe ser determinístico (no volver al LLM)
FINAL_ACTION_TOOLS = ["send_email_notification", "send_telegram_notification"]


# ============================================================================
# NODOS DEL GRAFO
# ============================================================================

def get_llm():
    """Obtiene el LLM configurado con capacidad de fallback."""
    if not LANGCHAIN_AVAILABLE:
        raise ValueError("LangChain no disponible")
    
    from services.llm_fallback import get_llm_with_fallback
    
    llm, llm_type = get_llm_with_fallback(
        google_api_key=GOOGLE_API_KEY,
        openai_api_key=OPENAI_API_KEY,
        prefer_google=bool(GOOGLE_API_KEY),
        model_google="gemini-2.5-flash-lite",
        model_openai="gpt-4o-mini",
        temperature=0.3
    )
    
    return llm


def process_node(state: AssistantState) -> AssistantState:
    """
    Nodo principal que procesa el mensaje del usuario.
    """
    logger.info(f"[ASSISTANT] process_node - Iteración {state['iteration']}")
    
    user_message = state["user_message"]
    username = state["username"]
    
    # Construir prompt del sistema
    system_prompt = f"""Eres un asistente de IA para la aplicación Nementium.ai, una herramienta de gestión fiscal para autónomos y pequeñas empresas en España.

Tu rol es ayudar al usuario con:
1. Preguntas sobre cómo usar la aplicación
2. Información sobre modelos tributarios (303, 130, 111, etc.), plazos y obligaciones fiscales
3. Información sobre Seguridad Social para autónomos (cuotas, prestaciones, etc.)
4. Enviar notificaciones por email o Telegram a los contactos del usuario

Usuario actual: {username}

INSTRUCCIONES:
- Para preguntas sobre la app, Hacienda o Seguridad Social: usa primero rag_search para buscar en la documentación
- Si rag_search no da suficiente información, usa web_search_hacienda para buscar online
- Para enviar notificaciones: primero usa list_user_contacts para ver los contactos disponibles, luego send_email_notification o send_telegram_notification
- Para preguntas sobre plazos: usa get_current_date para saber la fecha actual
- Responde siempre en español
- Sé conciso pero completo
- Si no tienes información suficiente, dilo claramente

IMPORTANTE - MENSAJES DESPUÉS DE COMPLETAR TAREAS:
- Cuando completes una tarea (enviar email, responder pregunta, etc.) y vuelvas al contexto principal:
  * NO saludes de nuevo (no digas "¡Hola!", "Hola", etc.)
  * NO repitas el mensaje de bienvenida completo con todas tus capacidades
  * Usa mensajes cortos y continuistas como "¿En qué más puedo ayudarte?" o "Listo. ¿Necesitas algo más?"
  * Solo muestra el mensaje completo de bienvenida cuando es la PRIMERA interacción del usuario (sin historial previo)

IMPORTANTE - ENVÍO DE NOTIFICACIONES:
- SIEMPRE debes confirmar con el usuario ANTES de enviar cualquier notificación

FLUJO OBLIGATORIO PARA ENVIAR NOTIFICACIONES:
1. Cuando el usuario mencione un nombre de contacto (ej: "envía a elena medrano"):
   a) PRIMERO llama a list_user_contacts con search_term="elena medrano" para buscar el contacto
   b) Si no encuentras resultados, intenta con solo la primera palabra (ej: search_term="elena")
   c) Si encuentras UN contacto con email/telegram_username, USA ESE DATO para confirmar
   d) Solo si hay múltiples resultados o ninguno, pregunta al usuario para desambiguar

2. Si encontraste el contacto y tiene email/telegram_username:
   a) NUNCA pidas al usuario que te proporcione el email o username de Telegram
   b) USA el email/username que obtuviste de list_user_contacts
   c) Confirma directamente con ese dato: "¿Envío el email a elenamedranocopete@gmail.com?" o "¿Envío el mensaje de Telegram a @elenamedrano?"
   d) El usuario solo debe responder "sí" o "no", NO debe escribirte el email/username

3. Si el usuario no especifica a quién enviar, pregunta o muestra la lista de contactos

4. ANTES de llamar a send_email_notification o send_telegram_notification:
   * Si vas a enviar un EMAIL: confirma usando el EMAIL del contacto obtenido de list_user_contacts
     Ejemplo correcto: "¿Envío el email a elenamedranocopete@gmail.com?"
     Ejemplo INCORRECTO: "¿Me podrías proporcionar el email de Elena Medrano?"
   * Si vas a enviar un MENSAJE DE TELEGRAM: confirma usando el USERNAME DE TELEGRAM del contacto obtenido de list_user_contacts
     Ejemplo correcto: "¿Envío el mensaje de Telegram a @elenamedrano?"
     Ejemplo INCORRECTO: "¿Me podrías proporcionar el username de Telegram de Elena Medrano?"
   * NUNCA uses el ID del contacto (el usuario no lo conoce)
   * NUNCA pidas al usuario que te escriba el email o username - SIEMPRE usa los datos que obtuviste de list_user_contacts

5. AL LLAMAR a send_email_notification o send_telegram_notification:
   * DEBES usar el contact_id EXACTO del contacto que confirmaste (el que obtuviste de list_user_contacts)
   * Para EMAIL: SIEMPRE pasa el parámetro expected_email con el email que confirmaste (para validación de seguridad)
     Ejemplo: si confirmaste "elenamedranocopete@gmail.com" con contact_id=2, llama: 
     send_email_notification(contact_id=2, expected_email="elenamedranocopete@gmail.com", subject="...", body="...", username="...")
   * Para TELEGRAM: SIEMPRE pasa el parámetro expected_telegram_username con el username que confirmaste (para validación de seguridad)
     Ejemplo: si confirmaste "@elenamedrano" con contact_id=2, llama:
     send_telegram_notification(contact_id=2, expected_telegram_username="@elenamedrano", message="...", username="...")
   * NUNCA uses un contact_id diferente al del contacto confirmado - esto causaría enviar el mensaje a otra persona
   * El sistema validará automáticamente que el contact_id corresponde al email/username esperado - si no coincide, el envío será rechazado

6. DESPUÉS de enviar, SIEMPRE informa claramente al usuario:
   * Cuando recibas el resultado de send_email_notification o send_telegram_notification, DEBES responder al usuario confirmando el envío
   * Si se envió correctamente: responde con "✅ Email enviado correctamente a elenamedranocopete@gmail.com" o similar
   * Si hubo un error: responde con "❌ No se pudo enviar el email. [razón del error]"
   * NUNCA ignores el resultado de las herramientas de envío - SIEMPRE informa al usuario del resultado
   * NO termines sin informar al usuario sobre el resultado del envío

7. No envíes notificaciones sin confirmación previa del usuario

CRÍTICO - SEGURIDAD:
- NUNCA uses un contact_id que no corresponda al contacto confirmado
- SIEMPRE valida que el contact_id corresponde al email/username que confirmaste
- Si hay duda sobre el contact_id, vuelve a llamar a list_user_contacts para obtener el ID correcto
- El sistema validará automáticamente que el contact_id corresponde al expected_email - si no coincide, el envío será rechazado por seguridad"""

    try:
        llm = get_llm()
        
        # Construir mensajes
        messages = state["messages"].copy()
        
        # Añadir sistema si es primera iteración
        if state["iteration"] == 0:
            from langchain_core.messages import SystemMessage
            messages.insert(0, SystemMessage(content=system_prompt))
        
        # Detectar modelo inicial para log
        initial_model = "gemini-2.5-flash-lite" if GOOGLE_API_KEY else ("gpt-4o-mini" if OPENAI_API_KEY else "unknown")
        logger.info(f"[ASSISTANT] Invocando LLM ({initial_model}) - Iteración {state['iteration']}")
        
        # Invocar LLM con fallback automático
        from services.llm_fallback import invoke_llm_with_fallback
        
        response = invoke_llm_with_fallback(
            llm=llm,
            messages=messages,
            tools=ASSISTANT_TOOLS,
            google_api_key=GOOGLE_API_KEY,
            openai_api_key=OPENAI_API_KEY,
            model_google="gemini-2.5-flash-lite",
            model_openai="gpt-4o-mini",
            temperature=0.3,
            timeout=10.0
        )
        
        state["messages"].append(response)
        
        # Verificar si hay tool calls
        tool_calls = getattr(response, 'tool_calls', None) or []
        
        # Log de análisis del LLM
        logger.debug(f"[ASSISTANT] Análisis LLM - Iteración {state['iteration']}")
        logger.debug(f"[ASSISTANT] Respuesta del LLM: {response.content[:200]}...")
        
        if not tool_calls:
            # Sin tool calls = respuesta final
            state["should_finish"] = True
            state["final_response"] = response.content
            logger.info("[ASSISTANT] Respuesta final generada (sin tool calls)")
            logger.debug(f"[ASSISTANT] Respuesta completa: {response.content}")
        else:
            logger.info(f"[ASSISTANT] {len(tool_calls)} tool call(s) a ejecutar")
            for i, tc in enumerate(tool_calls):
                logger.debug(f"[ASSISTANT] Tool call {i+1}: {tc.get('name', 'unknown')} - args: {tc.get('args', {})}")
        
        return state
        
    except Exception as e:
        logger.exception(f"[ASSISTANT] Error en process_node: {e}")
        state["should_finish"] = True
        state["final_response"] = "Lo siento, ha ocurrido un problema al procesar tu solicitud. Por favor, inténtalo de nuevo en un momento."
        return state


def format_node(state: AssistantState) -> AssistantState:
    """
    Nodo que formatea la respuesta final.
    """
    logger.info("[ASSISTANT] format_node")
    
    if state.get("final_response"):
        logger.debug(f"[ASSISTANT] Respuesta final ya existe: {state['final_response'][:200]}...")
        return state
    
    # Obtener última respuesta del LLM
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            state["final_response"] = msg.content
            logger.debug(f"[ASSISTANT] Respuesta extraída del último AIMessage: {msg.content[:200]}...")
            break
    
    if not state.get("final_response"):
        state["final_response"] = "No pude procesar tu solicitud. Por favor, intenta de nuevo."
        logger.warning("[ASSISTANT] No se encontró respuesta en los mensajes, usando mensaje por defecto")
    
    # Si hay acciones ejecutadas y la respuesta es muy genérica o es el mensaje de bienvenida,
    # hacer el mensaje más conciso y continuista
    # PERO no sobrescribir si la respuesta contiene confirmaciones de envío exitoso
    if state.get("actions_executed") and len(state["actions_executed"]) > 0:
        final_response = state["final_response"]
        # Verificar si hay confirmaciones de envío en la respuesta
        has_send_confirmation = (
            "✅" in final_response or 
            "enviado correctamente" in final_response.lower() or
            "enviado a" in final_response.lower() or
            "mensaje enviado" in final_response.lower()
        )
        
        # Detectar si el LLM está generando un mensaje de bienvenida después de completar una tarea
        is_welcome_message = (
            "¡Hola!" in final_response or 
            "hola" in final_response.lower()[:10] or  # Saludo al inicio
            ("soy tu asistente" in final_response.lower() and "puedo ayudarte" in final_response.lower()) or
            ("nementium.ai" in final_response.lower() and "puedo ayudarte" in final_response.lower())
        )
        
        # Si la respuesta parece ser el mensaje de bienvenida o muy genérica, hacerla más concisa
        # PERO solo si NO contiene confirmación de envío
        if not has_send_confirmation:
            if is_welcome_message:
                # Si es un mensaje de bienvenida después de completar una tarea, reemplazarlo con mensaje corto sin saludo
                state["final_response"] = "¿En qué más puedo ayudarte?"
            elif len(final_response) > 200 and ("puedo ayudarte" in final_response.lower() or "preguntas sobre" in final_response.lower()):
                # Si es un mensaje largo con lista de capacidades, hacerlo más corto
                state["final_response"] = "¿En qué más puedo ayudarte?"
            elif len(final_response) > 200:
                # Si es muy largo y genérico, hacerlo más conciso
                state["final_response"] = "Listo. ¿En qué más puedo ayudarte?"
    
    logger.debug(f"[ASSISTANT] Respuesta final formateada: {state['final_response'][:200]}...")
    return state


def should_continue(state: AssistantState) -> Literal["tools", "format"]:
    """
    Decide si continuar con herramientas o formatear respuesta.
    """
    if state["should_finish"]:
        return "format"
    
    if state["iteration"] >= 5:
        logger.warning("[ASSISTANT] Máximo de iteraciones alcanzado")
        return "format"
    
    # Verificar si el último mensaje tiene tool_calls
    last_message = state["messages"][-1] if state["messages"] else None
    if isinstance(last_message, AIMessage):
        tool_calls = getattr(last_message, 'tool_calls', None) or []
        if tool_calls:
            return "tools"
    
    return "format"


def post_tools_node(state: AssistantState) -> AssistantState:
    """
    Nodo después de ejecutar herramientas.
    Detecta si se ejecutó una acción final y extrae su resultado.
    """
    state["iteration"] += 1
    
    # Registrar acciones ejecutadas y log
    tool_results = []
    final_action_result = None
    final_action_tool_name = None
    
    # Buscar ToolMessages de la iteración actual (los últimos añadidos)
    for msg in state["messages"]:
        if isinstance(msg, ToolMessage):
            tool_name = msg.name if hasattr(msg, 'name') else "unknown"
            tool_results.append(tool_name)
            state["actions_executed"].append({
                "tool": tool_name,
                "timestamp": datetime.now().isoformat()
            })
            
            # Detectar si se ejecutó una acción final
            if tool_name in FINAL_ACTION_TOOLS:
                final_action_tool_name = tool_name
                # Extraer el resultado de la acción final
                try:
                    content = msg.content if hasattr(msg, 'content') else ""
                    # El contenido puede ser JSON stringificado
                    if isinstance(content, str):
                        try:
                            result_data = json.loads(content)
                            if isinstance(result_data, dict):
                                # Usar el mensaje del resultado si existe
                                if result_data.get("message"):
                                    final_action_result = result_data["message"]
                                elif result_data.get("error"):
                                    final_action_result = result_data["error"]
                                else:
                                    final_action_result = str(result_data)
                            else:
                                final_action_result = content
                        except json.JSONDecodeError:
                            final_action_result = content
                    else:
                        final_action_result = str(content)
                except Exception as e:
                    logger.warning(f"[ASSISTANT] Error extrayendo resultado de {tool_name}: {e}")
                    final_action_result = "Acción completada"
    
    if tool_results:
        logger.debug(f"[ASSISTANT] Herramientas ejecutadas en iteración {state['iteration']-1}: {', '.join(tool_results)}")
        # Log del resultado de las herramientas (primeros 200 chars)
        for msg in state["messages"]:
            if isinstance(msg, ToolMessage):
                result_preview = str(msg.content)[:200] if hasattr(msg, 'content') else "sin contenido"
                logger.debug(f"[ASSISTANT] Resultado de {msg.name if hasattr(msg, 'name') else 'unknown'}: {result_preview}...")
    
    # Si se ejecutó una acción final, marcar para flujo determinístico
    if final_action_result and final_action_tool_name:
        state["final_action_triggered"] = True
        state["final_action_result"] = final_action_result
        logger.info(f"[ASSISTANT] FINAL ACTION detectada: {final_action_tool_name} - Resultado: {final_action_result[:100]}...")
    
    return state


def after_tools_router(state: AssistantState) -> Literal["format_final_action", "process"]:
    """
    Router que decide el siguiente paso después de ejecutar herramientas.
    Si se detectó una acción final, va al nodo determinístico.
    Si no, vuelve al LLM para continuar procesando.
    """
    if state.get("final_action_triggered"):
        logger.info("[ASSISTANT] Routing a format_final_action (flujo determinístico)")
        return "format_final_action"
    
    logger.debug("[ASSISTANT] Routing a process (continuar con LLM)")
    return "process"


def format_final_action_node(state: AssistantState) -> AssistantState:
    """
    Nodo determinístico que genera la respuesta final después de una acción final.
    No depende del LLM - usa directamente el resultado de la acción.
    """
    logger.info("[ASSISTANT] format_final_action_node - Generando respuesta determinística")
    
    # Obtener el resultado de la acción final
    action_result = state.get("final_action_result", "Acción completada")
    
    # Construir la respuesta determinística
    # El resultado ya contiene el emoji ✅ o ❌ y el mensaje
    follow_up = "\n\n¿En qué más puedo ayudarte?"
    
    state["final_response"] = f"{action_result}{follow_up}"
    state["should_finish"] = True
    
    logger.info(f"[ASSISTANT] Respuesta determinística generada: {state['final_response'][:100]}...")
    
    return state


# ============================================================================
# CREACIÓN DEL GRAFO
# ============================================================================

def create_assistant_graph():
    """
    Crea y compila el grafo del asistente.
    
    Flujo del grafo:
    START -> process -> [tools -> post_tools -> after_tools_router -> process | format_final_action] | format -> END
    
    Cuando se ejecuta una "acción final" (email, telegram), el flujo va determinísticamente
    a format_final_action en lugar de volver al LLM.
    """
    if not LANGCHAIN_AVAILABLE:
        raise ValueError("LangChain no disponible")
    
    # Crear ToolNode
    tool_node = ToolNode(ASSISTANT_TOOLS)
    
    # Crear grafo
    graph = StateGraph(AssistantState)
    
    # Añadir nodos
    graph.add_node("process", process_node)
    graph.add_node("tools", tool_node)
    graph.add_node("post_tools", post_tools_node)
    graph.add_node("format", format_node)
    graph.add_node("format_final_action", format_final_action_node)  # Nuevo nodo determinístico
    
    # Añadir edges
    graph.add_edge(START, "process")
    graph.add_conditional_edges("process", should_continue, {"tools": "tools", "format": "format"})
    graph.add_edge("tools", "post_tools")
    # Después de post_tools, el router decide si ir al LLM o al nodo determinístico
    graph.add_conditional_edges(
        "post_tools",
        after_tools_router,
        {"process": "process", "format_final_action": "format_final_action"}
    )
    graph.add_edge("format", END)
    graph.add_edge("format_final_action", END)  # El nodo determinístico va directo al END
    
    # Compilar
    compiled = graph.compile()
    logger.info("[ASSISTANT] Grafo del asistente creado (con flujo determinístico para acciones finales)")
    
    return compiled


# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================

async def process_assistant_message(
    message: str,
    username: str,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Procesa un mensaje del usuario y retorna la respuesta del asistente.
    
    Args:
        message: Mensaje del usuario
        username: Username del usuario
        conversation_history: Historial de conversación opcional
    
    Returns:
        Dict con response, actions_executed
    """
    logger.info("=" * 60)
    logger.info(f"[ASSISTANT] Procesando mensaje de {username}")
    logger.info(f"[ASSISTANT] Mensaje: {message[:100]}...")
    logger.debug(f"[ASSISTANT] Mensaje completo: {message}")
    logger.debug(f"[ASSISTANT] Historial de conversación: {len(conversation_history or [])} mensajes previos")
    
    try:
        # Crear grafo
        graph = create_assistant_graph()
        
        # Construir mensajes iniciales
        messages = []
        
        # Añadir historial si existe
        if conversation_history:
            for item in conversation_history[-10:]:  # Últimos 10 mensajes
                if item.get("role") == "user":
                    messages.append(HumanMessage(content=item["content"]))
                elif item.get("role") == "assistant":
                    messages.append(AIMessage(content=item["content"]))
        
        # Añadir mensaje actual
        messages.append(HumanMessage(content=message))
        
        # Estado inicial
        initial_state: AssistantState = {
            "messages": messages,
            "user_message": message,
            "username": username,
            "iteration": 0,
            "should_finish": False,
            "final_response": None,
            "actions_executed": [],
            # Campos para flujo determinístico de acciones finales
            "final_action_triggered": False,
            "final_action_result": None
        }
        
        # Ejecutar grafo
        logger.debug(f"[ASSISTANT] Iniciando ejecución del grafo - Iteración inicial: {initial_state['iteration']}")
        final_state = await graph.ainvoke(initial_state)
        
        response = final_state.get("final_response", "No pude procesar tu solicitud.")
        actions = final_state.get("actions_executed", [])
        iterations = final_state.get("iteration", 0)
        
        logger.info(f"[ASSISTANT] Respuesta generada ({len(response)} chars) después de {iterations} iteración(es)")
        logger.debug(f"[ASSISTANT] Respuesta completa: {response}")
        logger.debug(f"[ASSISTANT] Acciones ejecutadas: {len(actions)} - {[a.get('tool', 'unknown') for a in actions]}")
        logger.info("=" * 60)
        
        return {
            "response": response,
            "actions_executed": actions
        }
        
    except Exception as e:
        logger.exception(f"[ASSISTANT] Error: {e}")
        return {
            "response": "Lo siento, ha ocurrido un problema al procesar tu mensaje. Por favor, inténtalo de nuevo en un momento.",
            "actions_executed": [],
            "error": str(e)
        }
