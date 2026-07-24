from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_admin
from api.database import (
    clear_history,
    correct_session_plate,
    get_history,
    get_stats_today,
    review_session,
)
from api.schemas.parking import PlateCorrectionRequest, ReviewStatusRequest

router = APIRouter(tags=["history"])


@router.get("/api/history")
async def api_get_history(limit: int = 50, date: str = None):
    return get_history(limit=min(limit, 2000), date=date)


@router.patch("/api/history/{session_id}/plate")
async def api_correct_plate(
    session_id: int,
    request: PlateCorrectionRequest,
    user: dict = Depends(require_admin),
):
    try:
        return correct_session_plate(
            session_id, request.plate, user["username"]
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(409, str(exc))


@router.patch("/api/history/{session_id}/review")
async def api_review_session(
    session_id: int,
    request: ReviewStatusRequest,
    user: dict = Depends(require_admin),
):
    try:
        return review_session(
            session_id,
            request.status,
            int(user["sub"]),
            user["username"],
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/api/clear-history")
async def api_clear_history():
    clear_history()
    return {"status": "cleared"}


@router.get("/api/stats")
async def get_stats():
    return get_stats_today()
