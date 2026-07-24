"""Ciclo de vida único de la aplicación."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from api.auth import ensure_default_admin
    from api.staging import staging_loop

    ensure_default_admin()
    task = asyncio.create_task(staging_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
