import os
import time
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from app.config import IMAGES_DIR, VIDEOS_DIR, ensure_upload_dirs

router = APIRouter(prefix="/upload", tags=["Upload"])

ensure_upload_dirs()

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
ALLOWED_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".mkv"}


@router.post("")
async def upload_file(file: UploadFile = File(...)):
    """Upload an image or video file from local PC."""
    filename = file.filename or "upload"
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext in ALLOWED_IMAGE_EXTS:
        target_dir = IMAGES_DIR
        subfolder = "images"
    elif ext in ALLOWED_VIDEO_EXTS:
        target_dir = VIDEOS_DIR
        subfolder = "videos"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed image formats: {', '.join(ALLOWED_IMAGE_EXTS)}; Allowed video formats: {', '.join(ALLOWED_VIDEO_EXTS)}",
        )

    # Generate unique clean filename
    unique_filename = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
    destination_path = os.path.join(target_dir, unique_filename)

    try:
        with open(destination_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}",
        )
    finally:
        await file.close()

    public_url = f"/uploads/{subfolder}/{unique_filename}"
    return {
        "url": public_url,
        "filename": unique_filename,
        "media_type": "video" if subfolder == "videos" else "image",
    }
