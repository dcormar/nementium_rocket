from datetime import datetime, timedelta
from typing import Optional
import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# =========================
# Configuración desde variables de entorno
# =========================
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "supersecretkey")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))

# Usuario(s) de demo en memoria (sin BD)
fake_users_db = {
    "demo@demo.com": {
        "username": "demo@demo.com",
        "full_name": "Demo User",
        # password en claro: "demo"
        "hashed_password": "$2b$12$ifqc0gT0cKUSs9oszgJIhulcWO4tnCoTJzkDxFiO1crBUjArglfIG",
        "disabled": False,
    }
}

# =========================
# Modelos
# =========================
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    username: str
    full_name: Optional[str] = None
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

# =========================
# Seguridad
# =========================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

router = APIRouter(prefix="/auth", tags=["auth"])

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def get_user(db: dict, username: str) -> Optional[UserInDB]:
    user_dict = db.get(username)
    if user_dict:
        return UserInDB(**user_dict)
    return None

def authenticate_user(db: dict, username: str, password: str) -> Optional[UserInDB]:
    user = get_user(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if user.disabled:
        return None
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# =========================
# Dependencia reutilizable
# =========================
def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    Extrae el usuario autenticado desde el JWT (Authorization: Bearer <token>).
    Lanza 401 si el token no es válido o el usuario no existe en fake_users_db.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user_in_db = get_user(fake_users_db, username)
    if user_in_db is None:
        raise credentials_exception

    # devolvemos un User “limpio” (sin hashed_password)
    return User(username=user_in_db.username, full_name=user_in_db.full_name, disabled=user_in_db.disabled)

# =========================
# Endpoints
# =========================
@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login con usuario/contraseña contra fake_users_db.
    Por defecto existe:
      username: demo@demo.com
      password: demo
    """
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user