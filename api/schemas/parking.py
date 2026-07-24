from typing import Optional

from pydantic import BaseModel


class CarEntry(BaseModel):
    plate: str
    isEvent: bool = False
    eventFee: Optional[float] = None
    imagePath: Optional[str] = None


class PlateCorrectionRequest(BaseModel):
    plate: str


class ReviewStatusRequest(BaseModel):
    status: str
