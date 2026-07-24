from typing import Optional

from fastapi import APIRouter, HTTPException

from api.database import load_db
from api.schemas.parking import CarEntry
from api.services.parking import (
    register_entry,
    register_exit,
    void_parked_vehicle,
)

router = APIRouter(tags=["parking"])


@router.get("/api/cars")
async def get_cars():
    return load_db()


@router.post("/api/entry")
async def entry(entry_request: CarEntry):
    return register_entry(entry_request)


@router.post("/api/exit/{plate}")
async def exit_car(
    plate: str, fee: float = 0, image_path: Optional[str] = None
):
    try:
        return register_exit(plate, fee=fee, image_path=image_path)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/api/cars/{plate}")
async def delete_car(plate: str):
    return void_parked_vehicle(plate)
