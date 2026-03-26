# Nementium Rocket

Plataforma web de gestion fiscal y contable para autonomos y PYMEs desarrollada por **Nementium Technologies**. Automatiza el procesamiento de facturas, ventas, modelos tributarios y consultas mediante IA.

## Stack Tecnologico

### Frontend (este repo root)
- **React 19** + TypeScript
- **Vite 7** (dev server + build)
- **Tailwind CSS 4** (via PostCSS)
- **lucide-react** para iconos
- **react-router-dom 7** (no se usa como router SPA; la navegacion es por estado `page` en `App.tsx`)
- Sin libreria de graficas: la grafica de barras del dashboard es SVG custom (`BarsChart`)

### Backend (`backend/`)
- **FastAPI** + **Uvicorn**
- **Supabase** (PostgreSQL) via REST directo con `httpx` (no supabase-py)
- **JWT** auth con `python-jose` + `passlib/bcrypt`
- **Google Gemini** (`google-generativeai`) como LLM principal + **OpenAI** como fallback
- **LangChain 0.3** + **LangGraph 0.2** para workflows de agentes (consulta, asistente, email)
- **Google Drive API** para almacenamiento de facturas procesadas
- **ReportLab** para generacion de PDFs de facturas
- **Resend** para envio de emails
- **Playwright** para web scraping
- **DuckDuckGo Search** para busquedas web en agentes

## Estructura del Proyecto

```
nementium_rocket/
├── src/                          # Frontend React
│   ├── App.tsx                   # Router principal (estado `page`), nav, session management
│   ├── main.tsx                  # Entry point
│   ├── config.ts                 # Constantes de config (UPLOAD_DELAY_MS)
│   ├── pages/
│   │   ├── LoginPage.tsx         # Login con JWT (POST /api/auth/token)
│   │   ├── DashboardPage.tsx     # Resumen 6 meses + grafica SVG + historico operaciones
│   │   ├── UploadPage.tsx        # Subida de facturas/ventas con flujo AI paso a paso
│   │   ├── EstadoModelosPage.tsx # Estado trimestral modelos Hacienda (303, 130)
│   │   ├── MesDetallePage.tsx    # Historico con filtros y ordenacion
│   │   ├── CreateInvoicePage.tsx # Crear facturas de venta (con asistente IA)
│   │   └── ConsultaPage.tsx      # Consultas en lenguaje natural sobre datos
│   ├── components/
│   │   └── ChatAssistant.tsx     # Chat overlay IA (RAG + tools)
│   └── utils/
│       ├── fetchWithAuth.ts      # Wrapper fetch con JWT auto-401 + evento actividad
│       ├── useSessionRefresh.ts  # Hook: refresh token automatico, aviso inactividad
│       └── sleep.ts              # Utilidad sleep
├── backend/                      # FastAPI backend
│   ├── main.py                   # App FastAPI, routers, lifespan (check Supabase)
│   ├── auth.py                   # Auth endpoints (/api/auth/token, /me, /refresh)
│   ├── upload_api.py             # Subida ficheros + deteccion duplicados
│   ├── processing_api.py         # Pipeline AI analisis + Drive
│   ├── facturas_api.py           # CRUD facturas
│   ├── ventas_api.py             # CRUD ventas
│   ├── dashboard_api.py          # Resumen dashboard + historico
│   ├── modelos_api.py            # Calculo modelos tributarios
│   ├── generate_invoice_api.py   # Generacion facturas PDF
│   ├── consulta_api.py           # Endpoint consultas IA
│   ├── assistant_api.py          # Chat asistente RAG
│   ├── telegram_webhook_api.py   # Webhook Telegram
│   ├── email_contact_helper_api.py # Agente busqueda contactos email
│   ├── services/
│   │   ├── supabase_rest.py      # Cliente REST Supabase (httpx)
│   │   ├── drive_service.py      # Google Drive API
│   │   ├── invoice_analyzer_service.py  # Analisis facturas con Gemini/OpenAI
│   │   ├── llm_fallback.py       # Estrategia fallback Gemini -> OpenAI
│   │   ├── rag_service.py        # RAG: embeddings + busqueda semantica
│   │   ├── assistant_agent.py    # Agente LangGraph del asistente
│   │   ├── consulta_agent_*.py   # Agente consultas (graph, state, tools, executor)
│   │   ├── email_contact_helper_agent.py # Agente LangGraph busqueda contactos
│   │   ├── email_service.py      # Envio emails via Resend
│   │   ├── telegram_service.py   # Bot Telegram
│   │   └── exchange_service.py   # Tipos de cambio
│   ├── scripts/                  # Scripts de mantenimiento (index_rag_content.py)
│   ├── credentials/              # Tokens OAuth (gitignored)
│   └── requirements.txt
├── docs/ragdocuments/            # Documentos para indexar en RAG
│   ├── app_manual/               # Manual de usuario
│   ├── hacienda/                 # Info modelos tributarios
│   ├── seg_social/               # Guias Seguridad Social
│   └── nementium/                # About Nementium
├── vite.config.ts                # Proxy /api -> localhost:8000
├── package.json
├── tsconfig*.json
└── .env.example
```

