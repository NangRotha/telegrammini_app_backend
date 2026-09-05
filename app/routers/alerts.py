from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, AlertPopup
from app.schemas import AlertPopupResponse, AlertPopupCreate, AlertPopupUpdate
from app.websocket_manager import ws_manager

router = APIRouter(prefix="/alerts", tags=["Alert Popups"])


@router.get("", response_model=List[AlertPopupResponse])
async def list_alert_popups(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List all promotional & announcement popups for admin dashboard."""
    query = select(AlertPopup)
    if active_only:
        query = query.where(AlertPopup.is_active == True)
    query = query.order_by(AlertPopup.id.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/active", response_model=Optional[AlertPopupResponse])
async def get_active_alert_popup(db: AsyncSession = Depends(get_db)):
    """Fetch the currently active alert popup to display to shoppers in the Mini App."""
    query = select(AlertPopup).where(AlertPopup.is_active == True).order_by(AlertPopup.id.desc()).limit(1)
    result = await db.execute(query)
    popup = result.scalar_one_or_none()
    return popup


@router.post("", response_model=AlertPopupResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_popup(
    payload: AlertPopupCreate,
    db: AsyncSession = Depends(get_db),
):
    """Admin creates a new alert popup."""
    popup = AlertPopup(**payload.model_dump())
    db.add(popup)
    await db.commit()
    await db.refresh(popup)

    await ws_manager.broadcast("ALERT_UPDATED", {
        "action": "create",
        "id": popup.id,
        "is_active": popup.is_active,
    })
    return popup


@router.put("/{popup_id}", response_model=AlertPopupResponse)
async def update_alert_popup(
    popup_id: int,
    payload: AlertPopupUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Admin updates an alert popup or toggles is_active."""
    result = await db.execute(select(AlertPopup).where(AlertPopup.id == popup_id))
    popup = result.scalar_one_or_none()
    if not popup:
        raise HTTPException(status_code=404, detail="Alert popup not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(popup, field, val)

    popup.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(popup)

    await ws_manager.broadcast("ALERT_UPDATED", {
        "action": "update",
        "id": popup.id,
        "is_active": popup.is_active,
    })
    return popup


@router.delete("/{popup_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_popup(
    popup_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Admin deletes an alert popup."""
    result = await db.execute(select(AlertPopup).where(AlertPopup.id == popup_id))
    popup = result.scalar_one_or_none()
    if not popup:
        raise HTTPException(status_code=404, detail="Alert popup not found")

    await db.delete(popup)
    await db.commit()

    await ws_manager.broadcast("ALERT_UPDATED", {
        "action": "delete",
        "id": popup_id,
    })
    return None
