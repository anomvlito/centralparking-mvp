from fastapi import APIRouter, File, UploadFile

from api.services.detection import detect_image

router = APIRouter(tags=["detection"])


@router.post("/api/detect")
async def detect(image: UploadFile = File(...)):
    try:
        return detect_image(await image.read())
    except Exception as exc:
        return {"plate": None, "error": str(exc)}
