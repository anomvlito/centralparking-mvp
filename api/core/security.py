"""CORS y autenticación transversal de transporte."""

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from jose import JWTError, jwt

API_KEY = os.environ.get("API_KEY", "")
JWT_SECRET = os.environ.get(
    "JWT_SECRET", "changeme-set-JWT_SECRET-in-env"
)
PUBLIC_PATHS = {"/auth/login", "/docs", "/openapi.json", "/redoc"}
PUBLIC_PATH_PREFIXES = {
    "/api/monitor/file",
    "/api/monitor/images",
    "/api/monitor/review",
    "/api/ftp/",
}


def cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "3600",
    }


async def security_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(status_code=200, headers=cors_headers())

    client = request.client.host if request.client else ""
    is_local = client in ("127.0.0.1", "::1", "localhost")
    path = request.url.path
    is_public = path in PUBLIC_PATHS or any(
        path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES
    )
    if not is_local and not is_public:
        has_valid_api_key = bool(
            API_KEY and request.headers.get("X-API-Key", "") == API_KEY
        )
        has_valid_jwt = False
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                jwt.decode(
                    auth_header[7:],
                    JWT_SECRET,
                    algorithms=["HS256"],
                )
                has_valid_jwt = True
            except JWTError:
                pass
        if not (has_valid_api_key or has_valid_jwt):
            return JSONResponse(
                {"detail": "Se requiere autenticación (API Key o JWT)"},
                status_code=401,
                headers=cors_headers(),
            )

    response = await call_next(request)
    for key, value in cors_headers().items():
        response.headers[key] = value
    return response


def install_security(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=3600,
    )
    app.middleware("http")(security_middleware)
