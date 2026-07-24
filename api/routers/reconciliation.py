from fastapi import APIRouter, HTTPException, Query

from api.schemas.reconciliation import (
    DetectionActionRequest,
    ReconcileStayRequest,
)
from api.services.reconciliation import (
    dismiss_detection,
    list_detections,
    list_stays,
    reconcile_stay,
)

router = APIRouter(tags=["reconciliation"])


@router.get("/api/detections")
async def detections(
    limit: int = Query(100, ge=1, le=500),
    match_status: str | None = None,
    date: str | None = None,
):
    try:
        return list_detections(
            limit=limit, match_status=match_status, date=date
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/api/stays")
async def stays(
    limit: int = Query(100, ge=1, le=500),
    status: str | None = None,
    date: str | None = None,
    plate: str | None = None,
):
    try:
        return list_stays(
            limit=limit, status=status, date=date, plate=plate
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/api/stays/reconcile")
async def reconcile(request: ReconcileStayRequest):
    try:
        return reconcile_stay(request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.patch("/api/detections/{detection_id}")
async def patch_detection(
    detection_id: int, request: DetectionActionRequest
):
    try:
        return dismiss_detection(detection_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
