from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from app.telegram_service import (
    BOT_TOKEN,
    ADMIN_TELEGRAM_ID,
    MINI_APP_URL,
    TELEGRAM_API_BASE,
    send_telegram_message,
    setup_bot_menu_button,
    validate_init_data,
)
from app.schemas import NotifyRequest

router = APIRouter(prefix="/bot", tags=["Telegram Bot"])


class SetupMenuRequest(BaseModel):
    web_app_url: Optional[str] = None


class ValidateInitDataRequest(BaseModel):
    init_data: str


@router.get("/info")
async def get_bot_info():
    url = f"{TELEGRAM_API_BASE}/getMe"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            data = resp.json()
            return {
                "ok": data.get("ok", False),
                "bot_info": data.get("result", {}),
                "admin_id": ADMIN_TELEGRAM_ID,
                "configured_mini_app_url": MINI_APP_URL,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to communicate with Telegram: {e}")


@router.post("/setup-menu")
async def update_menu_button(payload: SetupMenuRequest):
    success = await setup_bot_menu_button(payload.web_app_url)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set Telegram chat menu button")
    return {"ok": True, "message": "Chat menu button updated successfully"}


@router.post("/notify")
async def notify_user(payload: NotifyRequest):
    success = await send_telegram_message(
        chat_id=payload.telegram_id,
        text=payload.message,
        parse_mode=payload.parse_mode or "Markdown",
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send Telegram message")
    return {"ok": True, "message": "Notification dispatched"}


@router.post("/validate-init-data")
async def validate_telegram_init_data(payload: ValidateInitDataRequest):
    user_info = validate_init_data(payload.init_data)
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid Telegram initData signature")
    return {"ok": True, "user": user_info}
