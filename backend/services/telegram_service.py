# telegram_service.py
# Servicio de Telegram para el asistente

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path
import httpx

# Cargar .env si está disponible (para asegurar que las variables estén disponibles)
try:
    from dotenv import load_dotenv
    # Intentar cargar .env desde el directorio backend
    current_file = Path(__file__)
    backend_dir = current_file.parent.parent  # backend/services/ -> backend/
    env_path = backend_dir / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)  # override=True para que .env tenga prioridad
    else:
        # Fallback: intentar cargar desde directorio actual
        load_dotenv(override=True)
except ImportError:
    # dotenv no disponible, continuar sin cargar (asumiendo que main.py ya lo cargó)
    pass

logger = logging.getLogger(__name__)

# Configuración (después de cargar .env)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def send_telegram_message(
    chat_id: str,
    message: str,
    parse_mode: str = "HTML",
    disable_notification: bool = False
) -> Dict[str, Any]:
    """
    Envía un mensaje por Telegram.
    
    Args:
        chat_id: ID del chat de Telegram
        message: Mensaje a enviar
        parse_mode: Modo de parseo ('HTML' o 'Markdown')
        disable_notification: Si True, envía sin notificación
    
    Returns:
        Dict con resultado del envío
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("[TELEGRAM] TELEGRAM_BOT_TOKEN no configurado")
        raise ValueError("TELEGRAM_BOT_TOKEN no está configurado")
    
    url = f"{TELEGRAM_API_URL}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_notification": disable_notification
    }
    
    logger.info(f"[TELEGRAM] Enviando mensaje a chat_id={chat_id}")
    logger.debug(f"[TELEGRAM] URL: {url}")
    logger.debug(f"[TELEGRAM] Token configurado: {TELEGRAM_BOT_TOKEN[:10]}...{TELEGRAM_BOT_TOKEN[-5:] if len(TELEGRAM_BOT_TOKEN) > 15 else 'CORTO'}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=30)
            logger.debug(f"[TELEGRAM] Response status: {response.status_code}")
            result = response.json()
            logger.debug(f"[TELEGRAM] Response body: {result}")
            
            if result.get("ok"):
                logger.info(f"[TELEGRAM] Mensaje enviado: message_id={result.get('result', {}).get('message_id')}")
                return {"success": True, "message_id": result.get("result", {}).get("message_id")}
            else:
                error_desc = result.get("description", "Error desconocido")
                logger.error(f"[TELEGRAM] Error: {error_desc}")
                return {"success": False, "error": error_desc}
                
    except httpx.TimeoutException:
        logger.error("[TELEGRAM] Timeout enviando mensaje")
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        logger.error(f"[TELEGRAM] Error: {e}")
        return {"success": False, "error": str(e)}


async def get_bot_info() -> Dict[str, Any]:
    """
    Obtiene información del bot.
    """
    if not TELEGRAM_BOT_TOKEN:
        return {"success": False, "error": "Token no configurado"}
    
    url = f"{TELEGRAM_API_URL}/getMe"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10)
            result = response.json()
            
            if result.get("ok"):
                return {"success": True, "bot": result.get("result")}
            else:
                return {"success": False, "error": result.get("description")}
                
    except Exception as e:
        return {"success": False, "error": str(e)}


async def set_webhook(webhook_url: str) -> Dict[str, Any]:
    """
    Configura el webhook del bot.
    
    Args:
        webhook_url: URL del webhook (debe ser HTTPS)
    """
    if not TELEGRAM_BOT_TOKEN:
        return {"success": False, "error": "Token no configurado"}
    
    url = f"{TELEGRAM_API_URL}/setWebhook"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={"url": webhook_url},
                timeout=10
            )
            result = response.json()
            
            if result.get("ok"):
                logger.info(f"[TELEGRAM] Webhook configurado: {webhook_url}")
                return {"success": True}
            else:
                return {"success": False, "error": result.get("description")}
                
    except Exception as e:
        return {"success": False, "error": str(e)}


async def process_webhook_update(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Procesa una actualización recibida por webhook.
    
    Args:
        update: Objeto update de Telegram
    
    Returns:
        Respuesta a enviar (si aplica)
    """
    from services.supabase_rest import SupabaseREST
    
    message = update.get("message", {})
    text = message.get("text", "")
    chat_id = str(message.get("chat", {}).get("id", ""))
    username = message.get("from", {}).get("username", "")
    
    if not text or not chat_id:
        return None
    
    logger.info(f"[TELEGRAM] Mensaje recibido de {username}: {text[:50]}...")
    
    # Comando /start con código de vinculación
    if text.startswith("/start "):
        link_code = text.replace("/start ", "").strip().upper()
        
        if link_code:
            try:
                sb = SupabaseREST()
                
                # Buscar contacto con este código
                # Nota: Esto requiere que el campo metadata tenga el código
                result = await sb.get("user_contacts", "*", {})
                
                # Buscar el contacto con el código correcto
                contact = None
                for c in result:
                    metadata = c.get("metadata", {}) or {}
                    if metadata.get("telegram_link_code") == link_code:
                        contact = c
                        break
                
                if contact:
                    # Vincular chat_id al contacto
                    await sb.patch(
                        "user_contacts",
                        {
                            "telegram_chat_id": chat_id,
                            "telegram_username": username,
                            "metadata": {}  # Limpiar código usado
                        },
                        {"id": f"eq.{contact['id']}"}
                    )
                    
                    logger.info(f"[TELEGRAM] Contacto vinculado: {contact['nombre']} -> {chat_id}")
                    
                    await send_telegram_message(
                        chat_id=chat_id,
                        message=f"✅ <b>¡Vinculación exitosa!</b>\n\n"
                               f"Tu cuenta de Telegram ha sido vinculada como contacto de Nementium.ai.\n\n"
                               f"Ahora recibirás notificaciones aquí."
                    )
                    return {"status": "linked", "contact_id": contact["id"]}
                else:
                    await send_telegram_message(
                        chat_id=chat_id,
                        message="❌ Código de vinculación inválido o expirado.\n\n"
                               "Solicita un nuevo código en la aplicación."
                    )
                    return {"status": "invalid_code"}
                    
            except Exception as e:
                logger.error(f"[TELEGRAM] Error vinculando: {e}")
                await send_telegram_message(
                    chat_id=chat_id,
                    message="❌ Error procesando la vinculación. Intenta de nuevo más tarde."
                )
                return {"status": "error", "error": str(e)}
    
    # Comando /start sin código
    elif text == "/start":
        await send_telegram_message(
            chat_id=chat_id,
            message="👋 <b>¡Hola!</b>\n\n"
                   "Soy el bot de notificaciones de <b>Nementium.ai</b>.\n\n"
                   "Para vincular tu cuenta, necesitas un código de la aplicación.\n"
                   "Pide al usuario de Nementium.ai que te envíe el enlace de vinculación."
        )
        return {"status": "welcome"}
    
    # Comando /help
    elif text == "/help":
        await send_telegram_message(
            chat_id=chat_id,
            message="ℹ️ <b>Ayuda</b>\n\n"
                   "Este bot envía notificaciones de la aplicación Nementium.ai.\n\n"
                   "<b>Comandos disponibles:</b>\n"
                   "/start - Iniciar bot o vincular cuenta\n"
                   "/help - Mostrar esta ayuda\n"
                   "/status - Ver estado de vinculación"
        )
        return {"status": "help"}
    
    # Comando /status
    elif text == "/status":
        try:
            sb = SupabaseREST()
            result = await sb.get(
                "user_contacts",
                "nombre,username",
                {"telegram_chat_id": f"eq.{chat_id}"}
            )
            
            if result and len(result) > 0:
                contact = result[0]
                await send_telegram_message(
                    chat_id=chat_id,
                    message=f"✅ <b>Cuenta vinculada</b>\n\n"
                           f"Nombre: {contact['nombre']}\n"
                           f"Usuario: {contact['username']}"
                )
            else:
                await send_telegram_message(
                    chat_id=chat_id,
                    message="❌ Tu cuenta de Telegram no está vinculada a ningún contacto."
                )
                
        except Exception as e:
            logger.error(f"[TELEGRAM] Error en status: {e}")
            
        return {"status": "status_checked"}
    
    # Mensaje no reconocido
    else:
        await send_telegram_message(
            chat_id=chat_id,
            message="🤖 Este bot solo envía notificaciones.\n\n"
                   "Usa /help para ver los comandos disponibles."
        )
        return {"status": "unknown_command"}


# ============================================================================
# ENDPOINT PARA WEBHOOK (usar en telegram_webhook_api.py si se necesita)
# ============================================================================

async def handle_telegram_webhook(update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handler para el endpoint de webhook.
    Llamar desde un router de FastAPI.
    """
    try:
        result = await process_webhook_update(update)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error(f"[TELEGRAM] Error en webhook: {e}")
        return {"ok": False, "error": str(e)}
