from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, Category
from app.schemas import CategoryResponse, CategoryCreate, CategoryUpdate
from app.websocket_manager import ws_manager

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("", response_model=List[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.id.asc()))
    return result.scalars().all()


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(payload: CategoryCreate, db: AsyncSession = Depends(get_db)):
    # Check if slug exists
    existing = await db.execute(select(Category).where(Category.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Category slug already exists")

    cat = Category(**payload.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)

    try:
        await ws_manager.broadcast("CATEGORY_UPDATED", {"action": "create", "category_id": cat.id})
    except Exception as ws_err:
        print(f"WebSocket broadcast warning: {ws_err}")

    return cat


@router.put("/{cat_id}", response_model=CategoryResponse)
async def update_category(cat_id: int, payload: CategoryUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(cat, field, val)

    await db.commit()
    await db.refresh(cat)

    try:
        await ws_manager.broadcast("CATEGORY_UPDATED", {"action": "update", "category_id": cat.id})
    except Exception as ws_err:
        print(f"WebSocket broadcast warning: {ws_err}")

    return cat


@router.delete("/{cat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(cat_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    await db.delete(cat)
    await db.commit()

    try:
        await ws_manager.broadcast("CATEGORY_UPDATED", {"action": "delete", "category_id": cat_id})
    except Exception as ws_err:
        print(f"WebSocket broadcast warning: {ws_err}")

    return None
