"""
auth.py — Central Parking MVP
Autenticación JWT con usuarios en PostgreSQL.

Endpoints:
  POST /auth/login           — login, devuelve token JWT
  GET  /auth/me              — info del usuario actual
  PATCH /auth/password       — cambiar contraseña propia
  POST  /auth/users          — crear usuario (solo admin)
  GET   /auth/users          — listar usuarios (solo admin)
  PATCH /auth/users/{id}     — activar/desactivar (solo admin)
"""

import os
import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from api.database import _db, now_cl

router  = APIRouter(prefix="/auth", tags=["auth"])
_pwd    = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)

SECRET_KEY = os.environ.get("JWT_SECRET", "changeme-set-JWT_SECRET-in-env")
ALGORITHM  = "HS256"
TOKEN_HOURS = 24 * 7


# ─────────────────────── JWT utils ──────────────────────────────────────────

def _make_token(user_id: int, username: str, role: str) -> str:
    exp = datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_HOURS)
    return jwt.encode(
        {"sub": str(user_id), "username": username, "role": role, "exp": exp},
        SECRET_KEY, algorithm=ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(401, "Token inválido o expirado")


def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> dict:
    if not creds:
        raise HTTPException(401, "Se requiere autenticación")
    return decode_token(creds.credentials)


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Se requiere rol admin")
    return user


# ─────────────────────── DB helpers ─────────────────────────────────────────

def _get_user_by_username(username: str) -> Optional[dict]:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE username = %s AND is_active = true",
                (username,)
            )
            row = cur.fetchone()
    return dict(row) if row else None


def _create_user_db(username: str, password: str, role: str = "admin") -> dict:
    hashed = _pwd.hash(password)
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (username, password_hash, role)
                VALUES (%s, %s, %s)
                RETURNING id, username, role, created_at
            """, (username, hashed, role))
            row = cur.fetchone()
    return dict(row)


def ensure_default_admin():
    """Crea el usuario admin por defecto si no existe ningún usuario."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM users")
            count = cur.fetchone()["n"]
    if count == 0:
        _create_user_db("admin", "admin123", "admin")
        print("[auth] Usuario admin creado con contraseña admin123 — cambiala!")


# ─────────────────────── Schemas ────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "admin"

class ToggleUserRequest(BaseModel):
    is_active: bool


# ─────────────────────── Endpoints ──────────────────────────────────────────

@router.post("/login")
def login(req: LoginRequest):
    user = _get_user_by_username(req.username)
    if not user or not _pwd.verify(req.password, user["password_hash"]):
        raise HTTPException(401, "Usuario o contraseña incorrectos")

    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET last_login = now() WHERE id = %s",
                (user["id"],)
            )

    token = _make_token(user["id"], user["username"], user["role"])
    return {
        "access_token": token,
        "token_type":   "bearer",
        "username":     user["username"],
        "role":         user["role"],
        "expires_in":   TOKEN_HOURS * 3600,
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, username, role, is_active, created_at, last_login
                FROM users WHERE id = %s
            """, (int(user["sub"]),))
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Usuario no encontrado")
    r = dict(row)
    r["created_at"] = r["created_at"].astimezone(__import__('zoneinfo').ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M")
    r["last_login"]  = r["last_login"].astimezone(__import__('zoneinfo').ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M") if r["last_login"] else None
    return r


@router.patch("/password")
def change_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    db_user = _get_user_by_username(user["username"])
    if not db_user or not _pwd.verify(req.current_password, db_user["password_hash"]):
        raise HTTPException(401, "Contraseña actual incorrecta")
    if len(req.new_password) < 6:
        raise HTTPException(400, "La contraseña debe tener al menos 6 caracteres")
    new_hash = _pwd.hash(req.new_password)
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (new_hash, db_user["id"])
            )
    return {"status": "ok", "message": "Contraseña actualizada"}


@router.post("/users")
def create_user(req: CreateUserRequest, _: dict = Depends(require_admin)):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE username = %s", (req.username,))
            if cur.fetchone():
                raise HTTPException(409, f"Usuario '{req.username}' ya existe")
    if len(req.password) < 6:
        raise HTTPException(400, "La contraseña debe tener al menos 6 caracteres")
    user = _create_user_db(req.username, req.password, req.role)
    return {"status": "created", **user}


@router.get("/users")
def list_users(_: dict = Depends(require_admin)):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, username, role, is_active, created_at, last_login
                FROM users ORDER BY id
            """)
            rows = cur.fetchall()
    _CL = __import__('zoneinfo').ZoneInfo("America/Santiago")
    result = []
    for r in rows:
        d = dict(r)
        d["created_at"] = d["created_at"].astimezone(_CL).strftime("%Y-%m-%d %H:%M")
        d["last_login"]  = d["last_login"].astimezone(_CL).strftime("%Y-%m-%d %H:%M") if d["last_login"] else None
        result.append(d)
    return result


@router.patch("/users/{user_id}")
def toggle_user(user_id: int, req: ToggleUserRequest, current: dict = Depends(require_admin)):
    if int(current["sub"]) == user_id:
        raise HTTPException(400, "No podés desactivar tu propio usuario")
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET is_active = %s WHERE id = %s RETURNING username",
                (req.is_active, user_id)
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Usuario no encontrado")
    action = "activado" if req.is_active else "desactivado"
    return {"status": action, "username": row["username"]}
