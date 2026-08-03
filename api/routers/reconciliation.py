from fastapi import APIRouter, Depends, HTTPException, Query
from api.auth import get_current_user, require_admin

from api.schemas.reconciliation import (
    DetectionActionRequest,
    PlateExclusionRequest,
    ReconcileStayRequest,
)
from api.services.reconciliation import (
    dismiss_detection,
    list_detections,
    list_stays,
    list_proposals,
    reconcile_exact,
    create_plate_exclusion,
    reconcile_stay,
    set_direction,
)

router = APIRouter(tags=["reconciliation"])


@router.get("/api/detections")
async def detections(
    limit: int = Query(100, ge=1, le=500),
    match_status: str | None = None,
    date: str | None = None,
    _: dict = Depends(get_current_user),
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
    _: dict = Depends(get_current_user),
):
    try:
        return list_stays(
            limit=limit, status=status, date=date, plate=plate
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/api/stays/reconcile")
async def reconcile(
    request: ReconcileStayRequest,
    _: dict = Depends(require_admin),
):
    try:
        return reconcile_stay(request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.patch("/api/detections/{detection_id}")
async def patch_detection(
    detection_id: int,
    request: DetectionActionRequest,
    _: dict = Depends(require_admin),
):
    try:
        if request.action == "set_direction":
            return set_direction(detection_id, request.direction)
        return dismiss_detection(detection_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/api/stay-proposals")
async def proposals(
    date: str,
    limit: int = Query(100, ge=1, le=200),
    _: dict = Depends(get_current_user),
):
    try:
        return list_proposals(date=date, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/api/stays/auto-reconcile-exact")
async def auto_reconcile_exact(
    date: str,
    limit: int = Query(200, ge=1, le=200),
    _: dict = Depends(require_admin),
):
    try:
        return reconcile_exact(date=date, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/api/plate-exclusions")
async def exclude_plate(
    request: PlateExclusionRequest,
    user: dict = Depends(require_admin),
):
    try:
        return create_plate_exclusion(
            request.plate, request.max_distance, user["username"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

@router.get("/api/plate-exclusions")
async def get_exclusions(user: dict = Depends(require_admin)):
    from api.database import get_plate_exclusions
    return get_plate_exclusions()

@router.delete("/api/plate-exclusions/{plate}")
async def delete_exclusion(plate: str, user: dict = Depends(require_admin)):
    from api.database import remove_plate_exclusion
    return remove_plate_exclusion(plate)
