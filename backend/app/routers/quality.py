from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from app import schemas
from app.mock_data.crops import CROP_BY_NAME
from app.services.quality_grading import analyze_image, no_image_fallback, InvalidImageError

router = APIRouter(prefix="/quality", tags=["quality"])


@router.post("/analyze")
async def analyze_quality_image(crop: str = Form(...), image: UploadFile = File(...)):
    """
    Real image-upload quality assessment. The uploaded file's actual bytes
    are read and analyzed (see app/services/quality_grading.py) -- nothing
    here is derived from the filename or crop name alone.
    """
    if crop not in CROP_BY_NAME:
        raise HTTPException(status_code=404, detail="Unknown crop")

    content = await image.read()
    try:
        from app.services.quality_grading import validate_upload
        validate_upload(image.content_type, len(content))
        result = analyze_image(crop, content)
    except InvalidImageError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


@router.post("/grade")
def grade_quality_legacy(payload: schemas.QualityGradeRequest):
    """
    Legacy no-image endpoint, kept for backward compatibility. Always
    returns an explicit "no image provided" placeholder rather than
    fabricating a result from the crop name/filename -- use POST
    /quality/analyze with a real uploaded photo instead.
    """
    if payload.crop not in CROP_BY_NAME:
        raise HTTPException(status_code=404, detail="Unknown crop")
    return no_image_fallback(payload.crop)
