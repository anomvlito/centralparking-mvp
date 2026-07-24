"""Diagnóstico autenticado de configuración y auditoría direccional."""

from fastapi import APIRouter, Depends

from api.auth import require_admin
from api.core.config import DIRECTION_SETTINGS
from api.database import get_direction_audit_metrics

router = APIRouter(
    prefix="/api/audit/direction",
    tags=["direction-audit"],
    dependencies=[Depends(require_admin)],
)


@router.get("/config")
async def get_direction_config():
    return DIRECTION_SETTINGS.public_dict()


@router.get("/metrics")
async def get_direction_metrics(date: str = None, limit: int = 5000):
    return get_direction_audit_metrics(date=date, limit=limit)
