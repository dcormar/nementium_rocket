import logging, os, httpx, asyncio
from dotenv import load_dotenv

# Carga .env en variables de entorno
load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auth import router as auth_router
from facturas_api import router as facturas_router
from ventas_api import router as ventas_router
from dashboard_api import router as dashboard_router
from modelos_api import router as modelos_router
from upload_api import router as upload_router
from upload_historico_api import router as upload_historico_router
from generate_invoice_api import router as generate_invoice_router
from processing_api import router as processing_router
from consulta_api import router as consulta_router
from assistant_api import router as assistant_router
from telegram_webhook_api import router as telegram_webhook_router
from email_contact_helper_api import router as email_contact_helper_router
from contextlib import asynccontextmanager




# Configuración global de logging desde .env
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_path = os.path.join(os.path.dirname(__file__), "log/modeloshaciendaweb.log")
log_format = '%(asctime)s %(levelname)s %(name)s %(message)s'

# Mapear string a nivel de logging
log_level_map = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
effective_log_level = log_level_map.get(LOG_LEVEL, logging.INFO)

logging.basicConfig(
    level=effective_log_level,
    format=log_format,
    handlers=[
        logging.FileHandler(log_path, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
# Silenciar loggers ruidosos de terceros
for logger_name in ("httpx", "httpcore", "uvicorn", "uvicorn.error", "uvicorn.access", "googleapiclient", "urllib3"):
    logging.getLogger(logger_name).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
logger.info(f"Nivel de logging configurado: {LOG_LEVEL}")

# ----------------------------------------
# Lifespan: se ejecuta antes de montar la app
# ----------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger(__name__)

    # Leer variables
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

    if not supabase_url or not supabase_key:
        logger.error("Faltan variables SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en el entorno.")
        raise RuntimeError("SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY no configuradas.")

    # URL genérica de salud del servicio REST de Supabase
    health_url = f"{supabase_url.rstrip('/')}/rest/v1/"

    logger.info(f"Verificando conexión con Supabase en: {health_url}")

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(health_url, headers={"apikey": supabase_key})

        if resp.status_code not in (200, 401, 404):
            raise RuntimeError(
                f"Supabase respondió con un código inesperado al arrancar: {resp.status_code}"
            )

        logger.info("Conexión con Supabase verificada correctamente.")
        
        # Verificar acceso a la tabla user_contacts
        logger.info("Verificando acceso a la tabla user_contacts...")
        try:
            from services.supabase_rest import SupabaseREST
            
            sb = SupabaseREST()
            result = await sb.get("user_contacts", "id", {})
            
            if result and len(result) > 0:
                logger.info(f"Acceso a user_contacts verificado correctamente (encontrado al menos 1 elemento).")
            else:
                logger.info("Acceso a user_contacts verificado correctamente (tabla vacía pero accesible).")
        except Exception as table_error:
            logger.exception(f"Error verificando tabla user_contacts: {table_error}")
            raise RuntimeError(f"Error accediendo a la tabla user_contacts: {str(table_error)}") from table_error

    except httpx.RequestError as e:
        logger.error(f"No se pudo conectar con Supabase: {e}")
        raise RuntimeError("Error de red al conectar con Supabase") from e

    # Continue app startup
    yield


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(facturas_router)
app.include_router(ventas_router)
app.include_router(dashboard_router)
app.include_router(modelos_router)
app.include_router(upload_router)
app.include_router(upload_historico_router)
app.include_router(generate_invoice_router)
app.include_router(processing_router)
app.include_router(consulta_router)
app.include_router(assistant_router)
app.include_router(telegram_webhook_router)
app.include_router(email_contact_helper_router)

logger.info("Routers montados y aplicación FastAPI iniciada")

@app.get("/")
def read_root():
    return {"msg": "Backend FastAPI funcionando"}
