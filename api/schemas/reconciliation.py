from typing import Literal

from pydantic import BaseModel, Field


class ReconcileStayRequest(BaseModel):
    entry_detection_id: int = Field(gt=0)
    exit_detection_id: int = Field(gt=0)
    resolved_plate: str = Field(min_length=1, max_length=20)


class DetectionActionRequest(BaseModel):
    action: Literal["dismiss"]


class PlateExclusionRequest(BaseModel):
    plate: str = Field(min_length=1, max_length=20)
    max_distance: int = Field(default=1, ge=0, le=2)
