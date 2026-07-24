"""Casos de uso de estacionamiento independientes de FastAPI."""

from api.database import (
    log_to_db,
    now_cl,
    remove_vehicle,
    upsert_vehicle,
    vehicle_exists,
    void_vehicle,
)
from api.schemas.parking import CarEntry


def register_entry(entry: CarEntry) -> dict:
    entry_time = now_cl().timestamp() * 1000
    upsert_vehicle(
        entry.plate,
        entry_time,
        entry.isEvent,
        entry.eventFee,
        image_path=entry.imagePath,
    )
    log_to_db(entry.plate, "ENTRY")
    return {
        "plate": entry.plate,
        "entryTime": entry_time,
        "isEvent": entry.isEvent,
        "eventFee": entry.eventFee,
    }


def register_exit(plate: str, fee: float = 0, image_path: str = None) -> dict:
    if not vehicle_exists(plate):
        raise LookupError("Plate not in parking")
    remove_vehicle(plate, fee=fee, image_path=image_path)
    log_to_db(plate, "EXIT", fee=fee)
    return {"status": "ok"}


def void_parked_vehicle(plate: str) -> dict:
    void_vehicle(plate)
    log_to_db(plate, "VOID")
    return {"status": "voided"}
