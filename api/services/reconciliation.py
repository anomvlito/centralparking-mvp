from api.database import (
    add_plate_exclusion,
    auto_reconcile_exact_matches,
    consolidate_fuzzy_sightings,
    dismiss_detection_event,
    get_detection_events,
    get_parking_stays,
    get_stay_proposals,
    reconcile_detection_events,
    set_detection_direction,
)
from api.schemas.reconciliation import ReconcileStayRequest


def list_detections(limit=100, match_status=None, date=None):
    return get_detection_events(
        limit=limit, match_status=match_status, date=date
    )


def list_stays(limit=100, status=None, date=None, plate=None):
    return get_parking_stays(
        limit=limit, status=status, date=date, plate=plate
    )

def list_proposals(date, limit=100):
    return get_stay_proposals(date=date, limit=limit)

def reconcile_exact(date, limit=200):
    return auto_reconcile_exact_matches(date=date, limit=limit)


def consolidate_fuzzy(date, limit=500):
    return consolidate_fuzzy_sightings(date=date, limit=limit)

def create_plate_exclusion(plate, max_distance, username):
    return add_plate_exclusion(plate, max_distance, username)


def reconcile_stay(request: ReconcileStayRequest):
    return reconcile_detection_events(
        entry_detection_id=request.entry_detection_id,
        exit_detection_id=request.exit_detection_id,
        resolved_plate=request.resolved_plate,
    )


def dismiss_detection(detection_id: int):
    return dismiss_detection_event(detection_id)


def set_direction(detection_id: int, direction: str):
    return set_detection_direction(detection_id, direction)
