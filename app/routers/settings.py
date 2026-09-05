import hashlib
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, StoreSetting
from app.schemas import (
    StoreSettingsResponse,
    StoreSettingsUpdate,
    AdminLoginRequest,
    AdminChangePasswordRequest,
)
from app.websocket_manager import ws_manager

router = APIRouter(tags=["Store Settings & Auth"])

SALT = "minishop_salt_"


def hash_password(pwd: str) -> str:
    return hashlib.sha256((SALT + pwd).encode("utf-8")).hexdigest()


async def get_setting_value(db: AsyncSession, key: str, default: str = "") -> str:
    result = await db.execute(select(StoreSetting).where(StoreSetting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


async def set_setting_value(db: AsyncSession, key: str, value: str):
    result = await db.execute(select(StoreSetting).where(StoreSetting.key == key))
    setting = result.scalar_one_or_none()
    if not setting:
        setting = StoreSetting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
    await db.commit()


@router.get("/settings", response_model=StoreSettingsResponse)
async def get_store_settings(db: AsyncSession = Depends(get_db)):
    """Fetch public store branding info: store name, logo, and tagline."""
    store_name = await get_setting_value(db, "store_name", "Mini Shop")
    store_logo = await get_setting_value(db, "store_logo", "🛍")
    store_tagline = await get_setting_value(db, "store_tagline", "Store Admin")
    admin_username = await get_setting_value(db, "admin_username", "admin")

    return StoreSettingsResponse(
        store_name=store_name,
        store_logo=store_logo,
        store_tagline=store_tagline,
        admin_username=admin_username,
    )


@router.put("/settings", response_model=StoreSettingsResponse)
async def update_store_settings(
    payload: StoreSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update store branding (name logo, logo image/icon, tagline)."""
    if payload.store_name is not None:
        await set_setting_value(db, "store_name", payload.store_name.strip())
    if payload.store_logo is not None:
        await set_setting_value(db, "store_logo", payload.store_logo.strip())
    if payload.store_tagline is not None:
        await set_setting_value(db, "store_tagline", payload.store_tagline.strip())

    store_name = await get_setting_value(db, "store_name", "Mini Shop")
    store_logo = await get_setting_value(db, "store_logo", "🛍")
    store_tagline = await get_setting_value(db, "store_tagline", "Store Admin")
    admin_username = await get_setting_value(db, "admin_username", "admin")

    # Broadcast real-time branding update to both Admin and User apps
    await ws_manager.broadcast("SETTINGS_UPDATED", {
        "store_name": store_name,
        "store_logo": store_logo,
        "store_tagline": store_tagline,
    })

    return StoreSettingsResponse(
        store_name=store_name,
        store_logo=store_logo,
        store_tagline=store_tagline,
        admin_username=admin_username,
    )


@router.post("/auth/login")
async def admin_login(
    payload: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate store administrator."""
    username = payload.username.strip()
    password = payload.password

    admin_username = await get_setting_value(db, "admin_username", "admin")
    stored_hash = await get_setting_value(
        db,
        "admin_password_hash",
        hash_password("admin123"),
    )

    if username != admin_username:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    input_hash = hash_password(password)
    if input_hash != stored_hash:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    store_name = await get_setting_value(db, "store_name", "Mini Shop")
    store_logo = await get_setting_value(db, "store_logo", "🛍")

    return {
        "success": True,
        "token": f"admin_session_{hashlib.sha256((username + input_hash).encode()).hexdigest()[:24]}",
        "username": admin_username,
        "store_name": store_name,
        "store_logo": store_logo,
    }


@router.post("/auth/change-password")
async def change_admin_password(
    payload: AdminChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update admin password."""
    stored_hash = await get_setting_value(
        db,
        "admin_password_hash",
        hash_password("admin123"),
    )

    if hash_password(payload.current_password) != stored_hash:
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(payload.new_password.strip()) < 4:
        raise HTTPException(status_code=400, detail="New password must be at least 4 characters")

    new_hash = hash_password(payload.new_password.strip())
    await set_setting_value(db, "admin_password_hash", new_hash)

    return {"success": True, "message": "Password changed successfully"}
