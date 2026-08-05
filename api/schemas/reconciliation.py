from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ReconcileStayRequest(BaseModel):
    entry_detection_id: int = Field(gt=0)
    exit_detection_id: int = Field(gt=0)
    resolved_plate: str = Field(min_length=1, max_length=20)


class DetectionActionRequest(BaseModel):
    action: Literal["dismiss", "set_direction"]
    direction: Optional[Literal["APPROACHING", "DEPARTING", "UNKNOWN"]] = None

    @model_validator(mode="after")
    def _require_direction_for_set_direction(self) -> "DetectionActionRequest":
        if self.action == "set_direction" and self.direction is None:
            raise ValueError("direction is required when action is set_direction")
        return self


class PlateExclusionRequest(BaseModel):
    plate: str = Field(min_length=1, max_length=20)
    max_distance: int = Field(default=1, ge=0, le=2)
