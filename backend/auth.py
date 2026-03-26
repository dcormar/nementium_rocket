"""
Autenticación basada en Supabase Auth.

El frontend hace login contra Supabase Auth directamente y obtiene un access_token JWT.
El backend valida ese JWT usando el SUPABASE_JWT_SECRET del proyecto.

No hay endpoints de login/refresh propios: todo lo gestiona Supabase Auth + el SDK JS.
Se mantienen /api/auth/me (útil para verificar sesión) y los modelos User/UserInDB
para compatibilidad con el resto de endpoints.
"""

from typing import Optional
import os
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

logger = logging.getLogger("auth")

# =========================
# Configuración Supabase JWT
# =========================
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
ALGORITHM = "HS256"

if not SUPABASE_JWT_SECRET:
    logger.warning("[AUTH] SUPABASE_JWT_SECRET no configurado - la autenticación fallará")

# =========================
# Modelos
# =========================
class User(BaseModel):
    id: str  # Supabase user UUID
    email: Optional[str] = None
    # Aliases para compatibilidad con código existente
    username: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None

# Mantener UserInDB como alias para no romper imports existentes
UserInDB = User

# =========================
# Seguridad
# =========================
security = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """
    Valida el JWT de Supabase Auth (Authorization: Bearer <token>).
    Lanza 401 si el token no es válido o ha expirado.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        logger.warning("[AUTH] No se recibió token")
        raise credentials_exception

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=[ALGORITHM],
            audience="authenticated",
        )

        user_id: Optional[str] = payload.get("sub")
        email: Optional[str] = payload.get("email")

        if not user_id:
            logger.warning("[AUTH] Token sin sub (user id)")
            raise credentials_exception

        logger.debug(f"[AUTH] Token OK para {email} (id={user_id})")

        return User(
            id=user_id,
            email=email,
            username=email,
            full_name=email,
            disabled=False,
        )

    except JWTError as e:
        logger.error(f"[AUTH] JWT Error: {type(e).__name__} - {str(e)}")
        raise credentials_exception


# =========================
# Endpoints
# =========================
@router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Devuelve el usuario autenticado (validando el JWT de Supabase)."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
    }
