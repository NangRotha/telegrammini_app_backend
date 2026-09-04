import os
import time
import shutil
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, User
from app.schemas import UserResponse, UserUpdate
from app.websocket_manager import ws_manager

router = APIRouter(prefix="/users", tags=["Users"])

AVATARS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "avatars"))
os.makedirs(AVATARS_DIR, exist_ok=True)
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@router.get("/{telegram_id}", response_model=UserResponse)
async def get_user_profile(telegram_id: int, db: AsyncSession = Depends(get_db)):
    """Fetch user profile by Telegram ID."""
    result = await db.execute(select(User).where(User.id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        # Return a provisional object if not yet in database
        return UserResponse(
            id=telegram_id,
            username="",
            first_name="",
            last_name="",
            phone="",
            default_address="",
            avatar_url="",
            points=100,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    return user


@router.post("/{telegram_id}/avatar", response_model=UserResponse)
async def upload_user_avatar(
    telegram_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload custom profile avatar for user."""
    filename = file.filename or "avatar.png"
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image format '{ext}'. Allowed: {', '.join(ALLOWED_IMAGE_EXTS)}",
        )

    clean_filename = f"user_{telegram_id}_{int(time.time())}{ext}"
    dest_path = os.path.join(AVATARS_DIR, clean_filename)

    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save avatar image: {str(e)}",
        )
    finally:
        await file.close()

    avatar_url = f"/uploads/avatars/{clean_filename}"

    result = await db.execute(select(User).where(User.id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            id=telegram_id,
            avatar_url=avatar_url,
            points=100,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(user)
    else:
        user.avatar_url = avatar_url
        user.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(user)

    await ws_manager.broadcast("PROFILE_UPDATED", {
        "id": user.id,
        "avatar_url": user.avatar_url,
        "points": user.points,
        "first_name": user.first_name,
        "last_name": user.last_name,
    })

    return user


@router.put("/{telegram_id}", response_model=UserResponse)
async def update_user_profile(
    telegram_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Create or update user profile with contact and delivery information."""
    result = await db.execute(select(User).where(User.id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            id=telegram_id,
            username=payload.username or "",
            first_name=payload.first_name or "",
            last_name=payload.last_name or "",
            phone=payload.phone or "",
            default_address=payload.default_address or "",
            avatar_url=payload.avatar_url or "",
            points=payload.points if payload.points is not None else 100,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(user)
    else:
        if payload.first_name is not None:
            user.first_name = payload.first_name
        if payload.last_name is not None:
            user.last_name = payload.last_name
        if payload.username is not None:
            user.username = payload.username
        if payload.phone is not None:
            user.phone = payload.phone
        if payload.default_address is not None:
            user.default_address = payload.default_address
        if payload.avatar_url is not None:
            user.avatar_url = payload.avatar_url
        if payload.points is not None:
            user.points = payload.points
        user.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(user)

    # Broadcast real-time profile update event
    user_data = {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "default_address": user.default_address,
        "avatar_url": user.avatar_url,
        "points": user.points,
    }
    await ws_manager.broadcast("PROFILE_UPDATED", user_data)

    return user


@router.get("", response_model=List[UserResponse])
async def list_users(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """List customer profiles for admin dashboard."""
    result = await db.execute(select(User).order_by(User.id.desc()).limit(limit))
    return result.scalars().all()