## API Endpoints (principales)

| Prefijo | Descripcion |
|---------|------------|
| `/api/auth/` | Login (token), refresh, /me |
| `/api/uploads/` | Subida ficheros, historico, duplicados |
| `/api/processing/` | Pipeline AI analisis + Drive |
| `/api/facturas/` | CRUD facturas |
| `/api/ventas/` | CRUD ventas |
| `/api/dashboard/` | Resumen + historico operaciones |
| `/api/modelos/` | Estado modelos Hacienda |
| `/api/generate-invoice/` | Crear facturas PDF |
| `/api/consulta/` | Consultas lenguaje natural |
| `/api/assistant/` | Chat asistente RAG |
| `/api/telegram/` | Webhook bot Telegram |
| `/api/email-contact-helper/` | Agente busqueda contactos |

## Configuracion

### Variables de entorno (`.env.example`)
- `JWT_SECRET_KEY` / `JWT_ALGORITHM` / `ACCESS_TOKEN_EXPIRE_MINUTES` - Auth
- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` - Base de datos
- `N8N_WEBHOOK_URL` / `N8N_WEBHOOK_SECRET` - Integraciones N8N
- `EMAIL_CONTACT_HELPER_API_KEY` - API key agente email

### Desarrollo
```bash
# Frontend
npm install
npm run dev          # Vite en http://localhost:5173

# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000 -ª mejor ejecutar con "cd backend + ./run.sh"
```

El proxy de Vite redirige `/api/*` a `localhost:8000`.

## Arquitectura de Sesion

- Login devuelve JWT (15 min expiracion)
- `fetchWithAuth` wrapper: inyecta Bearer token, detecta 401, emite evento `api-activity`
- `useSessionRefresh` hook: decodifica JWT para obtener `exp`, programa refresh automatico 2 min antes de expirar, muestra modal de inactividad a los 14 min
- Modal `SessionWarningModal` con countdown permite extender o cerrar sesion

## Flujo de Subida de Facturas

1. Upload fichero -> backend almacena en Supabase Storage
2. Deteccion de duplicados por hash
3. Analisis AI (Gemini/OpenAI) extrae datos: proveedor, importes, IVA, moneda, etc.
4. Usuario confirma/edita datos extraidos
5. Subida a Google Drive
6. Registro en Supabase (tabla facturas)

## Agentes IA

- **Asistente (ChatAssistant)**: RAG sobre documentos + tools para consultar datos, enviar emails/Telegram
- **Consulta**: Agente LangGraph que traduce preguntas naturales a queries SQL sobre Supabase
- **Email Contact Helper**: Busca emails de contacto de empresas via web scraping + LLM
